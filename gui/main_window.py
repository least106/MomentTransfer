"""
MomentTransfer GUI 主窗口模块
向后兼容入口：从 gui 包导入模块化的组件

重构说明：
- Mpl3DCanvas -> gui/canvas.py
- ExperimentalDialog -> gui/dialogs.py
- BatchProcessThread -> gui/batch_thread.py
- IntegratedAeroGUI -> 保留在此文件（待进一步拆分）
"""

# 某些模块为延迟加载以加快启动速度，接受受控的 import-outside-toplevel
# pylint: disable=import-outside-toplevel

import logging
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QHBoxLayout,
)
from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtGui import QDesktopServices

from gui.event_manager import EventManager
from gui.initialization_manager import InitializationManager

# 从模块化包导入组件
# Mpl3DCanvas 延迟加载以加快启动速度（在首次调用show_visualization时加载）
from gui.log_manager import LoggingManager
from gui.managers import FileSelectionManager, ModelManager, UIStateManager

# 导入面板组件
from gui.panels import ConfigPanel, OperationPanel

# 导入管理器和工具
from gui.signal_bus import SignalBus

logger = logging.getLogger(__name__)

# 主题常量（便于代码中引用）
THEME_MAIN = "#0078d7"
THEME_ACCENT = "#28a745"
THEME_DANGER = "#ff6b6b"
THEME_BG = "#f7f9fb"
LAYOUT_MARGIN = 12
LAYOUT_SPACING = 8


class IntegratedAeroGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        # 基本属性
        self.setWindowTitle("MomentTransfer")
        self.resize(1500, 900)

        # 初始化标志
        self._is_initializing = True

        # 核心数据（移到 ModelManager）
        self.signal_bus = SignalBus.instance()
        self.data_config = None
        self.visualization_window = None

        # 管理器化的状态：文件选择、模型、UI 状态
        self.file_selection_manager = FileSelectionManager(self)
        self.model_manager = ModelManager(self)

        self.ui_state_manager = UIStateManager(self)

        # 管理器占位（将由 InitializationManager 初始化）
        self.config_manager = None
        self.part_manager = None
        self.batch_manager = None
        self.layout_manager = None

        # UI 状态标志
        self.data_loaded = False
        self.config_loaded = False
        self.operation_performed = False

        # 新管理器
        self.initialization_manager = InitializationManager(self)
        self.event_manager = EventManager(self)

        # 执行初始化
        self.initialization_manager.setup_ui()
        self.initialization_manager.setup_managers()
        self.initialization_manager.setup_logging()
        self.initialization_manager.bind_post_ui_signals()

    def set_config_panel_visible(self, visible: bool) -> None:
        """按流程显示/隐藏配置编辑器，减少初始化干扰。"""
        # 将具体实现委托给 UIStateManager，主窗口保留向后兼容行为
        try:
            self.ui_state_manager.set_config_panel_visible(visible)
        except Exception:
            logger.debug("set_config_panel_visible failed", exc_info=True)

    def mark_data_loaded(self) -> None:
        """标记已加载数据文件并刷新控件状态"""
        try:
            self.data_loaded = True
            self._refresh_controls_state()
        except Exception:
            logger.debug("mark_data_loaded failed", exc_info=True)

    def mark_config_loaded(self) -> None:
        """标记已加载配置并刷新控件状态"""
        try:
            self.config_loaded = True
            self._refresh_controls_state()
        except Exception:
            logger.debug("mark_config_loaded failed", exc_info=True)

    def mark_user_modified(self) -> None:
        """标记为用户已修改（用于启用保存按钮）。

        与 data_loaded/config_loaded 区分，避免仅加载即启用保存。
        """
        try:
            self.operation_performed = True
            self._refresh_controls_state()
        except Exception:
            logger.debug("mark_user_modified failed", exc_info=True)

    def _refresh_controls_state(self) -> None:
        """根据当前状态标志启用/禁用按钮与选项卡。"""
        try:
            # 将控件状态刷新委托给 UIStateManager
            if hasattr(self, "ui_state_manager") and self.ui_state_manager:
                try:
                    self.ui_state_manager.refresh_controls_state()
                    return
                except Exception:
                    logger.debug("ui_state_manager.refresh_controls_state 调用失败，回退到本地实现", exc_info=True)

            # 回退实现（仅在 UIStateManager 不可用时使用）
            start_enabled = bool(self.data_loaded and self.config_loaded)
            for name in ("btn_start_menu", "btn_batch", "btn_batch_in_toolbar"):
                try:
                    btn = getattr(self, name, None)
                    if btn is not None:
                        btn.setEnabled(bool(start_enabled))
                except Exception as e:
                    logger.debug("设置启动按钮状态失败（非致命）: %s", e, exc_info=True)

            save_enabled = bool(self.operation_performed)
            for name in ("btn_save_project_toolbar",):
                try:
                    btn = getattr(self, name, None)
                    if btn is not None:
                        btn.setEnabled(bool(save_enabled))
                except Exception as e:
                    logger.debug("设置保存按钮状态失败（非致命）: %s", e, exc_info=True)
        except Exception:
            logger.debug("_refresh_controls_state failed", exc_info=True)

    def create_config_panel(self):
        """创建配置编辑器面板（由 InitializationManager 调用）"""
        panel = ConfigPanel(self)

        # 保存面板引用
        self.source_panel = panel.source_panel
        self.target_panel = panel.target_panel

        return panel

    def create_operation_panel(self):
        """创建批量处理面板（委托 OperationPanel 组件），并保持旧属性兼容。"""
        panel = OperationPanel(
            parent=self,
            on_batch_start=self.run_batch_processing,
            on_browse=self.browse_batch_input,
            on_select_all=self._select_all_files,
            on_select_none=self._select_none_files,
            on_invert_selection=self._invert_file_selection,
            on_quick_select=self._quick_select,
            on_save_project=self._on_save_project,
        )

        # 兼容旧属性映射
        try:
            panel.attach_legacy_aliases(self)
        except Exception:
            logger.debug("attach_legacy_aliases 失败", exc_info=True)

        # 将日志处理器连接到 GUI
        try:
            self._setup_gui_logging()
        except Exception:
            logger.debug(
                "_setup_gui_logging failed in create_operation_panel",
                exc_info=True,
            )

        return panel

    def toggle_config_sidebar(self) -> bool:
        """切换配置侧边栏，返回当前是否展开。"""
        try:
            sb = getattr(self, "config_sidebar", None)
            if sb is not None:
                sb.toggle_panel()
                return sb.is_expanded()
        except Exception:
            logger.debug("toggle_config_sidebar failed", exc_info=True)
            # 返回 None 表示发生错误，调用方不要将其误解释为已收起
            return None

    def toggle_history_sidebar(self) -> bool:
        """切换批处理历史侧边栏，返回当前是否展开。"""
        try:
            sb = getattr(self, "history_sidebar", None)
            if sb is not None:
                sb.toggle_panel()
                return sb.is_expanded()
        except Exception:
            logger.debug("toggle_history_sidebar failed", exc_info=True)
            # 返回 None 表示发生错误，调用方不要将其误解释为已收起
            return None

    def _quick_select(self):
        if self.batch_manager:
            try:
                self.batch_manager.open_quick_select_dialog()
            except Exception:
                logger.debug("打开快速选择对话框失败", exc_info=True)

    # 文件选择方法委托给 BatchManager
    def _select_all_files(self):
        if self.batch_manager:
            self.batch_manager.select_all_files()

    def _select_none_files(self):
        if self.batch_manager:
            self.batch_manager.select_none_files()

    def _invert_file_selection(self):
        if self.batch_manager:
            self.batch_manager.invert_file_selection()

    # Part 保存方法委托给 PartManager
    def _save_current_source_part(self):
        if self.part_manager:
            self.part_manager.save_current_source_part()

    def _save_current_target_part(self):
        if self.part_manager:
            self.part_manager.save_current_target_part()

    def load_config(self):
        """加载配置文件 - 委托给 ConfigManager"""
        try:
            self.config_manager.load_config()
        except AttributeError:
            # 如果管理器未初始化，记录警告
            logger.warning("ConfigManager 未初始化，无法加载配置")
        except Exception as e:
            logger.error("加载配置失败: %s", e)

    def save_config(self):
        """保存配置到JSON - 委托给 ConfigManager"""
        try:
            self.config_manager.save_config()
        except AttributeError:
            # 如果管理器未初始化，记录警告
            logger.warning("ConfigManager 未初始化，无法保存配置")
        except Exception as e:
            logger.error("保存配置失败: %s", e)

    def apply_config(self):
        """应用当前配置到计算器 - 委托给 ConfigManager"""
        try:
            self.config_manager.apply_config()
            # 应用配置后：提示用户是否切换到文件列表（避免打断当前任务）
            try:
                reply = QMessageBox.question(
                    self,
                    "配置已应用",
                    "配置已应用。是否切换到文件列表以查看文件？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
            except Exception as e:
                logger.debug("显示切换提示对话框失败（将不切换）: %s", e, exc_info=True)
                reply = QMessageBox.No

            if reply == QMessageBox.Yes:
                try:
                    if hasattr(self, "tab_main"):
                        tab = self.tab_main
                        idx = -1
                        try:
                            idx = tab.indexOf(getattr(self, "file_list_widget", None))
                        except Exception:
                            idx = -1
                        if idx is None or idx == -1:
                            idx = 0
                        tab.setCurrentIndex(idx)
                except Exception as e:
                    logger.debug("切换到文件列表失败（非致命）: %s", e, exc_info=True)
        except AttributeError:
            # 如果管理器未初始化，记录警告
            logger.warning("配置Manager 未初始化，无法应用配置")
        except Exception as e:
            logger.error("应用配置失败: %s", e)

    # 配置格式方法委托给 ConfigManager
    # 已移除全局数据格式配置功能（改为 per-file sidecar / registry 机制）

    def browse_batch_input(self):
        """选择输入文件或目录 - 委托给 BatchManager"""
        try:
            self.batch_manager.browse_batch_input()
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error("浏览批处理输入失败: %s", e)

    def _scan_and_populate_files(self, chosen_path):
        """扫描所选路径并刷新文件列表（委托给 BatchManager）。"""
        try:
            self.batch_manager.scan_and_populate_files(chosen_path)
        except Exception:
            logger.debug(
                "_scan_and_populate_files delegated call failed", exc_info=True
            )

    def _on_save_project(self):
        """保存Project（打开选择文件对话框）"""
        try:

            from PySide6.QtWidgets import QFileDialog

            # 打开保存文件对话框
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存Project文件",
                "",
                "MomentTransfer Project (*.mtproject);;All Files (*)",
            )

            if file_path:
                if self.project_manager:
                    self.project_manager.save_project(Path(file_path))
                try:
                    QMessageBox.information(
                        self, "成功", f"项目已保存到: {file_path}"
                    )
                except Exception as e:
                    logger.debug("无法显示保存成功提示: %s", e, exc_info=True)
        except Exception as e:
            logger.error("保存Project失败: %s", e)
            try:
                QMessageBox.critical(self, "错误", f"保存Project失败: {e}")
            except Exception:
                logger.debug("无法显示保存失败对话框（非致命）", exc_info=True)

    def _new_project(self):
        """创建新Project"""
        try:
            if self.project_manager:
                if self.project_manager.create_new_project():
                    try:
                        QMessageBox.information(self, "成功", "新项目已创建")
                    except Exception as e:
                        logger.debug("无法显示新项目提示: %s", e, exc_info=True)
        except Exception as e:
            logger.error("创建新Project失败: %s", e)

    def _open_project(self):
        """打开Project文件"""
        try:
            from pathlib import Path

            from PySide6.QtWidgets import QFileDialog

            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "打开Project文件",
                "",
                "MomentTransfer Project (*.mtproject);;All Files (*)",
            )

            if file_path:
                if self.project_manager:
                    if self.project_manager.load_project(Path(file_path)):
                        try:
                            QMessageBox.information(
                                self, "成功", f"项目已加载: {file_path}"
                            )
                        except Exception as e:
                            logger.debug("无法显示加载成功提示: %s", e, exc_info=True)
                    else:
                        try:
                            QMessageBox.critical(self, "错误", "项目加载失败")
                        except Exception:
                            logger.debug("无法显示加载失败对话框（非致命）", exc_info=True)
        except Exception as e:
            logger.error("打开Project失败: %s", e)

    def run_batch_processing(self):
        """运行批处理 - 委托给 BatchManager"""
        try:
            # 检查配置是否被修改
            if self.config_manager and self.config_manager.is_config_modified():
                reply = QMessageBox.question(
                    self,
                    "配置已修改",
                    "检测到配置已修改但未保存。\n\n是否要保存修改的配置后再进行批处理？",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Save,
                )

                # 用户选择保存：尝试保存并仅在成功后继续
                if reply == QMessageBox.Save:
                    try:
                        saved = self.config_manager.save_config()
                    except Exception as e:
                        logger.error("保存配置时发生异常: %s", e, exc_info=True)
                        saved = False

                    if not saved:
                        try:
                            QMessageBox.critical(
                                self,
                                "保存失败",
                                "配置保存失败，已取消批处理。",
                            )
                        except Exception:
                            logger.debug("无法显示保存失败对话框", exc_info=True)
                        return

                    logger.debug("配置已保存，继续执行批处理")

                # 用户选择取消：中断批处理
                elif reply == QMessageBox.Cancel:
                    logger.debug("用户取消批处理启动（选择取消保存）")
                    return

            # 运行批处理（配置未修改或用户选择丢弃/已保存）
            self.batch_manager.run_batch_processing()
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error("运行批处理失败: %s", e)

    def on_batch_finished(self, message):
        """批处理完成 - 委托给 BatchManager"""
        try:
            self.batch_manager.on_batch_finished(message)
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error("处理批处理完成事件失败: %s", e)

    def on_batch_error(self, error_msg):
        """批处理出错 - 委托给 BatchManager"""
        try:
            self.batch_manager.on_batch_error(error_msg)
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error("处理批处理错误事件失败: %s", e)
            try:
                if hasattr(self, "btn_cancel"):
                    self.btn_cancel.setVisible(False)
                    self.btn_cancel.setEnabled(False)
            except Exception:
                logger.debug(
                    "Failed to hide/disable cancel button after error",
                    exc_info=True,
                )

        # 友好的错误提示，包含可行建议
        try:
            dlg = QMessageBox(self)
            dlg.setIcon(QMessageBox.Critical)
            dlg.setWindowTitle("处理失败")
            dlg.setText(
                "批处理过程中发生错误，已记录到日志。请检查输入文件与格式定义。"
            )
            dlg.setInformativeText(
                "建议：检查 per-file 格式定义（<文件名>.format.json / 同目录 format.json / registry），"
                "以及 Target 配置中的 MomentCenter/Q/S。"
            )
            dlg.setDetailedText(str(error_msg))
            # 保留模态对话框以确保用户注意到严重错误
            dlg.exec()
        except Exception:
            logger.debug("无法显示错误对话框（非致命）", exc_info=True)

        # 非阻塞通知：在状态栏添加“查看详情”按钮，点击打开非模态详情对话框
        try:
            # 移除旧的按钮（如果存在）
            try:
                old_btn = getattr(self, "_batch_error_btn", None)
                if old_btn is not None:
                    try:
                        self.statusBar().removeWidget(old_btn)
                    except Exception:
                        old_btn.setVisible(False)
            except Exception:
                pass

            btn = QPushButton("查看详情", self)
            btn.setToolTip("在非模态窗口中查看错误详情，并可复制或打开日志文件")
            btn.clicked.connect(lambda: self._show_non_modal_error_details(str(error_msg)))
            self._batch_error_btn = btn
            try:
                self.statusBar().addPermanentWidget(btn)
            except Exception:
                # 若不支持 addPermanentWidget，回退到简短消息
                self.statusBar().showMessage("发生错误，查看日志以获取更多信息")

            # 在 2 分钟后自动移除该按钮以避免长期占用状态栏
            def _remove_btn():
                try:
                    b = getattr(self, "_batch_error_btn", None)
                    if b is not None:
                        try:
                            self.statusBar().removeWidget(b)
                        except Exception:
                            b.setVisible(False)
                        try:
                            del self._batch_error_btn
                        except Exception:
                            pass
                except Exception:
                    logger.debug("清除状态栏错误按钮失败（非致命）", exc_info=True)

            try:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(_remove_btn)
                timer.start(120000)
            except Exception:
                pass

            try:
                self.statusBar().showMessage("批处理出错 — 点击 '查看详情' 获取更多信息")
            except Exception:
                logger.debug("无法在状态栏显示消息（非致命）", exc_info=True)

        except Exception:
            logger.debug("设置非阻塞错误通知失败（非致命）", exc_info=True)

    def _show_non_modal_error_details(self, error_msg: str) -> None:
        """在非模态对话框中显示错误详情，提供复制与打开日志的功能。"""
        try:
            dlg = QDialog(self)
            dlg.setWindowTitle("错误详情")
            dlg.setModal(False)
            dlg.setAttribute(Qt.WA_DeleteOnClose, True)

            layout = QVBoxLayout(dlg)
            text = QPlainTextEdit(dlg)
            text.setReadOnly(True)
            text.setPlainText(error_msg)
            layout.addWidget(text)

            btn_layout = QHBoxLayout()
            copy_btn = QPushButton("复制错误", dlg)
            open_log_btn = QPushButton("打开日志文件", dlg)
            close_btn = QPushButton("关闭", dlg)

            btn_layout.addWidget(copy_btn)
            btn_layout.addWidget(open_log_btn)
            btn_layout.addStretch(1)
            btn_layout.addWidget(close_btn)
            layout.addLayout(btn_layout)

            def _copy():
                try:
                    QApplication.clipboard().setText(str(error_msg))
                except Exception:
                    logger.debug("复制错误到剪贴板失败（非致命）", exc_info=True)

            def _open_log():
                try:
                    from pathlib import Path

                    log_file = Path.home() / ".momenttransfer" / "momenttransfer.log"
                    if log_file.exists():
                        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_file)))
                    else:
                        QMessageBox.information(dlg, "日志未找到", f"未找到日志文件: {log_file}")
                except Exception:
                    logger.debug("打开日志文件失败（非致命）", exc_info=True)

            copy_btn.clicked.connect(_copy)
            open_log_btn.clicked.connect(_open_log)
            close_btn.clicked.connect(dlg.close)

            dlg.resize(700, 400)
            dlg.show()
        except Exception:
            logger.debug("显示非模态错误详情失败（非致命）", exc_info=True)

    BUTTON_LAYOUT_THRESHOLD = 720

    def update_button_layout(self, threshold=None):
        """根据窗口宽度在网格中切换按钮位置 - 委托给 LayoutManager"""
        try:
            self.layout_manager.update_button_layout(threshold)
        except AttributeError:
            logger.warning("LayoutManager 未初始化")
        except Exception as e:
            logger.error("更新按钮布局失败: %s", e)

    # 事件处理方法委托给 EventManager
    def resizeEvent(self, event):
        """窗口大小改变事件"""
        if hasattr(self, "event_manager") and self.event_manager:
            self.event_manager.on_resize_event(event)
        return super().resizeEvent(event)

    def showEvent(self, event):
        """在窗口首次显示后触发初始化"""
        if hasattr(self, "event_manager") and self.event_manager:
            self.event_manager.on_show_event(event)
        return super().showEvent(event)

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        if hasattr(self, "event_manager") and self.event_manager:
            self.event_manager.on_close_event(event)
        return super().closeEvent(event)

    def _force_layout_refresh(self):
        """委托给 LayoutManager.force_layout_refresh()"""
        try:
            if hasattr(self, "layout_manager") and self.layout_manager:
                self.layout_manager.force_layout_refresh()
        except Exception:
            logger.debug("_force_layout_refresh delegated call failed", exc_info=True)

    def _refresh_layouts(self):
        """委托给 LayoutManager 刷新布局与按钮布局"""
        try:
            if hasattr(self, "layout_manager") and self.layout_manager:
                try:
                    self.layout_manager.refresh_layouts()
                finally:
                    self.layout_manager.update_button_layout()
        except Exception:
            logger.debug("_refresh_layouts delegated call failed", exc_info=True)

    # ----- 辅助方法：配置预览已委托给 ConfigManager -----

    def _add_source_part(self):
        """添加 Source Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, "_is_initializing", False):
            return
        try:
            self.part_manager.add_source_part()
        except Exception as e:
            logger.error("添加 Source Part 失败: %s", e)

    def _remove_source_part(self):
        """删除当前 Source Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, "_is_initializing", False):
            return
        try:
            self.part_manager.remove_source_part()
        except Exception as e:
            logger.error("删除 Source Part 失败: %s", e)

    def _add_target_part(self):
        """添加 Target Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, "_is_initializing", False):
            return
        try:
            self.part_manager.add_target_part()
        except Exception as e:
            logger.error("添加 Target Part 失败: %s", e)

    def _remove_target_part(self):
        """删除当前 Target Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, "_is_initializing", False):
            return
        try:
            self.part_manager.remove_target_part()
        except Exception as e:
            logger.error("删除 Target Part 失败: %s", e)

    def _on_src_partname_changed(self, new_text: str):
        """Part Name 文本框变化 - 委托给 PartManager"""
        if getattr(self, "_is_initializing", False):
            return
        if self.part_manager:
            self.part_manager.on_source_part_name_changed(new_text)

    def _on_tgt_partname_changed(self, new_text: str):
        """Part Name 文本框变化 - 委托给 PartManager"""
        if getattr(self, "_is_initializing", False):
            return
        if self.part_manager:
            self.part_manager.on_target_part_name_changed(new_text)

    # 批处理控制方法委托给 BatchManager
    def request_cancel_batch(self):
        if self.batch_manager:
            self.batch_manager.request_cancel_batch()

    def _setup_gui_logging(self):
        """设置日志系统，将所有日志输出到 GUI 的处理日志面板"""
        try:
            logging_manager = LoggingManager(self)
            logging_manager.setup_gui_logging()
        except Exception as e:
            logger.debug("GUI logging setup failed (non-fatal): %s", e, exc_info=True)

    def _set_controls_locked(self, locked: bool):
        """锁定或解锁与配置相关的控件，防止用户在批处理运行期间修改配置。

        locked=True 时禁用；locked=False 时恢复。此方法尽量保持幂等并静默忽略缺失控件。
        """
        try:
            if hasattr(self, "ui_state_manager") and self.ui_state_manager:
                self.ui_state_manager.set_controls_locked(locked)
        except Exception:
            logger.debug("_set_controls_locked delegation failed", exc_info=True)


def _initialize_exception_hook():
    """设置初始化期间的异常钩子，用于在初始化期间阻止异常弹窗"""
    original_excepthook = sys.excepthook

    def custom_excepthook(exc_type, exc_value, traceback_obj):
        """在初始化期间，仅记录异常而不显示弹窗"""
        # 获取当前正在执行的主窗口实例（如果存在）
        main_window = None
        for obj in list(QApplication.topLevelWidgets()):
            if isinstance(obj, IntegratedAeroGUI):
                main_window = obj
                break

        # 如果主窗口正在初始化，记录异常但不显示弹窗
        if main_window and getattr(main_window, "_is_initializing", False):
            logger.debug(
                f"初始化期间捕获异常（被抑制）: {exc_type.__name__}: {exc_value}"
            )
            return

        # 否则使用原始钩子显示异常
        original_excepthook(exc_type, exc_value, traceback_obj)

    sys.excepthook = custom_excepthook


def main():
    # 设置初始化异常钩子
    _initialize_exception_hook()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # 设置统一字体与样式表（styles.qss）以实现统一主题与可维护的样式
    try:
        from PySide6.QtGui import QFont

        app.setFont(QFont("Segoe UI", 10))
    except Exception:
        logger.debug("设置应用字体失败（非致命）", exc_info=True)
    # 按系统主题自动加载明/暗样式
    try:

        def _is_windows_dark_mode() -> bool:
            try:
                import platform

                if platform.system().lower() != "windows":
                    return False
                import winreg

                key_path = (
                    r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"
                )
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    # 0 表示暗色，1 表示浅色
                    val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                    return int(val) == 0
            except Exception:
                return False

        base_dir = Path(__file__).resolve().parent.parent
        dark = _is_windows_dark_mode()
        qss_file = base_dir / ("styles.dark.qss" if dark else "styles.qss")
        if qss_file.exists():
            with open(qss_file, "r", encoding="utf-8") as fh:
                app.setStyleSheet(fh.read())
        elif dark:
            # 兜底：若无暗色QSS，应用深色调色板
            from PySide6.QtGui import QColor, QPalette

            pal = QPalette()
            pal.setColor(QPalette.Window, QColor(45, 45, 48))
            pal.setColor(QPalette.WindowText, QColor(230, 230, 230))
            pal.setColor(QPalette.Base, QColor(37, 37, 38))
            pal.setColor(QPalette.AlternateBase, QColor(45, 45, 48))
            pal.setColor(QPalette.ToolTipBase, QColor(45, 45, 48))
            pal.setColor(QPalette.ToolTipText, QColor(230, 230, 230))
            pal.setColor(QPalette.Text, QColor(230, 230, 230))
            pal.setColor(QPalette.Button, QColor(45, 45, 48))
            pal.setColor(QPalette.ButtonText, QColor(230, 230, 230))
            pal.setColor(QPalette.BrightText, QColor(255, 0, 0))
            pal.setColor(QPalette.Highlight, QColor(0, 120, 215))
            pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
            app.setPalette(pal)
    except Exception:
        logger.debug("自动主题加载失败（忽略）", exc_info=True)
    window = IntegratedAeroGUI()
    window.show()
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        # 在控制台运行 GUI 时，按 Ctrl+C 时优雅退出
        logger.info("收到中断信号(Ctrl+C)，正在退出应用")
        try:
            app.quit()
        except Exception:
            logger.debug("尝试退出应用时关闭失败（非致命）", exc_info=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
