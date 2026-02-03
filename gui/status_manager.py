"""状态栏消息管理模块 - 处理状态栏消息的优先级和显示逻辑"""

import logging
import uuid
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QStatusBar

logger = logging.getLogger(__name__)


class StatusMessageManager:
    """管理状态栏消息的显示、优先级和超时"""

    def __init__(self, status_bar: QStatusBar, status_label: QLabel):
        """
        初始化状态消息管理器

        参数：
            status_bar: 状态栏组件
            status_label: 状态标签组件
        """
        self.status_bar = status_bar
        self.status_label = status_label
        self._status_token: Optional[str] = None
        self._status_priority: int = 0
        self._status_clear_timer: Optional[QTimer] = None

    def show_message(
        self, message: str, timeout: int = 0, priority: int = 1
    ) -> Optional[str]:
        """
        显示状态栏消息

        参数：
            message: 要显示的消息
            timeout: 超时时间（毫秒），0表示永久显示
            priority: 优先级（数字越大优先级越高）

        返回：
            消息令牌，用于后续清除或更新
        """
        try:
            # 只有优先级更高或相等时才允许更新消息
            if priority < self._status_priority:
                logger.debug(
                    f"消息优先级({priority})低于当前优先级"
                    f"({self._status_priority})，忽略"
                )
                return None

            # 生成新令牌
            token = uuid.uuid4().hex
            self._status_token = token
            self._status_priority = priority

            # 显示消息
            self.status_label.setText(message)
            self.status_bar.showMessage(message, timeout)

            # 处理定时清除
            if timeout > 0:
                self._schedule_clear(timeout, token, priority)

            return token

        except Exception:
            logger.debug("显示状态消息失败", exc_info=True)
            return None

    def clear_message(
        self, token: Optional[str] = None, min_priority: int = 0
    ) -> bool:
        """
        清除状态栏消息

        参数：
            token: 消息令牌，如果提供则只清除匹配的消息
            min_priority: 最小优先级，只清除优先级>=此值的消息

        返回：
            是否成功清除
        """
        try:
            # 检查令牌是否匹配
            if token and token != self._status_token:
                return False

            # 检查优先级
            if self._status_priority < min_priority:
                return False

            # 清除消息
            self.status_label.setText("")
            self.status_bar.clearMessage()
            self._status_token = None
            self._status_priority = 0

            # 取消定时器
            if self._status_clear_timer:
                self._status_clear_timer.stop()
                self._status_clear_timer = None

            return True

        except Exception:
            logger.debug("清除状态消息失败", exc_info=True)
            return False

    def _schedule_clear(self, timeout: int, token: str, priority: int):
        """
        安排消息的自动清除

        参数：
            timeout: 超时时间（毫秒）
            token: 消息令牌
            priority: 消息优先级
        """
        try:
            # 取消之前的定时器
            if self._status_clear_timer:
                self._status_clear_timer.stop()

            # 创建新定时器
            self._status_clear_timer = QTimer()
            self._status_clear_timer.setSingleShot(True)
            self._status_clear_timer.timeout.connect(
                lambda: self.clear_message(token, priority)
            )
            self._status_clear_timer.start(timeout)

        except Exception:
            logger.debug("安排消息清除失败", exc_info=True)


class NotificationManager:
    """管理通知消息的显示和超时"""

    def __init__(self, parent):
        """
        初始化通知管理器

        参数：
            parent: 父窗口
        """
        self.parent = parent
        self._notification_token: Optional[str] = None
        self._notification_timer: Optional[QTimer] = None
        self._notification_btn: Optional[object] = None

    def show_notification(
        self,
        message: str,
        level: str = "info",
        timeout: int = 5000,
        action_text: Optional[str] = None,
        action_callback=None,
    ) -> Optional[str]:
        """
        显示通知消息

        参数：
            message: 消息内容
            level: 消息级别（info/warning/error）
            timeout: 超时时间（毫秒），0表示永久显示
            action_text: 操作按钮文本
            action_callback: 操作按钮回调

        返回：
            通知令牌
        """
        try:
            from gui.ui_utils import create_notification

            token = uuid.uuid4().hex
            self._notification_token = token

            # 创建通知
            notif_widget, btn = create_notification(
                self.parent,
                message,
                level=level,
                action_text=action_text,
                action_callback=action_callback,
            )

            self._notification_btn = btn

            # 处理自动关闭
            if timeout > 0:
                self._schedule_clear(timeout, token)

            return token

        except Exception:
            logger.debug("显示通知失败", exc_info=True)
            return None

    def clear_notification(self, token: Optional[str] = None) -> bool:
        """
        清除通知

        参数：
            token: 通知令牌，如果提供则只清除匹配的通知

        返回：
            是否成功清除
        """
        try:
            # 检查令牌
            if token and token != self._notification_token:
                return False

            # 清除通知按钮
            if self._notification_btn:
                try:
                    self._notification_btn.deleteLater()
                except Exception:
                    pass
                self._notification_btn = None

            self._notification_token = None

            # 取消定时器
            if self._notification_timer:
                self._notification_timer.stop()
                self._notification_timer = None

            return True

        except Exception:
            logger.debug("清除通知失败", exc_info=True)
            return False

    def _schedule_clear(self, timeout: int, token: str):
        """
        安排通知的自动清除

        参数：
            timeout: 超时时间（毫秒）
            token: 通知令牌
        """
        try:
            # 取消之前的定时器
            if self._notification_timer:
                self._notification_timer.stop()

            # 创建新定时器
            self._notification_timer = QTimer()
            self._notification_timer.setSingleShot(True)
            self._notification_timer.timeout.connect(
                lambda: self.clear_notification(token)
            )
            self._notification_timer.start(timeout)

        except Exception:
            logger.debug("安排通知清除失败", exc_info=True)
