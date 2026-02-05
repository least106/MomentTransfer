"""批处理状态管理模块 - 管理缓存、选择状态"""

import logging
import threading
from functools import partial
from pathlib import Path
from typing import Dict

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

logger = logging.getLogger(__name__)


class BatchStateManager:
    """管理批处理的所有状态和缓存"""

    def __init__(self):
        """初始化状态管理器"""
        # 特殊格式：缓存解析结果
        # key: file_path_str -> {"mtime": float, "data": Dict[str, DataFrame]}
        self.special_data_cache: Dict = {}

        # 常规表格（CSV/Excel）：缓存预览数据
        # key: file_path_str -> {"mtime": float, "df": DataFrame, "preview_rows": int}
        self.table_data_cache: Dict = {}

    def get_special_data_dict(self, file_path: Path, manager_instance):
        """获取特殊格式解析结果（带 mtime 缓存）

        改进的解析状态管理：
        1. 添加超时机制防止长期占用
        2. 改进错误处理，确保 flag 总是被清除
        3. 检测并清除超时的解析任务

        Args:
            file_path: 文件路径
            manager_instance: BatchManager 实例（用于访问 GUI 和缓存）

        Returns:
            解析后的数据字典 {part_name: DataFrame}，若解析中返回 {}
        """
        from gui.background_worker import BackgroundWorker
        from gui.managers import _report_ui_exception, report_user_error
        from gui.signal_bus import SignalBus
        from src.special_format_parser import parse_special_format_file

        fp_str = str(file_path)
        try:
            mtime = file_path.stat().st_mtime
        except Exception:
            mtime = None

        cached = self.special_data_cache.get(fp_str)
        if cached and cached.get("mtime") == mtime and cached.get("data") is not None:
            return cached.get("data")

        # 异步解析以避免阻塞主线程
        try:
            # 改进的幂等性检查：同时检查超时
            in_progress_key = f"_parsing:{fp_str}"
            parsing_timeout_key = f"_parsing_timeout:{fp_str}"

            # 检查是否有超时的解析任务（需要清除 flag）
            import time

            now = time.time()
            parsing_start_time = getattr(manager_instance, parsing_timeout_key, None)

            if getattr(manager_instance, in_progress_key, False):
                # 如果解析已经超过5分钟，强制清除 flag
                if parsing_start_time and now - parsing_start_time > 300:
                    logger.warning(
                        "检测到超时的特殊格式解析任务（5分钟以上），强制清除 flag: %s",
                        fp_str,
                    )
                    setattr(manager_instance, in_progress_key, False)
                    setattr(manager_instance, parsing_timeout_key, None)
                    # 清除超时 flag 后，继续允许重新解析（不返回空 dict）
                    # 这样用户可以重新尝试该文件
                else:
                    # 解析仍在进行中（且未超时），返回空 dict 等待
                    return {}

            # 标记解析开始
            setattr(manager_instance, in_progress_key, True)
            setattr(manager_instance, parsing_timeout_key, now)

            # 显示加载指示器
            try:
                if hasattr(manager_instance.gui, "statusBar"):
                    manager_instance.gui.statusBar().showMessage(
                        f"正在解析特殊格式文件: {file_path.name}...", 0
                    )
            except Exception:
                logger.debug("显示解析状态栏消息失败（非致命）", exc_info=True)

            def _do_parse(path: Path):
                return parse_special_format_file(path)

            thread = QThread()
            worker = BackgroundWorker(partial(_do_parse, file_path))
            worker.moveToThread(thread)

            def _cleanup_flags():
                """清除解析标志"""
                try:
                    setattr(manager_instance, in_progress_key, False)
                    setattr(manager_instance, parsing_timeout_key, None)
                except Exception:
                    logger.debug("清除解析标志失败（非致命）", exc_info=True)

            def _on_finished(result):
                try:
                    data_dict = result or {}
                    try:
                        self.special_data_cache[fp_str] = {
                            "mtime": mtime,
                            "data": data_dict,
                        }
                    except Exception:
                        logger.debug("更新特殊格式缓存失败（非致命）", exc_info=True)
                    try:
                        if hasattr(manager_instance.gui, "statusBar"):
                            manager_instance.gui.statusBar().showMessage(
                                f"特殊格式文件解析完成: {file_path.name}", 3000
                            )
                    except Exception:
                        logger.debug("清除状态栏消息失败（非致命）", exc_info=True)
                    try:
                        SignalBus.instance().specialDataParsed.emit(fp_str)
                    except Exception:
                        logger.debug(
                            "发出 specialDataParsed 信号失败（非致命）", exc_info=True
                        )
                finally:
                    _cleanup_flags()
                    try:
                        worker.deleteLater()
                    except Exception:
                        logger.debug("清理 worker 失败（非致命）", exc_info=True)
                    try:
                        # 确保线程被完全清理
                        thread.quit()
                        if not thread.wait(2000):  # 增加等待时间到2秒
                            logger.warning("线程未能在超时时间内停止，强制结束")
                        thread.deleteLater()  # 确保线程对象也被删除
                    except Exception:
                        logger.debug("停止后台线程失败（非致命）", exc_info=True)

            def _on_error(tb_str):
                logger.error("后台解析特殊格式失败: %s", tb_str)
                try:
                    if hasattr(manager_instance.gui, "statusBar"):
                        manager_instance.gui.statusBar().showMessage(
                            f"解析特殊格式文件失败: {file_path.name}", 5000
                        )
                    QMessageBox.warning(
                        manager_instance.gui,
                        "解析失败",
                        f"无法解析特殊格式文件：\n{file_path.name}\n\n"
                        f"错误信息：\n{tb_str[:200]}...\n\n"
                        "请检查文件格式是否正确。",
                    )
                except Exception:
                    logger.debug("显示解析错误提示失败", exc_info=True)
                finally:
                    # 关键：在错误处理中也要清除 flag
                    _cleanup_flags()
                    try:
                        worker.deleteLater()
                    except Exception:
                        logger.debug("清理 worker 失败（错误路径）", exc_info=True)
                    try:
                        thread.quit()
                        thread.wait(1000)
                    except Exception:
                        logger.debug("停止后台线程失败（错误路径）", exc_info=True)

            worker.finished.connect(_on_finished)
            worker.error.connect(_on_error)
            thread.started.connect(worker.run)
            thread.start()
        except Exception as e:
            logger.warning(
                "无法用 QThread 启动后台解析，尝试回退：%s", e, exc_info=True
            )
            # 在异常处理中也要清除 flag（确保状态一致）
            in_progress_key = f"_parsing:{fp_str}"
            parsing_timeout_key = f"_parsing_timeout:{fp_str}"
            try:
                setattr(manager_instance, in_progress_key, False)
                setattr(manager_instance, parsing_timeout_key, None)
            except Exception:
                logger.debug("清除解析标志失败（异常处理路径，非致命）", exc_info=True)

            # Python threading 回退 - 添加明确的超时机制
            try:
                result_holder = {}
                done_event = threading.Event()

                def _worker():
                    try:
                        result_holder["data"] = parse_special_format_file(file_path)
                    except Exception as ex:
                        result_holder["exc"] = ex
                        logger.debug("Python 线程解析异常: %s", ex, exc_info=True)
                    finally:
                        done_event.set()

                thr = threading.Thread(target=_worker, daemon=True)
                thr.start()

                # 显示进度对话框
                try:
                    dlg = QProgressDialog(
                        "正在解析特殊格式…", "取消", 0, 0, manager_instance.gui
                    )
                    dlg.setWindowModality(Qt.NonModal)
                    dlg.setMaximumWidth(400)
                    cancel_requested = [False]

                    def _on_cancel():
                        cancel_requested[0] = True

                    dlg.canceled.connect(_on_cancel)
                    dlg.setMinimumDuration(500)
                    dlg.show()
                except Exception:
                    dlg = None
                    cancel_requested = [False]

                user_cancelled = False
                timeout_reached = False
                timeout_seconds = 60  # 60 秒超时
                import time as time_module

                timeout_start = time_module.time()

                try:
                    while not done_event.wait(0.1):
                        # 检查超时
                        if time_module.time() - timeout_start > timeout_seconds:
                            logger.warning(
                                "特殊格式解析线程超时（%d 秒），放弃等待",
                                timeout_seconds,
                            )
                            timeout_reached = True
                            break

                        # 检查用户取消
                        if cancel_requested[0]:
                            logger.info("用户取消了特殊格式解析")
                            user_cancelled = True
                            break

                        # 处理 GUI 事件
                        try:
                            QApplication.processEvents()
                        except Exception:
                            logger.debug(
                                "处理 GUI 事件时出错（轮询线程）", exc_info=True
                            )
                finally:
                    try:
                        if dlg is not None:
                            dlg.close()
                    except Exception:
                        logger.debug("关闭解析等待对话失败（非致命）", exc_info=True)

                # 处理用户取消的情况
                if user_cancelled:
                    logger.info("等待后台解析线程结束...")
                    try:
                        thr.join(timeout=2.0)
                        if thr.is_alive():
                            logger.warning("后台解析线程未能及时结束，但已取消用户等待")
                    except Exception:
                        logger.debug("等待线程结束时出错", exc_info=True)
                    return {}

                # 处理超时的情况
                if timeout_reached:
                    try:
                        thr.join(timeout=1.0)
                        if thr.is_alive():
                            logger.error(
                                "后台解析线程仍在运行（后台继续执行），返回空结果"
                            )
                    except Exception:
                        logger.debug("等待线程结束时出错（超时路径）", exc_info=True)

                    # 显示超时警告
                    try:
                        report_user_error(
                            manager_instance.gui,
                            "解析超时",
                            f"解析文件 {file_path.name} 超过 {timeout_seconds} 秒，已取消。\n\n"
                            "您可以稍后重试或联系技术支持。",
                            is_warning=True,
                        )
                    except Exception:
                        logger.debug("显示超时警告失败（非致命）", exc_info=True)
                    return {}

                # 处理解析完成的情况
                if "data" in result_holder:
                    data_dict = result_holder.get("data") or {}
                    try:
                        self.special_data_cache[fp_str] = {
                            "mtime": mtime,
                            "data": data_dict,
                        }
                    except Exception:
                        logger.debug("写入特殊格式缓存失败（非致命）", exc_info=True)
                    return data_dict

                # 没有返回结果
                logger.warning("Python 线程解析完成但无结果，回退到同步解析")
                _report_ui_exception(
                    manager_instance.gui,
                    "后台解析特殊格式时无法获得结果，已回退到同步解析",
                )
            except Exception as thread_ex:
                logger.warning(
                    "无法启动 Python 后台线程，回退到主线程同步解析: %s",
                    thread_ex,
                    exc_info=True,
                )

            # 同步解析（在主线程执行）
            try:
                try:
                    manager_instance.gui.statusBar().showMessage(
                        f"正在解析特殊格式：{file_path.name}…", 0
                    )
                except Exception:
                    logger.debug("显示状态栏消息失败（非致命）", exc_info=True)

                try:
                    QApplication.processEvents()
                except Exception:
                    logger.debug("处理 GUI 事件时出错（同步解析）", exc_info=True)
            except Exception:
                pass

            try:
                data_dict = parse_special_format_file(file_path)
                try:
                    self.special_data_cache[fp_str] = {
                        "mtime": mtime,
                        "data": data_dict,
                    }
                except Exception:
                    logger.debug(
                        "写入特殊格式缓存失败（同步回退，非致命）", exc_info=True
                    )
                try:
                    manager_instance.gui.statusBar().showMessage("", 0)
                except Exception:
                    logger.debug("清除状态栏消息失败（非致命）", exc_info=True)
                return data_dict
            except Exception as ex:
                report_user_error(
                    manager_instance.gui,
                    "解析特殊格式失败",
                    f"无法解析文件 {file_path.name}，已跳过",
                    details=str(ex),
                    is_warning=True,
                )
                try:
                    self.special_data_cache[fp_str] = {"mtime": mtime, "data": {}}
                except Exception:
                    logger.debug("写入空特殊格式缓存失败（非致命）", exc_info=True)

        return {}

    def get_table_df_preview(self, file_path: Path, gui_instance, max_rows: int = 200):
        """读取 CSV/Excel 的预览数据（带 mtime 缓存）

        Args:
            file_path: 文件路径
            gui_instance: GUI 主窗口实例
            max_rows: 最大预览行数

        Returns:
            DataFrame 或 None
        """
        import pandas as pd

        from gui.managers import report_user_error
        from src.utils import read_table_preview

        fp_str = str(file_path)
        try:
            mtime = file_path.stat().st_mtime
        except Exception:
            mtime = None

        cached = self.table_data_cache.get(fp_str)
        if (
            cached
            and cached.get("mtime") == mtime
            and cached.get("df") is not None
            and cached.get("preview_rows") == int(max_rows)
        ):
            return cached.get("df")

        try:
            df = read_table_preview(file_path, int(max_rows))
        except (
            FileNotFoundError,
            PermissionError,
            OSError,
            pd.errors.ParserError,
        ) as e:
            report_user_error(
                gui_instance,
                "读取表格预览失败",
                f"无法读取文件预览（{type(e).__name__}）",
                details=str(e),
                is_warning=True,
            )
            df = None
        except Exception:
            logger.debug("读取表格预览失败（非致命）", exc_info=True)
            df = None

        self.table_data_cache[fp_str] = {
            "mtime": mtime,
            "df": df,
            "preview_rows": int(max_rows),
        }
        return df

    def validate_special_format(self, manager_instance, file_path: Path):
        """对特殊格式文件进行预检，返回状态文本或 None 表示非特殊格式

        状态符号说明：
        - ✓ 特殊格式(可处理)：所有 parts 映射已完成，文件可以处理
        - ✓ 特殊格式(待配置)：项目尚未配置 parts，但文件格式正确
        - ⚠ 未映射: part1, part2：指定的 parts 尚未配置映射关系
        - ⚠ Source缺失: part→source：指定的 Source 不在项目配置中
        - ⚠ Target缺失: part→target：指定的 Target 不在项目配置中
        - ❓ 未验证：验证过程出错，无法判断文件状态

        Args:
            manager_instance: BatchManager 实例
            file_path: 要验证的文件路径

        Returns:
            str | None: 状态文本，None 表示非特殊格式
        """
        from src.special_format_detector import looks_like_special_format
        from src.special_format_parser import get_part_names

        status = None
        try:
            if not looks_like_special_format(file_path):
                status = None
            else:
                part_names = get_part_names(file_path)
                mapping = manager_instance._get_special_mapping_if_exists(file_path)
                source_parts, target_parts = manager_instance._get_project_parts()

                # 若项目中无 parts 则提示待配置
                if not source_parts and not target_parts:
                    status = "✓ 特殊格式(待配置)"
                else:
                    mapping = mapping or {}

                    # 检查新的映射结构：每个内部部件 -> {source, target}
                    unmapped_parts = []
                    missing_source_parts = []
                    missing_target_parts = []

                    for part_name in part_names:
                        part_name_str = str(part_name)
                        part_mapping = mapping.get(part_name_str)

                        if not isinstance(part_mapping, dict):
                            # 兼容旧格式或未映射
                            unmapped_parts.append(part_name_str)
                            continue

                        source_part = (part_mapping.get("source") or "").strip()
                        target_part = (part_mapping.get("target") or "").strip()

                        # 检查source part
                        if not source_part:
                            unmapped_parts.append(part_name_str)
                        elif source_part not in source_parts:
                            missing_source_parts.append(
                                f"{part_name_str}→{source_part}"
                            )

                        # 检查target part
                        if not target_part:
                            if source_part:  # 只有当source已选择时才检查target
                                unmapped_parts.append(part_name_str)
                        elif target_part not in target_parts:
                            missing_target_parts.append(
                                f"{part_name_str}→{target_part}"
                            )

                    if unmapped_parts:
                        status = f"⚠ 未映射: {', '.join(unmapped_parts)}"
                    elif missing_source_parts:
                        status = f"⚠ Source缺失: {', '.join(missing_source_parts)}"
                    elif missing_target_parts:
                        status = f"⚠ Target缺失: {', '.join(missing_target_parts)}"
                    else:
                        status = "✓ 特殊格式(可处理)"
        except Exception:
            logger.debug("特殊格式校验失败", exc_info=True)
            status = None

        return status

    def ensure_special_mapping_rows(self, manager_instance, file_item, file_path: Path):
        """在文件节点下创建/刷新子节点：每个内部部件一行，包含source和target两个下拉框

        Args:
            manager_instance: BatchManager 实例
            file_item: 文件树节点
            file_path: 文件路径
        """
        from src.special_format_parser import get_part_names

        try:
            mapping = manager_instance._get_or_init_special_mapping(file_path)
            mapping_by_file = getattr(
                manager_instance.gui, "special_part_mapping_by_file", {}
            )
            mapping_by_file = mapping_by_file or {}
            part_names = get_part_names(file_path)
            source_names = manager_instance._get_source_part_names()
            target_names = manager_instance._get_target_part_names()

            # 智能推测：在加载配置/新增 part 后自动补全未映射项（不覆盖用户已设置的映射）
            try:
                if source_names and target_names:
                    if manager_instance._auto_fill_special_mappings(
                        file_path,
                        part_names,
                        source_names,
                        target_names,
                        mapping,
                    ):
                        mapping_by_file[str(file_path)] = mapping
                        manager_instance.gui.special_part_mapping_by_file = (
                            mapping_by_file
                        )
            except Exception:
                logger.debug("自动补全映射失败", exc_info=True)

            # 行选择缓存：确保存在（首次默认全选）
            manager_instance._ensure_special_row_selection_storage(
                file_path, part_names
            )

            # 特殊格式解析数据：用于生成数据行预览
            data_dict = manager_instance._get_special_data_dict(file_path)

            # 清理旧的子节点与 widget 引用（避免 target part 列表变化后残留）
            for i in range(file_item.childCount() - 1, -1, -1):
                try:
                    child = file_item.child(i)
                    file_item.removeChild(child)
                except Exception:
                    logger.debug("移除子节点失败", exc_info=True)

            for internal_part_name in part_names:
                try:
                    manager_instance._create_special_part_node(
                        file_item,
                        file_path,
                        internal_part_name,
                        source_names,
                        target_names,
                        mapping,
                        data_dict,
                    )
                except Exception:
                    logger.debug("创建 special part 节点失败", exc_info=True)

            try:
                file_item.setExpanded(True)
            except Exception:
                logger.debug("展开文件项失败", exc_info=True)

            # 刷新文件状态（映射模式下会提示未映射/缺失）
            try:
                file_item.setText(1, manager_instance._validate_file_config(file_path))
            except Exception:
                logger.debug("刷新文件状态文本失败", exc_info=True)
        except Exception:
            logger.debug("ensure_special_mapping_rows failed", exc_info=True)

    def determine_part_selection_status(
        self, manager_instance, file_path: Path, project_data
    ):
        """基于 project_data 与当前选择推断该文件的 source/target 状态

        状态符号说明：
        - ✓ 可处理：Source/Target 已完整选择，文件可以处理
        - ✓ 格式正常(待配置)：文件格式正确但项目尚未配置任何 parts
        - ⚠ 未选择 Source/Target：缺少必要的 Source 或 Target 选择
        - ⚠ Source缺失: part：选择的 Source 不在项目配置中
        - ⚠ Target缺失: part：选择的 Target 不在项目配置中
        - ❓ 未验证：验证过程出错，无法判断文件状态

        Args:
            manager_instance: BatchManager 实例
            file_path: 文件路径
            project_data: 项目配置数据

        Returns:
            str: 状态文本
        """
        try:
            sel = (
                getattr(manager_instance.gui, "file_part_selection_by_file", {}) or {}
            ).get(str(file_path)) or {}
            source_sel = (sel.get("source") or "").strip()
            target_sel = (sel.get("target") or "").strip()

            try:
                source_names = list(
                    (getattr(project_data, "source_parts", {}) or {}).keys()
                )
                target_names = list(
                    (getattr(project_data, "target_parts", {}) or {}).keys()
                )
            except Exception:
                source_names, target_names = [], []

            # 允许"唯一 part 自动选取"的兜底
            if not source_sel and len(source_names) == 1:
                source_sel = str(source_names[0])
            if not target_sel and len(target_names) == 1:
                target_sel = str(target_names[0])

            if not source_sel or not target_sel:
                return "⚠ 未选择 Source/Target"
            if source_names and source_sel not in source_names:
                return f"⚠ Source缺失: {source_sel}"
            if target_names and target_sel not in target_names:
                return f"⚠ Target缺失: {target_sel}"
            return "✓ 可处理"
        except Exception:
            logger.debug("确定 part 选择状态失败", exc_info=True)
            return "❓ 未验证"

    def clear_parsing_flag(self, file_path: Path, manager_instance):
        """手动清除卡住的特殊格式文件解析 flag

        当文件解析超时或出现异常且 flag 未被清除时，使用此方法恢复：
        1. 清除 in_progress 标志，允许重新解析
        2. 清除超时计时器
        3. 清除该文件的缓存，强制下次重新解析
        4. 返回恢复是否成功

        Args:
            file_path: 要清除 flag 的文件路径
            manager_instance: BatchManager 实例

        Returns:
            tuple: (success: bool, message: str) - 是否成功清除及描述信息
        """
        fp_str = str(file_path)
        in_progress_key = f"_parsing:{fp_str}"
        parsing_timeout_key = f"_parsing_timeout:{fp_str}"

        try:
            # 检查 flag 是否存在
            was_stuck = getattr(manager_instance, in_progress_key, False)

            # 清除 flag 和超时计时器
            try:
                setattr(manager_instance, in_progress_key, False)
                logger.info("已清除文件 %s 的解析进行 flag", fp_str)
            except Exception as e:
                logger.error("清除解析进行 flag 失败: %s", e)
                return False, f"清除解析标志失败: {e}"

            try:
                setattr(manager_instance, parsing_timeout_key, None)
                logger.info("已清除文件 %s 的超时计时器", fp_str)
            except Exception as e:
                logger.error("清除超时计时器失败: %s", e)
                return False, f"清除超时计时器失败: {e}"

            # 清除缓存，强制下次重新解析
            try:
                if fp_str in self.special_data_cache:
                    del self.special_data_cache[fp_str]
                    logger.info("已清除文件 %s 的特殊格式缓存", fp_str)
            except Exception as e:
                logger.error("清除缓存失败: %s", e)
                return False, f"清除缓存失败: {e}"

            # 返回恢复信息
            if was_stuck:
                msg = f"已恢复文件 {file_path.name} 的解析状态，可以重新尝试解析"
                logger.info(msg)
                return True, msg
            else:
                msg = f"文件 {file_path.name} 未卡住，但已清除缓存以确保重新解析"
                logger.info(msg)
                return True, msg

        except Exception as e:
            logger.error("清除解析 flag 时发生未预期的错误: %s", e, exc_info=True)
            return False, f"清除失败：{e}"
