"""
Part 管理模块 - 处理 Part 的添加、删除和切换
"""

# 为了处理循环导入，允许在函数内或局部进行受控导入
# pylint: disable=import-outside-toplevel

import logging
from typing import Optional

# 引入 QMessageBox 以便测试对其进行 monkeypatch，且供模块内部使用
from PySide6.QtWidgets import QMessageBox

from gui.signal_bus import SignalBus

# 尝试提前导入 ModelManager，避免函数内多次局部导入带来的 pylint 噪音；
# 若因循环导入失败则保留为 None，函数内按需回退本地导入。
try:
    from gui.managers import ModelManager
except Exception:
    ModelManager = None

logger = logging.getLogger(__name__)


class PartManager:
    """Part 管理器 - 管理 Source 和 Target Part"""

    def __init__(self, gui_instance):
        """初始化 Part 管理器"""
        self.gui = gui_instance
        self.model_manager = getattr(gui_instance, "model_manager", None)
        try:
            self.signal_bus = getattr(gui_instance, "signal_bus", SignalBus.instance())
        except Exception:
            self.signal_bus = SignalBus.instance()
        # 连接总线请求信号
        try:
            self.signal_bus.partAddRequested.connect(self._on_part_add_requested)
            self.signal_bus.partRemoveRequested.connect(self._on_part_remove_requested)
        except Exception:
            logger.debug("连接 Part 请求信号失败", exc_info=True)

    def _get_model_manager(self):
        """返回可用的 ModelManager 实例：
        - 优先使用 `self.model_manager` 或 `self.gui.model_manager`。
        - 若不存在，尝试按需导入并创建一个实例以保证向后兼容。
        - 若无法获得，记录警告并返回 None（调用方应对 None 做显式回退处理）。
        """
        try:
            mm = self.model_manager or getattr(self.gui, "model_manager", None)
            if mm:
                return mm
            # 按需导入并尝试创建实例以保持兼容
            from gui.managers import ModelManager

            mm = ModelManager(self.gui)
            # 缓存以便后续使用
            self.model_manager = mm
            return mm
        except Exception:
            logger.warning("无法获取 ModelManager 实例，某些操作将回退或失败", exc_info=True)
            return None

    def _inform_model_manager_missing(self, operation: str = "操作"):
        """在 ModelManager 缺失时记录并向用户提示，避免沉默失败。"""
        msg = f"{operation} 需要 ModelManager，但未找到可用的 model_manager 实例。某些功能将不可用。"
        logger.warning(msg)
        try:
            QMessageBox.warning(self.gui, "缺失依赖: ModelManager", msg)
        except Exception:
            # 在非 GUI 环境或测试中，弹窗可能失败；已经记录日志即可。
            logger.debug("无法弹出 QMessageBox 提示 (可能在测试/无界面环境)", exc_info=True)

    # ===== 辅助方法 =====
    def _ensure_project_model(self) -> bool:
        """确保 gui 持有 ProjectConfigModel，必要时创建空模型。"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "_ensure_project_model"):
                return bool(mm._ensure_project_model())
            self._inform_model_manager_missing("保证项目模型")
        except Exception:
            logger.debug("委托 _ensure_project_model 失败", exc_info=True)
        return False

    def _unique_name(self, base: str, existing: set) -> str:
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "_unique_name"):
                return mm._unique_name(base, existing)
        except (AttributeError, TypeError):
            logger.debug("delegated _unique_name failed", exc_info=True)
        name = base or "Part"
        if name not in existing:
            return name
        idx = 1
        while f"{name}_{idx}" in existing:
            idx += 1
        return f"{name}_{idx}"

    def _get_variants(self, part_name: str, is_source: bool):
        """优先从 ProjectConfigModel 读取变体，缺失时回退到 legacy ProjectData。"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "_get_variants"):
                return mm._get_variants(part_name, is_source)
        except Exception:
            logger.debug("delegated _get_variants failed", exc_info=True)
        variants = []
        mm = self._get_model_manager()
        if mm and hasattr(mm, "project_model"):
            if self._ensure_project_model():
                parts = (
                    mm.project_model.source_parts
                    if is_source
                    else mm.project_model.target_parts
                )
                part = parts.get(part_name)
                if part:
                    variants = part.variants

        if not variants and mm:
            cfg = getattr(mm, "current_config", None)
            if cfg:
                parts = cfg.source_parts if is_source else cfg.target_parts
                part = parts.get(part_name)
                if part:
                    if isinstance(part, list):
                        variants = part
                    elif hasattr(part, "variants"):
                        variants = part.variants

        return variants

    def _read_variant_fields(self, variant):
        """从变体读取字段，返回统一元组。

        兼容两类对象：
        - 强类型模型：src.models.project_model.PartVariant
        - legacy：src.data_loader.FrameConfiguration
        """
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "_read_variant_fields"):
                return mm._read_variant_fields(variant)
        except Exception:
            logger.debug("delegated _read_variant_fields failed", exc_info=True)
        if variant is None:
            return None, None, None, 0.0, 0.0, 0.0, 0.0

        cs = getattr(variant, "coord_system", None)
        part_name = getattr(variant, "part_name", "") or ""

        mc = None
        if cs is not None and getattr(cs, "moment_center", None) is not None:
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

        cref_val = self._safe_float(cref_val)
        bref_val = self._safe_float(bref_val)
        sref_val = self._safe_float(sref_val)
        q_val = self._safe_float(q_val)

        return part_name, cs, mc, cref_val, bref_val, sref_val, q_val

    def _safe_float(self, value: Optional[object]) -> float:
        """将任意值安全转换为 float，失败时返回 0.0。"""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _rename_part(self, new_name: str, is_source: bool):
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "_rename_part"):
                return mm._rename_part(new_name, is_source)
        except Exception:
            logger.debug("delegated _rename_part failed", exc_info=True)
        # 回退到本地实现（与旧行为一致）
        try:
            mm = self.model_manager or getattr(self.gui, "model_manager", None)
            if mm is None or not self._ensure_project_model():
                return
            new_name = (new_name or "").strip()
            if not new_name:
                return

            parts = (
                mm.project_model.source_parts
                if is_source
                else mm.project_model.target_parts
            )
            selector = None
            try:
                selector = (
                    self.gui.source_panel.part_selector
                    if is_source
                    else self.gui.target_panel.part_selector
                )
            except Exception:
                selector = None

            try:
                panel = self.gui.source_panel if is_source else self.gui.target_panel
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
                if hasattr(self.gui, "source_panel"):
                    self.gui.source_panel._current_part_name = new_name
            else:
                if hasattr(self.gui, "target_panel"):
                    self.gui.target_panel._current_part_name = new_name

            if selector:
                try:
                    # 在更新选择器项时阻断其信号，避免触发递归或重复保存/验证回调
                    block_fn = getattr(selector, "blockSignals", None)
                    should_unblock = False
                    if callable(block_fn):
                        try:
                            block_fn(True)
                            should_unblock = True
                        except Exception:
                            should_unblock = False

                    try:
                        idx = selector.findText(current_name)
                        if idx >= 0:
                            selector.setItemText(idx, new_name)
                        # 优先使用 setCurrentText 保持行为一致；若不可用，尝试通过索引设置
                        try:
                            selector.setCurrentText(new_name)
                        except Exception:
                            new_idx = selector.findText(new_name)
                            if new_idx >= 0 and hasattr(selector, "setCurrentIndex"):
                                try:
                                    selector.setCurrentIndex(new_idx)
                                except Exception:
                                    # 忽略单次失败，已记录在外层
                                    pass
                    finally:
                        if should_unblock and callable(block_fn):
                            try:
                                block_fn(False)
                            except Exception:
                                logger.debug("恢复 selector 信号失败", exc_info=True)
                except Exception:
                    logger.debug("更新选择器名称失败", exc_info=True)
        except Exception:
            logger.debug("重命名 Part 失败", exc_info=True)

    # ===== Source 管理 =====
    def add_source_part(self, suggested_name: str = None):
        """添加新的 Source Part（使用 ProjectConfigModel）"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "add_source_part"):
                return mm.add_source_part(suggested_name)
            self._inform_model_manager_missing("添加 Source Part")
            return None
        except Exception:
            logger.exception("委托给 model_manager.add_source_part 失败")

    def remove_source_part(self, name_hint: str = None):
        """删除当前 Source Part（使用 ProjectConfigModel）"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "remove_source_part"):
                return mm.remove_source_part(name_hint)
            self._inform_model_manager_missing("删除 Source Part")
            return None
        except Exception:
            logger.exception("委托给 model_manager.remove_source_part 失败")

    # ===== Target 管理 =====
    def add_target_part(self, suggested_name: str = None):
        """添加新 Target Part（使用 ProjectConfigModel）。

        不再弹出输入对话框；优先使用传入的 `suggested_name` 或面板上的文本字段。
        行为与 `add_source_part` 保持一致。
        """
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "add_target_part"):
                return mm.add_target_part(suggested_name)
            self._inform_model_manager_missing("添加 Target Part")
            return None
        except Exception:
            logger.exception("委托给 model_manager.add_target_part 失败")

    def remove_target_part(self):
        """删除当前 Target Part（使用 ProjectConfigModel）"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "remove_target_part"):
                return mm.remove_target_part()
            self._inform_model_manager_missing("删除 Target Part")
            return None
        except Exception:
            logger.exception("委托给 model_manager.remove_target_part 失败")

    # ===== 切换事件 =====
    def on_source_variant_changed(self, idx: int):
        """Source 变体索引变化事件：根据索引更新 UI。"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "on_source_variant_changed"):
                return mm.on_source_variant_changed(idx)
            self._inform_model_manager_missing("Source 变体切换")
            return None
        except Exception:
            logger.exception("委托给 model_manager.on_source_variant_changed 失败")

    def on_target_variant_changed(self, idx: int):
        """Target 变体索引变化事件：根据索引更新 UI。"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "on_target_variant_changed"):
                return mm.on_target_variant_changed(idx)
            self._inform_model_manager_missing("Target 变体切换")
            return None
        except Exception:
            logger.exception("委托给 model_manager.on_target_variant_changed 失败")

    # ===== 名称变更事件 =====
    def on_source_part_name_changed(self, new_text: str):
        """Source PartName 文本框变化"""
        try:
            self._rename_part(new_text, is_source=True)

        except Exception as e:
            logger.debug("Source PartName 变化处理失败: %s", e)

    def on_target_part_name_changed(self, new_text: str):
        """Target PartName 文本框变化"""
        try:
            self._rename_part(new_text, is_source=False)

        except Exception as e:
            logger.debug("Target PartName 变化处理失败: %s", e)

    # ===== 总线请求处理 =====
    def _on_part_add_requested(self, side: str, name: str):
        try:
            side_l = (side or "").lower()
            if side_l in ("source", "src"):
                self.add_source_part(suggested_name=name)
            elif side_l in ("target", "tgt"):
                # 传递建议名称以保持与 source 分支一致的 UX
                self.add_target_part(suggested_name=name)
        except Exception:
            logger.debug("处理 partAddRequested 失败", exc_info=True)

    def _on_part_remove_requested(self, side: str, name: str):
        try:
            side_l = (side or "").lower()
            if side_l in ("source", "src"):
                self.remove_source_part(name_hint=name)
            elif side_l in ("target", "tgt"):
                self.remove_target_part()
        except Exception:
            logger.debug("处理 partRemoveRequested 失败", exc_info=True)

    # ===== Part 保存方法（从 main_window 迁移）=====
    def save_current_source_part(self):
        """将当前 Source 表单保存到新模型（使用强类型接口）"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "save_current_source_part"):
                return mm.save_current_source_part()
            self._inform_model_manager_missing("保存当前 Source Part")
            return None
        except Exception:
            logger.exception("save_current_source_part delegation failed")

    def save_current_target_part(self):
        """将当前 Target 表单保存到新模型（使用强类型接口）"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "save_current_target_part"):
                return mm.save_current_target_part()
            self._inform_model_manager_missing("保存当前 Target Part")
            return None
        except Exception:
            logger.exception("save_current_target_part delegation failed")

    # ===== Part 变更事件处理（从 main_window 迁移）=====
    def on_source_part_changed(self):
        """Source Part 选择变化时的处理"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "on_source_part_changed"):
                return mm.on_source_part_changed()
            self._inform_model_manager_missing("Source Part 切换")
            return None
        except Exception:
            logger.exception("on_source_part_changed delegation failed")

    def on_target_part_changed(self):
        """Target Part 选择变化时的处理"""
        try:
            mm = self._get_model_manager()
            if mm and hasattr(mm, "on_target_part_changed"):
                return mm.on_target_part_changed()
            self._inform_model_manager_missing("Target Part 切换")
            return None
        except Exception:
            logger.exception("on_target_part_changed delegation failed")
