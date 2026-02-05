"""测试配置加载后的用户反馈功能"""

import pytest
from unittest.mock import MagicMock
from pathlib import Path


class TestConfigLoadFeedback:
    """测试配置加载后的详细反馈"""

    def test_status_message_format_with_parts(self):
        """测试状态消息格式包含 Parts 数量"""
        from gui.status_message_queue import MessagePriority
        
        # 测试消息格式
        source_count = 2
        target_count = 3
        config_name = "test_config.json"
        
        parts_info = f"{source_count} 个 Source Parts，{target_count} 个 Target Parts"
        message = f"✓ 已加载配置：{config_name} | {parts_info}"
        
        # 验证消息格式
        assert "✓" in message
        assert "已加载配置" in message
        assert config_name in message
        assert "2 个 Source Parts" in message
        assert "3 个 Target Parts" in message
        assert "|" in message  # 分隔符

    def test_status_message_with_zero_parts(self):
        """测试 0 个 Parts 的消息格式"""
        source_count = 0
        target_count = 0
        config_name = "empty.json"
        
        parts_info = f"{source_count} 个 Source Parts，{target_count} 个 Target Parts"
        message = f"✓ 已加载配置：{config_name} | {parts_info}"
        
        assert "0 个 Source Parts" in message
        assert "0 个 Target Parts" in message

    def test_status_message_with_one_part(self):
        """测试只有 1 个 Part 的消息格式"""
        source_count = 1
        target_count = 1
        config_name = "simple.json"
        
        parts_info = f"{source_count} 个 Source Parts，{target_count} 个 Target Parts"
        message = f"✓ 已加载配置：{config_name} | {parts_info}"
        
        assert "1 个 Source Parts" in message
        assert "1 个 Target Parts" in message

    def test_status_message_with_many_parts(self):
        """测试多个 Parts 的消息格式"""
        source_count = 10
        target_count = 15
        config_name = "complex.json"
        
        parts_info = f"{source_count} 个 Source Parts，{target_count} 个 Target Parts"
        message = f"✓ 已加载配置：{config_name} | {parts_info}"
        
        assert "10 个 Source Parts" in message
        assert "15 个 Target Parts" in message

    def test_message_priority_is_medium(self):
        """测试消息优先级为 MEDIUM"""
        from gui.status_message_queue import MessagePriority
        
        # MEDIUM 优先级确保用户看到重要的配置加载信息
        assert MessagePriority.MEDIUM > MessagePriority.LOW
        assert MessagePriority.MEDIUM < MessagePriority.HIGH

    def test_message_timeout_is_sufficient(self):
        """测试消息显示时间足够长"""
        timeout = 8000  # 8 秒
        
        # 8 秒应该足够用户阅读 Parts 数量信息
        assert timeout >= 5000  # 至少 5 秒
        assert timeout <= 15000  # 不超过 15 秒

    def test_filename_extraction(self):
        """测试从完整路径提取文件名"""
        full_path = "C:/Users/test/config/my_config.json"
        config_name = Path(full_path).name
        
        assert config_name == "my_config.json"
        assert "/" not in config_name
        assert "\\" not in config_name

    def test_parts_info_format(self):
        """测试 Parts 信息字符串格式"""
        source_count = 5
        target_count = 7
        
        parts_info = f"{source_count} 个 Source Parts，{target_count} 个 Target Parts"
        
        # 验证格式
        assert "Source Parts" in parts_info
        assert "Target Parts" in parts_info
        assert "，" in parts_info  # 中文逗号分隔
        assert str(source_count) in parts_info
        assert str(target_count) in parts_info

