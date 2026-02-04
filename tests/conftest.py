"""
pytest 配置文件 - 全局测试环境设置

确保测试运行时不会污染真实的批处理历史记录和配置文件
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """设置测试环境变量，确保测试隔离
    
    - 设置 TESTING=1 标记测试环境
    - 创建临时测试目录
    - 测试结束后清理（可选）
    """
    # 设置测试环境标记
    os.environ["TESTING"] = "1"
    
    # 创建临时测试目录
    test_dir = Path(tempfile.gettempdir()) / ".momentconversion_test"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"测试环境已启用")
    print(f"  TESTING=1")
    print(f"  临时目录: {test_dir}")
    print(f"{'='*60}\n")
    
    yield
    
    # 测试结束后清理环境变量
    os.environ.pop("TESTING", None)
    
    print(f"\n{'='*60}")
    print(f"测试环境已清理")
    print(f"{'='*60}\n")


@pytest.fixture(scope="function", autouse=True)
def isolate_test():
    """为每个测试函数提供隔离环境
    
    确保测试之间互不影响
    """
    # 测试开始前的设置
    yield
    # 测试结束后的清理（如果需要）


# 可选：添加测试标记
def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line(
        "markers", 
        "gui: 标记 GUI 相关测试（需要 QApplication）"
    )
    config.addinivalue_line(
        "markers",
        "slow: 标记慢速测试"
    )
    config.addinivalue_line(
        "markers",
        "integration: 标记集成测试"
    )
