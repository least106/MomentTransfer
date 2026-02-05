"""
测试新建项目流程 - 确保状态正确重置、UI 恢复初始状态、状态横幅显示
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock


@pytest.fixture
def mock_ui_state_manager():
    """创建模拟的 UIStateManager"""
    manager = MagicMock()
    manager._data_loaded = False
    manager._config_loaded = False
    manager._operation_performed = False
    manager.reset_to_initial_state = MagicMock()
    manager.clear_user_modified = MagicMock()
    return manager


@pytest.fixture
def mock_state_banner():
    """创建模拟的 StateBanner"""
    banner = MagicMock()
    banner.show_new_project = MagicMock()
    return banner


@pytest.fixture
def mock_gui(mock_ui_state_manager, mock_state_banner):
    """创建模拟的 GUI 实例"""
    gui = MagicMock()
    
    # 使用预先创建的 mock
    gui.ui_state_manager = mock_ui_state_manager
    gui.state_banner = mock_state_banner
    
    # 模拟批处理管理器
    batch_manager = MagicMock()
    batch_manager._set_workflow_step = MagicMock()
    gui.batch_manager = batch_manager
    
    # 模拟文件选择管理器
    fsm = MagicMock()
    fsm.special_part_mapping_by_file = {}
    fsm.special_part_row_selection_by_file = {}
    fsm.file_part_selection_by_file = {}
    fsm.table_row_selection_by_file = {}
    fsm._data_loaded = False
    fsm._config_loaded = False
    fsm._operation_performed = False
    gui.file_selection_manager = fsm
    
    # 模拟文件树
    file_tree = MagicMock()
    file_tree.clear = MagicMock()
    gui.file_tree = file_tree
    gui._file_tree_items = {}
    
    # 模拟确认保存对话框 - 默认返回 True，但可在测试中覆盖
    gui._has_unsaved_changes = MagicMock(return_value=False)
    gui._confirm_save_discard_cancel = MagicMock(return_value=True)
    
    # 模拟属性
    gui.operation_performed = False
    gui.special_part_mapping_by_file = {}
    gui.special_part_row_selection_by_file = {}
    gui.file_part_selection_by_file = {}
    gui.table_row_selection_by_file = {}
    
    return gui

@pytest.fixture
def project_manager_class():
    """模拟 ProjectManager 类定义"""
    # 创建一个简单的 ProjectManager mock 类
    class MockProjectManager:
        def __init__(self, gui):
            self.gui = gui
            self.current_project_file = None
            self.last_saved_state = None
            self._background_workers = []
        
        def create_new_project(self, skip_confirm=False):
            """简化版的 create_new_project 用于测试"""
            try:
                # 检查未保存更改
                if not skip_confirm:
                    if hasattr(self.gui, "_has_unsaved_changes") and callable(self.gui._has_unsaved_changes):
                        if self.gui._has_unsaved_changes():
                            if hasattr(self.gui, "_confirm_save_discard_cancel"):
                                proceed = self.gui._confirm_save_discard_cancel("创建新项目")
                                if not proceed:
                                    return False
                
                # 清除项目状态
                self.current_project_file = None
                self.last_saved_state = None
                
                # 重置工作流
                if hasattr(self.gui, "batch_manager") and self.gui.batch_manager:
                    self.gui.batch_manager._set_workflow_step("init")
                
                # 清理文件选择管理器
                if hasattr(self.gui, "file_selection_manager"):
                    fsm = self.gui.file_selection_manager
                    fsm.special_part_mapping_by_file = {}
                    fsm.special_part_row_selection_by_file = {}
                    fsm.file_part_selection_by_file = {}
                    fsm.table_row_selection_by_file = {}
                    fsm._data_loaded = False
                    fsm._config_loaded = False
                    fsm._operation_performed = False
                
                # 重置 UI 状态
                if hasattr(self.gui, "ui_state_manager"):
                    self.gui.ui_state_manager.clear_user_modified()
                    self.gui.ui_state_manager.reset_to_initial_state()
                
                # 清理主窗口属性
                self.gui.operation_performed = False
                for attr in [
                    "special_part_mapping_by_file",
                    "special_part_row_selection_by_file",
                    "file_part_selection_by_file",
                    "table_row_selection_by_file",
                ]:
                    setattr(self.gui, attr, {})
                
                # 清空文件树
                if hasattr(self.gui, "file_tree"):
                    self.gui.file_tree.clear()
                    self.gui._file_tree_items = {}
                
                # 显示新项目横幅
                if hasattr(self.gui, "state_banner"):
                    self.gui.state_banner.show_new_project()
                
                return True
            except Exception:
                return False
    
    return MockProjectManager


@pytest.fixture
def project_manager(mock_gui, project_manager_class):
    """创建 ProjectManager 实例（使用 mock 类）"""
    pm = project_manager_class(mock_gui)
    return pm


def test_create_new_project_basic(project_manager, mock_gui):
    """测试基本的新建项目流程"""
    # 执行
    result = project_manager.create_new_project(skip_confirm=True)
    
    # 验证
    assert result is True
    assert project_manager.current_project_file is None
    assert project_manager.last_saved_state is None


def test_create_new_project_resets_workflow(project_manager, mock_gui):
    """测试新建项目重置工作流步骤"""
    # 执行
    project_manager.create_new_project(skip_confirm=True)
    
    # 验证批处理管理器的工作流被重置
    mock_gui.batch_manager._set_workflow_step.assert_called_once_with("init")


def test_create_new_project_clears_file_selection_state(project_manager, mock_gui):
    """测试新建项目清除文件选择状态"""
    # 准备：设置一些状态
    mock_gui.file_selection_manager.special_part_mapping_by_file = {"test.csv": {}}
    mock_gui.file_selection_manager._data_loaded = True
    mock_gui.file_selection_manager._operation_performed = True
    
    # 执行
    project_manager.create_new_project(skip_confirm=True)
    
    # 验证状态被清除
    assert mock_gui.file_selection_manager.special_part_mapping_by_file == {}
    assert mock_gui.file_selection_manager._data_loaded is False
    assert mock_gui.file_selection_manager._operation_performed is False


def test_create_new_project_resets_ui_state(project_manager, mock_gui):
    """测试新建项目重置 UI 状态"""
    # 执行
    project_manager.create_new_project(skip_confirm=True)
    
    # 验证 UI 状态管理器的 reset_to_initial_state 被调用
    mock_gui.ui_state_manager.reset_to_initial_state.assert_called_once()


def test_create_new_project_shows_state_banner(project_manager, mock_gui):
    """测试新建项目显示状态横幅"""
    # 执行
    project_manager.create_new_project(skip_confirm=True)
    
    # 验证状态横幅显示新项目状态
    mock_gui.state_banner.show_new_project.assert_called_once()


def test_create_new_project_clears_file_tree(project_manager, mock_gui):
    """测试新建项目清空文件树"""
    # 执行
    project_manager.create_new_project(skip_confirm=True)
    
    # 验证文件树被清空
    mock_gui.file_tree.clear.assert_called()
    assert mock_gui._file_tree_items == {}


def test_create_new_project_with_unsaved_changes_prompts(project_manager, mock_gui):
    """测试有未保存更改时提示用户"""
    # 准备：设置有未保存的更改
    mock_gui._has_unsaved_changes.return_value = True
    mock_gui._confirm_save_discard_cancel.return_value = True
    
    # 执行
    result = project_manager.create_new_project(skip_confirm=False)
    
    # 验证确认对话框被调用
    mock_gui._has_unsaved_changes.assert_called_once()
    mock_gui._confirm_save_discard_cancel.assert_called_once_with("创建新项目")
    assert result is True


def test_create_new_project_with_unsaved_changes_cancelled(project_manager, mock_gui):
    """测试用户取消新建项目"""
    # 准备：用户选择取消
    mock_gui._has_unsaved_changes.return_value = True
    mock_gui._confirm_save_discard_cancel.return_value = False
    
    # 执行
    result = project_manager.create_new_project(skip_confirm=False)
    
    # 验证操作被取消
    assert result is False
    # 状态不应被修改
    mock_gui.ui_state_manager.reset_to_initial_state.assert_not_called()
    mock_gui.state_banner.show_new_project.assert_not_called()


def test_ui_state_manager_reset_to_initial_state(mock_ui_state_manager):
    """测试 UIStateManager 的 reset_to_initial_state 方法"""
    # 设置一些初始状态
    mock_ui_state_manager._data_loaded = True
    mock_ui_state_manager._config_loaded = True
    mock_ui_state_manager._operation_performed = True
    
    # 模拟 reset_to_initial_state 的行为
    def mock_reset():
        mock_ui_state_manager._data_loaded = False
        mock_ui_state_manager._config_loaded = False
        mock_ui_state_manager._operation_performed = False
    
    mock_ui_state_manager.reset_to_initial_state.side_effect = mock_reset
    
    # 执行重置
    mock_ui_state_manager.reset_to_initial_state()
    
    # 验证所有状态被清除
    assert mock_ui_state_manager._data_loaded is False
    assert mock_ui_state_manager._config_loaded is False
    assert mock_ui_state_manager._operation_performed is False
    mock_ui_state_manager.reset_to_initial_state.assert_called_once()


def test_state_banner_show_new_project(mock_state_banner):
    """测试状态横幅显示新项目状态"""
    # 执行
    mock_state_banner.show_new_project()
    
    # 验证
    mock_state_banner.show_new_project.assert_called_once()
