"""
状态横幅组件 - 显示重做状态、加载的项目等持久化状态信息
类似 VS Code 的顶部通知栏，可以关闭
"""

import logging
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

logger = logging.getLogger(__name__)


class BannerStateType(Enum):
    """状态横幅显示的状态类型"""
    NONE = auto()
    REDO_MODE = auto()
    PROJECT_LOADED = auto()
    CUSTOM = auto()


class StateBanner(QWidget):
    """状态横幅 - 显示当前持久化状态（重做模式、加载的项目等）"""

    # 信号：用户点击退出，传递当前状态类型
    exitRequested = Signal()
    # 信号：带状态类型的退出请求
    exitStateRequested = Signal(object)  # BannerStateType

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_state_type = BannerStateType.NONE
        self._setup_ui()
        self.hide()  # 默认隐藏

    def _setup_ui(self):
        """设置 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)  # 减少边距
        layout.setSpacing(8)

        # 默认尺寸策略（非工具栏模式）
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(32)
        self.setMinimumWidth(300)  # 设置最小宽度确保可见
        # 图标标签
        self.icon_label = QLabel("ℹ️")
        self.icon_label.setStyleSheet("font-size: 14px;")  # 缩小图标
        self.icon_label.setFixedWidth(20)
        layout.addWidget(self.icon_label)

        # 消息标签
        self.message_label = QLabel()
        self.message_label.setStyleSheet("font-weight: 500; font-size: 12px;")  # 缩小字体
        self.message_label.setMinimumHeight(24)  # 固定高度以保证工具栏高度一致
        layout.addWidget(self.message_label, 1)

        # 退出按钮
        self.exit_button = QPushButton("✕")  # 改用 ✕ 符号
        self.exit_button.setFixedHeight(22)
        self.exit_button.setFixedWidth(32)
        self.exit_button.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                color: #856404;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255, 193, 7, 0.2);
                border-radius: 3px;
            }
            QPushButton:pressed {
                background-color: rgba(255, 193, 7, 0.4);
            }
        """)
        self.exit_button.clicked.connect(self._on_exit_clicked)
        layout.addWidget(self.exit_button)

        # 样式 - 更紧凑
        self.setStyleSheet("""
            StateBanner {
                background-color: #fff3cd;
                border-bottom: 1px solid #ffc107;
                border-radius: 0px;
                padding: 0px;
                margin: 0px;
                min-height: 32px;
            }
            StateBanner QLabel {
                color: #856404;
                margin: 0px;
                padding: 0px;
            }
        """)

    def apply_toolbar_mode(self):
        """在工具栏中使用时的紧凑模式"""
        try:
            self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            self.setMinimumHeight(28)
            self.setMinimumWidth(200)
            self.setMaximumWidth(320)
            self.message_label.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Preferred
            )
            self.message_label.setMinimumWidth(0)
        except Exception:
            logger.debug("设置状态横幅工具栏模式失败", exc_info=True)

    def set_toolbar_action(self, action):
        """设置工具栏中对应的 QAction，用于控制可见性"""
        self._toolbar_action = action

    def _on_exit_clicked(self):
        """用户点击退出按钮"""
        state_type = self._current_state_type
        self._current_state_type = BannerStateType.NONE
        self._set_visible(False)
        # 发射带状态类型的信号
        try:
            self.exitStateRequested.emit(state_type)
        except Exception:
            pass
        # 同时发射兼容的无参信号
        self.exitRequested.emit()

    def _set_visible(self, visible: bool):
        """设置可见性（兼容工具栏模式）"""
        try:
            action = getattr(self, "_toolbar_action", None)
            if action is not None:
                # 工具栏模式：需要同时设置 action 和 widget 的可见性
                action.setVisible(visible)
                self.setVisible(visible)
            else:
                self.setVisible(visible)
        except Exception:
            self.setVisible(visible)

    def show_redo_state(self, record_info: dict):
        """显示重做状态横幅

        Args:
            record_info: 历史记录信息，包含 input_path, timestamp, redo_count 等
        """
        try:
            input_path = record_info.get("input_path", "未知")
            timestamp = record_info.get("timestamp", "")
            redo_count = record_info.get("redo_count", 0)

            # 简化路径显示
            if input_path and input_path != "未知":
                try:
                    path_obj = Path(input_path)
                    display_path = path_obj.name
                except Exception:
                    display_path = input_path
            else:
                display_path = input_path

            # 构建更详细的消息
            msg_parts = [f"🔄 重做: {display_path}"]
            if timestamp:
                # 提取时间部分（如 10:50:59）
                try:
                    time_part = timestamp.split(" ")[-1] if " " in timestamp else timestamp
                    msg_parts.append(f"({time_part})")
                except Exception:
                    pass
            if redo_count > 0:
                msg_parts.append(f"[已重做 {redo_count} 次]")
            
            msg = " ".join(msg_parts)

            self._current_state_type = BannerStateType.REDO_MODE
            self.icon_label.setText("🔄")
            self.message_label.setText(msg)
            self._set_visible(True)
            self.raise_()
            # 强制更新布局和几何信息
            self.updateGeometry()
            self.adjustSize()
            if self.parent():
                self.parent().update()
            logger.info("状态横幅显示重做状态: visible=%s, sizeHint=%s, geometry=%s", 
                       self.isVisible(), self.sizeHint(), self.geometry())
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

            self._current_state_type = BannerStateType.PROJECT_LOADED
            self.icon_label.setText("📁")
            self.message_label.setText(msg)
            self._set_visible(True)
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
            self._current_state_type = BannerStateType.CUSTOM
            self.icon_label.setText(icon)
            self.message_label.setText(message)
            if style:
                self.setStyleSheet(style)
            self._set_visible(True)
        except Exception as e:
            logger.debug("显示自定义横幅失败: %s", e, exc_info=True)

    def clear(self):
        """清除并隐藏横幅"""
        self._current_state_type = BannerStateType.NONE
        self._set_visible(False)
        self.message_label.setText("")

    @property
    def current_state_type(self) -> BannerStateType:
        """获取当前显示的状态类型"""
        return self._current_state_type
