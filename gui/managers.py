"""GUI 管理器集合：将 `IntegratedAeroGUI` 的部分职责拆分为独立管理器。

设计原则：最小侵入、向后兼容。当前实现提供轻量包装，未来可逐步迁移逻辑。

=== 错误处理规范 ===

为保持错误处理一致性，应使用以下函数进行错误报告：

1. 非关键的 UI 操作异常 -> _report_ui_exception()
   - 适用：UI 交互失败、参数验证失败等
   - 行为：记录警告日志 + 状态栏提示（5秒）
   - 示例：无法更新控件、对话框操作失败

2. 用户可见的错误 -> report_user_error()
   - 适用：用户操作失败、处理流程中断等
   - 行为：记录错误日志 + 状态栏提示 + 错误消息框（如需）
   - 示例：浏览失败、批处理启动失败、文件解析失败
   
3. 仅记录日志的异常 -> logger.error/warning/debug()
   - 适用：内部编程错误、调试信息
   - 不应用于用户交互相关的错误
   
禁止直接使用：
- QMessageBox.critical() 直接调用（应用 report_user_error）
- print() 用于错误信息（应用日志系统）
"""

# 管理器模块中为避免循环导入，部分导入为延迟导入，允许 import-outside-toplevel
# 同时临时允许部分注释/文档导致的行过长告警（C0301）
# pylint: disable=import-outside-toplevel, line-too-long

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtWidgets import QWidget

import logging
import functools

_logger = logging.getLogger(__name__)


def _report_ui_exception(parent: QWidget, context: str, exc_info=True):
    """记录警告并尝试在主窗口状态栏显示轻量提示以便可见化异常。

    此工具用于替换仓库中大量的 silent-pass 模式，保持最小侵入性。
    """
    try:
        _logger.warning("UI 操作异常：%s", context, exc_info=exc_info)
    except Exception:
        try:
            _logger.warning("UI 操作异常（无法记录 exc_info）：%s", context)
        except Exception:
            pass
    try:
        # 使用 SignalBus 的统一状态通道以避免分散写入 statusBar
        try:
            from gui.signal_bus import SignalBus

            try:
                SignalBus.instance().statusMessage.emit(f"提示：{context}", 5000, 0)
                return
            except Exception:
                pass
        except Exception:
            pass

        if parent is not None and hasattr(parent, "statusBar"):
            try:
                sb = parent.statusBar()
                if sb is not None:
                    sb.showMessage(f"提示：{context}", 5000)
            except Exception:
                # 状态栏展示为非关键功能，忽略展示失败
                pass
    except Exception:
        pass


def report_user_error(parent: QWidget, title: str, message: str, details: str = None, is_warning: bool = False):
    """统一的用户错误报告函数：记录日志并显示用户可见的消息。
    
    参数：
        parent: 父窗口（用于消息框的父窗口和状态栏访问）
        title: 错误/警告标题
        message: 用户可读的错误消息
        details: 详细信息（可选，仅记录到日志）
        is_warning: 是否为警告而非错误（决定日志级别和图标）
    """
    # 记录到日志
    if is_warning:
        if details:
            _logger.warning("%s：%s - %s", title, message, details)
        else:
            _logger.warning("%s：%s", title, message)
    else:
        if details:
            _logger.error("%s：%s - %s", title, message, details)
        else:
            _logger.error("%s：%s", title, message)
    
    # 优先使用状态栏提示以避免过多弹窗
    try:
        from gui.signal_bus import SignalBus
        try:
            # 优先级：错误=高，警告=中
            priority = 1 if not is_warning else 0
            SignalBus.instance().statusMessage.emit(f"{title}：{message}", 8000, priority)
            return
        except Exception:
            pass
    except Exception:
        pass
    
    # 状态栏失败时尝试显示消息框（仅对关键错误）
    if not is_warning:
        try:
            from PySide6.QtWidgets import QMessageBox
            
            if parent is not None:
                QMessageBox.critical(parent, title, message)
            return
        except Exception:
            pass
    
    # 最后尝试直接更新状态栏
    try:
        if parent is not None and hasattr(parent, "statusBar"):
            sb = parent.statusBar()
            if sb is not None:
                sb.showMessage(f"{title}：{message}", 8000)
    except Exception:
        pass


def report_exceptions(context: str = None):
    """装饰器：包装方法，在捕获异常时记录并向 UI 报告，而不是静默吞掉。

    使用示例：
        @report_exceptions("标记 skipped rows 失败")
        def mark_skipped_rows(...):
            ...
    """
    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                try:
                    # 尝试从实例中获取 parent 以进行 UI 报告
                    parent = None
                    if len(args) >= 1:
                        inst = args[0]
                        parent = getattr(inst, "parent", None)
                    msg = context or f"{func.__name__} 执行失败"
                    _report_ui_exception(parent, msg, exc_info=True)
                except Exception:
                    try:
                        _logger.exception("report_exceptions failed while reporting")
                    except Exception:
                        pass
                # 仍记录异常到日志（供开发定位）
                try:
                    _logger.exception(f"Exception in {func.__name__}")
                except Exception:
                    pass
                # 返回 None 或适当的默认值以保持向后兼容（多数调用者忽略返回值）
                return None
        return wrapper
    return deco


def normalize_path_key(p):
    """规范化路径键为绝对解析字符串（兼容 Path / str）。"""
    try:
        if p is None:
            return None
        # 如果已经是 Path，直接解析；否则尝试构造 Path
        kp = p if isinstance(p, Path) else Path(str(p))
        return str(kp.resolve())
    except Exception:
        try:
            return str(p)
        except Exception:
            return None


class FileSelectionManager:
    """管理与文件选择相关的状态与映射。

    属性保留旧名称以保证向后兼容（主窗口可直接读取这些属性）。
    """

    def __init__(self, parent: QWidget):
        self.parent = parent
        # 将 UI 级别状态迁移到此管理器内部（single source of truth）
        # 同时在设置时尝试同步回 parent 属性以兼容可能直接访问 parent 属性的旧代码。
        self._data_loaded = False
        self._config_loaded = False
        self._operation_performed = False
        # 内部锁计数：允许嵌套的锁请求（例如批处理启动/子流程），
        # 仅当计数为0->1时真正禁用控件，计数回退到0时恢复控件。
        self._lock_count = 0
        # 特殊格式映射：{str(file): {source_part: target_part}}
        self.special_part_mapping_by_file: Dict[str, Dict[str, str]] = {}
        # 特殊格式选中行：{str(file): {source_part: set(row_idx)}}
        self.special_part_row_selection_by_file: Dict[str, Dict[str, set]] = {}
        # 常规文件的 part 选择：{str(file): {"source": str, "target": str}}
        self.file_part_selection_by_file: Dict[str, Dict[str, str]] = {}
        # 常规文件的行选择：{str(file): set(row_idx)} or None
        self.table_row_selection_by_file: Dict[str, Optional[set]] = {}
        # 被用户标记为跳过的行：{str(file): set(row_idx)}
        # 用于在处理时忽略特定行（可序列化到 Project 文件）
        self.skipped_rows_by_file: Dict[str, Optional[set]] = {}

    # ---- skipped rows API ----
    def mark_skipped_rows(self, file_path: Path, rows) -> None:
        """标记指定文件的多行为跳过（rows 可以是可迭代的索引）。"""
        @report_exceptions("标记 skipped rows 失败")
        def _impl(file_path, rows):
            try:
                key = str(Path(file_path).resolve()) if file_path is not None else str(file_path)
            except Exception:
                key = str(file_path)
            existing = self.skipped_rows_by_file.get(key) or set()
            existing = set(existing)
            existing.update(set(rows or []))
            self.skipped_rows_by_file[key] = existing
            try:
                setattr(self.parent, "skipped_rows_by_file", self.skipped_rows_by_file)
            except Exception:
                _report_ui_exception(self.parent, "同步 skipped_rows_by_file 到父窗口失败")

        return _impl(file_path, rows)

    def clear_skipped_rows(self, file_path: Path, rows=None) -> None:
        """清除指定文件的跳过行；若 rows 为 None 则清空所有跳过行。"""
        @report_exceptions("清理 skipped rows 失败")
        def _impl(file_path, rows=None):
            try:
                key = str(Path(file_path).resolve()) if file_path is not None else str(file_path)
            except Exception:
                key = str(file_path)
            if rows is None:
                self.skipped_rows_by_file.pop(key, None)
            else:
                existing = self.skipped_rows_by_file.get(key) or set()
                existing = set(existing)
                for r in rows:
                    existing.discard(r)
                if existing:
                    self.skipped_rows_by_file[key] = existing
                else:
                    self.skipped_rows_by_file.pop(key, None)
            try:
                setattr(self.parent, "skipped_rows_by_file", self.skipped_rows_by_file)
            except Exception:
                _report_ui_exception(self.parent, "同步 skipped_rows_by_file 到父窗口失败（清理）")

        return _impl(file_path, rows)

    def get_skipped_rows(self, file_path: Path):
        """返回指定文件的跳过行集合（set）或 None。"""
        @report_exceptions("读取 skipped rows 失败")
        def _impl(file_path):
            try:
                key = str(Path(file_path).resolve()) if file_path is not None else str(file_path)
            except Exception:
                key = str(file_path)
            s = self.skipped_rows_by_file.get(key)
            try:
                setattr(self.parent, "skipped_rows_by_file", self.skipped_rows_by_file)
            except Exception:
                _report_ui_exception(self.parent, "同步 skipped_rows_by_file 到父窗口失败（读取）")
            return set(s) if s is not None else None

        return _impl(file_path)

    def ensure_special_row_selection_storage(
        self, file_path: Path, part_names: list
    ) -> dict:
        """确保行选择缓存存在，并为未初始化的 part 默认全选。

        返回 by_part dict（可被调用方修改）。
        """
        @report_exceptions("ensure_special_row_selection_storage 失败")
        def _impl(file_path, part_names):
            by_file = self.special_part_row_selection_by_file or {}
            key = None
            try:
                key = normalize_path_key(file_path)
            except Exception:
                try:
                    key = str(file_path)
                except Exception:
                    key = None
            if key is None:
                return {}
            by_file.setdefault(key, {})
            by_part = by_file[key]
            for pn in part_names:
                by_part.setdefault(str(pn), None)
            self.special_part_row_selection_by_file = by_file
            try:
                setattr(self.parent, "special_part_row_selection_by_file", self.special_part_row_selection_by_file)
            except Exception:
                _report_ui_exception(self.parent, "同步 special_part_row_selection_by_file 到父窗口失败")
            return by_part

        return _impl(file_path, part_names)

    def open_quick_select_dialog(self) -> None:
        """打开快速选择对话框（委托给 GUI 的 QuickSelectDialog）。"""
        @report_exceptions("打开快速选择对话失败")
        def _impl():
            from gui.quick_select_dialog import QuickSelectDialog

            dlg = QuickSelectDialog(self, parent=self.parent)
            dlg.exec()

        return _impl()


class ModelManager:
    """管理核心数据模型（calculator / project_model / current_config）。

    用于集中管理模型实例，便于在未来注入或 mock。
    """

    def __init__(self, parent: QWidget):
        self.parent = parent
        self.calculator = None
        self.current_config = None
        self.project_model = None

    def _ensure_project_model(self) -> bool:
        """确保 parent（主窗口）持有 ProjectConfigModel，必要时创建空模型。

        返回 True 如果存在或创建成功，False 否则。
        """
        try:
            if getattr(self.parent, "project_model", None) is None:
                from src.models import ProjectConfigModel

                try:
                    self.parent.project_model = ProjectConfigModel()
                    self.project_model = self.parent.project_model
                except Exception:
                    return False
            else:
                self.project_model = self.parent.project_model
            return True
        except Exception:
            return False

    def save_current_source_part(self):
        """保存当前 Source 面板的变体到 ProjectConfigModel（与 PartManager 共用逻辑）。"""
        try:
            if not self._ensure_project_model():
                return
            part_name = (
                self.parent.source_panel.part_name_input.text()
                if hasattr(self.parent, "source_panel")
                else "Global"
            )
            if hasattr(self.parent, "source_panel"):
                # 使用面板提供的强类型模型接口
                cs_model = (
                    self.parent.source_panel.get_coordinate_system_model()
                )
                refs_model = (
                    self.parent.source_panel.get_reference_values_model()
                )
                from src.models.project_model import Part as PMPart
                from src.models.project_model import PartVariant as PMVariant

                pm_variant = PMVariant(
                    part_name=part_name, coord_system=cs_model, refs=refs_model
                )
                self.parent.project_model.source_parts[part_name] = PMPart(
                    part_name=part_name, variants=[pm_variant]
                )
                self.project_model = self.parent.project_model
        except Exception:
            pass

    def save_current_target_part(self):
        """保存当前 Target 面板的变体到 ProjectConfigModel。"""
        try:
            if not self._ensure_project_model():
                return
            part_name = (
                self.parent.target_panel.part_name_input.text()
                if hasattr(self.parent, "target_panel")
                else "Target"
            )
            if hasattr(self.parent, "target_panel"):
                cs_model = (
                    self.parent.target_panel.get_coordinate_system_model()
                )
                refs_model = (
                    self.parent.target_panel.get_reference_values_model()
                )
                from src.models.project_model import Part as PMPart
                from src.models.project_model import PartVariant as PMVariant

                pm_variant = PMVariant(
                    part_name=part_name, coord_system=cs_model, refs=refs_model
                )
                self.parent.project_model.target_parts[part_name] = PMPart(
                    part_name=part_name, variants=[pm_variant]
                )
                self.project_model = self.parent.project_model
        except Exception:
            pass

    # ---- 以下方法迁移自旧的 PartManager，供逐步重构使用 ----
    @staticmethod
    def _unique_name(base: str, existing: set) -> str:
        name = base or "Part"
        if name not in existing:
            return name
        idx = 1
        while f"{name}_{idx}" in existing:
            idx += 1
        return f"{name}_{idx}"

    def _get_variants(self, part_name: str, is_source: bool):
        """优先从 ProjectConfigModel 读取变体，缺失时回退到 legacy ProjectData。"""
        variants = []
        try:
            if self._ensure_project_model():
                parts = (
                    self.parent.project_model.source_parts
                    if is_source
                    else self.parent.project_model.target_parts
                )
                part = parts.get(part_name)
                if part:
                    variants = part.variants

            if not variants:
                cfg = getattr(self.parent, "current_config", None)
                if cfg:
                    parts = cfg.source_parts if is_source else cfg.target_parts
                    part = parts.get(part_name)
                    if part:
                        if isinstance(part, list):
                            variants = part
                        elif hasattr(part, "variants"):
                            variants = part.variants
        except Exception:
            logger = __import__("logging").getLogger(__name__)
            logger.debug("_get_variants failed", exc_info=True)
        return variants

    def _read_variant_fields(self, variant):
        try:
            if variant is None:
                return None, None, None, 0.0, 0.0, 0.0, 0.0

            cs = getattr(variant, "coord_system", None)
            part_name = getattr(variant, "part_name", "") or ""

            mc = None
            if (
                cs is not None
                and getattr(cs, "moment_center", None) is not None
            ):
                mc = list(getattr(cs, "moment_center"))
            if mc is None:
                mc = getattr(variant, "moment_center", None)
                if mc is not None:
                    mc = list(mc)
            if not mc:
                mc = [0.0, 0.0, 0.0]

            refs = getattr(variant, "refs", None)
            cref_val = getattr(refs, "cref", None) if refs else None
            bref_val = getattr(refs, "bref", None) if refs else None
            sref_val = getattr(refs, "sref", None) if refs else None
            q_val = getattr(refs, "q", None) if refs else None

            if cref_val is None:
                cref_val = getattr(variant, "c_ref", 0.0)
            if bref_val is None:
                bref_val = getattr(variant, "b_ref", 0.0)
            if sref_val is None:
                sref_val = getattr(variant, "s_ref", 0.0)
            if q_val is None:
                q_val = getattr(variant, "q", 0.0)

            try:
                cref_val = float(cref_val)
            except Exception:
                cref_val = 0.0
            try:
                bref_val = float(bref_val)
            except Exception:
                bref_val = 0.0
            try:
                sref_val = float(sref_val)
            except Exception:
                sref_val = 0.0
            try:
                q_val = float(q_val)
            except Exception:
                q_val = 0.0
            return part_name, cs, mc, cref_val, bref_val, sref_val, q_val
        except Exception:
            logger = __import__("logging").getLogger(__name__)
            logger.debug("_read_variant_fields failed", exc_info=True)
            return None, None, None, 0.0, 0.0, 0.0, 0.0

    def _rename_part(self, new_name: str, is_source: bool):
        logger = __import__("logging").getLogger(__name__)
        try:
            if not self._ensure_project_model():
                return
            new_name = (new_name or "").strip()
            if not new_name:
                return

            parts = (
                self.parent.project_model.source_parts
                if is_source
                else self.parent.project_model.target_parts
            )
            selector = None
            try:
                selector = (
                    self.parent.source_panel.part_selector
                    if is_source
                    else self.parent.target_panel.part_selector
                )
            except Exception:
                selector = None

            try:
                panel = (
                    self.parent.source_panel
                    if is_source
                    else self.parent.target_panel
                )
                current_name = getattr(panel, "_current_part_name", None)
                if not current_name and selector:
                    current_name = selector.currentText()
            except Exception:
                current_name = None

            if not current_name:
                return

            part_obj = parts.pop(current_name, None)
            if part_obj is None:
                return

            if new_name in parts:
                new_name = self._unique_name(new_name, set(parts.keys()))

            part_obj.part_name = new_name
            for v in part_obj.variants:
                try:
                    v.part_name = new_name
                except Exception:
                    logger.debug("同步变体名称失败", exc_info=True)

            parts[new_name] = part_obj

            if is_source:
                if hasattr(self.parent, "source_panel"):
                    self.parent.source_panel._current_part_name = new_name
            else:
                if hasattr(self.parent, "target_panel"):
                    self.parent.target_panel._current_part_name = new_name

            if selector:
                try:
                    idx = selector.findText(current_name)
                    if idx >= 0:
                        selector.setItemText(idx, new_name)
                    selector.setCurrentText(new_name)
                except Exception:
                    logger.debug("更新选择器名称失败", exc_info=True)
        except Exception:
            logger.debug("重命名 Part 失败", exc_info=True)

    def add_source_part(self, suggested_name: str = None):
        logger = __import__("logging").getLogger(__name__)
        try:
            if getattr(self.parent, "_is_initializing", False):
                logger.debug("初始化期间跳过 add_source_part")
                return
            if not self._ensure_project_model():
                return
            base_name = (suggested_name or "").strip()
            if not base_name:
                try:
                    base_name = (
                        self.parent.source_panel.part_name_input.text().strip()
                    )
                except Exception:
                    base_name = "NewSourcePart"
            existing = set(self.parent.project_model.source_parts.keys())
            name = self._unique_name(base_name, existing)

            try:
                cs_model = (
                    self.parent.source_panel.get_coordinate_system_model()
                )
                refs_model = (
                    self.parent.source_panel.get_reference_values_model()
                )
            except Exception:
                logger.debug("读取 Source 面板强类型数据失败", exc_info=True)
                cs_model = None
                refs_model = None
            if cs_model is None or refs_model is None:
                raise ValueError("无法从 Source 面板读取强类型数据")
            from src.models.project_model import Part as PMPart
            from src.models.project_model import PartVariant as PMVariant

            variant = PMVariant(
                part_name=name, coord_system=cs_model, refs=refs_model
            )
            self.parent.project_model.source_parts[name] = PMPart(
                part_name=name, variants=[variant]
            )
            if hasattr(self.parent, "source_panel"):
                self.parent.source_panel._current_part_name = name

            try:
                self.parent.signal_bus.partAdded.emit("Source", name)
            except Exception:
                logger.debug("发射 partAdded 信号失败", exc_info=True)
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(
                    self.parent, "成功", f'Source Part "{name}" 已添加'
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"添加 Source Part 失败: {e}")
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(self.parent, "错误", f"添加失败: {e}")
            except Exception:
                pass

    def remove_source_part(self, name_hint: str = None):
        logger = __import__("logging").getLogger(__name__)
        try:
            if not self._ensure_project_model():
                return
            name = (name_hint or "").strip()
            if not name:
                try:
                    name = self.parent.source_panel.part_selector.currentText()
                except Exception:
                    name = None
        except Exception:
            name = None
        if not name:
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self.parent, "提示", "没有可删除的 Source Part"
                )
            except Exception:
                pass
            return
        try:
            self.parent.project_model.source_parts.pop(name, None)
            self.parent._current_source_part_name = None
            try:
                self.parent.signal_bus.partRemoved.emit("Source", name)
            except Exception:
                logger.debug("发射 partRemoved 信号失败", exc_info=True)
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(
                    self.parent, "成功", f'Source Part "{name}" 已删除'
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"删除 Source Part 失败: {e}")
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(self.parent, "错误", f"删除失败: {e}")
            except Exception:
                pass

    def add_target_part(self, suggested_name: str = None):
        logger = __import__("logging").getLogger(__name__)
        try:
            if getattr(self.parent, "_is_initializing", False):
                logger.debug("初始化期间跳过 add_target_part")
                return
            if not self._ensure_project_model():
                return
            base_name = (suggested_name or "").strip()
            if not base_name:
                try:
                    base_name = (
                        self.parent.target_panel.part_name_input.text().strip()
                    )
                except Exception:
                    base_name = "NewTargetPart"
            existing = set(self.parent.project_model.target_parts.keys())
            name = self._unique_name(base_name, existing)
            try:
                cs_model = (
                    self.parent.target_panel.get_coordinate_system_model()
                )
                refs_model = (
                    self.parent.target_panel.get_reference_values_model()
                )
                from src.models.project_model import Part as PMPart
                from src.models.project_model import PartVariant as PMVariant

                variant = PMVariant(
                    part_name=name, coord_system=cs_model, refs=refs_model
                )
            except Exception:
                logger.debug("读取 Target 面板强类型数据失败", exc_info=True)
                raise
            self.parent.project_model.target_parts[name] = PMPart(
                part_name=name, variants=[variant]
            )
            if hasattr(self.parent, "target_panel"):
                self.parent.target_panel._current_part_name = name
            try:
                self.parent.signal_bus.partAdded.emit("Target", name)
            except Exception:
                logger.debug("发射 partAdded 信号失败", exc_info=True)
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(
                    self.parent, "成功", f'Target Part "{name}" 已添加'
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"添加 Target Part 失败: {e}")
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(self.parent, "错误", f"添加失败: {e}")
            except Exception:
                pass

    def remove_target_part(self):
        logger = __import__("logging").getLogger(__name__)
        try:
            if not self._ensure_project_model():
                return
            try:
                name = self.parent.target_panel.part_selector.currentText()
            except Exception:
                name = None
        except Exception:
            name = None
        if not name:
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self.parent, "提示", "当前没有可删除的 Target Part"
                )
            except Exception:
                pass
            return
        try:
            self.parent.project_model.target_parts.pop(name, None)
            self.parent._current_target_part_name = None
            self.parent._current_target_variant = None
            try:
                self.parent.tgt_table.clearContents()
            except Exception:
                pass
            try:
                self.parent.signal_bus.partRemoved.emit("Target", name)
            except Exception:
                logger.debug("发射 partRemoved 信号失败", exc_info=True)
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(
                    self.parent, "成功", f'Target Part "{name}" 已删除'
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"删除 Target Part 失败: {e}")
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(self.parent, "错误", f"删除失败: {e}")
            except Exception:
                pass

    def on_source_variant_changed(self, idx: int):
        logger = __import__("logging").getLogger(__name__)
        try:
            sel = (
                getattr(self.parent.source_panel, "_current_part_name", None)
                or getattr(
                    self.parent.source_panel.part_selector,
                    "currentText",
                    lambda: "",
                )()
            )
            variants = self._get_variants(sel, is_source=True)
            if not variants:
                return
            if idx < 0 or idx >= len(variants):
                idx = 0
            frame = variants[idx]
            part_name, cs, mc, cref_val, bref_val, sref_val, q_val = (
                self._read_variant_fields(frame)
            )
            if cs is None:
                return
            try:
                self.parent.source_panel.part_name_input.blockSignals(True)
                self.parent.source_panel.part_name_input.setText(part_name)
            finally:
                try:
                    self.parent.source_panel.part_name_input.blockSignals(
                        False
                    )
                except Exception:
                    pass
            try:
                coord_dict = {
                    "Orig": [cs.origin[0], cs.origin[1], cs.origin[2]],
                    "X": [cs.x_axis[0], cs.x_axis[1], cs.x_axis[2]],
                    "Y": [cs.y_axis[0], cs.y_axis[1], cs.y_axis[2]],
                    "Z": [cs.z_axis[0], cs.z_axis[1], cs.z_axis[2]],
                    "MomentCenter": mc,
                }
                self.parent.source_panel.set_coord_data(coord_dict)
            except Exception:
                logger.debug("同步 Source 变体坐标失败", exc_info=True)
        except Exception as e:
            logger.error(f"Source 变体切换失败: {e}", exc_info=True)

    def on_target_variant_changed(self, idx: int):
        logger = __import__("logging").getLogger(__name__)
        try:
            sel = (
                getattr(self.parent.target_panel, "_current_part_name", None)
                or getattr(
                    self.parent.target_panel.part_selector,
                    "currentText",
                    lambda: "",
                )()
            )
            variants = self._get_variants(sel, is_source=False)
            if not variants:
                return
            if idx < 0 or idx >= len(variants):
                idx = 0
            frame = variants[idx]
            part_name, cs, mc, cref_val, bref_val, sref_val, q_val = (
                self._read_variant_fields(frame)
            )
            if cs is None:
                return
            try:
                self.parent.target_panel.part_name_input.blockSignals(True)
                self.parent.target_panel.part_name_input.setText(part_name)
            finally:
                try:
                    self.parent.target_panel.part_name_input.blockSignals(
                        False
                    )
                except Exception:
                    pass
            try:
                coord_dict = {
                    "Orig": [cs.origin[0], cs.origin[1], cs.origin[2]],
                    "X": [cs.x_axis[0], cs.x_axis[1], cs.x_axis[2]],
                    "Y": [cs.y_axis[0], cs.y_axis[1], cs.y_axis[2]],
                    "Z": [cs.z_axis[0], cs.z_axis[1], cs.z_axis[2]],
                    "MomentCenter": mc,
                }
                self.parent.target_panel.set_coord_data(coord_dict)
            except Exception:
                logger.debug("同步 Target 变体坐标失败", exc_info=True)
        except Exception as e:
            logger.error(f"Target 变体切换失败: {e}", exc_info=True)

    def on_source_part_changed(self):
        logger = __import__("logging").getLogger(__name__)
        try:
            logger.debug("=== on_source_part_changed 被调用 ===")
            if not hasattr(self.parent, "source_panel"):
                logger.debug("source_panel 不存在")
                return
            part_name = self.parent.source_panel.part_selector.currentText()
            logger.debug(f"当前选择的 Source Part: {part_name}")
            if not part_name:
                logger.debug("part_name 为空")
                return
            old_name = getattr(
                self.parent.source_panel, "_current_part_name", None
            )
            logger.debug(f"旧的 Source Part: {old_name}")
            if old_name and old_name != part_name:
                logger.debug(f"保存旧 Part: {old_name}")
                self.save_current_source_part()
            variants = self._get_variants(part_name, is_source=True)
            logger.debug(f"找到 {len(variants) if variants else 0} 个变体")
            if variants:
                variant = variants[0]
                _, cs, mc, cref_val, bref_val, sref_val, q_val = (
                    self._read_variant_fields(variant)
                )
                logger.debug(
                    f"读取变体字段: cs={cs is not None}, mc={mc}, cref={cref_val}, bref={bref_val}, sref={sref_val}, q={q_val}"
                )
                payload = {
                    "PartName": part_name,
                    "CoordSystem": {
                        "Orig": list(cs.origin) if cs else [0.0, 0.0, 0.0],
                        "X": list(cs.x_axis) if cs else [1.0, 0.0, 0.0],
                        "Y": list(cs.y_axis) if cs else [0.0, 1.0, 0.0],
                        "Z": list(cs.z_axis) if cs else [0.0, 0.0, 1.0],
                        "MomentCenter": mc,
                    },
                    "Cref": cref_val,
                    "Bref": bref_val,
                    "Sref": sref_val,
                    "Q": q_val,
                }
                logger.debug(f"准备应用 payload: {payload}")
                self.parent.source_panel.apply_variant_payload(payload)
                logger.debug("payload 已应用")
            else:
                logger.warning(f"未找到 Part '{part_name}' 的变体")
            if hasattr(self.parent, "source_panel"):
                self.parent.source_panel._current_part_name = part_name
            logger.debug("=== on_source_part_changed 完成 ===")
        except Exception as e:
            logger.error(f"on_source_part_changed 失败: {e}", exc_info=True)

    def on_target_part_changed(self):
        logger = __import__("logging").getLogger(__name__)
        try:
            logger.debug("=== on_target_part_changed 被调用 ===")
            if not hasattr(self.parent, "target_panel"):
                logger.debug("target_panel 不存在")
                return
            part_name = self.parent.target_panel.part_selector.currentText()
            logger.debug(f"当前选择的 Target Part: {part_name}")
            if not part_name:
                logger.debug("part_name 为空")
                return
            old_name = getattr(
                self.parent.target_panel, "_current_part_name", None
            )
            logger.debug(f"旧的 Target Part: {old_name}")
            if old_name and old_name != part_name:
                logger.debug(f"保存旧 Part: {old_name}")
                self.save_current_target_part()
            variants = self._get_variants(part_name, is_source=False)
            logger.debug(f"找到 {len(variants) if variants else 0} 个变体")
            if variants:
                variant = variants[0]
                _, cs, mc, cref_val, bref_val, sref_val, q_val = (
                    self._read_variant_fields(variant)
                )
                logger.debug(
                    f"读取变体字段: cs={cs is not None}, mc={mc}, cref={cref_val}, bref={bref_val}, sref={sref_val}, q={q_val}"
                )
                payload = {
                    "PartName": part_name,
                    "CoordSystem": {
                        "Orig": list(cs.origin) if cs else [0.0, 0.0, 0.0],
                        "X": list(cs.x_axis) if cs else [1.0, 0.0, 0.0],
                        "Y": list(cs.y_axis) if cs else [0.0, 1.0, 0.0],
                        "Z": list(cs.z_axis) if cs else [0.0, 0.0, 1.0],
                        "MomentCenter": mc,
                    },
                    "Cref": cref_val,
                    "Bref": bref_val,
                    "Sref": sref_val,
                    "Q": q_val,
                }
                logger.debug(f"准备应用 payload: {payload}")
                self.parent.target_panel.apply_variant_payload(payload)
                logger.debug("payload 已应用")
            else:
                logger.warning(f"未找到 Part '{part_name}' 的变体")
            if hasattr(self.parent, "target_panel"):
                self.parent.target_panel._current_part_name = part_name
            logger.debug("=== on_target_part_changed 完成 ===")
        except Exception as e:
            logger.error(f"on_target_part_changed 失败: {e}", exc_info=True)


class UIStateManager:
    """管理 UI 状态相关逻辑（可扩展）。

    当前只封装了一些常用的状态方法，主窗口仍保持对外兼容方法。
    """

    def __init__(self, parent: QWidget):
        self.parent = parent

    def set_config_panel_visible(self, visible: bool) -> None:
        # 直接实现显示/隐藏配置编辑器的行为，避免递归委托到主窗口同名方法。
        @report_exceptions("切换配置面板可见性失败")
        def _impl(vis: bool):
            sidebar = getattr(self.parent, "config_sidebar", None)
            if sidebar is not None:
                if vis:
                    sidebar.show_panel()
                else:
                    sidebar.hide_panel()
                return

            # 旧版兼容代码（侧边栏已改为浮动层，不再使用 splitter）
            panel = getattr(self.parent, "config_panel", None)
            if panel is None:
                func = getattr(self.parent, "_set_config_panel_visible", None)
                if callable(func):
                    try:
                        func(vis)
                    except Exception:
                        pass
                return

            panel.setVisible(bool(vis))
            try:
                # 兼容旧版使用的 splitter 属性，避免未定义的全局变量引用
                parent_splitter = getattr(self.parent, "splitter", None)
                if parent_splitter is not None:
                    try:
                        if vis:
                            parent_splitter.setSizes([1, 3])
                        else:
                            parent_splitter.setSizes([0, 1])
                    except Exception:
                        # 忽略 splitter 操作失败，保留向后兼容行为
                        pass
            except Exception:
                pass

            try:
                if hasattr(self.parent, "_force_layout_refresh"):
                    self.parent._force_layout_refresh()
            except Exception:
                pass

        return _impl(visible)

    def set_controls_locked(self, locked: bool) -> None:
        # 支持嵌套锁定：使用计数器来避免竞态或重复释放导致的状态不一致
        @report_exceptions("设置控件锁定状态失败")
        def _impl(locked: bool):
            if bool(locked):
                # 增加锁计数，只有由0->1时才真正禁用控件
                try:
                    prev = getattr(self, "_lock_count", 0)
                    self._lock_count = prev + 1
                except Exception:
                    self._lock_count = 1
                if self._lock_count > 1:
                    # 已经被锁定，不需要重复应用
                    return
            else:
                # 解除锁：减少计数但不低于0；只有计数回退到0时才恢复控件
                try:
                    prev = getattr(self, "_lock_count", 0)
                    self._lock_count = max(0, prev - 1)
                except Exception:
                    self._lock_count = 0
                if self._lock_count > 0:
                    # 仍有内层锁请求，不恢复控件
                    return

            # 实际应用启用/禁用到控件（当需要时）
            widgets = [
                getattr(self.parent, "btn_load", None),
                getattr(self.parent, "btn_save", None),
                getattr(self.parent, "btn_apply", None),
                getattr(self.parent, "btn_batch", None),
            ]
            for w in widgets:
                try:
                    if w is not None:
                        w.setEnabled(not bool(self._lock_count))
                except Exception:
                    pass

            # 取消按钮：始终保持可见以避免布局跳动，仅通过 setEnabled 控制可交互性。
            try:
                if hasattr(self.parent, "btn_cancel"):
                    try:
                        self.parent.btn_cancel.setVisible(True)
                    except Exception:
                        # 若控件不支持可见性设置，忽略
                        pass
                    try:
                        # 在有锁时允许点击取消以便中断操作；否则禁用但保留占位
                        self.parent.btn_cancel.setEnabled(bool(self._lock_count))
                    except Exception:
                        pass
            except Exception:
                pass

        res = _impl(locked)
        if res is None:
            # 若上层发生异常，尝试回退到父窗口实现以保持尽量的兼容性
            try:
                func = getattr(self.parent, "_set_controls_locked", None)
                if callable(func):
                    func(locked)
            except Exception:
                pass
        return res

    def refresh_controls_state(self) -> None:
        """集中刷新所有控件的启用/禁用状态。

        该方法读取主窗口的状态标志（`data_loaded`, `config_loaded`,
        `operation_performed`），并统一更新相关按钮与选项卡的状态。
        将以前散落在主窗口的方法集中到此处以便维护。
        """
        try:
            parent = self.parent
            # Start 按钮：仅在已加载数据且已加载配置时启用
            start_enabled = bool(
                self.is_data_loaded() and self.is_config_loaded()
            )

            # 检查配置是否被修改，用于展示 tooltip 和文件列表上的未保存指示
            config_modified = False
            try:
                cfg_mgr = getattr(parent, "config_manager", None)
                if cfg_mgr is not None and hasattr(
                    cfg_mgr, "is_config_modified"
                ):
                    try:
                        config_modified = bool(cfg_mgr.is_config_modified())
                    except Exception:
                        import logging

                        logging.getLogger(__name__).debug(
                            "检测配置是否修改失败（非致命）", exc_info=True
                        )
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "访问 config_manager 失败（非致命）", exc_info=True
                )

            base_tooltip = "开始批量处理（Ctrl+R）"
            for name in (
                "btn_start_menu",
                "btn_batch",
                "btn_batch_in_toolbar",
            ):
                try:
                    btn = getattr(parent, name, None)
                    if btn is not None:
                        btn.setEnabled(bool(start_enabled))
                        try:
                            tt = base_tooltip
                            if config_modified:
                                tt = f"{tt}（检测到未保存配置 — 开始将提示保存）"
                            btn.setToolTip(tt)
                        except Exception:
                            # 忽略 tooltip 设置失败
                            pass
                except Exception:
                    # 非致命，记录到日志而不是抛出
                    import logging

                    logging.getLogger(__name__).debug(
                        "设置启动按钮状态或 tooltip 失败（非致命）",
                        exc_info=True,
                    )

            # 更新状态栏右侧的永久提示标签：当可以开始时提示用户开始批处理
            try:
                from PySide6.QtWidgets import QLabel

                lbl = parent.statusBar().findChild(QLabel, "statusMessage")
                if lbl is not None:
                    try:
                        if bool(start_enabled):
                            lbl.setText("准备开始处理：点击开始处理")
                        else:
                            # 若尚未加载数据，回到步骤1提示；否则保持原有文本不覆盖（避免误改）
                            if not bool(self.is_data_loaded()):
                                lbl.setText("步骤1：选择文件或目录")
                    except Exception:
                        pass
            except Exception:
                # 忽略对状态栏永久标签更新失败
                pass

            # 将未保存配置的可视指示同步到 BatchPanel（文件列表上方）
            try:
                if (
                    hasattr(parent, "batch_panel")
                    and parent.batch_panel is not None
                ):
                    try:
                        parent.batch_panel.set_unsaved_indicator(
                            config_modified
                        )
                    except Exception:
                        import logging

                        logging.getLogger(__name__).debug(
                            "设置 batch_panel 未保存指示器失败（非致命）",
                            exc_info=True,
                        )
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "访问 parent.batch_panel 失败（非致命）", exc_info=True
                )

            # 数据管理选项卡：在没有加载数据时禁用
            try:
                if hasattr(parent, "tab_main") and hasattr(
                    parent, "file_list_widget"
                ):
                    tab = parent.tab_main
                    idx = -1
                    try:
                        idx = tab.indexOf(
                            getattr(parent, "file_list_widget", None)
                        )
                    except Exception:
                        idx = -1
                    if idx is not None and idx >= 0:
                        tab.setTabEnabled(idx, bool(self.is_data_loaded()))
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "设置数据管理选项卡状态失败（非致命）", exc_info=True
                )

            # 参考系管理（配置）选项卡
            try:
                if hasattr(parent, "tab_main"):
                    tab = parent.tab_main
                    config_panel = getattr(parent, "config_panel", None)
                    if config_panel is not None:
                        try:
                            cidx = tab.indexOf(config_panel)
                        except Exception:
                            cidx = -1
                        if cidx is not None and cidx >= 0:
                            tab.setTabEnabled(
                                cidx,
                                bool(
                                    self.is_data_loaded()
                                    or self.is_config_loaded()
                                ),
                            )
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "设置参考系管理选项卡状态失败（非致命）", exc_info=True
                )

            # 保存按钮：在没有任何操作前禁用
            save_enabled = bool(self.is_operation_performed())
            # 如果主窗口标记为临时禁用 project 按钮，则保持禁用状态
            project_buttons_disabled = bool(
                getattr(parent, "_project_buttons_temporarily_disabled", False)
            )
            for name in ("btn_save_project_toolbar",):
                try:
                    btn = getattr(parent, name, None)
                    if btn is not None:
                        if project_buttons_disabled:
                            btn.setEnabled(False)
                        else:
                            btn.setEnabled(bool(save_enabled))
                except Exception:
                    import logging

                    logging.getLogger(__name__).debug(
                        "设置保存按钮状态失败（非致命）", exc_info=True
                    )

            try:
                if hasattr(parent, "batch_panel"):
                    try:
                        # 同上：若临时禁用，则保持禁用
                        if project_buttons_disabled:
                            parent.batch_panel.btn_save_project.setEnabled(
                                False
                            )
                        else:
                            parent.batch_panel.btn_save_project.setEnabled(
                                bool(save_enabled)
                            )
                    except Exception:
                        import logging

                        logging.getLogger(__name__).debug(
                            "设置 batch_panel 保存按钮状态失败（非致命）",
                            exc_info=True,
                        )
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "访问 batch_panel 失败（非致命）", exc_info=True
                )

            try:
                if hasattr(parent, "config_panel"):
                    try:
                        parent.config_panel.btn_save.setEnabled(
                            bool(save_enabled)
                        )
                    except Exception:
                        import logging

                        logging.getLogger(__name__).debug(
                            "设置 config_panel 保存按钮失败（非致命）",
                            exc_info=True,
                        )
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "访问 config_panel 失败（非致命）", exc_info=True
                )

        except Exception:
            # 最后兜底：记录错误但不抛出，避免在 UI 更新时中断
            import logging

            logging.getLogger(__name__).debug(
                "refresh_controls_state 失败（非致命）", exc_info=True
            )

    # 状态设置辅助方法，鼓励通过 UIStateManager 管理窗口级状态
    def set_data_loaded(self, loaded: bool) -> None:
        """设置数据已加载标志并刷新控件状态。
        
        注意：不写回 parent.data_loaded，避免属性 setter 递归调用。
        parent 的属性 getter 会读取 _data_loaded，setter 只更新 UIStateManager 内部状态。
        """
        try:
            self._data_loaded = bool(loaded)
            self.refresh_controls_state()
        except Exception:
            pass

    def set_config_loaded(self, loaded: bool) -> None:
        """设置配置已加载标志并刷新控件状态。
        
        注意：不写回 parent.config_loaded，避免属性 setter 递归调用。
        """
        try:
            self._config_loaded = bool(loaded)
            self.refresh_controls_state()
        except Exception:
            pass

    def set_operation_performed(self, performed: bool) -> None:
        """设置用户已执行操作标志（用于启用保存按钮）。
        
        注意：不写回 parent.operation_performed，避免属性 setter 递归调用。
        """
        try:
            self._operation_performed = bool(performed)
            self.refresh_controls_state()
        except Exception:
            pass

    def mark_user_modified(self) -> None:
        """快捷方法：标记为用户已修改并刷新状态。"""
        try:
            self.set_operation_performed(True)
        except Exception:
            pass

    def clear_user_modified(self) -> None:
        """快捷方法：清除用户修改标志并刷新状态。"""
        try:
            self.set_operation_performed(False)
        except Exception:
            pass

    # 状态查询方法，封装对 parent 属性的读取
    def is_data_loaded(self) -> bool:
        try:
            return bool(getattr(self, "_data_loaded", False))
        except Exception:
            return False

    def is_config_loaded(self) -> bool:
        try:
            return bool(getattr(self, "_config_loaded", False))
        except Exception:
            return False

    def is_operation_performed(self) -> bool:
        try:
            return bool(getattr(self, "_operation_performed", False))
        except Exception:
            return False

    # ---- UI 恢复辅助 API ----
    def set_tab_index(self, index: int) -> None:
        """设置主选项卡索引（若主窗口存在 tab_main）。"""
        try:
            tab = getattr(self.parent, "tab_main", None)
            if tab is not None and hasattr(tab, "setCurrentIndex"):
                try:
                    tab.setCurrentIndex(int(index))
                except Exception:
                    pass
        except Exception:
            pass

    def restore_window_geometry(self, geom: dict) -> None:
        """恢复窗口几何：期望 geom 为 {"x":int,"y":int,"w":int,"h":int}。"""
        try:
            if not geom:
                return
            win = self.parent
            try:
                x = int(geom.get("x", 0))
                y = int(geom.get("y", 0))
                w = int(geom.get("w", win.width() if hasattr(win, "width") else 800))
                h = int(geom.get("h", win.height() if hasattr(win, "height") else 600))
                try:
                    win.setGeometry(x, y, w, h)
                except Exception:
                    # 回退到 resize/move
                    try:
                        win.resize(w, h)
                        win.move(x, y)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    def set_selected_files(self, file_list: list) -> None:
        """设置当前选中文件列表到 FileSelectionManager（尽量安全）。"""
        try:
            if not file_list:
                return
            fsm = getattr(self.parent, "file_selection_manager", None)
            if fsm is None:
                return
            try:
                # 规范化为绝对字符串键
                by_file = {}
                for p in file_list:
                    try:
                        key = str(Path(p).resolve()) if p is not None else str(p)
                    except Exception:
                        key = str(p)
                    by_file[key] = by_file.get(key, set())
                # 将选择写入 parent 的表格选择结构（兼容旧代码）
                try:
                    fsm.table_row_selection_by_file = getattr(fsm, "table_row_selection_by_file", {}) or {}
                    # 保留现有结构，不覆盖其他 keys
                    for k in by_file.keys():
                        fsm.table_row_selection_by_file.setdefault(k, None)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass
