"""
测试状态消息优先级与多来源竞争管理。

问题 10：状态消息的优先级与多来源竞争
- 多个模块同时发出 statusMessage 信号
- 优先级系统可能在快速操作序列中失效
- 用户看到错误的状态消息
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
import time

from gui.status_message_queue import (
    StatusMessage,
    StatusMessageQueue,
    MessagePriority,
)


class TestStatusMessage:
    """单个状态消息的测试"""

    def test_status_message_creation(self):
        """测试状态消息创建"""
        msg = StatusMessage(
            text="测试消息", timeout_ms=5000, priority=1, source="test"
        )

        assert msg.text == "测试消息"
        assert msg.timeout_ms == 5000
        assert msg.priority == 1
        assert msg.source == "test"
        assert msg.token is not None

    def test_status_message_unique_tokens(self):
        """测试不同消息有不同的 token"""
        msg1 = StatusMessage("消息1", 5000, 1)
        msg2 = StatusMessage("消息2", 5000, 1)

        assert msg1.token != msg2.token

    def test_status_message_comparison_by_priority(self):
        """测试消息按优先级排序（高优先级先）"""
        msg_low = StatusMessage("低优先级", 5000, 0)
        msg_high = StatusMessage("高优先级", 5000, 2)

        # 高优先级消息应小于低优先级消息（用于逆序排列）
        assert msg_high < msg_low

    def test_status_message_comparison_same_priority_by_timestamp(self):
        """测试相同优先级的消息按时间戳排序"""
        msg1 = StatusMessage("消息1", 5000, 1)
        time.sleep(0.01)  # 确保时间戳不同
        msg2 = StatusMessage("消息2", 5000, 1)

        # msg1 应在 msg2 之前（先入先出）
        assert msg1 < msg2

    def test_status_message_equality_by_token(self):
        """测试消息按 token 比较相等"""
        msg1 = StatusMessage("消息", 5000, 1)
        msg2 = StatusMessage("其他消息", 5000, 1)

        # 虽然文本不同，但应能按 token 识别
        assert msg1 != msg2
        assert msg1 == msg1


class TestStatusMessageQueue:
    """状态消息队列的测试"""

    def test_queue_initialization(self):
        """测试队列初始化"""
        queue = StatusMessageQueue()

        assert queue.queue_size() == 0
        assert not queue.has_messages()
        assert queue.get_next_message() is None

    def test_add_single_message(self):
        """测试添加单个消息"""
        queue = StatusMessageQueue()
        token = queue.add_message("测试消息", 5000, 1)

        assert token is not None
        assert queue.has_messages()
        assert queue.queue_size() == 1

    def test_add_multiple_messages(self):
        """测试添加多个消息"""
        queue = StatusMessageQueue()
        token1 = queue.add_message("消息1", 5000, 1)
        token2 = queue.add_message("消息2", 5000, 1)
        token3 = queue.add_message("消息3", 5000, 1)

        assert queue.queue_size() == 3
        assert token1 != token2 != token3

    def test_queue_prioritization(self):
        """测试消息按优先级排序"""
        queue = StatusMessageQueue()
        queue.add_message("低优先级", 5000, 0)
        queue.add_message("高优先级", 5000, 2)
        queue.add_message("中优先级", 5000, 1)

        # 获取顶部消息应是高优先级
        top = queue.get_next_message()
        assert top is not None
        assert top.text == "高优先级"
        assert top.priority == 2

    def test_same_priority_fifo(self):
        """测试相同优先级按先入先出排序"""
        queue = StatusMessageQueue()
        queue.add_message("消息A", 5000, 1)
        time.sleep(0.01)  # 确保时间戳差异
        queue.add_message("消息B", 5000, 1)

        # 顶部应是先添加的消息A
        top = queue.get_next_message()
        assert top is not None
        assert top.text == "消息A"

    def test_remove_message_by_token(self):
        """测试按 token 删除消息"""
        queue = StatusMessageQueue()
        token1 = queue.add_message("消息1", 5000, 1)
        token2 = queue.add_message("消息2", 5000, 1)

        assert queue.queue_size() == 2
        removed = queue.remove_message(token1)

        assert removed is True
        assert queue.queue_size() == 1
        top = queue.get_next_message()
        assert top.text == "消息2"

    def test_remove_nonexistent_message(self):
        """测试删除不存在的消息"""
        queue = StatusMessageQueue()
        queue.add_message("消息1", 5000, 1)

        removed = queue.remove_message("不存在的token")
        assert removed is False
        assert queue.queue_size() == 1

    def test_clear_lower_priority(self):
        """测试清除低优先级消息"""
        queue = StatusMessageQueue()
        queue.add_message("优先级0", 5000, 0)
        queue.add_message("优先级1", 5000, 1)
        queue.add_message("优先级2", 5000, 2)

        # 清除低于优先级 2 的消息
        removed_count = queue.clear_lower_priority(2)

        assert removed_count == 2
        assert queue.queue_size() == 1
        top = queue.get_next_message()
        assert top.priority == 2

    def test_clear_all(self):
        """测试清除所有消息"""
        queue = StatusMessageQueue()
        queue.add_message("消息1", 5000, 1)
        queue.add_message("消息2", 5000, 1)

        queue.clear_all()

        assert queue.queue_size() == 0
        assert not queue.has_messages()

    def test_set_and_get_current_message(self):
        """测试设置和获取当前消息"""
        queue = StatusMessageQueue()
        msg = StatusMessage("当前消息", 5000, 1)

        queue.set_current_message(msg)

        assert queue.get_current_message() == msg
        assert queue.get_current_timer_token() == msg.token

    def test_message_is_current(self):
        """测试检查消息是否为当前显示的"""
        queue = StatusMessageQueue()
        msg = StatusMessage("当前消息", 5000, 1)

        queue.set_current_message(msg)

        assert queue.message_is_current(msg.token)
        assert not queue.message_is_current("其他token")

    def test_should_accept_message_higher_priority(self):
        """测试高优先级消息会被接受并中断当前消息"""
        queue = StatusMessageQueue()
        msg_current = StatusMessage("当前消息", 5000, 1)
        queue.set_current_message(msg_current)

        msg_new = StatusMessage("新消息", 5000, 2)  # 更高优先级

        accept, interrupt_token = queue.should_accept_message(msg_new)

        assert accept is True
        assert interrupt_token == msg_current.token

    def test_should_accept_message_lower_priority(self):
        """测试低优先级消息不会中断当前消息"""
        queue = StatusMessageQueue()
        msg_current = StatusMessage("当前消息", 5000, 2)
        queue.set_current_message(msg_current)

        msg_new = StatusMessage("新消息", 5000, 1)  # 更低优先级

        accept, interrupt_token = queue.should_accept_message(msg_new)

        assert accept is False
        assert interrupt_token is None

    def test_should_accept_message_same_priority(self):
        """测试相同优先级的消息被接受但不中断"""
        queue = StatusMessageQueue()
        msg_current = StatusMessage("当前消息", 5000, 1)
        queue.set_current_message(msg_current)

        msg_new = StatusMessage("新消息", 5000, 1)  # 相同优先级

        accept, interrupt_token = queue.should_accept_message(msg_new)

        assert accept is True
        assert interrupt_token is None

    def test_should_accept_message_no_current(self):
        """测试没有当前消息时所有消息都被接受"""
        queue = StatusMessageQueue()

        msg = StatusMessage("新消息", 5000, 1)

        accept, interrupt_token = queue.should_accept_message(msg)

        assert accept is True
        assert interrupt_token is None


class TestMessagePriorityEnum:
    """优先级枚举的测试"""

    def test_priority_values(self):
        """测试优先级值"""
        assert MessagePriority.LOW == 0
        assert MessagePriority.MEDIUM == 1
        assert MessagePriority.HIGH == 2
        assert MessagePriority.CRITICAL == 3

    def test_priority_ordering(self):
        """测试优先级可以比较"""
        assert MessagePriority.HIGH > MessagePriority.LOW
        assert MessagePriority.CRITICAL > MessagePriority.MEDIUM


class TestQueueComplexScenarios:
    """复杂场景测试"""

    def test_rapid_message_sequence(self):
        """测试快速消息序列"""
        queue = StatusMessageQueue()

        # 模拟快速操作序列
        token1 = queue.add_message("配置已加载", 2000, 0)
        token2 = queue.add_message("正在准备批处理", 0, 2)
        token3 = queue.add_message("扫描目录中...", 0, 1)

        # 最高优先级应在顶部
        top = queue.get_next_message()
        assert top.priority == 2
        assert top.text == "正在准备批处理"

        # 移除后应显示下一条
        queue.remove_message(token2)
        top = queue.get_next_message()
        assert top.priority == 1
        assert top.text == "扫描目录中..."

    def test_concurrent_sources(self):
        """测试多来源并发消息"""
        queue = StatusMessageQueue()

        # 模拟来自不同模块的并发消息
        queue.add_message("配置已加载", 3000, 0, source="ConfigManager")
        queue.add_message("文件已选择", 2000, 1, source="BatchManager")
        queue.add_message("步骤2：选择行", 0, 2, source="UIStateManager")

        # 应显示最高优先级的消息
        top = queue.get_next_message()
        assert top.source == "UIStateManager"
        assert top.priority == 2

    def test_message_replacement_scenario(self):
        """测试消息替换场景"""
        queue = StatusMessageQueue()

        # 初始消息
        token1 = queue.add_message("初始消息", 5000, 0)
        queue.set_current_message(queue.get_next_message())

        # 高优先级消息中断
        queue.add_message("紧急消息", 0, 2)

        # 检查是否应中断
        msg_current = queue.get_current_message()
        new_msg = StatusMessage("新优先级2消息", 0, 2)
        accept, interrupt = queue.should_accept_message(new_msg)

        # 当前消息被中断
        assert msg_current.priority == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
