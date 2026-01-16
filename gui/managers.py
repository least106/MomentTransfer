"""GUI 管理器集合：将 `IntegratedAeroGUI` 的部分职责拆分为独立管理器。

设计原则：最小侵入、向后兼容。当前实现提供轻量包装，未来可逐步迁移逻辑。
"""
from typing import Dict, Optional
from pathlib import Path

from PySide6.QtWidgets import QWidget


class FileSelectionManager:
    """管理与文件选择相关的状态与映射。

    属性保留旧名称以保证向后兼容（主窗口可直接读取这些属性）。
    """

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name in {
            "special_part_mapping_by_file",
            "special_part_row_selection_by_file",
            "file_part_selection_by_file",
            "table_row_selection_by_file",
        }:
            try:
                parent = super().__getattribute__("parent")
            except Exception:
                parent = None
            if parent is not None and name != "parent":
                try:
                    setattr(parent, name, value)
                except Exception:
                    pass

    def __init__(self, parent: QWidget):
        self.parent = parent
        # 特殊格式映射：{str(file): {source_part: target_part}}
        self.special_part_mapping_by_file: Dict[str, Dict[str, str]] = {}
        # 特殊格式选中行：{str(file): {source_part: set(row_idx)}}
        self.special_part_row_selection_by_file: Dict[str, Dict[str, set]] = {}
        # 常规文件的 part 选择：{str(file): {"source": str, "target": str}}
        self.file_part_selection_by_file: Dict[str, Dict[str, str]] = {}
        # 常规文件的行选择：{str(file): set(row_idx)} or None
        self.table_row_selection_by_file: Dict[str, Optional[set]] = {}

        # 向后兼容：将状态引用同步到主窗口属性
        try:
            self.parent.special_part_mapping_by_file = self.special_part_mapping_by_file
            self.parent.special_part_row_selection_by_file = self.special_part_row_selection_by_file
            self.parent.file_part_selection_by_file = self.file_part_selection_by_file
            self.parent.table_row_selection_by_file = self.table_row_selection_by_file
        except Exception:
            pass

    def ensure_special_row_selection_storage(self, file_path: Path, part_names: list) -> dict:
        """确保行选择缓存存在，并为未初始化的 part 默认全选。

        返回 by_part dict（可被调用方修改）。
        """
        try:
            by_file = self.special_part_row_selection_by_file or {}
            by_file.setdefault(str(file_path), {})
            by_part = by_file[str(file_path)]
            for pn in part_names:
                by_part.setdefault(str(pn), None)
            self.special_part_row_selection_by_file = by_file
            try:
                self.parent.special_part_row_selection_by_file = by_file
            except Exception:
                pass
            return by_part
        except Exception:
            return {}

    def open_quick_select_dialog(self) -> None:
        """打开快速选择对话框（委托给 GUI 的 QuickSelectDialog）。"""
        try:
            from gui.quick_select_dialog import QuickSelectDialog

            dlg = QuickSelectDialog(self, parent=self.parent)
            dlg.exec()
        except Exception:
            # 日志由调用方处理
            pass


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
                cs_model = self.parent.source_panel.get_coordinate_system_model()
                refs_model = self.parent.source_panel.get_reference_values_model()
                from src.models.project_model import Part as PMPart, PartVariant as PMVariant

                pm_variant = PMVariant(part_name=part_name, coord_system=cs_model, refs=refs_model)
                self.parent.project_model.source_parts[part_name] = PMPart(part_name=part_name, variants=[pm_variant])
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
                cs_model = self.parent.target_panel.get_coordinate_system_model()
                refs_model = self.parent.target_panel.get_reference_values_model()
                from src.models.project_model import Part as PMPart, PartVariant as PMVariant

                pm_variant = PMVariant(part_name=part_name, coord_system=cs_model, refs=refs_model)
                self.parent.project_model.target_parts[part_name] = PMPart(part_name=part_name, variants=[pm_variant])
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
                panel = self.parent.source_panel if is_source else self.parent.target_panel
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
                if hasattr(self.parent, 'source_panel'):
                    self.parent.source_panel._current_part_name = new_name
            else:
                if hasattr(self.parent, 'target_panel'):
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
                    base_name = self.parent.source_panel.part_name_input.text().strip()
                except Exception:
                    base_name = "NewSourcePart"
            existing = set(self.parent.project_model.source_parts.keys())
            name = self._unique_name(base_name, existing)

            try:
                cs_model = self.parent.source_panel.get_coordinate_system_model()
                refs_model = self.parent.source_panel.get_reference_values_model()
            except Exception:
                logger.debug("读取 Source 面板强类型数据失败", exc_info=True)
                cs_model = None
                refs_model = None
            if cs_model is None or refs_model is None:
                raise ValueError("无法从 Source 面板读取强类型数据")
            from src.models.project_model import Part as PMPart, PartVariant as PMVariant

            variant = PMVariant(part_name=name, coord_system=cs_model, refs=refs_model)
            self.parent.project_model.source_parts[name] = PMPart(part_name=name, variants=[variant])
            if hasattr(self.parent, 'source_panel'):
                self.parent.source_panel._current_part_name = name

            try:
                self.parent.signal_bus.partAdded.emit("Source", name)
            except Exception:
                logger.debug("发射 partAdded 信号失败", exc_info=True)
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(self.parent, "成功", f'Source Part "{name}" 已添加')
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

                QMessageBox.warning(self.parent, "提示", "没有可删除的 Source Part")
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

                QMessageBox.information(self.parent, "成功", f'Source Part "{name}" 已删除')
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
                    base_name = self.parent.target_panel.part_name_input.text().strip()
                except Exception:
                    base_name = "NewTargetPart"
            existing = set(self.parent.project_model.target_parts.keys())
            name = self._unique_name(base_name, existing)
            try:
                cs_model = self.parent.target_panel.get_coordinate_system_model()
                refs_model = self.parent.target_panel.get_reference_values_model()
                from src.models.project_model import Part as PMPart, PartVariant as PMVariant

                variant = PMVariant(part_name=name, coord_system=cs_model, refs=refs_model)
            except Exception:
                logger.debug("读取 Target 面板强类型数据失败", exc_info=True)
                raise
            self.parent.project_model.target_parts[name] = PMPart(part_name=name, variants=[variant])
            if hasattr(self.parent, 'target_panel'):
                self.parent.target_panel._current_part_name = name
            try:
                self.parent.signal_bus.partAdded.emit("Target", name)
            except Exception:
                logger.debug("发射 partAdded 信号失败", exc_info=True)
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(self.parent, "成功", f'Target Part "{name}" 已添加')
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

                QMessageBox.warning(self.parent, "提示", "当前没有可删除的 Target Part")
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

                QMessageBox.information(self.parent, "成功", f'Target Part "{name}" 已删除')
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
            part_name, cs, mc, cref_val, bref_val, sref_val, q_val = self._read_variant_fields(frame)
            if cs is None:
                return
            try:
                self.parent.source_panel.part_name_input.blockSignals(True)
                self.parent.source_panel.part_name_input.setText(part_name)
            finally:
                try:
                    self.parent.source_panel.part_name_input.blockSignals(False)
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
            part_name, cs, mc, cref_val, bref_val, sref_val, q_val = self._read_variant_fields(frame)
            if cs is None:
                return
            try:
                self.parent.target_panel.part_name_input.blockSignals(True)
                self.parent.target_panel.part_name_input.setText(part_name)
            finally:
                try:
                    self.parent.target_panel.part_name_input.blockSignals(False)
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
            old_name = getattr(self.parent.source_panel, "_current_part_name", None)
            logger.debug(f"旧的 Source Part: {old_name}")
            if old_name and old_name != part_name:
                logger.debug(f"保存旧 Part: {old_name}")
                self.save_current_source_part()
            variants = self._get_variants(part_name, is_source=True)
            logger.debug(f"找到 {len(variants) if variants else 0} 个变体")
            if variants:
                variant = variants[0]
                _, cs, mc, cref_val, bref_val, sref_val, q_val = self._read_variant_fields(variant)
                logger.debug(f"读取变体字段: cs={cs is not None}, mc={mc}, cref={cref_val}, bref={bref_val}, sref={sref_val}, q={q_val}")
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
            if hasattr(self.parent, 'source_panel'):
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
            old_name = getattr(self.parent.target_panel, "_current_part_name", None)
            logger.debug(f"旧的 Target Part: {old_name}")
            if old_name and old_name != part_name:
                logger.debug(f"保存旧 Part: {old_name}")
                self.save_current_target_part()
            variants = self._get_variants(part_name, is_source=False)
            logger.debug(f"找到 {len(variants) if variants else 0} 个变体")
            if variants:
                variant = variants[0]
                _, cs, mc, cref_val, bref_val, sref_val, q_val = self._read_variant_fields(variant)
                logger.debug(f"读取变体字段: cs={cs is not None}, mc={mc}, cref={cref_val}, bref={bref_val}, sref={sref_val}, q={q_val}")
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
            if hasattr(self.parent, 'target_panel'):
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
        try:
            panel = getattr(self.parent, "config_panel", None)
            splitter = getattr(self.parent, "main_splitter", None)
            if panel is None or splitter is None:
                # 无法访问面板或 splitter，则尝试调用主窗口的底层实现（若存在）
                func = getattr(self.parent, "_set_config_panel_visible", None)
                if callable(func):
                    try:
                        func(visible)
                    except Exception:
                        pass
                return

            panel.setVisible(bool(visible))
            try:
                # 调整 splitter 大小：显示时分配更多给配置面板，隐藏时将其收缩
                if visible:
                    # 给配置面板一个合理的初始高度比例（1:3）
                    splitter.setSizes([1, 3])
                else:
                    splitter.setSizes([0, 1])
            except Exception:
                # 忽略 splitter 调整失败
                pass

            # 尝试强制刷新主窗口布局以确保可见性更新
            try:
                if hasattr(self.parent, "_force_layout_refresh"):
                    self.parent._force_layout_refresh()
            except Exception:
                pass
        except Exception:
            # 静默失败以免在初始化阶段中断流程
            return

    def set_controls_locked(self, locked: bool) -> None:
        # 直接实现控件锁定/解锁行为，避免再次委托到父对象导致递归。
        try:
            widgets = [
                getattr(self.parent, "btn_load", None),
                getattr(self.parent, "btn_save", None),
                getattr(self.parent, "btn_apply", None),
                getattr(self.parent, "btn_config_format", None),
                getattr(self.parent, "btn_batch", None),
            ]
            for w in widgets:
                try:
                    if w is not None:
                        w.setEnabled(not bool(locked))
                except Exception:
                    pass

            # 取消按钮在锁定时应保持可见/可用
            try:
                if hasattr(self.parent, "btn_cancel"):
                    if locked:
                        self.parent.btn_cancel.setVisible(True)
                        self.parent.btn_cancel.setEnabled(True)
                    else:
                        self.parent.btn_cancel.setVisible(False)
                        self.parent.btn_cancel.setEnabled(False)
            except Exception:
                pass
        except Exception:
            # 回退到父对象的实现（如果存在且非递归）
            try:
                func = getattr(self.parent, "_set_controls_locked", None)
                if callable(func):
                    func(locked)
            except Exception:
                pass
