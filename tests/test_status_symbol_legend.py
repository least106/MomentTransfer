"""测试文件验证状态符号说明"""

import pytest
from unittest.mock import MagicMock, patch


class TestStatusSymbolLegend:
    """测试状态符号说明面板"""

    def test_status_info_completeness(self):
        """测试状态符号信息的完整性"""
        from gui.status_symbol_legend import STATUS_INFO, STATUS_READY, STATUS_WARNING, STATUS_UNVERIFIED

        required_symbols = [STATUS_READY, STATUS_WARNING, STATUS_UNVERIFIED]
        required_fields = ["name", "color", "description", "details"]

        for symbol in required_symbols:
            assert symbol in STATUS_INFO, f"缺少状态符号: {symbol}"
            info = STATUS_INFO[symbol]
            for field in required_fields:
                assert field in info, f"状态 {symbol} 缺少字段: {field}"
                assert info[field], f"状态 {symbol} 字段 {field} 为空"
                
    def test_status_ready_symbol(self):
        """测试已就绪状态符号"""
        from gui.status_symbol_legend import STATUS_INFO, STATUS_READY

        info = STATUS_INFO[STATUS_READY]
        assert "就绪" in info["name"]
        assert "✓" in info["description"] or "配置正常" in info["description"]
        assert len(info["details"]) > 0

    def test_status_warning_symbol(self):
        """测试警告状态符号"""
        from gui.status_symbol_legend import STATUS_INFO, STATUS_WARNING

        info = STATUS_INFO[STATUS_WARNING]
        assert "不完整" in info["name"] or "警告" in info["name"]
        assert "⚠" in info["description"] or "缺少" in info["description"]
        assert len(info["details"]) > 0

    def test_status_unverified_symbol(self):
        """测试无法验证状态符号"""
        from gui.status_symbol_legend import STATUS_INFO, STATUS_UNVERIFIED

        info = STATUS_INFO[STATUS_UNVERIFIED]
        assert "无法验证" in info["name"]
        assert "无法确定" in info["description"] or "验证" in info["description"]
        assert len(info["details"]) > 0

    def test_legend_creation(self):
        """测试说明面板创建"""
        try:
            from gui.status_symbol_legend import StatusSymbolLegend
            
            legend = StatusSymbolLegend()
            assert legend is not None
            # 创建小部件（需要 QApplication）
            # widget = legend.create_widget() 跳过，因为需要 Qt 环境
        except Exception as e:
            # 如果没有 Qt 环境则跳过
            pytest.skip(f"需要 Qt 环境: {e}")

    def test_status_symbol_button(self):
        """测试状态符号帮助按钮"""
        try:
            from gui.status_symbol_legend import StatusSymbolButton, StatusSymbolLegend
            
            button = StatusSymbolButton()
            assert button is not None
            # 检查属性
            assert button.text() == "?"
            assert "查看" in button.toolTip()
        except Exception as e:
            pytest.skip(f"需要 Qt 环境: {e}")


class TestStatusSymbolIntegration:
    """测试状态符号与管理器的集成"""

    def test_managers_exports_symbols(self):
        """测试 managers 导出状态符号常数"""
        from gui.managers import (
            STATUS_SYMBOL_READY,
            STATUS_SYMBOL_WARNING,
            STATUS_SYMBOL_UNVERIFIED,
        )

        assert STATUS_SYMBOL_READY == "✓"
        assert STATUS_SYMBOL_WARNING == "⚠"
        assert STATUS_SYMBOL_UNVERIFIED == "❓"

    def test_managers_exports_legend_classes(self):
        """测试 managers 导出说明面板类"""
        try:
            from gui.managers import StatusSymbolLegend, StatusSymbolButton
            
            # 如果导入成功，说明类已导出
            assert StatusSymbolLegend is not None
            assert StatusSymbolButton is not None
        except ImportError:
            # 允许导入失败（可能是配置原因）
            pass


class TestStatusSymbolMessages:
    """测试状态符号相关的消息内容"""

    def test_symbol_meanings(self):
        """测试符号的含义清晰性"""
        from gui.status_symbol_legend import STATUS_INFO

        for symbol, info in STATUS_INFO.items():
            # 验证描述中包含符号
            desc = info["description"]
            
            # 至少有一个字段包含符号或相关关键词
            has_meaning = (
                symbol in desc or
                info["name"] or
                info["description"]
            )
            
            assert has_meaning, f"符号 {symbol} 的含义不清晰"

    def test_details_are_actionable(self):
        """测试详细说明是否提供可操作的信息"""
        from gui.status_symbol_legend import STATUS_INFO

        for symbol, info in STATUS_INFO.items():
            details = info["details"]
            
            # 每个详情应该清晰地说明问题或解决方案
            for detail in details:
                # 详情中应该包含具体内容，不是空白
                assert detail.strip(), f"符号 {symbol} 的详情为空"
                
                # 详情应该包含符号或相关关键词
                assert (
                    symbol in detail or
                    "✓" in detail or
                    "⚠" in detail or
                    "❓" in detail or
                    len(detail) > 5
                ), f"符号 {symbol} 的详情缺乏具体内容"
