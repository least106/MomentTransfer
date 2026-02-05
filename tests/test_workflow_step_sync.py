"""
测试批处理工作流步骤与 UI 同步问题。

问题 9：批处理的步骤导引（Workflow Step）与实际 UI 同步问题
- 确保所有改变文件选择的操作都更新 workflow step
- 确保快速选择完成后正确设置 workflow step
- 确保用户看到的状态栏提示与实际流程步骤一致
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from gui.batch_manager import BatchManager


class TestWorkflowStepTracking:
    """工作流步骤追踪测试"""

    def test_batch_manager_initializes_with_init_step(self):
        """测试 BatchManager 初始化为 init 步骤"""
        gui = MagicMock()
        manager = BatchManager(gui)

        assert manager._current_workflow_step == "init"

    def test_set_workflow_step_updates_current_step(self):
        """测试 _set_workflow_step 正确更新当前步骤"""
        gui = MagicMock()
        gui.batch_panel = None  # 模拟不存在 batch_panel

        manager = BatchManager(gui)
        assert manager._current_workflow_step == "init"

        manager._set_workflow_step("step1")
        assert manager._current_workflow_step == "step1"

        manager._set_workflow_step("step2")
        assert manager._current_workflow_step == "step2"

        manager._set_workflow_step("step3")
        assert manager._current_workflow_step == "step3"

    def test_set_workflow_step_forwards_to_batch_panel(self):
        """测试 _set_workflow_step 转发到 BatchPanel"""
        gui = MagicMock()
        bp = MagicMock()
        gui.batch_panel = bp

        manager = BatchManager(gui)
        manager._set_workflow_step("step2")

        # 验证 BatchPanel 的 set_workflow_step 被调用
        bp.set_workflow_step.assert_called_once_with("step2")

    def test_set_workflow_step_handles_missing_batch_panel(self):
        """测试 _set_workflow_step 在 batch_panel 缺失时不崩溃"""
        gui = MagicMock()
        gui.batch_panel = None

        manager = BatchManager(gui)
        # 不应抛出异常
        manager._set_workflow_step("step2")
        assert manager._current_workflow_step == "step2"

    def test_set_workflow_step_strips_whitespace(self):
        """测试 _set_workflow_step 去除空白"""
        gui = MagicMock()
        gui.batch_panel = None

        manager = BatchManager(gui)
        manager._set_workflow_step("  step2  ")
        assert manager._current_workflow_step == "step2"

    def test_set_workflow_step_handles_batch_panel_exception(self):
        """测试 _set_workflow_step 在 batch_panel 抛出异常时继续工作"""
        gui = MagicMock()
        bp = MagicMock()
        bp.set_workflow_step.side_effect = RuntimeError("模拟 batch_panel 错误")
        gui.batch_panel = bp

        manager = BatchManager(gui)
        # 不应抛出异常，应该继续工作
        manager._set_workflow_step("step2")
        assert manager._current_workflow_step == "step2"

    def test_workflow_step_none_defaults_to_init(self):
        """测试传入 None 步骤默认为 init"""
        gui = MagicMock()
        gui.batch_panel = None

        manager = BatchManager(gui)
        manager._set_workflow_step(None)
        assert manager._current_workflow_step == "init"

    def test_workflow_step_empty_string_defaults_to_init(self):
        """测试传入空字符串步骤默认为 init"""
        gui = MagicMock()
        gui.batch_panel = None

        manager = BatchManager(gui)
        manager._set_workflow_step("")
        assert manager._current_workflow_step == "init"


class TestWorkflowStepStepSequence:
    """工作流步骤顺序测试"""

    def test_workflow_step_state_transitions(self):
        """测试正常的工作流步骤转换序列"""
        gui = MagicMock()
        gui.batch_panel = None

        manager = BatchManager(gui)

        # 初始状态
        assert manager._current_workflow_step == "init"

        # 转换到 step1（选择文件）
        manager._set_workflow_step("step1")
        assert manager._current_workflow_step == "step1"

        # 转换到 step2（文件列表选择）
        manager._set_workflow_step("step2")
        assert manager._current_workflow_step == "step2"

        # 转换到 step3（配置选择）
        manager._set_workflow_step("step3")
        assert manager._current_workflow_step == "step3"

        # 回到 step1（重新选择文件）
        manager._set_workflow_step("step1")
        assert manager._current_workflow_step == "step1"

    def test_workflow_step_persistence_across_calls(self):
        """测试工作流步骤在多次调用间的持久性"""
        gui = MagicMock()
        gui.batch_panel = None

        manager = BatchManager(gui)

        # 设置为 step2
        manager._set_workflow_step("step2")
        assert manager._current_workflow_step == "step2"

        # 调用其他方法不应改变步骤
        try:
            manager._collect_files_for_scan(Path("."))
        except Exception:
            pass

        # 步骤应保持不变
        assert manager._current_workflow_step == "step2"


class TestWorkflowStepBatchPanelIntegration:
    """workflow step 与 BatchPanel 集成测试"""

    def test_batch_panel_set_workflow_step_called_with_correct_step(self):
        """测试 BatchPanel.set_workflow_step 被正确的步骤调用"""
        gui = MagicMock()
        bp = MagicMock()
        gui.batch_panel = bp

        manager = BatchManager(gui)

        steps = ["init", "step1", "step2", "step3"]
        for step in steps:
            bp.reset_mock()
            manager._set_workflow_step(step)
            bp.set_workflow_step.assert_called_once_with(step)

    def test_batch_panel_exception_doesnt_prevent_tracking(self):
        """测试 BatchPanel 异常不影响步骤追踪"""
        gui = MagicMock()
        bp = MagicMock()
        bp.set_workflow_step.side_effect = Exception("模拟异常")
        gui.batch_panel = bp

        manager = BatchManager(gui)

        manager._set_workflow_step("step2")
        manager._set_workflow_step("step3")

        # 即使 batch_panel 异常，步骤仍应被追踪
        assert manager._current_workflow_step == "step3"


class TestWorkflowStepErrorRecovery:
    """工作流步骤异常恢复测试"""

    def test_multiple_workflow_step_changes_with_errors(self):
        """测试在错误情况下的多次工作流步骤变更"""
        gui = MagicMock()
        bp = MagicMock()
        # 第一次失败，第二次成功，第三次失败
        bp.set_workflow_step.side_effect = [
            Exception("错误1"),
            None,
            Exception("错误2"),
        ]
        gui.batch_panel = bp

        manager = BatchManager(gui)

        # 第一次调用（失败）
        manager._set_workflow_step("step1")
        assert manager._current_workflow_step == "step1"

        # 第二次调用（成功）
        manager._set_workflow_step("step2")
        assert manager._current_workflow_step == "step2"

        # 第三次调用（失败）
        manager._set_workflow_step("step3")
        assert manager._current_workflow_step == "step3"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
