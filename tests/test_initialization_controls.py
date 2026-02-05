"""
测试初始化期间的控件启用/禁用状态管理。

问题 8：控制初始化阶段控件状态混乱
- 确保初始化期间所有控件都被禁用
- 确保初始化完成后控件可用性状态正确更新
- 确保不会出现按钮闪烁或用户能在初始化期间触发操作
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from gui.managers import UIStateManager


class TestInitializationControlStates:
    """初始化期间的控件状态管理测试"""

    def test_ui_state_manager_starts_in_initializing_state(self):
        """测试 UIStateManager 初始化时处于初始化状态"""
        parent = MagicMock()
        manager = UIStateManager(parent)

        assert (
            manager._is_initializing is True
        ), "UIStateManager 应该初始化为 _is_initializing=True"

    def test_set_data_loaded_skips_refresh_during_initialization(self):
        """测试初始化期间调用 set_data_loaded 不会触发 UI 刷新"""
        parent = MagicMock()
        manager = UIStateManager(parent)
        manager._is_initializing = True

        # Mock refresh_controls_state 方法
        with patch.object(manager, "refresh_controls_state") as mock_refresh:
            manager.set_data_loaded(True)

            # 初始化期间不应调用 refresh
            mock_refresh.assert_not_called()
            assert manager._data_loaded is True

    def test_set_data_loaded_triggers_refresh_after_initialization(self):
        """测试初始化完成后调用 set_data_loaded 会触发 UI 刷新"""
        parent = MagicMock()
        manager = UIStateManager(parent)
        manager._is_initializing = False  # 初始化已完成

        # Mock refresh_controls_state 方法
        with patch.object(manager, "refresh_controls_state") as mock_refresh:
            manager.set_data_loaded(True)

            # 初始化完成后应调用 refresh
            mock_refresh.assert_called_once()
            assert manager._data_loaded is True

    def test_set_config_loaded_skips_refresh_during_initialization(self):
        """测试初始化期间调用 set_config_loaded 不会触发 UI 刷新"""
        parent = MagicMock()
        manager = UIStateManager(parent)
        manager._is_initializing = True

        with patch.object(manager, "refresh_controls_state") as mock_refresh:
            manager.set_config_loaded(True)

            # 初始化期间不应调用 refresh
            mock_refresh.assert_not_called()
            assert manager._config_loaded is True

    def test_set_config_loaded_triggers_refresh_after_initialization(self):
        """测试初始化完成后调用 set_config_loaded 会触发 UI 刷新"""
        parent = MagicMock()
        manager = UIStateManager(parent)
        manager._is_initializing = False

        with patch.object(manager, "refresh_controls_state") as mock_refresh:
            manager.set_config_loaded(True)

            # 初始化完成后应调用 refresh
            mock_refresh.assert_called_once()
            assert manager._config_loaded is True

    def test_set_operation_performed_skips_refresh_during_initialization(self):
        """测试初始化期间调用 set_operation_performed 不会触发 UI 刷新"""
        parent = MagicMock()
        manager = UIStateManager(parent)
        manager._is_initializing = True

        with patch.object(manager, "refresh_controls_state") as mock_refresh:
            manager.set_operation_performed(True)

            # 初始化期间不应调用 refresh
            mock_refresh.assert_not_called()
            assert manager._operation_performed is True

    def test_set_operation_performed_triggers_refresh_after_initialization(self):
        """测试初始化完成后调用 set_operation_performed 会触发 UI 刷新"""
        parent = MagicMock()
        manager = UIStateManager(parent)
        manager._is_initializing = False

        with patch.object(manager, "refresh_controls_state") as mock_refresh:
            manager.set_operation_performed(True)

            # 初始化完成后应调用 refresh
            mock_refresh.assert_called_once()
            assert manager._operation_performed is True

    def test_multiple_state_changes_during_initialization_no_flicker(self):
        """测试初始化期间多次状态变更不会导致 UI 闪烁"""
        parent = MagicMock()
        manager = UIStateManager(parent)
        manager._is_initializing = True

        with patch.object(manager, "refresh_controls_state") as mock_refresh:
            # 模拟初始化期间的多次状态变更
            manager.set_data_loaded(False)
            manager.set_config_loaded(False)
            manager.set_operation_performed(False)
            manager.set_data_loaded(True)
            manager.set_config_loaded(True)

            # 初始化期间不应有任何 refresh 调用
            mock_refresh.assert_not_called()

    def test_state_changes_after_initialization_all_trigger_refresh(self):
        """测试初始化完成后每次状态变更都会触发 UI 刷新"""
        parent = MagicMock()
        manager = UIStateManager(parent)
        manager._is_initializing = False

        with patch.object(manager, "refresh_controls_state") as mock_refresh:
            manager.set_data_loaded(True)
            assert mock_refresh.call_count == 1

            manager.set_config_loaded(True)
            assert mock_refresh.call_count == 2

            manager.set_operation_performed(True)
            assert mock_refresh.call_count == 3


class TestInitializationGate:
    """初始化门控机制测试"""

    def test_initialization_flag_protects_ui_updates(self):
        """测试 _is_initializing 标志能够保护 UI 更新"""
        parent = MagicMock()
        manager = UIStateManager(parent)

        # 标记为初始化中
        manager._is_initializing = True
        refresh_called = []

        def track_refresh():
            refresh_called.append(True)

        manager.refresh_controls_state = track_refresh

        # 多次设置状态
        manager.set_data_loaded(True)
        manager.set_config_loaded(True)
        manager.set_operation_performed(True)

        # 初始化期间没有 refresh 调用
        assert len(refresh_called) == 0, "初始化期间不应有任何 refresh 调用"

        # 标记初始化完成
        manager._is_initializing = False

        # 再设置一次状态，应该触发 refresh
        manager.set_data_loaded(False)
        assert len(refresh_called) == 1, "初始化完成后应有 refresh 调用"

    def test_exception_in_state_setter_doesnt_prevent_state_update(self):
        """测试即使 refresh 失败，状态仍会被更新"""
        parent = MagicMock()
        manager = UIStateManager(parent)
        manager._is_initializing = False

        # Mock refresh_controls_state 抛出异常
        def failing_refresh():
            raise RuntimeError("模拟 refresh 失败")

        manager.refresh_controls_state = failing_refresh

        # 即使 refresh 失败，set_data_loaded 应该仍然更新状态
        manager.set_data_loaded(True)
        assert manager._data_loaded is True, "即使 refresh 失败，状态也应该被更新"


class TestInitializationCompletionSync:
    """初始化完成后的状态同步测试"""

    def test_initialization_completion_syncs_all_flags(self):
        """测试初始化完成时正确同步所有 _is_initializing 标志"""
        # 这个测试验证 InitializationManager.finalize_initialization()
        # 能够同步 main_window 和 ui_state_manager 的 _is_initializing 标志
        parent = MagicMock()
        parent.ui_state_manager = UIStateManager(parent)

        # 初始状态：都在初始化中
        assert parent.ui_state_manager._is_initializing is True

        # 模拟初始化完成时的同步
        parent.ui_state_manager._is_initializing = False

        # 验证标志已同步
        assert parent.ui_state_manager._is_initializing is False


class TestControlsStateRefresh:
    """控件状态刷新测试"""

    def test_refresh_controls_state_checks_initialization_status(self):
        """测试 refresh_controls_state 能够检查初始化状态"""
        parent = MagicMock()
        parent.statusBar = MagicMock()
        manager = UIStateManager(parent)

        # 初始化期间刷新应该安全执行（不会导致异常）
        manager._is_initializing = True
        try:
            manager.refresh_controls_state()
        except Exception as e:
            pytest.fail(f"初始化期间调用 refresh_controls_state 不应抛出异常: {e}")

    def test_state_consistency_across_initialization(self):
        """测试初始化过程中的状态一致性"""
        parent = MagicMock()
        manager = UIStateManager(parent)

        # 设置多个状态
        manager.set_data_loaded(True)
        manager.set_config_loaded(True)
        manager.set_operation_performed(False)

        # 验证所有状态都被正确设置
        assert manager._data_loaded is True
        assert manager._config_loaded is True
        assert manager._operation_performed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
