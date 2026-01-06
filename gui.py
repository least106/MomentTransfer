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

# 从模块化包导入组件
# Mpl3DCanvas 延迟加载以加快启动速度（在首次调用show_visualization时加载）
from gui.dialogs import ColumnMappingDialog
from gui.batch_thread import BatchProcessThread

# 导入管理器和工具
from gui.ui_utils import create_input, create_triple_spin, get_numeric_value, create_vector_row
from gui.config_manager import ConfigManager
from gui.part_manager import PartManager
from gui.batch_manager import BatchManager
from gui.visualization_manager import VisualizationManager
from gui.layout_manager import LayoutManager

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
        self.chk_show_source = None
        self.grp_file_list = None
        self.layout_manager = None
        self.visualization_manager = None
        self.batch_manager = None
        self.part_manager = None
        self.config_manager = None
        self.setWindowTitle("MomentTransfer")
        self.resize(1400, 850)

        self._is_initializing = True  # 标记正在初始化，禁止弹窗
        self._show_event_fired = False  # 标记 showEvent 是否已触发过
        self.calculator = None
        self.current_config = None
        self.data_config = None
        self.canvas3d = None
        self.visualization_window = None

        self.init_ui()
        # 注意：不在这里设置 _is_initializing = False
        # 将在 show() 之后通过延迟定时器设置，以避免 showEvent 期间的弹窗

    def init_ui(self):
        """初始化界面"""
        # 初始化各个管理器
        try:
            self.config_manager = ConfigManager(self)
            self.part_manager = PartManager(self)
            self.batch_manager = BatchManager(self)
            self.visualization_manager = VisualizationManager(self)
            self.layout_manager = LayoutManager(self)
            logger.info("所有管理器初始化成功")
        except Exception as e:
            logger.error(f"管理器初始化失败: {e}")
            # 继续运行，即使管理器初始化失败
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        # 设置主布局的边距，使界面更紧凑
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # 使用垂直分割器：上方是配置面板，下方是批量处理面板
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(4)  # 设置分割条宽度
        splitter.addWidget(self.create_config_panel())
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

    def create_config_panel(self):
        """创建左侧配置编辑面板"""
        # 在整个panel构建期间禁用应用级别的信号，避免任何误触发
        try:
            app = QApplication.instance()
            if app:
                app.blockSignals(True)
        except Exception:
            pass
        
        panel = QWidget()
        # 横向布局需要更大的最小宽度
        panel.setMinimumWidth(900)
        panel.setMaximumHeight(550)  # 限制最大高度，避免过多空白
        # 移除最大宽度限制，允许横向布局充分展开
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)

        # 标题
        title = QLabel("配置编辑器")
        try:
            title.setObjectName('panelTitle')
        except Exception:
            pass
        layout.addWidget(title)

        # === Source 坐标系（可折叠） ===
        self.chk_show_source = QCheckBox("显示 Source 坐标系设置")
        try:
            self.chk_show_source.setObjectName('sectionToggle')
        except Exception:
            pass
        self.chk_show_source.stateChanged.connect(self.toggle_source_visibility)

        self.grp_source = QGroupBox("Source Coordinate System")
        # 设置尺寸约束，避免过多空白
        self.grp_source.setMinimumWidth(350)
        self.grp_source.setMaximumHeight(500)
        self.grp_source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        form_source = QFormLayout()
        try:
            form_source.setLabelAlignment(Qt.AlignRight)
        except Exception:
            pass

        # Source 坐标系输入表格
        self.src_coord_table = self._create_coord_table('src')
        
        # 保留原有的独立控件引用（用于兼容现有代码）
        # 但这些不再显示在UI中，而是作为表格的数据访问接口
        self.src_ox, self.src_oy, self.src_oz = self._create_triple_spin(0.0, 0.0, 0.0)
        self.src_xx, self.src_xy, self.src_xz = self._create_triple_spin(1.0, 0.0, 0.0)
        self.src_yx, self.src_yy, self.src_yz = self._create_triple_spin(0.0, 1.0, 0.0)
        self.src_zx, self.src_zy, self.src_zz = self._create_triple_spin(0.0, 0.0, 1.0)

        # Source Part Name（与 Target 对等）
        # 支持多 Part/Variant 的下拉选择（当从 ProjectData 加载时会显示）
        self.src_part_name = self._create_input("")  # 先设置空字符串避免触发信号
        self.src_part_name.blockSignals(True)  # 阻止信号在初始化期间触发
        self.src_part_name.setText("Global")
        self._current_source_part_name = "Global"  # 初始化当前名称
        # 当用户直接编辑 Part Name 时，实时更新下拉列表（若可见）与 current_config 的键名
        try:
            self.src_part_name.textChanged.connect(self._on_src_partname_changed)
        except Exception:
            logger.debug("无法连接 src_part_name.textChanged", exc_info=True)
        # 注意：信号恢复延迟到 panel 返回前，避免在构建期间触发
        # 注意：控件创建时必须指定 parent，否则在 Windows 下调用 setVisible(True)
        # 可能会导致其被当作“顶层窗口”短暂显示（表现为启动时弹窗一闪而过）。
        self.cmb_source_parts = QComboBox(panel)
        self.cmb_source_parts.blockSignals(True)  # 初始也阻止信号
        self.spin_source_variant = QSpinBox(panel)
        self.spin_source_variant.setRange(0, 100)
        self.spin_source_variant.setValue(0)
        self.spin_source_variant.setVisible(False)
        self.cmb_source_parts.currentTextChanged.connect(lambda _: self._on_source_part_changed())

        self.src_xx, self.src_xy, self.src_xz = self._create_triple_spin(1.0, 0.0, 0.0)

        self.src_yx, self.src_yy, self.src_yz = self._create_triple_spin(0.0, 1.0, 0.0)

        self.src_zx, self.src_zy, self.src_zz = self._create_triple_spin(0.0, 0.0, 1.0)

        # Source 力矩中心（单行三元）
        self.src_mcx, self.src_mcy, self.src_mcz = self._create_triple_spin(0.0, 0.0, 0.0)

        # 当有多个 source part 时显示下拉；否则使用自由文本框
        form_source.addRow("Part Name:", self.src_part_name)
        # 使用带新增/删除按钮的组合控件以便在未加载文件时也能管理 Parts
        src_part_widget = QWidget()
        src_part_h = QHBoxLayout(src_part_widget)
        src_part_h.setContentsMargins(0, 0, 0, 0)
        src_part_h.addWidget(self.cmb_source_parts)
        self.btn_add_source_part = QPushButton("+")
        self.btn_add_source_part.setMaximumWidth(28)
        self.btn_remove_source_part = QPushButton("−")
        self.btn_remove_source_part.setMaximumWidth(28)
        try:
            self.btn_add_source_part.setObjectName('smallButton')
            self.btn_remove_source_part.setObjectName('smallButton')
        except Exception:
            pass
        self.btn_add_source_part.clicked.connect(self._add_source_part)
        self.btn_remove_source_part.clicked.connect(self._remove_source_part)
        src_part_h.addWidget(self.btn_add_source_part)
        src_part_h.addWidget(self.btn_remove_source_part)
        form_source.addRow("选择 Source Part:", src_part_widget)
        # Variant 索引已移除（始终使用第 0 个 variant）；避免用户混淆，因此不在表单中显示
        
        # 使用表格显示坐标系（3x4表格取代12个独立输入框）
        lbl = QLabel("坐标系:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
        form_source.addRow(lbl, self.src_coord_table)

        # Source 参考量（与 Target 对等）
        self.src_cref = self._create_input("1.0")
        self.src_bref = self._create_input("1.0")
        self.src_sref = self._create_input("10.0")
        self.src_q = self._create_input("1000.0")

        lbl = QLabel("Moment Center:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_source.addRow(lbl, self._create_vector_row(self.src_mcx, self.src_mcy, self.src_mcz))
        lbl = QLabel("C_ref (m):")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_source.addRow(lbl, self.src_cref)
        lbl = QLabel("B_ref (m):")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_source.addRow(lbl, self.src_bref)
        lbl = QLabel("S_ref (m²):")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_source.addRow(lbl, self.src_sref)
        lbl = QLabel("Q (Pa):")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_source.addRow(lbl, self.src_q)

        self.grp_source.setLayout(form_source)
        self.grp_source.setVisible(False)

        # === Target 配置 ===
        grp_target = QGroupBox("Target Configuration")
        # 设置尺寸约束，避免过多空白
        grp_target.setMinimumWidth(350)
        grp_target.setMaximumHeight(500)
        grp_target.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        form_target = QFormLayout()
        try:
            form_target.setLabelAlignment(Qt.AlignRight)
        except Exception:
            pass

        # Part Name
        # 使用 _create_input 以保持与 Source 的输入框样式与宽度一致
        self.tgt_part_name = self._create_input("")  # 先设置空字符串避免触发信号
        self.tgt_part_name.blockSignals(True)  # 阻止信号在初始化期间触发
        self.tgt_part_name.setText("TestModel")
        self._current_target_part_name = "TestModel"  # 初始化当前名称
        try:
            self.tgt_part_name.textChanged.connect(self._on_tgt_partname_changed)
        except Exception:
            logger.debug("无法连接 tgt_part_name.textChanged", exc_info=True)
        # 注意：信号恢复延迟到 panel 返回前，避免在构建期间触发
        form_target.addRow("Part Name:", self.tgt_part_name)

        # 当加载 ProjectData 时，展示可选的 Part 下拉框与 Variant 索引选择器
        # 同上：创建时绑定 parent，避免未 parent 状态下短暂成为顶层窗口。
        self.cmb_target_parts = QComboBox(panel)
        self.cmb_target_parts.blockSignals(True)  # 初始也阻止信号
        self.spin_target_variant = QSpinBox(panel)
        self.spin_target_variant.setRange(0, 100)
        self.spin_target_variant.setValue(0)
        self.spin_target_variant.setVisible(False)
        # 当选择不同 part 时，更新 variant 最大值（在 load_config 中设置）
        self.cmb_target_parts.currentTextChanged.connect(lambda _: self._on_target_part_changed())
        # 目标 Part 下拉也使用带新增/删除的组合控件
        tgt_part_widget = QWidget()
        tgt_part_h = QHBoxLayout(tgt_part_widget)
        tgt_part_h.setContentsMargins(0, 0, 0, 0)
        tgt_part_h.addWidget(self.cmb_target_parts)
        self.btn_add_target_part = QPushButton("+")
        self.btn_add_target_part.setMaximumWidth(28)
        self.btn_remove_target_part = QPushButton("−")
        self.btn_remove_target_part.setMaximumWidth(28)
        try:
            self.btn_add_target_part.setObjectName('smallButton')
            self.btn_remove_target_part.setObjectName('smallButton')
        except Exception:
            pass
        self.btn_add_target_part.clicked.connect(self._add_target_part)
        self.btn_remove_target_part.clicked.connect(self._remove_target_part)
        tgt_part_h.addWidget(self.btn_add_target_part)
        tgt_part_h.addWidget(self.btn_remove_target_part)
        form_target.addRow("选择 Target Part:", tgt_part_widget)
        # Variant 索引已移除（始终使用第 0 个 variant）

        # Target 坐标系输入表格
        self.tgt_coord_table = self._create_coord_table('tgt')
        
        # 保留原有的独立控件引用（用于兼容现有代码）
        self.tgt_ox, self.tgt_oy, self.tgt_oz = self._create_triple_spin(0.0, 0.0, 0.0)
        self.tgt_xx, self.tgt_xy, self.tgt_xz = self._create_triple_spin(1.0, 0.0, 0.0)
        self.tgt_yx, self.tgt_yy, self.tgt_yz = self._create_triple_spin(0.0, 1.0, 0.0)
        self.tgt_zx, self.tgt_zy, self.tgt_zz = self._create_triple_spin(0.0, 0.0, 1.0)

        # 使用表格显示坐标系
        lbl = QLabel("坐标系:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
        form_target.addRow(lbl, self.tgt_coord_table)

        # Moment Center
        self.tgt_mcx, self.tgt_mcy, self.tgt_mcz = self._create_triple_spin(0.5, 0.0, 0.0)
        form_target.addRow("Moment Center:", self._create_vector_row(self.tgt_mcx, self.tgt_mcy, self.tgt_mcz))

        # Target 参考量（与 Source 对等）
        self.tgt_cref = self._create_input("1.0")
        self.tgt_bref = self._create_input("1.0")
        self.tgt_sref = self._create_input("10.0")
        self.tgt_q = self._create_input("1000.0")

        lbl = QLabel("C_ref (m):")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_target.addRow(lbl, self.tgt_cref)
        lbl = QLabel("B_ref (m):")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_target.addRow(lbl, self.tgt_bref)
        lbl = QLabel("S_ref (m²):")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_target.addRow(lbl, self.tgt_sref)
        lbl = QLabel("Q (Pa):")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_target.addRow(lbl, self.tgt_q)
        grp_target.setLayout(form_target)

        # === 配置操作按钮（竖向排列）===
        btn_widget = QWidget()
        btn_widget.setFixedWidth(120)
        btn_layout = QVBoxLayout(btn_widget)
        btn_layout.setSpacing(8)

        self.btn_load = QPushButton("加载配置")
        self.btn_load.setFixedHeight(40)
        try:
            self.btn_load.setObjectName('secondaryButton')
            self.btn_load.setToolTip('从磁盘加载配置文件')
        except Exception:
            pass
        self.btn_load.clicked.connect(self.load_config)

        self.btn_save = QPushButton("保存配置")
        self.btn_save.setFixedHeight(40)
        try:
            self.btn_save.setObjectName('primaryButton')
            self.btn_save.setToolTip('将当前配置保存到磁盘 (Ctrl+S)')
            self.btn_save.setShortcut('Ctrl+S')
        except Exception:
            pass
        self.btn_save.clicked.connect(self.save_config)

        self.btn_apply = QPushButton("应用配置")
        self.btn_apply.setFixedHeight(40)
        try:
            self.btn_apply.setObjectName('primaryButton')
            self.btn_apply.setShortcut('Ctrl+R')
            self.btn_apply.setToolTip('应用当前配置并初始化计算器 (Ctrl+Enter)')
        except Exception:
            pass
        self.btn_apply.clicked.connect(self.apply_config)

        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_apply)
        btn_layout.addStretch()

        # === 横向布局：Source + Target + 按钮 ===
        coord_layout = QHBoxLayout()
        coord_layout.addWidget(self.grp_source)
        coord_layout.addWidget(grp_target)
        coord_layout.addWidget(btn_widget)
        # 设置比例：Source:Target:按钮 = 1:1:0（按钮固定宽度）
        coord_layout.setStretch(0, 1)
        coord_layout.setStretch(1, 1)
        coord_layout.setStretch(2, 0)

        # 添加横向布局到主布局
        layout.addWidget(self.chk_show_source)
        layout.addLayout(coord_layout)
        
        # 设置伸缩：让横向布局在垂直方向扩展以填充空间
        try:
            layout.setStretch(1, 1)  # chk_show_source index 0, coord_layout index 1
        except Exception:
            logger.debug("layout.setStretch failed (non-fatal)", exc_info=True)
        layout.addStretch()

        # 在返回前统一恢复所有被阻止的信号，此时UI已完全构建
        # 这样可以避免在构建过程中触发信号导致的弹窗
        try:
            self.src_part_name.blockSignals(False)
            self.tgt_part_name.blockSignals(False)
            self.cmb_source_parts.blockSignals(False)
            self.cmb_target_parts.blockSignals(False)
        except Exception:
            logger.debug("恢复信号失败", exc_info=True)
        
        # 恢复应用级别的信号
        try:
            app = QApplication.instance()
            if app:
                app.blockSignals(False)
        except Exception:
            pass

        return panel

    def create_operation_panel(self):
        """创建右侧操作面板"""
        # 在整个panel构建期间禁用应用级别的信号，避免任何误触发
        try:
            app = QApplication.instance()
            if app:
                app.blockSignals(True)
        except Exception:
            pass
        
        panel = QWidget()
        panel.setMinimumWidth(900)
        panel.setMinimumHeight(300)
        # 移除最大宽度限制，批量处理面板应该占据整个宽度
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)  # 从 15 减为 8，更紧凑

        self.grp_batch = QGroupBox("批量处理 (Batch Processing)")
        self.grp_batch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 右侧批处理的主布局（作为实例属性以便在其它方法中引用）
        self.layout_batch = QVBoxLayout()
        self.layout_batch.setSpacing(6)  # 更紧凑的间距
        self.layout_batch.setContentsMargins(8, 8, 8, 8)  # 减少外边距

        # 文件选择表单（作为实例属性供后续方法访问）
        self.file_form = QFormLayout()
        self.file_form.setSpacing(4)  # 更小的间距
        self.file_form.setContentsMargins(2, 2, 2, 2)  # 减少内边距

        # 输入行：文件路径 + 浏览
        self.inp_batch_input = QLineEdit()
        self.inp_batch_input.setPlaceholderText("选择文件或目录...")
        self.inp_batch_input.setMaximumWidth(650)  # 限制最大宽度
        btn_browse_input = QPushButton("浏览")
        btn_browse_input.setMaximumWidth(80)
        try:
            btn_browse_input.setObjectName('smallButton')
            btn_browse_input.setToolTip('选择输入文件或目录')
        except Exception:
            pass
        btn_browse_input.clicked.connect(self.browse_batch_input)
        input_row = QHBoxLayout()
        input_row.addWidget(self.inp_batch_input)
        input_row.addWidget(btn_browse_input)

        # 文件匹配模式 + 预设
        self.inp_pattern = QLineEdit("*.csv")
        self.inp_pattern.setToolTip("文件名匹配模式，如 *.csv, data_*.xlsx；支持分号多模式：*.csv;*.xlsx")
        self.inp_pattern.setMaximumWidth(300)  # 限制最大宽度
        self.cmb_pattern_preset = QComboBox()
        try:
            self.cmb_pattern_preset.setObjectName('patternPreset')
        except Exception:
            pass
        self._pattern_presets = [
            ("自定义", None),
            ("仅 CSV", "*.csv"),
            ("CSV + Excel", "*.csv;*.xlsx;*.xls"),
            ("特殊格式", "*.mtfmt;*.mtdata;*.txt;*.dat"),
            ("全部支持", "*.csv;*.xlsx;*.xls;*.mtfmt;*.mtdata;*.txt;*.dat"),
        ]
        for name, _pat in self._pattern_presets:
            self.cmb_pattern_preset.addItem(name)

        def _apply_preset(idx: int) -> None:
            try:
                if idx < 0 or idx >= len(self._pattern_presets):
                    return
                pat = self._pattern_presets[idx][1]
                if not pat:
                    return
                try:
                    self.inp_pattern.blockSignals(True)
                    self.inp_pattern.setText(pat)
                finally:
                    self.inp_pattern.blockSignals(False)
                # 主动触发刷新（兼容某些情况下 textChanged 未触发）
                try:
                    self._on_pattern_changed()
                except Exception:
                    pass
            except Exception:
                logger.debug('apply preset failed', exc_info=True)

        def _mark_custom(_text: str) -> None:
            try:
                # 用户手动编辑时切回“自定义”
                if self.cmb_pattern_preset.currentIndex() != 0:
                    self.cmb_pattern_preset.blockSignals(True)
                    self.cmb_pattern_preset.setCurrentIndex(0)
                    self.cmb_pattern_preset.blockSignals(False)
            except Exception:
                pass

        try:
            self.cmb_pattern_preset.currentIndexChanged.connect(_apply_preset)
        except Exception:
            logger.debug('无法连接 cmb_pattern_preset 信号', exc_info=True)

        try:
            self.inp_pattern.textEdited.connect(_mark_custom)
        except Exception:
            pass

        pattern_row = QHBoxLayout()
        pattern_row.addWidget(QLabel("匹配模式:"))
        pattern_row.addWidget(self.inp_pattern)
        pattern_row.addWidget(self.cmb_pattern_preset)
        try:
            # 实时根据模式更新文件列表（若已选择输入路径）
            self.inp_pattern.textChanged.connect(lambda _: self._on_pattern_changed())
        except Exception:
            logger.debug("无法连接 inp_pattern.textChanged 信号", exc_info=True)





        # 直接将文件表单添加到批处理布局
        self.file_form.addRow("输入路径:", input_row)
        self.file_form.addRow("匹配模式:", pattern_row)
        self.layout_batch.addLayout(self.file_form)

        # 文件列表（使用树形结构显示目录）
        self.grp_file_list = QGroupBox("文件列表")
        self.grp_file_list.setVisible(False)
        file_list_layout = QVBoxLayout()
        
        # 添加操作按钮行
        btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_none = QPushButton("全不选")
        self.btn_select_invert = QPushButton("反选")
        
        for btn in (self.btn_select_all, self.btn_select_none, self.btn_select_invert):
            btn.setMaximumWidth(80)
            try:
                btn.setObjectName('smallButton')
            except Exception:
                pass
        
        self.btn_select_all.clicked.connect(self._select_all_files)
        self.btn_select_none.clicked.connect(self._select_none_files)
        self.btn_select_invert.clicked.connect(self._invert_file_selection)
        
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_select_none)
        btn_row.addWidget(self.btn_select_invert)
        btn_row.addStretch()
        file_list_layout.addLayout(btn_row)
        
        # 使用TreeWidget显示文件层次结构
        from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QHeaderView
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["文件/目录", "状态"])
        self.file_tree.setColumnWidth(0, 400)
        
        # 设置表头自动调整
        header = self.file_tree.header()
        try:
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        except Exception:
            pass
        
        self.file_tree.setMinimumHeight(200)
        file_list_layout.addWidget(self.file_tree)
        self.grp_file_list.setLayout(file_list_layout)

        # 存储文件信息的字典：{file_path: tree_item}
        self._file_tree_items = {}

        # 数据格式配置按钮
        self.btn_config_format = QPushButton("⚙ 配置数据格式")
        try:
            self.btn_config_format.setObjectName('secondaryButton')
            self.btn_config_format.setShortcut('Ctrl+Shift+F')
        except Exception:
            pass
        self.btn_config_format.setToolTip("设置会话级别的全局数据格式（仅全局，不再按每个文件查找侧车/registry）")
        self.btn_config_format.clicked.connect(self.configure_data_format)

        # 进度条（隐藏）
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        # 执行/撤销按钮
        self.btn_batch = QPushButton("开始批量处理")
        try:
            self.btn_batch.setObjectName('primaryButton')
            self.btn_batch.setShortcut('Ctrl+R')
            self.btn_batch.setToolTip('开始批量处理。运行时会禁用此按钮。')
        except Exception:
            pass
        self.btn_batch.clicked.connect(self.run_batch_processing)

        # 撤销按钮（初始隐藏）
        self.btn_undo = QPushButton("撤销批处理")
        try:
            self.btn_undo.setObjectName('secondaryButton')
            self.btn_undo.setShortcut('Ctrl+Z')
            self.btn_undo.setToolTip('撤销最近一次批处理操作')
        except Exception:
            pass
        self.btn_undo.clicked.connect(self.undo_batch_processing)
        self.btn_undo.setVisible(False)
        self.btn_undo.setEnabled(False)
        
        # 保存最近批处理的信息用于撤销
        self._last_batch_info = None

        self.txt_batch_log = QTextEdit()
        try:
            self.txt_batch_log.setObjectName('batchLog')
        except Exception:
            pass
        self.txt_batch_log.setReadOnly(True)
        self.txt_batch_log.setFont(QFont("Consolas", 9))
        self.txt_batch_log.setMinimumHeight(160)
        self.txt_batch_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 按钮容器（grid）
        self.btn_widget = QWidget()
        try:
            self.btn_widget.setObjectName('btnWidget')
        except Exception:
            pass
        BTN_CONTENT_HEIGHT = 30
        V_PADDING = 12
        self.btn_widget.setMinimumHeight(BTN_CONTENT_HEIGHT + V_PADDING)
        self.btn_widget.setFixedHeight(BTN_CONTENT_HEIGHT + V_PADDING)
        self.btn_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_grid = QGridLayout(self.btn_widget)
        self.btn_grid.setSpacing(0)
        self.btn_grid.setContentsMargins(0, 0, 0, 0)
        self.btn_grid.setColumnStretch(0, 1)
        self.btn_grid.setColumnStretch(1, 1)
        self.btn_config_format.setFixedHeight(40)
        self.btn_config_format.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_batch.setFixedHeight(40)
        self.btn_batch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_grid.addWidget(self.btn_config_format, 0, 0)
        self.btn_grid.addWidget(self.btn_batch, 0, 1)
        self.btn_grid.addWidget(self.btn_undo, 1, 1)

        # 把form和按钮行放入批处理组内
        self.layout_batch.addWidget(self.btn_widget)
        self.layout_batch.addWidget(self.progress_bar)

        # 创建 Tab 容器：信息、文件列表和处理日志
        self.tab_main = QTabWidget()
        try:
            self.tab_main.setObjectName('mainTab')
        except Exception:
            pass
        
        # Tab 0: 信息页
        self.info_tab_widget = QWidget()
        info_tab_layout = QVBoxLayout(self.info_tab_widget)
        info_tab_layout.setContentsMargins(12, 12, 12, 12)
        info_tab_layout.setSpacing(8)
        
        # 配置状态
        self.lbl_status = QLabel("未加载配置")
        try:
            self.lbl_status.setObjectName('statusLabel')
            font = self.lbl_status.font()
            font.setPointSize(10)
            font.setBold(True)
            self.lbl_status.setFont(font)
        except Exception:
            pass
        info_tab_layout.addWidget(self.lbl_status)
        
        # 数据格式预览区域
        format_group = QGroupBox("数据格式预览")
        format_layout = QVBoxLayout(format_group)
        format_layout.setSpacing(4)
        
        self.lbl_preview_skip = QLabel("跳过行: -")
        self.lbl_preview_passthrough = QLabel("保留列: -")
        self.lbl_preview_columns = QLabel("列映射: -")
        
        for w in (self.lbl_preview_skip, self.lbl_preview_passthrough, self.lbl_preview_columns):
            try:
                w.setObjectName('previewText')
            except Exception:
                pass
            format_layout.addWidget(w)
        
        info_tab_layout.addWidget(format_group)
        info_tab_layout.addStretch()
        
        self.tab_main.addTab(self.info_tab_widget, "信息")
        
        # Tab 1: 文件列表
        self.tab_main.addTab(self.grp_file_list, "文件列表")
        
        # Tab 2: 处理日志
        self.tab_logs_widget = QWidget()
        tab_logs_layout = QVBoxLayout(self.tab_logs_widget)
        tab_logs_layout.setContentsMargins(0, 0, 0, 0)
        tab_logs_layout.addWidget(self.txt_batch_log)
        self.tab_main.addTab(self.tab_logs_widget, "处理日志")
        
        # 添加 Tab 到批处理布局
        self.layout_batch.addWidget(self.tab_main)



        # 设置伸缩：Tab 拉伸占满空间
        try:
            idx_tab = self.layout_batch.indexOf(self.tab_main)
            if idx_tab >= 0:
                self.layout_batch.setStretch(idx_tab, 1)
        except Exception:
            logger.debug("layout_batch.setStretch for tab failed (non-fatal)", exc_info=True)

        # 将布局应用到 grp_batch
        self.grp_batch.setLayout(self.layout_batch)

        layout.addWidget(self.grp_batch)

        # 设置伸缩：批处理组占据所有可用空间
        try:
            idx_batch = layout.indexOf(self.grp_batch)
            if idx_batch >= 0:
                layout.setStretch(idx_batch, 1)
        except Exception:
            try:
                layout.setStretch(0, 1)
            except Exception:
                pass

        layout.addStretch()
        
        # 恢复应用级别的信号
        try:
            app = QApplication.instance()
            if app:
                app.blockSignals(False)
        except Exception:
            pass

        return panel

    def _create_input(self, default_value):
        """创建输入框"""
        inp = QLineEdit(default_value)
        # 提高最大宽度以适配高 DPI 和更长的文本输入，使 Source/Target 输入框长度一致
        inp.setMaximumWidth(220)
        try:
            inp.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        except Exception:
            logger.debug("inp.setSizePolicy failed (non-fatal)", exc_info=True)
        return inp

    def _create_coord_table(self, name_prefix: str):
        """
        创建坐标系输入表格（3x4: 4行×3列）
        行：Orig, X, Y, Z
        列：x, y, z分量
        
        Args:
            name_prefix: 控件名称前缀（如 'src' 或 'tgt'）
            
        Returns:
            QTableWidget实例
        """
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
        from PySide6.QtCore import Qt
        
        table = QTableWidget(4, 3)
        table.setHorizontalHeaderLabels(['X', 'Y', 'Z'])
        table.setVerticalHeaderLabels(['Orig', 'X轴', 'Y轴', 'Z轴'])
        
        # 设置默认值
        default_values = [
            [0.0, 0.0, 0.0],  # Orig
            [1.0, 0.0, 0.0],  # X轴
            [0.0, 1.0, 0.0],  # Y轴
            [0.0, 0.0, 1.0],  # Z轴
        ]
        
        for row in range(4):
            for col in range(3):
                item = QTableWidgetItem(str(default_values[row][col]))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
            # 设置更紧凑的行高
            table.setRowHeight(row, 26)
        
        # 设置表格样式 - 紧凑但完整显示
        table.setFixedHeight(145)  # 减小高度
        table.setFixedWidth(260)   # 略微减小宽度
        
        # 调整列宽
        for col in range(3):
            table.setColumnWidth(col, 70)
            table.setColumnWidth(col, 70)
        
        try:
            table.setObjectName(f'{name_prefix}_coord_table')
        except Exception:
            pass
        
        return table

    def _create_triple_spin(self, a: float, b: float, c: float):
        """创建一行三个紧凑型 QDoubleSpinBox，返回 (spin_a, spin_b, spin_c)"""
        s1 = QDoubleSpinBox()
        s2 = QDoubleSpinBox()
        s3 = QDoubleSpinBox()
        for s in (s1, s2, s3):
            try:
                s.setRange(-1e6, 1e6)
                s.setDecimals(2)
                s.setSingleStep(0.1)
                s.setValue(0.0)
                s.setProperty('compact', 'true')
                s.setMaximumWidth(96)
            except Exception:
                logger.debug("triple spin init failed", exc_info=True)
        s1.setValue(float(a))
        s2.setValue(float(b))
        s3.setValue(float(c))
        # ToolTip 提示
        try:
            s1.setToolTip('X 分量')
            s2.setToolTip('Y 分量')
            s3.setToolTip('Z 分量')
        except Exception:
            pass
        return s1, s2, s3

    def _num(self, widget):
        """从 QDoubleSpinBox 或 QLineEdit 返回 float 值的统一访问器"""
        try:
            if hasattr(widget, 'value'):
                return float(widget.value())
            else:
                return float(widget.text())
        except Exception as e:
            # 若解析失败，抛出 ValueError 以便上层显示提示
            raise ValueError(f"无法解析数值输入: {e}")

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

    def _get_coord_from_table(self, table):
        """
        从坐标表格中读取值
        
        Args:
            table: QTableWidget实例
            
        Returns:
            包含4个向量的字典：{'Orig': [x,y,z], 'X': [x,y,z], 'Y': [x,y,z], 'Z': [x,y,z]}
        """
        result = {
            'Orig': [0.0, 0.0, 0.0],
            'X': [1.0, 0.0, 0.0],
            'Y': [0.0, 1.0, 0.0],
            'Z': [0.0, 0.0, 1.0],
        }
        
        row_keys = ['Orig', 'X', 'Y', 'Z']
        
        for row_idx, key in enumerate(row_keys):
            for col_idx in range(3):
                try:
                    item = table.item(row_idx, col_idx)
                    if item:
                        result[key][col_idx] = float(item.text())
                except (ValueError, AttributeError):
                    # 保持默认值
                    pass
        
        return result

    def _set_coord_to_table(self, table, coord_dict):
        """
        设置坐标表格的值
        
        Args:
            table: QTableWidget实例
            coord_dict: 包含Orig/X/Y/Z的字典
        """
        from PySide6.QtWidgets import QTableWidgetItem
        from PySide6.QtCore import Qt
        
        row_keys = ['Orig', 'X', 'Y', 'Z']
        
        for row_idx, key in enumerate(row_keys):
            vector = coord_dict.get(key, [0.0, 0.0, 0.0])
            for col_idx in range(3):
                try:
                    value = float(vector[col_idx])
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row_idx, col_idx, item)
                except Exception:
                    pass

    def _create_vector_row(self, inp1, inp2, inp3):
        """创建向量输入行 [x, y, z]"""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lb1 = QLabel("[")
        lb_comma1 = QLabel(",")
        lb_comma2 = QLabel(",")
        lb2 = QLabel("]")
        for lb in (lb1, lb_comma1, lb_comma2, lb2):
            try:
                lb.setObjectName('smallLabel')
            except Exception:
                pass
        # 对传入的输入框标记为 compact 以便样式表进行收缩
        try:
            for w in (inp1, inp2, inp3):
                w.setProperty('compact', 'true')
                try:
                    w.setMaximumWidth(96)
                except Exception:
                    pass
        except Exception:
            pass
        layout.addWidget(lb1)
        layout.addWidget(inp1)
        layout.addWidget(lb_comma1)
        layout.addWidget(inp2)
        layout.addWidget(lb_comma2)
        layout.addWidget(inp3)
        layout.addWidget(lb2)
        # 使用小间距替代 stretch，避免把右侧控件挤出可见区域
        layout.addSpacing(6)
        return row

    def _save_current_source_part(self):
        """将当前 Source 表单保存回 self._raw_project_dict 中对应的 Part（只更新第一个 Variant）。"""
        try:
            old = getattr(self, '_current_source_part_name', None)
            if not old:
                return
            if not getattr(self, '_raw_project_dict', None) or not isinstance(self._raw_project_dict, dict):
                return
            parts = self._raw_project_dict.get('Source', {}).get('Parts', [])
            for p in parts:
                if p.get('PartName') == old:
                    vars = p.setdefault('Variants', [])
                    if not vars:
                        vars.append({})
                    v = vars[0]
                    try:
                        v['PartName'] = self.src_part_name.text()
                    except Exception:
                        pass
                    v['CoordSystem'] = {
                        'Orig': [self._num(self.src_ox), self._num(self.src_oy), self._num(self.src_oz)],
                        'X': [self._num(self.src_xx), self._num(self.src_xy), self._num(self.src_xz)],
                        'Y': [self._num(self.src_yx), self._num(self.src_yy), self._num(self.src_yz)],
                        'Z': [self._num(self.src_zx), self._num(self.src_zy), self._num(self.src_zz)]
                    }
                    v['MomentCenter'] = [self._num(self.src_mcx), self._num(self.src_mcy), self._num(self.src_mcz)]
                    try:
                        v['Cref'] = float(self.src_cref.text())
                        v['Bref'] = float(self.src_bref.text())
                        v['Q'] = float(self.src_q.text())
                        v['S'] = float(self.src_sref.text())
                    except Exception:
                        pass
                    break
            try:
                self.current_config = ProjectData.from_dict(self._raw_project_dict)
            except Exception:
                pass
        except Exception:
            logger.debug("_save_current_source_part failed", exc_info=True)

    def _save_current_target_part(self):
        """将当前 Target 表单保存回 self._raw_project_dict 中对应的 Part（只更新第一个 Variant）。"""
        try:
            old = getattr(self, '_current_target_part_name', None)
            if not old:
                return
            if not getattr(self, '_raw_project_dict', None) or not isinstance(self._raw_project_dict, dict):
                return
            parts = self._raw_project_dict.get('Target', {}).get('Parts', [])
            for p in parts:
                if p.get('PartName') == old:
                    vars = p.setdefault('Variants', [])
                    if not vars:
                        vars.append({})
                    v = vars[0]
                    try:
                        v['PartName'] = self.tgt_part_name.text()
                    except Exception:
                        pass
                    v['CoordSystem'] = {
                        'Orig': [self._num(self.tgt_ox), self._num(self.tgt_oy), self._num(self.tgt_oz)],
                        'X': [self._num(self.tgt_xx), self._num(self.tgt_xy), self._num(self.tgt_xz)],
                        'Y': [self._num(self.tgt_yx), self._num(self.tgt_yy), self._num(self.tgt_yz)],
                        'Z': [self._num(self.tgt_zx), self._num(self.tgt_zy), self._num(self.tgt_zz)]
                    }
                    v['MomentCenter'] = [self._num(self.tgt_mcx), self._num(self.tgt_mcy), self._num(self.tgt_mcz)]
                    try:
                        v['Cref'] = float(self.tgt_cref.text())
                        v['Bref'] = float(self.tgt_bref.text())
                        v['Q'] = float(self.tgt_q.text())
                        v['S'] = float(self.tgt_sref.text())
                    except Exception:
                        pass
                    break
            try:
                self.current_config = ProjectData.from_dict(self._raw_project_dict)
            except Exception:
                pass
        except Exception:
            logger.debug("_save_current_target_part failed", exc_info=True)

    def toggle_source_visibility(self, state):
        """切换 Source 坐标系的显示/隐藏"""
        self.grp_source.setVisible(state == Qt.Checked)
        # 切换后刷新布局以确保组框填满高度并使右侧底部元素可见
        try:
            QTimer.singleShot(30, self._refresh_layouts)
        except RuntimeError as re:
            logger.debug("QTimer.singleShot 调度失败: %s", re, exc_info=True)
            try:
                self._refresh_layouts()
            except Exception as e:
                logger.exception("_refresh_layouts 直接调用时出现异常")
        except Exception as e:
            logger.exception("调度 _refresh_layouts 时出现意外异常")

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
        """在原始项目或内存结构中添加一个新的 Source Part - 委托给 PartManager"""
        # 初始化期间禁止添加操作，避免误触发弹窗
        if getattr(self, '_is_initializing', False):
            return
        try:
            self.part_manager.add_source_part()
            return  # 成功则直接返回
        except AttributeError:
            # PartManager 未初始化，继续执行 fallback 逻辑
            logger.warning("PartManager 未初始化，使用 fallback 逻辑")
        except Exception as e:
            # PartManager 存在但执行失败，记录错误并终止，不执行 fallback
            logger.error(f"添加 Source Part 失败: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "添加失败",
                f"添加 Source Part 时发生错误:\n{str(e)}"
            )
            return  # 不继续执行 fallback
        
        # 只有在 AttributeError 时才执行以下 fallback 逻辑
        raw_project = getattr(self, '_raw_project_dict', None)
        if not isinstance(raw_project, dict):
            logger.debug(
                "_add_source_part fallback aborted: _raw_project_dict 未初始化或不是 dict"
            )
            return
        parts = raw_project.setdefault('Source', {}).setdefault('Parts', [])
        # 基于当前 UI 构造一个新 part，先生成不重复的 PartName
        preferred_name = self.src_part_name.text() if hasattr(self, 'src_part_name') else 'NewSource'
        existing_names = [p.get('PartName') for p in parts if isinstance(p, dict) and 'PartName' in p]
        name = preferred_name
        if name in existing_names:
            # 名称已存在，提示用户选择：覆盖 / 创建唯一名 / 取消
            msg = QMessageBox(self)
            msg.setWindowTitle('已存在的 Part')
            msg.setText(f"Source Part 名称 '{preferred_name}' 已存在。请选择操作：")
            btn_overwrite = msg.addButton('覆盖', QMessageBox.AcceptRole)
            btn_unique = msg.addButton('创建唯一名', QMessageBox.DestructiveRole)
            btn_cancel = msg.addButton('取消', QMessageBox.RejectRole)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == btn_cancel:
                return
            if clicked == btn_overwrite:
                # 查找到已存在的 part 并用新数据覆盖（第一 Variant）
                for p in parts:
                    if p.get('PartName') == preferred_name:
                        try:
                            cref_val = float(self.src_cref.text()) if hasattr(self, 'src_cref') and self.src_cref.text() else 1.0
                        except (ValueError, AttributeError):
                            logger.warning(f"无效的 Cref 值: {getattr(self.src_cref, 'text', lambda: 'N/A')()}，使用默认值 1.0")
                            cref_val = 1.0
                        try:
                            bref_val = float(self.src_bref.text()) if hasattr(self, 'src_bref') and self.src_bref.text() else 1.0
                        except (ValueError, AttributeError):
                            logger.warning(f"无效的 Bref 值，使用默认值 1.0")
                            bref_val = 1.0
                        try:
                            q_val = float(self.src_q.text()) if hasattr(self, 'src_q') and self.src_q.text() else 1000.0
                        except (ValueError, AttributeError):
                            logger.warning(f"无效的 Q 值，使用默认值 1000.0")
                            q_val = 1000.0
                        try:
                            s_val = float(self.src_sref.text()) if hasattr(self, 'src_sref') and self.src_sref.text() else 10.0
                        except (ValueError, AttributeError):
                            logger.warning(f"无效的 S 值，使用默认值 10.0")
                            s_val = 10.0

                        p['Variants'] = [
                            {
                                'PartName': preferred_name,
                                'CoordSystem': {
                                    'Orig': [self._num(self.src_ox), self._num(self.src_oy), self._num(self.src_oz)],
                                    'X': [self._num(self.src_xx), self._num(self.src_xy), self._num(self.src_xz)],
                                    'Y': [self._num(self.src_yx), self._num(self.src_yy), self._num(self.src_yz)],
                                    'Z': [self._num(self.src_zx), self._num(self.src_zy), self._num(self.src_zz)]
                                },
                                'MomentCenter': [self._num(self.src_mcx), self._num(self.src_mcy), self._num(self.src_mcz)],
                                'Cref': cref_val,
                                'Bref': bref_val,
                                'Q': q_val,
                                'S': s_val
                            }
                        ]
                        break
                try:
                    self.current_config = ProjectData.from_dict(self._raw_project_dict)
                except Exception:
                    pass
                return
            # 创建唯一名
            i = 1
            while f"{preferred_name}_{i}" in existing_names:
                i += 1
            name = f"{preferred_name}_{i}"

        # 安全获取参数值，带错误处理
        try:
            cref_val = float(self.src_cref.text()) if hasattr(self, 'src_cref') and self.src_cref.text() else 1.0
        except (ValueError, AttributeError):
            logger.warning(f"无效的 Cref 值，使用默认值 1.0")
            cref_val = 1.0
        try:
            bref_val = float(self.src_bref.text()) if hasattr(self, 'src_bref') and self.src_bref.text() else 1.0
        except (ValueError, AttributeError):
            logger.warning(f"无效的 Bref 值，使用默认值 1.0")
            bref_val = 1.0
        try:
            q_val = float(self.src_q.text()) if hasattr(self, 'src_q') and self.src_q.text() else 1000.0
        except (ValueError, AttributeError):
            logger.warning(f"无效的 Q 值，使用默认值 1000.0")
            q_val = 1000.0
        try:
            s_val = float(self.src_sref.text()) if hasattr(self, 'src_sref') and self.src_sref.text() else 10.0
        except (ValueError, AttributeError):
            logger.warning(f"无效的 S 值，使用默认值 10.0")
            s_val = 10.0

        new_part = {
            'PartName': name,
            'Variants': [
                {
                    'PartName': name,
                    'CoordSystem': {
                        'Orig': [self._num(self.src_ox), self._num(self.src_oy), self._num(self.src_oz)],
                        'X': [self._num(self.src_xx), self._num(self.src_xy), self._num(self.src_xz)],
                        'Y': [self._num(self.src_yx), self._num(self.src_yy), self._num(self.src_yz)],
                        'Z': [self._num(self.src_zx), self._num(self.src_zy), self._num(self.src_zz)]
                    },
                    'MomentCenter': [self._num(self.src_mcx), self._num(self.src_mcy), self._num(self.src_mcz)],
                    'Cref': cref_val,
                    'Bref': bref_val,
                    'Q': q_val,
                    'S': s_val
                }
            ]
        }
        parts.append(new_part)
        # 更新 combo
        self.cmb_source_parts.addItem(new_part['PartName'])
        self.cmb_source_parts.setVisible(True)
        # 解析为 ProjectData
        try:
            self.current_config = ProjectData.from_dict(self._raw_project_dict)
        except Exception:
            logger.debug("_add_source_part failed", exc_info=True)

    def _remove_source_part(self):
        """从原始项目或内存结构中移除当前选中的 Source Part - 委托给 PartManager"""
        # 初始化期间禁止删除操作
        if getattr(self, '_is_initializing', False):
            return
        try:
            self.part_manager.remove_source_part()
        except AttributeError:
            logger.warning("PartManager 未初始化")
        except Exception as e:
            logger.error(f"删除 Source Part 失败: {e}")

    def _add_target_part(self):
        """添加新 Target Part - 委托给 PartManager"""
        # 初始化期间禁止添加操作，避免误触发弹窗
        if getattr(self, '_is_initializing', False):
            return
        try:
            self.part_manager.add_target_part()
        except AttributeError:
            logger.warning("PartManager 未初始化")
        except Exception as e:
            logger.error(f"添加 Target Part 失败: {e}")

    def _remove_target_part(self):
        """删除当前 Target Part - 委托给 PartManager"""
        # 初始化期间禁止删除操作
        if getattr(self, '_is_initializing', False):
            return
        try:
            self.part_manager.remove_target_part()
        except AttributeError:
            logger.warning("PartManager 未初始化")
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
            import shutil
            
            reply = QMessageBox.question(
                self, 
                '确认撤销',
                '确定要撤销最近一次批处理？这将删除生成的输出文件。',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # 尝试删除最近生成的输出文件
            deleted_count = 0
            try:
                output_dir = getattr(self, 'output_dir', None)
                if output_dir and Path(output_dir).exists():
                    # 删除输出目录中最近创建的文件
                    # 这里简单实现：删除整个输出目录下的所有文件
                    output_path = Path(output_dir)
                    for file in output_path.glob('*'):
                        if file.is_file():
                            try:
                                file.unlink()
                                deleted_count += 1
                            except Exception as e:
                                logger.warning(f"无法删除文件 {file}: {e}")
                    
                    self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 已撤销批处理，删除了 {deleted_count} 个输出文件")
                    QMessageBox.information(self, '完成', f'已删除 {deleted_count} 个输出文件')
                else:
                    QMessageBox.warning(self, '提示', '未找到输出目录')
                    
                # 禁用撤销按钮
                if hasattr(self, 'btn_undo'):
                    self.btn_undo.setEnabled(False)
                    self.btn_undo.setVisible(False)
                    
            except Exception as e:
                logger.error(f"撤销批处理失败: {e}")
                QMessageBox.critical(self, '错误', f'撤销失败: {e}')
                
        except Exception as e:
            logger.error(f"撤销批处理失败: {e}")

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
        qss_path = Path(__file__).resolve().parent / 'styles.qss'
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
