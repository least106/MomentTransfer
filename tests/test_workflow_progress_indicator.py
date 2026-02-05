"""测试批处理工作流进度指示器"""

import pytest
from unittest.mock import MagicMock, patch


class TestWorkflowProgressIndicator:
    """测试工作流进度指示器"""

    def test_create_widget(self):
        """测试创建进度指示器小部件"""
        from gui.workflow_progress_indicator import WorkflowProgressIndicator

        indicator = WorkflowProgressIndicator()
        widget = indicator.create_widget()
        
        assert widget is not None
        # 再次调用应该返回同一个小部件
        widget2 = indicator.create_widget()
        assert widget is widget2

    def test_step_progression(self):
        """测试步骤进度"""
        from gui.workflow_progress_indicator import WorkflowProgressIndicator

        indicator = WorkflowProgressIndicator()
        
        # 初始状态
        assert indicator.get_current_step() == "init"
        assert not indicator.is_ready_to_process()
        
        # 进行到步骤1
        indicator.update_step("step1")
        assert indicator.get_current_step() == "step1"
        assert not indicator.is_ready_to_process()
        
        # 进行到步骤2
        indicator.update_step("step2")
        assert indicator.get_current_step() == "step2"
        assert not indicator.is_ready_to_process()
        
        # 进行到步骤3
        indicator.update_step("step3")
        assert indicator.get_current_step() == "step3"
        assert indicator.is_ready_to_process()

    def test_step_display_name(self):
        """测试步骤显示名称"""
        from gui.workflow_progress_indicator import WorkflowProgressIndicator

        assert "初始化" in WorkflowProgressIndicator.get_step_display_name("init")
        assert "步骤1" in WorkflowProgressIndicator.get_step_display_name("step1")
        assert "步骤2" in WorkflowProgressIndicator.get_step_display_name("step2")
        assert "步骤3" in WorkflowProgressIndicator.get_step_display_name("step3")

    def test_step_instruction(self):
        """测试步骤操作指令"""
        from gui.workflow_progress_indicator import WorkflowProgressIndicator

        instruction = WorkflowProgressIndicator.get_step_instruction("step1")
        assert "配置" in instruction or "加载" in instruction

    def test_batch_manager_integration(self):
        """测试 BatchManager 与进度指示器集成"""
        from gui.batch_manager import BatchManager

        gui = MagicMock()
        gui.batch_panel = MagicMock()
        gui.batch_panel.set_workflow_step = MagicMock()

        manager = BatchManager(gui)

        # 验证进度指示器已初始化
        assert hasattr(manager, "_progress_indicator")

        # 验证可以获取进度指示器小部件
        widget = manager.get_workflow_progress_indicator()
        # 小部件可能为 None（如果 QApplication 不存在），但方法应该能运行
        # 不抛异常就说明集成正确

    def test_workflow_steps_completeness(self):
        """测试工作流步骤定义完整性"""
        from gui.workflow_progress_indicator import WORKFLOW_STEPS

        required_steps = ["init", "step1", "step2", "step3"]
        required_fields = ["display", "description", "instruction", "next_step"]

        for step in required_steps:
            assert step in WORKFLOW_STEPS, f"缺少步骤: {step}"
            step_info = WORKFLOW_STEPS[step]
            for field in required_fields:
                assert field in step_info, f"步骤 {step} 缺少字段: {field}"
                assert step_info[field], f"步骤 {step} 字段 {field} 为空"


class TestBatchPanelWorkflowSteps:
    """测试批处理面板工作流步骤"""

    def test_workflow_step_transitions(self):
        """测试工作流步骤转换提示"""
        # 这个测试需要 Qt 环境，跳过单独的集成测试
        # 实际测试应在完整 GUI 环境中进行

        from gui.workflow_progress_indicator import WORKFLOW_STEPS

        # 验证步骤转换链
        step = "init"
        visited = set()

        while step not in visited:
            visited.add(step)
            assert step in WORKFLOW_STEPS
            step = WORKFLOW_STEPS[step].get("next_step", "ready")
            if step == "ready":
                break

        # 应该访问至少 init, step1, step2, step3
        assert "init" in visited
        assert "step1" in visited
        assert "step2" in visited
        assert "step3" in visited
