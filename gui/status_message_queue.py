"""
状态消息队列管理器 - 处理多来源状态消息的优先级与竞争。

功能：
- 优先级队列：高优先级消息不被低优先级覆盖
- FIFO 同优先级：相同优先级按顺序显示
- 自动超时清理：每个消息有独立的超时
- 来源追踪：记录消息来源以便调试
"""

from typing import Optional, List, Tuple, Any
from dataclasses import dataclass, field
from enum import IntEnum
import uuid
import logging

logger = logging.getLogger(__name__)


class MessagePriority(IntEnum):
    """状态消息优先级定义"""

    LOW = 0  # 一般信息（配置加载、文件验证）
    MEDIUM = 1  # 进行中的操作（扫描目录、筛选）
    HIGH = 2  # 工作流步骤指导（步骤1、步骤2）
    CRITICAL = 3  # 错误或严重警告
    # 兼容语义化别名（用于测试与旧调用）
    INFO = LOW
    WARNING = MEDIUM
    ERROR = HIGH


@dataclass
class StatusMessage:
    """单个状态消息"""

    text: str
    timeout_ms: int  # 0 = 永久显示
    priority: int
    source: str = "unknown"  # 消息来源（用于调试）
    token: str = field(default_factory=lambda: uuid.uuid4().hex)  # 唯一标识
    timestamp: float = field(default_factory=lambda: __import__("time").time())

    def __lt__(self, other: "StatusMessage") -> bool:
        """比较用于优先级队列：高优先级先（使用反向排序）"""
        if self.priority != other.priority:
            return self.priority > other.priority
        # 相同优先级按时间戳排序（先入先出）
        return self.timestamp < other.timestamp

    def __eq__(self, other: Any) -> bool:
        """按 token 比较相等"""
        if not isinstance(other, StatusMessage):
            return False
        return self.token == other.token


class StatusMessageQueue:
    """管理状态消息的优先级队列"""

    def __init__(self):
        self._queue: List[StatusMessage] = []
        self._current_message: Optional[StatusMessage] = None
        self._current_timer_token: Optional[str] = None

    def add_message(
        self,
        text: str,
        timeout_ms: int = 0,
        priority: int = 0,
        source: str = "unknown",
    ) -> str:
        """
        添加消息到队列。

        Args:
            text: 消息文本
            timeout_ms: 超时（毫秒），0 表示永久
            priority: 优先级（越高越优先）
            source: 消息来源（用于调试）

        Returns:
            消息的 token（用于后续更新或取消）
        """
        msg = StatusMessage(text, timeout_ms, priority, source)
        self._queue.append(msg)
        # 按优先级排序
        self._queue.sort()
        logger.debug(
            f"添加消息到队列: '{text[:50]}' (priority={priority}, source={source})"
        )
        return msg.token

    def get_next_message(self) -> Optional[StatusMessage]:
        """获取当前应显示的消息（队列顶部的消息）"""
        if not self._queue:
            return None
        return self._queue[0]

    def remove_message(self, token: str) -> bool:
        """
        删除指定 token 的消息。

        Args:
            token: 消息的 token

        Returns:
            是否找到并删除了消息
        """
        original_size = len(self._queue)
        self._queue = [msg for msg in self._queue if msg.token != token]
        removed = len(self._queue) < original_size

        if removed:
            logger.debug(f"从队列移除消息: token={token}")
            # 如果删除的是当前显示的消息，需要更新显示
            if (
                self._current_message is not None
                and self._current_message.token == token
            ):
                self._current_message = None
                self._current_timer_token = None

        return removed

    def clear_lower_priority(self, min_priority: int) -> int:
        """
        清除所有低于指定优先级的消息。

        Args:
            min_priority: 最低优先级（低于此优先级的消息会被清除）

        Returns:
            清除的消息数量
        """
        original_size = len(self._queue)
        self._queue = [msg for msg in self._queue if msg.priority >= min_priority]
        removed_count = original_size - len(self._queue)

        if removed_count > 0:
            logger.debug(f"清除 {removed_count} 条低优先级消息（阈值={min_priority}）")

        return removed_count

    def clear_all(self) -> None:
        """清除所有消息"""
        self._queue.clear()
        self._current_message = None
        self._current_timer_token = None
        logger.debug("清除所有状态消息")

    def has_messages(self) -> bool:
        """检查队列是否有消息"""
        return len(self._queue) > 0

    def queue_size(self) -> int:
        """获取队列中的消息数量"""
        return len(self._queue)

    def set_current_message(self, msg: Optional[StatusMessage]) -> None:
        """设置当前正在显示的消息"""
        self._current_message = msg
        if msg is not None:
            self._current_timer_token = msg.token

    def get_current_message(self) -> Optional[StatusMessage]:
        """获取当前正在显示的消息"""
        return self._current_message

    def get_current_timer_token(self) -> Optional[str]:
        """获取当前显示消息的 token"""
        return self._current_timer_token

    def message_is_current(self, token: str) -> bool:
        """检查指定 token 的消息是否为当前显示的消息"""
        return (
            self._current_message is not None and self._current_message.token == token
        )

    def should_accept_message(
        self, new_msg: StatusMessage
    ) -> Tuple[bool, Optional[str]]:
        """
        检查是否应接受新消息。

        如果新消息优先级高于当前显示的消息，应接受。
        如果新消息优先级相同或更低，但队列中有更高优先级的消息等待，也应接受。

        Returns:
            (是否接受, 需要中断的消息 token)
        """
        if self._current_message is None:
            return (True, None)

        if new_msg.priority > self._current_message.priority:
            # 新消息优先级更高，应中断当前消息
            return (True, self._current_message.token)

        if new_msg.priority < self._current_message.priority:
            # 新消息优先级更低，不中断当前消息
            return (False, None)

        # 相同优先级：若当前为永久提示且新消息也是永久提示，则允许替换
        try:
            if (
                self._current_message is not None
                and self._current_message.timeout_ms == 0
                and new_msg.timeout_ms == 0
            ):
                return (True, self._current_message.token)
        except Exception:
            pass

        # 相同优先级，接受但不中断
        return (True, None)
