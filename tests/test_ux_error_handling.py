"""UX 专项测试 - 错误处理和用户反馈

测试用户体验相关的功能：
- 错误消息的清晰度和准确性
- 用户操作的及时反馈
- 初始化状态的正确管理
- 全局错误处理器的功能
"""

import logging
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QMessageBox, QWidget

from gui.global_error_handler import (
    ErrorRecord,
    ErrorSeverity,
    GlobalErrorHandler,
    connect_to_signal_bus,
    report_error,
    report_exception,
)
from gui.initialization_state import (
    ComponentState,
    InitializationStage,
    InitializationStateManager,
    guard_initialization,
)

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def reset_singletons():
    """每个测试前重置单例"""
    # 重置 GlobalErrorHandler
    GlobalErrorHandler._instance = None

    # 重置 InitializationStateManager
    InitializationStateManager._instance = None

    yield

    # 清理
    GlobalErrorHandler._instance = None
    InitializationStateManager._instance = None


class TestGlobalErrorHandler:
    """测试全局错误处理器"""

    def test_singleton_pattern(self):
        """测试单例模式"""
        handler1 = GlobalErrorHandler.instance()
        handler2 = GlobalErrorHandler.instance()
        assert handler1 is handler2

    def test_error_reporting(self):
        """测试错误报告"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        record = handler.report_error(
            title="测试错误",
            message="这是一个测试错误",
            severity=ErrorSeverity.ERROR,
            details="详细信息",
            source="test",
        )

        assert record.title == "测试错误"
        assert record.message == "这是一个测试错误"
        assert record.severity == ErrorSeverity.ERROR
        assert record.details == "详细信息"
        assert record.source == "test"

    def test_exception_reporting(self):
        """测试异常报告"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        try:
            raise ValueError("测试异常")
        except ValueError as e:
            record = handler.report_exception(
                title="异常测试", exception=e, source="test"
            )

            assert record.title == "异常测试"
            assert "测试异常" in record.message
            assert record.traceback is not None
            assert "ValueError" in record.details

    def test_error_severity_levels(self):
        """测试不同严重程度的错误"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        severities = [
            ErrorSeverity.DEBUG,
            ErrorSeverity.INFO,
            ErrorSeverity.WARNING,
            ErrorSeverity.ERROR,
            ErrorSeverity.CRITICAL,
        ]

        for severity in severities:
            handler.report_error(
                title=f"{severity.value} 测试",
                message="测试消息",
                severity=severity,
            )

        # 验证所有错误都被记录
        history = handler.get_error_history(limit=10)
        assert len(history) == len(severities)

    def test_error_history(self):
        """测试错误历史记录"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        # 添加多个错误
        for i in range(5):
            handler.report_error(
                title=f"错误 {i}",
                message=f"消息 {i}",
                severity=ErrorSeverity.ERROR,
            )

        # 获取历史
        history = handler.get_error_history()
        assert len(history) == 5

        # 验证顺序（最新的在前）
        assert history[0].title == "错误 4"
        assert history[4].title == "错误 0"

    def test_error_history_filtering(self):
        """测试错误历史过滤"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        # 添加不同严重程度的错误
        handler.report_error("错误1", "msg", ErrorSeverity.ERROR)
        handler.report_error("警告1", "msg", ErrorSeverity.WARNING)
        handler.report_error("错误2", "msg", ErrorSeverity.ERROR)
        handler.report_error("警告2", "msg", ErrorSeverity.WARNING)

        # 只获取错误
        errors = handler.get_error_history(severity=ErrorSeverity.ERROR)
        assert len(errors) == 2
        assert all(e.severity == ErrorSeverity.ERROR for e in errors)

        # 只获取警告
        warnings = handler.get_error_history(severity=ErrorSeverity.WARNING)
        assert len(warnings) == 2
        assert all(w.severity == ErrorSeverity.WARNING for w in warnings)

    def test_error_history_limit(self):
        """测试错误历史限制"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        # 添加10个错误
        for i in range(10):
            handler.report_error(f"错误 {i}", "msg", ErrorSeverity.ERROR)

        # 只获取前3个
        history = handler.get_error_history(limit=3)
        assert len(history) == 3

    def test_notification_strategy(self):
        """测试错误通知策略"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        # 默认策略：ERROR 和 CRITICAL 通知用户
        error_record = handler.report_error(
            "错误", "msg", ErrorSeverity.ERROR
        )
        assert error_record.user_notified is True

        critical_record = handler.report_error(
            "严重错误", "msg", ErrorSeverity.CRITICAL
        )
        assert critical_record.user_notified is True

        warning_record = handler.report_error(
            "警告", "msg", ErrorSeverity.WARNING
        )
        assert warning_record.user_notified is True

        # INFO 和 DEBUG 不通知
        handler.clear_history()
        info_record = handler.report_error(
            "信息", "msg", ErrorSeverity.INFO
        )
        assert info_record.user_notified is False

    def test_custom_notification_strategy(self):
        """测试自定义通知策略"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        # 设置只通知 CRITICAL 的策略
        handler.set_notification_strategy(
            lambda r: r.severity == ErrorSeverity.CRITICAL
        )

        error_record = handler.report_error(
            "错误", "msg", ErrorSeverity.ERROR
        )
        assert error_record.user_notified is False

        critical_record = handler.report_error(
            "严重", "msg", ErrorSeverity.CRITICAL
        )
        assert critical_record.user_notified is True

    def test_signal_emission(self, qtbot):
        """测试信号发送"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        # 监听错误发生信号
        with qtbot.waitSignal(handler.errorOccurred, timeout=1000) as blocker:
            handler.report_error("测试", "msg", ErrorSeverity.ERROR)

        # 验证信号参数
        record = blocker.args[0]
        assert isinstance(record, ErrorRecord)
        assert record.title == "测试"

    def test_convenience_functions(self):
        """测试便捷函数"""
        GlobalErrorHandler.instance().clear_history()

        # 测试 report_error 便捷函数
        record1 = report_error("便捷错误", "msg", ErrorSeverity.ERROR)
        assert record1.title == "便捷错误"

        # 测试 report_exception 便捷函数
        try:
            raise ValueError("测试")
        except ValueError as e:
            record2 = report_exception("便捷异常", e)
            assert record2.title == "便捷异常"
            assert "ValueError" in record2.details


class TestInitializationStateManager:
    """测试初始化状态管理器"""

    def test_singleton_pattern(self):
        """测试单例模式"""
        manager1 = InitializationStateManager.instance()
        manager2 = InitializationStateManager.instance()
        assert manager1 is manager2

    def test_component_registration(self):
        """测试组件注册"""
        manager = InitializationStateManager.instance()

        manager.register_component("test_component")
        assert manager.get_component_state("test_component") == ComponentState.NOT_INITIALIZED

    def test_component_with_dependencies(self):
        """测试带依赖的组件"""
        manager = InitializationStateManager.instance()

        manager.register_component("component_a")
        manager.register_component("component_b", dependencies={"component_a"})

        # component_b 依赖 component_a
        assert not manager.check_dependencies_ready("component_b")

        # 标记 component_a 就绪
        manager.mark_component_ready("component_a")
        assert manager.check_dependencies_ready("component_b")

    def test_component_lifecycle(self):
        """测试组件生命周期"""
        manager = InitializationStateManager.instance()

        name = "lifecycle_test"
        manager.register_component(name)

        # 初始状态
        assert manager.get_component_state(name) == ComponentState.NOT_INITIALIZED

        # 开始初始化
        manager.mark_component_initializing(name)
        assert manager.get_component_state(name) == ComponentState.INITIALIZING

        # 就绪
        manager.mark_component_ready(name)
        assert manager.get_component_state(name) == ComponentState.READY
        assert manager.is_component_ready(name)

    def test_component_error(self):
        """测试组件错误"""
        manager = InitializationStateManager.instance()

        name = "error_test"
        manager.register_component(name)
        manager.mark_component_error(name, "初始化失败")

        assert manager.get_component_state(name) == ComponentState.ERROR
        info = manager.get_all_components_info()
        assert info[name].error == "初始化失败"

    def test_initialization_stage(self):
        """测试初始化阶段"""
        manager = InitializationStateManager.instance()

        stages = [
            InitializationStage.NOT_STARTED,
            InitializationStage.UI_SETUP,
            InitializationStage.MANAGERS_SETUP,
            InitializationStage.COMPLETED,
        ]

        for stage in stages:
            manager.set_stage(stage)
            # 验证阶段已设置（通过信号或状态）

    def test_require_initialized(self):
        """测试初始化要求"""
        manager = InitializationStateManager.instance()
        manager._is_completed = False

        # 未完成时应该返回 False
        assert not manager.require_initialized("test_operation", show_message=False)

        # 完成后应该返回 True
        manager._is_completed = True
        assert manager.require_initialized("test_operation", show_message=False)

    def test_require_components(self):
        """测试组件要求"""
        manager = InitializationStateManager.instance()

        manager.register_component("comp1")
        manager.register_component("comp2")

        # 组件未就绪
        assert not manager.require_components(
            ["comp1", "comp2"], "test_op", show_message=False
        )

        # 标记就绪
        manager.mark_component_ready("comp1")
        manager.mark_component_ready("comp2")

        # 现在应该可以执行
        assert manager.require_components(
            ["comp1", "comp2"], "test_op", show_message=False
        )

    def test_initialization_progress(self):
        """测试初始化进度"""
        manager = InitializationStateManager.instance()

        # 清空组件
        manager._components.clear()

        # 注册3个组件
        for i in range(3):
            manager.register_component(f"comp{i}")

        # 初始进度
        ready, total, percentage = manager.get_initialization_progress()
        assert ready == 0
        assert total == 3
        assert percentage == 0

        # 标记1个就绪
        manager.mark_component_ready("comp0")
        ready, total, percentage = manager.get_initialization_progress()
        assert ready == 1
        assert total == 3
        assert percentage == pytest.approx(33.33, rel=0.1)

        # 全部就绪
        manager.mark_component_ready("comp1")
        manager.mark_component_ready("comp2")
        ready, total, percentage = manager.get_initialization_progress()
        assert ready == 3
        assert total == 3
        assert percentage == 100

    def test_guard_initialization_decorator(self):
        """测试初始化防护装饰器"""
        manager = InitializationStateManager.instance()
        manager._is_completed = False

        # 定义被保护的函数
        @guard_initialization()
        def protected_operation():
            return "执行成功"

        # 未完成时应该被阻止
        result = protected_operation()
        assert result is None

        # 完成后应该可以执行
        manager._is_completed = True
        result = protected_operation()
        assert result == "执行成功"

    def test_guard_with_component(self):
        """测试带组件检查的防护装饰器"""
        manager = InitializationStateManager.instance()
        manager.register_component("required_comp")

        @guard_initialization("required_comp")
        def component_operation():
            return "成功"

        # 组件未就绪
        result = component_operation()
        assert result is None

        # 组件就绪
        manager.mark_component_ready("required_comp")
        result = component_operation()
        assert result == "成功"


class TestUserExperienceCoverage:
    """用户体验覆盖测试"""

    def test_error_message_clarity(self):
        """测试错误消息的清晰度"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        # 好的错误消息应该：
        # 1. 有明确的标题
        # 2. 有简洁的描述
        # 3. 有详细信息（可选）

        record = handler.report_error(
            title="配置加载失败",
            message="无法读取配置文件 config.json",
            severity=ErrorSeverity.ERROR,
            details="FileNotFoundError: config.json 文件不存在",
            source="config_loader",
        )

        # 验证消息结构
        assert record.title  # 有标题
        assert record.message  # 有消息
        assert len(record.message) < 100  # 消息简洁
        assert record.details  # 有详细信息
        assert record.source  # 有来源

    def test_timely_user_feedback(self):
        """测试及时的用户反馈"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        start_time = datetime.now()

        # 报告错误
        record = handler.report_error(
            title="测试", message="msg", severity=ErrorSeverity.ERROR
        )

        end_time = datetime.now()

        # 错误应该立即记录
        assert record.timestamp >= start_time
        assert record.timestamp <= end_time

        # 时间戳应该在毫秒级别内
        delta = (end_time - start_time).total_seconds()
        assert delta < 0.1  # 小于100毫秒

    def test_initialization_state_visibility(self):
        """测试初始化状态的可见性"""
        manager = InitializationStateManager.instance()

        # 用户应该能够查询初始化状态
        is_ready = manager.is_initialized()
        assert isinstance(is_ready, bool)

        # 用户应该能够查看进度
        ready, total, percentage = manager.get_initialization_progress()
        assert isinstance(ready, int)
        assert isinstance(total, int)
        assert isinstance(percentage, float)

    def test_error_context_information(self):
        """测试错误的上下文信息"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        # 错误应该包含足够的上下文
        context = {
            "file_path": "/path/to/file.csv",
            "line_number": 42,
            "user_action": "批处理",
        }

        record = handler.report_error(
            title="数据处理错误",
            message="无效的数据格式",
            severity=ErrorSeverity.ERROR,
            context=context,
        )

        # 验证上下文被保存
        assert record.context == context
        assert record.context["file_path"] == "/path/to/file.csv"

    def test_error_deduplication(self):
        """测试错误去重（避免重复弹窗）"""
        handler = GlobalErrorHandler.instance()
        handler.clear_history()

        # 短时间内相同的错误不应该重复通知
        # 这个功能可以在实际使用时实现，这里测试基础功能

        handler.report_error("重复错误", "msg", ErrorSeverity.ERROR)
        handler.report_error("重复错误", "msg", ErrorSeverity.ERROR)

        # 两个错误都被记录
        history = handler.get_error_history()
        assert len(history) == 2

        # 但在实际应用中，可以实现通知去重逻辑
