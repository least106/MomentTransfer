"""
MomentTransfer GUI 主窗口模块
向后兼容入口：从 gui 包导入模块化的组件

重构说明：
- Mpl3DCanvas -> gui/canvas.py
- ExperimentalDialog -> gui/dialogs.py
- BatchProcessThread -> gui/batch_thread.py
- IntegratedAeroGUI -> 保留在此文件（待进一步拆分）
"""

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

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
            on_format_config=self.configure_data_format,
            on_undo=self.undo_batch_processing,
            on_browse=self.browse_batch_input,
            on_pattern_changed=lambda: self._on_pattern_changed(),
            on_select_all=self._select_all_files,
            on_select_none=self._select_none_files,
            on_invert_selection=self._invert_file_selection,
            on_quick_select=self._quick_select,
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
            # 应用配置后自动切换到文件列表
            try:
                if hasattr(self, "tab_main"):
                    self.tab_main.setCurrentIndex(0)  # 文件列表在第0个Tab
            except Exception:
                pass
        except AttributeError:
            # 如果管理器未初始化，记录警告
            logger.warning("配置Manager 未初始化，无法应用配置")
        except Exception as e:
            logger.error("应用配置失败: %s", e)

    # 配置格式方法委托给 ConfigManager
    def configure_data_format(self):
        # 全局数据格式配置已移除：请使用 per-file format（file-sidecar/目录 format.json/registry）。
        try:
            QMessageBox.information(
                self,
                "提示",
                "已移除全局数据格式配置。\n"
                "请为每类数据文件提供 format.json（同目录）或 <文件名>.format.json（侧车），"
                "或使用 registry 进行格式匹配。",
            )
        except Exception:
            pass

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

    def _on_pattern_changed(self):
        """当匹配模式改变时刷新文件列表（委托给 BatchManager）。"""
        try:
            self.batch_manager.on_pattern_changed()
        except Exception:
            logger.debug("_on_pattern_changed delegated call failed", exc_info=True)

    def run_batch_processing(self):
        """运行批处理 - 委托给 BatchManager"""
        try:
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
            dlg.exec()
        except Exception:
            logger.debug("无法显示错误对话框", exc_info=True)

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

    def undo_batch_processing(self):
        if self.batch_manager:
            self.batch_manager.undo_batch_processing()

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
        pass
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
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()
