"""
配置编辑器面板 - 汇总 Source/Target 坐标配置与加载/保存/应用按钮。
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

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
        # 不设置固定的最小宽度，让侧边栏容器决定大小
        self.setMinimumWidth(100)
        # 移除最大高度限制，允许滚动
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

        # 防止在侧边栏宽度较小时被强行压缩导致控件挤压/错位。
        # 外层 QScrollArea 会自动提供水平滚动条。
        self.source_panel.setMinimumWidth(360)
        self.target_panel.setMinimumWidth(360)

        # 配置操作按钮
        btn_widget = QWidget(self)
        btn_widget.setFixedHeight(50)
        btn_layout = QHBoxLayout(btn_widget)
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

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addStretch()

        # 创建滚动区域容纳横向布局的面板
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 滚动内容容器
        scroll_content = QWidget()
        coord_layout = QHBoxLayout(scroll_content)
        coord_layout.setSpacing(4)
        coord_layout.setContentsMargins(0, 0, 0, 0)
        coord_layout.addWidget(self.source_panel)
        coord_layout.addWidget(self.target_panel)
        coord_layout.setStretch(0, 1)
        coord_layout.setStretch(1, 1)

        scroll_area.setWidget(scroll_content)

        main_layout.addWidget(scroll_area)
        main_layout.addWidget(btn_widget)
