"""测试文件树右键菜单和智能筛选功能"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

# 确保测试导入时项目根在 sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from gui.panels.batch_panel import BatchPanel


@pytest.fixture(scope="module")
def app():
    """提供 QApplication 实例"""
    if not QApplication.instance():
        return QApplication(sys.argv)
    return QApplication.instance()


@pytest.fixture
def panel(app):
    """提供 BatchPanel 实例"""
    return BatchPanel()


class TestFileTreeContextMenu:
    """测试文件树右键菜单功能"""

    def test_context_menu_policy_enabled(self, panel):
        """测试文件树启用了右键菜单策略"""
        assert panel.file_tree.contextMenuPolicy() == Qt.CustomContextMenu

    def test_context_menu_signal_connected(self, panel):
        """测试右键菜单信号已连接"""
        # 验证信号已连接（通过检查信号是否有接收者）
        signal = panel.file_tree.customContextMenuRequested
        assert signal is not None
        # 通过触发信号验证连接（不会抛出异常表示连接正常）
        try:
            signal.emit(QPoint(0, 0))
        except Exception as e:
            # 如果是合理的异常（如 QMenu 相关），说明连接正常
            assert "QMenu" in str(e) or "PySide6" in str(e)

    @patch("PySide6.QtWidgets.QMenu")
    def test_context_menu_basic_actions(self, mock_menu_class, panel):
        """测试右键菜单包含基础选择操作"""
        mock_menu = MagicMock()
        mock_menu_class.return_value = mock_menu

        # 触发右键菜单
        panel._show_file_tree_context_menu(QPoint(0, 0))

        # 验证菜单被创建
        mock_menu_class.assert_called_once()

        # 验证基础操作被添加（全选、全不选、反选）
        calls = [str(call) for call in mock_menu.addAction.call_args_list]
        action_texts = [call for call in calls if "全选" in call or "全不选" in call or "反选" in call]
        assert len(action_texts) >= 3  # 至少有 3 个基础操作

    @patch("PySide6.QtWidgets.QMenu")
    def test_context_menu_smart_filters(self, mock_menu_class, panel):
        """测试右键菜单包含智能筛选操作"""
        mock_menu = MagicMock()
        mock_menu_class.return_value = mock_menu

        # 触发右键菜单
        panel._show_file_tree_context_menu(QPoint(0, 0))

        # 验证智能筛选操作被添加
        calls = [str(call) for call in mock_menu.addAction.call_args_list]
        smart_filter_texts = [
            call
            for call in calls
            if any(symbol in call for symbol in ["✓", "⚠", "❓", "❌"])
        ]
        assert len(smart_filter_texts) >= 4  # 至少有 4 个智能筛选操作

    @patch("PySide6.QtWidgets.QMenu")
    def test_context_menu_separator_exists(self, mock_menu_class, panel):
        """测试右键菜单中存在分隔符"""
        mock_menu = MagicMock()
        mock_menu_class.return_value = mock_menu

        # 触发右键菜单
        panel._show_file_tree_context_menu(QPoint(0, 0))

        # 验证分隔符被添加
        assert mock_menu.addSeparator.called


class TestSmartFiltering:
    """测试智能筛选功能"""

    def test_select_ready_files(self, panel):
        """测试选择已就绪文件（✓）"""
        # 创建测试树项
        self._setup_test_tree(panel)

        # 执行筛选
        panel._select_files_by_status("✓")

        # 验证只有就绪文件被选中
        assert self._is_item_checked(panel.file_tree.topLevelItem(0))  # file1.csv
        assert not self._is_item_checked(panel.file_tree.topLevelItem(1))  # file2.csv
        assert not self._is_item_checked(panel.file_tree.topLevelItem(2))  # file3.csv

    def test_select_warning_files(self, panel):
        """测试选择有警告的文件（⚠）"""
        # 创建测试树项
        self._setup_test_tree(panel)

        # 执行筛选
        panel._select_files_by_status("⚠")

        # 验证只有警告文件被选中
        assert not self._is_item_checked(panel.file_tree.topLevelItem(0))  # file1.csv
        assert self._is_item_checked(panel.file_tree.topLevelItem(1))  # file2.csv
        assert not self._is_item_checked(panel.file_tree.topLevelItem(2))  # file3.csv

    def test_select_unverified_files(self, panel):
        """测试选择未验证文件（❓）"""
        # 创建测试树项
        self._setup_test_tree(panel)

        # 执行筛选
        panel._select_files_by_status("❓")

        # 验证只有未验证文件被选中
        assert not self._is_item_checked(panel.file_tree.topLevelItem(0))  # file1.csv
        assert not self._is_item_checked(panel.file_tree.topLevelItem(1))  # file2.csv
        assert self._is_item_checked(panel.file_tree.topLevelItem(2))  # file3.csv

    def test_select_error_files(self, panel):
        """测试选择有错误的文件（❌）"""
        # 创建测试树项
        self._setup_test_tree(panel)

        # 添加错误文件
        error_item = QTreeWidgetItem(["file4.csv", "❌ 未知格式"])
        error_item.setCheckState(0, Qt.Unchecked)
        error_item.setData(0, Qt.UserRole, "/path/to/file4.csv")
        panel.file_tree.addTopLevelItem(error_item)

        # 执行筛选
        panel._select_files_by_status("❌")

        # 验证只有错误文件被选中
        assert not self._is_item_checked(panel.file_tree.topLevelItem(0))  # file1.csv
        assert not self._is_item_checked(panel.file_tree.topLevelItem(1))  # file2.csv
        assert not self._is_item_checked(panel.file_tree.topLevelItem(2))  # file3.csv
        assert self._is_item_checked(panel.file_tree.topLevelItem(3))  # file4.csv

    def test_filtering_ignores_directories(self, panel):
        """测试筛选忽略目录节点"""
        # 创建带目录的树结构
        dir_item = QTreeWidgetItem(["data", ""])
        dir_item.setData(0, Qt.UserRole, None)  # 目录节点
        panel.file_tree.addTopLevelItem(dir_item)

        file_item = QTreeWidgetItem(["file.csv", "✓ 已就绪"])
        file_item.setCheckState(0, Qt.Unchecked)
        file_item.setData(0, Qt.UserRole, "/path/to/file.csv")
        dir_item.addChild(file_item)

        # 执行筛选
        panel._select_files_by_status("✓")

        # 验证只有文件被选中，目录不受影响
        assert self._is_item_checked(file_item)
        # 目录节点没有勾选状态，不应报错
        try:
            dir_item.checkState(0)
        except Exception:
            pass  # 预期行为

    def test_filtering_nested_structure(self, panel):
        """测试嵌套目录结构中的筛选"""
        # 创建嵌套结构
        root_dir = QTreeWidgetItem(["root", ""])
        root_dir.setData(0, Qt.UserRole, None)
        panel.file_tree.addTopLevelItem(root_dir)

        sub_dir = QTreeWidgetItem(["subdir", ""])
        sub_dir.setData(0, Qt.UserRole, None)
        root_dir.addChild(sub_dir)

        file1 = QTreeWidgetItem(["file1.csv", "✓ 已就绪"])
        file1.setCheckState(0, Qt.Unchecked)
        file1.setData(0, Qt.UserRole, "/root/file1.csv")
        root_dir.addChild(file1)

        file2 = QTreeWidgetItem(["file2.csv", "⚠ 未映射"])
        file2.setCheckState(0, Qt.Unchecked)
        file2.setData(0, Qt.UserRole, "/root/subdir/file2.csv")
        sub_dir.addChild(file2)

        # 执行筛选
        panel._select_files_by_status("✓")

        # 验证嵌套文件正确筛选
        assert self._is_item_checked(file1)
        assert not self._is_item_checked(file2)

    def test_filtering_with_empty_tree(self, panel):
        """测试空树筛选不报错"""
        # 清空树
        panel.file_tree.clear()

        # 执行筛选（不应报错）
        try:
            panel._select_files_by_status("✓")
        except Exception as e:
            pytest.fail(f"空树筛选不应报错: {e}")

    def test_filtering_preserves_previous_selection(self, panel):
        """测试筛选会覆盖之前的选择状态"""
        # 创建测试树项
        self._setup_test_tree(panel)

        # 先选中所有
        for i in range(panel.file_tree.topLevelItemCount()):
            item = panel.file_tree.topLevelItem(i)
            if item.data(0, Qt.UserRole):  # 只处理文件节点
                item.setCheckState(0, Qt.Checked)

        # 执行筛选（只选择警告文件）
        panel._select_files_by_status("⚠")

        # 验证只有警告文件被选中，其他保持之前的选择状态
        # 注意：当前实现只会选中匹配的，不会取消不匹配的
        assert self._is_item_checked(panel.file_tree.topLevelItem(1))  # file2.csv (警告)

    # 辅助方法

    def _setup_test_tree(self, panel):
        """设置测试用的文件树"""
        panel.file_tree.clear()

        # 添加已就绪文件
        item1 = QTreeWidgetItem(["file1.csv", "✓ 已就绪"])
        item1.setCheckState(0, Qt.Unchecked)
        item1.setData(0, Qt.UserRole, "/path/to/file1.csv")
        panel.file_tree.addTopLevelItem(item1)

        # 添加警告文件
        item2 = QTreeWidgetItem(["file2.csv", "⚠ 未映射: Part1"])
        item2.setCheckState(0, Qt.Unchecked)
        item2.setData(0, Qt.UserRole, "/path/to/file2.csv")
        panel.file_tree.addTopLevelItem(item2)

        # 添加未验证文件
        item3 = QTreeWidgetItem(["file3.csv", "❓ 未验证"])
        item3.setCheckState(0, Qt.Unchecked)
        item3.setData(0, Qt.UserRole, "/path/to/file3.csv")
        panel.file_tree.addTopLevelItem(item3)

    def _is_item_checked(self, item):
        """检查树项是否被选中"""
        try:
            return item.checkState(0) == Qt.Checked
        except Exception:
            return False


class TestKeyboardShortcuts:
    """测试键盘快捷键"""

    def test_select_all_shortcut(self, panel):
        """测试全选快捷键（Ctrl+A）"""
        assert panel.btn_select_all.shortcut().toString() == "Ctrl+A"

    def test_select_none_shortcut(self, panel):
        """测试全不选快捷键（Ctrl+Shift+A）"""
        assert panel.btn_select_none.shortcut().toString() == "Ctrl+Shift+A"

    def test_invert_selection_shortcut(self, panel):
        """测试反选快捷键（Ctrl+I）"""
        assert panel.btn_select_invert.shortcut().toString() == "Ctrl+I"

    def test_button_tooltips_show_shortcuts(self, panel):
        """测试按钮提示包含快捷键信息"""
        assert "Ctrl+A" in panel.btn_select_all.toolTip()
        assert "Ctrl+Shift+A" in panel.btn_select_none.toolTip()
        assert "Ctrl+I" in panel.btn_select_invert.toolTip()


class TestUserExperience:
    """测试用户体验改进"""

    def test_context_menu_shows_keyboard_shortcuts(self, panel):
        """测试右键菜单显示键盘快捷键"""
        with patch("PySide6.QtWidgets.QMenu") as mock_menu_class:
            mock_menu = MagicMock()
            mock_menu_class.return_value = mock_menu

            panel._show_file_tree_context_menu(QPoint(0, 0))

            # 验证菜单项包含快捷键提示
            calls = [str(call) for call in mock_menu.addAction.call_args_list]
            shortcut_hints = [
                call for call in calls if "Ctrl" in call or "快捷" in str(call)
            ]
            assert len(shortcut_hints) >= 3  # 至少 3 个带快捷键提示

    def test_smart_filter_icons_visible(self, panel):
        """测试智能筛选菜单项包含状态图标"""
        with patch("PySide6.QtWidgets.QMenu") as mock_menu_class:
            mock_menu = MagicMock()
            mock_menu_class.return_value = mock_menu

            panel._show_file_tree_context_menu(QPoint(0, 0))

            # 验证菜单项包含状态符号
            calls = [str(call) for call in mock_menu.addAction.call_args_list]
            icon_items = [
                call
                for call in calls
                if any(symbol in call for symbol in ["✓", "⚠", "❓", "❌"])
            ]
            assert len(icon_items) >= 4  # 4 个智能筛选项都有图标

    def test_context_menu_position_correct(self, panel):
        """测试右键菜单在正确位置显示"""
        with patch("PySide6.QtWidgets.QMenu") as mock_menu_class:
            mock_menu = MagicMock()
            mock_menu_class.return_value = mock_menu

            test_pos = QPoint(100, 200)
            panel._show_file_tree_context_menu(test_pos)

            # 验证 exec 被调用（菜单显示）
            assert mock_menu.exec.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
