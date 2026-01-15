"""
配置编辑器面板 - 汇总 Source/Target 坐标配置与加载/保存/应用按钮。
"""

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .source_panel import SourcePanel
from .target_panel import TargetPanel

logger = logging.getLogger(__name__)


class ConfigPanel(QWidget):
    """配置编辑器面板，封装 Source/Target 面板与配置按钮。"""

    loadRequested = Signal()
    saveRequested = Signal()
    # 已移除：applyRequested 信号与“应用配置”按钮，
    # 因为配置现在直接保存为 ProjectConfigModel 并在需要时由批处理按文件创建计算器。

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(950)
        self.setMaximumHeight(550)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        title = QLabel("配置编辑器")
        try:
            title.setObjectName("panelTitle")
        except Exception:
            pass
        main_layout.addWidget(title)

        # 面板组件
        self.source_panel = SourcePanel(self)
        self.target_panel = TargetPanel(self)

        # 配置操作按钮
        btn_widget = QWidget(self)
        btn_widget.setFixedWidth(120)
        btn_layout = QVBoxLayout(btn_widget)
        btn_layout.setSpacing(8)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        # “加载配置”入口已统一移动到文件列表右上角：避免用户在配置编辑器内重复入口。
        # 为保持向后兼容，这里保留 loadRequested 信号，但不再展示加载按钮。
        self.btn_load = None

        self.btn_save = QPushButton("保存配置", btn_widget)
        self.btn_save.setFixedHeight(40)
        try:
            self.btn_save.setObjectName("primaryButton")
            self.btn_save.setToolTip("将当前配置保存到磁盘 (Ctrl+S)")
            self.btn_save.setShortcut("Ctrl+S")
        except Exception:
            pass
        self.btn_save.clicked.connect(self.saveRequested.emit)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addStretch()

        # 横向布局
        coord_layout = QHBoxLayout()
        coord_layout.setSpacing(8)
        coord_layout.addWidget(self.source_panel)
        coord_layout.addWidget(self.target_panel)
        coord_layout.addWidget(btn_widget)
        coord_layout.setStretch(0, 1)
        coord_layout.setStretch(1, 1)
        coord_layout.setStretch(2, 0)

        main_layout.addLayout(coord_layout)
        main_layout.addStretch()
