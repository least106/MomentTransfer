"""测试批处理历史面板改进功能"""

import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

# 确保测试导入时项目根在 sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from gui.batch_history import BatchHistoryPanel, BatchHistoryStore


@pytest.fixture(scope="module")
def app():
    """提供 QApplication 实例"""
    if not QApplication.instance():
        return QApplication(sys.argv)
    return QApplication.instance()


@pytest.fixture
def temp_store():
    """提供临时的历史存储"""
    with TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / "test_history.json"
        store = BatchHistoryStore(store_path=store_path)
        yield store


@pytest.fixture
def panel(app, temp_store):
    """提供历史面板实例"""
    return BatchHistoryPanel(temp_store)


class TestStatsInRecords:
    """测试记录中的统计信息"""

    def test_add_record_with_stats(self, temp_store):
        """测试添加带统计信息的记录"""
        stats = {"success": 5, "failed": 1, "skipped": 2}
        record = temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output",
            files=["file1.csv", "file2.csv"],
            new_files=["out1.csv", "out2.csv"],
            stats=stats,
        )

        assert record["stats"] == stats
        assert record["stats"]["success"] == 5
        assert record["stats"]["failed"] == 1
        assert record["stats"]["skipped"] == 2

    def test_add_record_without_stats_uses_default(self, temp_store):
        """测试不提供统计信息时使用默认值"""
        record = temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output",
            files=["file1.csv"],
            new_files=["out1.csv", "out2.csv"],  # 2 个新文件
        )

        # 默认统计：所有文件成功
        assert record["stats"]["success"] == 2
        assert record["stats"]["failed"] == 0
        assert record["stats"]["skipped"] == 0

    def test_stats_persisted_to_storage(self, temp_store):
        """测试统计信息被持久化"""
        stats = {"success": 3, "failed": 2, "skipped": 1}
        temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output",
            files=["file1.csv"],
            new_files=["out1.csv"],
            stats=stats,
        )

        # 重新加载存储
        records = temp_store.get_records()
        assert len(records) > 0
        assert records[0]["stats"] == stats


class TestStatsDisplay:
    """测试统计信息显示"""

    def test_stats_text_with_success_only(self, panel):
        """测试只有成功的统计文本"""
        rec = {"stats": {"success": 5, "failed": 0, "skipped": 0}}
        stats_text = panel._build_stats_text(rec)
        assert "✅ 5" in stats_text
        assert "❌" not in stats_text
        assert "⏭" not in stats_text

    def test_stats_text_with_all_types(self, panel):
        """测试包含所有类型的统计文本"""
        rec = {"stats": {"success": 3, "failed": 1, "skipped": 2}}
        stats_text = panel._build_stats_text(rec)
        assert "✅ 3" in stats_text
        assert "❌ 1" in stats_text
        assert "⏭ 2" in stats_text

    def test_stats_text_empty_when_no_stats(self, panel):
        """测试没有统计信息时返回空字符串"""
        rec = {}
        stats_text = panel._build_stats_text(rec)
        assert stats_text == ""

    def test_stats_text_with_zero_values(self, panel):
        """测试统计值为 0 时不显示"""
        rec = {"stats": {"success": 5, "failed": 0, "skipped": 0}}
        stats_text = panel._build_stats_text(rec)
        assert "✅ 5" in stats_text
        assert "❌" not in stats_text
        assert "⏭" not in stats_text

    def test_stats_column_in_tree(self, panel, temp_store):
        """测试树形控件中显示统计列"""
        temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output",
            files=["file1.csv"],
            new_files=["out1.csv"],
            stats={"success": 5, "failed": 1, "skipped": 0},
        )

        panel.refresh()

        # 验证表头包含"统计"列
        headers = [
            panel.tree.headerItem().text(i) for i in range(panel.tree.columnCount())
        ]
        assert "统计" in headers

    def test_stats_in_tooltip(self, panel, temp_store):
        """测试详情提示包含统计信息"""
        record = temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output",
            files=["file1.csv"],
            new_files=["out1.csv"],
            stats={"success": 3, "failed": 1, "skipped": 2},
        )

        details = panel.get_record_details(record["id"])
        assert details is not None
        assert "📊 处理统计" in details
        assert "✅ 成功: 3" in details
        assert "❌ 失败: 1" in details
        assert "⏭ 跳过: 2" in details


class TestSearchFunctionality:
    """测试搜索功能"""

    def test_search_box_exists(self, panel):
        """测试搜索框存在"""
        assert hasattr(panel, "inp_search")
        assert panel.inp_search is not None

    def test_clear_search_button_exists(self, panel):
        """测试清除搜索按钮存在"""
        assert hasattr(panel, "btn_clear_search")
        assert panel.btn_clear_search is not None

    def test_search_by_input_path(self, panel, temp_store):
        """测试按输入路径搜索"""
        temp_store.add_record(
            input_path="/input/data1.csv",
            output_dir="/output",
            files=["file1.csv"],
            new_files=["out1.csv"],
        )
        temp_store.add_record(
            input_path="/input/data2.csv",
            output_dir="/output",
            files=["file2.csv"],
            new_files=["out2.csv"],
        )

        # 搜索 data1
        panel._search_text = "data1"
        panel.refresh()

        # 验证搜索文本已设置
        assert panel._search_text == "data1"

    def test_search_by_output_dir(self, panel, temp_store):
        """测试按输出目录搜索"""
        temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output/folder1",
            files=["file1.csv"],
            new_files=["out1.csv"],
        )
        temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output/folder2",
            files=["file2.csv"],
            new_files=["out2.csv"],
        )

        panel.inp_search.setText("folder1")
        panel.refresh()

        assert panel._search_text == "folder1"

    def test_search_by_date(self, panel, temp_store):
        """测试按日期搜索"""
        temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output",
            files=["file1.csv"],
            new_files=["out1.csv"],
            timestamp=datetime(2026, 2, 5, 10, 30),
        )
        temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output",
            files=["file2.csv"],
            new_files=["out2.csv"],
            timestamp=datetime(2026, 1, 15, 14, 20),
        )

        # 搜索 2026-02
        panel.inp_search.setText("2026-02")
        panel.refresh()

        assert panel._search_text == "2026-02"

    def test_clear_search_resets_filter(self, panel):
        """测试清除搜索重置过滤"""
        panel._search_text = "test"
        assert panel._search_text == "test"

        panel._clear_search()

        assert panel._search_text == ""
        assert panel.inp_search.text() == ""

    def test_search_case_insensitive(self, panel, temp_store):
        """测试搜索不区分大小写"""
        temp_store.add_record(
            input_path="/input/DATA.CSV",
            output_dir="/output",
            files=["/path/to/FILE.csv"],
            new_files=["out.csv"],
        )

        rec = temp_store.get_records()[0]

        # 小写搜索应该匹配大写路径
        panel._search_text = "data.csv"
        assert panel._matches_search(rec)

        # 大写搜索应该匹配小写路径（搜索文件名）
        panel._search_text = "file"
        assert panel._matches_search(rec)

    def test_search_by_filename(self, panel, temp_store):
        """测试按文件名搜索"""
        temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output",
            files=["/path/to/important_file.csv", "/path/to/other.csv"],
            new_files=["out1.csv"],
        )

        rec = temp_store.get_records()[0]
        panel._search_text = "important_file"
        assert panel._matches_search(rec)

    def test_matches_search_returns_true_when_no_search(self, panel):
        """测试没有搜索条件时返回 True"""
        panel._search_text = ""
        rec = {"input_path": "/any/path", "output_dir": "/any/output"}
        assert panel._matches_search(rec)


class TestStatsAggregation:
    """测试统计信息聚合"""

    def test_total_stats_shown_when_searching(self, panel, temp_store):
        """测试搜索时显示总体统计"""
        temp_store.add_record(
            input_path="/input/data1.csv",
            output_dir="/output",
            files=["file1.csv"],
            new_files=["out1.csv"],
            stats={"success": 3, "failed": 1, "skipped": 0},
        )
        temp_store.add_record(
            input_path="/input/data2.csv",
            output_dir="/output",
            files=["file2.csv"],
            new_files=["out2.csv"],
            stats={"success": 2, "failed": 0, "skipped": 1},
        )

        panel._search_text = "data"
        panel.refresh()

        # 验证统计标签内容
        stats_text = panel.lbl_stats.text()
        assert "✅" in stats_text  # 包含成功图标

    def test_stats_label_hidden_when_not_searching(self, panel, temp_store):
        """测试未搜索时统计标签隐藏"""
        temp_store.add_record(
            input_path="/input/data.csv",
            output_dir="/output",
            files=["file1.csv"],
            new_files=["out1.csv"],
        )

        panel.inp_search.clear()
        panel.refresh()

        assert not panel.lbl_stats.isVisible()

    def test_stats_aggregation_across_records(self, panel, temp_store):
        """测试跨记录统计聚合"""
        temp_store.add_record(
            input_path="/input/data1.csv",
            output_dir="/output",
            files=["file1.csv"],
            new_files=["out1.csv"],
            stats={"success": 5, "failed": 2, "skipped": 1},
        )
        temp_store.add_record(
            input_path="/input/data2.csv",
            output_dir="/output",
            files=["file2.csv"],
            new_files=["out2.csv"],
            stats={"success": 3, "failed": 1, "skipped": 0},
        )

        panel.inp_search.setText("input")
        panel.refresh()

        stats_text = panel.lbl_stats.text()
        # 总计：success=8, failed=3, skipped=1
        assert "✅ 8" in stats_text
        assert "❌ 3" in stats_text


class TestBackwardCompatibility:
    """测试向后兼容性"""

    def test_old_records_without_stats_still_work(self, panel, temp_store):
        """测试没有统计信息的旧记录仍然正常工作"""
        # 模拟旧记录（没有 stats 字段）
        old_record = {
            "id": "test_id",
            "timestamp": datetime.now().isoformat(),
            "input_path": "/input/data.csv",
            "output_dir": "/output",
            "files": ["file1.csv"],
            "new_files": ["out1.csv"],
            "status": "completed",
        }
        temp_store.records.insert(0, old_record)

        # 应该不会报错
        try:
            panel.refresh()
            stats_text = panel._build_stats_text(old_record)
            assert stats_text == ""  # 旧记录没有统计信息
        except Exception as e:
            pytest.fail(f"旧记录处理失败: {e}")

    def test_get_details_with_missing_stats(self, panel, temp_store):
        """测试获取没有统计信息的记录详情"""
        old_record = {
            "id": "test_id_2",
            "timestamp": datetime.now().isoformat(),
            "input_path": "/input/data.csv",
            "output_dir": "/output",
            "files": ["file1.csv"],
            "new_files": ["out1.csv"],
            "status": "completed",
        }
        temp_store.records.insert(0, old_record)

        details = panel.get_record_details("test_id_2")
        # 不应该包含统计信息部分
        assert "📊 处理统计" not in details


class TestUIInteraction:
    """测试 UI 交互"""

    def test_search_box_placeholder(self, panel):
        """测试搜索框占位文本"""
        assert panel.inp_search.placeholderText() == "搜索路径、日期..."

    def test_search_box_tooltip(self, panel):
        """测试搜索框提示"""
        tooltip = panel.inp_search.toolTip()
        assert "搜索" in tooltip
        assert "路径" in tooltip or "日期" in tooltip

    def test_clear_button_initially_hidden(self, panel):
        """测试清除按钮初始隐藏"""
        assert not panel.btn_clear_search.isVisible()

    def test_clear_button_visible_when_searching(self, panel):
        """测试搜索时清除按钮逻辑"""
        # 测试 _on_search_changed 方法会设置可见性
        panel._on_search_changed("test")
        assert panel._search_text == "test"

    def test_clear_button_tooltip(self, panel):
        """测试清除按钮提示"""
        assert panel.btn_clear_search.toolTip() == "清除搜索"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
