"""
全局数据筛选面板 - 提供基于列值的行过滤条件
支持多条件 AND/OR/NOT 逻辑
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import pandas as pd
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class FilterOperator(Enum):
    """筛选操作符"""

    CONTAINS = "包含"
    NOT_CONTAINS = "不包含"
    EQUALS = "="
    NOT_EQUALS = "!="
    LESS_THAN = "<"
    GREATER_THAN = ">"
    LESS_EQUAL = "<="
    GREATER_EQUAL = ">="


class FilterLogic(Enum):
    """多条件逻辑操作符"""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class FilterCondition:
    """单条筛选条件"""

    def __init__(
        self,
        column: str,
        operator: FilterOperator,
        value: str,
        logic: FilterLogic = FilterLogic.AND,
    ):
        """
        Args:
            column: 列名
            operator: 比较操作符
            value: 比较值
            logic: 逻辑操作符（当作为第一个条件时忽略）
        """
        self.column = column
        self.operator = operator
        self.value = value
        self.logic = logic  # AND 或 OR 或 NOT

    def matches(self, row_value: Any) -> bool:
        """检查行值是否满足条件"""
        try:
            row_str = str(row_value).strip()
            val_str = str(self.value).strip()

            if self.operator == FilterOperator.CONTAINS:
                return val_str in row_str
            elif self.operator == FilterOperator.NOT_CONTAINS:
                return val_str not in row_str
            elif self.operator == FilterOperator.EQUALS:
                return row_str == val_str
            elif self.operator == FilterOperator.NOT_EQUALS:
                return row_str != val_str
            elif self.operator == FilterOperator.LESS_THAN:
                try:
                    return float(row_str) < float(val_str)
                except ValueError:
                    return False
            elif self.operator == FilterOperator.GREATER_THAN:
                try:
                    return float(row_str) > float(val_str)
                except ValueError:
                    return False
            elif self.operator == FilterOperator.LESS_EQUAL:
                try:
                    return float(row_str) <= float(val_str)
                except ValueError:
                    return False
            elif self.operator == FilterOperator.GREATER_EQUAL:
                try:
                    return float(row_str) >= float(val_str)
                except ValueError:
                    return False
        except Exception as e:
            logger.debug("筛选条件匹配失败: %s", e)
            return False

        return True


class GlobalFilterPanel(QWidget):
    """全局数据筛选面板"""

    filtersChanged = Signal()  # 筛选条件变化

    def __init__(self, parent=None):
        super().__init__(parent)
        self.conditions: List[FilterCondition] = []
        self.hidden_rows_by_table: Dict[int, Set[int]] = (
            {}
        )  # table_id -> hidden row indices
        self._columns: List[str] = []  # 当前可用列名
        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(4, 4, 4, 4)

        # 标题
        title = QLabel("数据筛选")
        title_font = QFont()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # 条件容器（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(150)

        self.conditions_container = QWidget()
        self.conditions_layout = QVBoxLayout(self.conditions_container)
        self.conditions_layout.setSpacing(4)
        self.conditions_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self.conditions_container)
        layout.addWidget(scroll)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self.btn_add_condition = QPushButton("添加条件")
        self.btn_add_condition.setMaximumWidth(80)
        self.btn_add_condition.clicked.connect(self._on_add_condition)

        self.btn_clear_filters = QPushButton("清除筛选")
        self.btn_clear_filters.setMaximumWidth(80)
        self.btn_clear_filters.clicked.connect(self._on_clear_filters)

        btn_layout.addWidget(self.btn_add_condition)
        btn_layout.addWidget(self.btn_clear_filters)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

    def _on_add_condition(self):
        """添加新筛选条件"""
        # 确定逻辑操作符：如果已有条件，让用户选择；否则忽略
        logic = FilterLogic.AND

        if self.conditions:
            # 创建临时对话框让用户选择逻辑
            logic_choice = self._show_logic_selector()
            if logic_choice is None:
                return
            logic = logic_choice

        # 创建条件编辑小部件
        condition_widget = FilterConditionWidget(
            logic=logic,
            is_first=(len(self.conditions) == 0),
            on_remove=self._on_remove_condition,
        )
        try:
            condition_widget.set_available_columns(self._columns)
        except Exception:
            pass
        self.conditions_layout.insertWidget(
            len(self.conditions), condition_widget
        )

        # 暂时存储空条件（稍后在编辑时更新）
        self.conditions.append(
            FilterCondition("", FilterOperator.EQUALS, "", logic)
        )

        self.filtersChanged.emit()

    def _show_logic_selector(self) -> Optional[FilterLogic]:
        """显示逻辑选择对话框（简化版）"""
        # 在实际应用中，可以使用 QDialog；这里简化为直接选择
        # 暂时返回 AND，用户可以在条件小部件中修改
        return FilterLogic.AND

    def _on_remove_condition(self, condition_widget: "FilterConditionWidget"):
        """移除条件"""
        try:
            idx = self.conditions_layout.indexOf(condition_widget)
            if idx >= 0:
                self.conditions_layout.removeWidget(condition_widget)
                condition_widget.deleteLater()
                if idx < len(self.conditions):
                    self.conditions.pop(idx)
                self.filtersChanged.emit()
        except Exception as e:
            logger.debug("移除条件失败: %s", e)

    def _on_clear_filters(self):
        """清除所有筛选条件"""
        # 清除UI
        while self.conditions_layout.count() > 0:
            widget = self.conditions_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()

        # 清除数据
        self.conditions.clear()
        self.hidden_rows_by_table.clear()

        self.filtersChanged.emit()

    # === 列管理 ===
    def set_columns(self, columns: List[str]) -> None:
        """更新可选列列表，并同步到所有条件下拉框"""
        try:
            self._columns = columns or []
            for i in range(self.conditions_layout.count()):
                widget = self.conditions_layout.itemAt(i).widget()
                if isinstance(widget, FilterConditionWidget):
                    widget.set_available_columns(self._columns)
        except Exception as e:
            logger.debug("更新筛选列失败: %s", e)

    def get_conditions(self) -> List[FilterCondition]:
        """获取当前所有条件（从UI更新）"""
        self.conditions.clear()

        for i in range(self.conditions_layout.count()):
            widget = self.conditions_layout.itemAt(i).widget()
            if isinstance(widget, FilterConditionWidget):
                condition = widget.get_condition()
                if condition and condition.column:  # 只添加有效条件
                    self.conditions.append(condition)

        return self.conditions

    def apply_filters(self, df: pd.DataFrame, table_id: int) -> Set[int]:
        """
        对DataFrame应用筛选，返回被隐藏的行索引集合

        Args:
            df: 数据框
            table_id: 表格标识符（用于缓存隐藏行）

        Returns:
            隐藏行的索引集合
        """
        conditions = self.get_conditions()

        if not conditions or df.empty:
            self.hidden_rows_by_table[table_id] = set()
            return set()

        hidden_rows = set()

        # 评估每一行
        for row_idx in range(len(df)):
            # 初始化：第一个条件直接使用，后续条件通过逻辑操作符组合
            result = None

            for cond_idx, condition in enumerate(conditions):
                # 确保列存在
                if condition.column not in df.columns:
                    if cond_idx == 0:
                        result = False
                    elif condition.logic == FilterLogic.AND:
                        result = result and False
                    elif condition.logic == FilterLogic.OR:
                        result = result or False
                    elif condition.logic == FilterLogic.NOT:
                        result = result and (not False)
                    continue

                match = condition.matches(df.iloc[row_idx][condition.column])

                if cond_idx == 0:
                    result = match
                elif condition.logic == FilterLogic.AND:
                    result = result and match
                elif condition.logic == FilterLogic.OR:
                    result = result or match
                elif condition.logic == FilterLogic.NOT:
                    result = result and (not match)

            # 如果结果为 False（不匹配），则隐藏该行
            if result is False:
                hidden_rows.add(row_idx)

        self.hidden_rows_by_table[table_id] = hidden_rows
        return hidden_rows

    def is_row_visible(self, table_id: int, row_idx: int) -> bool:
        """检查行是否可见"""
        return row_idx not in self.hidden_rows_by_table.get(table_id, set())

    def get_hidden_rows(self, table_id: int) -> Set[int]:
        """获取隐藏行"""
        return self.hidden_rows_by_table.get(table_id, set())


class FilterConditionWidget(QWidget):
    """单条筛选条件编辑小部件"""

    def __init__(
        self,
        logic: FilterLogic = FilterLogic.AND,
        is_first: bool = False,
        on_remove=None,
        parent=None,
    ):
        super().__init__(parent)
        self.logic = logic
        self.is_first = is_first
        self.on_remove = on_remove
        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QHBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        # 逻辑操作符（第一个条件隐藏）
        if not self.is_first:
            self.cmb_logic = QComboBox()
            self.cmb_logic.addItems([fl.value for fl in FilterLogic])
            self.cmb_logic.setCurrentText(self.logic.value)
            self.cmb_logic.setMaximumWidth(60)
            layout.addWidget(self.cmb_logic)
        else:
            self.cmb_logic = None

        # 列选择
        self.cmb_column = QComboBox()
        self.cmb_column.setMaximumWidth(100)
        layout.addWidget(self.cmb_column)

        # 操作符
        self.cmb_operator = QComboBox()
        self.cmb_operator.addItems([op.value for op in FilterOperator])
        self.cmb_operator.setMaximumWidth(90)
        layout.addWidget(self.cmb_operator)

        # 值输入
        self.inp_value = QLineEdit()
        self.inp_value.setPlaceholderText("输入值...")
        self.inp_value.setMaximumWidth(100)
        layout.addWidget(self.inp_value)

        # 移除按钮
        self.btn_remove = QPushButton("×")
        self.btn_remove.setMaximumWidth(30)
        self.btn_remove.clicked.connect(self._on_remove_clicked)
        layout.addWidget(self.btn_remove)

        layout.addStretch()

    def _on_remove_clicked(self):
        """移除此条件"""
        if self.on_remove:
            self.on_remove(self)

    def set_available_columns(self, columns: List[str]):
        """设置可用的列选项"""
        self.cmb_column.clear()
        self.cmb_column.addItems(columns)

    def get_condition(self) -> Optional[FilterCondition]:
        """获取当前条件"""
        column = self.cmb_column.currentText()
        if not column:
            return None

        operator_text = self.cmb_operator.currentText()
        operator = next(
            (op for op in FilterOperator if op.value == operator_text),
            FilterOperator.EQUALS,
        )

        value = self.inp_value.text()

        if self.cmb_logic:
            logic_text = self.cmb_logic.currentText()
            logic = next(
                (fl for fl in FilterLogic if fl.value == logic_text),
                FilterLogic.AND,
            )
        else:
            logic = FilterLogic.AND

        return FilterCondition(column, operator, value, logic)

    def set_condition(self, condition: FilterCondition):
        """设置条件值"""
        self.cmb_column.setCurrentText(condition.column)
        self.cmb_operator.setCurrentText(condition.operator.value)
        self.inp_value.setText(condition.value)
        if self.cmb_logic:
            self.cmb_logic.setCurrentText(condition.logic.value)
