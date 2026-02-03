"""测试批处理历史的 Undo/Redo 功能"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from gui.batch_history import BatchHistoryStore


class TestUndoRedo:
    """测试撤销/重做功能"""

    def setup_method(self):
        """每个测试前创建临时存储"""
        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        self.temp_file.close()
        self.store_path = Path(self.temp_file.name)
        self.store = BatchHistoryStore(store_path=self.store_path)

    def teardown_method(self):
        """清理临时文件"""
        try:
            if self.store_path.exists():
                self.store_path.unlink()
        except Exception:
            pass

    def test_redo_stack_initialization(self):
        """测试 redo_stack 初始化"""
        assert hasattr(self.store, "redo_stack")
        assert isinstance(self.store.redo_stack, list)
        assert len(self.store.redo_stack) == 0

    def test_add_record_clears_redo_stack(self):
        """测试新增记录时清空 redo 栈"""
        # 添加一条记录
        rec1 = self.store.add_record(
            input_path="test1.csv",
            output_dir="/tmp/out1",
            files=["file1.csv"],
            new_files=["result1.csv"],
        )

        # 撤销
        self.store.undo_record(rec1["id"])
        assert len(self.store.redo_stack) == 1

        # 新增记录应清空 redo 栈
        self.store.add_record(
            input_path="test2.csv",
            output_dir="/tmp/out2",
            files=["file2.csv"],
            new_files=["result2.csv"],
        )
        assert len(self.store.redo_stack) == 0

    def test_undo_record_adds_to_redo_stack(self):
        """测试撤销操作将记录加入 redo 栈"""
        rec = self.store.add_record(
            input_path="test.csv",
            output_dir="/tmp/out",
            files=["file.csv"],
            new_files=["result.csv"],
            status="completed",
        )

        # 撤销
        undone = self.store.undo_record(rec["id"])
        assert undone is not None
        assert undone["status"] == "undone"
        assert len(self.store.redo_stack) == 1

        # 检查 redo 栈内容
        redo_item = self.store.redo_stack[0]
        assert redo_item["action"] == "undo"
        assert redo_item["record"]["id"] == rec["id"]

    def test_redo_record_restores_status(self):
        """测试重做操作恢复记录状态"""
        rec = self.store.add_record(
            input_path="test.csv",
            output_dir="/tmp/out",
            files=["file.csv"],
            new_files=["result.csv"],
            status="completed",
        )

        # 撤销
        self.store.undo_record(rec["id"])
        assert rec["status"] == "undone"

        # 重做
        redone = self.store.redo_record()
        assert redone is not None
        assert redone["id"] == rec["id"]
        assert redone["status"] == "completed"
        assert len(self.store.redo_stack) == 0

    def test_multiple_undo_redo_sequence(self):
        """测试多次撤销和重做的序列"""
        # 添加3条记录
        rec1 = self.store.add_record(
            input_path="test1.csv",
            output_dir="/tmp/out1",
            files=["file1.csv"],
            new_files=["result1.csv"],
        )
        rec2 = self.store.add_record(
            input_path="test2.csv",
            output_dir="/tmp/out2",
            files=["file2.csv"],
            new_files=["result2.csv"],
        )
        rec3 = self.store.add_record(
            input_path="test3.csv",
            output_dir="/tmp/out3",
            files=["file3.csv"],
            new_files=["result3.csv"],
        )

        # 撤销最后两条
        self.store.undo_record(rec3["id"])
        self.store.undo_record(rec2["id"])
        assert len(self.store.redo_stack) == 2

        # 重做一次
        redone = self.store.redo_record()
        assert redone["id"] == rec2["id"]
        assert len(self.store.redo_stack) == 1

        # 再重做一次
        redone = self.store.redo_record()
        assert redone["id"] == rec3["id"]
        assert len(self.store.redo_stack) == 0

    def test_redo_with_empty_stack(self):
        """测试空 redo 栈时重做"""
        result = self.store.redo_record()
        assert result is None

    def test_get_redo_info(self):
        """测试获取 redo 信息"""
        # 空栈
        info = self.store.get_redo_info()
        assert info is None

        # 添加并撤销
        rec = self.store.add_record(
            input_path="test.csv",
            output_dir="/tmp/out",
            files=["file.csv"],
            new_files=["result1.csv", "result2.csv", "result3.csv"],
        )
        self.store.undo_record(rec["id"])

        # 获取信息
        info = self.store.get_redo_info()
        assert info is not None
        assert info["count"] == 3
        assert info["output_dir"] == "/tmp/out"
        assert "timestamp" in info

    def test_redo_after_new_batch(self):
        """测试新批处理后 redo 栈被清空"""
        rec1 = self.store.add_record(
            input_path="test1.csv",
            output_dir="/tmp/out1",
            files=["file1.csv"],
            new_files=["result1.csv"],
        )

        # 撤销
        self.store.undo_record(rec1["id"])
        assert len(self.store.redo_stack) == 1

        # 新增批处理
        self.store.add_record(
            input_path="test2.csv",
            output_dir="/tmp/out2",
            files=["file2.csv"],
            new_files=["result2.csv"],
        )

        # redo 栈应被清空
        assert len(self.store.redo_stack) == 0
        info = self.store.get_redo_info()
        assert info is None

    def test_persistence_with_redo_stack(self):
        """测试持久化保存和加载 redo 栈"""
        # 添加记录并撤销
        rec = self.store.add_record(
            input_path="test.csv",
            output_dir="/tmp/out",
            files=["file.csv"],
            new_files=["result.csv"],
        )
        self.store.undo_record(rec["id"])

        # 创建新 store 加载
        new_store = BatchHistoryStore(store_path=self.store_path)
        assert len(new_store.redo_stack) == 1
        assert new_store.redo_stack[0]["action"] == "undo"

        # 验证可以重做
        redone = new_store.redo_record()
        assert redone is not None
        assert redone["status"] == "completed"

    def test_backward_compatibility(self):
        """测试对旧格式的向后兼容性"""
        # 手动写入旧格式（仅包含 records 列表）
        import json

        old_format = [
            {
                "id": "test123",
                "timestamp": datetime.now().isoformat(),
                "input_path": "test.csv",
                "output_dir": "/tmp/out",
                "files": ["file.csv"],
                "new_files": ["result.csv"],
                "status": "completed",
            }
        ]
        self.store_path.write_text(json.dumps(old_format), encoding="utf-8")

        # 加载应该成功且 redo_stack 为空
        store = BatchHistoryStore(store_path=self.store_path)
        assert len(store.records) == 1
        assert len(store.redo_stack) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
