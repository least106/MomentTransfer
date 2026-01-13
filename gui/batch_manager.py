"""批处理管理模块 - 处理批处理相关功能"""

import fnmatch
import logging
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
)

from src.format_registry import get_format_for_file
from src.special_format_parser import (
    looks_like_special_format,
    get_part_names,
    parse_special_format_file,
)

logger = logging.getLogger(__name__)


class BatchManager:
    """批处理管理器 - 管理批处理相关操作"""

    def __init__(self, gui_instance):
        """初始化批处理管理器"""
        self.gui = gui_instance
        self.batch_thread = None
        self._bus_connected = False

        # 特殊格式：缓存每个文件的 source->target 映射控件
        # key: (file_path_str, source_part)
        self._special_part_combo = {}

        # 特殊格式：缓存解析结果，避免频繁全量解析
        # key: file_path_str -> {"mtime": float, "data": Dict[str, DataFrame]}
        self._special_data_cache = {}

        # 常规表格（CSV/Excel）：缓存预览数据，避免频繁读取
        # key: file_path_str -> {"mtime": float, "df": DataFrame, "preview_rows": int}
        self._table_data_cache = {}

        # 文件树批量更新标记，避免 itemChanged 递归触发
        self._is_updating_tree = False

        # 预览表格控件映射，便于批量全选/反选
        # 特殊格式：key=(file_path_str, source_part) -> QTableWidget
        self._special_preview_tables = {}
        # 常规表格：key=file_path_str -> QTableWidget
        self._table_preview_tables = {}

        # 快速筛选状态
        self._quick_filter_column = ""
        self._quick_filter_operator = "包含"
        self._quick_filter_value = ""

        # 连接文件树交互与配置/Part 变更事件
        self._connect_ui_signals()
        self._connect_signal_bus_events()
        self._connect_quick_filter()

    def _connect_ui_signals(self) -> None:
        """连接文件树与 SignalBus 事件，保证状态/映射随配置变化刷新。"""
        try:
            if (
                hasattr(self.gui, "file_tree")
                and self.gui.file_tree is not None
            ):
                try:
                    self.gui.file_tree.itemClicked.connect(
                        self._on_file_tree_item_clicked
                    )
                except Exception:
                    logger.debug(
                        "连接 file_tree.itemClicked 失败", exc_info=True
                    )
                try:
                    self.gui.file_tree.itemChanged.connect(
                        self._on_file_tree_item_changed
                    )
                except Exception:
                    logger.debug(
                        "连接 file_tree.itemChanged 失败", exc_info=True
                    )
        except Exception:
            pass

    def _connect_signal_bus_events(self) -> None:
        """将配置/Part 变更信号与文件状态刷新绑定（只注册一次）。"""
        if self._bus_connected:
            return
        try:
            bus = getattr(self.gui, "signal_bus", None)
            if bus is None:
                return
            try:
                bus.configLoaded.connect(
                    lambda _m=None: self.refresh_file_statuses()
                )
            except Exception:
                pass
            try:
                bus.configApplied.connect(lambda: self.refresh_file_statuses())
            except Exception:
                pass
            try:
                bus.partAdded.connect(
                    lambda _side=None, _name=None: self.refresh_file_statuses()
                )
            except Exception:
                pass
            try:
                bus.partRemoved.connect(
                    lambda _side=None, _name=None: self.refresh_file_statuses()
                )
            except Exception:
                pass
            self._bus_connected = True
        except Exception:
            logger.debug("连接 SignalBus 刷新事件失败", exc_info=True)

    def _connect_quick_filter(self) -> None:
        """连接快速筛选信号"""
        try:
            if hasattr(self.gui, "batch_panel") and hasattr(
                self.gui.batch_panel, "quickFilterChanged"
            ):
                self.gui.batch_panel.quickFilterChanged.connect(
                    self._on_quick_filter_changed
                )
                logger.info("快速筛选信号连接成功")
            else:
                logger.warning(
                    "快速筛选信号连接失败：batch_panel 或 quickFilterChanged 不存在"
                )
        except Exception as e:
            logger.error(f"连接快速筛选信号失败: {e}", exc_info=True)

    def _on_quick_filter_changed(
        self, column: str, operator: str, value: str
    ) -> None:
        """快速筛选条件变化，刷新所有表格的行显示"""
        try:
            logger.info(
                f"快速筛选变化: 列={column}, 运算符={operator}, 值={value}"
            )
            self._quick_filter_column = column
            self._quick_filter_operator = operator
            self._quick_filter_value = value

            # 刷新所有常规表格
            for fp_str, table in list(self._table_preview_tables.items()):
                try:
                    self._apply_quick_filter_to_table(table, fp_str)
                except Exception:
                    logger.debug(f"刷新表格筛选 {fp_str} 失败", exc_info=True)

            # 刷新所有特殊格式表格
            for (fp_str, source_part), table in list(
                self._special_preview_tables.items()
            ):
                try:
                    self._apply_quick_filter_to_special_table(
                        table, fp_str, source_part
                    )
                except Exception:
                    logger.debug(
                        f"刷新特殊格式表格筛选 {fp_str}/{source_part} 失败",
                        exc_info=True,
                    )
        except Exception:
            logger.debug("快速筛选刷新失败", exc_info=True)

    def open_quick_select_dialog(self) -> None:
        """打开“快速选择”对话框，支持多文件/part 批量取消勾选指定行。"""
        try:
            from gui.quick_select_dialog import QuickSelectDialog
            dlg = QuickSelectDialog(self, parent=self.gui)
            dlg.exec()
        except Exception as e:
            logger.error(f"快速选择对话框失败: {e}")

    def _get_item_meta(self, item):
        """读取文件树节点元信息（保存在 Qt.UserRole+1）。"""
        try:
            return item.data(0, int(Qt.UserRole) + 1)
        except Exception:
            return None

    def _ensure_special_row_selection_storage(
        self, file_path: Path, part_names: list
    ) -> dict:
        """确保行选择缓存存在，并为未初始化的 part 默认全选。"""
        try:
            if not hasattr(self.gui, "special_part_row_selection_by_file"):
                self.gui.special_part_row_selection_by_file = {}
            by_file = (
                getattr(self.gui, "special_part_row_selection_by_file", {})
                or {}
            )
            by_file.setdefault(str(file_path), {})
            self.gui.special_part_row_selection_by_file = by_file

            by_part = by_file[str(file_path)]
            for pn in part_names:
                by_part.setdefault(str(pn), None)
            return by_part
        except Exception:
            return {}

    def _get_special_data_dict(self, file_path: Path):
        """获取特殊格式解析结果（带 mtime 缓存）。"""
        fp_str = str(file_path)
        try:
            mtime = file_path.stat().st_mtime
        except Exception:
            mtime = None

        cached = self._special_data_cache.get(fp_str)
        if (
            cached
            and cached.get("mtime") == mtime
            and cached.get("data") is not None
        ):
            return cached.get("data")

        try:
            data_dict = parse_special_format_file(file_path)
        except Exception:
            logger.debug("解析特殊格式文件失败", exc_info=True)
            data_dict = {}

        self._special_data_cache[fp_str] = {"mtime": mtime, "data": data_dict}
        return data_dict

    def _build_row_preview_text(self, row_index: int, row_series) -> str:
        """构造数据行预览文本（尽量精简，便于在树节点中展示）。"""

        def _fmt(v):
            try:
                if v is None:
                    return ""
                # pandas 可能返回 numpy 标量
                fv = float(v)
                if fv != fv:  # NaN
                    return ""
                return f"{fv:.6g}"
            except Exception:
                try:
                    return str(v)
                except Exception:
                    return ""

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
                    val = _fmt(row_series.get(k))
                    if val != "":
                        parts.append(f"{k}={val}")
            except Exception:
                continue
        if not parts:
            return f"第{row_index + 1}行"
        # 显示全部已格式化的列键值对，而不是仅前6项
        return f"第{row_index + 1}行：" + " ".join(parts)

    def _create_preview_table(
        self,
        df,
        selected_set: set,
        on_toggle,
        *,
        max_rows: int = 200,
        max_cols: int = None,
    ):
        """创建带勾选列的数据预览表格（分页版）。

        为了适配 5000+ 行数据，使用分页容器 PagedTableWidget，其中每页默认显示
        max_rows 行，并内置上一页/下一页按钮，且与快速筛选联动。
        """
        try:
            from gui.paged_table import PagedTableWidget
        except Exception:
            # 回退：若导入失败，使用旧表格方式
            table = QTableWidget()
            rows = min(len(df), int(max_rows))
            if max_cols is None:
                cols = len(df.columns)
            else:
                cols = min(len(df.columns), int(max_cols))
            table.setRowCount(rows)
            table.setColumnCount(cols + 1)
            try:
                headers = ["选中"] + [str(c) for c in list(df.columns)[:cols]]
                table.setHorizontalHeaderLabels(headers)
            except Exception:
                pass
            for r in range(rows):
                cb = QCheckBox()
                cb.setChecked(r in (selected_set or set()))
                try:
                    cb.stateChanged.connect(
                        lambda state, row=r: on_toggle(row, state == Qt.Checked)
                    )
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

        widget = PagedTableWidget(
            df,
            set(selected_set or set()),
            on_toggle,
            page_size=max(1, int(max_rows)),
            max_cols=max_cols,
        )
        return widget

    def _apply_quick_filter_to_table(
        self, table, file_path_str: str
    ) -> None:
        """对常规表格应用快速筛选。

        - 若为分页表格，调用其 set_filter_with_df 以联动翻页。
        - 否则回退为灰显不匹配行。
        """
        try:
            from PySide6.QtGui import QColor

            # 如果没有筛选条件，恢复所有行
            if not self._quick_filter_column or not self._quick_filter_value:
                for r in range(table.rowCount()):
                    for c in range(1, table.columnCount()):  # 跳过勾选列
                        item = table.item(r, c)
                        if item:
                            item.setBackground(QColor(255, 255, 255))
                            item.setForeground(QColor(0, 0, 0))
                return

            # 获取数据
            cached = self._table_data_cache.get(file_path_str)
            if not cached or cached.get("df") is None:
                return

            df = cached.get("df")
            if (
                df is None
                or df.empty
                or self._quick_filter_column not in df.columns
            ):
                return

            # 分页组件联动：优先使用分页表格的筛选跳页
            try:
                # 避免循环导入，仅通过 duck-typing 调用
                if hasattr(table, "set_filter_with_df"):
                    def _eval(v):
                        return self._evaluate_filter(v, operator, self._quick_filter_value)
                    table.set_filter_with_df(df, _eval, self._quick_filter_column)
                    return
            except Exception:
                pass

            # 应用筛选
            gray_color = QColor(220, 220, 220)
            text_color = QColor(160, 160, 160)
            operator = self._quick_filter_operator

            for r in range(min(table.rowCount(), len(df))):
                try:
                    row_value = df.iloc[r][self._quick_filter_column]
                    matches = self._evaluate_filter(
                        row_value, operator, self._quick_filter_value
                    )

                    for c in range(1, table.columnCount()):  # 跳过勾选列
                        item = table.item(r, c)
                        if item:
                            if matches:
                                item.setBackground(QColor(255, 255, 255))
                                item.setForeground(QColor(0, 0, 0))
                            else:
                                item.setBackground(gray_color)
                                item.setForeground(text_color)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"应用表格快速筛选失败: {e}", exc_info=True)

    def _evaluate_filter(
        self, row_value, operator: str, filter_value: str
    ) -> bool:
        """评估筛选条件是否匹配"""
        try:
            if operator == "包含":
                return str(filter_value).lower() in str(row_value).lower()
            elif operator == "不包含":
                return str(filter_value).lower() not in str(row_value).lower()
            elif operator in ["=", "≠", "<", ">", "≤", "≥", "≈"]:
                # 数值比较
                try:
                    val = float(row_value)
                    flt = float(filter_value)
                except (ValueError, TypeError):
                    return False

                if operator == "=":
                    return abs(val - flt) < 1e-10
                elif operator == "≠":
                    return abs(val - flt) >= 1e-10
                elif operator == "<":
                    return val < flt
                elif operator == ">":
                    return val > flt
                elif operator == "≤":
                    return val <= flt
                elif operator == "≥":
                    return val >= flt
                elif operator == "≈":
                    # 近似相等（误差在1%以内）
                    if abs(flt) > 1e-10:
                        return abs(val - flt) / abs(flt) < 0.01
                    else:
                        return abs(val - flt) < 1e-10
            return False
        except Exception:
            return False

    def _apply_quick_filter_to_special_table(
        self, table, file_path_str: str, source_part: str
    ) -> None:
        """对特殊格式表格应用快速筛选。

        - 若为分页表格，调用其 set_filter_with_df 以联动翻页。
        - 否则回退为灰显不匹配行。
        """
        try:
            from PySide6.QtGui import QColor

            # 如果没有筛选条件，恢复所有行
            if not self._quick_filter_column or not self._quick_filter_value:
                for r in range(table.rowCount()):
                    for c in range(1, table.columnCount()):
                        item = table.item(r, c)
                        if item:
                            item.setBackground(QColor(255, 255, 255))
                            item.setForeground(QColor(0, 0, 0))
                return

            # 获取数据
            data_dict = self._get_special_data_dict(Path(file_path_str))
            df = data_dict.get(source_part)
            if (
                df is None
                or df.empty
                or self._quick_filter_column not in df.columns
            ):
                return

            # 分页组件联动
            try:
                if hasattr(table, "set_filter_with_df"):
                    def _eval(v):
                        return self._evaluate_filter(v, operator, self._quick_filter_value)
                    table.set_filter_with_df(df, _eval, self._quick_filter_column)
                    return
            except Exception:
                pass

            # 应用筛选
            gray_color = QColor(220, 220, 220)
            text_color = QColor(160, 160, 160)
            operator = self._quick_filter_operator

            for r in range(min(table.rowCount(), len(df))):
                try:
                    row_value = df.iloc[r][self._quick_filter_column]
                    matches = self._evaluate_filter(
                        row_value, operator, self._quick_filter_value
                    )

                    for c in range(1, table.columnCount()):
                        item = table.item(r, c)
                        if item:
                            if matches:
                                item.setBackground(QColor(255, 255, 255))
                                item.setForeground(QColor(0, 0, 0))
                            else:
                                item.setBackground(gray_color)
                                item.setForeground(text_color)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"应用特殊格式表格快速筛选失败: {e}", exc_info=True)

    def _build_table_row_preview_text(self, row_index: int, row_series) -> str:
        """构造表格（CSV/Excel）数据行预览文本。"""
        try:
            values = []
            try:
                # 只显示前 6 列，避免树节点过长
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

    def _get_table_df_preview(self, file_path: Path, *, max_rows: int = 200):
        """读取 CSV/Excel 的预览数据（带 mtime 缓存）。"""
        fp_str = str(file_path)
        try:
            mtime = file_path.stat().st_mtime
        except Exception:
            mtime = None

        cached = self._table_data_cache.get(fp_str)
        if (
            cached
            and cached.get("mtime") == mtime
            and cached.get("df") is not None
            and cached.get("preview_rows") == int(max_rows)
        ):
            return cached.get("df")

        try:
            import pandas as pd

            def _csv_has_header(path: Path) -> bool:
                """简单探测：首行含非数值token则视为表头。"""
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        first_line = fh.readline()
                    if not first_line:
                        return False
                    # 逗号/制表符分隔
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
                    # 至少半数非数值，认为是表头
                    return total > 0 and non_numeric >= max(1, total // 2)
                except Exception:
                    return False

            # 预览统一使用“原始表格内容”（不依赖列映射）
            if file_path.suffix.lower() == ".csv":
                header_opt = 0 if _csv_has_header(file_path) else None
                df = pd.read_csv(
                    file_path, header=header_opt, nrows=int(max_rows)
                )
            else:
                # Excel 默认按原始内容预览，不强制表头
                df = pd.read_excel(file_path, header=None)
                try:
                    df = df.head(int(max_rows))
                except Exception:
                    pass
        except Exception:
            logger.debug("读取表格预览失败", exc_info=True)
            df = None

        self._table_data_cache[fp_str] = {
            "mtime": mtime,
            "df": df,
            "preview_rows": int(max_rows),
        }
        return df

    def _ensure_table_row_selection_storage(
        self, file_path: Path, row_count: int
    ) -> Optional[set]:
        """确保常规表格的行选择缓存存在（默认全选）。"""
        try:
            if not hasattr(self.gui, "table_row_selection_by_file"):
                self.gui.table_row_selection_by_file = {}
            by_file = (
                getattr(self.gui, "table_row_selection_by_file", {}) or {}
            )
            fp_str = str(file_path)
            sel = by_file.get(fp_str)
            if sel is None:
                by_file[fp_str] = set(range(int(row_count)))
                sel = by_file[fp_str]
            self.gui.table_row_selection_by_file = by_file
            return sel
        except Exception:
            return None

    def _find_special_part_item(self, fp_str: str, source_part: str):
        """根据文件与part名在树中查找对应part节点。"""
        try:
            file_item = getattr(self.gui, "_file_tree_items", {}).get(fp_str)
            if file_item is None:
                return None
            for i in range(file_item.childCount()):
                child = file_item.child(i)
                meta = self._get_item_meta(child)
                if (
                    isinstance(meta, dict)
                    and meta.get("kind") == "special_part"
                ):
                    if str(meta.get("source") or "") == str(source_part):
                        return child
        except Exception:
            pass
        return None

    def _populate_table_data_rows(
        self, file_item, file_path: Path, df
    ) -> None:
        """为常规表格文件创建数据行预览表格（带勾选列）。"""
        from PySide6.QtWidgets import QTreeWidgetItem

        if df is None:
            return

        fp_str = str(file_path)
        # 清理旧的表格预览 group 和 widget 引用
        for i in range(file_item.childCount() - 1, -1, -1):
            try:
                child = file_item.child(i)
                meta = self._get_item_meta(child)
                if (
                    isinstance(meta, dict)
                    and meta.get("kind") == "table_data_group"
                ):
                    try:
                        self.gui.file_tree.removeItemWidget(child, 0)
                    except Exception:
                        pass
                    file_item.removeChild(child)
            except Exception:
                pass
        try:
            self._table_preview_tables.pop(fp_str, None)
        except Exception:
            pass

        group = QTreeWidgetItem(["数据行预览", ""])
        group.setData(
            0,
            int(Qt.UserRole) + 1,
            {"kind": "table_data_group", "file": fp_str},
        )
        file_item.addChild(group)

        try:
            sel = (
                self._ensure_table_row_selection_storage(file_path, len(df))
                or set()
            )
        except Exception:
            sel = set()

        def _on_toggle(row_idx: int, checked: bool, *, fp_local=fp_str):
            try:
                if not hasattr(self.gui, "table_row_selection_by_file"):
                    self.gui.table_row_selection_by_file = {}
                by_file_local = (
                    getattr(self.gui, "table_row_selection_by_file", {}) or {}
                )
                sel_local = by_file_local.get(fp_local)
                if sel_local is None:
                    sel_local = set()
                    by_file_local[fp_local] = sel_local
                if checked:
                    sel_local.add(int(row_idx))
                else:
                    sel_local.discard(int(row_idx))
                self.gui.table_row_selection_by_file = by_file_local
            except Exception:
                logger.debug("table toggle failed", exc_info=True)

        table = self._create_preview_table(
            df, set(sel or set()), _on_toggle, max_rows=200, max_cols=None
        )
        try:
            self.gui.file_tree.setItemWidget(group, 0, table)
            self._table_preview_tables[fp_str] = table

            # 更新快速筛选列选项
            try:
                if hasattr(self.gui, "batch_panel"):
                    self.gui.batch_panel.update_filter_columns(
                        list(df.columns)
                    )
            except Exception:
                pass

            # 应用当前筛选
            try:
                self._apply_quick_filter_to_table(table, fp_str)
            except Exception:
                pass
        except Exception:
            logger.debug("embed table preview failed", exc_info=True)

        try:
            group.setExpanded(False)
        except Exception:
            pass

    def _populate_special_data_rows(
        self, part_item, file_path: Path, source_part: str, df
    ) -> None:
        """为某个 part 节点创建数据行预览表格（带勾选列）。"""
        from PySide6.QtWidgets import QTreeWidgetItem

        fp_str = str(file_path)
        try:
            by_file = (
                getattr(self.gui, "special_part_row_selection_by_file", {})
                or {}
            )
            by_part = by_file.setdefault(fp_str, {})
            sel = by_part.get(source_part)
        except Exception:
            by_part = {}
            sel = None

        # 默认全选
        if sel is None:
            try:
                sel = set(range(len(df)))
                by_part[source_part] = sel
                if not hasattr(self.gui, "special_part_row_selection_by_file"):
                    self.gui.special_part_row_selection_by_file = {}
                self.gui.special_part_row_selection_by_file.setdefault(
                    fp_str, {}
                )[source_part] = sel
            except Exception:
                sel = set()

        # 清理旧的预览节点和表格引用
        for i in range(part_item.childCount() - 1, -1, -1):
            try:
                child = part_item.child(i)
                meta = self._get_item_meta(child)
                if isinstance(meta, dict) and meta.get("kind") in (
                    "special_data_row",
                    "special_data_table",
                ):
                    try:
                        self.gui.file_tree.removeItemWidget(child, 0)
                    except Exception:
                        pass
                    part_item.removeChild(child)
            except Exception:
                pass
        try:
            self._special_preview_tables.pop((fp_str, str(source_part)), None)
        except Exception:
            pass

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

        def _on_toggle(
            row_idx: int,
            checked: bool,
            *,
            fp_local=fp_str,
            sp_local=str(source_part),
        ):
            try:
                if not hasattr(self.gui, "special_part_row_selection_by_file"):
                    self.gui.special_part_row_selection_by_file = {}
                by_file_local = (
                    getattr(self.gui, "special_part_row_selection_by_file", {})
                    or {}
                )
                by_part_local = by_file_local.setdefault(fp_local, {})
                sel_local = by_part_local.get(sp_local)
                if sel_local is None:
                    sel_local = set()
                    by_part_local[sp_local] = sel_local
                if checked:
                    sel_local.add(int(row_idx))
                else:
                    sel_local.discard(int(row_idx))
                self.gui.special_part_row_selection_by_file = by_file_local
            except Exception:
                logger.debug("special table toggle failed", exc_info=True)

        table = self._create_preview_table(
            df, set(sel or set()), _on_toggle, max_rows=200, max_cols=None
        )
        try:
            self.gui.file_tree.setItemWidget(group, 0, table)
            self._special_preview_tables[(fp_str, str(source_part))] = table

            # 更新快速筛选列选项
            try:
                if hasattr(self.gui, "batch_panel"):
                    self.gui.batch_panel.update_filter_columns(
                        list(df.columns)
                    )
            except Exception:
                pass

            # 应用当前筛选
            try:
                self._apply_quick_filter_to_special_table(
                    table, fp_str, source_part
                )
            except Exception:
                pass
        except Exception:
            logger.debug("embed special preview table failed", exc_info=True)

        try:
            group.setExpanded(False)
        except Exception:
            pass

    def _on_file_tree_item_changed(self, item, column: int) -> None:
        """监听数据行复选框变化，同步到 selection 缓存。"""
        if self._is_updating_tree:
            return
        if column != 0:
            return
        try:
            meta = self._get_item_meta(item)
            if not isinstance(meta, dict):
                return

            kind = meta.get("kind")
            if kind == "special_data_row":
                fp_str = str(meta.get("file") or "")
                source = str(meta.get("source") or "")
                row_idx = meta.get("row")
                if not fp_str or not source or row_idx is None:
                    return

                if not hasattr(self.gui, "special_part_row_selection_by_file"):
                    self.gui.special_part_row_selection_by_file = {}
                by_file = (
                    getattr(self.gui, "special_part_row_selection_by_file", {})
                    or {}
                )
                by_part = by_file.setdefault(fp_str, {})
                sel = by_part.get(source)
                if sel is None:
                    sel = set()
                    by_part[source] = sel

                checked = item.checkState(0) == Qt.Checked
                try:
                    idx_int = int(row_idx)
                except Exception:
                    return

                if checked:
                    sel.add(idx_int)
                else:
                    sel.discard(idx_int)

                self.gui.special_part_row_selection_by_file = by_file
                return

            if kind == "table_data_row":
                fp_str = str(meta.get("file") or "")
                row_idx = meta.get("row")
                if not fp_str or row_idx is None:
                    return
                if not hasattr(self.gui, "table_row_selection_by_file"):
                    self.gui.table_row_selection_by_file = {}
                by_file = (
                    getattr(self.gui, "table_row_selection_by_file", {}) or {}
                )
                sel = by_file.get(fp_str)
                if sel is None:
                    sel = set()
                    by_file[fp_str] = sel

                checked = item.checkState(0) == Qt.Checked
                try:
                    idx_int = int(row_idx)
                except Exception:
                    return

                if checked:
                    sel.add(idx_int)
                else:
                    sel.discard(idx_int)
                self.gui.table_row_selection_by_file = by_file
                return
        except Exception:
            logger.debug("处理数据行勾选变化失败", exc_info=True)

        # SignalBus 事件在初始化阶段已注册

    def browse_batch_input(self):
        """浏览并选择输入文件或目录，沿用 GUI 原有文件列表面板。"""
        try:
            dlg = QFileDialog(self.gui, "选择输入文件或目录")
            dlg.setOption(QFileDialog.DontUseNativeDialog, True)
            dlg.setFileMode(QFileDialog.ExistingFile)
            dlg.setNameFilter(
                "Data Files (*.csv *.xlsx *.xls *.mtfmt *.mtdata *.txt *.dat);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls);;MomentTransfer (*.mtfmt *.mtdata)"
            )

            # 允许切换目录模式
            from PySide6.QtWidgets import QCheckBox

            chk_dir = QCheckBox("选择目录（切换到目录选择模式）")
            chk_dir.setToolTip(
                "勾选后可以直接选择文件夹；不勾选则选择单个数据文件。"
            )
            try:
                layout = dlg.layout()
                layout.addWidget(chk_dir)
            except Exception:
                pass

            def on_toggle_dir(checked):
                if checked:
                    dlg.setFileMode(QFileDialog.Directory)
                    dlg.setOption(QFileDialog.ShowDirsOnly, True)
                else:
                    dlg.setFileMode(QFileDialog.ExistingFile)
                    dlg.setOption(QFileDialog.ShowDirsOnly, False)

            chk_dir.toggled.connect(on_toggle_dir)

            if dlg.exec() != QDialog.Accepted:
                return

            selected = dlg.selectedFiles()
            if not selected:
                return

            chosen_path = Path(selected[0])
            if hasattr(self.gui, "inp_batch_input"):
                self.gui.inp_batch_input.setText(str(chosen_path))

            # 统一由 BatchManager 扫描并填充文件列表
            self._scan_and_populate_files(chosen_path)

            # 输入路径后自动切换到文件列表页
            try:
                if hasattr(self.gui, "tab_main"):
                    self.gui.tab_main.setCurrentIndex(0)  # 文件列表在第0个Tab
            except Exception:
                pass

        except Exception as e:
            logger.error(f"浏览输入失败: {e}")
            QMessageBox.critical(self.gui, "错误", f"浏览失败: {e}")

    def _scan_and_populate_files(self, chosen_path: Path):
        """扫描所选路径并在文件树中显示（支持目录结构，默认全选）。"""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem

        try:
            p = Path(chosen_path)
            # 根据所选路径类型启用/禁用匹配模式控件：
            try:
                # 当选择单个文件时，将匹配模式控件与输入框灰掉，避免用户误操作；选择目录时恢复
                is_file = p.is_file()
                # 设置启用/禁用
                if (
                    hasattr(self.gui, "inp_pattern")
                    and self.gui.inp_pattern is not None
                ):
                    self.gui.inp_pattern.setEnabled(not is_file)
                    try:
                        if is_file:
                            self.gui.inp_pattern.setStyleSheet(
                                "color: gray; background-color: #f0f0f0"
                            )
                        else:
                            self.gui.inp_pattern.setStyleSheet("")
                    except Exception:
                        pass
                if (
                    hasattr(self.gui, "cmb_pattern_preset")
                    and self.gui.cmb_pattern_preset is not None
                ):
                    self.gui.cmb_pattern_preset.setEnabled(not is_file)
                    try:
                        if is_file:
                            self.gui.cmb_pattern_preset.setStyleSheet(
                                "color: gray; background-color: #f0f0f0"
                            )
                        else:
                            self.gui.cmb_pattern_preset.setStyleSheet("")
                    except Exception:
                        pass
            except Exception:
                logger.debug("设置匹配控件/输入框启用状态失败", exc_info=True)
            files = []

            if p.is_file():
                files = [p]
                try:
                    self.gui.output_dir = p.parent
                except Exception:
                    pass
            elif p.is_dir():
                # 支持分号分隔多模式：*.csv;*.xlsx
                pattern_text = "*.csv"
                try:
                    if (
                        hasattr(self.gui, "inp_pattern")
                        and self.gui.inp_pattern is not None
                    ):
                        pt = self.gui.inp_pattern.text().strip()
                        if pt:
                            pattern_text = pt
                except Exception:
                    pass

                patterns = [
                    x.strip() for x in pattern_text.split(";") if x.strip()
                ]
                if not patterns:
                    patterns = ["*.csv"]

                for file_path in p.rglob("*"):
                    if not file_path.is_file():
                        continue
                    if any(
                        fnmatch.fnmatch(file_path.name, pat)
                        for pat in patterns
                    ):
                        files.append(file_path)
                files = sorted(set(files))

                try:
                    self.gui.output_dir = p
                except Exception:
                    pass

            # 检查UI组件是否存在
            if not hasattr(self.gui, "file_tree"):
                return

            # 清空旧的树项
            self.gui.file_tree.clear()
            self.gui._file_tree_items = {}

            if not files:
                try:
                    self.gui.file_list_widget.setVisible(False)
                except Exception:
                    pass
                return

            # 步骤2：进入文件列表选择阶段
            try:
                bp = getattr(self.gui, "batch_panel", None)
                if bp is not None and hasattr(bp, "set_workflow_step"):
                    bp.set_workflow_step("step2")
            except Exception:
                pass
            try:
                self.gui.statusBar().showMessage(
                    "步骤2：在文件列表选择数据文件"
                )
            except Exception:
                pass

            # 构建目录树结构
            # 获取所有文件的共同根目录
            if p.is_file():
                base_path = p.parent
            else:
                base_path = p

            # 创建目录节点的字典：{relative_dir_path: QTreeWidgetItem}
            dir_items = {}

            for fp in files:
                # 计算相对路径
                try:
                    rel_path = fp.relative_to(base_path)
                except ValueError:
                    # 如果文件不在base_path下，直接显示完整路径
                    rel_path = fp

                # 构建父目录节点
                parts = rel_path.parts[:-1]  # 不包括文件名
                parent_item = None
                current_path = Path()

                for part in parts:
                    current_path = current_path / part
                    if current_path not in dir_items:
                        # 创建目录节点
                        dir_item = QTreeWidgetItem([str(part), ""])
                        dir_item.setData(
                            0, Qt.UserRole, None
                        )  # 目录节点不存储路径

                        if parent_item is None:
                            self.gui.file_tree.addTopLevelItem(dir_item)
                        else:
                            parent_item.addChild(dir_item)

                        dir_items[current_path] = dir_item
                        parent_item = dir_item
                    else:
                        parent_item = dir_items[current_path]

                # 创建文件节点
                file_item = QTreeWidgetItem([rel_path.name, ""])
                file_item.setCheckState(0, Qt.Checked)  # 默认选中
                file_item.setData(0, Qt.UserRole, str(fp))  # 存储完整路径

                # 单文件模式下：仅禁用复选框，防止用户取消选中，但不灰显整行
                try:
                    if p.is_file():
                        # 确保复选框保持选中
                        file_item.setCheckState(0, Qt.Checked)
                        # 移除用户交互修改复选框的标志，但保留项可见和可选中
                        flags = file_item.flags()
                        file_item.setFlags(flags & ~Qt.ItemIsUserCheckable)
                        # 添加提示说明
                        try:
                            file_item.setToolTip(
                                0, "单文件模式，无法修改选择状态"
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

                # 验证配置：检查target name是否存在
                status_text = self._validate_file_config(fp)
                file_item.setText(1, status_text)

                if parent_item is None:
                    self.gui.file_tree.addTopLevelItem(file_item)
                else:
                    parent_item.addChild(file_item)

                self.gui._file_tree_items[str(fp)] = file_item

            # 展开所有节点
            self.gui.file_tree.expandAll()

            # 显示文件列表区域
            try:
                self.gui.file_list_widget.setVisible(True)
            except Exception:
                pass

            logger.info(f"已扫描到 {len(files)} 个文件")

        except Exception as e:
            logger.error(f"扫描并填充文件列表失败: {e}")
            import traceback

            traceback.print_exc()

    def _validate_file_config(self, file_path: Path) -> str:
        """验证文件的配置，返回状态文本"""
        try:
            # 特殊格式：提前检查 part 是否存在于当前配置
            try:
                if looks_like_special_format(file_path):
                    part_names = get_part_names(file_path)

                    # 特殊格式约定：part_name 视为 source part；target 通过映射或同名 target 兜底
                    mapping = None
                    try:
                        mapping = (
                            getattr(
                                self.gui, "special_part_mapping_by_file", {}
                            )
                            or {}
                        ).get(str(file_path))
                    except Exception:
                        mapping = None

                    # 读取可用的 source/target parts
                    source_parts = {}
                    target_parts = {}
                    try:
                        model = getattr(self.gui, "project_model", None)
                        if model is not None:
                            source_parts = (
                                getattr(model, "source_parts", {}) or {}
                            )
                            target_parts = (
                                getattr(model, "target_parts", {}) or {}
                            )
                    except Exception:
                        pass
                    try:
                        cfg = getattr(self.gui, "current_config", None)
                        if cfg is not None:
                            source_parts = source_parts or (
                                getattr(cfg, "source_parts", {}) or {}
                            )
                            target_parts = target_parts or (
                                getattr(cfg, "target_parts", {}) or {}
                            )
                    except Exception:
                        pass

                    # 若尚未加载/创建任何配置（source/target 都为空），不要给出“缺失”提示
                    if not source_parts and not target_parts:
                        return "✓ 特殊格式(待配置)"

                    missing_source = [
                        pn for pn in part_names if pn not in source_parts
                    ]
                    if missing_source:
                        return f"⚠ Source缺失: {', '.join(missing_source)}"

                    mapping = mapping or {}
                    unmapped = []
                    missing_target = []
                    for pn in part_names:
                        tp = (mapping.get(pn) or "").strip()
                        if not tp:
                            # 未显式映射：仅允许同名 target
                            if pn in target_parts:
                                tp = pn
                            else:
                                unmapped.append(pn)
                                continue
                        if tp not in target_parts:
                            missing_target.append(f"{pn}->{tp}")

                    if unmapped:
                        return f"⚠ 未映射: {', '.join(unmapped)}"
                    if missing_target:
                        return f"⚠ Target缺失: {', '.join(missing_target)}"
                    return "✓ 特殊格式(可处理)"
            except Exception:
                logger.debug("特殊格式预检查失败", exc_info=True)

            # 使用缓存机制读取文件头部用于格式检测
            from src.file_cache import get_file_cache
            from src.cli_helpers import resolve_file_format, BatchConfig

            cache = get_file_cache()

            # 尝试从缓存获取格式信息
            cached_format = cache.get_metadata(file_path, "format_info")
            if cached_format:
                fmt_info = cached_format
            else:
                # 构造BatchConfig用于格式解析
                base_cfg = BatchConfig(skip_rows=0, columns={}, passthrough=[])

                fmt_info = resolve_file_format(
                    str(file_path),
                    base_cfg,
                    enable_sidecar=True,
                    registry_db=getattr(self.gui, "_registry_db", None),
                )

                # 缓存格式信息
                if fmt_info:
                    cache.set_metadata(file_path, "format_info", fmt_info)

            if not fmt_info:
                return "❌ 未知格式"

            # 常规格式：若已加载配置，则要求为该文件选择 source/target（除非唯一可推断）
            project_data = getattr(self.gui, "current_config", None)
            if project_data is None:
                return "✓ 格式正常(待配置)"

            sel = (
                getattr(self.gui, "file_part_selection_by_file", {}) or {}
            ).get(str(file_path)) or {}
            source_sel = (sel.get("source") or "").strip()
            target_sel = (sel.get("target") or "").strip()

            try:
                source_names = list(
                    (getattr(project_data, "source_parts", {}) or {}).keys()
                )
                target_names = list(
                    (getattr(project_data, "target_parts", {}) or {}).keys()
                )
            except Exception:
                source_names, target_names = [], []

            # 允许“唯一 part 自动选取”的兜底
            if not source_sel and len(source_names) == 1:
                source_sel = str(source_names[0])
            if not target_sel and len(target_names) == 1:
                target_sel = str(target_names[0])

            if not source_sel or not target_sel:
                return "⚠ 未选择 Source/Target"
            if source_names and source_sel not in source_names:
                return f"⚠ Source缺失: {source_sel}"
            if target_names and target_sel not in target_names:
                return f"⚠ Target缺失: {target_sel}"

            return "✓ 可处理"

        except Exception as e:
            logger.debug(f"验证文件配置失败: {e}")
            return "❓ 未验证"

    def _on_file_tree_item_clicked(self, item, _column: int):
        """点击文件项后：更新步骤提示，并在文件树内展示 source->target 映射。

        注意：不再自动弹出配置编辑器；由用户在文件列表勾选“显示配置编辑器”后再显示。
        """
        try:
            fp = item.data(0, Qt.UserRole)
            if not fp:
                return
            file_path = Path(str(fp))
            if not file_path.exists():
                return
            try:
                self.gui.statusBar().showMessage(
                    "步骤3：如需编辑配置请勾选“显示配置编辑器”；步骤4：在文件列表设置映射"
                )
            except Exception:
                pass

            # 特殊格式：为该文件建立映射编辑区（无弹窗）
            try:
                if looks_like_special_format(file_path):
                    self._ensure_special_mapping_rows(item, file_path)
                else:
                    # 常规文件：为该文件建立 source/target 选择区（无弹窗）
                    self._ensure_regular_file_selector_rows(item, file_path)
                    # 常规文件：为该文件建立数据行预览与勾选（无弹窗）
                    try:
                        df_preview = self._get_table_df_preview(
                            file_path, max_rows=200
                        )
                        if df_preview is not None:
                            self._populate_table_data_rows(
                                item, file_path, df_preview
                            )
                    except Exception:
                        logger.debug("填充表格数据行预览失败", exc_info=True)
            except Exception:
                logger.debug(
                    "ensure special mapping rows failed", exc_info=True
                )
        except Exception:
            logger.debug("_on_file_tree_item_clicked failed", exc_info=True)

    def _get_target_part_names(self) -> list:
        """获取当前可选 Target part 名称列表。"""
        names = []
        try:
            model = getattr(self.gui, "project_model", None)
            if model is not None:
                names = list((getattr(model, "target_parts", {}) or {}).keys())
        except Exception:
            names = []
        if not names:
            try:
                cfg = getattr(self.gui, "current_config", None)
                names = list((getattr(cfg, "target_parts", {}) or {}).keys())
            except Exception:
                names = []
        return sorted([str(x) for x in names])

    def _get_source_part_names(self) -> list:
        """获取当前可选 Source part 名称列表。"""
        names = []
        try:
            model = getattr(self.gui, "project_model", None)
            if model is not None:
                names = list((getattr(model, "source_parts", {}) or {}).keys())
        except Exception:
            names = []
        if not names:
            try:
                cfg = getattr(self.gui, "current_config", None)
                names = list((getattr(cfg, "source_parts", {}) or {}).keys())
            except Exception:
                names = []
        return sorted([str(x) for x in names])

    def _infer_part_from_text(
        self, text: str, candidate_names: list
    ) -> Optional[str]:
        """从给定文本推测匹配的 part 名（必须唯一命中）。"""
        try:
            src = (text or "").strip()
            if not src:
                return None
            cands = [str(x) for x in (candidate_names or []) if str(x).strip()]
            if not cands:
                return None

            if src in cands:
                return src

            src_lower = src.lower()
            ci = [t for t in cands if t.lower() == src_lower]
            if len(ci) == 1:
                return ci[0]

            def norm(s: str) -> str:
                try:
                    return "".join(
                        ch
                        for ch in (s or "")
                        if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff")
                    ).lower()
                except Exception:
                    return (s or "").lower()

            src_norm = norm(src)
            if not src_norm:
                return None
            nm = [t for t in cands if norm(t) == src_norm]
            if len(nm) == 1:
                return nm[0]
        except Exception:
            logger.debug("推测 part 失败", exc_info=True)
        return None

    def _ensure_file_part_selection_storage(self, file_path: Path) -> dict:
        """确保常规文件的 source/target 选择缓存存在。"""
        try:
            if not hasattr(self.gui, "file_part_selection_by_file"):
                self.gui.file_part_selection_by_file = {}
            by_file = (
                getattr(self.gui, "file_part_selection_by_file", {}) or {}
            )
            by_file.setdefault(str(file_path), {"source": "", "target": ""})
            self.gui.file_part_selection_by_file = by_file
            return by_file[str(file_path)]
        except Exception:
            return {"source": "", "target": ""}

    def _ensure_regular_file_selector_rows(
        self, file_item, file_path: Path
    ) -> None:
        """为常规文件创建 source/target 选择行（树内联下拉）。"""
        from PySide6.QtWidgets import QTreeWidgetItem, QComboBox

        try:
            sel = self._ensure_file_part_selection_storage(file_path)
            source_names = self._get_source_part_names()
            target_names = self._get_target_part_names()

            # 智能推测：首次进入时，尝试用文件名推测
            try:
                stem = file_path.stem
                if not (sel.get("source") or "").strip() and source_names:
                    inferred_s = self._infer_part_from_text(stem, source_names)
                    if inferred_s:
                        sel["source"] = inferred_s
                if not (sel.get("target") or "").strip() and target_names:
                    inferred_t = self._infer_part_from_text(stem, target_names)
                    if inferred_t:
                        sel["target"] = inferred_t
            except Exception:
                pass

            # 清理旧的 selector 子节点（避免重复）
            for i in range(file_item.childCount() - 1, -1, -1):
                try:
                    child = file_item.child(i)
                    meta = self._get_item_meta(child)
                    if isinstance(meta, dict) and meta.get("kind") in (
                        "file_source_selector",
                        "file_target_selector",
                    ):
                        file_item.removeChild(child)
                except Exception:
                    pass

            # Source selector
            src_item = QTreeWidgetItem(["Source Part", ""])
            src_item.setData(
                0,
                int(Qt.UserRole) + 1,
                {"kind": "file_source_selector", "file": str(file_path)},
            )
            file_item.addChild(src_item)

            src_combo = QComboBox(self.gui.file_tree)
            src_combo.setEditable(False)
            src_combo.setMinimumWidth(160)
            src_combo.addItem("（未选择）", "")
            for n in source_names:
                src_combo.addItem(n, n)
            if not source_names:
                src_combo.setEnabled(False)
                src_combo.setToolTip("请先加载配置以获得 Source parts")

            current_src = (sel.get("source") or "").strip()
            try:
                src_combo.blockSignals(True)
                if current_src and current_src in source_names:
                    src_combo.setCurrentText(current_src)
                else:
                    src_combo.setCurrentIndex(0)
            finally:
                src_combo.blockSignals(False)

            def _on_src_changed(text: str, *, fp_str=str(file_path)):
                try:
                    d = (
                        getattr(self.gui, "file_part_selection_by_file", {})
                        or {}
                    ).setdefault(fp_str, {"source": "", "target": ""})
                    d["source"] = (text or "").strip()
                    try:
                        node = getattr(self.gui, "_file_tree_items", {}).get(
                            fp_str
                        )
                        if node is not None:
                            node.setText(
                                1, self._validate_file_config(Path(fp_str))
                            )
                    except Exception:
                        pass
                except Exception:
                    logger.debug("更新文件 source 选择失败", exc_info=True)

            src_combo.currentTextChanged.connect(_on_src_changed)
            self.gui.file_tree.setItemWidget(src_item, 1, src_combo)

            # Target selector
            tgt_item = QTreeWidgetItem(["Target Part", ""])
            tgt_item.setData(
                0,
                int(Qt.UserRole) + 1,
                {"kind": "file_target_selector", "file": str(file_path)},
            )
            file_item.addChild(tgt_item)

            tgt_combo = QComboBox(self.gui.file_tree)
            tgt_combo.setEditable(False)
            tgt_combo.setMinimumWidth(160)
            tgt_combo.addItem("（未选择）", "")
            for n in target_names:
                tgt_combo.addItem(n, n)
            if not target_names:
                tgt_combo.setEnabled(False)
                tgt_combo.setToolTip("请先加载配置以获得 Target parts")

            current_tgt = (sel.get("target") or "").strip()
            try:
                tgt_combo.blockSignals(True)
                if current_tgt and current_tgt in target_names:
                    tgt_combo.setCurrentText(current_tgt)
                else:
                    tgt_combo.setCurrentIndex(0)
            finally:
                tgt_combo.blockSignals(False)

            def _on_tgt_changed(text: str, *, fp_str=str(file_path)):
                try:
                    d = (
                        getattr(self.gui, "file_part_selection_by_file", {})
                        or {}
                    ).setdefault(fp_str, {"source": "", "target": ""})
                    d["target"] = (text or "").strip()
                    try:
                        node = getattr(self.gui, "_file_tree_items", {}).get(
                            fp_str
                        )
                        if node is not None:
                            node.setText(
                                1, self._validate_file_config(Path(fp_str))
                            )
                    except Exception:
                        pass
                except Exception:
                    logger.debug("更新文件 target 选择失败", exc_info=True)

            tgt_combo.currentTextChanged.connect(_on_tgt_changed)
            self.gui.file_tree.setItemWidget(tgt_item, 1, tgt_combo)

            try:
                file_item.setExpanded(True)
            except Exception:
                pass
        except Exception:
            logger.debug(
                "_ensure_regular_file_selector_rows failed", exc_info=True
            )

    def _infer_target_part(
        self, source_part: str, target_names: list
    ) -> Optional[str]:
        """智能推测 source->target 映射。

        规则（从强到弱，且必须唯一命中才返回）：
        1) 完全同名
        2) 忽略大小写同名
        3) 归一化（去掉空格/下划线/连字符等分隔符）后同名

        注意：该推测只用于“默认填充”，不会覆盖用户手动设置的映射。
        """
        try:
            sp = (source_part or "").strip()
            if not sp:
                return None
            tns = [str(x) for x in (target_names or []) if str(x).strip()]
            if not tns:
                return None

            # 1) 完全同名
            if sp in tns:
                return sp

            # 2) 忽略大小写
            sp_lower = sp.lower()
            ci = [t for t in tns if t.lower() == sp_lower]
            if len(ci) == 1:
                return ci[0]

            # 3) 归一化：仅保留字母/数字/中文
            def norm(s: str) -> str:
                try:
                    s2 = "".join(
                        ch
                        for ch in (s or "")
                        if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff")
                    )
                    return s2.lower()
                except Exception:
                    return (s or "").lower()

            sp_norm = norm(sp)
            if not sp_norm:
                return None
            nm = [t for t in tns if norm(t) == sp_norm]
            if len(nm) == 1:
                return nm[0]

            return None
        except Exception:
            logger.debug("推测 target part 失败", exc_info=True)
            return None

    def _auto_fill_special_mappings(
        self,
        file_path: Path,
        part_names: list,
        target_names: list,
        mapping: dict,
    ) -> bool:
        """为某个文件自动补全未映射的 source->target。

        Returns:
            是否发生了映射变更。
        """
        changed = False
        try:
            if mapping is None or not isinstance(mapping, dict):
                return False
            for sp in part_names or []:
                sp = str(sp)
                # 不覆盖用户已选映射
                if (mapping.get(sp) or "").strip():
                    continue
                inferred = self._infer_target_part(sp, target_names)
                if inferred:
                    mapping[sp] = inferred
                    changed = True
        except Exception:
            logger.debug("自动补全映射失败", exc_info=True)
        return changed

    def _ensure_special_mapping_rows(self, file_item, file_path: Path) -> None:
        """在文件节点下创建/刷新子节点：每个 source part 一行，右侧为 target 下拉。"""
        from PySide6.QtWidgets import QTreeWidgetItem, QComboBox

        try:
            mapping_by_file = getattr(
                self.gui, "special_part_mapping_by_file", None
            )
            if mapping_by_file is None:
                self.gui.special_part_mapping_by_file = {}
                mapping_by_file = self.gui.special_part_mapping_by_file

            mapping_by_file.setdefault(str(file_path), {})
            mapping = mapping_by_file[str(file_path)]

            part_names = get_part_names(file_path)
            target_names = self._get_target_part_names()

            # 智能推测：在加载配置/新增 part 后自动补全未映射项（不覆盖用户已设置的映射）
            try:
                if target_names:
                    if self._auto_fill_special_mappings(
                        file_path, part_names, target_names, mapping
                    ):
                        mapping_by_file[str(file_path)] = mapping
                        self.gui.special_part_mapping_by_file = mapping_by_file
            except Exception:
                logger.debug("自动补全映射失败", exc_info=True)

            # 行选择缓存：确保存在（首次默认全选）
            self._ensure_special_row_selection_storage(file_path, part_names)

            # 特殊格式解析数据：用于生成数据行预览
            data_dict = self._get_special_data_dict(file_path)

            # 清理旧的子节点与 widget 引用（避免 target part 列表变化后残留）
            for i in range(file_item.childCount() - 1, -1, -1):
                try:
                    child = file_item.child(i)
                    file_item.removeChild(child)
                except Exception:
                    pass

            for source_part in part_names:
                child = QTreeWidgetItem([str(source_part), ""])
                # 子节点不应被当作“文件项”，因此 Qt.UserRole 保持为空
                child.setData(
                    0,
                    int(Qt.UserRole) + 1,
                    {
                        "kind": "special_part",
                        "file": str(file_path),
                        "source": str(source_part),
                    },
                )
                file_item.addChild(child)

                combo = QComboBox(self.gui.file_tree)
                combo.setEditable(False)
                combo.setMinimumWidth(160)
                combo.addItem("（未选择）", "")
                for tn in target_names:
                    combo.addItem(tn, tn)

                # 若尚无任何 Target part，则禁用，提示用户先加载/创建
                if not target_names:
                    combo.setEnabled(False)
                    combo.setToolTip("请先加载配置或创建 Target Part")
                else:
                    combo.setEnabled(True)
                    combo.setToolTip("选择该 Source part 对应的 Target part")

                # 恢复已选值
                current = (mapping or {}).get(source_part) or ""
                try:
                    combo.blockSignals(True)
                    if current and current in target_names:
                        combo.setCurrentText(current)
                    else:
                        combo.setCurrentIndex(0)
                finally:
                    combo.blockSignals(False)

                def _on_changed(
                    text: str, *, fp_str=str(file_path), sp=str(source_part)
                ):
                    try:
                        m = (
                            getattr(
                                self.gui, "special_part_mapping_by_file", {}
                            )
                            or {}
                        ).setdefault(fp_str, {})
                        val = (text or "").strip()
                        if not val or val == "（未选择）":
                            m.pop(sp, None)
                        else:
                            m[sp] = val
                        # 更新该文件的状态列
                        try:
                            file_node = getattr(
                                self.gui, "_file_tree_items", {}
                            ).get(fp_str)
                            if file_node is not None:
                                file_node.setText(
                                    1, self._validate_file_config(Path(fp_str))
                                )
                        except Exception:
                            pass
                    except Exception:
                        logger.debug(
                            "special mapping changed handler failed",
                            exc_info=True,
                        )

                combo.currentTextChanged.connect(_on_changed)

                # 将下拉框嵌到“状态”列，达到“文件列表里直接编辑映射”的效果
                self.gui.file_tree.setItemWidget(child, 1, combo)
                self._special_part_combo[
                    (str(file_path), str(source_part))
                ] = combo

                # 在 part 节点下创建数据行预览（用户可展开查看并勾选）
                try:
                    df = (data_dict or {}).get(str(source_part))
                    if df is not None:
                        self._populate_special_data_rows(
                            child, file_path, str(source_part), df
                        )
                except Exception:
                    logger.debug("填充数据行预览失败", exc_info=True)

            try:
                file_item.setExpanded(True)
            except Exception:
                pass

            # 刷新文件状态（映射模式下会提示未映射/缺失）
            try:
                file_item.setText(1, self._validate_file_config(file_path))
            except Exception:
                pass
        except Exception:
            logger.debug("_ensure_special_mapping_rows failed", exc_info=True)

    def refresh_file_statuses(self) -> None:
        """当配置/Part 变化后，刷新文件列表的状态与映射下拉选项。"""
        try:
            items = getattr(self.gui, "_file_tree_items", {}) or {}
            for fp_str, item in items.items():
                try:
                    item.setText(1, self._validate_file_config(Path(fp_str)))
                except Exception:
                    pass

                try:
                    p = Path(fp_str)
                    if looks_like_special_format(p):
                        # 特殊格式：刷新映射行和推测
                        self._ensure_special_mapping_rows(item, p)
                    else:
                        # 常规表格：刷新 Source/Target 下拉并重跑推测
                        self._ensure_regular_file_selector_rows(item, p)
                except Exception:
                    logger.debug("刷新文件节点失败: %s", fp_str, exc_info=True)
        except Exception:
            logger.debug("refresh_file_statuses failed", exc_info=True)

    def _on_pattern_changed(self):
        """当匹配模式改变时，基于当前输入路径重新扫描并刷新文件列表。"""
        try:
            path_text = (
                self.gui.inp_batch_input.text().strip()
                if hasattr(self.gui, "inp_batch_input")
                else ""
            )
            if not path_text:
                return
            chosen = Path(path_text)
            if chosen.exists():
                self._scan_and_populate_files(chosen)
        except Exception:
            logger.debug("_on_pattern_changed 处理失败", exc_info=True)

    def run_batch_processing(self):
        """运行批处理（兼容 GUI 原有文件复选框面板与输出目录逻辑）。"""
        try:
            # 新语义：不再依赖“全局 calculator / 应用配置”。
            # 批处理只需要当前配置(ProjectData)存在，并且每个文件已在列表中选择 source/target（或可唯一推断）。
            project_data = getattr(self.gui, "current_config", None)
            if project_data is None:
                QMessageBox.warning(self.gui, "提示", "请先加载配置（JSON）")
                return

            # 输入路径
            if not hasattr(self.gui, "inp_batch_input"):
                QMessageBox.warning(self.gui, "提示", "缺少输入路径控件")
                return
            input_path = Path(self.gui.inp_batch_input.text().strip())
            if not input_path.exists():
                QMessageBox.warning(self.gui, "错误", "输入路径不存在")
                return

            files_to_process = []
            output_dir = getattr(self.gui, "output_dir", None)

            if input_path.is_file():
                files_to_process = [input_path]
                if output_dir is None:
                    output_dir = input_path.parent
            elif input_path.is_dir():
                # 使用树形文件列表收集选中的文件
                if hasattr(self.gui, "file_tree") and hasattr(
                    self.gui, "_file_tree_items"
                ):
                    from PySide6.QtCore import Qt
                    from PySide6.QtWidgets import QTreeWidgetItemIterator

                    iterator = QTreeWidgetItemIterator(self.gui.file_tree)
                    while iterator.value():
                        item = iterator.value()
                        # 只处理文件项（有UserRole数据的）
                        file_path_str = item.data(0, Qt.UserRole)
                        if file_path_str and item.checkState(0) == Qt.Checked:
                            files_to_process.append(Path(file_path_str))
                        iterator += 1

                    if output_dir is None:
                        output_dir = input_path
                else:
                    # Fallback：直接扫描目录
                    pattern = getattr(self.gui, "inp_pattern", None)
                    pattern_text = (
                        pattern.text().strip() if pattern else "*.csv"
                    )
                    patterns = [
                        x.strip() for x in pattern_text.split(";") if x.strip()
                    ]
                    if not patterns:
                        patterns = ["*.csv"]
                    for file_path in input_path.rglob("*"):
                        if not file_path.is_file():
                            continue
                        if any(
                            fnmatch.fnmatch(file_path.name, pat)
                            for pat in patterns
                        ):
                            files_to_process.append(file_path)
                    if output_dir is None:
                        output_dir = input_path
                if not files_to_process:
                    QMessageBox.warning(
                        self.gui,
                        "提示",
                        f"未找到匹配 '{getattr(self.gui, 'inp_pattern', None).text() if hasattr(self.gui, 'inp_pattern') else '*.csv'}' 的文件或未选择任何文件",
                    )
                    return
            else:
                QMessageBox.warning(self.gui, "错误", "输入路径无效")
                return

            # 输出目录
            if output_dir is None:
                output_dir = Path("data/output")
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # 记录批处理前的文件列表（用于撤销时恢复）
            # 重要：使用完整路径字符串，而不是仅文件名，确保撤销时能正确比对
            existing_files = set(
                str(f) for f in output_path.glob("*") if f.is_file()
            )
            self.gui._batch_output_dir = output_path
            self.gui._batch_existing_files = existing_files
            # 全局数据格式配置已废弃：线程内部将按文件解析格式（sidecar/目录/registry）。
            data_config = None

            from gui.batch_thread import BatchProcessThread

            self.batch_thread = BatchProcessThread(
                getattr(self.gui, "calculator", None),
                files_to_process,
                output_path,
                data_config,
                registry_db=getattr(self.gui, "_registry_db", None),
                project_data=project_data,
                timestamp_format=getattr(
                    self.gui, "timestamp_format", "%Y%m%d_%H%M%S"
                ),
                special_part_mapping_by_file=getattr(
                    self.gui, "special_part_mapping_by_file", {}
                ),
                special_row_selection_by_file=getattr(
                    self.gui, "special_part_row_selection_by_file", {}
                ),
                file_part_selection_by_file=getattr(
                    self.gui, "file_part_selection_by_file", {}
                ),
                table_row_selection_by_file=getattr(
                    self.gui, "table_row_selection_by_file", {}
                ),
            )

            # 连接信号
            try:
                self.batch_thread.progress.connect(
                    self.gui.progress_bar.setValue
                )
            except Exception:
                pass
            try:
                self.batch_thread.log_message.connect(
                    lambda msg: self.gui.txt_batch_log.append(
                        f"[{self._now_str()}] {msg}"
                    )
                )
            except Exception:
                pass
            try:
                self.batch_thread.finished.connect(self.on_batch_finished)
            except Exception:
                pass
            try:
                self.batch_thread.error.connect(self.on_batch_error)
            except Exception:
                pass

            try:
                self.gui._set_controls_locked(True)
            except Exception:
                pass

            # 禁用批处理按钮，防止重复点击
            try:
                if hasattr(self.gui, "btn_batch"):
                    self.gui.btn_batch.setEnabled(False)
                    self.gui.btn_batch.setText("处理中...")
            except Exception:
                logger.debug("无法禁用批处理按钮", exc_info=True)

            # 批处理开始时自动切换到处理日志页
            try:
                if hasattr(self.gui, "tab_main"):
                    self.gui.tab_main.setCurrentIndex(
                        1
                    )  # 处理日志页在第1个Tab
            except Exception:
                pass

            self.batch_thread.start()
            logger.info(f"开始批处理 {len(files_to_process)} 个文件")
        except Exception as e:
            logger.error(f"启动批处理失败: {e}")
            QMessageBox.critical(self.gui, "错误", f"启动失败: {e}")

    def _now_str(self):
        from datetime import datetime

        return datetime.now().strftime("%H:%M:%S")

    def _on_batch_log(self, message: str):
        """批处理日志回调"""
        try:
            if hasattr(self.gui, "txt_batch_log"):
                self.gui.txt_batch_log.append(message)
        except Exception:
            logger.debug(f"无法更新日志: {message}")

    def on_batch_finished(self, message: str):
        """批处理完成回调"""
        try:
            logger.info(f"批处理完成: {message}")
            if hasattr(self.gui, "_set_controls_locked"):
                self.gui._set_controls_locked(False)

            # 重新启用批处理按钮
            try:
                if hasattr(self.gui, "btn_batch"):
                    self.gui.btn_batch.setEnabled(True)
                    self.gui.btn_batch.setText("开始批量处理")
            except Exception:
                logger.debug("无法启用批处理按钮", exc_info=True)

            # 启用撤销按钮
            try:
                if hasattr(self.gui, "btn_undo"):
                    self.gui.btn_undo.setEnabled(True)
                    self.gui.btn_undo.setVisible(True)
            except Exception:
                logger.debug("无法启用撤销按钮", exc_info=True)

            QMessageBox.information(self.gui, "完成", message)
        except Exception as e:
            logger.error(f"处理完成事件失败: {e}")

    def on_batch_error(self, error_msg: str):
        """批处理错误回调"""
        try:
            logger.error(f"批处理错误: {error_msg}")
            if hasattr(self.gui, "_set_controls_locked"):
                self.gui._set_controls_locked(False)

            # 重新启用批处理按钮
            try:
                if hasattr(self.gui, "btn_batch"):
                    self.gui.btn_batch.setEnabled(True)
                    self.gui.btn_batch.setText("开始批量处理")
            except Exception:
                logger.debug("无法启用批处理按钮", exc_info=True)

            QMessageBox.critical(self.gui, "错误", f"批处理出错: {error_msg}")
        except Exception as e:
            logger.error(f"处理错误事件失败: {e}")

    def _determine_format_source(self, fp: Path) -> Tuple[str, Optional[Path]]:
        """快速判断单个文件的格式来源，返回 (label, path_or_None)。

        label: 'registry' | 'sidecar' | 'dir' | 'global' | 'unknown'
        path_or_None: 指向具体的 format 文件（Path）或 None
        说明：当 per-file 覆盖未启用时（默认），直接返回 ('global', None)。
        """
        try:
            # 若 per-file 覆盖未显式启用，则统一视作全局（不检查 registry/sidecar）
            try:
                if hasattr(self.gui, "experimental_settings"):
                    if not bool(
                        self.gui.experimental_settings.get(
                            "enable_sidecar", False
                        )
                    ):
                        return ("global", None)
                else:
                    if (
                        hasattr(self.gui, "chk_enable_sidecar")
                        and not self.gui.chk_enable_sidecar.isChecked()
                    ):
                        return ("global", None)
            except Exception:
                pass

            # 1) registry 优先（若界面提供了 db 路径）
            if hasattr(self.gui, "inp_registry_db"):
                dbp = self.gui.inp_registry_db.text().strip()
                if dbp:
                    try:
                        fmt = get_format_for_file(dbp, str(fp))
                        if fmt:
                            return ("registry", Path(fmt))
                    except Exception:
                        pass

            # 2) file-sidecar
            for suf in (".format.json", ".json"):
                cand = fp.parent / f"{fp.stem}{suf}"
                if cand.exists():
                    return ("sidecar", cand)

            # 3) 目录级默认
            dir_cand = fp.parent / "format.json"
            if dir_cand.exists():
                return ("dir", dir_cand)

            return ("global", None)
        except Exception:
            return ("unknown", None)

    def _format_label_from(self, src: str, src_path: Optional[Path]):
        """将源类型与路径格式化为显示文本、tooltip 与颜色。"""
        try:
            if src == "registry":
                name = Path(src_path).name if src_path else ""
                return (
                    f"registry ({name})" if name else "registry",
                    str(src_path) if src_path else "",
                    "#1f77b4",
                )
            if src == "sidecar":
                name = Path(src_path).name if src_path else ""
                return (
                    f"sidecar ({name})" if name else "sidecar",
                    str(src_path) if src_path else "",
                    "#28a745",
                )
            if src == "dir":
                name = Path(src_path).name if src_path else ""
                return (
                    f"dir ({name})" if name else "dir",
                    str(src_path) if src_path else "",
                    "#ff8c00",
                )
            if src == "global":
                return ("global", "", "#6c757d")
            return ("unknown", "", "#dc3545")
        except Exception:
            logger.debug("_format_label_from encountered error", exc_info=True)
            return ("unknown", "", "#dc3545")

    def _refresh_format_labels(self):
        """遍历当前文件列表，重新解析并更新每个文件旁的来源标签及 tooltip。"""
        try:
            items = getattr(self.gui, "_file_check_items", None)
            if not items:
                return
            for tup in items:
                if len(tup) == 2:
                    continue
                cb, fp, lbl = tup
                try:
                    src, src_path = self._determine_format_source(fp)
                    disp, tip, color = self._format_label_from(src, src_path)
                    lbl.setText(disp)
                    lbl.setToolTip(tip or "")
                    try:
                        if color == "#dc3545":
                            lbl.setProperty("variant", "error")
                        elif color == "#6c757d":
                            lbl.setProperty("variant", "muted")
                        else:
                            lbl.setProperty("variant", "normal")
                    except Exception:
                        pass
                except Exception:
                    logger.debug(
                        "Failed to set label text from format source",
                        exc_info=True,
                    )
                    try:
                        lbl.setText("未知")
                        lbl.setToolTip("")
                        try:
                            lbl.setProperty("variant", "error")
                        except Exception:
                            pass
                    except Exception:
                        pass
        except Exception:
            logger.debug("_refresh_format_labels failed", exc_info=True)

    # 对外提供与 gui.py 同名的委托入口（供 GUI 壳方法调用）
    def on_pattern_changed(self):
        return self._on_pattern_changed()

    def scan_and_populate_files(self, chosen_path: Path):
        return self._scan_and_populate_files(chosen_path)

    def refresh_format_labels(self):
        return self._refresh_format_labels()

    def _get_active_special_part_context(self):
        """判断当前焦点是否在特殊格式的 part/数据行上。

        Returns:
            (part_item, file_path_str, source_part) 或 (None, None, None)
        """
        try:
            if (
                not hasattr(self.gui, "file_tree")
                or self.gui.file_tree is None
            ):
                return None, None, None

            item = self.gui.file_tree.currentItem()
            if item is None:
                selected = self.gui.file_tree.selectedItems()
                item = selected[0] if selected else None
            # 无论当前项情况如何，都尝试通过焦点反推一次（修复表格聚焦但树项未切换时无法识别的问题）
            try:
                from PySide6.QtWidgets import QApplication

                fw = (
                    QApplication.instance().focusWidget()
                    if QApplication.instance()
                    else None
                )
                if fw is not None:
                    for (fp_str, sp), table in (
                        self._special_preview_tables or {}
                    ).items():
                        w = fw
                        inner = getattr(table, "table", None)
                        while w is not None:
                            if w is table or (inner is not None and w is inner):
                                part_item = self._find_special_part_item(
                                    fp_str, sp
                                )
                                if part_item is not None:
                                    return part_item, fp_str, sp
                                break
                            w = w.parentWidget()
            except Exception:
                pass

            meta = self._get_item_meta(item)
            if not isinstance(meta, dict):
                return None, None, None

            kind = meta.get("kind")
            if kind == "special_part":
                fp_str = str(meta.get("file") or "")
                sp = str(meta.get("source") or "")
                return item, fp_str, sp
            if kind == "special_data_row":
                parent = item.parent()
                if parent is None:
                    return None, None, None
                parent_meta = self._get_item_meta(parent)
                if (
                    isinstance(parent_meta, dict)
                    and parent_meta.get("kind") == "special_part"
                ):
                    fp_str = str(parent_meta.get("file") or "")
                    sp = str(parent_meta.get("source") or "")
                    return parent, fp_str, sp
        except Exception:
            logger.debug("获取当前特殊 part 上下文失败", exc_info=True)
        return None, None, None

    def _get_active_table_context(self):
        """判断当前焦点是否在常规表格数据行上。

        Returns:
            (file_item, file_path_str) 或 (None, None)
        """
        try:
            if (
                not hasattr(self.gui, "file_tree")
                or self.gui.file_tree is None
            ):
                return None, None
            item = self.gui.file_tree.currentItem()
            if item is None:
                selected = self.gui.file_tree.selectedItems()
                item = selected[0] if selected else None
            # 始终尝试通过焦点反推上下文，避免当前树项干扰
            try:
                from PySide6.QtWidgets import QApplication

                fw = (
                    QApplication.instance().focusWidget()
                    if QApplication.instance()
                    else None
                )
                if fw is not None:
                    for fp_str, table in (
                        self._table_preview_tables or {}
                    ).items():
                        w = fw
                        inner = getattr(table, "table", None)
                        while w is not None:
                            if w is table or (inner is not None and w is inner):
                                file_item = getattr(
                                    self.gui, "_file_tree_items", {}
                                ).get(fp_str)
                                if file_item is not None:
                                    return file_item, fp_str
                                break
                            w = w.parentWidget()
            except Exception:
                pass

            meta = self._get_item_meta(item)
            if not isinstance(meta, dict):
                return None, None

            kind = meta.get("kind")
            if kind == "table_data_group":
                fp_str = str(meta.get("file") or "")
                if not fp_str:
                    return None, None
                file_item = getattr(self.gui, "_file_tree_items", {}).get(
                    fp_str
                )
                return file_item, fp_str

            if kind == "table_data_row":
                fp_str = str(meta.get("file") or "")
                if not fp_str:
                    return None, None
                file_item = getattr(self.gui, "_file_tree_items", {}).get(
                    fp_str
                )
                return file_item, fp_str
        except Exception:
            logger.debug("获取当前表格数据行上下文失败", exc_info=True)
        return None, None

    def _should_bulk_apply_row_selection(self) -> bool:
        """是否对所有选中文件批量应用行选择操作。"""
        try:
            bp = getattr(self.gui, "batch_panel", None)
            chk = (
                getattr(bp, "chk_bulk_row_selection", None)
                if bp is not None
                else None
            )
            if chk is None:
                return False
            return bool(chk.isChecked())
        except Exception:
            return False

    def _iter_checked_file_items(self):
        """遍历当前文件树中被勾选的文件项（仅文件项）。"""
        try:
            from PySide6.QtWidgets import QTreeWidgetItemIterator

            if (
                not hasattr(self.gui, "file_tree")
                or self.gui.file_tree is None
            ):
                return
            it = QTreeWidgetItemIterator(self.gui.file_tree)
            while it.value():
                item = it.value()
                fp = item.data(0, Qt.UserRole)
                if fp and item.checkState(0) == Qt.Checked:
                    yield item, str(fp)
                it += 1
        except Exception:
            return

    def _set_table_rows_checked_for_file(
        self, file_item, fp_str: str, *, mode: str
    ) -> None:
        """对某个文件下的表格数据行执行全选/全不选/反选。"""
        if file_item is None or not fp_str:
            return

        table = self._table_preview_tables.get(fp_str)

        if not hasattr(self.gui, "table_row_selection_by_file"):
            self.gui.table_row_selection_by_file = {}
        by_file = getattr(self.gui, "table_row_selection_by_file", {}) or {}
        sel = by_file.get(fp_str)
        if sel is None:
            sel = set()
            by_file[fp_str] = sel

        # 优先使用表格复选框
        if table is not None:
            self._is_updating_tree = True
            try:
                rows = table.rowCount()
                selected = set(by_file.get(fp_str) or set())
                for r in range(rows):
                    cb = table.cellWidget(r, 0)
                    if cb is None:
                        continue
                    if mode == "all":
                        cb.setChecked(True)
                        selected.add(r)
                    elif mode == "none":
                        cb.setChecked(False)
                        selected.discard(r)
                    elif mode == "invert":
                        new_state = not cb.isChecked()
                        cb.setChecked(new_state)
                        if new_state:
                            selected.add(r)
                        else:
                            selected.discard(r)
                by_file[fp_str] = selected
            finally:
                self._is_updating_tree = False
            self.gui.table_row_selection_by_file = by_file
            return

        # 回退：无表格时使用树节点
        # 找到 group
        group = None
        for i in range(file_item.childCount()):
            try:
                child = file_item.child(i)
                meta = self._get_item_meta(child)
                if (
                    isinstance(meta, dict)
                    and meta.get("kind") == "table_data_group"
                ):
                    group = child
                    break
            except Exception:
                continue
        if group is None:
            return

        row_items = []
        for i in range(group.childCount()):
            try:
                child = group.child(i)
                meta = self._get_item_meta(child)
                if (
                    isinstance(meta, dict)
                    and meta.get("kind") == "table_data_row"
                ):
                    row_items.append(child)
            except Exception:
                continue
        if not row_items:
            return

        self._is_updating_tree = True
        try:
            if mode == "all":
                selected = set()
                for child in row_items:
                    meta = self._get_item_meta(child) or {}
                    idx = meta.get("row")
                    try:
                        idx_int = int(idx)
                    except Exception:
                        continue
                    selected.add(idx_int)
                    child.setCheckState(0, Qt.Checked)
                by_file[fp_str] = selected

            elif mode == "none":
                for child in row_items:
                    child.setCheckState(0, Qt.Unchecked)
                by_file[fp_str] = set()

            elif mode == "invert":
                selected = set(by_file.get(fp_str) or set())
                for child in row_items:
                    meta = self._get_item_meta(child) or {}
                    idx = meta.get("row")
                    try:
                        idx_int = int(idx)
                    except Exception:
                        continue
                    if child.checkState(0) == Qt.Checked:
                        child.setCheckState(0, Qt.Unchecked)
                        selected.discard(idx_int)
                    else:
                        child.setCheckState(0, Qt.Checked)
                        selected.add(idx_int)
                by_file[fp_str] = selected
        finally:
            self._is_updating_tree = False

        self.gui.table_row_selection_by_file = by_file

    def _set_special_part_rows_checked(
        self, part_item, file_path_str: str, source_part: str, *, mode: str
    ) -> None:
        """对某个 part 下的数据行执行全选/全不选/反选（表格预览优先）。"""
        if part_item is None or not file_path_str or not source_part:
            return

        fp_str = str(file_path_str)
        table = self._special_preview_tables.get((fp_str, str(source_part)))

        if not hasattr(self.gui, "special_part_row_selection_by_file"):
            self.gui.special_part_row_selection_by_file = {}
        by_file = (
            getattr(self.gui, "special_part_row_selection_by_file", {}) or {}
        )
        by_part = by_file.setdefault(fp_str, {})

        # 有表格则直接操作表格复选框
        if table is not None:
            self._is_updating_tree = True
            try:
                selected = set(by_part.get(str(source_part)) or set())
                rows = table.rowCount()
                for r in range(rows):
                    cb = table.cellWidget(r, 0)
                    if cb is None:
                        continue
                    if mode == "all":
                        cb.setChecked(True)
                        selected.add(r)
                    elif mode == "none":
                        cb.setChecked(False)
                        selected.discard(r)
                    elif mode == "invert":
                        new_state = not cb.isChecked()
                        cb.setChecked(new_state)
                        if new_state:
                            selected.add(r)
                        else:
                            selected.discard(r)
                by_part[str(source_part)] = selected
            finally:
                self._is_updating_tree = False
            self.gui.special_part_row_selection_by_file = by_file
            return

        # 回退：无表格时使用树节点
        row_items = []
        for i in range(part_item.childCount()):
            try:
                child = part_item.child(i)
                meta = self._get_item_meta(child)
                if (
                    isinstance(meta, dict)
                    and meta.get("kind") == "special_data_row"
                ):
                    row_items.append(child)
            except Exception:
                continue

        if not row_items:
            return

        self._is_updating_tree = True
        try:
            if mode == "all":
                selected = set()
                for child in row_items:
                    meta = self._get_item_meta(child) or {}
                    idx = meta.get("row")
                    try:
                        idx_int = int(idx)
                    except Exception:
                        continue
                    selected.add(idx_int)
                    child.setCheckState(0, Qt.Checked)
                by_part[str(source_part)] = selected

            elif mode == "none":
                for child in row_items:
                    child.setCheckState(0, Qt.Unchecked)
                by_part[str(source_part)] = set()

            elif mode == "invert":
                selected = set(by_part.get(str(source_part)) or set())
                for child in row_items:
                    meta = self._get_item_meta(child) or {}
                    idx = meta.get("row")
                    try:
                        idx_int = int(idx)
                    except Exception:
                        continue
                    if child.checkState(0) == Qt.Checked:
                        child.setCheckState(0, Qt.Unchecked)
                        selected.discard(idx_int)
                    else:
                        child.setCheckState(0, Qt.Checked)
                        selected.add(idx_int)
                by_part[str(source_part)] = selected
        finally:
            self._is_updating_tree = False

        self.gui.special_part_row_selection_by_file = by_file

    # 文件选择方法（从 main_window 迁移）
    def select_all_files(self):
        """全选：文件模式下全选文件；数据模式下全选当前 part 数据行。"""
        part_item, fp_str, sp = self._get_active_special_part_context()
        if part_item is not None:
            self._set_special_part_rows_checked(
                part_item, fp_str, sp, mode="all"
            )
            return

        file_item, table_fp = self._get_active_table_context()
        if file_item is not None and table_fp:
            if self._should_bulk_apply_row_selection():
                for it, fp in self._iter_checked_file_items() or []:
                    self._set_table_rows_checked_for_file(
                        it, str(fp), mode="all"
                    )
            else:
                self._set_table_rows_checked_for_file(
                    file_item, table_fp, mode="all"
                )
            return
        self._set_all_file_items_checked(Qt.Checked)

    def select_none_files(self):
        """全不选：文件模式下全不选文件；数据模式下全不选当前 part 数据行。"""
        part_item, fp_str, sp = self._get_active_special_part_context()
        if part_item is not None:
            self._set_special_part_rows_checked(
                part_item, fp_str, sp, mode="none"
            )
            return

        file_item, table_fp = self._get_active_table_context()
        if file_item is not None and table_fp:
            if self._should_bulk_apply_row_selection():
                for it, fp in self._iter_checked_file_items() or []:
                    self._set_table_rows_checked_for_file(
                        it, str(fp), mode="none"
                    )
            else:
                self._set_table_rows_checked_for_file(
                    file_item, table_fp, mode="none"
                )
            return
        self._set_all_file_items_checked(Qt.Unchecked)

    def invert_file_selection(self):
        """反选：文件模式下反选文件；数据模式下反选当前 part 数据行。"""
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        if not hasattr(self.gui, "file_tree"):
            return

        part_item, fp_str, sp = self._get_active_special_part_context()
        if part_item is not None:
            self._set_special_part_rows_checked(
                part_item, fp_str, sp, mode="invert"
            )
            return

        file_item, table_fp = self._get_active_table_context()
        if file_item is not None and table_fp:
            if self._should_bulk_apply_row_selection():
                for it, fp in self._iter_checked_file_items() or []:
                    self._set_table_rows_checked_for_file(
                        it, str(fp), mode="invert"
                    )
            else:
                self._set_table_rows_checked_for_file(
                    file_item, table_fp, mode="invert"
                )
            return

        iterator = QTreeWidgetItemIterator(self.gui.file_tree)
        while iterator.value():
            item = iterator.value()
            # 只反选文件项（有用户数据中存储了路径的项）
            if item.data(0, Qt.UserRole):
                # 仅在项可由用户修改复选框时才改变状态
                try:
                    if bool(item.flags() & Qt.ItemIsUserCheckable):
                        if item.checkState(0) == Qt.Checked:
                            item.setCheckState(0, Qt.Unchecked)
                        else:
                            item.setCheckState(0, Qt.Checked)
                except Exception:
                    # 保守处理：若检查 flags 失败，则跳过该项
                    pass
            iterator += 1

    def _set_all_file_items_checked(self, check_state):
        """设置所有文件项的选中状态（仅文件，不包括目录节点）"""
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        if not hasattr(self.gui, "file_tree"):
            return

        iterator = QTreeWidgetItemIterator(self.gui.file_tree)
        while iterator.value():
            item = iterator.value()
            # 只选中文件项（有用户数据中存储了路径的项）
            if item.data(0, Qt.UserRole):
                # 仅对允许用户改变复选框的项执行设置，尊重单文件模式下禁用的复选框
                try:
                    if bool(item.flags() & Qt.ItemIsUserCheckable):
                        item.setCheckState(0, check_state)
                except Exception:
                    # 保守处理：若检查 flags 失败，则跳过
                    pass
            iterator += 1

    # 批处理控制方法（从 main_window 迁移）
    def request_cancel_batch(self):
        """请求取消正在运行的批处理任务"""
        from datetime import datetime

        try:
            batch_thread = getattr(self.gui, "batch_thread", None)
            if batch_thread is not None:
                if hasattr(self.gui, "txt_batch_log"):
                    self.gui.txt_batch_log.append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] 用户请求取消任务，正在停止..."
                    )
                try:
                    batch_thread.request_stop()
                except Exception:
                    logger.debug(
                        "batch_thread.request_stop 调用失败（可能已结束）",
                        exc_info=True,
                    )

                # 禁用取消按钮以避免重复点击
                if hasattr(self.gui, "btn_cancel"):
                    try:
                        self.gui.btn_cancel.setEnabled(False)
                    except Exception:
                        pass
        except Exception:
            logger.debug("request_cancel_batch 失败", exc_info=True)

    def undo_batch_processing(self):
        """撤销最近一次批处理操作"""
        try:
            output_dir = getattr(self.gui, "_batch_output_dir", None)
            existing_files = getattr(self.gui, "_batch_existing_files", set())

            # 安全检查：确保有记录的输出目录和已存在文件列表
            if not output_dir or not isinstance(existing_files, set):
                QMessageBox.warning(
                    self.gui,
                    "提示",
                    "没有可撤销的批处理记录。请先运行批处理。",
                )
                return

            reply = QMessageBox.question(
                self.gui,
                "确认撤销",
                f"确定要撤销最近一次批处理？\n将删除 {output_dir} 中的新生成文件（保留源数据）。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply != QMessageBox.Yes:
                return

            # 只删除本次批处理新生成的文件
            deleted_count = 0
            try:
                if output_dir and Path(output_dir).exists():
                    output_path = Path(output_dir)
                    for file in output_path.iterdir():
                        # 使用完整路径字符串进行比对
                        file_path_str = str(file.resolve())
                        # 转换existing_files中的路径为绝对路径进行比较
                        existing_files_resolved = set(
                            str(Path(p).resolve()) for p in existing_files
                        )

                        if (
                            file.is_file()
                            and file_path_str not in existing_files_resolved
                        ):
                            try:
                                file.unlink()
                                deleted_count += 1
                                logger.info(f"已删除: {file}")
                            except Exception as e:
                                logger.warning(f"无法删除 {file}: {e}")

                QMessageBox.information(
                    self.gui, "撤销完成", f"已删除 {deleted_count} 个输出文件"
                )

                # 清空批处理记录
                self.gui._batch_output_dir = None
                self.gui._batch_existing_files = set()
                # 隐藏并禁用撤销按钮，避免用户误以为仍可撤销
                try:
                    if hasattr(self.gui, "btn_undo"):
                        self.gui.btn_undo.setEnabled(False)
                        self.gui.btn_undo.setVisible(False)
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"撤销批处理失败: {e}", exc_info=True)
                QMessageBox.critical(self.gui, "错误", f"撤销失败: {e}")

        except Exception as e:
            logger.error(f"undo_batch_processing 失败: {e}", exc_info=True)
