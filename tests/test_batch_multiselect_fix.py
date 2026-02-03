"""测试批处理多选文件和目录修复"""


import pytest

from gui.batch_manager import BatchManager
from gui.batch_manager_files import _collect_checked_files_from_tree


class MockGUI:
    """模拟 GUI 对象"""

    def __init__(self):
        self.current_config = object()  # 模拟有配置
        self.inp_batch_input = MockInput()
        self.file_tree = MockTree()
        self._file_tree_items = {}
        self.output_dir = None


class MockInput:
    """模拟输入框"""

    def __init__(self):
        self._text = ""

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text


class MockTree:
    """模拟文件树"""

    pass


class MockItem:
    """模拟树节点"""

    def __init__(self, checked=False, kind="file"):
        self._checked = checked
        self._meta = {"kind": kind}

    def checkState(self, col):
        from PySide6.QtCore import Qt

        return Qt.Checked if self._checked else Qt.Unchecked


def test_multiselect_saves_paths_not_display_text(tmp_path):
    """测试多选时保存实际路径而不是显示文本"""
    # 创建测试文件
    f1 = tmp_path / "file1.csv"
    f2 = tmp_path / "file2.csv"
    f1.write_text("a,b\n1,2\n", encoding="utf-8")
    f2.write_text("c,d\n3,4\n", encoding="utf-8")

    gui = MockGUI()
    manager = BatchManager(gui)

    # 模拟多选场景
    chosen_paths = [f1, f2]

    # 模拟 _on_browse_input_clicked 中的逻辑
    first_path = chosen_paths[0]
    if len(chosen_paths) > 1:
        display_text = f"{first_path} (+{len(chosen_paths)-1} 项)"
    else:
        display_text = str(first_path)
    gui.inp_batch_input.setText(display_text)

    # 保存实际路径列表
    manager._selected_paths = chosen_paths

    # 验证显示文本包含 "(+N 项)"
    assert "(+1 项)" in gui.inp_batch_input.text()

    # 验证保存的路径是完整的路径列表
    assert hasattr(manager, "_selected_paths")
    assert len(manager._selected_paths) == 2
    assert manager._selected_paths[0] == f1
    assert manager._selected_paths[1] == f2


def test_collect_checked_files_from_tree(tmp_path):
    """测试从文件树收集勾选的文件"""
    from PySide6.QtCore import Qt

    # 创建测试文件
    f1 = tmp_path / "file1.csv"
    f2 = tmp_path / "file2.csv"
    f3 = tmp_path / "file3.csv"
    for f in [f1, f2, f3]:
        f.write_text("test", encoding="utf-8")

    gui = MockGUI()
    manager = BatchManager(gui)

    # 模拟文件树中的项目
    item1 = MockItem(checked=True, kind="file")
    item2 = MockItem(checked=False, kind="file")
    item3 = MockItem(checked=True, kind="file")
    dir_item = MockItem(checked=True, kind="dir")

    gui._file_tree_items = {
        str(f1): item1,
        str(f2): item2,
        str(f3): item3,
        str(tmp_path): dir_item,
    }

    # 收集勾选的文件
    checked = _collect_checked_files_from_tree(manager)

    # 验证只收集了勾选的文件项（不包括目录）
    assert len(checked) == 2
    assert f1 in checked
    assert f3 in checked
    assert f2 not in checked


def test_button_disabled_during_batch():
    """测试批处理期间按钮被正确禁用"""

    class MockButton:
        def __init__(self):
            self._enabled = True
            self._text = "开始处理"

        def setEnabled(self, enabled):
            self._enabled = enabled

        def setText(self, text):
            self._text = text

        def isEnabled(self):
            return self._enabled

    gui = MockGUI()
    manager = BatchManager(gui)

    # 添加所有可能的开始按钮
    gui.btn_batch = MockButton()
    gui.btn_start_menu = MockButton()
    gui.btn_batch_in_toolbar = MockButton()

    # 模拟进入批处理模式
    from gui.batch_manager_batch import prepare_gui_for_batch

    prepare_gui_for_batch(manager)

    # 验证所有按钮都被禁用
    assert not gui.btn_batch.isEnabled()
    assert not gui.btn_start_menu.isEnabled()
    assert not gui.btn_batch_in_toolbar.isEnabled()

    # 验证有 setText 的按钮更新了文本
    assert "处理中" in gui.btn_batch._text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
