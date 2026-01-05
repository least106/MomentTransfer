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
    QDialog, QDialogButtonBox, QDoubleSpinBox, QScrollArea, QSizePolicy, QGridLayout
)
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QEvent
from PySide6.QtGui import QFont
from src.physics import AeroCalculator
from src.data_loader import ProjectData
from typing import Optional, List, Tuple
from src.format_registry import get_format_for_file, list_mappings, register_mapping, delete_mapping, update_mapping, init_db

# 从模块化包导入组件
from gui.canvas import Mpl3DCanvas
from gui.dialogs import ColumnMappingDialog, ExperimentalDialog
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

# 注意：Mpl3DCanvas, ColumnMappingDialog, ExperimentalDialog, BatchProcessThread
# 已从 gui 包中导入，不再在此文件中定义

class IntegratedAeroGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MomentTransfer")
        self.resize(1400, 850)

        self.calculator = None
        self.current_config = None
        self.data_config = None
        self.canvas3d = None
        self.visualization_window = None

        self.init_ui()

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
        main_layout = QHBoxLayout(central_widget)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.create_config_panel())
        splitter.addWidget(self.create_operation_panel())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        # 初始 splitter 大小，优先显示左侧配置和右侧操作（近似匹配图一布局）
        try:
            splitter.setSizes([520, 880])
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
        panel = QWidget()
        # 给左侧配置面板一个合理的最小宽度，避免在窄窗口时完全压扁
        panel.setMinimumWidth(420)
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        # 标题与可视化按钮
        header_layout = QHBoxLayout()
        title = QLabel("配置编辑器")
        try:
            title.setObjectName('panelTitle')
        except Exception:
            pass

        # 实验功能按钮（打开独立对话框）
        btn_exp = QPushButton('实验功能')
        btn_exp.setToolTip('打开实验性功能对话框（包含 per-file/registry 等实验项）')
        try:
            btn_exp.setObjectName('smallButton')
        except Exception:
            pass
        btn_exp.clicked.connect(lambda: self.open_experimental_dialog())

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(btn_exp)

        layout.addLayout(header_layout)

        # === Source 坐标系（可折叠） ===
        self.chk_show_source = QCheckBox("显示 Source 坐标系设置")
        try:
            self.chk_show_source.setObjectName('sectionToggle')
        except Exception:
            pass
        self.chk_show_source.stateChanged.connect(self.toggle_source_visibility)
        layout.addWidget(self.chk_show_source)

        self.grp_source = QGroupBox("Source Coordinate System")
        # 允许在垂直方向扩展以填充空间，使底部按钮保持在窗口底部
        self.grp_source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form_source = QFormLayout()
        try:
            form_source.setLabelAlignment(Qt.AlignRight)
        except Exception:
            pass

        # 使用单行三元 QDoubleSpinBox 以节省垂直空间
        self.src_ox, self.src_oy, self.src_oz = self._create_triple_spin(0.0, 0.0, 0.0)

        # Source Part Name（与 Target 对等）
        # 支持多 Part/Variant 的下拉选择（当从 ProjectData 加载时会显示）
        self.src_part_name = self._create_input("Global")
        # 当用户直接编辑 Part Name 时，实时更新下拉列表（若可见）与 current_config 的键名
        try:
            self.src_part_name.textChanged.connect(self._on_src_partname_changed)
        except Exception:
            logger.debug("无法连接 src_part_name.textChanged", exc_info=True)
        self.cmb_source_parts = QComboBox()
        self.cmb_source_parts.setVisible(True)
        self.spin_source_variant = QSpinBox()
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
        # 使用一致宽度的 QLabel 以避免表单断行并保持对齐
        lbl = QLabel("Orig:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_source.addRow(lbl, self._create_vector_row(self.src_ox, self.src_oy, self.src_oz))

        lbl = QLabel("X:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_source.addRow(lbl, self._create_vector_row(self.src_xx, self.src_xy, self.src_xz))

        lbl = QLabel("Y:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_source.addRow(lbl, self._create_vector_row(self.src_yx, self.src_yy, self.src_yz))

        lbl = QLabel("Z:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_source.addRow(lbl, self._create_vector_row(self.src_zx, self.src_zy, self.src_zz))

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
        layout.addWidget(self.grp_source)

        # === Target 配置 ===
        grp_target = QGroupBox("Target Configuration")
        grp_target.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form_target = QFormLayout()
        try:
            form_target.setLabelAlignment(Qt.AlignRight)
        except Exception:
            pass

        # Part Name
        # 使用 _create_input 以保持与 Source 的输入框样式与宽度一致
        self.tgt_part_name = self._create_input("TestModel")
        try:
            self.tgt_part_name.textChanged.connect(self._on_tgt_partname_changed)
        except Exception:
            logger.debug("无法连接 tgt_part_name.textChanged", exc_info=True)
        form_target.addRow("Part Name:", self.tgt_part_name)

        # 当加载 ProjectData 时，展示可选的 Part 下拉框与 Variant 索引选择器
        self.cmb_target_parts = QComboBox()
        self.cmb_target_parts.setVisible(True)
        self.spin_target_variant = QSpinBox()
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

        # Target 坐标系
        self.tgt_ox, self.tgt_oy, self.tgt_oz = self._create_triple_spin(0.0, 0.0, 0.0)

        self.tgt_xx, self.tgt_xy, self.tgt_xz = self._create_triple_spin(1.0, 0.0, 0.0)

        self.tgt_yx, self.tgt_yy, self.tgt_yz = self._create_triple_spin(0.0, 1.0, 0.0)

        self.tgt_zx, self.tgt_zy, self.tgt_zz = self._create_triple_spin(0.0, 0.0, 1.0)

        lbl = QLabel("Orig:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_target.addRow(lbl, self._create_vector_row(self.tgt_ox, self.tgt_oy, self.tgt_oz))

        lbl = QLabel("X:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_target.addRow(lbl, self._create_vector_row(self.tgt_xx, self.tgt_xy, self.tgt_xz))

        lbl = QLabel("Y:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_target.addRow(lbl, self._create_vector_row(self.tgt_yx, self.tgt_yy, self.tgt_yz))

        lbl = QLabel("Z:")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_target.addRow(lbl, self._create_vector_row(self.tgt_zx, self.tgt_zy, self.tgt_zz))

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

        # === 配置操作按钮 ===
        btn_layout = QHBoxLayout()

        self.btn_load = QPushButton("加载配置")
        self.btn_load.setFixedHeight(34)
        try:
            self.btn_load.setObjectName('secondaryButton')
            self.btn_load.setToolTip('从磁盘加载配置文件')
        except Exception:
            pass
        self.btn_load.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_load.clicked.connect(self.load_config)

        self.btn_save = QPushButton("保存配置")
        self.btn_save.setFixedHeight(34)
        try:
            self.btn_save.setObjectName('primaryButton')
            self.btn_save.setToolTip('将当前配置保存到磁盘 (Ctrl+S)')
            self.btn_save.setShortcut('Ctrl+S')
        except Exception:
            pass
        self.btn_save.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_save.clicked.connect(self.save_config)

        self.btn_apply = QPushButton("应用配置")
        self.btn_apply.setFixedHeight(34)
        try:
            self.btn_apply.setObjectName('primaryButton')
            self.btn_apply.setShortcut('Ctrl+R')
            self.btn_apply.setToolTip('应用当前配置并初始化计算器 (Ctrl+Enter)')
        except Exception:
            pass
        self.btn_apply.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_apply.clicked.connect(self.apply_config)

        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_apply)

        # 添加到主布局
        layout.addWidget(grp_target)
        # layout.addWidget(grp_global)  # 删除未定义的grp_global，避免报错
        layout.addLayout(btn_layout)
        # 设置伸缩：让 Source/Target 在垂直方向扩展以填充空间
        # header_layout index 0, chk_show_source index 1, grp_source index 2, grp_target index 3, btn_layout index 4
        try:
            layout.setStretch(2, 1)
            layout.setStretch(3, 1)
        except Exception:
            logger.debug("layout.setStretch failed (non-fatal)", exc_info=True)
        layout.addStretch()

        return panel

    def create_operation_panel(self):
        """创建右侧操作面板"""
        panel = QWidget()
        panel.setMinimumWidth(600)
        layout = QVBoxLayout(panel)
        layout.setSpacing(15)

        # 将关键 UI 对象设为实例属性以确保在函数内所有分支和外部方法中均可访问，避免静态分析误报
        # 基本状态与批处理容器
        self.status_group = QGroupBox("当前配置状态")
        status_layout = QHBoxLayout()
        self.lbl_status = QLabel("未加载配置")
        try:
            self.lbl_status.setObjectName('statusLabel')
        except Exception:
            pass
        status_layout.addWidget(self.lbl_status)
        status_layout.addStretch()
        self.status_group.setLayout(status_layout)

        self.grp_batch = QGroupBox("批量处理 (Batch Processing)")
        self.grp_batch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 右侧批处理的主布局（作为实例属性以便在其它方法中引用）
        self.layout_batch = QVBoxLayout()

        # 文件选择表单（作为实例属性供后续方法访问）
        self.file_form = QFormLayout()

        # 输入行：文件路径 + 浏览
        self.inp_batch_input = QLineEdit()
        self.inp_batch_input.setPlaceholderText("选择文件或目录...")
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

        # 文件匹配模式
        self.inp_pattern = QLineEdit("*.csv")
        self.inp_pattern.setToolTip("文件名匹配模式，如 *.csv, data_*.xlsx")
        pattern_row = QHBoxLayout()
        pattern_row.addWidget(QLabel("匹配模式:"))
        pattern_row.addWidget(self.inp_pattern)
        try:
            # 实时根据模式更新文件列表（若已选择输入路径）
            self.inp_pattern.textChanged.connect(lambda _: self._on_pattern_changed())
        except Exception:
            logger.debug("无法连接 inp_pattern.textChanged 信号", exc_info=True)

        # Registry DB 输入行（可选，实验性）
        self.inp_registry_db = QLineEdit()
        self.inp_registry_db.setPlaceholderText("可选: format registry 数据库 (.sqlite) - 实验性")
        try:
            self.inp_registry_db.textChanged.connect(lambda _: self._refresh_format_labels())
        except Exception:
            logger.debug("Failed to connect inp_registry_db.textChanged signal", exc_info=True)
        btn_browse_registry = QPushButton("浏览")
        btn_browse_registry.setMaximumWidth(80)
        try:
            btn_browse_registry.setObjectName('smallButton')
            btn_browse_registry.setToolTip('选择 format registry (.sqlite) 文件')
        except Exception:
            pass
        btn_browse_registry.clicked.connect(self.browse_registry_db)
        registry_row = QHBoxLayout()
        registry_row.addWidget(QLabel("格式注册表 (实验):"))
        registry_row.addWidget(self.inp_registry_db)
        registry_row.addWidget(btn_browse_registry)

        # per-file 开关（实验性）
        self.chk_enable_sidecar = QCheckBox("启用 per-file 覆盖（sidecar/registry，实验）")
        self.chk_enable_sidecar.setChecked(False)
        self.chk_enable_sidecar.setToolTip("默认关闭；需在实验性功能中显式启用；启用后批处理将按文件尝试使用侧车/registry 覆盖全局配置。")
        registry_row.addWidget(self.chk_enable_sidecar)
        # 记录 per-file 开关状态，并提供实例级回调以避免 AttributeError
        self._perfile_enabled = False
        self._set_perfile_enabled = lambda checked: setattr(self, "_perfile_enabled", bool(checked))
        try:
            self.chk_enable_sidecar.toggled.connect(self._set_perfile_enabled)
            self._set_perfile_enabled(False)
        except Exception:
            logger.debug("Failed to connect chk_enable_sidecar toggled signal", exc_info=True)

        # Registry 映射管理区（列表 + 注册/删除）
        self.grp_registry_list = QGroupBox("Registry 映射管理 (可选)")
        self.grp_registry_list.setVisible(False)
        reg_layout = QVBoxLayout()
        from PySide6.QtWidgets import QListWidget
        self.lst_registry = QListWidget()
        self.lst_registry.setSelectionMode(QListWidget.SingleSelection)
        self.lst_registry.setMinimumHeight(100)

        reg_form = QHBoxLayout()
        self.inp_registry_pattern = QLineEdit()
        self.inp_registry_pattern.setPlaceholderText("Pattern，例如: sample.csv 或 *.csv")
        self.inp_registry_format = QLineEdit()
        self.inp_registry_format.setPlaceholderText("Format 文件路径 (JSON)")
        btn_browse_format = QPushButton("浏览格式文件")
        btn_browse_format.setMaximumWidth(90)
        try:
            btn_browse_format.setObjectName('smallButton')
            btn_browse_format.setToolTip('浏览并选择 JSON 格式文件')
        except Exception:
            pass
        btn_browse_format.clicked.connect(self._browse_registry_format)
        btn_preview_format = QPushButton("预览格式")
        btn_preview_format.setMaximumWidth(90)
        try:
            btn_preview_format.setObjectName('smallButton')
            btn_preview_format.setToolTip('展示所选格式的关键信息')
        except Exception:
            pass
        btn_preview_format.clicked.connect(self._on_preview_format)
        reg_form.addWidget(self.inp_registry_pattern)
        reg_form.addWidget(self.inp_registry_format)
        reg_form.addWidget(btn_browse_format)
        reg_form.addWidget(btn_preview_format)

        ops_row = QHBoxLayout()
        self.btn_registry_register = QPushButton("注册映射")
        self.btn_registry_edit = QPushButton("编辑选中")
        self.btn_registry_remove = QPushButton("删除选中")
        try:
            self.btn_registry_register.setObjectName('primaryButton')
            self.btn_registry_register.setToolTip('将当前 pattern -> format 条目注册到 registry（可选）')
            self.btn_registry_edit.setObjectName('secondaryButton')
            self.btn_registry_edit.setToolTip('编辑选中的 registry 映射')
            self.btn_registry_remove.setObjectName('dangerButton')
            self.btn_registry_remove.setToolTip('从 registry 中删除选中项（不可逆）')
        except Exception:
            pass
        self.btn_registry_register.clicked.connect(self._on_registry_register)
        self.btn_registry_edit.clicked.connect(self._on_registry_edit)
        self.btn_registry_remove.clicked.connect(self._on_registry_remove)
        ops_row.addWidget(self.btn_registry_register)
        ops_row.addWidget(self.btn_registry_edit)
        ops_row.addWidget(self.btn_registry_remove)

        reg_layout.addWidget(self.lst_registry)
        reg_layout.addLayout(reg_form)
        reg_layout.addLayout(ops_row)
        self.grp_registry_list.setLayout(reg_layout)
        try:
            self.grp_registry_list.setEnabled(False)
        except Exception:
            pass

        # 将文件表单行添加到会话级文件_form
        self.file_form.addRow("输入路径:", input_row)
        self.file_form.addRow("", pattern_row)

        # 文件列表（可复选、可滚动）
        self.grp_file_list = QGroupBox("找到的文件列表")
        self.grp_file_list.setVisible(False)
        file_list_layout = QVBoxLayout()
        self.file_scroll = QScrollArea()
        self.file_scroll.setWidgetResizable(True)
        self.file_list_widget = QWidget()
        self.file_list_layout_inner = QVBoxLayout(self.file_list_widget)
        try:
            self.file_list_layout_inner.setAlignment(Qt.AlignTop)
        except Exception:
            logger.debug("Error while setting file list layout alignment", exc_info=True)
        self.file_list_layout_inner.setContentsMargins(4, 4, 4, 4)
        self.file_scroll.setWidget(self.file_list_widget)
        # 初始最小高度较小，实际高度会根据文件数量在 _scan_and_populate_files 中调整
        self.file_scroll.setMinimumHeight(60)
        file_list_layout.addWidget(self.file_scroll)
        self.grp_file_list.setLayout(file_list_layout)

        # 存储文件复选框相关信息的元组列表
        self._file_check_items: List[Tuple[QCheckBox, Path, Optional[QLabel]]] = []

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

        # 执行/取消等按钮与日志
        self.btn_batch = QPushButton("开始批量处理")
        try:
            self.btn_batch.setObjectName('primaryButton')
            self.btn_batch.setShortcut('Ctrl+R')
            self.btn_batch.setToolTip('开始批量处理。运行时会锁定配置控件。')
        except Exception:
            pass
        self.btn_batch.clicked.connect(self.run_batch_processing)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedHeight(34)
        try:
            self.btn_cancel.setObjectName('secondaryButton')
            self.btn_cancel.setToolTip('取消正在运行的批处理任务')
            self.btn_cancel.setShortcut('Ctrl+.')
        except Exception:
            pass
        self.btn_cancel.clicked.connect(self.request_cancel_batch)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(False)

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
        self.btn_grid.addWidget(self.btn_cancel, 1, 1)

        # 把文件表单、registry 列表、文件列表、进度条、按钮区加入 layout_batch（实例属性）
        self.layout_batch.addLayout(self.file_form)
        self.layout_batch.addWidget(self.grp_registry_list)
        self.layout_batch.addWidget(self.grp_file_list)
        self.layout_batch.addWidget(self.progress_bar)
        self.layout_batch.addWidget(self.btn_widget)

        # 实验性功能组
        self.grp_experimental = QGroupBox("实验性功能（实验）")
        try:
            self.grp_experimental.setCheckable(True)
            self.grp_experimental.setChecked(False)
            self.grp_experimental.setToolTip("实验性功能：包含 3D 可视化与 per-file 覆盖，默认收起，谨慎使用。")
            self.grp_experimental.toggled.connect(lambda v: self.grp_experimental.setVisible(v))
            # 原先与主界面的复选框联动的逻辑已移至独立对话框
            self.grp_experimental.setVisible(False)
        except Exception:
            pass
        exp_layout = QVBoxLayout()

        self.btn_visualize = QPushButton("3D可视化")
        self.btn_visualize.setMaximumWidth(120)
        try:
            self.btn_visualize.setObjectName('smallButton')
            self.btn_visualize.setToolTip("打开3D坐标系可视化窗口（实验）")
        except Exception:
            pass
        self.btn_visualize.clicked.connect(self.toggle_visualization)
        exp_layout.addWidget(self.btn_visualize)
        exp_layout.addLayout(registry_row)
        self.grp_experimental.setLayout(exp_layout)
        self.layout_batch.addWidget(self.grp_experimental)

        self.layout_batch.addWidget(QLabel("处理日志:"))
        self.layout_batch.addWidget(self.txt_batch_log)

        # 设置伸缩：日志拉伸，文件列表不拉伸
        try:
            idx_file_list = self.layout_batch.indexOf(self.grp_file_list)
            if idx_file_list >= 0:
                self.layout_batch.setStretch(idx_file_list, 0)
            idx_log = self.layout_batch.indexOf(self.txt_batch_log)
            if idx_log >= 0:
                self.layout_batch.setStretch(idx_log, 1)
        except Exception:
            logger.debug("layout_batch.setStretch failed (non-fatal)", exc_info=True)

        # 将布局应用到 grp_batch
        self.grp_batch.setLayout(self.layout_batch)

        # 配置预览
        self.grp_config_preview = QGroupBox("数据格式预览")
        try:
            self.grp_config_preview.setMaximumHeight(140)
            self.grp_config_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass
        pv_layout = QVBoxLayout()
        self.lbl_preview_skip = QLabel("跳过行: -")
        self.lbl_preview_columns = QLabel("列映射: -")
        self.lbl_preview_passthrough = QLabel("保留列: -")
        for w in (self.lbl_preview_skip, self.lbl_preview_columns, self.lbl_preview_passthrough):
            try:
                w.setObjectName('previewText')
            except Exception:
                pass
            pv_layout.addWidget(w)
        self.grp_config_preview.setLayout(pv_layout)

        # 最近项目与快捷操作
        recent_group = QGroupBox("最近项目 & 快捷操作")
        recent_layout = QVBoxLayout()
        from PySide6.QtWidgets import QListWidget
        self.lst_recent = QListWidget()
        self.lst_recent.setMaximumHeight(120)
        self.lst_recent.itemActivated.connect(lambda it: self.inp_batch_input.setText(it.text()))
        recent_layout.addWidget(QLabel("最近打开的配置/项目（双击以填充输入路径）:"))
        recent_layout.addWidget(self.lst_recent)

        out_row = QHBoxLayout()
        self.inp_default_output = QLineEdit()
        self.inp_default_output.setPlaceholderText("默认输出目录，可选")
        btn_browse_default_out = QPushButton("浏览")
        btn_browse_default_out.clicked.connect(lambda: self._browse_default_output())
        out_row.addWidget(self.inp_default_output)
        out_row.addWidget(btn_browse_default_out)
        recent_layout.addLayout(out_row)

        self.btn_quick = QPushButton("一键处理")
        try:
            self.btn_quick.setObjectName('primaryButton')
            self.btn_quick.setShortcut('Ctrl+Shift+R')
        except Exception:
            pass
        self.btn_quick.setToolTip("使用当前配置与默认输出目录快速开始批处理")
        self.btn_quick.clicked.connect(self.one_click_process)
        recent_layout.addWidget(self.btn_quick)
        recent_group.setLayout(recent_layout)

        layout.addWidget(self.status_group)
        layout.addWidget(self.grp_config_preview)
        try:
            if hasattr(self, 'grp_experimental') and self.grp_experimental is not None:
                exp_layout.addWidget(recent_group)
            else:
                layout.addWidget(recent_group)
        except Exception:
            layout.addWidget(recent_group)
        layout.addWidget(self.grp_batch)

        try:
            idx_status = layout.indexOf(self.status_group)
            if idx_status >= 0:
                layout.setStretch(idx_status, 0)
            idx_batch = layout.indexOf(self.grp_batch)
            if idx_batch >= 0:
                layout.setStretch(idx_batch, 1)
        except Exception:
            try:
                layout.setStretch(0, 0)
                layout.setStretch(1, 1)
            except Exception:
                pass

        layout.addStretch()

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

    def toggle_visualization(self):
        """切换3D可视化窗口 - 委托给 VisualizationManager"""
        try:
            self.visualization_manager.toggle_visualization()
        except AttributeError:
            logger.warning("VisualizationManager 未初始化")
        except Exception as e:
            logger.error(f"切换可视化窗口失败: {e}")

    def open_experimental_dialog(self):
        """打开实验性功能对话框，用户确认后保存设置到 self.experimental_settings 并同步相关控件"""
        try:
            init = getattr(self, 'experimental_settings', None) or {}
            dlg = ExperimentalDialog(self, initial_settings=init)
            if dlg.exec() == QDialog.Accepted:
                s = dlg.get_settings()
                # 保存到实例属性以便其它逻辑读取
                self.experimental_settings = s
                # 将设置同步到界面上（若相应控件存在）
                try:
                    if hasattr(self, 'inp_registry_db'):
                        self.inp_registry_db.setText(s.get('registry_db', '') or '')
                except Exception:
                    pass
                try:
                    if hasattr(self, 'chk_enable_sidecar'):
                        self.chk_enable_sidecar.setChecked(bool(s.get('enable_sidecar', False)))
                        # 保持内部标志同步
                        try:
                            self._set_perfile_enabled(bool(s.get('enable_sidecar', False)))
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    # 刷新 registry 显示与文件来源标签
                    if hasattr(self, '_refresh_registry_list'):
                        self._refresh_registry_list()
                    if hasattr(self, '_refresh_format_labels'):
                        self._refresh_format_labels()
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.warning(self, '错误', f'打开实验性对话框失败: {e}')

    def show_visualization(self):
        """显示3D可视化窗口 - 委托给 VisualizationManager"""
        try:
            self.visualization_manager.show_visualization()
        except AttributeError:
            logger.warning("VisualizationManager 未初始化")
        except Exception as e:
            logger.error(f"显示可视化窗口失败: {e}")

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
        except AttributeError:
            # 如果管理器未初始化，记录警告
            logger.warning("ConfigManager 未初始化，无法应用配置")
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

    def browse_registry_db(self):
        """选择 format registry 数据库文件（可选）"""
        fname, _ = QFileDialog.getOpenFileName(self, '选择 format registry 数据库', '.', 'SQLite DB Files (*.sqlite *.db);;All Files (*)')
        if fname:
            try:
                self.inp_registry_db.setText(fname)
                self.txt_batch_log.append(f"已选择 registry: {fname}")
                # 选择后刷新已有文件的来源标签
                try:
                    self._refresh_format_labels()
                except Exception:
                    pass
                # 刷新 registry 映射显示
                try:
                    self._refresh_registry_list()
                except Exception:
                    pass
            except Exception:
                pass

    def _browse_registry_format(self):
        """选择一个 format JSON 文件以便注册映射时使用"""
        fname, _ = QFileDialog.getOpenFileName(self, '选择 format JSON', '.', 'JSON Files (*.json);;All Files (*)')
        if fname:
            try:
                self.inp_registry_format.setText(fname)
            except Exception:
                pass

    def _on_load_data_format_file(self):
        """从 JSON 文件加载数据格式并更新预览与当前 data_config。"""
        try:
            fname, _ = QFileDialog.getOpenFileName(self, '加载数据格式', '.', 'JSON Files (*.json);;All Files (*)')
            if not fname:
                return
            with open(fname, 'r', encoding='utf-8') as fh:
                cfg = json.load(fh)
            # 简单验证 cfg 是 dict
            if not isinstance(cfg, dict):
                QMessageBox.warning(self, '错误', '格式文件内容不是有效的 JSON 对象')
                return
            self.data_config = cfg
            try:
                self.update_config_preview()
            except Exception:
                logger.debug('update_config_preview failed after loading format', exc_info=True)
            self.txt_batch_log.append(f'已加载数据格式: {fname}')
            QMessageBox.information(self, '已加载', f'数据格式已加载: {fname}')
        except Exception as e:
            QMessageBox.warning(self, '加载失败', f'无法加载格式文件: {e}')

    def _on_registry_register(self):
        dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
        if not dbp:
            QMessageBox.warning(self, '错误', '请先选择 registry 数据库文件')
            return
        pat = self.inp_registry_pattern.text().strip()
        fmt = self.inp_registry_format.text().strip()
        if not pat or not fmt:
            QMessageBox.warning(self, '错误', '请填写 pattern 与 format 文件路径')
            return
        # 校验 format 文件是否存在且为合法 JSON
        try:
            fpath = Path(fmt)
            if not fpath.exists():
                QMessageBox.warning(self, '错误', f'格式文件不存在: {fmt}')
                return
            # 尝试解析 JSON
            with open(fpath, 'r', encoding='utf-8') as _fh:
                try:
                    json.load(_fh)
                except Exception as e:
                    QMessageBox.warning(self, '错误', f'格式文件不是有效的 JSON: {e}')
                    return
        except Exception:
            QMessageBox.warning(self, '错误', '无法访问或验证格式文件')
            return

        # 确认注册
        resp = QMessageBox.question(self, '确认', f'确定要注册映射吗？\n{pat} -> {fmt}', QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return

        # 如果处于编辑模式（存在 _editing_mapping_id），则执行 update
        if hasattr(self, '_editing_mapping_id') and self._editing_mapping_id is not None:
            try:
                update_mapping(dbp, self._editing_mapping_id, pat, fmt)
                self.txt_batch_log.append(f"已更新映射 id={self._editing_mapping_id}: {pat} -> {fmt}")
                # 清除编辑标识
                self._editing_mapping_id = None
                self._refresh_registry_list()
                return
            except Exception as e:
                QMessageBox.critical(self, '更新失败', str(e))
                return

        try:
            register_mapping(dbp, pat, fmt)
            self.txt_batch_log.append(f"已注册: {pat} -> {fmt}")
            self._refresh_registry_list()
        except Exception as e:
            QMessageBox.critical(self, '注册失败', str(e))

    def _on_registry_edit(self):
        """编辑选中映射：把选中项加载到输入框并在用户修改后更新。"""
        dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
        if not dbp:
            QMessageBox.warning(self, '错误', '请先选择 registry 数据库文件')
            return
        sel = self.lst_registry.selectedItems()
        if not sel:
            QMessageBox.warning(self, '错误', '请先选择要编辑的映射项')
            return
        text = sel[0].text()
        try:
            if text.startswith('['):
                end = text.find(']')
                mid = text[1:end]
                mapping_id = int(mid)
            else:
                raise ValueError('无法解析选中项 ID')
        except Exception as e:
            QMessageBox.critical(self, '错误', str(e))
            return

        # 把当前值填入输入框，允许用户修改并点击注册以提交（我们将把注册按钮作为新增/覆盖两用）
        # 也可以直接弹出编辑对话；这里采用填充方式并记录待编辑 id
        try:
            # 从 registry 读取当前映射详情
            mappings = list_mappings(dbp)
            entry = next((m for m in mappings if m['id'] == mapping_id), None)
            if not entry:
                QMessageBox.warning(self, '错误', f'映射 id={mapping_id} 未找到')
                return
            self.inp_registry_pattern.setText(entry['pattern'])
            self.inp_registry_format.setText(entry['format_path'])
            # 将编辑 id 存入属性以供后续保存
            self._editing_mapping_id = mapping_id
            QMessageBox.information(self, '编辑模式', f'已加载 id={mapping_id} 到输入框，修改后点击"注册映射"以保存')
        except Exception as e:
            QMessageBox.critical(self, '错误', str(e))

    def _on_registry_remove(self):
        dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
        if not dbp:
            QMessageBox.warning(self, '错误', '请先选择 registry 数据库文件')
            return
        sel = self.lst_registry.selectedItems()
        if not sel:
            QMessageBox.warning(self, '错误', '请先选择要删除的映射项')
            return
        # 解析选中项的 id（格式为 [id] ...）
        text = sel[0].text()
        try:
            if text.startswith('['):
                end = text.find(']')
                mid = text[1:end]
                mapping_id = int(mid)
            else:
                raise ValueError('无法解析选中项 ID')
            # 确认删除
            resp = QMessageBox.question(self, '确认删除', f'确认要删除映射 id={mapping_id} ?', QMessageBox.Yes | QMessageBox.No)
            if resp != QMessageBox.Yes:
                return
            delete_mapping(dbp, mapping_id)
            self.txt_batch_log.append(f"已删除映射 id={mapping_id}")
            self._refresh_registry_list()
        except Exception as e:
            QMessageBox.critical(self, '删除失败', str(e))

    def _on_preview_format(self):
        """显示当前输入格式文件的 JSON 摘要（前几行或 keys）。"""
        fmt = self.inp_registry_format.text().strip()
        if not fmt:
            QMessageBox.warning(self, '预览', '请先填写或选择格式文件路径')
            return
        try:
            p = Path(fmt)
            if not p.exists():
                QMessageBox.warning(self, '预览', f'格式文件不存在: {fmt}')
                return
            with open(p, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            # 构建简短摘要
            if isinstance(data, dict):
                keys = list(data.keys())[:10]
                preview = json.dumps({k: data[k] for k in keys}, indent=2, ensure_ascii=False)
            else:
                preview = json.dumps(data, indent=2, ensure_ascii=False)
            dlg = QDialog(self)
            dlg.setWindowTitle('格式文件预览')
            v = QVBoxLayout(dlg)
            te = QTextEdit()
            te.setReadOnly(True)
            te.setPlainText(preview)
            v.addWidget(te)
            btn = QDialogButtonBox(QDialogButtonBox.Ok)
            btn.accepted.connect(dlg.accept)
            v.addWidget(btn)
            dlg.resize(600, 400)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, '预览失败', str(e))

    def _scan_and_populate_files(self, chosen_path):
        """扫描所选路径并在滚动区域中生成复选框列表（默认全选）。"""
        p = Path(chosen_path)
        files = []
        if p.is_file():
            files = [p]

            self.output_dir = p.parent
        elif p.is_dir():
            pattern = self.inp_pattern.text() if hasattr(self, 'inp_pattern') else "*.csv"
            for file_path in p.rglob('*'):
                if file_path.is_file() and fnmatch.fnmatch(file_path.name, pattern):
                    files.append(file_path)
            self.output_dir = p
        # 清空旧的复选框
        # 清空旧的复选框及标签
        for i in reversed(range(self.file_list_layout_inner.count())):
            item = self.file_list_layout_inner.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w:
                w.setParent(None)
        self._file_check_items = []

        if not files:
            self.grp_file_list.setVisible(False)
            return

        # 创建复选框
        # 创建复选框并显示格式来源标签
        for fp in files:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox(fp.name)
            cb.setChecked(True)
            src_label = QLabel("")
            try:
                src_label.setObjectName('fileSrcLabel')
                src_label.setProperty('variant', 'muted')
            except Exception:
                pass
            # 解析并设置来源（同步快速判断）
            try:
                src, src_path = self._determine_format_source(fp)
                disp, tip, color = self._format_label_from(src, src_path)
                src_label.setText(disp)
                src_label.setToolTip(tip or "")
                # 映射返回的颜色到样式属性，样式表中根据 variant 设置颜色
                try:
                    if color == '#dc3545':
                        src_label.setProperty('variant', 'error')
                    elif color == '#6c757d':
                        src_label.setProperty('variant', 'muted')
                    else:
                        src_label.setProperty('variant', 'normal')
                except Exception:
                    pass
            except Exception:
                src_label.setText("未知")
                try:
                    src_label.setProperty('variant', 'error')
                except Exception:
                    pass

            row_layout.addWidget(cb)
            # 保持标签靠近复选框，并限制标签宽度，避免在窄窗口下被推到最右侧
            row_layout.addSpacing(8)
            src_label.setFixedWidth(300)
            src_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(src_label)
            self.file_list_layout_inner.addWidget(row)
            # 存储三元组 (checkbox, Path, label) 以便后续使用或更新
            self._file_check_items.append((cb, fp, src_label))

        # 根据文件数量自适应高度：当文件少时收缩至合适高度，当文件多时限制最大高度并显示滚动条
        try:
            row_count = len(files)
            row_height = 28  # 近似每行高度（像素）
            padding = 36     # 标题/内边距等额外高度
            min_h = 80
            max_h = 420
            desired = min(max_h, max(min_h, row_count * row_height + padding))
            # 设置为固定高度以便在弹性布局中不会无限拉伸
            self.file_scroll.setFixedHeight(int(desired))
        except Exception:
            # 发生异常时回退到默认显示高度
            try:
                self.file_scroll.setMinimumHeight(180)
            except Exception:
                pass

        # 显示并自动滚动到顶部
        self.grp_file_list.setVisible(True)
        self.file_scroll.verticalScrollBar().setValue(0)

    def _on_pattern_changed(self):
        """当匹配模式改变时，基于当前输入路径重新扫描并刷新文件列表。"""
        try:
            path_text = self.inp_batch_input.text().strip() if hasattr(self, 'inp_batch_input') else ''
            if not path_text:
                return
            chosen = Path(path_text)
            if chosen.exists():
                self._scan_and_populate_files(chosen)
        except Exception:
            logger.debug("_on_pattern_changed 处理失败", exc_info=True)

    def _determine_format_source(self, fp: Path):
        """快速判断单个文件的格式来源，返回 (label, path_or_None)。

        label: 'registry' | 'sidecar' | 'dir' | 'global' | 'unknown'
        path_or_None: 指向具体的 format 文件（Path）或 None
        注意：当界面上的 per-file 覆盖开关未启用时（默认），函数将直接返回 'global'，避免在 UI 上暴露侧车/registry 信息。
        """
        try:
            # 若 per-file 覆盖未显式启用，则统一视作全局（不检查 registry/sidecar）
            try:
                # 优先使用 experimental_settings（若用户通过对话框设置了实验项）
                if hasattr(self, 'experimental_settings'):
                    if not bool(self.experimental_settings.get('enable_sidecar', False)):
                        return ("global", None)
                else:
                    # 兼容旧控件（已被移入对话框）：若存在且未选中则视为关闭
                    if hasattr(self, 'chk_enable_sidecar') and not self.chk_enable_sidecar.isChecked():
                        return ("global", None)
            except Exception:
                pass

            # 1) registry 优先（若界面提供了 db 路径）
            if hasattr(self, 'inp_registry_db'):
                dbp = self.inp_registry_db.text().strip()
                if dbp:
                    try:
                        fmt = get_format_for_file(dbp, str(fp))
                        if fmt:
                            return ("registry", Path(fmt))
                    except Exception:
                        # registry 查询不应阻塞 UI，降级处理
                        pass

            # 2) file-sidecar
            for suf in ('.format.json', '.json'):
                cand = fp.parent / f"{fp.stem}{suf}"
                if cand.exists():
                    return ("sidecar", cand)

            # 3) 目录级默认
            dir_cand = fp.parent / 'format.json'
            if dir_cand.exists():
                return ("dir", dir_cand)

            # 4) 全局
            return ("global", None)
        except Exception:
            return ("unknown", None)

    def _format_label_from(self, src: str, src_path: Optional[Path]):
        """将源类型与路径格式化为显示文本、tooltip 与颜色。

        返回 (display_text, tooltip_text_or_empty, css_color)
        """
        try:
            if src == 'registry':
                name = Path(src_path).name if src_path else ''
                return (f"registry ({name})" if name else "registry", str(src_path) if src_path else "", '#1f77b4')
            if src == 'sidecar':
                name = Path(src_path).name if src_path else ''
                return (f"sidecar ({name})" if name else "sidecar", str(src_path) if src_path else "", '#28a745')
            if src == 'dir':
                name = Path(src_path).name if src_path else ''
                return (f"dir ({name})" if name else "dir", str(src_path) if src_path else "", '#ff8c00')
            if src == 'global':
                return ("global", "", '#6c757d')
            return ("unknown", "", '#dc3545')
        except Exception as e:
            logger.debug("_format_label_from encountered error", exc_info=True)
            return ("unknown", "", '#dc3545')

    def _refresh_format_labels(self):
        """遍历当前文件列表，重新解析并更新每个文件旁的来源标签及 tooltip。"""
        try:
            items = getattr(self, '_file_check_items', None)
            if not items:
                return
            for tup in items:
                # 支持旧的 (cb, fp) 形式或新的 (cb, fp, label)
                if len(tup) == 2:
                    # 旧结构 (cb, fp) 无标签，跳过
                    continue
                cb, fp, lbl = tup
                try:
                    src, src_path = self._determine_format_source(fp)
                    disp, tip, color = self._format_label_from(src, src_path)
                    lbl.setText(disp)
                    lbl.setToolTip(tip or "")
                    try:
                        if color == '#dc3545':
                            lbl.setProperty('variant', 'error')
                        elif color == '#6c757d':
                            lbl.setProperty('variant', 'muted')
                        else:
                            lbl.setProperty('variant', 'normal')
                    except Exception:
                        pass
                except Exception as e:
                    logger.debug("Failed to set label text from format source", exc_info=True)
                    try:
                        lbl.setText('未知')
                        lbl.setToolTip("")
                        try:
                            lbl.setProperty('variant', 'error')
                        except Exception:
                            pass
                    except Exception:
                        logger.debug("Failed to set fallback 'unknown' label", exc_info=True)
        except Exception as e:
            logger.debug("_refresh_format_labels failed", exc_info=True)


    def _refresh_registry_list(self):
        """将当前 registry 的映射列表渲染到 `self.lst_registry`。"""
        try:
            dbp = ''
            if hasattr(self, 'inp_registry_db'):
                dbp = self.inp_registry_db.text().strip()
            if not dbp:
                self.grp_registry_list.setVisible(False)
                return
            try:
                mappings = list_mappings(dbp)
            except Exception as e:
                self.lst_registry.clear()
                self.lst_registry.addItem(f"无法读取 registry: {e}")
                self.grp_registry_list.setVisible(True)
                return

            self.lst_registry.clear()
            if not mappings:
                self.lst_registry.addItem("(空)")
            else:
                for m in mappings:
                    text = f"[{m['id']}] {m['pattern']} -> {m['format_path']}  (added: {m['added_at']})"
                    self.lst_registry.addItem(text)

            self.grp_registry_list.setVisible(True)
        except Exception as e:
            logger.debug("_refresh_registry_list encountered error", exc_info=True)
            try:
                self.grp_registry_list.setVisible(False)
            except Exception:
                logger.debug("Failed to hide grp_registry_list after error", exc_info=True)

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
        try:
            QTimer.singleShot(50, self.update_button_layout)
            QTimer.singleShot(120, self._force_layout_refresh)
        except Exception:
            logger.debug("showEvent scheduling failed", exc_info=True)
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

    def add_recent_project(self, path_str: str):
        """将最近打开的配置/项目加入列表（去重，保持最新在上）。"""
        try:
            if not hasattr(self, 'recent_projects'):
                self.recent_projects = []
            p = str(path_str)
            if p in self.recent_projects:
                self.recent_projects.remove(p)
            self.recent_projects.insert(0, p)
            # 限制数量
            self.recent_projects = self.recent_projects[:10]
            # 更新 UI 列表
            try:
                self.lst_recent.clear()
                for rp in self.recent_projects:
                    self.lst_recent.addItem(rp)
            except Exception:
                logger.debug("Failed to update lst_recent", exc_info=True)
        except Exception:
            logger.debug("add_recent_project failed", exc_info=True)

    def _browse_default_output(self):
        try:
            d = QFileDialog.getExistingDirectory(self, '选择默认输出目录', '.')
            if d:
                self.inp_default_output.setText(d)
        except Exception:
            logger.debug("_browse_default_output failed", exc_info=True)

    def _toggle_experimental_visibility(self):
        """显示或隐藏实验性组，并刷新布局。"""
        try:
            visible = bool(self.chk_show_experimental.isChecked())
            if hasattr(self, 'grp_experimental'):
                self.grp_experimental.setVisible(visible)
            try:
                self._refresh_layouts()
            except Exception:
                logger.debug("_refresh_layouts failed after toggling experimental", exc_info=True)
        except Exception:
            logger.debug("_toggle_experimental_visibility failed", exc_info=True)

    def _on_target_part_changed(self):
        """当用户在下拉框选择不同 Part 时 - 委托给 PartManager"""
        try:
            self.part_manager.on_target_part_changed()
        except AttributeError:
            logger.debug("PartManager 未初始化")
        except Exception as e:
            logger.debug(f"Target Part 切换失败: {e}")

    def _add_source_part(self):
        """在原始项目或内存结构中添加一个新的 Source Part - 委托给 PartManager"""
        try:
            self.part_manager.add_source_part()
        except AttributeError:
            logger.warning("PartManager 未初始化")
        except Exception as e:
            logger.error(f"添加 Source Part 失败: {e}")
            parts = self._raw_project_dict.setdefault('Source', {}).setdefault('Parts', [])
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
                                    'Cref': float(self.src_cref.text()) if hasattr(self, 'src_cref') else 1.0,
                                    'Bref': float(self.src_bref.text()) if hasattr(self, 'src_bref') else 1.0,
                                    'Q': float(self.src_q.text()) if hasattr(self, 'src_q') else 1000.0,
                                    'S': float(self.src_sref.text()) if hasattr(self, 'src_sref') else 10.0
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
                        'Cref': float(self.src_cref.text()) if hasattr(self, 'src_cref') else 1.0,
                        'Bref': float(self.src_bref.text()) if hasattr(self, 'src_bref') else 1.0,
                        'Q': float(self.src_q.text()) if hasattr(self, 'src_q') else 1000.0,
                        'S': float(self.src_sref.text()) if hasattr(self, 'src_sref') else 10.0
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
                pass
        except Exception:
            logger.debug("_add_source_part failed", exc_info=True)

    def _remove_source_part(self):
        """从原始项目或内存结构中移除当前选中的 Source Part - 委托给 PartManager"""
        try:
            self.part_manager.remove_source_part()
        except AttributeError:
            logger.warning("PartManager 未初始化")
        except Exception as e:
            logger.error(f"删除 Source Part 失败: {e}")

    def _add_target_part(self):
        """添加新 Target Part - 委托给 PartManager"""
        try:
            self.part_manager.add_target_part()
        except AttributeError:
            logger.warning("PartManager 未初始化")
        except Exception as e:
            logger.error(f"添加 Target Part 失败: {e}")

    def _remove_target_part(self):
        """删除当前 Target Part - 委托给 PartManager"""
        try:
            self.part_manager.remove_target_part()
        except AttributeError:
            logger.warning("PartManager 未初始化")
        except Exception as e:
            logger.error(f"删除 Target Part 失败: {e}")
        except Exception:
            logger.debug("_remove_target_part failed", exc_info=True)

    def _on_source_part_changed(self):
        """当用户在 Source 下拉选择不同 Part 时 - 委托给 PartManager"""
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
            new_text = (new_text or '').strip()
            old = getattr(self, '_current_source_part_name', None)
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
                if getattr(self, '_raw_project_dict', None) and isinstance(self._raw_project_dict, dict):
                    parts = self._raw_project_dict.get('Source', {}).get('Parts', [])
                    for p in parts:
                        if p.get('PartName') == old_name:
                            p['PartName'] = new_text
                            # 也更新第一个 Variant 的 PartName 若存在
                            vars = p.get('Variants') or []
                            if vars and isinstance(vars, list) and 'PartName' in vars[0]:
                                vars[0]['PartName'] = new_text
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
            new_text = (new_text or '').strip()
            old = getattr(self, '_current_target_part_name', None)
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

    def one_click_process(self):
        """使用当前配置和默认输出目录快速启动批处理（单次、非交互）。"""
        try:
            # 初始化基本前置条件
            if not hasattr(self, 'calculator') or self.calculator is None:
                QMessageBox.warning(self, "错误", "尚未应用配置，请先点击“应用配置”。")
                return
            inp = self.inp_batch_input.text().strip()
            if not inp:
                # 若最近项目可用，则使用第一个
                if hasattr(self, 'recent_projects') and self.recent_projects:
                    inp = self.recent_projects[0]
                    self.inp_batch_input.setText(inp)
                else:
                    QMessageBox.warning(self, "错误", "请先选择输入文件或目录（或在最近项目中选择一项）。")
                    return

            output_dir = self.inp_default_output.text().strip() or None
            if output_dir:
                self.output_dir = Path(output_dir)
            else:
                self.output_dir = None

            # 将输入路径设置到控件并调用 run_batch_processing
            self.inp_batch_input.setText(inp)
            # 如果指定了默认输出目录，设置为实例属性，run_batch_processing 会优先使用它
            try:
                self.run_batch_processing()
            except Exception as e:
                logger.exception("one_click_process failed: %s", e)
        except Exception:
            logger.debug("one_click_process failed", exc_info=True)

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


def main():
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
