"""
Project 管理器 - 处理 MomentTransfer 项目文件的保存与恢复
"""

import base64
import json
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)
try:
    # 非强制依赖：仅用于在 GUI 环境下启动异步线程
    from PySide6.QtCore import Qt, QThread, Signal
except Exception:
    QThread = None
    Signal = None
    Qt = None

try:
    from gui.managers import _report_ui_exception
except Exception:
    _report_ui_exception = None


class ProjectManager:
    """管理 Project 文件的加载、保存和恢复"""

    PROJECT_VERSION = "1.0"
    PROJECT_FILE_EXTENSION = ".mtproject"

    def __init__(self, gui_instance):
        """初始化 ProjectManager

        Args:
            gui_instance: 主窗口实例
        """
        self.gui = gui_instance
        self.current_project_file: Optional[Path] = None
        self.last_saved_state: Optional[Dict] = None
        # 后台任务引用（防止被GC），支持同时保留多个并在完成后清理
        self._background_workers = []

    def _notify_user_error(
        self, title: str, message: str, details: Optional[str] = None
    ) -> None:
        """在 GUI 环境中向用户展示错误对话框；在无 GUI 时记录日志。

        只用于关键路径的用户可见提示，内部细节应记录到日志。
        """
        try:
            from PySide6.QtWidgets import QMessageBox

            try:
                msg = QMessageBox(self.gui)
                msg.setWindowTitle(title)
                msg.setText(message)
                if details:
                    msg.setDetailedText(details)
                msg.exec()
                return
            except Exception:
                logger.debug("显示错误对话框失败", exc_info=True)
        except Exception:
            # 无 Qt 环境或导入失败，回退为日志记录
            pass

        if details:
            logger.error("%s: %s\n%s", title, message, details)
        else:
            logger.error("%s: %s", title, message)

    def create_new_project(self) -> bool:
        """创建新项目（清除当前工作状态）"""
        try:
            # 清除当前项目路径/状态
            self.current_project_file = None
            self.last_saved_state = None

            # 重置工作流程到初始步骤（若有 BatchManager）
            try:
                if hasattr(self.gui, "batch_manager") and self.gui.batch_manager:
                    try:
                        self.gui.batch_manager._set_workflow_step("init")
                    except Exception:
                        logger.debug(
                            "batch_manager _set_workflow_step failed", exc_info=True
                        )
            except Exception:
                logger.debug("检查 batch_manager 失败（非致命）", exc_info=True)

            # 清理 FileSelectionManager 的缓存与状态（向后兼容）
            try:
                fsm = getattr(self.gui, "file_selection_manager", None)
                if fsm is not None:
                    try:
                        fsm.special_part_mapping_by_file = {}
                        fsm.special_part_row_selection_by_file = {}
                        fsm.file_part_selection_by_file = {}
                        fsm.table_row_selection_by_file = {}
                        fsm._data_loaded = False
                        fsm._config_loaded = False
                        fsm._operation_performed = False
                    except Exception:
                        logger.debug(
                            "重置 file_selection_manager 映射失败（非致命）",
                            exc_info=True,
                        )
            except Exception:
                logger.debug(
                    "访问 file_selection_manager 失败（非致命）", exc_info=True
                )

            # 清理主窗口上旧的属性与文件树、列表缓存
            try:
                for attr in (
                    "special_part_mapping_by_file",
                    "special_part_row_selection_by_file",
                    "file_part_selection_by_file",
                    "table_row_selection_by_file",
                ):
                    try:
                        setattr(self.gui, attr, {})
                    except Exception:
                        try:
                            if _report_ui_exception:
                                _report_ui_exception(
                                    self.gui, f"设置主窗口属性 {attr} 失败"
                                )
                            else:
                                logger.debug(
                                    "设置主窗口属性 %s 失败", attr, exc_info=True
                                )
                        except Exception:
                            logger.debug("设置主窗口属性失败", exc_info=True)
            except Exception:
                try:
                    if _report_ui_exception:
                        _report_ui_exception(self.gui, "清理主窗口属性失败")
                    else:
                        logger.debug("清理主窗口属性失败", exc_info=True)
                except Exception:
                    logger.debug("清理主窗口属性失败", exc_info=True)

            try:
                if (
                    hasattr(self.gui, "file_tree")
                    and getattr(self.gui, "file_tree") is not None
                ):
                    try:
                        self.gui.file_tree.clear()
                    except Exception:
                        try:
                            if _report_ui_exception:
                                _report_ui_exception(
                                    self.gui, "清空 file_tree 失败（非致命）"
                                )
                            else:
                                logger.debug(
                                    "清空 file_tree 失败（非致命）", exc_info=True
                                )
                        except Exception:
                            logger.debug("清空 file_tree 失败（非致命）", exc_info=True)
                try:
                    setattr(self.gui, "_file_tree_items", {})
                except Exception:
                    try:
                        if _report_ui_exception:
                            _report_ui_exception(
                                self.gui, "重置 _file_tree_items 失败（非致命）"
                            )
                        else:
                            logger.debug(
                                "重置 _file_tree_items 失败（非致命）", exc_info=True
                            )
                    except Exception:
                        logger.debug(
                            "重置 _file_tree_items 失败（非致命）", exc_info=True
                        )
            except Exception:
                try:
                    if _report_ui_exception:
                        _report_ui_exception(
                            self.gui, "访问/清理 file_tree 失败（非致命）"
                        )
                    else:
                        logger.debug(
                            "访问/清理 file_tree 失败（非致命）", exc_info=True
                        )
                except Exception:
                    logger.debug("访问/清理 file_tree 失败（非致命）", exc_info=True)

            try:
                flw = getattr(self.gui, "file_list_widget", None)
                if flw is not None:
                    try:
                        layout = flw.layout()
                        if layout is not None:
                            while layout.count():
                                item = layout.takeAt(0)
                                w = item.widget()
                                if w is not None:
                                    try:
                                        w.setParent(None)
                                    except Exception:
                                        try:
                                            if _report_ui_exception:
                                                _report_ui_exception(
                                                    self.gui,
                                                    "移除 file_list_widget 子控件失败（非致命）",
                                                )
                                            else:
                                                logger.debug(
                                                    "移除 file_list_widget 子控件失败（非致命）",
                                                    exc_info=True,
                                                )
                                        except Exception:
                                            logger.debug(
                                                "移除 file_list_widget 子控件失败（非致命）",
                                                exc_info=True,
                                            )
                    except Exception:
                        try:
                            if _report_ui_exception:
                                _report_ui_exception(
                                    self.gui, "清理 file_list_widget 布局失败（非致命）"
                                )
                            else:
                                logger.debug(
                                    "清理 file_list_widget 布局失败（非致命）",
                                    exc_info=True,
                                )
                        except Exception:
                            logger.debug(
                                "清理 file_list_widget 布局失败（非致命）",
                                exc_info=True,
                            )
            except Exception:
                try:
                    if _report_ui_exception:
                        _report_ui_exception(
                            self.gui, "访问 file_list_widget 失败（非致命）"
                        )
                    else:
                        logger.debug(
                            "访问 file_list_widget 失败（非致命）", exc_info=True
                        )
                except Exception:
                    logger.debug("访问 file_list_widget 失败（非致命）", exc_info=True)

            # 标记为用户已修改以启用保存（与 UIStateManager 协同）
            try:
                if hasattr(self.gui, "ui_state_manager") and self.gui.ui_state_manager:
                    try:
                        # 新建项目通常视为需要保存（用户需确认/命名），标记为已修改
                        self.gui.ui_state_manager.set_data_loaded(True)
                        self.gui.ui_state_manager.set_config_loaded(True)
                        self.gui.ui_state_manager.mark_user_modified()
                    except Exception:
                        pass
                else:
                    try:
                        if hasattr(self.gui, "mark_user_modified") and callable(
                            self.gui.mark_user_modified
                        ):
                            self.gui.mark_user_modified()
                    except Exception:
                        pass
            except Exception:
                pass

            logger.info("新项目已创建")
            return True
        except Exception as e:
            # 关键错误通知并记录堆栈，便于用户知晓原因
            tb = traceback.format_exc()
            self._notify_user_error("创建新项目失败", str(e), tb)
            return False

    def save_project(self, file_path: Optional[Path] = None) -> bool:
        """保存当前项目到文件

        Args:
            file_path: 保存路径，若为 None 则使用最后打开的路径

        Returns:
            是否保存成功
        """
        # 当在主线程调用时，将实际写盘放到后台线程并显示模态进度，避免阻塞 UI。
        try:
            from PySide6.QtCore import QEventLoop, QThread
            from PySide6.QtWidgets import QApplication, QProgressDialog

            in_main_thread = QThread.currentThread() == QApplication.instance().thread()
        except Exception:
            in_main_thread = False

        if in_main_thread:
            try:

                loop = QEventLoop()
                dlg = None
                try:
                    parent = getattr(self, "gui", None)
                    dlg = QProgressDialog("正在保存项目…", None, 0, 0, parent)
                    dlg.setWindowModality(Qt.WindowModal)
                    try:
                        dlg.setCancelButton(None)
                    except Exception:
                        pass
                    dlg.setMinimumDuration(0)
                    dlg.show()
                except Exception:
                    dlg = None

                result_holder = {"res": False}

                def _on_done(success):
                    try:
                        result_holder["res"] = bool(success)
                    except Exception:
                        result_holder["res"] = False
                    try:
                        if dlg is not None:
                            dlg.close()
                    except Exception:
                        pass
                    try:
                        loop.quit()
                    except Exception:
                        pass

                try:
                    import threading

                    def _bg():
                        try:
                            ok = self._do_save(file_path)
                        except Exception:
                            logger.exception("主线程回退后台保存异常")
                            ok = False
                        try:
                            _on_done(ok)
                        except Exception:
                            pass

                    thr = threading.Thread(target=_bg, daemon=True)
                    thr.start()
                    loop.exec()
                    return bool(result_holder.get("res"))
                except Exception:
                    logger.debug(
                        "用后台线程执行保存失败，回退到同步保存", exc_info=True
                    )
                    if dlg is not None:
                        try:
                            dlg.close()
                        except Exception:
                            pass
                    return self._do_save(file_path)
            except Exception:
                logger.debug("主线程保存回退到同步路径", exc_info=True)
                return self._do_save(file_path)

        # 非主线程或无法创建 UI 组件时，直接同步执行写盘
        return self._do_save(file_path)

    def _do_save(self, file_path: Optional[Path] = None) -> bool:
        """内部保存实现：执行原子写入并发出信号。此方法为同步执行。"""
        try:
            if file_path is None:
                file_path = self.current_project_file

            if file_path is None:
                logger.error("未指定保存路径")
                return False

            file_path = Path(file_path)
            if not file_path.suffix:
                file_path = file_path.with_suffix(self.PROJECT_FILE_EXTENSION)

            # 收集当前状态
            project_data = self._collect_current_state()

            # 保存到临时文件，然后用原子替换确保不会丢失原文件
            file_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(project_data, f, indent=2, ensure_ascii=False)
                    try:
                        f.flush()
                        os.fsync(f.fileno())
                    except Exception:
                        # 非致命：继续尝试替换
                        logger.debug("刷新临时文件失败，继续尝试替换", exc_info=True)

                # 原子替换（Windows/Unix 可用）
                try:
                    os.replace(tmp_path, file_path)
                except Exception:
                    # 若替换失败，尝试删除临时文件并抛出
                    try:
                        if tmp_path.exists():
                            tmp_path.unlink()
                    except Exception:
                        logger.debug("删除临时文件失败", exc_info=True)
                    raise

                self.current_project_file = file_path
                self.last_saved_state = project_data
                logger.info(f"项目已保存: {file_path}")
                try:
                    sb = (
                        getattr(self.gui, "signal_bus", None)
                        or __import__(
                            "gui.signal_bus", fromlist=["SignalBus"]
                        ).SignalBus.instance()
                    )
                    try:
                        sb.projectSaved.emit(file_path)
                    except Exception:
                        logger.debug("发射 projectSaved 信号失败", exc_info=True)
                except Exception:
                    logger.debug(
                        "获取 SignalBus 失败，无法发射 projectSaved", exc_info=True
                    )
                return True
            except Exception as e:
                # 保证原文件不被修改；提示用户并记录日志
                logger.error("原子保存项目失败: %s", e, exc_info=True)
                try:
                    from PySide6.QtWidgets import QMessageBox

                    try:
                        QMessageBox.critical(
                            self.gui,
                            "保存失败",
                            f"项目保存失败，原文件已保留。错误: {e}",
                        )
                    except Exception:
                        logger.debug("显示保存失败对话框失败", exc_info=True)
                except Exception:
                    # 非GUI环境：仅记录日志
                    logger.debug("无法导入 QMessageBox 以显示错误", exc_info=True)

                # 在关键失败处也向用户展示更详细的错误（带堆栈）
                try:
                    self._notify_user_error(
                        "保存项目失败", str(e), traceback.format_exc()
                    )
                except Exception:
                    logger.debug("通知用户保存失败时出错", exc_info=True)

                return False
        except Exception as e:
            logger.error("保存项目失败: %s", e)
            return False

    def save_project_async(self, file_path: Optional[Path] = None, on_finished=None):
        """在后台线程中异步保存项目，完成时触发回调。

        Args:
            file_path: 保存路径，若为 None 则使用当前路径
            on_finished: 可选回调，签名为 `func(success: bool, file_path: Path)`
        """
        if QThread is None:
            # 无 Qt QThread 时，退回到 Python 线程以避免阻塞主线程
            try:
                import threading

                def _bg():
                    try:
                        res = self.save_project(file_path)
                    except Exception:
                        logger.exception("线程式后台保存异常")
                        res = False
                    if callable(on_finished):
                        try:
                            on_finished(
                                res,
                                (
                                    Path(file_path)
                                    if file_path
                                    else self.current_project_file
                                ),
                            )
                        except Exception:
                            logger.debug("异步回调执行失败", exc_info=True)

                thr = threading.Thread(target=_bg, daemon=True)
                thr.start()
            except Exception:
                # 极端情况下退回到同步保存（并调用回调）以保证功能性
                res = self.save_project(file_path)
                if callable(on_finished):
                    try:
                        on_finished(
                            res,
                            Path(file_path) if file_path else self.current_project_file,
                        )
                    except Exception:
                        logger.debug("异步回调执行失败", exc_info=True)
            return None

        class _SaveWorker(QThread):
            finished = Signal(bool, object)

            def __init__(self, pm, path):
                super().__init__()
                self.pm = pm
                self.path = Path(path) if path is not None else None

            def run(self):
                try:
                    # 调用内部同步写盘实现，避免递归调用 save_project -> save_project_async
                    result = self.pm._do_save(self.path)
                except Exception:
                    logger.exception("后台保存线程运行时异常")
                    result = False
                try:
                    self.finished.emit(result, self.path)
                except Exception:
                    logger.debug("SaveWorker finished emit 失败", exc_info=True)

        worker = _SaveWorker(self, file_path)

        def _cleanup(success, fp):
            try:
                # 确保线程对象被删除
                try:
                    worker.deleteLater()
                except Exception:
                    pass
                try:
                    self._background_workers.remove(worker)
                except Exception:
                    pass
                if callable(on_finished):
                    try:
                        on_finished(success, fp)
                    except Exception:
                        logger.debug("on_finished 回调失败", exc_info=True)
            except Exception:
                logger.debug("后台保存清理失败", exc_info=True)

        worker.finished.connect(_cleanup)
        self._background_workers.append(worker)
        worker.start()
        return worker

    def load_project(self, file_path: Path) -> bool:
        """加载项目文件

        Args:
            file_path: 项目文件路径

        Returns:
            是否加载成功
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.error(f"项目文件不存在: {file_path}")
                return False

            # 读取并解析 JSON，捕获语法错误并向用户提示
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    project_data = json.load(f)
                except Exception as e:
                    logger.error("项目文件 JSON 解析失败: %s", e, exc_info=True)
                    try:
                        from PySide6.QtWidgets import QFileDialog, QMessageBox

                        msg = QMessageBox(self.gui)
                        msg.setWindowTitle("项目文件解析失败")
                        msg.setText("无法解析项目文件 (JSON 语法错误)。")
                        msg.setInformativeText(str(e))
                        btn_save = msg.addButton("另存为", QMessageBox.AcceptRole)
                        btn_cancel = msg.addButton("取消", QMessageBox.RejectRole)
                        # UX：默认/ESC 走“取消”，避免误触回车导致进入另存为流程
                        try:
                            msg.setIcon(QMessageBox.Critical)
                        except Exception:
                            pass
                        try:
                            msg.setDefaultButton(btn_cancel)
                        except Exception:
                            pass
                        try:
                            msg.setEscapeButton(btn_cancel)
                        except Exception:
                            pass
                        msg.exec()
                        if msg.clickedButton() == btn_save:
                            try:
                                suggested = file_path.name
                                save_path, _ = QFileDialog.getSaveFileName(
                                    self.gui,
                                    "另存项目文件",
                                    suggested,
                                    "MomentTransfer Project (*.mtproject);;All Files (*)",
                                )
                                if save_path:
                                    # 将原始文本写入目标路径以保留内容
                                    f.seek(0)
                                    raw = f.read()
                                    with open(save_path, "w", encoding="utf-8") as out:
                                        out.write(raw)
                            except Exception:
                                logger.debug("另存为失败", exc_info=True)
                        return False
                    except Exception:
                        try:
                            from gui.managers import _report_ui_exception

                            _report_ui_exception(self.gui, "显示项目解析错误对话失败")
                        except Exception:
                            logger.debug("显示解析错误对话失败", exc_info=True)
                        return False

            # 验证版本一致性，若不一致向用户提供 继续/取消/另存为 选项
            version = project_data.get("version")
            if version != self.PROJECT_VERSION:
                logger.warning(
                    f"项目版本不匹配: {version} (期望 {self.PROJECT_VERSION})"
                )
                try:
                    from PySide6.QtWidgets import QFileDialog, QMessageBox

                    msg = QMessageBox(self.gui)
                    msg.setWindowTitle("项目版本不匹配")
                    msg.setText(
                        f"项目版本为 {version} ，与当前版本 {self.PROJECT_VERSION} 不一致。继续可能导致数据丢失或行为异常。"
                    )
                    msg.setDetailedText(
                        json.dumps(project_data, indent=2, ensure_ascii=False)
                    )
                    msg.addButton("继续", QMessageBox.AcceptRole)
                    btn_discard = msg.addButton("取消", QMessageBox.RejectRole)
                    btn_save = msg.addButton("另存为", QMessageBox.DestructiveRole)
                    # UX：默认/ESC 走“取消”，降低误操作概率（继续加载可能有数据风险）
                    try:
                        msg.setIcon(QMessageBox.Warning)
                    except Exception:
                        pass
                    try:
                        msg.setDefaultButton(btn_discard)
                    except Exception:
                        pass
                    try:
                        msg.setEscapeButton(btn_discard)
                    except Exception:
                        pass
                    msg.exec()
                    clicked = msg.clickedButton()
                    if clicked == btn_discard:
                        return False
                    if clicked == btn_save:
                        try:
                            suggested = file_path.name
                            save_path, _ = QFileDialog.getSaveFileName(
                                self.gui,
                                "另存项目文件",
                                suggested,
                                "MomentTransfer Project (*.mtproject);;All Files (*)",
                            )
                            if save_path:
                                self._atomic_write_dict(Path(save_path), project_data)
                        except Exception:
                            logger.debug("版本不匹配时另存为失败", exc_info=True)
                        # 继续加载原文件
                except Exception:
                    logger.debug("显示版本不匹配对话失败，继续加载", exc_info=True)

            # 在尝试恢复前先清理现有的文件选择/映射与 GUI，避免把新项目合并到旧状态
            try:
                fsm = getattr(self.gui, "file_selection_manager", None)
                if fsm is not None:
                    # 重置 FSM 的映射和状态标志
                    try:
                        fsm.special_part_mapping_by_file = {}
                        fsm.special_part_row_selection_by_file = {}
                        fsm.file_part_selection_by_file = {}
                        fsm.table_row_selection_by_file = {}
                    except Exception:
                        logger.debug(
                            "重置 file_selection_manager 映射失败（非致命）",
                            exc_info=True,
                        )

                    try:
                        fsm._data_loaded = False
                        fsm._config_loaded = False
                        fsm._operation_performed = False
                    except Exception:
                        logger.debug(
                            "清理 file_selection_manager 状态失败（非致命）",
                            exc_info=True,
                        )

                # 清空主窗口上的相关缓存与控件
                try:
                    if (
                        hasattr(self.gui, "file_tree")
                        and getattr(self.gui, "file_tree") is not None
                    ):
                        try:
                            self.gui.file_tree.clear()
                        except Exception:
                            logger.debug("清空 file_tree 失败（非致命）", exc_info=True)

                    try:
                        setattr(self.gui, "_file_tree_items", {})
                    except Exception:
                        logger.debug(
                            "重置 _file_tree_items 失败（非致命）", exc_info=True
                        )

                    # 清空 file_list_widget 子控件（若存在）
                    flw = getattr(self.gui, "file_list_widget", None)
                    if flw is not None and hasattr(flw, "layout"):
                        try:
                            layout = flw.layout()
                            if layout is not None:
                                while layout.count():
                                    it = layout.takeAt(0)
                                    w = it.widget()
                                    if w is not None:
                                        try:
                                            w.setParent(None)
                                        except Exception:
                                            logger.debug(
                                                "移除 file_list_widget 子控件失败（非致命）",
                                                exc_info=True,
                                            )
                        except Exception:
                            logger.debug(
                                "清理 file_list_widget 布局失败（非致命）",
                                exc_info=True,
                            )
                except Exception:
                    logger.debug("清空 GUI 文件树/缓存失败（非致命）", exc_info=True)
            except Exception:
                logger.debug("加载前清理文件选择/UI 失败（非致命）", exc_info=True)

            # 尝试恢复配置（解析模型失败时向用户提示并给予选项）
            try:
                # 使用内部恢复方法，它会尝试创建 ProjectConfigModel
                self._restore_config(project_data)
            except Exception as e:
                logger.error("恢复配置时发生异常: %s", e, exc_info=True)
                try:
                    from PySide6.QtWidgets import QFileDialog, QMessageBox

                    msg = QMessageBox(self.gui)
                    msg.setWindowTitle("项目解析失败")
                    msg.setText("无法解析项目到内部模型，可能缺失字段或格式不兼容。")
                    msg.setDetailedText(traceback.format_exc())
                    msg.addButton("继续", QMessageBox.AcceptRole)
                    btn_discard = msg.addButton("取消", QMessageBox.RejectRole)
                    btn_save = msg.addButton("另存为", QMessageBox.DestructiveRole)
                    # UX：默认/ESC 走“取消”，避免误触回车继续进入“可能不完整的项目状态”
                    try:
                        msg.setIcon(QMessageBox.Critical)
                    except Exception:
                        pass
                    try:
                        msg.setDefaultButton(btn_discard)
                    except Exception:
                        pass
                    try:
                        msg.setEscapeButton(btn_discard)
                    except Exception:
                        pass
                    msg.exec()
                    clicked = msg.clickedButton()
                    if clicked == btn_discard:
                        return False
                    if clicked == btn_save:
                        try:
                            suggested = file_path.name
                            save_path, _ = QFileDialog.getSaveFileName(
                                self.gui,
                                "另存项目文件",
                                suggested,
                                "MomentTransfer Project (*.mtproject);;All Files (*)",
                            )
                            if save_path:
                                self._atomic_write_dict(Path(save_path), project_data)
                        except Exception:
                            logger.debug("解析失败时另存为失败", exc_info=True)
                    # 若选择继续，则继续后续恢复（尽管模型可能未能设置）
                except Exception:
                    logger.debug("显示解析失败对话失败，放弃加载", exc_info=True)
                    return False

            # 恢复数据文件和工作流程
            self._restore_data_files(project_data)
            self._restore_workflow_step(project_data)

            # 记录加载路径与状态
            self.current_project_file = file_path
            self.last_saved_state = project_data

            try:
                # 在加载成功后设置 UI 状态：标记为已加载且未被用户修改
                try:
                    if (
                        hasattr(self.gui, "ui_state_manager")
                        and self.gui.ui_state_manager
                    ):
                        try:
                            self.gui.ui_state_manager.set_data_loaded(True)
                        except Exception:
                            pass
                        try:
                            self.gui.ui_state_manager.set_config_loaded(True)
                        except Exception:
                            pass
                        try:
                            self.gui.ui_state_manager.clear_user_modified()
                        except Exception:
                            pass
                    else:
                        try:
                            self.gui.data_loaded = True
                        except Exception:
                            pass
                        try:
                            self.gui.config_loaded = True
                        except Exception:
                            pass
                        try:
                            self.gui.operation_performed = False
                        except Exception:
                            pass

                    # 确保 project 相关按钮在加载完成后按初始化时的行为被启用
                    try:
                        setattr(
                            self.gui, "_project_buttons_temporarily_disabled", False
                        )
                    except Exception:
                        pass
                    try:
                        if hasattr(self.gui, "_refresh_controls_state"):
                            try:
                                self.gui._refresh_controls_state()
                            except Exception:
                                pass
                    except Exception:
                        pass

                except Exception:
                    logger.debug(
                        "设置 UIStateManager 状态失败（非致命）", exc_info=True
                    )

                sb = (
                    getattr(self.gui, "signal_bus", None)
                    or __import__(
                        "gui.signal_bus", fromlist=["SignalBus"]
                    ).SignalBus.instance()
                )
                try:
                    sb.projectLoaded.emit(file_path)
                except Exception:
                    logger.debug("发射 projectLoaded 信号失败", exc_info=True)
            except Exception:
                logger.debug(
                    "获取 SignalBus 失败，无法发射 projectLoaded", exc_info=True
                )

            logger.info(f"项目已加载: {file_path}")
            return True
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("加载项目失败: %s", e, exc_info=True)
            try:
                self._notify_user_error("加载项目失败", str(e), tb)
            except Exception:
                logger.debug("通知用户加载失败时出错", exc_info=True)
            return False

    def load_project_async(self, file_path: Path, on_finished=None):
        """在后台线程中异步加载项目，完成时触发回调。

        Args:
            file_path: 项目路径
            on_finished: 可选回调，签名为 `func(success: bool, file_path: Path)`
        """
        if QThread is None:
            # 无 Qt QThread 时，使用 Python 线程执行以避免阻塞主线程
            try:
                import threading

                def _bg_load():
                    try:
                        res = self.load_project(file_path)
                    except Exception:
                        logger.exception("线程式后台加载异常")
                        res = False
                    if callable(on_finished):
                        try:
                            on_finished(res, Path(file_path))
                        except Exception:
                            logger.debug("异步加载回调失败", exc_info=True)

                thr = threading.Thread(target=_bg_load, daemon=True)
                thr.start()
            except Exception:
                res = self.load_project(file_path)
                if callable(on_finished):
                    try:
                        on_finished(res, Path(file_path))
                    except Exception:
                        logger.debug("异步加载回调失败", exc_info=True)
            return None

        class _LoadWorker(QThread):
            finished = Signal(bool, object)

            def __init__(self, pm, path):
                super().__init__()
                self.pm = pm
                self.path = Path(path)

            def run(self):
                try:
                    result = self.pm.load_project(self.path)
                except Exception:
                    logger.exception("后台加载线程运行时异常")
                    result = False
                try:
                    self.finished.emit(result, self.path)
                except Exception:
                    logger.debug("LoadWorker finished emit 失败", exc_info=True)

        worker = _LoadWorker(self, file_path)

        def _cleanup(success, fp):
            try:
                try:
                    worker.deleteLater()
                except Exception:
                    pass
                try:
                    self._background_workers.remove(worker)
                except Exception:
                    pass
                if callable(on_finished):
                    try:
                        on_finished(success, fp)
                    except Exception:
                        logger.debug("load on_finished 回调失败", exc_info=True)
            except Exception:
                logger.debug("后台加载清理失败", exc_info=True)

        worker.finished.connect(_cleanup)
        self._background_workers.append(worker)
        worker.start()
        return worker

    def _collect_current_state(self) -> Dict:
        """收集当前工作状态"""
        project_data = {
            "version": self.PROJECT_VERSION,
            "timestamp": datetime.now().isoformat(),
        }

        # 保存参考系配置
        try:
            config = None
            if hasattr(self.gui, "project_model") and self.gui.project_model:
                config = self._serialize_project_model(self.gui.project_model)
            elif hasattr(self.gui, "current_config") and self.gui.current_config:
                config = self._serialize_config(self.gui.current_config)

            if config:
                project_data["reference_config"] = {
                    "data": config,
                    "timestamp": datetime.now().isoformat(),
                }
        except Exception as e:
            logger.debug(f"收集配置失败: {e}", exc_info=True)

        # 保存数据文件及映射
        try:
            data_files = []
            if hasattr(self.gui, "file_selection_manager"):
                fsm = self.gui.file_selection_manager

                # 收集特殊格式映射
                special_mappings = (
                    getattr(fsm, "special_part_mapping_by_file", {}) or {}
                )
                table_selection = getattr(fsm, "table_row_selection_by_file", {}) or {}

                for file_path, mapping in special_mappings.items():
                    row_sel = table_selection.get(file_path)
                    data_files.append(
                        {
                            "path": file_path,
                            "special_mappings": mapping,
                            "row_selection": list(row_sel) if row_sel else [],
                        }
                    )

            project_data["data_files"] = data_files
        except Exception as e:
            logger.debug(f"收集数据文件失败: {e}", exc_info=True)
            project_data["data_files"] = []

        # 保存工作流程步骤
        try:
            if hasattr(self.gui, "batch_manager"):
                step = getattr(self.gui.batch_manager, "_current_workflow_step", 1)
                project_data["workflow_step"] = step
        except Exception:
            project_data["workflow_step"] = 1

        # 保存输出目录
        try:
            if hasattr(self.gui, "output_dir"):
                project_data["output_dir"] = str(self.gui.output_dir)
        except Exception:
            pass

        # 保存一些最小的 UI 状态以便恢复用户工作上下文
        try:
            ui_state = {}
            try:
                tab = getattr(self.gui, "tab_main", None)
                if tab is not None and hasattr(tab, "currentIndex"):
                    ui_state["tab_index"] = int(tab.currentIndex())
            except Exception:
                pass

            try:
                geom_saved = None
                try:
                    if hasattr(self.gui, "saveGeometry") and callable(
                        getattr(self.gui, "saveGeometry")
                    ):
                        raw = self.gui.saveGeometry()
                        if raw is not None:
                            try:
                                raw_bytes = (
                                    bytes(raw)
                                    if not isinstance(raw, (bytes, bytearray))
                                    else bytes(raw)
                                )
                            except Exception:
                                try:
                                    raw_bytes = (
                                        raw.data()
                                        if hasattr(raw, "data")
                                        else bytes(raw)
                                    )
                                except Exception:
                                    raw_bytes = None
                            if raw_bytes:
                                geom_saved = base64.b64encode(raw_bytes).decode("ascii")
                except Exception:
                    geom_saved = None

                try:
                    g = getattr(self.gui, "geometry", None)
                    if callable(g):
                        r = self.gui.geometry()
                        ui_state["window_geometry"] = {
                            "x": r.x(),
                            "y": r.y(),
                            "w": r.width(),
                            "h": r.height(),
                        }
                except Exception:
                    pass

                if geom_saved:
                    ui_state["geometry_b64"] = geom_saved
            except Exception:
                pass

            try:
                fsm = getattr(self.gui, "file_selection_manager", None)
                if fsm is not None:
                    try:
                        sel = list(
                            (
                                getattr(fsm, "table_row_selection_by_file", {}) or {}
                            ).keys()
                        )
                        if sel:
                            ui_state["selected_files"] = sel
                    except Exception:
                        pass
            except Exception:
                pass

            if ui_state:
                project_data["ui_state"] = ui_state
        except Exception:
            pass

        return project_data

    def _restore_config(self, project_data: Dict) -> bool:
        """恢复配置"""
        try:
            config_data = project_data.get("reference_config", {}).get("data")
            if not config_data:
                return False

            # 创建 ProjectConfigModel 并恢复
            try:
                from src.models import ProjectConfigModel

                model = ProjectConfigModel.from_dict(config_data)
                if hasattr(self.gui, "project_model"):
                    self.gui.project_model = model
            except Exception as e:
                logger.debug(f"恢复 ProjectConfigModel 失败: {e}")
                return False

            logger.info("配置已恢复")
            return True
        except Exception as e:
            logger.debug(f"恢复配置失败: {e}", exc_info=True)
            return False

    def _restore_data_files(self, project_data: Dict) -> bool:
        """恢复数据文件选择和映射"""
        try:
            data_files = project_data.get("data_files", [])
            if not data_files or not hasattr(self.gui, "file_selection_manager"):
                return False

            fsm = self.gui.file_selection_manager

            # 恢复特殊格式映射
            for file_info in data_files:
                file_path = file_info.get("path")
                mappings = file_info.get("special_mappings", {})
                row_sel = file_info.get("row_selection", [])

                # 统一键格式为绝对解析路径的字符串，避免相对/Path 混用导致查找失败或重复
                try:
                    key = str(Path(file_path).resolve()) if file_path else None
                except Exception:
                    key = str(file_path) if file_path else None

                if key and mappings:
                    try:
                        fsm.special_part_mapping_by_file[key] = mappings
                    except Exception:
                        # 回退：尝试直接写入原 key
                        try:
                            fsm.special_part_mapping_by_file[file_path] = mappings
                        except Exception:
                            pass

                if key and row_sel:
                    try:
                        fsm.table_row_selection_by_file[key] = set(row_sel)
                    except Exception:
                        try:
                            fsm.table_row_selection_by_file[file_path] = set(row_sel)
                        except Exception:
                            pass

            logger.info(f"已恢复 {len(data_files)} 个数据文件的配置")
            return True
        except Exception as e:
            logger.debug(f"恢复数据文件失败: {e}", exc_info=True)
            return False

    def _restore_workflow_step(self, project_data: Dict) -> bool:
        """恢复工作流程步骤"""
        try:
            step = project_data.get("workflow_step", 1)
            if hasattr(self.gui, "batch_manager"):
                # 映射步骤到字符串
                step_map = {1: "init", 2: "step2", 3: "step3"}
                step_str = step_map.get(step, "init")
                self.gui.batch_manager._set_workflow_step(step_str)

            logger.info(f"工作流程已恢复到步骤 {step}")
            return True
        except Exception as e:
            logger.debug(f"恢复工作流程失败: {e}", exc_info=True)
            return False

    @staticmethod
    def _serialize_project_model(model) -> Optional[Dict]:
        """序列化 ProjectConfigModel"""
        try:
            if hasattr(model, "to_dict"):
                return model.to_dict()

            # 回退：手动构建
            data = {
                "source_parts": {},
                "target_parts": {},
            }

            if hasattr(model, "source_parts"):
                for name, part in (model.source_parts or {}).items():
                    data["source_parts"][name] = ProjectManager._serialize_part(part)

            if hasattr(model, "target_parts"):
                for name, part in (model.target_parts or {}).items():
                    data["target_parts"][name] = ProjectManager._serialize_part(part)

            return data
        except Exception:
            return None

    @staticmethod
    def _serialize_part(part) -> Dict:
        """序列化 Part 对象"""
        try:
            data = {
                "name": getattr(part, "part_name", ""),
                "variants": [],
            }

            if hasattr(part, "variants"):
                for variant in part.variants or []:
                    var_data = ProjectManager._serialize_variant(variant)
                    if var_data:
                        data["variants"].append(var_data)

            return data
        except Exception:
            return {}

    @staticmethod
    def _serialize_variant(variant) -> Optional[Dict]:
        """序列化 Variant 对象"""
        try:
            data = {
                "part_name": getattr(variant, "part_name", ""),
            }

            # 坐标系
            if hasattr(variant, "coord_system"):
                cs = variant.coord_system
                data["coord_system"] = {
                    "origin": getattr(cs, "origin", [0, 0, 0]),
                    "moment_center": getattr(cs, "moment_center", [0, 0, 0]),
                }

            # 参考值
            if hasattr(variant, "refs"):
                refs = variant.refs
                data["refs"] = {
                    "q": getattr(refs, "q", 1.0),
                    "s_ref": getattr(refs, "s_ref", 1.0),
                    "c_ref": getattr(refs, "c_ref", 1.0),
                    "b_ref": getattr(refs, "b_ref", 1.0),
                }

            return data
        except Exception:
            return None

    @staticmethod
    def _serialize_config(config) -> Optional[Dict]:
        """序列化配置对象（备用方案）"""
        try:
            data = {
                "source_parts": {},
                "target_parts": {},
            }

            if hasattr(config, "source_parts"):
                for name, part in (config.source_parts or {}).items():
                    data["source_parts"][name] = str(part)

            if hasattr(config, "target_parts"):
                for name, part in (config.target_parts or {}).items():
                    data["target_parts"][name] = str(part)

            return data
        except Exception:
            return None


__all__ = ["ProjectManager"]
