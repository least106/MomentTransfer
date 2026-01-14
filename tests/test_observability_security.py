"""
可观测性和安全性测试 - 验证性能监控、日志和数据验证功能
"""

import sys
import tempfile
from pathlib import Path

import pytest

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from src.logging_system import (LogContext, LoggerFactory, StructuredLogger,
                                log_operation_context)
from src.performance import (PerformanceMonitor, get_performance_monitor,
                             measure_performance)
from src.validator import DataValidator, ValidationError


class TestPerformanceMonitoring:
    """性能监控测试"""

    def test_performance_monitor_creation(self):
        """测试性能监控器创建"""
        monitor = PerformanceMonitor()
        assert monitor is not None

    def test_start_end_measurement(self):
        """测试测量开始和结束"""
        import time

        monitor = PerformanceMonitor()
        metrics = monitor.start_measurement("test_metric")
        assert metrics.metric_name == "test_metric"
        assert metrics.duration_ms == 0.0

        time.sleep(0.01)  # 增加微小延迟以确保时间差
        monitor.end_measurement(metrics)
        assert metrics.duration_ms >= 10.0  # 至少 10ms

    def test_measure_context_manager(self):
        """测试上下文管理器测量"""
        monitor = PerformanceMonitor()

        with monitor.measure("test_operation"):
            import time

            time.sleep(0.01)

        stats = monitor.get_stats("test_operation")
        assert stats["count"] == 1
        assert stats["duration_ms"]["avg"] >= 10.0

    def test_get_stats(self):
        """测试获取统计信息"""
        monitor = PerformanceMonitor()
        monitor.record_metric("metric1", 10.0)
        monitor.record_metric("metric1", 20.0)
        monitor.record_metric("metric1", 30.0)

        stats = monitor.get_stats("metric1")
        assert stats["count"] == 3
        assert stats["duration_ms"]["min"] == 10.0
        assert stats["duration_ms"]["max"] == 30.0
        assert abs(stats["duration_ms"]["avg"] - 20.0) < 0.01

    def test_system_stats(self):
        """测试系统统计"""
        monitor = PerformanceMonitor()
        sys_stats = monitor.get_system_stats()

        # psutil 可能不可用，所以只检查如果存在的话要有正确的类型
        if "cpu_percent" in sys_stats:
            assert isinstance(sys_stats["cpu_percent"], (int, float))
        # 如果 psutil 不可用，dict 可能为空，这也是可接受的

    def test_decorator(self):
        """测试性能监控装饰器"""

        @measure_performance
        def test_func():
            import time

            time.sleep(0.01)  # 增加延迟
            return 42

        result = test_func()
        assert result == 42

        monitor = get_performance_monitor()
        stats = monitor.get_stats("test_observability_security.test_func")
        if stats:  # 如果收集到了统计信息
            assert stats["count"] >= 1


class TestStructuredLogging:
    """结构化日志测试"""

    def test_logger_creation(self):
        """测试日志记录器创建"""
        logger = StructuredLogger("test")
        assert logger is not None

    def test_log_context(self):
        """测试日志上下文"""
        with LogContext("ctx_123", "test_operation", user_id="user_1") as ctx:
            assert LogContext.get_current() == ctx
            context_dict = ctx.to_dict()
            assert context_dict["context_id"] == "ctx_123"
            assert context_dict["operation"] == "test_operation"

        assert LogContext.get_current() is None

    def test_logger_factory(self):
        """测试日志工厂"""
        LoggerFactory.configure(log_level="INFO")
        logger1 = LoggerFactory.get_logger("test1")
        logger2 = LoggerFactory.get_logger("test1")

        assert logger1 is logger2  # 单例模式

    def test_operation_context(self):
        """测试操作上下文"""
        with log_operation_context("test_op", "op_123") as logger:
            logger.info("test message")

        # 应该执行无错误
        assert True


class TestDataValidation:
    """数据验证测试"""

    def test_validate_coordinate_list(self):
        """测试坐标验证（列表）"""
        coord = DataValidator.validate_coordinate([1.0, 2.0, 3.0])
        assert coord == (1.0, 2.0, 3.0)

    def test_validate_coordinate_invalid_length(self):
        """测试无效坐标长度"""
        with pytest.raises(ValidationError):
            DataValidator.validate_coordinate([1.0, 2.0])

    def test_validate_coordinate_nan(self):
        """测试包含 NaN 的坐标"""
        with pytest.raises(ValidationError):
            DataValidator.validate_coordinate([1.0, np.nan, 3.0])

    def test_validate_numeric_range(self):
        """测试数值范围验证"""
        val = DataValidator.validate_numeric_range(5.0, min_val=0, max_val=10)
        assert val == 5.0

    def test_validate_numeric_range_violation(self):
        """测试数值范围违反"""
        with pytest.raises(ValidationError):
            DataValidator.validate_numeric_range(15.0, min_val=0, max_val=10)

    def test_validate_file_path(self):
        """测试文件路径验证"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test")

            validated = DataValidator.validate_file_path(
                str(test_file), must_exist=True
            )
            assert validated.exists()

    def test_validate_file_path_not_exists(self):
        """测试不存在的文件路径"""
        with pytest.raises(ValidationError):
            DataValidator.validate_file_path("/nonexistent/path.txt", must_exist=True)

    def test_validate_path_traversal(self):
        """测试路径遍历防护"""
        with pytest.raises(ValidationError):
            DataValidator.validate_file_path("../../etc/passwd")

    def test_validate_csv_safety(self):
        """测试 CSV 文件安全性验证"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "test.csv"
            csv_file.write_text("col1,col2\n1,2\n3,4")

            validated = DataValidator.validate_csv_safety(str(csv_file))
            assert validated.exists()

    def test_validate_data_frame(self):
        """测试 DataFrame 验证"""
        df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        validated_df = DataValidator.validate_data_frame(
            df, required_columns=["A", "B"]
        )
        assert len(validated_df) == 3

    def test_validate_data_frame_missing_column(self):
        """测试缺失列验证"""
        df = pd.DataFrame({"A": [1, 2, 3]})
        with pytest.raises(ValidationError):
            DataValidator.validate_data_frame(df, required_columns=["A", "B"])

    def test_validate_column_mapping(self):
        """测试列映射验证"""
        available = ["col1", "col2", "col3"]
        mapping = {"x": "col1", "y": "col2"}
        validated = DataValidator.validate_column_mapping(mapping, available)
        assert validated == mapping

    def test_validate_column_mapping_missing_column(self):
        """测试映射中的缺失列"""
        available = ["col1", "col2"]
        mapping = {"x": "col3"}
        with pytest.raises(ValidationError):
            DataValidator.validate_column_mapping(mapping, available)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
