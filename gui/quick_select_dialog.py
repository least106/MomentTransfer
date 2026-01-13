from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
    QWidget,
    QScrollArea,
)

logger = logging.getLogger(__name__)


class QuickSelectDialog(QDialog):
    """快速选择对话框（按文件/part 分组输入跳过行并即时预览）。"""

    def __init__(self, batch_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快速选择")
        self.resize(820, 560)
        self.batch = batch_manager
        self.gui = getattr(batch_manager, "gui", None)
        self._entry_widgets: list[dict] = []  # 保存 {key, input, preview}

        lay = QVBoxLayout(self)
        desc = QLabel(
            "勾选要操作的项后，会在下方生成对应的输入框。每个输入框填入要跳过的行号（1基，逗号分隔），下方立即显示这些行的数据。"
        )
        lay.addWidget(desc)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["文件名", "part"])
        self.tree.setColumnWidth(0, 380)
        lay.addWidget(self.tree, 1)

        # 信息区（随勾选动态生成），使用滚动区域避免内容过多时溢出
        self.info_area = QScrollArea(self)
        self.info_area.setWidgetResizable(True)
        self.info_widget = QWidget(self.info_area)
        self.info_layout = QVBoxLayout(self.info_widget)
        self.info_layout.setContentsMargins(4, 4, 4, 4)
        self.info_layout.setSpacing(8)
        self.info_area.setWidget(self.info_widget)
        lay.addWidget(self.info_area, 2)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("确定", self)
        btn_cancel = QPushButton("取消", self)
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        self.tree.itemChanged.connect(self._on_item_changed)
        self._populate_items()

    # ---------- 数据与勾选 ----------
    def _iter_files(self) -> List[Path]:
        files = []
        try:
            if hasattr(self.gui, "_file_tree_items"):
                for fp_str in (self.gui._file_tree_items or {}).keys():
                    files.append(Path(fp_str))
        except Exception:
            pass
        return files

    def _populate_items(self) -> None:
        from src.special_format_parser import looks_like_special_format, get_part_names

        try:
            self.tree.blockSignals(True)
            self.tree.clear()
            for fp in self._iter_files():
                try:
                    if looks_like_special_format(fp):
                        for part in get_part_names(fp) or []:
                            it = QTreeWidgetItem([fp.name, str(part)])
                            it.setCheckState(0, Qt.Unchecked)
                            it.setData(0, Qt.UserRole, (str(fp), str(part)))
                            self.tree.addTopLevelItem(it)
                    else:
                        it = QTreeWidgetItem([fp.name, ""])
                        it.setCheckState(0, Qt.Unchecked)
                        it.setData(0, Qt.UserRole, (str(fp), None))
                        self.tree.addTopLevelItem(it)
                except Exception:
                    logger.debug("快速选择行构建失败", exc_info=True)
        finally:
            try:
                self.tree.blockSignals(False)
            except Exception:
                pass

    def _on_item_changed(self, item, column: int) -> None:
        if column != 0:
            return
        self._rebuild_entries()

    # ---------- 行输入与预览 ----------
    def _clear_entries(self) -> None:
        while self.info_layout.count():
            child = self.info_layout.takeAt(0)
            w = child.widget()
            if w is not None:
                w.deleteLater()
        self._entry_widgets.clear()

    def _rebuild_entries(self) -> None:
        self._clear_entries()
        selected_items = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it and it.checkState(0) == Qt.Checked:
                selected_items.append(it)
        if not selected_items:
            return

        for it in selected_items:
            fp_str, part = it.data(0, Qt.UserRole)
            self._add_entry(fp_str, part)
        self.info_layout.addStretch(1)

    def _add_entry(self, fp_str: str, part: Optional[str]) -> None:
        container = QWidget(self.info_widget)
        v = QVBoxLayout(container)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        title = f"文件: {Path(fp_str).name}" + (f"  part: {part}" if part else "")
        lbl = QLabel(title)
        v.addWidget(lbl)

        row = QHBoxLayout()
        row.addWidget(QLabel("跳过行(1基):"))
        inp = QLineEdit()
        inp.setPlaceholderText("如 1,5,10")
        row.addWidget(inp, 1)
        v.addLayout(row)

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setMinimumHeight(80)
        v.addWidget(preview)

        entry = {"key": (fp_str, part), "input": inp, "preview": preview}
        self._entry_widgets.append(entry)
        inp.textChanged.connect(lambda _t, e=entry: self._update_entry_preview(e))
        # 初始更新（空输入不会展示内容）
        self._update_entry_preview(entry)

        self.info_layout.addWidget(container)

    def _parse_rows(self, text: str) -> List[int]:
        txt = (text or "").strip()
        if not txt:
            return []
        rows: List[int] = []
        for seg in txt.split(","):
            s = seg.strip()
            if not s:
                continue
            try:
                n = int(s)
                if n > 0:
                    rows.append(n - 1)  # 转为 0 基
            except Exception:
                pass
        return sorted(set(rows))

    def _update_entry_preview(self, entry: dict) -> None:
        rows = self._parse_rows(entry["input"].text())
        preview: QTextEdit = entry["preview"]
        preview.clear()
        if not rows:
            return
        fp_str, part = entry["key"]
        lines = self._render_rows(fp_str, part, rows)
        if lines:
            preview.setPlainText("\n".join(lines))

    def _render_rows(self, fp_str: str, part: Optional[str], rows: List[int]) -> List[str]:
        """获取指定行的文本表示，便于在预览中展示。"""
        try:
            fp = Path(fp_str)
            max_need = max(rows) + 1 if rows else 0
            if part is None:
                df = self.batch._get_table_df_preview(fp, max_rows=max(max_need, 200))
                if df is None:
                    return []
                out = [f"文件: {fp.name}"]
                for r in rows:
                    if 0 <= r < len(df):
                        vals = []
                        try:
                            vals = [
                                "" if v is None else str(v)
                                for v in list(df.iloc[r].values)[:6]
                            ]
                        except Exception:
                            pass
                        out.append(f"第{r+1}条数据: " + " | ".join(vals))
                return out
            else:
                data = self.batch._get_special_data_dict(fp)
                df = (data or {}).get(str(part))
                if df is None:
                    return []
                out = [f"文件: {fp.name}  part: {part}"]
                for r in rows:
                    if 0 <= r < len(df):
                        vals = []
                        try:
                            vals = [
                                "" if v is None else str(v)
                                for v in list(df.iloc[r].values)[:6]
                            ]
                        except Exception:
                            pass
                        out.append(f"第{r+1}条数据: " + " | ".join(vals))
                return out
        except Exception:
            logger.debug("快速选择预览失败", exc_info=True)
        return []

    # ---------- 应用勾选 ----------
    def apply_changes(self) -> None:
        if not self._entry_widgets:
            return
        try:
            for entry in self._entry_widgets:
                rows = self._parse_rows(entry["input"].text())
                if not rows:
                    continue
                fp_str, part = entry["key"]
                fp = Path(fp_str)
                if part is None:
                    # 普通表格
                    max_need = max(rows) + 1
                    df = self.batch._get_table_df_preview(fp, max_rows=max(max_need, 200))
                    row_count = len(df) if df is not None else max_need
                    sel = self.batch._ensure_table_row_selection_storage(fp, row_count) or set()
                    by_file = getattr(self.gui, "table_row_selection_by_file", {}) or {}
                    cur = by_file.get(str(fp))
                    if cur is None:
                        cur = set()
                        by_file[str(fp)] = cur
                    for r in rows:
                        cur.discard(int(r))
                    self.gui.table_row_selection_by_file = by_file
                    table = (self.batch._table_preview_tables or {}).get(str(fp))
                    if table is not None and hasattr(table, "uncheck_rows_if_visible"):
                        table.uncheck_rows_if_visible(rows)
                else:
                    # 特殊格式
                    data = self.batch._get_special_data_dict(fp)
                    df = (data or {}).get(str(part))
                    row_count = len(df) if df is not None else (max(rows) + 1)
                    by_file = getattr(self.gui, "special_part_row_selection_by_file", {}) or {}
                    by_part = by_file.setdefault(str(fp), {})
                    sel = by_part.get(str(part))
                    if sel is None:
                        sel = set(range(row_count))
                        by_part[str(part)] = sel
                    for r in rows:
                        sel.discard(int(r))
                    self.gui.special_part_row_selection_by_file = by_file
                    table = (self.batch._special_preview_tables or {}).get((str(fp), str(part)))
                    if table is not None and hasattr(table, "uncheck_rows_if_visible"):
                        table.uncheck_rows_if_visible(rows)
        except Exception:
            logger.debug("快速选择应用失败", exc_info=True)

    # ---------- 接口 ----------
    def accept(self) -> None:
        try:
            self.apply_changes()
        except Exception:
            pass
        super().accept()
