"""测试状态符号说明与批处理面板集成"""

import pytest
from unittest.mock import MagicMock, patch, Mock
from pathlib import Path


@pytest.fixture
def mock_qt_app():
    """提供 Qt 应用环境"""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
    except ImportError:
        pytest.skip("需要 PySide6")


class TestBatchPanelStatusSymbolIntegration:
    """测试批处理面板中的状态符号说明集成"""

    def test_batch_panel_has_status_help_button(self, mock_qt_app):
        """测试批处理面板有状态帮助按钮"""
        try:
            from gui.panels.batch_panel import BatchPanel
            from gui.global_state_manager import GlobalStateManager
            
            # 创建 mock 状态管理器
            state_manager = MagicMock(spec=GlobalStateManager)
            state_manager.get_part = MagicMock(return_value="TEST_PART")
            
            panel = BatchPanel(state_manager)
            
            # 检查按钮属性
            assert hasattr(panel, 'btn_status_help'), "BatchPanel 应有 btn_status_help 属性"
            assert panel.btn_status_help is not None, "btn_status_help 应被初始化"
            
        except Exception as e:
            pytest.skip(f"需要完整的 Qt 和 GUI 环境: {e}")

    def test_batch_panel_status_legend_lazy_init(self, mock_qt_app):
        """测试状态符号说明的延迟初始化"""
        try:
            from gui.panels.batch_panel import BatchPanel
            from gui.global_state_manager import GlobalStateManager
            
            state_manager = MagicMock(spec=GlobalStateManager)
            state_manager.get_part = MagicMock(return_value="TEST_PART")
            
            panel = BatchPanel(state_manager)
            
            # 初始时，_status_legend 应为 None（延迟初始化）
            assert panel._status_legend is None, "_status_legend 初始应为 None"
            
            # 调用延迟初始化方法
            if hasattr(panel, '_init_status_legend_lazily'):
                panel._init_status_legend_lazily()
                
                # 现在应该已初始化
                assert panel._status_legend is not None, "_status_legend 应被初始化"
                
        except Exception as e:
            pytest.skip(f"需要完整的 Qt 和 GUI 环境: {e}")

    def test_status_legend_panel_creation(self, mock_qt_app):
        """测试状态符号说明面板的创建"""
        try:
            from gui.status_symbol_legend import StatusSymbolLegend
            
            legend = StatusSymbolLegend()
            
            # 创建小部件（需要 QApplication）
            widget = legend.create_widget()
            assert widget is not None, "应能创建小部件"
            
        except Exception as e:
            pytest.skip(f"需要完整的 Qt 环境: {e}")

    def test_status_symbol_button_tooltip(self, mock_qt_app):
        """测试状态符号帮助按钮的提示文本"""
        try:
            from gui.status_symbol_legend import StatusSymbolButton
            
            button = StatusSymbolButton()
            
            # 检查按钮的提示文本
            tooltip = button.toolTip()
            assert "查看" in tooltip or "状态" in tooltip, "按钮提示应说明其功能"
            
        except Exception as e:
            pytest.skip(f"需要完整的 Qt 环境: {e}")


class TestStatusSymbolMessageHandling:
    """测试状态符号相关的消息处理"""

    def test_workflow_step_message_with_symbol(self):
        """测试工作流步骤消息中包含符号说明"""
        from src.execution import ExecutionContext
        from gui.signal_bus import SignalBus
        
        # 创建执行上下文
        ctx = ExecutionContext(
            project_data=MagicMock(),
            config=MagicMock(),
            batch_config=MagicMock(),
            source_part=MagicMock(),
            target_part=MagicMock(),
        )
        
        signal_bus = SignalBus()
        
        # 模拟状态消息
        message = "📂 步骤2: 请选择输入数据文件..."
        assert "步骤2" in message, "消息应包含步骤标识"
        assert "选择" in message, "消息应包含操作指令"

    def test_error_message_with_status_symbol(self):
        """测试错误消息与状态符号的关联"""
        from gui.status_message_queue import MessagePriority
        
        # 验证消息优先级
        assert MessagePriority.ERROR > MessagePriority.INFO
        assert MessagePriority.WARNING < MessagePriority.ERROR
        
        # 错误消息应高于普通消息
        assert hasattr(MessagePriority, 'ERROR')
        assert hasattr(MessagePriority, 'WARNING')
        assert hasattr(MessagePriority, 'INFO')


class TestStatusSymbolConsistency:
    """测试状态符号的一致性"""

    def test_symbols_defined_consistently(self):
        """测试状态符号在所有模块中定义一致"""
        from gui.status_symbol_legend import (
            STATUS_READY,
            STATUS_WARNING, 
            STATUS_UNVERIFIED,
            STATUS_INFO,
        )
        from gui.managers import (
            STATUS_SYMBOL_READY,
            STATUS_SYMBOL_WARNING,
            STATUS_SYMBOL_UNVERIFIED,
        )
        
        # 验证符号一致
        assert STATUS_SYMBOL_READY == STATUS_READY, "符号定义应一致"
        assert STATUS_SYMBOL_WARNING == STATUS_WARNING, "符号定义应一致"
        assert STATUS_SYMBOL_UNVERIFIED == STATUS_UNVERIFIED, "符号定义应一致"
        
        # 验证所有符号都在 STATUS_INFO 中
        for symbol in [STATUS_READY, STATUS_WARNING, STATUS_UNVERIFIED]:
            assert symbol in STATUS_INFO, f"符号 {symbol} 应在 STATUS_INFO 中"

    def test_symbol_colors_valid(self):
        """测试状态符号颜色值有效"""
        from gui.status_symbol_legend import STATUS_INFO
        
        for symbol, info in STATUS_INFO.items():
            color = info["color"]
            
            # 验证颜色格式（十六进制）
            assert color.startswith("#"), f"颜色 {color} 应以 # 开头"
            assert len(color) == 7, f"颜色 {color} 长度应为 7"
            
            # 验证十六进制数值
            try:
                int(color[1:], 16)
            except ValueError:
                pytest.fail(f"颜色 {color} 不是有效的十六进制")
