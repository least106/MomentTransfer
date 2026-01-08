"""
MomentTransfer GUI 主窗口模块
向后兼容入口：从 gui 包导入模块化的组件

重构说明：
- Mpl3DCanvas -> gui/canvas.py
- ColumnMappingDialog, ExperimentalDialog -> gui/dialogs.py
- BatchProcessThread -> gui/batch_thread.py
- IntegratedAeroGUI -> 保留在此文件（待进一步拆分）
"""
import sys
import logging

import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import fnmatch

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox, QFormLayout, QFileDialog,
    QTextEdit, QMessageBox, QProgressBar, QSplitter, QCheckBox, QSpinBox,
    QComboBox,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QScrollArea, QSizePolicy, QGridLayout,
    QTabWidget
)
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QEvent
from PySide6.QtGui import QFont
from src.physics import AeroCalculator
from src.data_loader import ProjectData
from typing import Optional, List, Tuple
from src.format_registry import get_format_for_file
from src.models import ProjectConfigModel, ReferenceValues, CSModel as CSModelAlias, PartVariant as PMPartVariant

# 从模块化包导入组件
# Mpl3DCanvas 延迟加载以加快启动速度（在首次调用show_visualization时加载）
from gui.dialogs import ColumnMappingDialog
from gui.batch_thread import BatchProcessThread
from gui.log_manager import LoggingManager

# 导入管理器和工具
from gui.config_manager import ConfigManager
from gui.part_manager import PartManager
from gui.signal_bus import SignalBus
from gui.batch_manager import BatchManager
from gui.visualization_manager import VisualizationManager
from gui.layout_manager import LayoutManager
from gui.initialization_manager import InitializationManager
from gui.event_manager import EventManager
from gui.compatibility_manager import CompatibilityManager

# 导入面板组件
from gui.panels import SourcePanel, TargetPanel, ConfigPanel, OperationPanel

logger = logging.getLogger(__name__)

# 主题常量（便于代码中引用）
THEME_MAIN = '#0078d7'
THEME_ACCENT = '#28a745'
THEME_DANGER = '#ff6b6b'
THEME_BG = '#f7f9fb'
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
        
        # 核心数据
        self.calculator = None
        self.signal_bus = SignalBus.instance()
        self.current_config = None
        self.project_model: ProjectConfigModel | None = None
        self.data_config = None
        self.canvas3d = None
        self.visualization_window = None
        
        # 管理器占位（将由 InitializationManager 初始化）
        self.config_manager = None
        self.part_manager = None
        self.batch_manager = None
        self.visualization_manager = None
        self.layout_manager = None
        
        # 新管理器
        self.initialization_manager = InitializationManager(self)
        self.event_manager = EventManager(self)
        self.compatibility_manager = CompatibilityManager(self)
        
        # 执行初始化
        self.initialization_manager.setup_ui()
        self.initialization_manager.setup_managers()
        self.initialization_manager.setup_logging()
        
        # 设置兼容性
        self.compatibility_manager.setup_legacy_aliases()
        self.compatibility_manager.handle_legacy_signals()
        
        # 连接信号
        try:
            self._connect_signals()
        except Exception:
            logger.debug("_connect_signals 初始化失败（占位）", exc_info=True)

    def _connect_signals(self):
        """集中信号连接"""
        try:
            # 基本 UI 控制
            self.signal_bus.controlsLocked.connect(self._set_controls_locked)
        except Exception:
            logger.debug("连接 controlsLocked 信号失败", exc_info=True)
    
    # Part 变更封装方法（委托给 PartManager）
    def _on_source_part_changed_wrapper(self):
        if self.part_manager:
            self.part_manager.on_source_part_changed()
    
    def _on_target_part_changed_wrapper(self):
        if self.part_manager:
            self.part_manager.on_target_part_changed()

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
            logger.debug("_setup_gui_logging failed in create_operation_panel", exc_info=True)

        return panel

    

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
            logger.error(f"加载配置失败: {e}")

    def save_config(self):
        """保存配置到JSON - 委托给 ConfigManager"""
        try:
            self.config_manager.save_config()
        except AttributeError:
            # 如果管理器未初始化，记录警告
            logger.warning("ConfigManager 未初始化，无法保存配置")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def apply_config(self):
        """应用当前配置到计算器 - 委托给 ConfigManager"""
        try:
            self.config_manager.apply_config()
            # 应用配置后自动切换到信息页
            try:
                if hasattr(self, 'tab_main'):
                    self.tab_main.setCurrentIndex(0)  # 信息页是第0个Tab
            except Exception:
                pass
        except AttributeError:
            # 如果管理器未初始化，记录警告
            logger.warning("配置Manager 未初始化，无法应用配置")
        except Exception as e:
            logger.error(f"应用配置失败: {e}")

    # 配置格式方法委托给 ConfigManager
    def configure_data_format(self):
        if self.config_manager:
            self.config_manager.configure_data_format()
    
    def update_config_preview(self):
        if self.config_manager:
            self.config_manager.update_config_preview()


    def browse_batch_input(self):
        """选择输入文件或目录 - 委托给 BatchManager"""
        try:
            self.batch_manager.browse_batch_input()
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error(f"浏览批处理输入失败: {e}")

    def _scan_and_populate_files(self, chosen_path):
        """扫描所选路径并刷新文件列表（委托给 BatchManager）。"""
        try:
            self.batch_manager.scan_and_populate_files(chosen_path)
        except Exception:
            logger.debug("_scan_and_populate_files delegated call failed", exc_info=True)

    def _on_pattern_changed(self):
        """当匹配模式改变时刷新文件列表（委托给 BatchManager）。"""
        try:
            self.batch_manager.on_pattern_changed()
        except Exception:
            logger.debug("_on_pattern_changed delegated call failed", exc_info=True)

    def _determine_format_source(self, fp: Path):
        """判断单个文件的格式来源（委托给 BatchManager）。"""
        try:
            return self.batch_manager._determine_format_source(fp)
        except Exception:
            return ("unknown", None)

    def _format_label_from(self, src: str, src_path: Optional[Path]):
        """格式来源标签格式化（委托给 BatchManager）。"""
        try:
            return self.batch_manager._format_label_from(src, src_path)
        except Exception:
            return ("unknown", "", '#dc3545')

    def _refresh_format_labels(self):
        """刷新文件列表的来源标签（委托给 BatchManager）。"""
        try:
            self.batch_manager.refresh_format_labels()
        except Exception:
            logger.debug("_refresh_format_labels delegated call failed", exc_info=True)


    def run_batch_processing(self):
        """运行批处理 - 委托给 BatchManager"""
        try:
            self.batch_manager.run_batch_processing()
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error(f"运行批处理失败: {e}")

    def on_batch_finished(self, message):
        """批处理完成 - 委托给 BatchManager"""
        try:
            self.batch_manager.on_batch_finished(message)
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error(f"处理批处理完成事件失败: {e}")

    def on_batch_error(self, error_msg):
        """批处理出错 - 委托给 BatchManager"""
        try:
            self.batch_manager.on_batch_error(error_msg)
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error(f"处理批处理错误事件失败: {e}")
            try:
                if hasattr(self, 'btn_cancel'):
                    self.btn_cancel.setVisible(False)
                    self.btn_cancel.setEnabled(False)
            except Exception:
                logger.debug("Failed to hide/disable cancel button after error", exc_info=True)

        # 友好的错误提示，包含可行建议
        try:
            dlg = QMessageBox(self)
            dlg.setIcon(QMessageBox.Critical)
            dlg.setWindowTitle("处理失败")
            dlg.setText("批处理过程中发生错误，已记录到日志。请检查输入文件与数据格式配置。")
            dlg.setInformativeText("建议：检查数据格式映射（列索引）、Target 配置中的 MomentCenter/Q/S，或在 GUI 中打开“配置数据格式”进行修正。")
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
            logger.error(f"更新按钮布局失败: {e}")

    # 事件处理方法委托给 EventManager
    def resizeEvent(self, event):
        """窗口大小改变事件"""
        if hasattr(self, 'event_manager') and self.event_manager:
            self.event_manager.on_resize_event(event)
        return super().resizeEvent(event)

    def showEvent(self, event):
        """在窗口首次显示后触发初始化"""
        if hasattr(self, 'event_manager') and self.event_manager:
            self.event_manager.on_show_event(event)
        return super().showEvent(event)
    
    def closeEvent(self, event):
        """处理窗口关闭事件"""
        if hasattr(self, 'event_manager') and self.event_manager:
            self.event_manager.on_close_event(event)
        return super().closeEvent(event)

    def _force_layout_refresh(self):
        """
        尝试强制刷新布局：激活布局并做一个极小的像素级尺寸微调以触发布局重算。

        说明：
        由于 Qt（包括 PySide6/PyQt5）在某些复杂嵌套布局下，调用 layout().activate() 或 processEvents() 可能无法立即刷新所有控件的实际显示，
        尤其是涉及 QSplitter/QScrollArea/QTabWidget 等嵌套时。此处采用“窗口宽度+2像素再还原”的 hack，
        能强制 Qt 的底层布局引擎重新计算和应用所有控件的尺寸与位置。
        该方法在 Windows/Linux/Mac 下 Qt 5/6 均有效，但未来 Qt 版本可能修复此类刷新 bug 时可移除。
        若主窗口被设置为不可调整大小，则此 hack 可能无效。
        """
        try:
            cw = self.centralWidget()
            if cw and cw.layout():
                cw.layout().activate()
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            except Exception:
                logger.debug("QApplication.processEvents failed in _force_layout_refresh", exc_info=True)

            # --- Qt 布局刷新 hack ---
            # 微调窗口宽度 (+2 然后恢复) 以触发底层布局引擎重新布局。
            w = self.width()
            h = self.height()
            # 如果主窗口是可调整大小的，做一次非常小的尺寸变动并回滚
            self.resize(w + 2, h)
            QTimer.singleShot(20, lambda: self.resize(w, h))
        except Exception:
            logger.debug("_force_layout_refresh failed", exc_info=True)

    def _refresh_layouts(self):
        """激活并刷新主要布局与 splitter，以保证子控件正确伸缩。"""
        try:
            cw = self.centralWidget()
            if cw and cw.layout():
                cw.layout().activate()
            # 激活左右 splitter 的布局
            try:
                # 触发按钮布局更新和一次强制刷新
                self.update_button_layout()
            except Exception:
                logger.debug("update_button_layout failed in _refresh_layouts", exc_info=True)
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            except Exception:
                logger.debug("QApplication.processEvents failed in _refresh_layouts", exc_info=True)
            # 轻微调整 splitter 大小以促使 Qt 重新布局（仅在必要时）
            try:
                s = self.findChild(QSplitter)
                if s:
                    sizes = s.sizes()
                    s.setSizes(sizes)
            except Exception:
                logger.debug("Splitter resize refresh failed in _refresh_layouts", exc_info=True)
        except Exception:
            logger.debug("_refresh_layouts failed", exc_info=True)

    # ----- 辅助方法：配置预览已委托给 ConfigManager -----

    def _add_source_part(self):
        """添加 Source Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, '_is_initializing', False):
            return
        try:
            self.part_manager.add_source_part()
        except Exception as e:
            logger.error(f"添加 Source Part 失败: {e}")

    def _remove_source_part(self):
        """删除当前 Source Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, '_is_initializing', False):
            return
        try:
            self.part_manager.remove_source_part()
        except Exception as e:
            logger.error(f"删除 Source Part 失败: {e}")

    def _add_target_part(self):
        """添加 Target Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, '_is_initializing', False):
            return
        try:
            self.part_manager.add_target_part()
        except Exception as e:
            logger.error(f"添加 Target Part 失败: {e}")

    def _remove_target_part(self):
        """删除当前 Target Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, '_is_initializing', False):
            return
        try:
            self.part_manager.remove_target_part()
        except Exception as e:
            logger.error(f"删除 Target Part 失败: {e}")

    def _on_src_partname_changed(self, new_text: str):
        """Part Name 文本框变化 - 委托给 PartManager"""
        if getattr(self, '_is_initializing', False):
            return
        if self.part_manager:
            self.part_manager.on_source_part_name_changed(new_text)

    def _on_tgt_partname_changed(self, new_text: str):
        """Part Name 文本框变化 - 委托给 PartManager"""
        if getattr(self, '_is_initializing', False):
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
            logger.debug(f"GUI logging setup failed (non-fatal): {e}", exc_info=True)

    def _set_controls_locked(self, locked: bool):
        """锁定或解锁与配置相关的控件，防止用户在批处理运行期间修改配置。

        locked=True 时禁用；locked=False 时恢复。此方法尽量保持幂等并静默忽略缺失控件。
        """
        widgets = [
            getattr(self, 'btn_load', None),
            getattr(self, 'btn_save', None),
            getattr(self, 'btn_apply', None),
            getattr(self, 'btn_config_format', None),
            getattr(self, 'btn_registry_register', None),
            getattr(self, 'btn_registry_edit', None),
            getattr(self, 'btn_registry_remove', None),
            getattr(self, 'btn_batch', None),
            getattr(self, 'inp_registry_db', None),
            getattr(self, 'inp_registry_pattern', None),
            getattr(self, 'inp_registry_format', None),
        ]
        for w in widgets:
            try:
                if w is not None:
                    w.setEnabled(not locked)
            except Exception:
                pass

        # 取消按钮在锁定时仍应保持可见/可用以提供取消能力
        try:
            if hasattr(self, 'btn_cancel'):
                # 当 locked=True 时显示取消按钮并保持启用；当 locked=False 时隐藏
                if locked:
                    self.btn_cancel.setVisible(True)
                    self.btn_cancel.setEnabled(True)
                else:
                    self.btn_cancel.setVisible(False)
                    self.btn_cancel.setEnabled(False)
        except Exception:
            logger.debug("Failed to set btn_cancel visibility/state in _set_controls_locked", exc_info=True)


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
        if main_window and getattr(main_window, '_is_initializing', False):
            logger.debug(f"初始化期间捕获异常（被抑制）: {exc_type.__name__}: {exc_value}")
            return
        
        # 否则使用原始钩子显示异常
        original_excepthook(exc_type, exc_value, traceback_obj)
    
    sys.excepthook = custom_excepthook


def main():
    # 设置初始化异常钩子
    _initialize_exception_hook()
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    # 设置统一字体与样式表（styles.qss）以实现统一主题与可维护的样式
    try:
        from PySide6.QtGui import QFont
        app.setFont(QFont('Segoe UI', 10))
    except Exception:
        pass
    try:
        # main_window 位于 gui/ 下，样式文件在仓库根目录
        qss_path = Path(__file__).resolve().parent.parent / 'styles.qss'
        if qss_path.exists():
            with open(qss_path, 'r', encoding='utf-8') as fh:
                app.setStyleSheet(fh.read())
    except Exception:
        logger.debug('加载 styles.qss 失败（忽略）', exc_info=True)
    window = IntegratedAeroGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
