"""批处理状态管理模块 - 管理缓存、选择状态"""

import logging
import threading
from functools import partial
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import QApplication, QProgressDialog, QMessageBox

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
        
        Args:
            file_path: 文件路径
            manager_instance: BatchManager 实例（用于访问 GUI 和缓存）
        
        Returns:
            解析后的数据字典 {part_name: DataFrame}
        """
        from src.special_format_parser import parse_special_format_file
        from gui.background_worker import BackgroundWorker
        from gui.signal_bus import SignalBus
        from gui.managers import report_user_error, _report_ui_exception
        
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
            # 安全幂等：如果已有后台解析正在进行，则不重复提交
            in_progress_key = f"_parsing:{fp_str}"
            if getattr(manager_instance, in_progress_key, False):
                return {}
            setattr(manager_instance, in_progress_key, True)

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

            def _on_finished(result):
                try:
                    data_dict = result or {}
                    try:
                        self.special_data_cache[fp_str] = {"mtime": mtime, "data": data_dict}
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
                        logger.debug("发出 specialDataParsed 信号失败（非致命）", exc_info=True)
                finally:
                    try:
                        setattr(manager_instance, in_progress_key, False)
                    except Exception:
                        logger.debug("设置解析进行标志失败（非致命）", exc_info=True)
                    try:
                        worker.deleteLater()
                    except Exception:
                        logger.debug("清理 worker 失败（非致命）", exc_info=True)
                    try:
                        thread.quit()
                        thread.wait(1000)
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
                try:
                    setattr(manager_instance, in_progress_key, False)
                    worker.deleteLater()
                    thread.quit()
                    thread.wait(1000)
                except Exception:
                    logger.debug("清理失败（错误路径）", exc_info=True)

            worker.finished.connect(_on_finished)
            worker.error.connect(_on_error)
            thread.started.connect(worker.run)
            thread.start()
        except Exception as e:
            logger.warning("无法用 QThread 启动后台解析，尝试回退：%s", e, exc_info=True)
            try:
                result_holder = {}
                done_event = threading.Event()

                def _worker():
                    try:
                        result_holder["data"] = parse_special_format_file(file_path)
                    except Exception as ex:
                        result_holder["exc"] = ex
                    finally:
                        done_event.set()

                thr = threading.Thread(target=_worker, daemon=True)
                thr.start()

                try:
                    dlg = QProgressDialog("正在解析特殊格式…", "取消", 0, 0, manager_instance.gui)
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
                try:
                    while not done_event.wait(0.1):
                        if cancel_requested[0]:
                            logger.info("用户取消了特殊格式解析")
                            user_cancelled = True
                            break
                        try:
                            QApplication.processEvents()
                        except Exception:
                            logger.debug("处理 GUI 事件时出错（轮询线程）", exc_info=True)
                finally:
                    try:
                        if dlg is not None:
                            dlg.close()
                    except Exception:
                        logger.debug("关闭解析等待对话失败（非致命）", exc_info=True)

                if user_cancelled:
                    logger.info("等待后台解析线程结束...")
                    try:
                        thr.join(timeout=2.0)
                        if thr.is_alive():
                            logger.warning("后台解析线程未能及时结束，但已取消用户等待")
                    except Exception:
                        logger.debug("等待线程结束时出错", exc_info=True)
                    return None

                if "data" in result_holder:
                    data_dict = result_holder.get("data") or {}
                    try:
                        self.special_data_cache[fp_str] = {"mtime": mtime, "data": data_dict}
                    except Exception:
                        logger.debug("写入特殊格式缓存失败（非致命）", exc_info=True)
                    return data_dict

                logger.warning("Python 线程解析失败或抛出异常，回退到同步解析")
                _report_ui_exception(
                    manager_instance.gui,
                    "后台解析特殊格式时发生错误，已回退到同步解析",
                )
            except Exception:
                logger.warning("无法启动 Python 后台线程，回退到主线程同步解析", exc_info=True)

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
                    self.special_data_cache[fp_str] = {"mtime": mtime, "data": data_dict}
                except Exception:
                    logger.debug("写入特殊格式缓存失败（同步回退，非致命）", exc_info=True)
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
        from src.utils import read_table_preview
        from gui.managers import report_user_error
        
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
