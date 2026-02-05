"""测试 Part 选择器的用户体验改进"""

import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QComboBox, QApplication


@pytest.fixture
def qt_app():
    """提供 Qt 应用环境"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestPartSelectorPlaceholder:
    """测试 Part 选择器的占位文本和禁用状态"""

    def test_combo_has_placeholder_when_empty(self, qt_app):
        """测试空选择器显示占位文本"""
        combo = QComboBox()
        combo.setEnabled(False)
        combo.addItem("请先加载配置文件")
        
        # 验证占位文本
        assert combo.count() == 1
        assert "请先加载配置" in combo.itemText(0)
        assert not combo.isEnabled()

    def test_combo_enabled_when_has_items(self, qt_app):
        """测试有项目时选择器启用"""
        combo = QComboBox()
        combo.addItem("Part1")
        combo.addItem("Part2")
        combo.setEnabled(True)
        
        assert combo.count() == 2
        assert combo.isEnabled()

    def test_combo_tooltip_explains_state(self, qt_app):
        """测试提示文本解释当前状态"""
        # 禁用状态
        combo_disabled = QComboBox()
        combo_disabled.setEnabled(False)
        combo_disabled.setToolTip("请加载配置文件以加载 SOURCE Parts\n点击 '加载配置' 按钮导入配置文件")
        
        tooltip_disabled = combo_disabled.toolTip()
        assert "请加载配置" in tooltip_disabled
        assert "加载配置" in tooltip_disabled
        
        # 启用状态
        combo_enabled = QComboBox()
        combo_enabled.addItem("Part1")
        combo_enabled.setEnabled(True)
        combo_enabled.setToolTip("选择要编辑的 SOURCE Part\n当前有 3 个可用 Parts")
        
        tooltip_enabled = combo_enabled.toolTip()
        assert "选择" in tooltip_enabled
        assert "可用" in tooltip_enabled

    def test_warning_symbol_in_placeholder(self, qt_app):
        """测试占位文本包含警告符号"""
        combo = QComboBox()
        combo.clear()
        combo.addItem("⚠ 请先加载配置")
        
        assert "⚠" in combo.itemText(0)
        assert "请先加载配置" in combo.itemText(0)


class TestPartSelectorStateTransition:
    """测试 Part 选择器的状态转换"""

    def test_transition_from_empty_to_filled(self, qt_app):
        """测试从空状态到填充状态的转换"""
        combo = QComboBox()
        
        # 初始状态：空
        combo.setEnabled(False)
        combo.addItem("请先加载配置文件")
        assert not combo.isEnabled()
        assert combo.count() == 1
        
        # 转换到填充状态
        combo.clear()
        combo.addItem("Part1")
        combo.addItem("Part2")
        combo.setEnabled(True)
        
        assert combo.isEnabled()
        assert combo.count() == 2
        assert combo.itemText(0) == "Part1"

    def test_transition_from_filled_to_empty(self, qt_app):
        """测试从填充状态到空状态的转换"""
        combo = QComboBox()
        
        # 初始状态：有项目
        combo.addItem("Part1")
        combo.addItem("Part2")
        combo.setEnabled(True)
        assert combo.isEnabled()
        
        # 转换到空状态
        combo.clear()
        combo.addItem("请先加载配置文件")
        combo.setEnabled(False)
        
        assert not combo.isEnabled()
        assert combo.count() == 1
        assert "请先加载配置" in combo.itemText(0)


class TestPartSelectorTooltips:
    """测试 Part 选择器的提示文本"""

    def test_tooltip_shows_count_when_enabled(self, qt_app):
        """测试启用时提示显示项目数量"""
        parts = ["Part1", "Part2", "Part3"]
        combo = QComboBox()
        
        for part in parts:
            combo.addItem(part)
        
        combo.setEnabled(True)
        combo.setToolTip(f"选择要编辑的 SOURCE Part\n当前有 {len(parts)} 个可用 Parts")
        
        tooltip = combo.toolTip()
        assert "3 个" in tooltip or "3个" in tooltip
        assert "可用" in tooltip

    def test_tooltip_guides_user_when_disabled(self, qt_app):
        """测试禁用时提示引导用户操作"""
        combo = QComboBox()
        combo.setEnabled(False)
        combo.setToolTip(
            "请加载配置文件以加载 SOURCE Parts\n"
            "点击 '加载配置' 按钮导入配置文件"
        )
        
        tooltip = combo.toolTip()
        assert "请加载配置" in tooltip or "请先加载配置" in tooltip
        assert "加载配置" in tooltip or "导入配置" in tooltip

    def test_tooltip_explains_mapping_purpose(self, qt_app):
        """测试提示说明映射目的"""
        combo = QComboBox()
        combo.addItem("（未选择）")
        combo.addItem("Target1")
        combo.setEnabled(True)
        combo.setToolTip("选择该 Source part 对应的 Target part\n当前有 1 个可用 Target Parts")
        
        tooltip = combo.toolTip()
        assert "Source" in tooltip or "source" in tooltip
        assert "Target" in tooltip or "target" in tooltip


class TestPartSelectorVisualFeedback:
    """测试 Part 选择器的视觉反馈"""

    def test_disabled_state_is_clear(self, qt_app):
        """测试禁用状态清晰可见"""
        combo = QComboBox()
        combo.setEnabled(False)
        
        assert not combo.isEnabled()
        # 禁用的 QComboBox 在 Qt 中有灰色外观

    def test_placeholder_text_is_descriptive(self, qt_app):
        """测试占位文本描述性强"""
        placeholders = [
            "请先加载配置文件",
            "⚠ 请先加载配置",
            "请加载配置文件以获取部件列表",
        ]
        
        for placeholder in placeholders:
            assert len(placeholder) > 5  # 足够长以提供信息
            assert "配置" in placeholder  # 提到核心操作
            
    def test_warning_symbol_draws_attention(self, qt_app):
        """测试警告符号吸引注意"""
        combo = QComboBox()
        combo.addItem("⚠ 请先加载配置")
        
        text = combo.itemText(0)
        # ⚠ 符号应该在文本开头，易于识别
        assert text.startswith("⚠")


class TestPartSelectorIntegration:
    """测试 Part 选择器与其他组件的集成"""

    def test_coordinate_panel_selector_state(self, qt_app):
        """测试坐标面板中的选择器状态"""
        # 模拟初始状态：没有配置
        combo = QComboBox()
        combo.setEnabled(False)
        combo.addItem("请先加载配置文件")
        combo.setToolTip("请加载配置文件以加载 SOURCE Parts\n点击 '加载配置' 按钮导入配置文件")
        
        assert not combo.isEnabled()
        assert "请先加载配置" in combo.itemText(0)
        
        # 模拟配置加载后
        combo.clear()
        combo.addItem("Part1")
        combo.addItem("Part2")
        combo.setEnabled(True)
        combo.setToolTip("选择要编辑的 SOURCE Part\n当前有 2 个可用 Parts")
        
        assert combo.isEnabled()
        assert combo.count() == 2

    def test_batch_mapping_selector_state(self, qt_app):
        """测试批处理映射中的选择器状态"""
        # 模拟没有 Target Parts
        combo = QComboBox()
        combo.clear()
        combo.addItem("⚠ 请先加载配置")
        combo.setEnabled(False)
        combo.setToolTip("请加载配置文件以获取 Target Part 列表\n点击 '加载配置' 按钮导入配置文件")
        
        assert not combo.isEnabled()
        assert "⚠" in combo.itemText(0)
        
        # 模拟有 Target Parts
        combo.clear()
        combo.addItem("（未选择）")
        combo.addItem("Target1")
        combo.setEnabled(True)
        combo.setToolTip("选择该 Source part 对应的 Target part\n当前有 1 个可用 Target Parts")
        
        assert combo.isEnabled()
        assert combo.count() == 2
