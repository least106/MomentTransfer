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
        # Source 面板始终显示（不使用复选框控制）
        self.file_list_widget = None
        self.layout_manager = None
        self.visualization_manager = None
        self.batch_manager = None
        self.part_manager = None
        self.config_manager = None
        self.setWindowTitle("MomentTransfer")
        self.resize(1500, 900)

        self._is_initializing = True  # 标记正在初始化，禁止弹窗
        self._show_event_fired = False  # 标记 showEvent 是否已触发过
        self.calculator = None
        self.signal_bus = SignalBus.instance()
        self.current_config = None
        self.project_model: ProjectConfigModel | None = None
        self.data_config = None
        self.canvas3d = None
        self.visualization_window = None

        self.init_ui()
        try:
            self._connect_signals()
        except Exception:
            logger.debug("_connect_signals 初始化失败（占位）", exc_info=True)
        # 注意：不在这里设置 _is_initializing = False
        # 将在 show() 之后通过延迟定时器设置，以避免 showEvent 期间的弹窗

    def init_ui(self):
        """初始化界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        # 设置主布局的边距，使界面更紧凑
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # 使用垂直分割器：上方是配置面板，下方是批量处理面板
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(4)  # 设置分割条宽度
        
        # 先创建 config_panel（需要在 ConfigManager 初始化前）
        config_panel = self.create_config_panel()
        splitter.addWidget(config_panel)
        splitter.addWidget(self.create_operation_panel())
        # 调整拉伸因子，配置面板和批量处理面板各占一半
        splitter.setStretchFactor(0, 1)  # 上方配置面板
        splitter.setStretchFactor(1, 1)  # 下方批量处理面板
        # 初始 splitter 大小
        try:
            splitter.setSizes([380, 420])  # 上方配置面板占更少空间
        except Exception:
            logger.debug("splitter.setSizes failed (non-fatal)", exc_info=True)

        main_layout.addWidget(splitter)
        self.statusBar().showMessage("就绪 - 请加载或创建配置")

        # 根据当前窗口宽度设置按钮初始布局
        try:
            self.update_button_layout()
        except Exception:
            # 若方法尚未定义或出现异常，记录调试堆栈以便诊断，但不阻止 UI 启动
            logger.debug("update_button_layout failed (non-fatal)", exc_info=True)
        
        # 初始化各个管理器（ConfigManager 需要 config_panel）
        try:
            self.config_manager = ConfigManager(self, config_panel)
            self.part_manager = PartManager(self)
            self.batch_manager = BatchManager(self)
            self.visualization_manager = VisualizationManager(self)
            self.layout_manager = LayoutManager(self)
            logger.info("所有管理器初始化成功")
        except Exception as e:
            logger.error(f"管理器初始化失败: {e}")
            # 继续运行，即使管理器初始化失败

    def create_config_panel(self):
        """创建配置编辑器面板（委托 ConfigPanel 组件），并保持旧属性兼容。"""
        panel = ConfigPanel(self)

        # 兼容旧代码：保持对旧控件的引用
        self.source_panel = panel.source_panel
        self.target_panel = panel.target_panel
        self.btn_load = panel.btn_load
        self.btn_save = panel.btn_save
        self.btn_apply = panel.btn_apply

        self._setup_panel_compatibility()

        # 注意：ConfigPanel 的 loadRequested/saveRequested/applyRequested 信号
        # 已在 ConfigManager.__init__() 中连接，无需在此重复连接
        
        # 面板内部的部件信号（改为使用 SignalBus 请求，在面板内部已连接）
        self.source_panel.partSelected.connect(self._on_source_part_changed_wrapper)

        # Target 同样由面板发起请求（面板已连接到 SignalBus）
        self.target_panel.partSelected.connect(self._on_target_part_changed_wrapper)

        return panel

    def _connect_signals(self):
        """集中信号连接（占位，逐步迁移分散连接）。"""
        try:
            # 基本 UI 控制
            self.signal_bus.controlsLocked.connect(self._set_controls_locked)
        except Exception:
            logger.debug("连接 controlsLocked 信号失败", exc_info=True)
    
    def _setup_panel_compatibility(self):
        """设置面板兼容性 - 保持对旧控件的引用"""
        # Source 面板控件引用
        self.grp_source = self.source_panel
        self.src_part_name = self.source_panel.part_name_input
        self.cmb_source_parts = self.source_panel.part_selector
        self.src_coord_table = self.source_panel.coord_table
        self.btn_add_source_part = self.source_panel.btn_add_part
        self.btn_remove_source_part = self.source_panel.btn_remove_part
        
        # Target 面板控件引用
        self.tgt_part_name = self.target_panel.part_name_input
        self.cmb_target_parts = self.target_panel.part_selector
        self.tgt_coord_table = self.target_panel.coord_table
        self.btn_add_target_part = self.target_panel.btn_add_part
        self.btn_remove_target_part = self.target_panel.btn_remove_part
        
        # 已移除隐藏三元旋钮与旧 Variant 选择器（统一使用面板控件与模型）
        
        # 初始化当前Part名称
        self._current_source_part_name = "Global"
        self._current_target_part_name = "TestModel"
    
    def _on_source_part_changed_wrapper(self):
        """Source Part变化的封装方法"""
        try:
            self._on_source_part_changed()
        except Exception as e:
            logger.debug(f"Source part changed failed: {e}", exc_info=True)
    
    def _on_target_part_changed_wrapper(self):
        """Target Part变化的封装方法"""
        try:
            self._on_target_part_changed()
        except Exception as e:
            logger.debug(f"Target part changed failed: {e}", exc_info=True)

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

    

    def _select_all_files(self):
        """全选文件树中的所有文件项"""
        from PySide6.QtCore import Qt
        self._set_all_file_items_checked(Qt.Checked)

    def _select_none_files(self):
        """全不选文件树中的所有文件项"""
        from PySide6.QtCore import Qt
        self._set_all_file_items_checked(Qt.Unchecked)

    def _invert_file_selection(self):
        """反选文件树中的所有文件项"""
        from PySide6.QtCore import Qt
        # 在此处局部导入 QTreeWidgetItemIterator，避免在模块顶部遗漏导入导致未定义错误
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            # 只反选文件项（有用户数据中存储了路径的项）
            if item.data(0, Qt.UserRole):
                if item.checkState(0) == Qt.Checked:
                    item.setCheckState(0, Qt.Unchecked)
                else:
                    item.setCheckState(0, Qt.Checked)
            iterator += 1

    def _set_all_file_items_checked(self, check_state):
        """设置所有文件项的选中状态（仅文件，不包括目录节点）"""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            # 只选中文件项（有用户数据中存储了路径的项）
            if item.data(0, Qt.UserRole):
                item.setCheckState(0, check_state)
            iterator += 1

    # 注意：_get_coord_from_table 和 _set_coord_to_table 已移到 Panel 中
    # 调用方式改为：self.source_panel.get_coord_data() 和 self.source_panel.set_coord_data()

    def _save_current_source_part(self):
        """将当前 Source 表单保存到新模型（使用强类型接口）。"""
        try:
            part_name = self.src_part_name.text() if hasattr(self, "src_part_name") else "Global"
            payload = self.source_panel.to_variant_payload(part_name)

            # 更新新模型 ProjectConfigModel（使用强类型接口）
            try:
                if self.project_model is None:
                    self.project_model = ProjectConfigModel()
                # 使用面板提供的强类型模型接口
                cs_model = self.source_panel.get_coordinate_system_model()
                refs_model = self.source_panel.get_reference_values_model()
                pm_variant = PMPartVariant(part_name=part_name, coord_system=cs_model, refs=refs_model)
                from src.models.project_model import Part as PMPart
                self.project_model.source_parts[part_name] = PMPart(part_name=part_name, variants=[pm_variant])
            except Exception:
                logger.debug("更新 ProjectConfigModel 失败", exc_info=True)
        except Exception:
            logger.debug("_save_current_source_part failed", exc_info=True)

    def _save_current_target_part(self):
        """将当前 Target 表单保存到新模型（使用强类型接口）。"""
        try:
            part_name = self.tgt_part_name.text() if hasattr(self, "tgt_part_name") else "Target"
            payload = self.target_panel.to_variant_payload(part_name)

            # 更新新模型 ProjectConfigModel（使用强类型接口）
            try:
                if self.project_model is None:
                    self.project_model = ProjectConfigModel()
                # 使用面板提供的强类型模型接口
                cs_model = self.target_panel.get_coordinate_system_model()
                refs_model = self.target_panel.get_reference_values_model()
                pm_variant = PMPartVariant(part_name=part_name, coord_system=cs_model, refs=refs_model)
                from src.models.project_model import Part as PMPart
                self.project_model.target_parts[part_name] = PMPart(part_name=part_name, variants=[pm_variant])
            except Exception:
                logger.debug("更新 ProjectConfigModel 失败", exc_info=True)
        except Exception:
            logger.debug("_save_current_target_part failed", exc_info=True)

    def toggle_source_visibility(self, state):
        """切换 Source 坐标系的显示/隐藏"""
        # Source 面板始终显示，不再响应复选框切换。
        return

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

    def configure_data_format(self):
        """配置全局会话级别的数据格式（不会对单个文件进行侧车/registry 查找或编辑）。"""
        try:
            dlg = ColumnMappingDialog(self)
            # 若已有全局 data_config（字典或类似结构），尝试填充对话框
            try:
                if hasattr(self, 'data_config') and self.data_config:
                    if isinstance(self.data_config, dict):
                        dlg.set_config(self.data_config)
                    else:
                        # 兼容具有属性的配置对象
                        cfg = {}
                        try:
                            cfg['skip_rows'] = getattr(self.data_config, 'skip_rows', None)
                            cols = getattr(self.data_config, 'columns', None) or getattr(self.data_config, 'column_mappings', None)
                            cfg['columns'] = cols or {}
                            cfg['passthrough'] = getattr(self.data_config, 'passthrough', None) or getattr(self.data_config, 'passthrough_columns', [])
                            dlg.set_config(cfg)
                        except Exception:
                            pass
            except Exception:
                logger.debug('Failed to prefill ColumnMappingDialog with global data_config', exc_info=True)

            if dlg.exec() == QDialog.Accepted:
                cfg = dlg.get_config()
                self.data_config = cfg
                QMessageBox.information(self, '已更新', '会话级全局数据格式已更新')
                try:
                    self.update_config_preview()
                except Exception:
                    logger.debug('update_config_preview failed after configure_data_format', exc_info=True)
                # 配置数据格式后自动切换到信息页
                try:
                    if hasattr(self, 'tab_main'):
                        self.tab_main.setCurrentIndex(0)
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.critical(self, '错误', f'无法配置数据格式: {e}')


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

    def resizeEvent(self, event):
        """窗口大小改变事件 - 委托给 LayoutManager"""
        try:
            self.layout_manager.on_resize_event(event)
        except AttributeError:
            logger.debug("LayoutManager 未初始化")
        except Exception:
            logger.debug("resizeEvent 处理失败", exc_info=True)
        return super().resizeEvent(event)

    def showEvent(self, event):
        """在窗口首次显示后延迟触发一次布局更新以确保初始可见性。"""
        # 只在首次显示时执行初始化布局操作
        if not self._show_event_fired:
            self._show_event_fired = True
            try:
                QTimer.singleShot(50, self.update_button_layout)
                QTimer.singleShot(120, self._force_layout_refresh)
                # 在所有初始化定时器完成后（150ms）才重置 _is_initializing
                # panel已经在init_ui中立即创建，所以可以较快重置标志
                QTimer.singleShot(150, lambda: setattr(self, '_is_initializing', False))
            except Exception:
                logger.debug("showEvent scheduling failed", exc_info=True)
                # 如果定时器设置失败，立即重置标志以免永久阻塞弹窗
                self._is_initializing = False
        return super().showEvent(event)

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

    # ----- 新增辅助方法：配置预览 / 最近项目 / 快速处理 -----
    def update_config_preview(self):
        """根据当前的 `self.data_config` 显示数据格式预览（跳过行、列映射、保留列）。"""
        try:
            cfg = getattr(self, 'data_config', None)
            if cfg is None:
                self.lbl_preview_skip.setText('跳过行: -')
                self.lbl_preview_columns.setText('列映射: -')
                self.lbl_preview_passthrough.setText('保留列: -')
                return

            # 支持 dict 或具有属性的对象
            if isinstance(cfg, dict):
                skip = cfg.get('skip_rows')
                cols = cfg.get('columns', {}) or {}
                passth = cfg.get('passthrough', []) or []
            else:
                skip = getattr(cfg, 'skip_rows', None)
                cols = getattr(cfg, 'columns', {}) or {}
                # 兼容不同命名
                passth = getattr(cfg, 'passthrough', None) or getattr(cfg, 'passthrough_columns', []) or []

            # 跳过行
            self.lbl_preview_skip.setText(f"跳过行: {skip if skip is not None else '-'}")

            # 列映射摘要
            def _col_val(k):
                v = cols.get(k)
                return str(v) if v is not None else '缺失'

            col_keys = ['alpha', 'fx', 'fy', 'fz', 'mx', 'my', 'mz']
            col_parts = [f"{k.upper()}={_col_val(k)}" for k in col_keys]
            cols_text = ", ".join(col_parts)
            # 若关键力列缺失，标红提示
            if cols.get('fx') is None or cols.get('fy') is None or cols.get('fz') is None:
                try:
                    self.lbl_preview_columns.setProperty('state', 'error')
                except Exception:
                    pass
            else:
                try:
                    self.lbl_preview_columns.setProperty('state', 'normal')
                except Exception:
                    pass
            self.lbl_preview_columns.setText(f"列映射: {cols_text}")

            # 保留列
            try:
                pt_display = ','.join(str(int(x)) for x in (passth or [])) if passth else '-'
            except Exception:
                pt_display = str(passth)
            self.lbl_preview_passthrough.setText(f"保留列: {pt_display}")

        except Exception:
            logger.debug("update_config_preview failed", exc_info=True)





    def _on_target_part_changed(self):
        """当用户在下拉框选择不同 Part 时 - 委托给 PartManager"""
        # 初始化期间跳过所有逻辑
        if getattr(self, '_is_initializing', False):
            return
        try:
            self.part_manager.on_target_part_changed()
        except AttributeError:
            logger.debug("PartManager 未初始化")
        except Exception as e:
            logger.debug(f"Target Part 切换失败: {e}")

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

    def _on_source_part_changed(self):
        """当用户在 Source 下拉选择不同 Part 时 - 委托给 PartManager"""
        # 初始化期间跳过所有逻辑
        if getattr(self, '_is_initializing', False):
            return
        try:
            self.part_manager.on_source_part_changed()
        except AttributeError:
            logger.debug("PartManager 未初始化")
        except Exception as e:
            logger.debug(f"Source Part 切换失败: {e}")


    def _on_src_partname_changed(self, new_text: str):
        """当用户编辑 Source 的 Part Name 文本框时，实时更新下拉项与 current_config 的 key。

        限制：禁止重名（若输入的新名字已经被另一个 Part 使用，会回退并弹窗警告）。
        """
        try:
            # 初始化期间跳过所有逻辑
            if getattr(self, '_is_initializing', False):
                return
            
            new_text = (new_text or '').strip()
            old = getattr(self, '_current_source_part_name', None)
            
            # 如果是初始设置（old 为 None 且新值为 "Global"），跳过检查
            if old is None and new_text == "Global":
                self._current_source_part_name = new_text
                return
            
            # 当 current_config 可用时，检查重名（允许与自身相同）
            try:
                if hasattr(self, 'current_config') and isinstance(self.current_config, ProjectData):
                    if new_text in self.current_config.source_parts and new_text != old:
                        QMessageBox.warning(self, "重复的部件名", "另一个 Source Part 已使用相同的名称，请使用不同的名称。")
                        # 恢复旧值
                        try:
                            if old is not None and hasattr(self, 'src_part_name'):
                                self.src_part_name.blockSignals(True)
                                self.src_part_name.setText(old)
                                self.src_part_name.blockSignals(False)
                        except Exception:
                            pass
                        return
            except Exception:
                logger.debug("source part duplicate check failed", exc_info=True)

            # 不再实时把文本框改名同步到下拉与 current_config（避免连锁重命名错误）
            # 仅在内部记录新名称，并在原始字典中更新 PartName，以便后续显式保存或切换时持久化。
            # 更新记录的当前名，并同步到原始字典（若存在）以便保存
            old_name = old
            self._current_source_part_name = new_text
            try:
                raw = getattr(self, '_raw_project_dict', None)
                if isinstance(raw, dict):
                    parts = raw.get('Source', {}).get('Parts', [])
                    for p in parts:
                        if p.get('PartName') == old_name:
                            p['PartName'] = new_text
                            # 也更新第一个 Variant 的 PartName 若存在
                            vars_ = p.get('Variants') or []
                            if vars_ and isinstance(vars_[0], dict) and 'PartName' in vars_[0]:
                                vars_[0]['PartName'] = new_text
                            break
            except Exception:
                pass
        except Exception:
            logger.debug("_on_src_partname_changed failed", exc_info=True)

    def _on_tgt_partname_changed(self, new_text: str):
        """当用户编辑 Target 的 Part Name 文本框时，实时更新下拉项与 current_config 的 key。

        限制：禁止重名（若输入的新名字已经被另一个 Part 使用，会回退并弹窗警告）。
        """
        try:
            # 初始化期间跳过所有逻辑
            if getattr(self, '_is_initializing', False):
                return
            
            new_text = (new_text or '').strip()
            old = getattr(self, '_current_target_part_name', None)
            
            # 如果是初始设置（old 为 None 且新值为 "TestModel"），跳过检查
            if old is None and new_text == "TestModel":
                self._current_target_part_name = new_text
                return
            
            # 重名检查
            try:
                if hasattr(self, 'current_config') and isinstance(self.current_config, ProjectData):
                    if new_text in self.current_config.target_parts and new_text != old:
                        QMessageBox.warning(self, "重复的部件名", "另一个 Target Part 已使用相同的名称，请使用不同的名称。")
                        try:
                            if old is not None and hasattr(self, 'tgt_part_name'):
                                self.tgt_part_name.blockSignals(True)
                                self.tgt_part_name.setText(old)
                                self.tgt_part_name.blockSignals(False)
                        except Exception:
                            pass
                        return
            except Exception:
                logger.debug("target part duplicate check failed", exc_info=True)

            # 不再实时把文本框改名同步到下拉与 current_config（避免连锁重命名错误）
            # 仅记录新名称，稍后显式保存或在切换时写回原始字典
            self._current_target_part_name = new_text
            # 同步到原始字典以便保存
            try:
                old_name = old
                if getattr(self, '_raw_project_dict', None) and isinstance(self._raw_project_dict, dict):
                    parts = self._raw_project_dict.get('Target', {}).get('Parts', [])
                    for p in parts:
                        if p.get('PartName') == old_name:
                            p['PartName'] = new_text
                            vars = p.get('Variants') or []
                            if vars and isinstance(vars, list) and 'PartName' in vars[0]:
                                vars[0]['PartName'] = new_text
                            break
            except Exception:
                pass
        except Exception:
            logger.debug("_on_tgt_partname_changed failed", exc_info=True)


    def request_cancel_batch(self):
        """UI 回调：请求取消正在运行的批处理任务"""
        try:
            if hasattr(self, 'batch_thread') and self.batch_thread is not None:
                self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 用户请求取消任务，正在停止...")
                try:
                    self.batch_thread.request_stop()
                except Exception:
                    logger.debug("batch_thread.request_stop 调用失败（可能已结束）", exc_info=True)
                # 禁用取消按钮以避免重复点击
                try:
                    if hasattr(self, 'btn_cancel'):
                        self.btn_cancel.setEnabled(False)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("request_cancel_batch 失败", exc_info=True)

    def undo_batch_processing(self):
        """撤销最近一次批处理操作"""
        try:
            from pathlib import Path
            
            reply = QMessageBox.question(
                self, 
                '确认撤销',
                '确定要撤销最近一次批处理？这将删除本次生成的输出文件（保留源数据）。',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # 只删除本次批处理新生成的文件
            deleted_count = 0
            try:
                output_dir = getattr(self, '_batch_output_dir', None)
                existing_files = getattr(self, '_batch_existing_files', set())
                
                if output_dir and Path(output_dir).exists():
                    output_path = Path(output_dir)
                    # 只删除不在 existing_files 中的文件（即本次新生成的）
                    for file in output_path.glob('*'):
                        if file.is_file() and file.name not in existing_files:
                            try:
                                file.unlink()
                                deleted_count += 1
                            except Exception as e:
                                logger.warning(f"无法删除文件 {file}: {e}")
                    
                    self.txt_batch_log.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✓ 撤销完成，已删除 {deleted_count} 个输出文件")
                    QMessageBox.information(self, '完成', f'已删除 {deleted_count} 个输出文件（源数据保留）')
                else:
                    QMessageBox.warning(self, '提示', '未找到输出目录或没有之前的批处理记录')
                    
                # 禁用撤销按钮
                if hasattr(self, 'btn_undo'):
                    self.btn_undo.setEnabled(False)
                    self.btn_undo.setVisible(False)
                    
                # 清空批处理追踪信息
                self._batch_output_dir = None
                self._batch_existing_files = set()
                    
            except Exception as e:
                logger.error(f"撤销批处理失败: {e}")
                QMessageBox.critical(self, '错误', f'撤销失败: {e}')
                
        except Exception as e:
            logger.error(f"撤销批处理失败: {e}")

    def _setup_gui_logging(self):
        """设置日志系统，将所有日志输出到 GUI 的处理日志面板"""
        try:
            logging_manager = LoggingManager(self)
            logging_manager.setup_gui_logging()
        except Exception as e:
            logger.debug(f"GUI logging setup failed (non-fatal): {e}", exc_info=True)

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        try:
            # 如果批处理正在进行中，先停止它
            if hasattr(self, 'batch_thread') and self.batch_thread is not None and self.batch_thread.isRunning():
                try:
                    self.batch_thread.request_stop()
                    # 等待线程完成（最多1秒）
                    self.batch_thread.wait(1000)
                except Exception:
                    pass
            
            # 接受关闭事件
            event.accept()
        except Exception as e:
            logger.debug(f"closeEvent handling failed: {e}", exc_info=True)
            event.accept()

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
