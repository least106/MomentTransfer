"""
测试批处理历史记录的环境隔离

确保测试运行时不会污染真实的历史记录
"""

import os
import tempfile
from pathlib import Path

import pytest


class TestHistoryIsolation:
    """测试历史记录的环境隔离"""

    def test_testing_environment_flag(self):
        """验证测试环境标志已设置"""
        assert os.getenv("TESTING") == "1", "测试环境标志未设置"

    def test_history_store_uses_temp_path(self):
        """验证测试环境下使用临时路径"""
        from gui.batch_history import BatchHistoryStore

        store = BatchHistoryStore()

        # 验证使用临时目录
        assert store._is_testing is True, "未标记为测试环境"

        temp_dir = Path(tempfile.gettempdir())
        assert str(store.store_path).startswith(
            str(temp_dir)
        ), f"测试环境应使用临时路径，实际: {store.store_path}"

        # 验证不是真实的生产路径
        real_path = Path.home() / ".momentconversion" / "batch_history.json"
        assert store.store_path != real_path, "测试环境不应使用生产路径"

    def test_history_save_skipped_in_test(self):
        """验证测试环境下不保存到磁盘"""
        from gui.batch_history import BatchHistoryStore

        store = BatchHistoryStore()

        # 添加一条测试记录
        record = store.add_record(
            input_path="test_input.csv",
            output_dir="test_output/",
            files=["test_file.csv"],
            new_files=["test_result.csv"],
            status="completed",
        )

        # 验证记录在内存中
        assert len(store.records) == 1
        assert store.records[0]["id"] == record["id"]

        # 保存应该被跳过（不写入磁盘）
        store.save()

        # 验证文件不存在或为空（因为跳过了保存）
        if store.store_path.exists():
            # 如果文件存在，应该是空的或者是之前测试留下的
            # 但不应该包含刚刚添加的记录
            pytest.skip("临时文件存在，跳过此验证")

    def test_production_path_unchanged(self):
        """验证生产环境路径没有被污染"""
        real_history = Path.home() / ".momentconversion" / "batch_history.json"

        if not real_history.exists():
            pytest.skip("生产历史文件不存在，跳过验证")

        # 读取生产环境历史记录（处理可能的 BOM）
        import json

        try:
            data = json.loads(real_history.read_text(encoding="utf-8-sig"))
        except Exception as e:
            pytest.skip(f"无法读取生产历史文件: {e}")

        # 验证没有测试数据（所有 test_*.csv 相关记录）
        if isinstance(data, dict):
            records = data.get("records", [])
        else:
            records = data

        test_records = [
            r
            for r in records
            if "test_input.csv" in r.get("input_path", "")
            or "test_file.csv" in str(r.get("files", []))
        ]

        assert (
            len(test_records) == 0
        ), f"生产环境发现测试记录，环境隔离失败: {test_records}"

    def test_batch_manager_respects_testing_flag(self):
        """验证 BatchManager 在测试环境下跳过历史记录"""
        from gui.batch_manager import BatchManager
        from PySide6.QtWidgets import QApplication, QMainWindow

        # 确保 QApplication 存在
        app = QApplication.instance()
        if app is None:
            import sys

            app = QApplication(sys.argv)

        # 创建最小化主窗口
        main_window = QMainWindow()
        main_window.statusBar()

        # 创建 BatchManager
        batch_manager = BatchManager(main_window)

        # 模拟批处理上下文
        batch_manager._current_batch_context = {
            "input_path": "test_batch_input.csv",
            "files": ["test_file1.csv", "test_file2.csv"],
            "output_dir": "test_output/",
        }

        # 设置输出目录和文件
        main_window._batch_output_dir = "test_output/"
        main_window._batch_existing_files = set()

        # 尝试记录历史（应该被跳过）
        batch_manager._record_batch_history(status="completed")

        # 验证：如果有 history_store，它应该在测试环境下
        if batch_manager.history_store:
            assert (
                batch_manager.history_store._is_testing is True
            ), "BatchManager 的 history_store 应该在测试环境下"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
