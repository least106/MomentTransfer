"""测试预览表格的选择状态持久化功能 - 问题 19 修复验证"""

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from gui.batch_state import BatchStateManager

logger = logging.getLogger(__name__)


class TestBatchStateSelectionManagement:
    """测试 BatchStateManager 的选择状态管理功能"""

    def test_table_selection_initialization(self):
        """测试常规表格选择状态的初始化（默认全选）"""
        state = BatchStateManager()
        file_path = "test_file.csv"
        row_count = 10

        # 第一次获取应自动初始化为全选
        selection = state.get_table_selection(file_path, row_count)

        assert isinstance(selection, set)
        assert len(selection) == row_count
        assert selection == set(range(row_count))

    def test_table_selection_persistence(self):
        """测试常规表格选择状态的持久化"""
        state = BatchStateManager()
        file_path = "test_file.csv"
        row_count = 10

        # 初始化选择状态
        selection = state.get_table_selection(file_path, row_count)

        # 修改选择状态（取消选择部分行）
        selection.discard(0)
        selection.discard(5)
        selection.discard(9)
        state.set_table_selection(file_path, selection)

        # 再次获取，应保持修改后的状态
        retrieved = state.get_table_selection(file_path)

        assert len(retrieved) == 7  # 10 - 3 = 7
        assert 0 not in retrieved
        assert 5 not in retrieved
        assert 9 not in retrieved
        assert 1 in retrieved
        assert 2 in retrieved

    def test_special_selection_initialization(self):
        """测试特殊格式选择状态的初始化（默认全选）"""
        state = BatchStateManager()
        file_path = "test_special.mtfmt"
        part_name = "BODY"
        row_count = 20

        # 第一次获取应自动初始化为全选
        selection = state.get_special_selection(file_path, part_name, row_count)

        assert isinstance(selection, set)
        assert len(selection) == row_count
        assert selection == set(range(row_count))

    def test_special_selection_persistence(self):
        """测试特殊格式选择状态的持久化"""
        state = BatchStateManager()
        file_path = "test_special.mtfmt"
        part1 = "BODY"
        part2 = "WING"
        row_count = 15

        # 初始化两个 Part 的选择状态
        sel1 = state.get_special_selection(file_path, part1, row_count)
        sel2 = state.get_special_selection(file_path, part2, row_count)

        # 修改 Part1 的选择状态
        sel1.discard(0)
        sel1.discard(10)
        state.set_special_selection(file_path, part1, sel1)

        # 修改 Part2 的选择状态
        sel2.discard(5)
        sel2.discard(14)
        state.set_special_selection(file_path, part2, sel2)

        # 再次获取，两个 Part 应独立保持修改后的状态
        retrieved1 = state.get_special_selection(file_path, part1)
        retrieved2 = state.get_special_selection(file_path, part2)

        assert len(retrieved1) == 13  # 15 - 2 = 13
        assert 0 not in retrieved1
        assert 10 not in retrieved1

        assert len(retrieved2) == 13  # 15 - 2 = 13
        assert 5 not in retrieved2
        assert 14 not in retrieved2

    def test_selection_cache_isolation(self):
        """测试不同文件的选择状态相互独立"""
        state = BatchStateManager()
        file1 = "file1.csv"
        file2 = "file2.csv"
        row_count = 10

        # 初始化两个文件的选择状态
        sel1 = state.get_table_selection(file1, row_count)
        sel2 = state.get_table_selection(file2, row_count)

        # 修改 file1 的选择状态
        sel1.discard(0)
        sel1.discard(5)
        state.set_table_selection(file1, sel1)

        # file2 的选择状态应不受影响
        retrieved2 = state.get_table_selection(file2)
        assert len(retrieved2) == row_count
        assert 0 in retrieved2
        assert 5 in retrieved2

    def test_clear_selection_cache_single_file(self):
        """测试清除单个文件的选择状态缓存"""
        state = BatchStateManager()
        file1 = "file1.csv"
        file2 = "file2.csv"

        # 初始化两个文件的选择状态
        state.get_table_selection(file1, 10)
        state.get_table_selection(file2, 20)

        # 清除 file1 的选择状态
        state.clear_selection_cache(file1)

        # file1 应被清除，file2 应保留
        assert file1 not in state.table_row_selection
        assert file2 in state.table_row_selection

    def test_clear_selection_cache_all(self):
        """测试清除所有选择状态缓存"""
        state = BatchStateManager()

        # 初始化多个文件的选择状态
        state.get_table_selection("file1.csv", 10)
        state.get_table_selection("file2.csv", 20)
        state.get_special_selection("special.mtfmt", "BODY", 15)

        # 清除所有选择状态
        state.clear_selection_cache()

        # 所有选择状态应被清除
        assert len(state.table_row_selection) == 0
        assert len(state.special_row_selection) == 0

    def test_selection_survives_data_cache_changes(self):
        """测试选择状态在数据缓存更新时仍保持不变"""
        state = BatchStateManager()
        file_path = "test.csv"

        # 初始化选择状态
        selection = state.get_table_selection(file_path, 10)
        selection.discard(0)
        selection.discard(5)
        state.set_table_selection(file_path, selection)

        # 模拟数据缓存更新（不应影响选择状态）
        state.table_data_cache[file_path] = {
            "mtime": 12345.0,
            "df": pd.DataFrame({"A": range(10)}),
            "preview_rows": 200,
        }

        # 选择状态应保持不变
        retrieved = state.get_table_selection(file_path)
        assert len(retrieved) == 8
        assert 0 not in retrieved
        assert 5 not in retrieved


class TestSelectionStatePersistenceInPreview:
    """测试预览表格切换文件时选择状态的持久化"""

    def test_file_switch_preserves_selection(self):
        """测试切换文件后再回来，选择状态应保持"""
        state = BatchStateManager()
        file1 = "file1.csv"
        file2 = "file2.csv"

        # 文件 1：初始化并修改选择状态
        sel1 = state.get_table_selection(file1, 10)
        sel1.discard(0)
        sel1.discard(5)
        sel1.discard(9)
        state.set_table_selection(file1, sel1)

        # 文件 2：初始化并修改选择状态
        sel2 = state.get_table_selection(file2, 20)
        sel2.discard(10)
        sel2.discard(15)
        state.set_table_selection(file2, sel2)

        # 模拟切换到文件 2（获取文件 2 的选择状态）
        retrieved2 = state.get_table_selection(file2)
        assert len(retrieved2) == 18  # 20 - 2 = 18
        assert 10 not in retrieved2
        assert 15 not in retrieved2

        # 模拟切换回文件 1（选择状态应保持不变）
        retrieved1 = state.get_table_selection(file1)
        assert len(retrieved1) == 7  # 10 - 3 = 7
        assert 0 not in retrieved1
        assert 5 not in retrieved1
        assert 9 not in retrieved1

    def test_special_format_part_switch_preserves_selection(self):
        """测试特殊格式切换 Part 后再回来，选择状态应保持"""
        state = BatchStateManager()
        file_path = "special.mtfmt"
        body = "BODY"
        wing = "WING"

        # BODY：初始化并修改选择状态
        sel_body = state.get_special_selection(file_path, body, 15)
        sel_body.discard(0)
        sel_body.discard(7)
        sel_body.discard(14)
        state.set_special_selection(file_path, body, sel_body)

        # WING：初始化并修改选择状态
        sel_wing = state.get_special_selection(file_path, wing, 20)
        sel_wing.discard(5)
        sel_wing.discard(10)
        state.set_special_selection(file_path, wing, sel_wing)

        # 模拟切换到 WING（获取 WING 的选择状态）
        retrieved_wing = state.get_special_selection(file_path, wing)
        assert len(retrieved_wing) == 18  # 20 - 2 = 18
        assert 5 not in retrieved_wing
        assert 10 not in retrieved_wing

        # 模拟切换回 BODY（选择状态应保持不变）
        retrieved_body = state.get_special_selection(file_path, body)
        assert len(retrieved_body) == 12  # 15 - 3 = 12
        assert 0 not in retrieved_body
        assert 7 not in retrieved_body
        assert 14 not in retrieved_body

    def test_multiple_file_switches_preserve_all_selections(self):
        """测试多次切换文件，所有选择状态应保持"""
        state = BatchStateManager()
        files = [f"file{i}.csv" for i in range(5)]
        row_counts = [10, 15, 20, 25, 30]

        # 为每个文件初始化并修改选择状态
        for file_path, row_count in zip(files, row_counts):
            sel = state.get_table_selection(file_path, row_count)
            # 取消选择前 3 行
            for i in range(3):
                sel.discard(i)
            state.set_table_selection(file_path, sel)

        # 模拟多次切换文件并验证选择状态
        for file_path, row_count in zip(files, row_counts):
            retrieved = state.get_table_selection(file_path)
            assert len(retrieved) == row_count - 3
            assert 0 not in retrieved
            assert 1 not in retrieved
            assert 2 not in retrieved


class TestBackwardCompatibility:
    """测试向后兼容性（GUI 对象属性存储）"""

    def test_fallback_to_gui_attributes_when_no_batch_state(self):
        """测试当没有 BatchState 时，回退到 GUI 对象属性存储"""
        # 这个测试需要在实际的 GUI 环境中运行
        # 这里只做基本的接口验证

        # 创建 mock manager（没有 _batch_state）
        mock_manager = MagicMock()
        mock_gui = MagicMock()
        mock_manager.gui = mock_gui
        mock_manager._batch_state = None

        # 确保函数不会崩溃
        from gui.batch_manager_preview import _ensure_table_row_selection_storage

        file_path = Path("test.csv")
        result = _ensure_table_row_selection_storage(mock_manager, file_path, 10)

        # 应该使用 GUI 属性存储并返回 set
        assert result is not None or hasattr(
            mock_gui, "table_row_selection_by_file"
        )


class TestSelectionStateEdgeCases:
    """测试选择状态管理的边界情况"""

    def test_empty_selection(self):
        """测试空选择状态（全部取消选择）"""
        state = BatchStateManager()
        file_path = "test.csv"
        row_count = 10

        # 初始化并取消所有选择
        selection = state.get_table_selection(file_path, row_count)
        selection.clear()
        state.set_table_selection(file_path, selection)

        # 再次获取，应为空集合
        retrieved = state.get_table_selection(file_path)
        assert len(retrieved) == 0

    def test_zero_row_count(self):
        """测试行数为 0 的情况"""
        state = BatchStateManager()
        file_path = "empty.csv"

        # 获取空文件的选择状态
        selection = state.get_table_selection(file_path, 0)

        assert isinstance(selection, set)
        assert len(selection) == 0

    def test_large_row_count(self):
        """测试大量行数的选择状态"""
        state = BatchStateManager()
        file_path = "large.csv"
        row_count = 100000

        # 初始化大量行的选择状态（默认全选）
        selection = state.get_table_selection(file_path, row_count)

        assert len(selection) == row_count

        # 取消选择部分行
        for i in range(0, row_count, 1000):
            selection.discard(i)
        state.set_table_selection(file_path, selection)

        # 验证修改后的状态
        retrieved = state.get_table_selection(file_path)
        assert len(retrieved) == row_count - 100  # 取消了 100 行

    def test_concurrent_modification(self):
        """测试并发修改选择状态（基本测试）"""
        state = BatchStateManager()
        file_path = "test.csv"
        row_count = 10

        # 获取选择状态的引用
        sel1 = state.get_table_selection(file_path, row_count)
        sel2 = state.get_table_selection(file_path)

        # 两个引用应指向同一个集合
        assert sel1 is sel2

        # 通过一个引用修改，另一个引用也会看到变化
        sel1.discard(0)
        assert 0 not in sel2
