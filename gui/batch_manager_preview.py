"""子模块：`batch_manager_preview` — 处理预览表格、分页表与快速筛选的 helper。

这些函数以 `manager`（`BatchManager` 实例）作为第一个参数，以便逐步迁移并保持兼容。

注意：当前处于分步重构阶段，文件中仍存在若干超长行（C0301）。
为便于迭代，我在此临时禁用该规则（后续会逐条修复并移除禁用）。
# pylint: disable=C0301
"""

import logging
import math
from pathlib import Path
from typing import Optional

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QTableWidget, QTableWidgetItem, QTreeWidgetItem

from gui.paged_table import PagedTableWidget

logger = logging.getLogger(__name__)


def _format_preview_value(manager, v):
    """将单元格值格式化为便于显示的字符串（处理 None/NaN 和异常）。"""
    try:
        if v is None:
            return ""
        fv = float(v)
        if math.isnan(fv):
            return ""
        return f"{fv:.6g}"
    except Exception:
        try:
            return str(v)
        except Exception:
            return ""


def _build_row_preview_text(manager, row_index: int, row_series) -> str:
    """构造数据行预览文本（尽量精简，便于在树节点中展示）。"""
    keys = [
        "Alpha",
        "CL",
        "CD",
        "Cm",
        "Cx",
        "Cy",
        "Cz/FN",
        "CMx",
        "CMy",
        "CMz",
    ]
    parts = []
    for k in keys:
        try:
            if k in row_series.index:
                val = _format_preview_value(manager, row_series.get(k))
                if val != "":
                    parts.append(f"{k}={val}")
        except Exception:
            continue
    if not parts:
        return f"第{row_index + 1}行"
    prefix = f"第{row_index + 1}行："
    return prefix + " ".join(parts)


def _create_preview_table(
    manager,
    df,
    selected_set: set,
    on_toggle,
    max_rows: int = 200,
    **kwargs,
):
    """创建带勾选列的数据预览表格（分页版）。"""
    try:
        widget = PagedTableWidget(
            df,
            set(selected_set or set()),
            on_toggle,
            page_size=max(1, int(max_rows)),
            max_cols=kwargs.get("max_cols", None),
        )
        return widget
    except Exception:
        return _make_simple_preview_table(
            df,
            selected_set,
            on_toggle,
            max_rows=max_rows,
            max_cols=kwargs.get("max_cols", None),
        )


def _make_simple_preview_table(
    df,
    selected_set,
    on_toggle,
    *,
    max_rows: int = 200,
    max_cols: int = None,
):
    """当 PagedTableWidget 不可用时，创建普通的 QTableWidget 备选表格。

    该函数独立于 `manager`，便于测试并减少上层函数的参数与局部变量。
    """
    table = QTableWidget()
    rows = min(len(df), int(max_rows))
    if max_cols is None:
        cols = len(df.columns)
    else:
        cols = min(len(df.columns), int(max_cols))
    table.setRowCount(rows)
    table.setColumnCount(cols + 1)
    try:
        table.setHorizontalHeaderLabels(
            ["选中"] + [str(c) for c in list(df.columns)[:cols]]
        )
    except Exception:
        pass

    for r in range(rows):
        cb = QCheckBox()
        try:
            cb.setChecked(r in (selected_set or set()))
        except Exception:
            pass
        try:

            def _cb_state(state, row=r):
                try:
                    on_toggle(row, state == Qt.Checked)
                except Exception:
                    pass

            cb.stateChanged.connect(_cb_state)
        except Exception:
            pass
        table.setCellWidget(r, 0, cb)
        for c in range(cols):
            try:
                val = df.iloc[r, c]
                text = "" if val is None else str(val)
            except Exception:
                text = ""
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, c + 1, item)
    try:
        table.resizeColumnsToContents()
        table.resizeRowsToContents()
    except Exception:
        pass
    return table


def _apply_quick_filter_to_table(table, df, qcol, qval, operator: str) -> None:
    """对常规表格应用快速筛选。

    参数由调用方传入以避免直接访问 protected 属性。
    """
    try:
        if not qcol or not qval:
            # 恢复样式到未筛选状态
            for r in range(table.rowCount()):
                for c in range(1, table.columnCount()):
                    item = table.item(r, c)
                    if item:
                        item.setBackground(QColor(255, 255, 255))
                        item.setForeground(QColor(0, 0, 0))
            return

        if df is None or df.empty or qcol not in df.columns:
            return

        # 优先尝试由分页表格实现的筛选方法
        if _apply_quick_filter_with_paged_table_obj(table, df, operator, qcol, qval):
            return

        _apply_quick_filter_table_iter_obj(table, df, operator, qcol, qval)
    except Exception as e:
        logger.debug(f"应用表格快速筛选失败: {e}", exc_info=True)


def _clear_quick_filter_table(manager, table) -> None:
    get_item = getattr(manager, "_get_table_item", None)
    for r in range(table.rowCount()):
        for c in range(1, table.columnCount()):
            try:
                if callable(get_item):
                    item = get_item(table, r, c)
                else:
                    item = table.item(r, c)
            except Exception:
                try:
                    item = table.item(r, c)
                except Exception:
                    item = None
            if item:
                item.setBackground(QColor(255, 255, 255))
                item.setForeground(QColor(0, 0, 0))


def _apply_quick_filter_table_iter(manager, table, df, operator: str) -> None:
    gray_color = QColor(220, 220, 220)
    text_color = QColor(160, 160, 160)
    qcol = getattr(manager, "_quick_filter_column", None)
    qval = getattr(manager, "_quick_filter_value", None)
    get_item = getattr(manager, "_get_table_item", None)

    for r in range(min(table.rowCount(), len(df))):
        try:
            row_value = df.iloc[r][qcol]
            matches = _evaluate_filter(None, row_value, operator, qval)

            for c in range(1, table.columnCount()):
                try:
                    if callable(get_item):
                        item = get_item(table, r, c)
                    else:
                        item = table.item(r, c)
                except Exception:
                    try:
                        item = table.item(r, c)
                    except Exception:
                        item = None
                if item:
                    if matches:
                        item.setBackground(QColor(255, 255, 255))
                        item.setForeground(QColor(0, 0, 0))
                    else:
                        item.setBackground(gray_color)
                        item.setForeground(text_color)
        except Exception:
            pass


def _apply_quick_filter_with_paged_table(manager, table, df, operator: str) -> bool:
    try:
        if not hasattr(table, "set_filter_with_df"):
            return False

        qcol = getattr(manager, "_quick_filter_column", None)
        qval = getattr(manager, "_quick_filter_value", None)

        def _eval(v):
            return _evaluate_filter(None, v, operator, qval)

        try:
            table.set_filter_with_df(
                df,
                _eval,
                qcol,
            )
            return True
        except Exception:
            return False
    except Exception:
        return False


# pylint: disable=too-many-return-statements,too-many-branches
def _apply_quick_filter_with_paged_table_obj(
    table,
    df,
    operator: str,
    qcol,
    qval,
) -> bool:  # pylint: disable=too-many-return-statements,too-many-branches
    """分页表格的快速筛选实现（不依赖 manager）。"""
    try:
        if not hasattr(table, "set_filter_with_df"):
            return False

        def _eval(v):
            try:
                if operator == "包含":
                    return str(qval).lower() in str(v).lower()
                if operator == "不包含":
                    return str(qval).lower() not in str(v).lower()
                if operator in ["=", "≠", "<", ">", "≤", "≥", "≈"]:
                    try:
                        val = float(v)
                        flt = float(qval)
                    except (ValueError, TypeError):
                        return False
                    # 复用比较逻辑
                    if operator == "≈":
                        if abs(flt) > 1e-10:
                            return abs(val - flt) / abs(flt) < 0.01
                        return abs(val - flt) < 1e-10
                    if operator == "=":
                        return abs(val - flt) < 1e-10
                    if operator == "≠":
                        return abs(val - flt) >= 1e-10
                    if operator == "<":
                        return val < flt
                    if operator == ">":
                        return val > flt
                    if operator == "≤":
                        return val <= flt
                    if operator == "≥":
                        return val >= flt
                return False
            except Exception:
                return False

        try:
            table.set_filter_with_df(df, _eval, qcol)
            return True
        except Exception:
            return False
    except Exception:
        return False


def _apply_quick_filter_table_iter_obj(table, df, operator: str, qcol, qval) -> None:
    """非分页表格的快速筛选实现（不依赖 manager）。"""
    gray_color = QColor(220, 220, 220)
    text_color = QColor(160, 160, 160)

    for r in range(min(table.rowCount(), len(df))):
        try:
            row_value = df.iloc[r][qcol]
            # 复用 _evaluate_filter 的逻辑，但传入显式参数
            matches = _evaluate_filter(None, row_value, operator, qval)

            for c in range(1, table.columnCount()):
                try:
                    item = table.item(r, c)
                except Exception:
                    item = None
                if item:
                    if matches:
                        item.setBackground(QColor(255, 255, 255))
                        item.setForeground(QColor(0, 0, 0))
                    else:
                        item.setBackground(gray_color)
                        item.setForeground(text_color)
        except Exception:
            pass


def _evaluate_filter(
    manager, row_value, operator: str, filter_value: str
) -> bool:  # pylint: disable=too-many-return-statements,too-many-branches
    try:
        if operator == "包含":
            return str(filter_value).lower() in str(row_value).lower()
        if operator == "不包含":
            return str(filter_value).lower() not in str(row_value).lower()
        ops = ("=", "≠", "<", ">", "≤", "≥", "≈")
        if operator in ops:
            try:
                val = float(row_value)
                flt = float(filter_value)
            except (ValueError, TypeError):
                return False
            return _compare_numeric(manager, val, flt, operator)
        return False
    except Exception:
        return False


def _compare_numeric(
    manager, val: float, flt: float, operator: str
) -> bool:  # pylint: disable=too-many-return-statements,too-many-branches
    try:
        if operator == "≈":
            if abs(flt) > 1e-10:
                return abs(val - flt) / abs(flt) < 0.01
            return abs(val - flt) < 1e-10
        if operator == "=":
            return abs(val - flt) < 1e-10
        if operator == "≠":
            return abs(val - flt) >= 1e-10
        if operator == "<":
            return val < flt
        if operator == ">":
            return val > flt
        if operator == "≤":
            return val <= flt
        if operator == "≥":
            return val >= flt
    except Exception:
        return False
    return False


def _apply_quick_filter_to_special_table(
    manager,
    table,
    file_path_str: str,
    source_part: str,
) -> None:
    try:
        qcol = getattr(manager, "_quick_filter_column", None)
        qval = getattr(manager, "_quick_filter_value", None)
        operator = getattr(manager, "_quick_filter_operator", None)

        if not qcol or not qval:
            _clear_quick_filter_table(manager, table)
            return

        file_path_obj = Path(file_path_str)
        get_special = getattr(manager, "_get_special_data_dict", None)
        data_dict = get_special(file_path_obj) if callable(get_special) else {}
        df = data_dict.get(source_part)
        if df is None or df.empty:
            return
        if qcol not in df.columns:
            return
        # operator/qval 已提前读取
        try:
            if hasattr(table, "set_filter_with_df"):
                # 使用提前获取的值，避免再次访问 manager 的受保护属性
                def _eval(v):
                    return _evaluate_filter(None, v, operator, qval)

                table.set_filter_with_df(df, _eval, qcol)
                return
        except Exception:
            pass

        _apply_quick_filter_special_iter_obj(table, df, operator, qcol, qval)
    except Exception as e:
        logger.debug(f"应用特殊格式表格快速筛选失败: {e}", exc_info=True)


def _apply_quick_filter_special_iter(manager, table, df, operator: str) -> None:
    gray_color = QColor(220, 220, 220)
    text_color = QColor(160, 160, 160)
    qcol = getattr(manager, "_quick_filter_column", None)
    qval = getattr(manager, "_quick_filter_value", None)
    get_item = getattr(manager, "_get_table_item", None)

    for r in range(min(table.rowCount(), len(df))):
        try:
            row_value = df.iloc[r][qcol]
            matches = _evaluate_filter(None, row_value, operator, qval)

            for c in range(1, table.columnCount()):
                try:
                    if callable(get_item):
                        item = get_item(table, r, c)
                    else:
                        item = table.item(r, c)
                except Exception:
                    try:
                        item = table.item(r, c)
                    except Exception:
                        item = None
                if item:
                    if matches:
                        item.setBackground(QColor(255, 255, 255))
                        item.setForeground(QColor(0, 0, 0))
                    else:
                        item.setBackground(gray_color)
                        item.setForeground(text_color)
        except Exception:
            pass


def _apply_quick_filter_special_iter_obj(table, df, operator: str, qcol, qval) -> None:
    """特殊表格（特殊格式）的非分页筛选实现（不依赖 manager）。"""
    gray_color = QColor(220, 220, 220)
    text_color = QColor(160, 160, 160)

    for r in range(min(table.rowCount(), len(df))):
        try:
            row_value = df.iloc[r][qcol]
            matches = _evaluate_filter(None, row_value, operator, qval)

            for c in range(1, table.columnCount()):
                try:
                    item = table.item(r, c)
                except Exception:
                    item = None
                if item:
                    if matches:
                        item.setBackground(QColor(255, 255, 255))
                        item.setForeground(QColor(0, 0, 0))
                    else:
                        item.setBackground(gray_color)
                        item.setForeground(text_color)
        except Exception:
            pass


def _build_table_row_preview_text(manager, row_index: int, row_series) -> str:
    try:
        values = []
        try:
            for v in list(row_series.values)[:6]:
                s = ""
                try:
                    if v is None:
                        s = ""
                    else:
                        s = str(v)
                except Exception:
                    s = ""
                values.append(s)
        except Exception:
            values = []
        if values:
            return f"第{row_index + 1}行：" + " | ".join(values)
    except Exception:
        pass
    return f"第{row_index + 1}行"


def _get_table_df_preview(manager, file_path: Path, *, max_rows: int = 200):
    fp_str = str(file_path)
    try:
        mtime = file_path.stat().st_mtime
    except Exception:
        mtime = None

    cached = getattr(manager, "_table_data_cache", {}).get(fp_str)
    if (
        cached
        and cached.get("mtime") == mtime
        and cached.get("df") is not None
        and cached.get("preview_rows") == int(max_rows)
    ):
        return cached.get("df")

    try:

        def _csv_has_header(path: Path) -> bool:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    first_line = fh.readline()
                if not first_line:
                    return False
                if "," in first_line:
                    tokens = [t.strip() for t in first_line.split(",")]
                elif "\t" in first_line:
                    tokens = [t.strip() for t in first_line.split("\t")]
                else:
                    tokens = first_line.split()
                non_numeric = 0
                total = 0
                for t in tokens:
                    if not t:
                        continue
                    total += 1
                    try:
                        float(t)
                    except Exception:
                        non_numeric += 1
                return total > 0 and non_numeric >= max(1, total // 2)
            except Exception:
                return False

        if file_path.suffix.lower() == ".csv":
            header_opt = 0 if _csv_has_header(file_path) else None
            df = pd.read_csv(file_path, header=header_opt, nrows=int(max_rows))
        else:
            df = pd.read_excel(file_path, header=None)
            try:
                df = df.head(int(max_rows))
            except Exception:
                pass
    except Exception:
        logger.debug("读取表格预览失败", exc_info=True)
        df = None

    td = getattr(manager, "_table_data_cache", None)
    if td is None:
        setattr(manager, "_table_data_cache", {})
        td = getattr(manager, "_table_data_cache")
    td[fp_str] = {
        "mtime": mtime,
        "df": df,
        "preview_rows": int(max_rows),
    }
    return df


def _ensure_table_row_selection_storage(
    manager,
    file_path: Path,
    row_count: int,
) -> Optional[set]:
    try:
        if not hasattr(manager.gui, "table_row_selection_by_file"):
            manager.gui.table_row_selection_by_file = {}
        by_file = getattr(manager.gui, "table_row_selection_by_file", {}) or {}
        fp_str = str(file_path)
        sel = by_file.get(fp_str)
        if sel is None:
            by_file[fp_str] = set(range(int(row_count)))
            sel = by_file[fp_str]
        manager.gui.table_row_selection_by_file = by_file
        return sel
    except Exception:
        return None


def _populate_table_data_rows(manager, file_item, file_path: Path, df) -> None:
    if df is None:
        return

    fp_str = str(file_path)
    _clear_preview_group(
        manager,
        file_item,
        ("table_data_group",),
        table_store=getattr(manager, "_table_preview_tables", None),
        store_key=fp_str,
    )

    group = QTreeWidgetItem(["数据行预览", ""])
    group.setData(
        0,
        int(Qt.UserRole) + 1,
        {
            "kind": "table_data_group",
            "file": fp_str,
        },
    )
    file_item.addChild(group)

    try:
        sel = _ensure_table_row_selection_storage(manager, file_path, len(df)) or set()
    except Exception:
        sel = set()

    _embed_preview_table(
        manager,
        group,
        df,
        fp_str,
        sel=sel,
        is_special=False,
    )


def _make_preview_toggle_callback(
    manager,
    *,
    is_special: bool = False,
    fp_local=None,
    source_part=None,
):
    def _cb(row_idx: int, checked: bool):
        try:
            fp_local_inner = fp_local
            sp_local_inner = None
            if source_part is not None:
                sp_local_inner = str(source_part)
            if is_special:
                if not hasattr(manager.gui, "special_part_row_selection_by_file"):
                    manager.gui.special_part_row_selection_by_file = {}
                by_file_local = getattr(
                    manager.gui, "special_part_row_selection_by_file", {}
                )
                by_file_local = by_file_local or {}
                by_part_local = by_file_local.setdefault(fp_local_inner, {})
                sel_local = by_part_local.get(sp_local_inner)
                if sel_local is None:
                    sel_local = set()
                    by_part_local[sp_local_inner] = sel_local
                if checked:
                    sel_local.add(int(row_idx))
                else:
                    sel_local.discard(int(row_idx))
                manager.gui.special_part_row_selection_by_file = by_file_local
            else:
                if not hasattr(manager.gui, "table_row_selection_by_file"):
                    manager.gui.table_row_selection_by_file = {}
                by_file_local = getattr(manager.gui, "table_row_selection_by_file", {})
                by_file_local = by_file_local or {}
                sel_local = by_file_local.get(fp_local_inner)
                if sel_local is None:
                    sel_local = set()
                    by_file_local[fp_local_inner] = sel_local
                if checked:
                    sel_local.add(int(row_idx))
                else:
                    sel_local.discard(int(row_idx))
                manager.gui.table_row_selection_by_file = by_file_local
        except Exception:
            logger.debug("preview table toggle failed", exc_info=True)

    return _cb


def _apply_preview_filters(
    manager,
    table,
    df,
    fp_str,
    *,
    is_special: bool = False,
    source_part=None,
):  # pylint: disable=too-many-arguments
    try:
        if hasattr(manager.gui, "batch_panel"):
            try:
                manager.gui.batch_panel.update_filter_columns(list(df.columns))
            except Exception:
                pass
    except Exception:
        pass

    try:
        if is_special:
            _apply_quick_filter_to_special_table(manager, table, fp_str, source_part)
        else:
            # 将筛选参数从 manager 中提取出来并传递给无依赖实现
            qcol = getattr(manager, "_quick_filter_column", None)
            qval = getattr(manager, "_quick_filter_value", None)
            operator = getattr(manager, "_quick_filter_operator", None)
            _apply_quick_filter_to_table(table, df, qcol, qval, operator)
    except Exception:
        pass


def _embed_preview_table(manager, group, df, fp_str, sel=None, **kwargs):
    is_special = bool(kwargs.get("is_special", False))
    source_part = kwargs.get("source_part", None)

    if is_special:
        table_store = getattr(manager, "_special_preview_tables", None)
        store_key = (
            fp_str,
            str(source_part) if source_part is not None else None,
        )
    else:
        table_store = getattr(manager, "_table_preview_tables", None)
        store_key = fp_str

    callback = _make_preview_toggle_callback(
        manager, is_special=is_special, fp_local=fp_str, source_part=source_part
    )

    table = _create_preview_table(
        manager, df, set(sel or set()), callback, max_rows=200, max_cols=None
    )
    try:
        manager.gui.file_tree.setItemWidget(group, 0, table)
        try:
            if table_store is not None:
                table_store[store_key] = table
        except Exception:
            pass

        try:
            _apply_preview_filters(
                manager,
                table,
                df,
                fp_str,
                is_special=is_special,
                source_part=source_part,
            )
        except Exception:
            pass
    except Exception:
        logger.debug("embed preview table failed", exc_info=True)

    try:
        group.setExpanded(False)
    except Exception:
        pass


def _populate_special_data_rows(
    manager,
    part_item,
    file_path: Path,
    source_part: str,
    df,
) -> None:
    fp_str = str(file_path)
    try:
        by_file = getattr(manager.gui, "special_part_row_selection_by_file", {}) or {}
        by_part = by_file.setdefault(fp_str, {})
        sel = by_part.get(source_part)
    except Exception:
        by_part = {}
        sel = None

    if sel is None:
        try:
            sel = set(range(len(df)))
            by_part[source_part] = sel
            if not hasattr(manager.gui, "special_part_row_selection_by_file"):
                manager.gui.special_part_row_selection_by_file = {}
            tmp_map = manager.gui.special_part_row_selection_by_file.setdefault(
                fp_str,
                {},
            )
            tmp_map[source_part] = sel
        except Exception:
            sel = set()

    _clear_preview_group(
        manager,
        part_item,
        ("special_data_row", "special_data_table"),
        table_store=getattr(manager, "_special_preview_tables", None),
        store_key=(fp_str, str(source_part)),
    )

    group = QTreeWidgetItem(["数据行预览", ""])
    group.setData(
        0,
        int(Qt.UserRole) + 1,
        {
            "kind": "special_data_table",
            "file": fp_str,
            "source": str(source_part),
        },
    )
    part_item.addChild(group)

    _embed_preview_table(
        manager,
        group,
        df,
        fp_str,
        sel=sel,
        is_special=True,
        source_part=source_part,
    )


def _clear_preview_group(
    manager,
    parent_item,
    kind_names,
    table_store=None,
    store_key=None,
):
    try:
        for i in range(parent_item.childCount() - 1, -1, -1):
            try:
                child = parent_item.child(i)
                get_meta = getattr(manager, "_get_item_meta", None)
                try:
                    meta = get_meta(child) if callable(get_meta) else None
                except Exception:
                    meta = None
                if isinstance(meta, dict) and meta.get("kind") in kind_names:
                    parent_item.removeChild(child)
            except Exception:
                pass
    except Exception:
        pass
