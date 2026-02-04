"""
Part 选择器面板 - 集中管理 Source 和 Target Part 的选择
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

logger = logging.getLogger(__name__)


class PartSelectorPanel(QGroupBox):
    """集中管理 Source 和 Target Part 选择的面板"""

    # 信号定义
    sourcePartSelected = Signal(str)  # Source Part 选择变化
    targetPartSelected = Signal(str)  # Target Part 选择变化
    partAddRequested = Signal(str, str)  # (side, suggested_name) 添加 Part 请求
    partRemoveRequested = Signal(str, str)  # (side, part_name) 移除 Part 请求

    def __init__(self, parent=None):
        """初始化 Part 选择器面板"""
        super().__init__("Part 选择器", parent)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 获取 SignalBus
        try:
            from gui.signal_bus import SignalBus

            self.signal_bus = SignalBus.instance()
            self.signal_bus.partAdded.connect(self._on_part_added)
            self.signal_bus.partRemoved.connect(self._on_part_removed)
        except Exception:
            logger.debug("SignalBus 初始化失败，Part 更新将不可用", exc_info=True)
            self.signal_bus = None

        self._init_ui()

    def _init_ui(self):
        """初始化UI布局"""
        # 创建表单布局
        form_layout = QFormLayout()
        form_layout.setContentsMargins(8, 8, 8, 8)
        form_layout.setSpacing(6)
        form_layout.setHorizontalSpacing(8)
        form_layout.setVerticalSpacing(8)
        try:
            form_layout.setLabelAlignment(Qt.AlignRight)
        except Exception:
            pass

        # Source Part 选择器
        (
            source_widget,
            self.source_selector,
            self.btn_add_source,
            self.btn_remove_source,
        ) = self._create_selector_widget("Source")

        lbl_source = QLabel("Source Part:")
        lbl_source.setFixedWidth(90)
        form_layout.addRow(lbl_source, source_widget)

        # Target Part 选择器
        (
            target_widget,
            self.target_selector,
            self.btn_add_target,
            self.btn_remove_target,
        ) = self._create_selector_widget("Target")

        lbl_target = QLabel("Target Part:")
        lbl_target.setFixedWidth(90)
        form_layout.addRow(lbl_target, target_widget)

        self.setLayout(form_layout)

        # 连接信号
        self._connect_signals()

    def _create_selector_widget(self, side: str):
        """创建单个选择器控件（包含下拉框和 +/- 按钮）
        返回: (widget, selector, btn_add, btn_remove)
        """
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # 下拉框
        selector = QComboBox()
        selector.setObjectName(f"{side.lower()}_selector")
        selector.setEditable(False)
        try:
            selector.setMaximumWidth(200)
            selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass
        layout.addWidget(selector)

        # + 按钮
        btn_add = QPushButton("+")
        btn_add.setObjectName(f"btn_add_{side.lower()}")
        btn_add.setMaximumWidth(28)
        try:
            btn_add.setObjectName("smallButton")
            btn_add.setToolTip(f"添加新的 {side} Part")
        except Exception:
            pass
        layout.addWidget(btn_add)

        # - 按钮
        btn_remove = QPushButton("−")
        btn_remove.setObjectName(f"btn_remove_{side.lower()}")
        btn_remove.setMaximumWidth(28)
        try:
            btn_remove.setObjectName("smallButton")
            btn_remove.setToolTip(f"移除当前 {side} Part")
        except Exception:
            pass
        layout.addWidget(btn_remove)

        try:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass

        return widget, selector, btn_add, btn_remove

    def _connect_signals(self):
        """连接内部信号"""
        # Source 信号
        self.source_selector.currentTextChanged.connect(
            lambda text: self.sourcePartSelected.emit(text)
        )
        self.btn_add_source.clicked.connect(
            lambda: self.partAddRequested.emit("Source", "")
        )
        self.btn_remove_source.clicked.connect(
            lambda: self.partRemoveRequested.emit(
                "Source", self.source_selector.currentText()
            )
        )

        # Target 信号
        self.target_selector.currentTextChanged.connect(
            lambda text: self.targetPartSelected.emit(text)
        )
        self.btn_add_target.clicked.connect(
            lambda: self.partAddRequested.emit("Target", "")
        )
        self.btn_remove_target.clicked.connect(
            lambda: self.partRemoveRequested.emit(
                "Target", self.target_selector.currentText()
            )
        )

        # 连接到 SignalBus（如果可用）
        try:
            if self.signal_bus:
                self.partAddRequested.connect(self.signal_bus.partAddRequested.emit)
                self.partRemoveRequested.connect(
                    self.signal_bus.partRemoveRequested.emit
                )
                logger.debug("Part 选择器面板已连接到 SignalBus")
        except Exception as e:
            logger.warning(
                "连接 Part 选择器面板到 SignalBus 失败: %s", e, exc_info=True
            )

    def _on_part_added(self, side: str, part_name: str):
        """响应 Part 添加事件"""
        try:
            if side == "Source":
                if self.source_selector.findText(part_name) == -1:
                    self.source_selector.addItem(part_name)
                self.source_selector.setCurrentText(part_name)
            elif side == "Target":
                if self.target_selector.findText(part_name) == -1:
                    self.target_selector.addItem(part_name)
                self.target_selector.setCurrentText(part_name)
            logger.debug("Part 选择器面板已添加 %s Part: %s", side, part_name)
        except Exception:
            logger.debug("处理 Part 添加事件失败", exc_info=True)

    def _on_part_removed(self, side: str, part_name: str):
        """响应 Part 移除事件"""
        try:
            if side == "Source":
                idx = self.source_selector.findText(part_name)
                if idx >= 0:
                    self.source_selector.removeItem(idx)
            elif side == "Target":
                idx = self.target_selector.findText(part_name)
                if idx >= 0:
                    self.target_selector.removeItem(idx)
            logger.debug("Part 选择器面板已移除 %s Part: %s", side, part_name)
        except Exception:
            logger.debug("处理 Part 移除事件失败", exc_info=True)

    def update_source_parts(self, part_names: list):
        """更新 Source Part 列表"""
        try:
            current = self.source_selector.currentText()
            self.source_selector.blockSignals(True)
            self.source_selector.clear()
            for name in part_names:
                self.source_selector.addItem(name)
            if current and current in part_names:
                self.source_selector.setCurrentText(current)
            elif part_names:
                self.source_selector.setCurrentIndex(0)
            self.source_selector.blockSignals(False)
            # 手动触发一次信号以同步状态
            if self.source_selector.currentText():
                self.sourcePartSelected.emit(self.source_selector.currentText())
        except Exception:
            logger.debug("更新 Source Part 列表失败", exc_info=True)

    def update_target_parts(self, part_names: list):
        """更新 Target Part 列表"""
        try:
            current = self.target_selector.currentText()
            self.target_selector.blockSignals(True)
            self.target_selector.clear()
            for name in part_names:
                self.target_selector.addItem(name)
            if current and current in part_names:
                self.target_selector.setCurrentText(current)
            elif part_names:
                self.target_selector.setCurrentIndex(0)
            self.target_selector.blockSignals(False)
            # 手动触发一次信号以同步状态
            if self.target_selector.currentText():
                self.targetPartSelected.emit(self.target_selector.currentText())
        except Exception:
            logger.debug("更新 Target Part 列表失败", exc_info=True)

    def get_source_part(self) -> str:
        """获取当前选中的 Source Part"""
        return self.source_selector.currentText()

    def get_target_part(self) -> str:
        """获取当前选中的 Target Part"""
        return self.target_selector.currentText()

    def set_source_part(self, part_name: str):
        """设置当前 Source Part"""
        try:
            idx = self.source_selector.findText(part_name)
            if idx >= 0:
                self.source_selector.setCurrentIndex(idx)
        except Exception:
            logger.debug("设置 Source Part 失败", exc_info=True)

    def set_target_part(self, part_name: str):
        """设置当前 Target Part"""
        try:
            idx = self.target_selector.findText(part_name)
            if idx >= 0:
                self.target_selector.setCurrentIndex(idx)
        except Exception:
            logger.debug("设置 Target Part 失败", exc_info=True)
