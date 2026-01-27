"""批处理管理模块 - 处理批处理相关功能"""

# 模块级 pylint 配置：批处理模块包含多个 GUI 回调，接受较多参数
# 为了在小步重构过程中避免大量噪声，临时禁用参数过多与超长行警告。
# 之后可以逐步移除或替换为局部禁用。
# pylint: disable=too-many-arguments,line-too-long

import fnmatch
import logging
import math
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
)

from gui.batch_history import BatchHistoryPanel, BatchHistoryStore
from gui.batch_manager_batch import (
    attach_batch_thread_signals as _attach_batch_thread_signals_impl,
)
from gui.batch_manager_batch import create_batch_thread as _create_batch_thread_impl
from gui.batch_manager_batch import (
    delete_new_output_files as _delete_new_output_files_impl,
)
from gui.batch_manager_batch import prepare_gui_for_batch as _prepare_gui_for_batch_impl
from gui.batch_manager_batch import request_cancel_batch as _request_cancel_batch_impl
from gui.batch_manager_batch import (
    restore_gui_after_batch as _restore_gui_after_batch_impl,
)
from gui.batch_manager_batch import run_batch_processing as _run_batch_processing_impl
from gui.batch_manager_batch import undo_batch_processing as _undo_batch_processing_impl
from gui.batch_manager_files import _add_file_tree_entry as _add_file_tree_entry_impl
from gui.batch_manager_files import (
    _auto_fill_special_mappings as _auto_fill_special_mappings_impl,
)
from gui.batch_manager_files import (
    _collect_files_for_scan as _collect_files_for_scan_impl,
)
from gui.batch_manager_files import (
    _collect_files_to_process as _collect_files_to_process_impl,
)
from gui.batch_manager_files import (
    _create_part_mapping_combo as _create_part_mapping_combo_impl,
)
from gui.batch_manager_files import (
    _create_special_part_node as _create_special_part_node_impl,
)
from gui.batch_manager_files import (
    _ensure_file_part_selection_storage as _ensure_file_part_selection_storage_impl,
)
from gui.batch_manager_files import (
    _ensure_regular_file_selector_rows as _ensure_regular_file_selector_rows_impl,
)
from gui.batch_manager_files import (
    _get_or_init_special_mapping as _get_or_init_special_mapping_impl,
)
from gui.batch_manager_files import _infer_target_part as _infer_target_part_impl
from gui.batch_manager_files import (
    _make_part_change_handler as _make_part_change_handler_impl,
)
from gui.batch_manager_files import (
    _populate_file_tree_from_files as _populate_file_tree_from_files_impl,
)
from gui.batch_manager_files import (
    _remove_old_selector_children as _remove_old_selector_children_impl,
)
from gui.batch_manager_files import (
    _safe_add_file_tree_entry as _safe_add_file_tree_entry_impl,
)
from gui.batch_manager_files import (
    _safe_set_combo_selection as _safe_set_combo_selection_impl,
)
from gui.batch_manager_files import (
    _scan_dir_for_patterns as _scan_dir_for_patterns_impl,
)

# 委托到 preview 子模块以避免在函数体内延迟导入
from gui.batch_manager_preview import (
    _apply_preview_filters as _apply_preview_filters_impl,
)
from gui.batch_manager_preview import (
    _apply_quick_filter_special_iter as _apply_quick_filter_special_iter_impl,
)
from gui.batch_manager_preview import (
    _apply_quick_filter_to_special_table as _apply_quick_filter_to_special_table_impl,
)
from gui.batch_manager_preview import (
    _build_row_preview_text as _build_row_preview_text_impl,
)
from gui.batch_manager_preview import (
    _build_table_row_preview_text as _build_table_row_preview_text_impl,
)
from gui.batch_manager_preview import _clear_preview_group as _clear_preview_group_impl
from gui.batch_manager_preview import (
    _create_preview_table as _create_preview_table_impl,
)
from gui.batch_manager_preview import _embed_preview_table as _embed_preview_table_impl
from gui.batch_manager_preview import (
    _ensure_table_row_selection_storage as _ensure_table_row_selection_storage_impl,
)
from gui.batch_manager_preview import (
    _format_preview_value as _format_preview_value_impl,
)
from gui.batch_manager_preview import (
    _get_table_df_preview as _get_table_df_preview_impl,
)
from gui.batch_manager_preview import (
    _make_preview_toggle_callback as _make_preview_toggle_callback_impl,
)
from gui.batch_manager_preview import (
    _populate_special_data_rows as _populate_special_data_rows_impl,
)
from gui.batch_manager_preview import (
    _populate_table_data_rows as _populate_table_data_rows_impl,
)
from gui.batch_manager_ui import connect_quick_filter as _connect_quick_filter_impl
from gui.batch_manager_ui import (
    connect_signal_bus_events as _connect_signal_bus_events_impl,
)
from gui.batch_manager_ui import connect_ui_signals as _connect_ui_signals_impl
from gui.batch_manager_ui import (
    safe_refresh_file_statuses as _safe_refresh_file_statuses_impl,
)
from gui.batch_thread import BatchProcessThread
from gui.paged_table import PagedTableWidget
from gui.quick_select_dialog import QuickSelectDialog
from src.cli_helpers import BatchConfig, resolve_file_format
from src.file_cache import get_file_cache

# 项目内模块（本地导入）
from src.special_format_detector import looks_like_special_format
from src.special_format_parser import get_part_names, parse_special_format_file

logger = logging.getLogger(__name__)


class BatchManager:
    """批处理管理器 - 管理批处理相关操作"""

    def __init__(self, gui_instance):
        """初始化批处理管理器"""
        self.gui = gui_instance
        self.batch_thread = None
        self._bus_connected = False
        self.history_store: Optional[BatchHistoryStore] = None
        self.history_panel: Optional[BatchHistoryPanel] = None

        # 特殊格式：缓存每个文件的 source->target 映射控件（已废弃，使用下面两个）
        # key: (file_path_str, source_part)
        self._special_part_combo = {}
        
        # 特殊格式：缓存source part选择器控件
        # key: (file_path_str, internal_part_name)
        self._special_part_source_combo = {}
        
        # 特殊格式：缓存target part选择器控件
        # key: (file_path_str, internal_part_name)
        self._special_part_target_combo = {}

        # 特殊格式：缓存解析结果，避免频繁全量解析
        # key: file_path_str -> {"mtime": float, "data": Dict[str, DataFrame]}
        self._special_data_cache = {}

        # 常规表格（CSV/Excel）：缓存预览数据，避免频繁读取
        # key: file_path_str -> {"mtime": float, "df": DataFrame, "preview_rows": int}
        self._table_data_cache = {}

        # 文件树批量更新标记，避免 itemChanged 递归触发
        self._is_updating_tree = False

        # 预览表格控件映射，便于批量全选/反选
        # 特殊格式：key=(file_path_str, internal_part_name) -> QTableWidget
        self._special_preview_tables = {}
        # 常规表格：key=file_path_str -> QTableWidget
        self._table_preview_tables = {}

        # 快速筛选状态
        # 在 __init__ 中初始化快速筛选相关属性，避免 W0201 警告
        self._quick_filter_column = None
        self._quick_filter_operator = None
        self._quick_filter_value = None
        self._connect_signal_bus_events()
        self._connect_quick_filter()
        self._connect_ui_signals()

    def attach_history(
        self, store: BatchHistoryStore, panel: Optional[BatchHistoryPanel]
    ):
        """绑定批处理历史存储与面板，供记录与撤销使用。"""
        try:
            self.history_store = store
            self.history_panel = panel
            if panel is not None and hasattr(panel, "set_undo_callback"):
                panel.set_undo_callback(self.undo_history_record)
        except Exception:
            logger.debug("绑定历史组件失败", exc_info=True)

    def _connect_ui_signals(self) -> None:
        """连接文件树与 SignalBus 事件，保证状态/映射随配置变化刷新。"""
        return _connect_ui_signals_impl(self)

    def _connect_signal_bus_events(self) -> None:
        """将配置/Part 变更信号与文件状态刷新绑定（只注册一次）。"""
        return _connect_signal_bus_events_impl(self)

    def _connect_quick_filter(self) -> None:
        """连接快速筛选信号"""
        return _connect_quick_filter_impl(self)

    def _safe_refresh_file_statuses(self, *args, **kwargs):
        """容错包装：用于 SignalBus 回调，安全地调用 `refresh_file_statuses`。

        接收任意参数以兼容不同信号签名。
        """
        return _safe_refresh_file_statuses_impl(self, *args, **kwargs)

    def _on_quick_filter_changed(self, column: str, operator: str, value: str) -> None:
        """快速筛选条件变化，刷新所有表格的行显示"""
        try:
            logger.info(f"快速筛选变化: 列={column}, 运算符={operator}, 值={value}")
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

    def _get_table_item(self, table, r: int, c: int):
        """兼容性访问表格项：支持 QTableWidget 或 PagedTableWidget（内部 QTableWidget）。"""
        try:
            # 直接支持的接口
            if hasattr(table, "item"):
                return table.item(r, c)
            # PagedTableWidget 使用 .table 作为内部 QTableWidget
            if hasattr(table, "table") and hasattr(table.table, "item"):
                return table.table.item(r, c)
        except Exception:
            return None
        return None

    def _ensure_special_row_selection_storage(
        self, file_path: Path, part_names: list
    ) -> dict:
        """委托给 `FileSelectionManager.ensure_special_row_selection_storage`。"""
        try:
            fsm = getattr(self.gui, "file_selection_manager", None)
            if fsm is not None:
                return fsm.ensure_special_row_selection_storage(file_path, part_names)
            # 兼容回退：直接操作主窗口上的属性
            if not hasattr(self.gui, "special_part_row_selection_by_file"):
                self.gui.special_part_row_selection_by_file = {}
            by_file = getattr(self.gui, "special_part_row_selection_by_file", {}) or {}
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
        if cached and cached.get("mtime") == mtime and cached.get("data") is not None:
            return cached.get("data")

        try:
            data_dict = parse_special_format_file(file_path)
        except Exception:
            logger.debug("解析特殊格式文件失败", exc_info=True)
            data_dict = {}

        self._special_data_cache[fp_str] = {"mtime": mtime, "data": data_dict}
        return data_dict

    def _format_preview_value(self, v):
        """将单元格值格式化为便于显示的字符串（处理 None/NaN 和异常）。"""
        # 委托到 preview 子模块实现（已在模块顶层导入）
        return _format_preview_value_impl(self, v)

    def _build_row_preview_text(self, row_index: int, row_series) -> str:
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
                    val = self._format_preview_value(row_series.get(k))
                    if val != "":
                        parts.append(f"{k}={val}")
            except Exception:
                continue
        if not parts:
            return f"第{row_index + 1}行"
        # 显示全部已格式化的列键值对，而不是仅前6项
        return _build_row_preview_text_impl(self, row_index, row_series)

    def _create_preview_table(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        df,
        selected_set: set,
        on_toggle,
        *,
        max_rows: int = 200,
        max_cols: int = None,
    ):  # pylint: disable=too-many-arguments
        """创建带勾选列的数据预览表格（分页版）。

        为了适配 5000+ 行数据，使用分页容器 PagedTableWidget，其中每页默认显示
        max_rows 行，并内置上一页/下一页按钮，且与快速筛选联动。
        """
        return _create_preview_table_impl(
            self,
            df,
            selected_set,
            on_toggle,
            max_rows=max_rows,
            max_cols=max_cols,
        )

    def _apply_quick_filter_to_table(self, table, file_path_str: str) -> None:
        """对常规表格应用快速筛选。

        - 若为分页表格，调用其 set_filter_with_df 以联动翻页。
        - 否则回退为灰显不匹配行。
        """
        try:
            # 如果没有筛选条件，恢复所有行
            if not self._quick_filter_column or not self._quick_filter_value:
                self._clear_quick_filter_table(table)
                return None

            # 获取数据
            cached = self._table_data_cache.get(file_path_str)
            if not cached or cached.get("df") is None:
                return None

            df = cached.get("df")
            if df is None or df.empty or self._quick_filter_column not in df.columns:
                return None

            operator = self._quick_filter_operator
            operator = self._quick_filter_operator

            # 分页组件联动：优先使用分页表格的筛选跳页
            if self._apply_quick_filter_with_paged_table(table, df, operator):
                return None


        except Exception as e:
            logger.debug(f"应用表格快速筛选失败: {e}", exc_info=True)
            return None

    def _clear_quick_filter_table(self, table) -> None:
        """将表格恢复到未筛选的显示（白底黑字），跳过勾选列。"""
        for r in range(table.rowCount()):
            for c in range(1, table.columnCount()):  # 跳过勾选列
                item = self._get_table_item(table, r, c)
                if item:
                    item.setBackground(QColor(255, 255, 255))
                    item.setForeground(QColor(0, 0, 0))

    def _apply_quick_filter_table_iter(self, table, df, operator: str) -> None:
        """迭代表格行并基于筛选结果调整颜色显示。"""
        gray_color = QColor(220, 220, 220)
        text_color = QColor(160, 160, 160)

        for r in range(min(table.rowCount(), len(df))):
            try:
                row_value = df.iloc[r][self._quick_filter_column]
                matches = self._evaluate_filter(
                    row_value, operator, self._quick_filter_value
                )

                for c in range(1, table.columnCount()):  # 跳过勾选列
                    item = self._get_table_item(table, r, c)
                    if item:
                        if matches:
                            item.setBackground(QColor(255, 255, 255))
                            item.setForeground(QColor(0, 0, 0))
                        else:
                            item.setBackground(gray_color)
                            item.setForeground(text_color)
            except Exception:
                pass

    def _apply_quick_filter_with_paged_table(self, table, df, operator: str) -> bool:
        """尝试在分页表格上应用筛选并返回是否已处理。

        Returns:
            bool: 如果已通过分页表格的 `set_filter_with_df` 处理则返回 True。
        """
        try:
            # 避免循环导入，仅通过 duck-typing 调用
            if not hasattr(table, "set_filter_with_df"):
                return False

            def _eval(v):
                return self._evaluate_filter(v, operator, self._quick_filter_value)

            try:
                table.set_filter_with_df(df, _eval, self._quick_filter_column)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def _evaluate_filter(self, row_value, operator: str, filter_value: str) -> bool:
        """评估筛选条件是否匹配"""
        try:
            if operator == "包含":
                return str(filter_value).lower() in str(row_value).lower()
            if operator == "不包含":
                return str(filter_value).lower() not in str(row_value).lower()
            if operator in ["=", "≠", "<", ">", "≤", "≥", "≈"]:
                # 数值比较，委托给 helper
                try:
                    val = float(row_value)
                    flt = float(filter_value)
                except (ValueError, TypeError):
                    return False
                return self._compare_numeric(val, flt, operator)
            return False
        except Exception:
            return False

    def _compare_numeric(self, val: float, flt: float, operator: str) -> bool:
        """比较两个浮点数，根据运算符返回布尔结果。"""
        try:
            if operator == "≈":
                # 近似相等（误差在1%以内）
                if abs(flt) > 1e-10:
                    return abs(val - flt) / abs(flt) < 0.01
                return abs(val - flt) < 1e-10

            ops = {
                "=": lambda a, b: abs(a - b) < 1e-10,
                "≠": lambda a, b: abs(a - b) >= 1e-10,
                "<": lambda a, b: a < b,
                ">": lambda a, b: a > b,
                "≤": lambda a, b: a <= b,
                "≥": lambda a, b: a >= b,
            }
            func = ops.get(operator)
            if func is not None:
                return func(val, flt)
        except Exception:
            return False
        return False

    def _apply_quick_filter_to_special_table(
        self, table, file_path_str: str, source_part: str
    ) -> None:
        """对特殊格式表格应用快速筛选。

        - 若为分页表格，调用其 set_filter_with_df 以联动翻页。
        - 否则回退为灰显不匹配行。
        """
        try:
            # 如果没有筛选条件，恢复所有行
            if not self._quick_filter_column or not self._quick_filter_value:
                self._clear_quick_filter_table(table)
                return None

            # 获取数据
            data_dict = self._get_special_data_dict(Path(file_path_str))
            df = data_dict.get(source_part)
            if df is None or df.empty or self._quick_filter_column not in df.columns:
                return None

            operator = self._quick_filter_operator

            # 分页组件联动
            try:
                if hasattr(table, "set_filter_with_df"):

                    def _eval(v):
                        return self._evaluate_filter(
                            v, operator, self._quick_filter_value
                        )

                    table.set_filter_with_df(df, _eval, self._quick_filter_column)
                    return None
            except Exception:
                pass

            # 应用筛选（委托给 helper）
            return _apply_quick_filter_to_special_table_impl(
                self, table, file_path_str, source_part
            )
        except Exception as e:
            logger.debug(f"应用特殊格式表格快速筛选失败: {e}", exc_info=True)
            return None

    def _apply_quick_filter_special_iter(self, table, df, operator: str) -> None:
        """针对特殊格式表的筛选迭代与颜色更新逻辑。"""
        gray_color = QColor(220, 220, 220)
        text_color = QColor(160, 160, 160)

        for r in range(min(table.rowCount(), len(df))):
            try:
                row_value = df.iloc[r][self._quick_filter_column]
                matches = self._evaluate_filter(
                    row_value, operator, self._quick_filter_value
                )

                for c in range(1, table.columnCount()):
                    item = self._get_table_item(table, r, c)
                    if item:
                        if matches:
                            item.setBackground(QColor(255, 255, 255))
                            item.setForeground(QColor(0, 0, 0))
                        else:
                            item.setBackground(gray_color)
                            item.setForeground(text_color)
            except Exception:
                pass
        return _apply_quick_filter_special_iter_impl(self, table, df, operator)

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
                df = pd.read_csv(file_path, header=header_opt, nrows=int(max_rows))
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
            by_file = getattr(self.gui, "table_row_selection_by_file", {}) or {}
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
            file_item = getattr(self.gui, "_file_tree_items", {})
            file_item = file_item.get(fp_str)
            if file_item is None:
                return None
            for i in range(file_item.childCount()):
                child = file_item.child(i)
                meta = self._get_item_meta(child)
                if isinstance(meta, dict) and meta.get("kind") == "special_part":
                    if str(meta.get("source") or "") == str(source_part):
                        return child
        except Exception:
            pass
        return None

    def _populate_table_data_rows(self, file_item, file_path: Path, df) -> None:
        """为常规表格文件创建数据行预览表格（带勾选列）。"""
        return _populate_table_data_rows_impl(self, file_item, file_path, df)

    def _make_preview_toggle_callback(
        self,
        *,
        is_special: bool = False,
        fp_local=None,
        source_part=None,
    ):  # pylint: disable=too-many-arguments
        """返回一个用于预览表格行勾选的回调函数（用于减小单个函数体大小）。"""
        return _make_preview_toggle_callback_impl(
            self, is_special=is_special, fp_local=fp_local, source_part=source_part
        )

    def _apply_preview_filters(
        self,
        table,
        df,
        fp_str,
        *,
        is_special: bool = False,
        source_part=None,
    ):  # pylint: disable=too-many-arguments
        """应用快速筛选并通知 batch_panel 更新列列表（提取为独立函数）。"""
        return _apply_preview_filters_impl(
            self,
            table,
            df,
            fp_str,
            is_special=is_special,
            source_part=source_part,
        )

    def _embed_preview_table(
        self,
        group,
        df,
        sel,
        fp_str,
        *,
        is_special: bool = False,
        source_part=None,
    ):
        """在树节点中嵌入预览表格并处理行选择回调与筛选应用（精简参数）。"""
        return _embed_preview_table_impl(
            self,
            group,
            df,
            fp_str,
            sel=sel,
            is_special=is_special,
            source_part=source_part,
        )

    def _populate_special_data_rows(
        self, part_item, file_path: Path, source_part: str, df
    ) -> None:
        """为某个 part 节点创建数据行预览表格（带勾选列）。"""
        return _populate_special_data_rows_impl(
            self, part_item, file_path, source_part, df
        )

    def _clear_preview_group(
        self,
        parent_item,
        kind_names,
        table_store=None,
        store_key=None,
    ):
        """通用：清理 parent_item 下的 preview 节点并从 table_store 中移除对应引用（若提供）。"""
        return _clear_preview_group_impl(
            self, parent_item, kind_names, table_store=table_store, store_key=store_key
        )

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
                if self._handle_special_data_row_change(meta, item):
                    return
            elif kind == "table_data_row":
                if self._handle_table_data_row_change(meta, item):
                    return
        except Exception:
            logger.debug("处理数据行勾选变化失败", exc_info=True)

    def _handle_special_data_row_change(self, meta: dict, item) -> bool:
        """处理 special_data_row 的复选框变化，返回是否已处理。"""
        try:
            fp_str = str(meta.get("file") or "")
            source = str(meta.get("source") or "")
            row_idx = meta.get("row")
            if not fp_str or not source or row_idx is None:
                return False
            checked = item.checkState(0) == Qt.Checked
            self._sync_row_selection(
                fp_str, row_idx, checked, is_special=True, source_part=source
            )
            return True
        except Exception:
            return False

    def _handle_table_data_row_change(self, meta: dict, item) -> bool:
        """处理 table_data_row 的复选框变化，返回是否已处理。"""
        try:
            fp_str = str(meta.get("file") or "")
            row_idx = meta.get("row")
            if not fp_str or row_idx is None:
                return False
            checked = item.checkState(0) == Qt.Checked
            self._sync_row_selection(fp_str, row_idx, checked, is_special=False)
            return True
        except Exception:
            return False
        # SignalBus 事件在初始化阶段已注册

    def browse_batch_input(self):
        """浏览并选择输入文件或目录，沿用 GUI 原有文件列表面板。"""
        try:
            dlg = self._create_browse_dialog()

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

    def _create_browse_dialog(self):
        """创建并配置选择输入文件或目录的 QFileDialog 实例（含路径输入框与目录切换复选框）。"""
        from pathlib import Path as PathClass

        dlg = QFileDialog(self.gui, "选择输入文件或目录")
        dlg.setOption(QFileDialog.DontUseNativeDialog, True)
        dlg.setFileMode(QFileDialog.ExistingFile)
        parts = [
            "Data Files (*.csv *.xlsx *.xls *.mtfmt *.mtdata *.txt *.dat)",
            "CSV Files (*.csv)",
            "Excel Files (*.xlsx *.xls)",
            "MomentTransfer (*.mtfmt *.mtdata)",
        ]
        dlg.setNameFilter(";;".join(parts))

        # 创建路径输入框（类似 Windows 资源管理器地址栏）
        try:
            path_layout = QHBoxLayout()
            path_layout.setContentsMargins(0, 0, 0, 0)
            path_layout.setSpacing(4)

            path_label = QLabel("路径:")
            path_input = QLineEdit()
            path_input.setPlaceholderText("输入或粘贴文件路径...")
            path_input.setToolTip("直接输入路径，按回车导航到该位置")

            # 初始化路径输入框为当前目录
            current_dir = dlg.directory().path()
            path_input.setText(current_dir)

            def navigate_to_path():
                """导航到输入框中的路径"""
                path_text = path_input.text().strip()
                if not path_text:
                    return
                try:
                    p = PathClass(path_text)
                    if p.exists():
                        if p.is_dir():
                            dlg.setDirectory(str(p))
                        else:
                            dlg.setDirectory(str(p.parent))
                            dlg.selectFile(str(p))
                        # 更新路径输入框
                        path_input.setText(dlg.directory().path())
                    else:
                        QMessageBox.warning(dlg, "路径不存在", f"路径不存在：{path_text}")
                except Exception as e:
                    QMessageBox.warning(dlg, "路径错误", f"无效的路径：{path_text}\n{str(e)}")

            def update_path_input():
                """当在对话框中选择文件/目录时，更新路径输入框"""
                path_input.setText(dlg.directory().path())

            # 监听对话框的目录变化
            try:
                dlg.directoryEntered.connect(update_path_input)
            except Exception:
                pass

            # 按钮：导航到指定路径
            nav_btn = QPushButton("转到")
            nav_btn.setToolTip("导航到输入的路径")
            nav_btn.setMaximumWidth(50)
            nav_btn.clicked.connect(navigate_to_path)

            # 按钮：刷新路径输入框
            refresh_btn = QPushButton("刷新")
            refresh_btn.setToolTip("刷新当前路径")
            refresh_btn.setMaximumWidth(50)

            def refresh_path():
                """刷新路径输入框为当前目录"""
                path_input.setText(dlg.directory().path())

            refresh_btn.clicked.connect(refresh_path)

            # 回车键导航
            path_input.returnPressed.connect(navigate_to_path)

            path_layout.addWidget(path_label)
            path_layout.addWidget(path_input, 1)
            path_layout.addWidget(nav_btn)
            path_layout.addWidget(refresh_btn)

            # 将路径布局添加到对话框
            layout = dlg.layout()
            if layout:
                # 在顶部插入路径输入框
                layout.insertLayout(0, path_layout)
        except Exception as e:
            logger.debug(f"添加路径输入框失败: {e}")

        # 允许切换目录模式
        chk_dir = QCheckBox("选择目录（切换到目录选择模式）")
        chk_dir.setToolTip("勾选后可以直接选择文件夹；不勾选则选择单个数据文件。")
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

        try:
            chk_dir.toggled.connect(on_toggle_dir)
        except Exception:
            pass

        return dlg

    def _scan_and_populate_files(self, chosen_path: Path):
        """扫描所选路径并在文件树中显示（支持目录结构，默认全选）。"""
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
                    try:
                        self._set_control_enabled_with_style(
                            self.gui.inp_pattern, not is_file
                        )
                    except Exception:
                        pass
                if (
                    hasattr(self.gui, "cmb_pattern_preset")
                    and self.gui.cmb_pattern_preset is not None
                ):
                    try:
                        self._set_control_enabled_with_style(
                            self.gui.cmb_pattern_preset, not is_file
                        )
                    except Exception:
                        pass
            except Exception:
                logger.debug("设置匹配控件/输入框启用状态失败", exc_info=True)
            files, base_path = self._collect_files_for_scan(p)

            # 检查UI组件是否存在
            if not hasattr(self.gui, "file_tree"):
                return

            # 清空旧的树项
            self.gui.file_tree.clear()
            # 访问 GUI 的受保护属性以维护文件树映射。
            # pylint: disable=protected-access
            self.gui._file_tree_items = {}
            # pylint: enable=protected-access

            if not files:
                try:
                    self.gui.file_list_widget.setVisible(False)
                except Exception:
                    pass
                return

            # 步骤2：进入文件列表选择阶段（委托 helper 以降低复杂度）
            try:
                self._prepare_file_list_ui()
            except Exception:
                pass

            try:
                self._populate_file_tree_from_files(files, base_path, p)
            except Exception:
                logger.debug("填充文件树失败", exc_info=True)

        except Exception as e:
            logger.error(f"扫描并填充文件列表失败: {e}")
            traceback.print_exc()

    def _prepare_file_list_ui(self) -> None:
        """准备文件列表界面（设置 workflow step 与状态栏）。"""
        try:
            bp = getattr(self.gui, "batch_panel", None)
            if bp is not None and hasattr(bp, "set_workflow_step"):
                try:
                    bp.set_workflow_step("step2")
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.gui.statusBar().showMessage("步骤2：在文件列表选择数据文件")
        except Exception:
            pass

    def _populate_file_tree_from_files(self, files, base_path, p: Path) -> None:
        """根据 files 填充 `self.gui.file_tree` 并显示文件列表区域。

        委托到 `gui.batch_manager_files` 子模块实现以便拆分。
        """
        # 委托给 files 子模块实现（已在模块顶层导入）
        return _populate_file_tree_from_files_impl(self, files, base_path, p)

    def _safe_add_file_tree_entry(
        self, base_path: Path, dir_items: dict, fp: Path, single_file_mode: bool
    ) -> None:
        """安全地调用 `_add_file_tree_entry` 并在发生异常时记录调试信息。"""
        return _safe_add_file_tree_entry_impl(
            self, base_path, dir_items, fp, single_file_mode
        )

    def _sync_row_selection(
        self,
        fp_str: str,
        row_idx,
        checked: bool,
        *,
        is_special: bool = False,
        source_part: Optional[str] = None,
    ) -> None:  # pylint: disable=too-many-arguments
        """同步单行复选框状态到对应的 selection 缓存（special 或 常规）。"""
        try:
            try:
                idx_int = int(row_idx)
            except Exception:
                return

            if is_special:
                if not hasattr(self.gui, "special_part_row_selection_by_file"):
                    self.gui.special_part_row_selection_by_file = {}
                by_file = (
                    getattr(self.gui, "special_part_row_selection_by_file", {}) or {}
                )
                by_part = by_file.setdefault(fp_str, {})
                sel = by_part.get(source_part)
                if sel is None:
                    sel = set()
                    by_part[source_part] = sel
                if checked:
                    sel.add(idx_int)
                else:
                    sel.discard(idx_int)
                self.gui.special_part_row_selection_by_file = by_file
            else:
                if not hasattr(self.gui, "table_row_selection_by_file"):
                    self.gui.table_row_selection_by_file = {}
                by_file = getattr(self.gui, "table_row_selection_by_file", {}) or {}
                sel = by_file.get(fp_str)
                if sel is None:
                    sel = set()
                    by_file[fp_str] = sel
                if checked:
                    sel.add(idx_int)
                else:
                    sel.discard(idx_int)
                self.gui.table_row_selection_by_file = by_file
        except Exception:
            logger.debug("同步单行选择失败", exc_info=True)

    def _collect_files_for_scan(self, p: Path):
        return _collect_files_for_scan_impl(self, p)

    def _validate_file_config(self, file_path: Path) -> str:
        """验证文件的配置，返回状态文本"""
        status = None
        try:
            # 特殊格式：提前检查 part 是否存在于当前配置
            try:
                special_status = self._validate_special_format(file_path)
            except Exception:
                special_status = None
                logger.debug("特殊格式预检查失败", exc_info=True)

            if special_status is not None:
                status = special_status
            else:
                # 使用 helper 获取格式信息（含缓存)
                fmt_info = self._get_format_info(file_path)
                if not fmt_info:
                    status = "❌ 未知格式"
                else:
                    # 常规格式：若已加载配置，则要求为该文件选择 source/target（除非唯一可推断）
                    project_data = getattr(self.gui, "current_config", None)
                    status = self._evaluate_file_config_non_special(
                        file_path, fmt_info, project_data
                    )

        except Exception as exc:  # pylint: disable=broad-except
            logger.debug(f"验证文件配置失败: {exc}")
            status = "❓ 未验证"

        # 确保返回字符串（若为 None 则视为未验证）
        return status or "❓ 未验证"

    def _get_format_info(self, file_path: Path):
        """从缓存或解析器获取文件格式信息，若未知返回 None。"""
        try:
            cache = get_file_cache()
            cached_format = cache.get_metadata(file_path, "format_info")
            if cached_format:
                return cached_format

            base_cfg = BatchConfig()
            base_cfg.skip_rows = 0
            base_cfg.columns = {}
            base_cfg.passthrough = []

            fmt_info = resolve_file_format(str(file_path), base_cfg)
            if fmt_info:
                try:
                    cache.set_metadata(file_path, "format_info", fmt_info)
                except Exception:
                    pass
            return fmt_info
        except Exception:
            return None

    def _validate_special_format(self, file_path: Path) -> Optional[str]:
        """对特殊格式文件进行预检，返回状态文本或 None 表示非特殊格式。"""
        status = None
        try:
            if not looks_like_special_format(file_path):
                status = None
            else:
                part_names = get_part_names(file_path)
                mapping = self._get_special_mapping_if_exists(file_path)
                source_parts, target_parts = self._get_project_parts()

                # 若项目中无 parts 则提示待配置
                if not source_parts and not target_parts:
                    status = "✓ 特殊格式(待配置)"
                else:
                    mapping = mapping or {}
                    
                    # 检查新的映射结构：每个内部部件 -> {source, target}
                    unmapped_parts = []
                    missing_source_parts = []
                    missing_target_parts = []
                    
                    for part_name in part_names:
                        part_name_str = str(part_name)
                        part_mapping = mapping.get(part_name_str)
                        
                        if not isinstance(part_mapping, dict):
                            # 兼容旧格式或未映射
                            unmapped_parts.append(part_name_str)
                            continue
                        
                        source_part = (part_mapping.get("source") or "").strip()
                        target_part = (part_mapping.get("target") or "").strip()
                        
                        # 检查source part
                        if not source_part:
                            unmapped_parts.append(part_name_str)
                        elif source_part not in source_parts:
                            missing_source_parts.append(f"{part_name_str}→{source_part}")
                        
                        # 检查target part
                        if not target_part:
                            if source_part:  # 只有当source已选择时才检查target
                                unmapped_parts.append(part_name_str)
                        elif target_part not in target_parts:
                            missing_target_parts.append(f"{part_name_str}→{target_part}")
                    
                    if unmapped_parts:
                        status = f"⚠ 未映射: {', '.join(unmapped_parts)}"
                    elif missing_source_parts:
                        status = f"⚠ Source缺失: {', '.join(missing_source_parts)}"
                    elif missing_target_parts:
                        status = f"⚠ Target缺失: {', '.join(missing_target_parts)}"
                    else:
                        status = "✓ 特殊格式(可处理)"
        except Exception:
            logger.debug("特殊格式校验失败", exc_info=True)
            status = None
        return status

    def _get_special_mapping_if_exists(self, file_path: Path):
        """安全获取 GUI 中已存在的 special mapping（不初始化）。"""
        try:
            tmp = getattr(self.gui, "special_part_mapping_by_file", {}) or {}
            return tmp.get(str(file_path))
        except Exception:
            return None

    def _get_project_parts(self):
        """
        从 GUI 的 model 或 current_config 获取 source/target parts，
        返回 (source_parts, target_parts)。
        """
        source_parts = {}
        target_parts = {}
        try:
            model = getattr(self.gui, "project_model", None)
            if model is not None:
                source_parts = getattr(model, "source_parts", {}) or {}
                target_parts = getattr(model, "target_parts", {}) or {}
        except Exception:
            pass
        try:
            cfg = getattr(self.gui, "current_config", None)
            if cfg is not None:
                source_parts = source_parts or (getattr(cfg, "source_parts", {}) or {})
                target_parts = target_parts or (getattr(cfg, "target_parts", {}) or {})
        except Exception:
            pass
        return source_parts, target_parts

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
                    "步骤3：如需编辑配置请勾选“显示配置编辑器”；"
                    "步骤4：在文件列表设置映射"
                )
            except Exception:
                pass

            # 特殊格式：为该文件建立映射编辑区（无弹窗）
            try:
                if looks_like_special_format(file_path):
                    self._ensure_special_mapping_rows(item, file_path)
                else:
                    try:
                        self._handle_regular_file_click(item, file_path)
                    except Exception:
                        logger.debug(
                            "_handle_regular_file_click 调用失败", exc_info=True
                        )
            except Exception:
                logger.debug("ensure special mapping rows failed", exc_info=True)
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

    def _handle_regular_file_click(self, item, file_path: Path) -> None:
        """处理常规文件点击：建立 source/target 选择区并填充数据预览。"""
        try:
            try:
                self._ensure_regular_file_selector_rows(item, file_path)
            except Exception:
                logger.debug("建立常规文件选择区失败", exc_info=True)

            try:
                df_preview = self._get_table_df_preview(file_path, max_rows=200)
                if df_preview is not None:
                    self._populate_table_data_rows(item, file_path, df_preview)
            except Exception:
                logger.debug("填充表格数据行预览失败", exc_info=True)
        except Exception:
            logger.debug("_handle_regular_file_click 处理失败", exc_info=True)

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

    def _infer_part_from_text(self, text: str, candidate_names: list) -> Optional[str]:
        """从给定文本推测匹配的 part 名（必须唯一命中）。"""
        result = None
        try:
            src = (text or "").strip()
            if src:
                cands = [str(x) for x in (candidate_names or []) if str(x).strip()]
                if cands:
                    if src in cands:
                        result = src
                    else:
                        src_lower = src.lower()
                        ci = [t for t in cands if t.lower() == src_lower]
                        if len(ci) == 1:
                            result = ci[0]
                        else:

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
                            if src_norm:
                                nm = [t for t in cands if norm(t) == src_norm]
                                if len(nm) == 1:
                                    result = nm[0]
        except Exception:
            logger.debug("推测 part 失败", exc_info=True)
        return result

    def _determine_part_selection_status(self, file_path: Path, project_data) -> str:
        """基于 project_data 与当前选择推断该文件的 source/target 状态。"""
        try:
            sel = (getattr(self.gui, "file_part_selection_by_file", {}) or {}).get(
                str(file_path)
            ) or {}
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
        except Exception:
            logger.debug("确定 part 选择状态失败", exc_info=True)
            return "❓ 未验证"

    def _analyze_special_mapping(self, part_names, mapping, target_parts):
        """分析特殊格式的 part 映射，返回 (unmapped, missing_target)。"""
        unmapped = []
        missing_target = []
        try:
            for pn in part_names:
                tp = (mapping.get(pn) or "").strip()
                if not tp:
                    if pn in target_parts:
                        tp = pn
                    else:
                        unmapped.append(pn)
                        continue
                if tp not in target_parts:
                    missing_target.append(f"{pn}->{tp}")
        except Exception:
            logger.debug("分析特殊映射失败", exc_info=True)
        return unmapped, missing_target

    def _set_control_enabled_with_style(self, widget, enabled: bool) -> None:
        """设置控件启用状态并在单文件模式下通过文字颜色灰显提示（安全包装）。"""
        try:
            if widget is None:
                return
            try:
                widget.setEnabled(enabled)
            except Exception:
                # 个别自定义控件可能不支持 setEnabled
                pass
            try:
                # 仅修改文字颜色，避免破坏暗色主题背景
                widget.setStyleSheet("" if enabled else "color: gray;")
            except Exception:
                pass

        except Exception:
            logger.debug("设置控件启用/样式失败", exc_info=True)

    def _evaluate_file_config_non_special(
        self,
        file_path: Path,
        fmt_info,
        project_data,
    ) -> str:
        """评估非特殊格式文件的配置状态（小包装）。"""
        try:
            if project_data is None:
                return "✓ 格式正常(待配置)"
            return self._determine_part_selection_status(file_path, project_data)
        except Exception:
            logger.debug("评估常规文件配置失败", exc_info=True)
            return "❓ 未验证"

    def _add_file_tree_entry(
        self, base_path: Path, dir_items: dict, fp: Path, single_file_mode: bool
    ) -> None:
        """将单个文件添加到文件树，委托到 `gui.batch_manager_files` 实现。"""
        return _add_file_tree_entry_impl(
            self, base_path, dir_items, fp, single_file_mode
        )

    def _ensure_file_part_selection_storage(self, file_path: Path) -> dict:
        """确保常规文件的 source/target 选择缓存存在（委托子模块）。"""
        return _ensure_file_part_selection_storage_impl(self, file_path)

    def _remove_old_selector_children(self, file_item) -> None:
        """移除文件节点中已存在的 source/target selector 子节点（委托子模块）。"""
        return _remove_old_selector_children_impl(self, file_item)

    def _add_part_selector(
        self,
        file_item,
        file_path: Path,
        kind: str,
        label: str,
        names,
        current_value,
        on_change,
        tooltip=None,
    ) -> None:  # pylint: disable=too-many-arguments
        """为 file_item 添加一个下拉选择器并连接回调。"""
        item = QTreeWidgetItem([label, ""])
        item.setData(0, int(Qt.UserRole) + 1, {"kind": kind, "file": str(file_path)})
        file_item.addChild(item)

        combo = QComboBox(self.gui.file_tree)
        combo.setEditable(False)
        combo.setMinimumWidth(160)
        combo.addItem("（未选择）", "")
        for n in names:
            combo.addItem(n, n)
        if not names and tooltip:
            combo.setEnabled(False)
            combo.setToolTip(tooltip)

        # 使用 helper 统一处理信号阻塞与选择，减少重复代码
        self._safe_set_combo_selection(combo, current_value, names)

        combo.currentTextChanged.connect(on_change)
        self.gui.file_tree.setItemWidget(item, 1, combo)

    def _ensure_regular_file_selector_rows(self, file_item, file_path: Path) -> None:
        return _ensure_regular_file_selector_rows_impl(self, file_item, file_path)

    def _infer_target_part(self, source_part: str, target_names: list) -> Optional[str]:
        return _infer_target_part_impl(self, source_part, target_names)

    def _make_part_change_handler(self, fp_str: str, key: str):
        return _make_part_change_handler_impl(self, fp_str, key)

    def _auto_fill_special_mappings(
        self,
        file_path: Path,
        part_names: list,
        source_names: list,
        target_names: list,
        mapping: dict,
    ) -> bool:
        """为某个文件自动补全未映射的 内部部件->source->target。

        Returns:
            是否发生了映射变更。
        """
        return _auto_fill_special_mappings_impl(
            self, file_path, part_names, source_names, target_names, mapping
        )

    def _get_or_init_special_mapping(self, file_path: Path) -> dict:
        return _get_or_init_special_mapping_impl(self, file_path)

    def _create_part_mapping_combo(
        self, file_path: Path, source_part, target_names: list, mapping: dict
    ):
        return _create_part_mapping_combo_impl(
            self, file_path, source_part, target_names, mapping
        )

    def _safe_set_combo_selection(self, combo, current, names):
        return _safe_set_combo_selection_impl(self, combo, current, names)

    def _create_special_part_node(
        self,
        file_item,
        file_path: Path,
        internal_part_name: str,
        source_names: list,
        target_names: list,
        mapping: dict,
        data_dict: dict,
    ) -> None:
        return _create_special_part_node_impl(
            self, file_item, file_path, internal_part_name, source_names, target_names, mapping, data_dict
        )

    def _safe_populate_special_preview(
        self, child, file_path: Path, source_part, data_dict: dict
    ):
        """安全地填充单个 special part 的数据预览表格（捕获异常）。"""
        try:
            df = (data_dict or {}).get(str(source_part))
            if df is not None:
                sp = str(source_part)
                self._populate_special_data_rows(child, file_path, sp, df)
        except Exception:
            logger.debug("填充数据行预览失败", exc_info=True)

    def _ensure_special_mapping_rows(self, file_item, file_path: Path) -> None:
        """在文件节点下创建/刷新子节点：每个内部部件一行，包含source和target两个下拉框。"""
        try:
            mapping = self._get_or_init_special_mapping(file_path)
            mapping_by_file = getattr(self.gui, "special_part_mapping_by_file", {})
            mapping_by_file = mapping_by_file or {}
            part_names = get_part_names(file_path)
            source_names = self._get_source_part_names()
            target_names = self._get_target_part_names()

            # 智能推测：在加载配置/新增 part 后自动补全未映射项（不覆盖用户已设置的映射）
            try:
                if source_names and target_names:
                    if self._auto_fill_special_mappings(
                        file_path,
                        part_names,
                        source_names,
                        target_names,
                        mapping,
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

            for internal_part_name in part_names:
                try:
                    self._create_special_part_node(
                        file_item,
                        file_path,
                        internal_part_name,
                        source_names,
                        target_names,
                        mapping,
                        data_dict,
                    )
                except Exception:
                    logger.debug("创建 special part 节点失败", exc_info=True)

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
        return _run_batch_processing_impl(self)

    def _now_str(self):
        return datetime.now().strftime("%H:%M:%S")

    def _attach_batch_thread_signals(self):
        """为当前的 `self.batch_thread` 连接信号（安全地忽略错误）。"""
        # 委托给批处理子模块的实现（已在模块顶层导入）
        try:
            return _attach_batch_thread_signals_impl(self)
        except Exception:
            logger.debug("连接 batch_thread 信号失败", exc_info=True)
            return None

    def _prepare_gui_for_batch(self):
        """更新 GUI 状态以进入批处理模式（锁定控件、切换标签、禁用按钮）。"""
        try:
            return _prepare_gui_for_batch_impl(self)
        except Exception:
            logger.debug("准备 GUI 进入批处理失败", exc_info=True)
            return None

    def _create_batch_thread(
        self, files_to_process, output_path: Path, data_config, project_data
    ):
        return _create_batch_thread_impl(
            self, files_to_process, output_path, data_config, project_data
        )

    def _restore_gui_after_batch(self, *, enable_undo: bool = False):
        return _restore_gui_after_batch_impl(self, enable_undo=enable_undo)

    def _collect_files_from_tree(self):
        """从 GUI 的文件树中收集被勾选的文件并返回 Path 列表（安全包装）。"""
        files = []
        try:
            if not hasattr(self.gui, "file_tree") or self.gui.file_tree is None:
                return files
            iterator = QTreeWidgetItemIterator(self.gui.file_tree)
            while iterator.value():
                try:
                    item = iterator.value()
                    file_path_str = item.data(0, Qt.UserRole)
                    if file_path_str and item.checkState(0) == Qt.Checked:
                        files.append(Path(file_path_str))
                except Exception:
                    pass
                iterator += 1
        except Exception:
            logger.debug("从树收集文件失败", exc_info=True)
        return files

    def _get_patterns_from_widget(self):
        """从 GUI 的 pattern 控件获取模式列表和原始显示文本。

        返回 (patterns_list, pattern_display_text)
        """
        pattern_widget = getattr(self.gui, "inp_pattern", None)
        pattern_text = (
            pattern_widget.text().strip()
            if (pattern_widget and hasattr(pattern_widget, "text"))
            else "*.csv"
        )
        patterns = [x.strip() for x in pattern_text.split(";") if x.strip()]
        if not patterns:
            patterns = ["*.csv"]
        return patterns, pattern_text

    def _collect_files_to_process(self, input_path: Path):
        # 委托给文件相关子模块实现
        return _collect_files_to_process_impl(self, input_path)

    def _scan_dir_for_patterns(self, input_path: Path, patterns: list) -> list:
        return _scan_dir_for_patterns_impl(self, input_path, patterns)

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
            self._record_batch_history(status="completed")
            # 恢复 GUI 状态并提示完成
            self._restore_gui_after_batch(enable_undo=True)
            QMessageBox.information(self.gui, "完成", message)
        except Exception as e:
            logger.error(f"处理完成事件失败: {e}")

    def on_batch_error(self, error_msg: str):
        """批处理错误回调"""
        try:
            logger.error(f"批处理错误: {error_msg}")
            self._record_batch_history(status="failed")
            # 恢复 GUI 状态并提示错误
            self._restore_gui_after_batch(enable_undo=False)
            QMessageBox.critical(self.gui, "错误", f"批处理出错: {error_msg}")
        except Exception as e:
            logger.error(f"处理错误事件失败: {e}")

    def _record_batch_history(self, status: str = "completed") -> None:
        """记录批处理历史并刷新右侧历史面板。"""
        try:
            store = self.history_store or getattr(self.gui, "history_store", None)
            if store is None:
                return

            ctx = getattr(self, "_current_batch_context", {}) or {}
            input_path = ctx.get("input_path", "")
            files = ctx.get("files", [])
            output_dir = ctx.get("output_dir") or getattr(
                self.gui, "_batch_output_dir", None
            )
            if not output_dir:
                return

            try:
                output_path = Path(output_dir)
            except Exception:
                return

            existing = getattr(self.gui, "_batch_existing_files", set()) or set()
            existing_resolved = set()
            for p in existing:
                try:
                    existing_resolved.add(str(Path(p).resolve()))
                except Exception:
                    existing_resolved.add(str(p))

            current_files = []
            try:
                for f in output_path.glob("*"):
                    if f.is_file():
                        current_files.append(str(f.resolve()))
            except Exception:
                pass

            new_files = [p for p in current_files if p not in existing_resolved]
            rec = store.add_record(
                input_path=input_path,
                output_dir=str(output_path),
                files=files,
                new_files=new_files,
                status=status,
            )
            try:
                self._last_history_record_id = rec.get("id")
            except Exception:
                pass

            try:
                if self.history_panel is not None:
                    self.history_panel.refresh()
            except Exception:
                logger.debug("刷新历史面板失败", exc_info=True)
        except Exception:
            logger.debug("记录批处理历史失败", exc_info=True)

    def undo_history_record(self, record_id: str) -> None:
        """撤销指定历史记录（删除新生成的输出文件）。"""
        try:
            store = self.history_store or getattr(self.gui, "history_store", None)
            if store is None or not record_id:
                return

            record = None
            for rec in store.get_records():
                if rec.get("id") == record_id:
                    record = rec
                    break
            if record is None:
                return

            new_files = record.get("new_files") or []
            deleted = 0
            for p in new_files:
                try:
                    fp = Path(p)
                    if fp.exists() and fp.is_file():
                        fp.unlink()
                        deleted += 1
                except Exception:
                    logger.debug("删除输出文件失败", exc_info=True)

            store.mark_status(record_id, "undone")
            try:
                if self.history_panel is not None:
                    self.history_panel.refresh()
            except Exception:
                pass

            try:
                QMessageBox.information(
                    self.gui, "撤销完成", f"已删除 {deleted} 个输出文件"
                )
            except Exception:
                logger.debug("撤销提示失败", exc_info=True)
        except Exception:
            logger.debug("撤销历史记录失败", exc_info=True)

    # 文件来源标签相关实现已完全移除

    # 文件来源相关的对外接口已移除

    # 对外提供与 gui.py 同名的委托入口（供 GUI 壳方法调用）
    def on_pattern_changed(self):
        return self._on_pattern_changed()

    def scan_and_populate_files(self, chosen_path: Path):
        return self._scan_and_populate_files(chosen_path)

    # refresh_format_labels 已移除

    def _get_active_special_part_context(self):
        """判断当前焦点是否在特殊格式的 part/数据行上。

        Returns:
            (part_item, file_path_str, source_part) 或 (None, None, None)
        """
        part_item = None
        fp_str = None
        sp = None
        try:
            if not hasattr(self.gui, "file_tree") or self.gui.file_tree is None:
                return None, None, None

            item = self.gui.file_tree.currentItem()
            if item is None:
                selected = self.gui.file_tree.selectedItems()
                item = selected[0] if selected else None

            # 优先尝试通过焦点反推（修复表格聚焦但树项未切换时无法识别的问题）
            try:
                fw = (
                    QApplication.instance().focusWidget()
                    if QApplication.instance()
                    else None
                )
                if fw is not None:
                    res = self._detect_focus_in_special_tables(fw)
                    if res:
                        part_item, fp_str, sp = res
            except Exception:
                pass

            if part_item is None and item is not None:
                p_item, p_fp_str, p_sp = self._extract_special_context_from_item(item)
                if p_item is not None:
                    part_item, fp_str, sp = p_item, p_fp_str, p_sp
        except Exception:
            logger.debug("获取当前特殊 part 上下文失败", exc_info=True)

        return part_item, fp_str, sp

    def _extract_special_context_from_item(self, item):
        """从树项提取特殊 part 上下文。

        返回 (part_item, file_path_str, source_part) 或 (None, None, None)。
        """
        try:
            meta = self._get_item_meta(item)
            if not isinstance(meta, dict):
                return None, None, None

            kind = meta.get("kind")
            if kind == "special_part":
                fp = str(meta.get("file") or "")
                sp = str(meta.get("source") or "")
                return item, fp, sp

            if kind == "special_data_row":
                parent = item.parent()
                if parent is None:
                    return None, None, None
                parent_meta = self._get_item_meta(parent)
                if (
                    isinstance(parent_meta, dict)
                    and parent_meta.get("kind") == "special_part"
                ):
                    fp = str(parent_meta.get("file") or "")
                    sp = str(parent_meta.get("source") or "")
                    return parent, fp, sp
        except Exception:
            return None, None, None

        return None, None, None

    def _get_active_table_context(self):
        """判断当前焦点是否在常规表格数据行上。

        Returns:
            (file_item, file_path_str) 或 (None, None)
        """
        file_item = None
        fp_str = None
        try:
            if not hasattr(self.gui, "file_tree") or self.gui.file_tree is None:
                return None, None
            item = self.gui.file_tree.currentItem()
            if item is None:
                selected = self.gui.file_tree.selectedItems()
                item = selected[0] if selected else None

            # 始终尝试通过焦点反推上下文，避免当前树项干扰
            try:
                fw = (
                    QApplication.instance().focusWidget()
                    if QApplication.instance()
                    else None
                )
                if fw is not None:
                    res = self._detect_focus_in_tables(fw)
                    if res:
                        file_item, fp_str = res
            except Exception:
                pass

            if file_item is None and item is not None:
                meta = self._get_item_meta(item)
                if isinstance(meta, dict):
                    kind = meta.get("kind")
                    if kind == "table_data_group":
                        fp_str = str(meta.get("file") or "")
                        if fp_str:
                            file_item = getattr(self.gui, "_file_tree_items", {}).get(
                                fp_str
                            )
                    elif kind == "table_data_row":
                        fp_str = str(meta.get("file") or "")
                        if fp_str:
                            file_item = getattr(self.gui, "_file_tree_items", {}).get(
                                fp_str
                            )
        except Exception:
            logger.debug("获取当前表格数据行上下文失败", exc_info=True)

        return file_item, fp_str

    def _detect_focus_in_tables(self, fw):
        """检测焦点是否位于某个常规表格预览中，若是返回 (file_item, fp_str)。"""
        try:
            for fp_str, table in (self._table_preview_tables or {}).items():
                w = fw
                inner = getattr(table, "table", None)
                while w is not None:
                    if w is table or (inner is not None and w is inner):
                        file_item = getattr(self.gui, "_file_tree_items", {}).get(
                            fp_str
                        )
                        if file_item is not None:
                            return file_item, fp_str
                        break
                    w = w.parentWidget()
        except Exception:
            pass
        return None

    def _detect_focus_in_special_tables(self, fw):
        """检测焦点是否位于某个特殊格式预览表格中，若是返回 (part_item, fp_str, sp)。"""
        try:
            for (fp_str, sp), table in (self._special_preview_tables or {}).items():
                w = fw
                inner = getattr(table, "table", None)
                while w is not None:
                    if w is table or (inner is not None and w is inner):
                        part_item = self._find_special_part_item(fp_str, sp)
                        if part_item is not None:
                            return part_item, fp_str, sp
                        break
                    w = w.parentWidget()
        except Exception:
            pass
        return None

    def _should_bulk_apply_row_selection(self) -> bool:
        """是否对所有选中文件批量应用行选择操作。"""
        try:
            bp = getattr(self.gui, "batch_panel", None)
            chk = (
                getattr(bp, "chk_bulk_row_selection", None) if bp is not None else None
            )
            if chk is None:
                return False
            return bool(chk.isChecked())
        except Exception:
            return False

    def _iter_checked_file_items(self):
        """遍历当前文件树中被勾选的文件项（仅文件项）。"""
        try:
            if not hasattr(self.gui, "file_tree") or self.gui.file_tree is None:
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

    def _collect_row_items_for_file(self, file_item):
        """从文件节点中收集属于表格数据行的子项列表，若未找到则返回空列表。"""
        group = None
        for i in range(file_item.childCount()):
            try:
                child = file_item.child(i)
                meta = self._get_item_meta(child)
                if isinstance(meta, dict) and meta.get("kind") == "table_data_group":
                    group = child
                    break
            except Exception:
                continue
        if group is None:
            return []

        row_items = []
        for i in range(group.childCount()):
            try:
                child = group.child(i)
                meta = self._get_item_meta(child)
                if isinstance(meta, dict) and meta.get("kind") == "table_data_row":
                    row_items.append(child)
            except Exception:
                continue
        return row_items

    def _apply_mode_to_tree_row_items(self, row_items, fp_str, mode, by_file) -> None:
        """针对树节点的行集合应用 `all|none|invert` 操作并更新 by_file 与 GUI 状态。"""
        if not row_items:
            return

        self._is_updating_tree = True
        try:
            if mode == "all":
                by_file[fp_str] = self._select_all_row_items(row_items)

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

    def _select_all_row_items(self, row_items):
        """将 row_items 全部选中并返回所选索引集合（安全包装）。"""
        selected = set()
        try:
            for child in row_items:
                meta = self._get_item_meta(child) or {}
                idx = meta.get("row")
                try:
                    idx_int = int(idx)
                except Exception:
                    continue
                selected.add(idx_int)
                child.setCheckState(0, Qt.Checked)
        except Exception:
            logger.debug("选中所有行时发生错误", exc_info=True)
        return selected

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
                by_file[fp_str] = self._apply_table_checkbox_mode(
                    table, mode, by_file, fp_str
                )
            finally:
                self._is_updating_tree = False
            self.gui.table_row_selection_by_file = by_file
            return

        # 回退：无表格时使用树节点（委托给 helper 处理以降低复杂度）
        row_items = self._collect_row_items_for_file(file_item)
        if not row_items:
            return
        self._apply_mode_to_tree_row_items(row_items, fp_str, mode, by_file)

    def _apply_table_checkbox_mode(self, table, mode, by_file, fp_str):
        """在表格预览中按 `mode` 操作复选框并返回更新后的选中集合。"""
        selected = set(by_file.get(fp_str) or set())
        try:
            rows = table.rowCount()
            for r in range(rows):
                try:
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
                except Exception:
                    # 单行出错则跳过，保持健壮性
                    continue
        except Exception:
            logger.debug("在表格中应用复选框模式失败", exc_info=True)
        return selected

    def _collect_special_row_items_for_part(self, part_item):
        """从 part 节点中收集属于 special 数据行的子项列表，若未找到则返回空列表。"""
        row_items = []
        for i in range(part_item.childCount()):
            try:
                child = part_item.child(i)
                meta = self._get_item_meta(child)
                if isinstance(meta, dict) and meta.get("kind") == "special_data_row":
                    row_items.append(child)
            except Exception:
                continue
        return row_items

    def _apply_mode_to_special_row_items(
        self, row_items, fp_str, source_part, mode, by_file
    ) -> None:
        """针对 special 类型的树节点行集合应用 `all|none|invert` 操作并更新 by_file 与 GUI 状态。"""
        if not row_items:
            return

        by_part = by_file.setdefault(fp_str, {})
        self._is_updating_tree = True
        try:
            if mode == "all":
                by_part[str(source_part)] = self._select_all_special_row_items(
                    row_items
                )

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

    def _apply_mode_to_special_table(self, table, by_part, source_part, mode):
        """在特殊格式的预览表格上按 mode 操作复选框并返回更新后的选中集合。"""
        selected = set(by_part.get(str(source_part)) or set())
        try:
            rows = table.rowCount()
            for r in range(rows):
                try:
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
                except Exception:
                    continue
        except Exception:
            logger.debug("在 special 表格中应用复选框模式失败", exc_info=True)
        return selected

    def _select_all_special_row_items(self, row_items):
        """将 special row_items 全部选中并返回所选索引集合（安全包装）。"""
        selected = set()
        try:
            for child in row_items:
                meta = self._get_item_meta(child) or {}
                idx = meta.get("row")
                try:
                    idx_int = int(idx)
                except Exception:
                    continue
                selected.add(idx_int)
                child.setCheckState(0, Qt.Checked)
        except Exception:
            logger.debug("选中所有 special 行时发生错误", exc_info=True)
        return selected

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
        by_file = getattr(self.gui, "special_part_row_selection_by_file", {}) or {}
        by_part = by_file.setdefault(fp_str, {})

        # 有表格则直接操作表格复选框
        if table is not None:
            self._is_updating_tree = True
            try:
                selected = self._apply_mode_to_special_table(
                    table, by_part, source_part, mode
                )
                by_part[str(source_part)] = selected
            finally:
                self._is_updating_tree = False
            self.gui.special_part_row_selection_by_file = by_file
            return

        # 回退：无表格时使用树节点
        # 回退：无表格时使用树节点（委托给 helper 处理以降低复杂度）
        row_items = self._collect_special_row_items_for_part(part_item)
        if not row_items:
            return
        self._apply_mode_to_special_row_items(
            row_items, fp_str, source_part, mode, by_file
        )

    # 文件选择方法（从 main_window 迁移）
    def select_all_files(self):
        """全选：文件模式下全选文件；数据模式下全选当前 part 数据行。"""
        part_item, fp_str, sp = self._get_active_special_part_context()
        if part_item is not None:
            self._set_special_part_rows_checked(part_item, fp_str, sp, mode="all")
            return

        file_item, table_fp = self._get_active_table_context()
        if file_item is not None and table_fp:
            if self._should_bulk_apply_row_selection():
                for it, fp in self._iter_checked_file_items() or []:
                    self._set_table_rows_checked_for_file(it, str(fp), mode="all")
            else:
                self._set_table_rows_checked_for_file(file_item, table_fp, mode="all")
            return
        self._set_all_file_items_checked(Qt.Checked)

    def select_none_files(self):
        """全不选：文件模式下全不选文件；数据模式下全不选当前 part 数据行。"""
        part_item, fp_str, sp = self._get_active_special_part_context()
        if part_item is not None:
            self._set_special_part_rows_checked(part_item, fp_str, sp, mode="none")
            return

        file_item, table_fp = self._get_active_table_context()
        if file_item is not None and table_fp:
            if self._should_bulk_apply_row_selection():
                for it, fp in self._iter_checked_file_items() or []:
                    self._set_table_rows_checked_for_file(it, str(fp), mode="none")
            else:
                self._set_table_rows_checked_for_file(file_item, table_fp, mode="none")
            return
        self._set_all_file_items_checked(Qt.Unchecked)

    def invert_file_selection(self):
        """反选：文件模式下反选文件；数据模式下反选当前 part 数据行。"""
        if not hasattr(self.gui, "file_tree"):
            return

        part_item, fp_str, sp = self._get_active_special_part_context()
        if part_item is not None:
            self._set_special_part_rows_checked(part_item, fp_str, sp, mode="invert")
            return

        file_item, table_fp = self._get_active_table_context()
        if file_item is not None and table_fp:
            if self._should_bulk_apply_row_selection():
                for it, fp in self._iter_checked_file_items() or []:
                    self._set_table_rows_checked_for_file(it, str(fp), mode="invert")
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
        return _request_cancel_batch_impl(self)

    def undo_batch_processing(self):
        return _undo_batch_processing_impl(self)

    def _delete_new_output_files(self, output_dir, existing_files):
        return _delete_new_output_files_impl(self, output_dir, existing_files)
