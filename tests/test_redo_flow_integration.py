"""
测试重做流程的完整集成
验证：全局状态管理器 -> batch_manager -> 历史记录 树结构
"""

import sys
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def reset_state_manager():
    """每个测试前后重置状态管理器"""
    from gui.global_state_manager import GlobalStateManager
    
    sm = GlobalStateManager.instance()
    sm.reset()
    yield
    sm.reset()


class TestRedoFlowIntegration:
    """测试重做流程的完整集成"""

    def test_redo_state_manager_integration(self):
        """测试重做状态管理器与 batch_manager 的集成"""
        from gui.global_state_manager import GlobalStateManager, AppState
        
        # 创建状态管理器
        sm = GlobalStateManager.instance()
        
        # 验证初始状态
        assert sm.current_state == AppState.NORMAL
        assert not sm.is_redo_mode
        
        # 进入重做模式
        test_parent_id = "parent_record_123"
        test_record = {"input_path": "test.csv", "id": test_parent_id}
        
        sm.set_redo_mode(test_parent_id, test_record)
        
        # 验证重做模式状态
        assert sm.current_state == AppState.REDO_MODE
        assert sm.is_redo_mode
        assert sm.redo_parent_id == test_parent_id
        
        # 在重做模式下进行项目加载 - 应该自动清除重做状态
        sm.set_loading_project("/some/project.json")
        
        assert sm.current_state == AppState.PROJECT_LOADING
        assert not sm.is_redo_mode
        assert sm.redo_parent_id is None
        
        # 重置状态
        sm.reset()
        assert sm.current_state == AppState.NORMAL

    def test_batch_manager_has_state_manager(self):
        """测试 batch_manager 已与全局状态管理器集成"""
        from gui.batch_manager import BatchManager
        from gui.global_state_manager import GlobalStateManager
        from PySide6.QtWidgets import QApplication, QMainWindow
        
        # 创建最小化的主窗口
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        main_window = QMainWindow()
        main_window.statusBar()
        
        # 创建 batch_manager
        batch_manager = BatchManager(main_window)
        
        # 验证 batch_manager 有 _state_manager
        assert batch_manager._state_manager is not None
        assert hasattr(batch_manager, "_redo_mode_parent_id")
        
        # 验证有 _on_redo_mode_changed 方法
        assert hasattr(batch_manager, "_on_redo_mode_changed")
        assert callable(batch_manager._on_redo_mode_changed)

    def test_exit_redo_mode_on_batch_completion(self):
        """测试批处理完成时退出重做模式"""
        from gui.batch_manager import BatchManager
        from gui.global_state_manager import GlobalStateManager, AppState
        from PySide6.QtWidgets import QApplication, QMainWindow
        from unittest.mock import MagicMock, patch
        
        # 创建 app 和窗口
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        main_window = QMainWindow()
        main_window.statusBar()
        
        # 创建 batch_manager
        batch_manager = BatchManager(main_window)
        
        # 设置状态管理器
        sm = GlobalStateManager.instance()
        
        # 进入重做模式
        parent_id = "parent_record_999"
        sm.set_redo_mode(parent_id, {"id": parent_id})
        
        # 模拟批处理完成
        with patch.object(batch_manager, "_record_batch_history"):
            with patch.object(batch_manager, "_restore_gui_after_batch"):
                with patch.object(batch_manager.gui, "statusBar", return_value=MagicMock()):
                    with patch("gui.signal_bus.SignalBus") as mock_signal_bus:
                        # 模拟 SignalBus.instance()
                        mock_bus = MagicMock()
                        mock_signal_bus.instance.return_value = mock_bus
                        
                        batch_manager.on_batch_finished("✓ 处理完成")
        
        # 验证已退出重做模式
        assert sm.current_state == AppState.NORMAL
        assert not sm.is_redo_mode
        assert batch_manager._redo_mode_parent_id is None

    def test_state_banner_signal_callback(self):
        """测试状态横幅的信号回调"""
        from gui.batch_manager import BatchManager
        from gui.global_state_manager import GlobalStateManager
        from PySide6.QtWidgets import QApplication, QMainWindow
        from unittest.mock import MagicMock
        
        # 创建 app 和窗口
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        main_window = QMainWindow()
        main_window.statusBar()
        
        # 创建 batch_manager
        batch_manager = BatchManager(main_window)
        
        # 模拟状态横幅
        mock_banner = MagicMock()
        main_window.state_banner = mock_banner
        
        # 测试进入重做模式时的回调
        batch_manager._on_redo_mode_changed(is_entering=True, record_id="test_123")
        
        # 验证没有显示横幅（因为在 _on_redo_mode_changed 中只是记录日志）
        # 实际的显示应该在 redo_history_record 中
        
        # 测试退出重做模式时的回调
        batch_manager._on_redo_mode_changed(is_entering=False, record_id="test_123")
        
        # 验证清除了横幅
        mock_banner.clear.assert_called()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
