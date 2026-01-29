from __future__ import annotations

from typing import Callable, Iterable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class PagedTableWidget(QWidget):
    """带分页与快速筛选跳转的表格容器。

    - 使用 QTableWidget 作为内部表格，仅渲染当前页的数据。
    - 提供 next/prev 翻页，支持“跳过无匹配页”。
    - 提供 set_filter(df, eval_fn) 以设定匹配行，用于快速筛选联动。
    - 为兼容旧逻辑，暴露 rowCount()/cellWidget() 等接口代理到当前页表格。
    """

    def __init__(
        self,
        df,
        selected_set: Optional[set],
        on_toggle: Callable[[int, bool], None],
        *,
        page_size: int = 200,
        max_cols: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.df = df
        self.on_toggle = on_toggle
        self.page_size = max(1, int(page_size))
        self.max_cols = max_cols
        self._current_page = 0
        self._match_flags: Optional[List[bool]] = None  # None 表示未筛选
        self._match_pages: Optional[List[bool]] = None  # 每页是否有匹配

        self.table = QTableWidget(self)
        # 保留原始列名供导出/筛选等逻辑使用（不受 UI 展示标签影响）
        try:
            self._all_column_names = list(df.columns)
        except Exception:
            self._all_column_names = []
        # 当前页面使用的纯列名（不含序号/换行）以及显示用表头（可能包含序号/换行）
        self._column_names: List[str] = []
        self._display_headers: List[str] = []
        self.lbl_page = QLabel(self)
        self.btn_prev = QPushButton("上一页", self)
        self.btn_next = QPushButton("下一页", self)
        for b in (self.btn_prev, self.btn_next):
            b.setObjectName("smallButton")
            b.setMaximumWidth(70)

        self.btn_prev.clicked.connect(lambda: self.goto_prev(True))
        self.btn_next.clicked.connect(lambda: self.goto_next(True))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.btn_prev)
        row.addWidget(self.btn_next)
        row.addStretch(1)
        row.addWidget(self.lbl_page)
        lay.addLayout(row)

        # 初始化选中集合（默认全选）
        self.selected_set = set(selected_set or set(range(len(df))))
        self._rebuild_page()

    # 兼容旧接口（当前页）
    def rowCount(self) -> int:
        return self.table.rowCount()

    def columnCount(self) -> int:
        return self.table.columnCount()

    def cellWidget(self, r: int, c: int):
        return self.table.cellWidget(r, c)

    def setItem(self, r: int, c: int, item: QTableWidgetItem) -> None:
        self.table.setItem(r, c, item)

    # 筛选与页码
    def set_filter_with_df(
        self,
        df,
        evaluator: Optional[Callable[[object], bool]],
        column_name: Optional[str] = None,
    ):
        """根据 evaluator 计算匹配行，并跳转到包含匹配的页。evaluator 接收 df[column_name] 的每个值。"""
        if (
            evaluator is None
            or column_name is None
            or column_name not in df.columns
        ):
            self._match_flags = None
            self._match_pages = None
            # 恢复到当前页（不跳转）
            self._update_page_label()
            return
        flags: List[bool] = []
        try:
            col = df[column_name]
            for v in col.values:
                try:
                    flags.append(bool(evaluator(v)))
                except Exception:
                    flags.append(False)
        except Exception:
            flags = [False] * len(df)
        self._match_flags = flags
        self._recompute_match_pages()
        self._jump_to_first_match_page()

    def _recompute_match_pages(self) -> None:
        if self._match_flags is None:
            self._match_pages = None
            return
        total = len(self.df)
        pages = (total + self.page_size - 1) // self.page_size
        page_has = [False] * max(1, pages)
        for idx, ok in enumerate(self._match_flags):
            if ok:
                p = idx // self.page_size
                if 0 <= p < len(page_has):
                    page_has[p] = True
        self._match_pages = page_has

    def _jump_to_first_match_page(self) -> None:
        if not self._match_pages or not any(self._match_pages):
            # 无匹配，停留当前页
            self._update_page_label()
            return
        for p, has in enumerate(self._match_pages):
            if has:
                self.goto_page(p)
                return

    def goto_prev(self, skip_empty_match_pages: bool = True) -> None:
        if self._current_page <= 0:
            return
        if skip_empty_match_pages and self._match_pages:
            p = self._current_page - 1
            while p >= 0 and not self._match_pages[p]:
                p -= 1
            if p >= 0:
                self.goto_page(p)
                return
        self.goto_page(self._current_page - 1)

    def goto_next(self, skip_empty_match_pages: bool = True) -> None:
        pages = self._page_count()
        if self._current_page >= pages - 1:
            return
        if skip_empty_match_pages and self._match_pages:
            p = self._current_page + 1
            while p < pages and not self._match_pages[p]:
                p += 1
            if p < pages:
                self.goto_page(p)
                return
        self.goto_page(self._current_page + 1)

    def goto_page(self, page_index: int) -> None:
        self._current_page = max(0, min(page_index, self._page_count() - 1))
        self._rebuild_page()

    def _page_count(self) -> int:
        total = len(self.df)
        return max(1, (total + self.page_size - 1) // self.page_size)

    def _rebuild_page(self) -> None:
        # 构建当前页数据
        start = self._current_page * self.page_size
        end = min(len(self.df), start + self.page_size)
        rows = max(0, end - start)
        try:
            if self.max_cols is None:
                cols = len(self.df.columns)
            else:
                cols = min(len(self.df.columns), int(self.max_cols))
        except Exception:
            cols = 0

        self.table.clear()
        self.table.setRowCount(rows)
        self.table.setColumnCount(cols + 1)
        try:
            # 当前页使用的纯列名列表（便于筛选/导出使用）
            self._column_names = list(self._all_column_names[:cols])
            # 构造显示用表头（在列名前加上序号，便于用户识别列索引）
            self._display_headers = ["选中"] + [
                f"{i+1}\n{str(c)}" for i, c in enumerate(self._column_names)
            ]
            self.table.setHorizontalHeaderLabels(self._display_headers)
        except Exception:
            # 在异常情况下依然尝试设置一个简单的头
            try:
                self._column_names = [
                    str(c) for c in self._all_column_names[:cols]
                ]
                self._display_headers = ["选中"] + self._column_names
                self.table.setHorizontalHeaderLabels(self._display_headers)
            except Exception:
                pass

        for i in range(rows):
            real_row = start + i
            cb = QCheckBox()
            cb.setChecked(real_row in self.selected_set)
            cb.stateChanged.connect(
                lambda st, rr=real_row: self._on_cb(rr, st)
            )
            self.table.setCellWidget(i, 0, cb)
            for c in range(cols):
                try:
                    val = self.df.iloc[real_row, c]
                    text = "" if val is None else str(val)
                except Exception:
                    text = ""
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, c + 1, item)
        try:
            self.table.resizeColumnsToContents()
            self.table.resizeRowsToContents()
        except Exception:
            pass
        self._update_page_label()

    def _on_cb(self, real_row: int, state: int) -> None:
        checked = state == Qt.Checked
        if checked:
            self.selected_set.add(real_row)
        else:
            self.selected_set.discard(real_row)
        try:
            self.on_toggle(real_row, checked)
        except Exception:
            pass

    def _update_page_label(self) -> None:
        self.lbl_page.setText(
            f"第 {self._current_page + 1}/{self._page_count()} 页"
        )

    def get_column_names(self) -> List[str]:
        """返回当前表格（当前页）对应的纯列名列表（不含 UI 序号/换行）。"""
        return list(self._column_names)

    def get_display_headers(self) -> List[str]:
        """返回当前表格显示用的表头文本列表（可能包含序号/换行）。"""
        return list(self._display_headers)

    # 批量更新可视页上的复选框（供“快速选择”后刷新当前页显示）
    def uncheck_rows_if_visible(self, rows: Iterable[int]) -> None:
        if not rows:
            return
        start = self._current_page * self.page_size
        end = min(len(self.df), start + self.page_size)
        for r in rows:
            if start <= r < end:
                vis_r = r - start
                cb = self.table.cellWidget(vis_r, 0)
                if cb is not None:
                    cb.setChecked(False)
