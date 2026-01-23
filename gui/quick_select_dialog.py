from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# 某些导入在运行时延迟加载以避免循环依赖，允许 import-outside-toplevel
# pylint: disable=import-outside-toplevel



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
        # 减小条目间距，使多个 entry 显示更紧凑
        self.info_layout.setSpacing(6)
        self.info_area.setWidget(self.info_widget)
        # 调整滚动策略并替换角部控件，避免出现样式相关的“奇怪小角块”
        try:
            self.info_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.info_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            # 使用一个空的 QWidget 作为角部控件，覆盖可能的样式残留
            self.info_area.setCornerWidget(QWidget())
        except Exception:
            logger.debug("设置滚动区域角部控件失败", exc_info=True)
        # 确保 info_widget 为不透明背景，避免与上方控件或样式叠加导致的残影
        try:
            bg = self.palette().color(self.backgroundRole()).name()
            self.info_widget.setStyleSheet(f"background-color: {bg};")
            self.info_widget.setAutoFillBackground(True)
        except Exception:
            logger.debug("设置 info_widget 背景失败", exc_info=True)
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
        # 从 GUI 恢复上次快速选择状态（若存在）或同步表格当前选中状态
        try:
            self._restore_state_from_gui()
        except Exception:
            logger.debug("恢复快速选择状态失败", exc_info=True)

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
        from src.special_format_parser import get_part_names, looks_like_special_format

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
        # 在填充后，尝试根据当前表格/特殊格式的选中集合标记项
        try:
            self._sync_items_with_table_selection()
        except Exception:
            logger.debug("快速选择同步表格选中失败", exc_info=True)

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

    def _show_empty_placeholder(self) -> None:
        """在 info area 显示空状态提示，避免出现残留的杂项控件。"""
        try:
            lbl = QLabel("未选择任何项")
            lbl.setStyleSheet("color: #888888; font-style: italic; padding:8px;")
            self.info_layout.addWidget(lbl)
            self.info_layout.addStretch(1)
        except Exception:
            pass

    def _rebuild_entries(self) -> None:
        self._clear_entries()
        selected_items = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it and it.checkState(0) == Qt.Checked:
                selected_items.append(it)
        if not selected_items:
            # 若无选中项，显示占位提示以避免出现残留控件或奇怪的小块
            self._show_empty_placeholder()
            return

        for it in selected_items:
            fp_str, part = it.data(0, Qt.UserRole)
            self._add_entry(fp_str, part)
        self.info_layout.addStretch(1)

    def _add_entry(self, fp_str: str, part: Optional[str]) -> None:
        container = QWidget(self.info_widget)
        v = QVBoxLayout(container)
        # 减小每个 entry 的内边距与间距
        v.setContentsMargins(4, 4, 4, 4)
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
        # 使用 objectName 以便通过 QSS 在暗/亮主题下一致地设定样式
        preview.setObjectName("quickSelectPreview")
        preview.setReadOnly(True)
        preview.setMinimumHeight(64)
        v.addWidget(preview)

        entry = {"key": (fp_str, part), "input": inp, "preview": preview}
        self._entry_widgets.append(entry)
        inp.textChanged.connect(lambda _t, e=entry: self._update_entry_preview(e))
        # 如果之前保存了输入文本，恢复到输入框
        try:
            state = getattr(self.gui, "_quick_select_state", {}) or {}
            key = (fp_str, part)
            saved = state.get(str(key))
            if saved is not None:
                txt = saved.get("rows_text")
                if txt:
                    inp.setText(txt)
        except Exception:
            pass
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
            except ValueError:
                # 非整数输入忽略；避免捕获过宽异常
                pass
        return sorted(set(rows))

    def _format_row_values(self, row_series) -> List[str]:
        """格式化单行的前若干列为字符串列表，失败返回空列表。"""
        try:
            return ["" if v is None else str(v) for v in list(row_series.values)[:6]]
        except Exception:
            logger.debug("格式化行值失败", exc_info=True)
            return []

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

    def _render_rows(
        self, fp_str: str, part: Optional[str], rows: List[int]
    ) -> List[str]:
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
                        vals = self._format_row_values(df.iloc[r])
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
                        vals = self._format_row_values(df.iloc[r])
                        out.append(f"第{r+1}条数据: " + " | ".join(vals))
                return out
        except Exception:
            logger.debug("快速选择预览失败", exc_info=True)
        return []

    # ---------- 应用勾选 ----------
    def apply_changes(self) -> None:
        if not self._entry_widgets:
            return
        gui = getattr(self, "gui", None)
        if gui is None:
            logger.warning("GUI 缺失，无法同步行选择状态")
            return
        try:
            for entry in self._entry_widgets:
                rows = self._parse_rows(entry["input"].text())
                fp_str, part = entry["key"]
                fp = Path(fp_str)

                if not rows:
                    # 空输入：视为“取消跳过”，恢复为全选
                    if part is None:
                        df = self.batch._get_table_df_preview(fp, max_rows=200)
                        row_count = len(df) if df is not None else 0
                        by_file = (
                            getattr(self.gui, "table_row_selection_by_file", {}) or {}
                        )
                        by_file[str(fp)] = set(range(row_count))
                        try:
                            self.gui.table_row_selection_by_file = by_file
                        except Exception:
                            pass
                        table = (self.batch._table_preview_tables or {}).get(str(fp))
                        if table is not None:
                            try:
                                table.selected_set = set(range(row_count))
                                table._rebuild_page()
                            except Exception:
                                pass
                    else:
                        data = self.batch._get_special_data_dict(fp)
                        df = (data or {}).get(str(part))
                        row_count = len(df) if df is not None else 0
                        by_file = (
                            getattr(self.gui, "special_part_row_selection_by_file", {})
                            or {}
                        )
                        by_part = by_file.setdefault(str(fp), {})
                        by_part[str(part)] = set(range(row_count))
                        try:
                            self.gui.special_part_row_selection_by_file = by_file
                        except Exception:
                            pass
                        table = (self.batch._special_preview_tables or {}).get(
                            (str(fp), str(part))
                        )
                        if table is not None:
                            try:
                                table.selected_set = set(range(row_count))
                                table._rebuild_page()
                            except Exception:
                                pass
                    continue

                if part is None:
                    # 普通表格：移除指定行（视为跳过）
                    max_need = max(rows) + 1
                    df = self.batch._get_table_df_preview(
                        fp, max_rows=max(max_need, 200)
                    )
                    row_count = len(df) if df is not None else max_need
                    by_file = getattr(self.gui, "table_row_selection_by_file", {}) or {}
                    cur = by_file.get(str(fp)) or set(range(row_count))
                    by_file[str(fp)] = cur
                    for r in rows:
                        cur.discard(int(r))
                    try:
                        self.gui.table_row_selection_by_file = by_file
                    except Exception:
                        pass
                    table = (self.batch._table_preview_tables or {}).get(str(fp))
                    if table is not None and hasattr(table, "uncheck_rows_if_visible"):
                        table.uncheck_rows_if_visible(rows)
                else:
                    # 特殊格式：移除指定行（视为跳过）
                    data = self.batch._get_special_data_dict(fp)
                    df = (data or {}).get(str(part))
                    row_count = len(df) if df is not None else (max(rows) + 1)
                    by_file = (
                        getattr(self.gui, "special_part_row_selection_by_file", {})
                        or {}
                    )
                    by_part = by_file.setdefault(str(fp), {})
                    sel = by_part.get(str(part))
                    if sel is None:
                        sel = set(range(row_count))
                        by_part[str(part)] = sel
                    for r in rows:
                        sel.discard(int(r))
                    try:
                        self.gui.special_part_row_selection_by_file = by_file
                    except Exception:
                        pass
                    table = (self.batch._special_preview_tables or {}).get(
                        (str(fp), str(part))
                    )
                    if table is not None and hasattr(table, "uncheck_rows_if_visible"):
                        table.uncheck_rows_if_visible(rows)

            # 保存对话框的状态以便下次打开恢复
            try:
                self._save_state_to_gui()
            except Exception:
                logger.debug("保存快速选择状态失败", exc_info=True)
        except Exception:
            logger.debug("快速选择应用失败", exc_info=True)

    # ---------- 接口 ----------
    def accept(self) -> None:
        try:
            self.apply_changes()
        except Exception:
            pass
        try:
            self._save_state_to_gui()
        except Exception:
            pass
        super().accept()

    def reject(self) -> None:
        # 关闭时也保存状态，便于下次打开恢复
        try:
            self._save_state_to_gui()
        except Exception:
            pass
        super().reject()

    # ---------- 状态保存/恢复与同步 ----------
    def _save_state_to_gui(self) -> None:
        try:
            state = getattr(self.gui, "_quick_select_state", {}) or {}
            for i in range(self.tree.topLevelItemCount()):
                it = self.tree.topLevelItem(i)
                if not it:
                    continue
                key = it.data(0, Qt.UserRole)
                if key is None:
                    continue
                kstr = str(key)
                cur = state.get(kstr, {})
                cur["checked"] = it.checkState(0) == Qt.Checked
                # 若存在输入条目，保存文本
                txt = ""
                for e in self._entry_widgets:
                    if e.get("key") == key:
                        try:
                            txt = e.get("input").text() or ""
                        except Exception:
                            txt = ""
                        break
                cur["rows_text"] = txt
                state[kstr] = cur
            try:
                self.gui._quick_select_state = state
            except Exception:
                pass
        except Exception:
            logger.debug("保存快速选择到 GUI 失败", exc_info=True)

    def _restore_state_from_gui(self) -> None:
        try:
            state = getattr(self.gui, "_quick_select_state", {}) or {}
            gui = getattr(self, "gui", None)
            if gui is None:
                logger.warning("GUI 缺失，无法恢复快速选择状态")
                return
            # 第一阶段：根据 state 或 table selection 标记 tree 项
            for i in range(self.tree.topLevelItemCount()):
                it = self.tree.topLevelItem(i)
                if not it:
                    continue
                key = it.data(0, Qt.UserRole)
                if key is None:
                    continue
                fp_str, part = key
                # 优先使用显式保存的状态，但如果 GUI 上存在实时的行选中集合
                # 则以 GUI 的实时选择为准（避免主界面变更后快速选择仍使用过时的保存状态）
                cur = state.get(str(key))
                # 检查 GUI 上是否有实时的选中信息
                try:
                    live_checked = None
                    if part is None:
                        by_file = (
                            getattr(self.gui, "table_row_selection_by_file", {}) or {}
                        )
                        sel = by_file.get(str(fp_str))
                        if sel is not None:
                            live_checked = True
                    else:
                        by_file = (
                            getattr(self.gui, "special_part_row_selection_by_file", {})
                            or {}
                        )
                        by_part = by_file.get(str(fp_str), {}) if by_file else None
                        sel = None
                        if by_part:
                            sel = by_part.get(str(part))
                        if sel is not None:
                            live_checked = True
                except Exception:
                    live_checked = None

                if cur is not None and live_checked is None:
                    # 没有实时信息时使用保存的状态
                    if cur.get("checked"):
                        it.setCheckState(0, Qt.Checked)
                    else:
                        it.setCheckState(0, Qt.Unchecked)
                    continue
                # 如果存在实时信息（由主界面或其他操作更新），优先使用实时信息
                if live_checked:
                    it.setCheckState(0, Qt.Checked)
                    # 不 continue，让后续逻辑用实时选择构建 rows_text
                    continue
                # 否则尝试从 gui 的表格选中集合同步
                try:
                    if part is None:
                        by_file = (
                            getattr(self.gui, "table_row_selection_by_file", {}) or {}
                        )
                        sel = by_file.get(str(fp_str))
                        if sel is not None:
                            it.setCheckState(0, Qt.Checked)
                            # 计算跳过行文本（全量减去选中）
                            df = self.batch._get_table_df_preview(
                                Path(fp_str), max_rows=200
                            )
                            row_count = len(df) if df is not None else 0
                            skipped = []
                            for r in range(row_count):
                                if r not in sel:
                                    skipped.append(str(r + 1))
                            # 保存到临时 state（在 entries构建后恢复到输入框）
                            if skipped:
                                state[str(key)] = {
                                    "checked": True,
                                    "rows_text": ",".join(skipped),
                                }
                            else:
                                state[str(key)] = {"checked": True, "rows_text": ""}
                    else:
                        by_file = (
                            getattr(self.gui, "special_part_row_selection_by_file", {})
                            or {}
                        )
                        by_part = by_file.get(str(fp_str), {}) if by_file else None
                        sel = None
                        if by_part:
                            sel = by_part.get(str(part))
                        if sel is not None:
                            it.setCheckState(0, Qt.Checked)
                            data = self.batch._get_special_data_dict(Path(fp_str))
                            df = (data or {}).get(str(part))
                            row_count = len(df) if df is not None else 0
                            skipped = []
                            for r in range(row_count):
                                if r not in sel:
                                    skipped.append(str(r + 1))
                            if skipped:
                                state[str(key)] = {
                                    "checked": True,
                                    "rows_text": ",".join(skipped),
                                }
                            else:
                                state[str(key)] = {"checked": True, "rows_text": ""}
                except Exception:
                    pass
            # 第二阶段：重建 entries 并把 saved rows_text 填入对应输入框
            self._rebuild_entries()
            try:
                for e in self._entry_widgets:
                    k = e.get("key")
                    saved = state.get(str(k))
                    if saved is not None:
                        txt = saved.get("rows_text", "") or ""
                        if txt:
                            try:
                                e.get("input").setText(txt)
                            except Exception:
                                pass
            except Exception:
                pass
        except Exception:
            logger.debug("恢复快速选择状态失败", exc_info=True)

    def _sync_items_with_table_selection(self) -> None:
        try:
            gui = getattr(self, "gui", None)
            if gui is None:
                logger.warning("GUI 缺失，无法同步快速选择勾选状态")
                return
            # 如果 GUI 上已有表格/特殊格式的选中信息，则将对应项设置为已勾选
            for i in range(self.tree.topLevelItemCount()):
                it = self.tree.topLevelItem(i)
                if not it:
                    continue
                key = it.data(0, Qt.UserRole)
                if not key:
                    continue
                fp_str, part = key
                try:
                    if part is None:
                        by_file = (
                            getattr(self.gui, "table_row_selection_by_file", {}) or {}
                        )
                        if str(fp_str) in by_file:
                            it.setCheckState(0, Qt.Checked)
                    else:
                        by_file = (
                            getattr(self.gui, "special_part_row_selection_by_file", {})
                            or {}
                        )
                        if str(fp_str) in by_file and str(part) in (
                            by_file.get(str(fp_str)) or {}
                        ):
                            it.setCheckState(0, Qt.Checked)
                except Exception:
                    pass
        except Exception:
            logger.debug("同步表格选中到快速选择失败", exc_info=True)
