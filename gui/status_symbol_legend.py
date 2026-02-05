"""文件验证状态符号说明面板

提供清晰、直观的文件状态符号解释，帮助用户快速理解文件的验证状态。
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
)
from PySide6.QtGui import QFont, QColor

logger = logging.getLogger(__name__)

# 状态符号常数
STATUS_READY = "✓"
STATUS_WARNING = "⚠"
STATUS_UNVERIFIED = "❓"

# 状态信息定义
STATUS_INFO = {
    STATUS_READY: {
        "name": "已就绪",
        "color": "#4caf50",  # 绿色
        "description": "文件配置正常，可以进行批处理",
        "details": [
            "✓ 特殊格式文件：所有 parts 映射已完成",
            "✓ 普通格式文件：Source/Target 已选择",
        ],
    },
    STATUS_WARNING: {
        "name": "配置不完整",
        "color": "#ff9800",  # 橙色
        "description": "文件缺少必要配置，需要用户处理",
        "details": [
            "⚠ 缺少部件映射或 Source/Target 选择",
            "⚠ 所选配置在当前项目中不存在",
            "⚠ 数据格式不匹配配置",
        ],
    },
    STATUS_UNVERIFIED: {
        "name": "无法验证",
        "color": "#2196f3",  # 蓝色
        "description": "文件状态无法确定，需要检查日志",
        "details": [
            "❓ 验证过程出错",
            "❓ 数据加载失败",
            "❓ 系统无法确定文件是否可以处理",
        ],
    },
}


class StatusSymbolLegend(QWidget):
    """文件验证状态符号说明面板

    显示所有状态符号的含义和用法，帮助用户理解文件验证状态。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化状态符号说明面板

        Args:
            parent: 父部件
        """
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """初始化 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # 标题
        title = QLabel("📋 文件验证状态说明")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title.setFont(title_font)
        main_layout.addWidget(title)

        # 状态卡片容器
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
            """
        )

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(8)

        # 创建每个状态的卡片
        for symbol in [STATUS_READY, STATUS_WARNING, STATUS_UNVERIFIED]:
            card = self._create_status_card(symbol)
            scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.hide)
        button_layout.addWidget(close_btn)

        main_layout.addLayout(button_layout)

    def _create_status_card(self, symbol: str) -> QFrame:
        """创建状态符号卡片

        Args:
            symbol: 状态符号（✓ ⚠ ❓）

        Returns:
            QFrame: 状态卡片
        """
        info = STATUS_INFO.get(symbol, {})

        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                border-left: 4px solid {info.get('color', '#ccc')};
                background-color: #f5f5f5;
                border-radius: 4px;
                padding: 12px;
            }}
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 符号和名称
        header = QHBoxLayout()
        symbol_label = QLabel(symbol)
        symbol_font = QFont()
        symbol_font.setPointSize(16)
        symbol_label.setFont(symbol_font)
        symbol_label.setFixedWidth(30)

        name_label = QLabel(info.get("name", "未知"))
        name_font = QFont()
        name_font.setBold(True)
        name_font.setPointSize(10)
        name_label.setFont(name_font)

        header.addWidget(symbol_label)
        header.addWidget(name_label)
        header.addStretch()
        layout.addLayout(header)

        # 描述
        desc_label = QLabel(info.get("description", ""))
        desc_label.setStyleSheet("color: #666; font-size: 10px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # 详细信息
        if info.get("details"):
            details_text = "\n".join(info.get("details", []))
            details_label = QLabel(details_text)
            details_label.setStyleSheet(
                "color: #555; font-size: 9px; background-color: #fff; padding: 6px; border-radius: 2px;"
            )
            details_label.setWordWrap(True)
            layout.addWidget(details_label)

        return card

    def show_legend(self) -> None:
        """显示说明面板"""
        self.show()

    def hide_legend(self) -> None:
        """隐藏说明面板"""
        self.hide()

    def toggle_legend(self) -> None:
        """切换说明面板的显示/隐藏"""
        if self.isVisible():
            self.hide()
        else:
            self.show()


class StatusSymbolButton(QPushButton):
    """状态符号帮助按钮

    点击打开状态符号说明面板。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化帮助按钮

        Args:
            parent: 父部件
        """
        super().__init__("?", parent)
        self.setToolTip("点击查看文件验证状态说明")
        self.setFixedSize(24, 24)
        self.setStyleSheet(
            """
            QPushButton {
                border-radius: 12px;
                background-color: #2196f3;
                color: white;
                font-weight: bold;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
            """
        )

        self._legend: Optional[StatusSymbolLegend] = None

    def set_legend(self, legend: StatusSymbolLegend) -> None:
        """设置关联的说明面板

        Args:
            legend: StatusSymbolLegend 实例
        """
        self._legend = legend
        self.clicked.connect(self._on_click)

    def _on_click(self) -> None:
        """处理按钮点击事件"""
        if self._legend is not None:
            self._legend.toggle_legend()
