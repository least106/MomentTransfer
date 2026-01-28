"""
表格筛选模块 - 为 QTableWidget 提供行筛选和灰显功能
"""

import logging
from typing import Dict, List, Set

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QWidget,
)

logger = logging.getLogger(__name__)


class TableFilterManager:
    """表格筛选管理器 - 管理筛选条件、灰显行、全选范围"""

    def __init__(self, table: QTableWidget):
        """初始化筛选管理器。

        参数：
            table: QTableWidget 实例
        """
        self.table = table
        self.filters: List[Dict] = (
            []
        )  # 筛选条件列表，每项为 {'column': int, 'operator': str, 'value': str}
        self.hidden_rows: Set[int] = set()  # 被筛选隐藏的行索引
        self.gray_color = QColor(200, 200, 200)  # 灰显颜色
        self.normal_color = QColor(255, 255, 255)  # 正常颜色

    def add_filter(self, column: int, operator: str, value: str) -> None:
        """添加筛选条件。

        参数：
            column: 列索引
            operator: 比较操作符（'==', '!=', '<', '>', '<=', '>=', 'contains', 'not_contains'）
            value: 比较值
        """
        self.filters.append({"column": column, "operator": operator, "value": value})
        self._apply_filters()

    def clear_filters(self) -> None:
        """清空所有筛选条件。"""
        self.filters.clear()
        self._apply_filters()

    def _apply_filters(self) -> None:
        """应用筛选条件，隐藏不符合条件的行。"""
        self.hidden_rows.clear()

        if not self.filters:
            # 无筛选，全部行显示
            for r in range(self.table.rowCount()):
                self._set_row_visible(r, True)
            return

        for r in range(self.table.rowCount()):
            if self._row_matches_filters(r):
                self._set_row_visible(r, True)
            else:
                self._set_row_visible(r, False)
                self.hidden_rows.add(r)

    def _row_matches_filters(self, row: int) -> bool:
        """检查某一行是否符合所有筛选条件（AND逻辑）。"""
        for filt in self.filters:
            col = filt.get("column")
            op = filt.get("operator")
            val = filt.get("value")

            try:
                item = self.table.item(row, col)
                if item is None:
                    return False
                cell_value = item.text() or ""
            except Exception:
                return False

            if not self._matches_condition(cell_value, op, val):
                return False

        return True

    def _matches_condition(
        self, cell_value: str, operator: str, filter_value: str
    ) -> bool:
        """检查单个单元格是否符合条件。"""
        try:
            if operator == "contains":
                return filter_value.lower() in cell_value.lower()
            elif operator == "not_contains":
                return filter_value.lower() not in cell_value.lower()
            elif operator == "==":
                return cell_value.lower() == filter_value.lower()
            elif operator == "!=":
                return cell_value.lower() != filter_value.lower()
            elif operator == "<":
                return float(cell_value) < float(filter_value)
            elif operator == ">":
                return float(cell_value) > float(filter_value)
            elif operator == "<=":
                return float(cell_value) <= float(filter_value)
            elif operator == ">=":
                return float(cell_value) >= float(filter_value)
        except Exception:
            pass
        return True

    def _set_row_visible(self, row: int, visible: bool) -> None:
        """设置行的显示/灰显状态。"""
        self.table.setRowHidden(row, not visible)

        # 设置颜色（灰显）
        color = self.normal_color if visible else self.gray_color
        for c in range(self.table.columnCount()):
            try:
                item = self.table.item(row, c)
                if item is not None:
                    item.setBackground(color)
            except Exception:
                pass

    def get_visible_rows(self) -> List[int]:
        """获取所有可见（未被筛选隐藏）的行索引。"""
        visible = []
        for r in range(self.table.rowCount()):
            if r not in self.hidden_rows:
                visible.append(r)
        return visible

    def get_hidden_rows(self) -> Set[int]:
        """获取所有被筛选隐藏的行索引。"""
        return self.hidden_rows.copy()


class TableFilterWidget(QWidget):
    """表格筛选控件 - 提供UI用于添加和管理筛选条件"""

    def __init__(self, table: QTableWidget, parent=None):
        """初始化筛选控件。

        参数：
            table: 要筛选的 QTableWidget
        """
        super().__init__(parent)
        self.table = table
        self.filter_manager = TableFilterManager(table)
        self._init_ui()

    def _init_ui(self) -> None:
        """初始化UI。"""
        layout = QHBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(2, 2, 2, 2)

        # 列选择
        lbl_col = QLabel("列:")
        self.cmb_column = QComboBox()
        try:
            # 若表头为显示用的带序号/换行格式（如 "1\nColName"），则取最后一行作为真实列名
            headers = []
            for c in range(self.table.columnCount()):
                try:
                    raw = self.table.horizontalHeaderItem(c).text()
                    # 取最后一行以移除序号或额外注释
                    clean = raw.splitlines()[-1] if raw else raw
                    headers.append(clean)
                except Exception:
                    headers.append("")
        except Exception:
            headers = [str(c) for c in range(self.table.columnCount())]
        self.cmb_column.addItems(headers)
        layout.addWidget(lbl_col)
        layout.addWidget(self.cmb_column)

        # 操作符选择
        lbl_op = QLabel("操作:")
        self.cmb_operator = QComboBox()
        self.cmb_operator.addItems(
            ["包含", "不包含", "等于", "不等于", "<", ">", "<=", ">="]
        )
        self._operator_map = {
            "包含": "contains",
            "不包含": "not_contains",
            "等于": "==",
            "不等于": "!=",
            "<": "<",
            ">": ">",
            "<=": "<=",
            ">=": ">=",
        }
        layout.addWidget(lbl_op)
        layout.addWidget(self.cmb_operator)

        # 值输入
        lbl_val = QLabel("值:")
        self.inp_value = QLineEdit()
        self.inp_value.setPlaceholderText("输入筛选值")
        layout.addWidget(lbl_val)
        layout.addWidget(self.inp_value)

        # 添加筛选按钮
        self.btn_add_filter = QPushButton("添加筛选")
        self.btn_add_filter.setMaximumWidth(80)
        self.btn_add_filter.clicked.connect(self._on_add_filter)
        layout.addWidget(self.btn_add_filter)

        # 清除筛选按钮
        self.btn_clear_filters = QPushButton("清除筛选")
        self.btn_clear_filters.setMaximumWidth(80)
        self.btn_clear_filters.clicked.connect(self._on_clear_filters)
        layout.addWidget(self.btn_clear_filters)

        layout.addStretch()

    def _on_add_filter(self) -> None:
        """添加筛选条件。"""
        col = self.cmb_column.currentIndex()
        op_text = self.cmb_operator.currentText()
        op = self._operator_map.get(op_text, "contains")
        val = self.inp_value.text().strip()

        if not val:
            logger.warning("筛选值为空")
            return

        self.filter_manager.add_filter(col, op, val)
        self.inp_value.clear()

    def _on_clear_filters(self) -> None:
        """清除所有筛选条件。"""
        self.filter_manager.clear_filters()
        self.inp_value.clear()

    def get_filter_manager(self) -> TableFilterManager:
        """获取筛选管理器。"""
        return self.filter_manager
