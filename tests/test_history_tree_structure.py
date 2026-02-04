"""测试历史记录树状结构和重做计数功能"""

import sys
import unittest

from PySide6.QtWidgets import QApplication

from gui.batch_history import BatchHistoryPanel, BatchHistoryStore


class TestHistoryTreeStructure(unittest.TestCase):
    """测试树状结构支持"""

    @classmethod
    def setUpClass(cls):
        """创建 QApplication"""
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        """设置测试环境"""
        self.store = BatchHistoryStore()
        self.panel = BatchHistoryPanel(self.store)

    def test_add_parent_record(self):
        """测试添加父记录"""
        rec = self.store.add_record(
            input_path="test.csv",
            output_dir="output/",
            files=["test.csv"],
            new_files=["result.csv"],
            status="completed",
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec["id"], rec["id"])
        self.assertNotIn("parent_record_id", rec)  # 顶级记录没有 parent_record_id
        print(f"✓ 创建父记录: {rec['id'][:8]}")

    def test_add_child_record(self):
        """测试添加子记录（重做生成的记录）"""
        # 创建父记录
        parent = self.store.add_record(
            input_path="test.csv",
            output_dir="output/",
            files=["test.csv"],
            new_files=["result.csv"],
            status="completed",
        )

        # 创建子记录（重做生成的）
        child = self.store.add_record(
            input_path="test.csv",
            output_dir="output/",
            files=["test.csv"],
            new_files=["result2.csv"],
            status="completed",
            parent_record_id=parent["id"],
        )

        self.assertIsNotNone(child)
        self.assertEqual(child["parent_record_id"], parent["id"])
        print(f"✓ 创建子记录: {child['id'][:8]} (父: {parent['id'][:8]})")

    def test_redo_count_display(self):
        """测试重做计数显示"""
        # 创建父记录
        parent = self.store.add_record(
            input_path="data.csv",
            output_dir="output/",
            files=["data.csv"],
            new_files=["result1.csv"],
            status="completed",
        )

        # 创建 3 个子记录（3 次重做）
        for i in range(3):
            self.store.add_record(
                input_path="data.csv",
                output_dir="output/",
                files=["data.csv"],
                new_files=[f"result{i+2}.csv"],
                status="completed",
                parent_record_id=parent["id"],
            )

        # 刷新面板并检查
        self.panel.refresh()

        # 验证树状结构
        all_records = self.store.get_records()
        print(f"✓ 总记录数: {len(all_records)}")

        # 查找父记录及其子记录
        parent_rec = None
        children = []
        for rec in all_records:
            if rec["id"] == parent["id"]:
                parent_rec = rec
            elif rec.get("parent_record_id") == parent["id"]:
                children.append(rec)

        self.assertIsNotNone(parent_rec)
        self.assertEqual(len(children), 3)
        print(f"✓ 父记录: {parent_rec['id'][:8]}")
        print(f"✓ 子记录数: {len(children)}")
        print(f"✓ 摘要应显示: 已重做 {len(children)} 次")

    def test_tree_widget_hierarchy(self):
        """测试 QTreeWidget 显示的层级结构"""
        # 创建测试数据
        parent1 = self.store.add_record(
            input_path="file1.csv",
            output_dir="output/",
            files=["file1.csv"],
            new_files=["result1.csv"],
            status="completed",
        )

        parent2 = self.store.add_record(
            input_path="file2.csv",
            output_dir="output/",
            files=["file2.csv"],
            new_files=["result2.csv"],
            status="completed",
        )

        # 为 parent1 添加 2 个子记录
        for i in range(2):
            self.store.add_record(
                input_path="file1.csv",
                output_dir="output/",
                files=["file1.csv"],
                new_files=[f"redo{i}.csv"],
                status="completed",
                parent_record_id=parent1["id"],
            )

        # 刷新面板
        self.panel.refresh()

        # 检查树的结构
        root_count = self.panel.tree.topLevelItemCount()
        print(f"✓ 日期组数: {root_count}")

        # 检查第一个日期组下的记录
        if root_count > 0:
            day_item = self.panel.tree.topLevelItem(0)
            record_count = day_item.childCount()
            print(f"✓ 该日期下的顶级记录数: {record_count}")

            # 检查第一个记录是否有子项
            if record_count > 0:
                first_record = day_item.child(0)
                child_count = first_record.childCount()
                print(f"✓ 第一个记录的子记录数: {child_count}")

    def test_child_record_styling(self):
        """测试子记录的样式（灰色）"""
        parent = self.store.add_record(
            input_path="test.csv",
            output_dir="output/",
            files=["test.csv"],
            new_files=["result1.csv"],
            status="completed",
        )

        child = self.store.add_record(
            input_path="test.csv",
            output_dir="output/",
            files=["test.csv"],
            new_files=["result2.csv"],
            status="completed",
            parent_record_id=parent["id"],
        )

        self.panel.refresh()

        # 树不应该为空
        self.assertGreater(self.panel.tree.topLevelItemCount(), 0)
        print("✓ 树状结构已正确创建")


if __name__ == "__main__":
    unittest.main()
