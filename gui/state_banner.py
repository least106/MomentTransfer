"""
状态横幅组件 - 显示重做状态、加载的项目等持久化状态信息
类似 VS Code 的顶部通知栏，可以关闭
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

logger = logging.getLogger(__name__)


class StateBanner(QWidget):
    """状态横幅 - 显示当前持久化状态（重做模式、加载的项目等）"""

    # 信号：用户点击退出
    exitRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.hide()  # 默认隐藏

    def _setup_ui(self):
        """设置 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 图标标签
        self.icon_label = QLabel("ℹ️")
        self.icon_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(self.icon_label)

        # 消息标签
        self.message_label = QLabel()
        self.message_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.message_label, 1)

        # 退出按钮
        self.exit_button = QPushButton("退出")
        self.exit_button.setFixedHeight(24)
        self.exit_button.setFixedWidth(60)
        self.exit_button.clicked.connect(self._on_exit_clicked)
        layout.addWidget(self.exit_button)

        # 样式
        self.setStyleSheet("""
            StateBanner {
                background-color: #fff3cd;
                border-bottom: 1px solid #ffc107;
                border-radius: 0px;
            }
            StateBanner QLabel {
                color: #856404;
            }
            StateBanner QPushButton {
                background-color: #ffc107;
                color: #212529;
                border: 1px solid #ffc107;
                border-radius: 3px;
                padding: 4px 12px;
                font-weight: bold;
            }
            StateBanner QPushButton:hover {
                background-color: #e0a800;
                border-color: #d39e00;
            }
            StateBanner QPushButton:pressed {
                background-color: #d39e00;
            }
        """)

    def _on_exit_clicked(self):
        """用户点击退出按钮"""
        self.hide()
        self.exitRequested.emit()

    def show_redo_state(self, record_info: dict):
        """显示重做状态横幅

        Args:
            record_info: 历史记录信息，包含 input_path, timestamp 等
        """
        try:
            input_path = record_info.get("input_path", "未知")
            timestamp = record_info.get("timestamp", "")

            # 简化路径显示
            if input_path and input_path != "未知":
                try:
                    path_obj = Path(input_path)
                    display_path = path_obj.name
                except Exception:
                    display_path = input_path
            else:
                display_path = input_path

            # 格式化时间
            time_str = ""
            if timestamp:
                try:
                    from datetime import datetime

                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    time_str = timestamp

            # 设置消息
            msg = f"🔄 重做模式：{display_path}"
            if time_str:
                msg += f" ({time_str})"
            msg += " - 点击「开始处理」重新执行批处理"

            self.icon_label.setText("🔄")
            self.message_label.setText(msg)
            self.show()
        except Exception as e:
            logger.debug("显示重做状态横幅失败: %s", e, exc_info=True)

    def show_project_loaded(self, project_path: str):
        """显示加载的项目横幅

        Args:
            project_path: 项目文件路径
        """
        try:
            # 简化路径显示
            try:
                path_obj = Path(project_path)
                display_name = path_obj.name
            except Exception:
                display_name = project_path

            msg = f"📁 已加载项目：{display_name}"

            self.icon_label.setText("📁")
            self.message_label.setText(msg)
            self.show()
        except Exception as e:
            logger.debug("显示项目加载横幅失败: %s", e, exc_info=True)

    def show_custom_message(
        self, message: str, icon: str = "ℹ️", style: Optional[str] = None
    ):
        """显示自定义消息

        Args:
            message: 消息文本
            icon: 图标 emoji
            style: 可选的自定义样式（覆盖默认样式）
        """
        try:
            self.icon_label.setText(icon)
            self.message_label.setText(message)
            if style:
                self.setStyleSheet(style)
            self.show()
        except Exception as e:
            logger.debug("显示自定义横幅失败: %s", e, exc_info=True)

    def clear(self):
        """清除并隐藏横幅"""
        self.hide()
        self.message_label.setText("")
