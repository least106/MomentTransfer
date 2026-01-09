"""
Part 管理模块 - 处理 Part 的添加、删除和切换
"""
import logging
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QInputDialog, QMessageBox
from src.models import ProjectConfigModel
from src.models.project_model import Part as PMPart
from src.models.project_model import PartVariant as PMVariant
from gui.signal_bus import SignalBus

logger = logging.getLogger(__name__)


class PartManager:
    """Part 管理器 - 管理 Source 和 Target Part"""

    def __init__(self, gui_instance):
        """初始化 Part 管理器"""
        self.gui = gui_instance
        try:
            self.signal_bus = getattr(gui_instance, 'signal_bus', SignalBus.instance())
        except Exception:
            self.signal_bus = SignalBus.instance()
        # 连接总线请求信号
        try:
            self.signal_bus.partAddRequested.connect(self._on_part_add_requested)
            self.signal_bus.partRemoveRequested.connect(self._on_part_remove_requested)
        except Exception:
            logger.debug("连接 Part 请求信号失败", exc_info=True)

    # ===== 辅助方法 =====
    def _ensure_project_model(self) -> bool:
        """确保 gui 持有 ProjectConfigModel，必要时创建空模型。"""
        if getattr(self.gui, "project_model", None) is None:
            try:
                self.gui.project_model = ProjectConfigModel()
            except Exception:
                logger.debug("创建 ProjectConfigModel 失败", exc_info=True)
                return False
        return True

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
        if self._ensure_project_model():
            parts = self.gui.project_model.source_parts if is_source else self.gui.project_model.target_parts
            part = parts.get(part_name)
            if part:
                variants = part.variants

        if not variants:
            cfg = getattr(self.gui, "current_config", None)
            if cfg:
                parts = cfg.source_parts if is_source else cfg.target_parts
                part = parts.get(part_name)
                if part:
                    # legacy ProjectData: value 是 List[FrameConfiguration]
                    if isinstance(part, list):
                        variants = part
                    # 兼容其他可能的结构（如对象有 variants 属性）
                    elif hasattr(part, 'variants'):
                        variants = part.variants

        return variants

    def _read_variant_fields(self, variant):
        """从变体读取字段，返回统一元组。

        兼容两类对象：
        - 强类型模型：src.models.project_model.PartVariant
        - legacy：src.data_loader.FrameConfiguration
        """
        try:
            if variant is None:
                return None, None, None, 0.0, 0.0, 0.0, 0.0

            cs = getattr(variant, 'coord_system', None)
            part_name = getattr(variant, 'part_name', '') or ''

            # 力矩中心：强类型在 cs.moment_center；legacy 在 variant.moment_center
            mc = None
            if cs is not None and getattr(cs, 'moment_center', None) is not None:
                mc = list(getattr(cs, 'moment_center'))
            if mc is None:
                mc = getattr(variant, 'moment_center', None)
                if mc is not None:
                    mc = list(mc)
            if not mc:
                mc = [0.0, 0.0, 0.0]

            # 参考量：强类型在 refs；legacy 在 variant.c_ref/b_ref/s_ref/q
            refs = getattr(variant, 'refs', None)
            cref_val = getattr(refs, 'cref', None) if refs else None
            bref_val = getattr(refs, 'bref', None) if refs else None
            sref_val = getattr(refs, 'sref', None) if refs else None
            q_val = getattr(refs, 'q', None) if refs else None

            if cref_val is None:
                cref_val = getattr(variant, 'c_ref', 0.0)
            if bref_val is None:
                bref_val = getattr(variant, 'b_ref', 0.0)
            if sref_val is None:
                sref_val = getattr(variant, 's_ref', 0.0)
            if q_val is None:
                q_val = getattr(variant, 'q', 0.0)

            # 强制 float 化，避免 None 透传
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
            logger.debug("读取变体字段失败", exc_info=True)
            return None, None, None, 0.0, 0.0, 0.0, 0.0

    def _rename_part(self, new_name: str, is_source: bool):
        """重命名当前 Part，保持模型与选择器一致。"""
        try:
            if not self._ensure_project_model():
                return
            new_name = (new_name or '').strip()
            if not new_name:
                return

            parts = self.gui.project_model.source_parts if is_source else self.gui.project_model.target_parts
            selector = None
            try:
                selector = self.gui.source_panel.part_selector if is_source else self.gui.target_panel.part_selector
            except Exception:
                selector = None

            try:
                current_name = getattr(self.gui, '_current_source_part_name' if is_source else '_current_target_part_name', None)
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
                self.gui._current_source_part_name = new_name
            else:
                self.gui._current_target_part_name = new_name

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

    # ===== Source 管理 =====
    def add_source_part(self, suggested_name: str = None):
        """添加新的 Source Part（使用 ProjectConfigModel）"""
        if getattr(self.gui, '_is_initializing', False):
            logger.debug("初始化期间跳过 add_source_part")
            return
        if not self._ensure_project_model():
            return
        try:
            base_name = (suggested_name or '').strip()
            if not base_name:
                try:
                    base_name = self.gui.src_part_name.text().strip()
                except Exception:
                    base_name = "NewSourcePart"
            existing = set(self.gui.project_model.source_parts.keys())
            name = self._unique_name(base_name, existing)

            # 读取面板强类型数据
            try:
                cs_model = self.gui.source_panel.get_coordinate_system_model()
                refs_model = self.gui.source_panel.get_reference_values_model()
            except Exception:
                logger.debug("读取 Source 面板强类型数据失败", exc_info=True)
                cs_model = None
                refs_model = None
            if cs_model is None or refs_model is None:
                raise ValueError("无法从 Source 面板读取强类型数据")
            variant = PMVariant(part_name=name, coord_system=cs_model, refs=refs_model)
            self.gui.project_model.source_parts[name] = PMPart(part_name=name, variants=[variant])
            self.gui._current_source_part_name = name

            # 发射 SignalBus 事件
            try:
                self.signal_bus.partAdded.emit('Source', name)
            except Exception:
                logger.debug("发射 partAdded 信号失败", exc_info=True)
            QMessageBox.information(self.gui, '成功', f'Source Part "{name}" 已添加')
        except Exception as e:
            logger.error(f"添加 Source Part 失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'添加失败: {e}')

    def remove_source_part(self, name_hint: str = None):
        """删除当前 Source Part（使用 ProjectConfigModel）"""
        if not self._ensure_project_model():
            return
        try:
            name = (name_hint or '').strip()
            if not name:
                try:
                    name = self.gui.source_panel.part_selector.currentText()
                except Exception:
                    name = None
        except Exception:
            name = None
        if not name:
            QMessageBox.warning(self.gui, '提示', '没有可删除的 Source Part')
            return
        try:
            self.gui.project_model.source_parts.pop(name, None)
            self.gui._current_source_part_name = None
            # 发射 SignalBus 事件
            try:
                self.signal_bus.partRemoved.emit('Source', name)
            except Exception:
                logger.debug("发射 partRemoved 信号失败", exc_info=True)
            QMessageBox.information(self.gui, '成功', f'Source Part "{name}" 已删除')
        except Exception as e:
            logger.error(f"删除 Source Part 失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'删除失败: {e}')

    # ===== Target 管理 =====
    def add_target_part(self, suggested_name: str = None):
        """添加新 Target Part（使用 ProjectConfigModel）。

        不再弹出输入对话框；优先使用传入的 `suggested_name` 或面板上的文本字段。
        行为与 `add_source_part` 保持一致。
        """
        if getattr(self.gui, '_is_initializing', False):
            logger.debug("初始化期间跳过 add_target_part")
            return
        if not self._ensure_project_model():
            return
        try:
            base_name = (suggested_name or '').strip()
            if not base_name:
                try:
                    base_name = self.gui.tgt_part_name.text().strip()
                except Exception:
                    base_name = "NewTargetPart"

            existing = set(self.gui.project_model.target_parts.keys())
            name = self._unique_name(base_name, existing)

            try:
                cs_model = self.gui.target_panel.get_coordinate_system_model()
                refs_model = self.gui.target_panel.get_reference_values_model()
                variant = PMVariant(part_name=name, coord_system=cs_model, refs=refs_model)
            except Exception:
                logger.debug("读取 Target 面板强类型数据失败", exc_info=True)
                raise

            self.gui.project_model.target_parts[name] = PMPart(part_name=name, variants=[variant])
            self.gui._current_target_part_name = name

            # 发射 SignalBus 事件
            try:
                self.signal_bus.partAdded.emit('Target', name)
            except Exception:
                logger.debug("发射 partAdded 信号失败", exc_info=True)
            QMessageBox.information(self.gui, '成功', f'Target Part "{name}" 已添加')
        except Exception as e:
            logger.error(f"添加 Target Part 失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'添加失败: {e}')

    def remove_target_part(self):
        """删除当前 Target Part（使用 ProjectConfigModel）"""
        if not self._ensure_project_model():
            return
        try:
            try:
                name = self.gui.target_panel.part_selector.currentText()
            except Exception:
                name = None
        except Exception:
            name = None
        if not name:
            QMessageBox.warning(self.gui, '提示', '当前没有可删除的 Target Part')
            return
        try:
            self.gui.project_model.target_parts.pop(name, None)

            self.gui._current_target_part_name = None
            self.gui._current_target_variant = None

            try:
                self.gui.tgt_table.clearContents()
            except Exception:
                pass
            # 面板会根据总线事件自行更新选择器列表

            # 无需回写 legacy 字典
            # 发射 SignalBus 事件
            try:
                self.signal_bus.partRemoved.emit('Target', name)
            except Exception:
                logger.debug("发射 partRemoved 信号失败", exc_info=True)
            QMessageBox.information(self.gui, '成功', f'Target Part "{name}" 已删除')
        except Exception as e:
            logger.error(f"删除 Target Part 失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'删除失败: {e}')

    # ===== 切换事件 =====
    def on_source_variant_changed(self, idx: int):
        """Source 变体索引变化事件：根据索引更新 UI。"""
        try:
            sel = getattr(self.gui, "_current_source_part_name", None) or getattr(self.gui.source_panel.part_selector, 'currentText', lambda: '')()
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
                self.gui.src_part_name.blockSignals(True)
                self.gui.src_part_name.setText(part_name)
            finally:
                try:
                    self.gui.src_part_name.blockSignals(False)
                except Exception:
                    pass

            # 旧兼容性隐藏控件已删除，使用 Panel setter 统一更新

            try:
                coord_dict = {
                    'Orig': [cs.origin[0], cs.origin[1], cs.origin[2]],
                    'X': [cs.x_axis[0], cs.x_axis[1], cs.x_axis[2]],
                    'Y': [cs.y_axis[0], cs.y_axis[1], cs.y_axis[2]],
                    'Z': [cs.z_axis[0], cs.z_axis[1], cs.z_axis[2]],
                    'MomentCenter': mc
                }
                self.gui.source_panel.set_coord_data(coord_dict)
            except Exception as e:
                logger.debug(f"同步 Source 变体坐标失败: {e}")
        except Exception as e:
            logger.error(f"Source 变体切换失败: {e}")

    def on_target_variant_changed(self, idx: int):
        """Target 变体索引变化事件：根据索引更新 UI。"""
        try:
            sel = getattr(self.gui, "_current_target_part_name", None) or getattr(self.gui.target_panel.part_selector, 'currentText', lambda: '')()
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
                self.gui.tgt_part_name.blockSignals(True)
                self.gui.tgt_part_name.setText(part_name)
            finally:
                try:
                    self.gui.tgt_part_name.blockSignals(False)
                except Exception:
                    pass

            # 通过面板控件统一更新，无需同步隐藏控件

            try:
                coord_dict = {
                    'Orig': [cs.origin[0], cs.origin[1], cs.origin[2]],
                    'X': [cs.x_axis[0], cs.x_axis[1], cs.x_axis[2]],
                    'Y': [cs.y_axis[0], cs.y_axis[1], cs.y_axis[2]],
                    'Z': [cs.z_axis[0], cs.z_axis[1], cs.z_axis[2]],
                    'MomentCenter': mc
                }
                self.gui.target_panel.set_coord_data(coord_dict)
            except Exception as e:
                logger.debug(f"同步 Target 变体坐标失败: {e}")
        except Exception as e:
            logger.error(f"Target 变体切换失败: {e}")


    # ===== 名称变更事件 =====
    def on_source_part_name_changed(self, new_text: str):
        """Source PartName 文本框变化"""
        try:
            self._rename_part(new_text, is_source=True)

        except Exception as e:
            logger.debug(f"Source PartName 变化处理失败: {e}")

    def on_target_part_name_changed(self, new_text: str):
        """Target PartName 文本框变化"""
        try:
            self._rename_part(new_text, is_source=False)

        except Exception as e:
            logger.debug(f"Target PartName 变化处理失败: {e}")

    # ===== 总线请求处理 =====
    def _on_part_add_requested(self, side: str, name: str):
        try:
            side_l = (side or '').lower()
            if side_l in ('source', 'src'):
                self.add_source_part(suggested_name=name)
            elif side_l in ('target', 'tgt'):
                self.add_target_part()
        except Exception:
            logger.debug("处理 partAddRequested 失败", exc_info=True)

    def _on_part_remove_requested(self, side: str, name: str):
        try:
            side_l = (side or '').lower()
            if side_l in ('source', 'src'):
                self.remove_source_part(name_hint=name)
            elif side_l in ('target', 'tgt'):
                self.remove_target_part()
        except Exception:
            logger.debug("处理 partRemoveRequested 失败", exc_info=True)
    
    # ===== Part 保存方法（从 main_window 迁移）=====
    def save_current_source_part(self):
        """将当前 Source 表单保存到新模型（使用强类型接口）"""
        try:
            part_name = self.gui.src_part_name.text() if hasattr(self.gui, "src_part_name") else "Global"
            if hasattr(self.gui, 'source_panel'):
                payload = self.gui.source_panel.to_variant_payload(part_name)
            else:
                logger.debug("source_panel 不存在")
                return

            # 更新新模型 ProjectConfigModel
            try:
                if not self._ensure_project_model():
                    return
                
                # 使用面板提供的强类型模型接口
                cs_model = self.gui.source_panel.get_coordinate_system_model()
                refs_model = self.gui.source_panel.get_reference_values_model()
                pm_variant = PMVariant(part_name=part_name, coord_system=cs_model, refs=refs_model)
                
                self.gui.project_model.source_parts[part_name] = PMPart(
                    part_name=part_name,
                    variants=[pm_variant]
                )
            except Exception:
                logger.debug("更新 ProjectConfigModel 失败", exc_info=True)
        except Exception:
            logger.debug("save_current_source_part failed", exc_info=True)

    def save_current_target_part(self):
        """将当前 Target 表单保存到新模型（使用强类型接口）"""
        try:
            part_name = self.gui.tgt_part_name.text() if hasattr(self.gui, "tgt_part_name") else "Target"
            if hasattr(self.gui, 'target_panel'):
                payload = self.gui.target_panel.to_variant_payload(part_name)
            else:
                logger.debug("target_panel 不存在")
                return

            # 更新新模型 ProjectConfigModel
            try:
                if not self._ensure_project_model():
                    return
                
                # 使用面板提供的强类型模型接口
                cs_model = self.gui.target_panel.get_coordinate_system_model()
                refs_model = self.gui.target_panel.get_reference_values_model()
                pm_variant = PMVariant(part_name=part_name, coord_system=cs_model, refs=refs_model)
                
                self.gui.project_model.target_parts[part_name] = PMPart(
                    part_name=part_name,
                    variants=[pm_variant]
                )
            except Exception:
                logger.debug("更新 ProjectConfigModel 失败", exc_info=True)
        except Exception:
            logger.debug("save_current_target_part failed", exc_info=True)
    
    # ===== Part 变更事件处理（从 main_window 迁移）=====
    def on_source_part_changed(self):
        """Source Part 选择变化时的处理"""
        try:
            logger.debug("=== on_source_part_changed 被调用 ===")
            if not hasattr(self.gui, 'source_panel'):
                logger.debug("source_panel 不存在")
                return
            
            part_name = self.gui.source_panel.part_selector.currentText()
            logger.debug(f"当前选择的 Source Part: {part_name}")
            if not part_name:
                logger.debug("part_name 为空")
                return
            
            # 保存当前 Part（如果需要）
            old_name = getattr(self.gui, '_current_source_part_name', None)
            logger.debug(f"旧的 Source Part: {old_name}")
            if old_name and old_name != part_name:
                logger.debug(f"保存旧 Part: {old_name}")
                self.save_current_source_part()
            
            # 加载新 Part
            variants = self._get_variants(part_name, is_source=True)
            logger.debug(f"找到 {len(variants) if variants else 0} 个变体")
            if variants:
                variant = variants[0]
                _, cs, mc, cref_val, bref_val, sref_val, q_val = self._read_variant_fields(variant)
                logger.debug(f"读取变体字段: cs={cs is not None}, mc={mc}, cref={cref_val}, bref={bref_val}, sref={sref_val}, q={q_val}")
                
                # 应用到面板
                payload = {
                    'PartName': part_name,
                    'CoordSystem': {
                        'Orig': list(cs.origin) if cs else [0.0, 0.0, 0.0],
                        'X': list(cs.x_axis) if cs else [1.0, 0.0, 0.0],
                        'Y': list(cs.y_axis) if cs else [0.0, 1.0, 0.0],
                        'Z': list(cs.z_axis) if cs else [0.0, 0.0, 1.0],
                        'MomentCenter': mc,
                    },
                    'Cref': cref_val,
                    'Bref': bref_val,
                    'Sref': sref_val,
                    'Q': q_val,
                }
                logger.debug(f"准备应用 payload: {payload}")
                self.gui.source_panel.apply_variant_payload(payload)
                logger.debug("payload 已应用")
            else:
                logger.warning(f"未找到 Part '{part_name}' 的变体")
            
            self.gui._current_source_part_name = part_name
            logger.debug("=== on_source_part_changed 完成 ===")
            
        except Exception as e:
            logger.error(f"on_source_part_changed 失败: {e}", exc_info=True)
    
    def on_target_part_changed(self):
        """Target Part 选择变化时的处理"""
        try:
            logger.debug("=== on_target_part_changed 被调用 ===")
            if not hasattr(self.gui, 'target_panel'):
                logger.debug("target_panel 不存在")
                return
            
            part_name = self.gui.target_panel.part_selector.currentText()
            logger.debug(f"当前选择的 Target Part: {part_name}")
            if not part_name:
                logger.debug("part_name 为空")
                return
            
            # 保存当前 Part（如果需要）
            old_name = getattr(self.gui, '_current_target_part_name', None)
            logger.debug(f"旧的 Target Part: {old_name}")
            if old_name and old_name != part_name:
                logger.debug(f"保存旧 Part: {old_name}")
                self.save_current_target_part()
            
            # 加载新 Part
            variants = self._get_variants(part_name, is_source=False)
            logger.debug(f"找到 {len(variants) if variants else 0} 个变体")
            if variants:
                variant = variants[0]
                _, cs, mc, cref_val, bref_val, sref_val, q_val = self._read_variant_fields(variant)
                logger.debug(f"读取变体字段: cs={cs is not None}, mc={mc}, cref={cref_val}, bref={bref_val}, sref={sref_val}, q={q_val}")
                
                # 应用到面板
                payload = {
                    'PartName': part_name,
                    'CoordSystem': {
                        'Orig': list(cs.origin) if cs else [0.0, 0.0, 0.0],
                        'X': list(cs.x_axis) if cs else [1.0, 0.0, 0.0],
                        'Y': list(cs.y_axis) if cs else [0.0, 1.0, 0.0],
                        'Z': list(cs.z_axis) if cs else [0.0, 0.0, 1.0],
                        'MomentCenter': mc,
                    },
                    'Cref': cref_val,
                    'Bref': bref_val,
                    'Sref': sref_val,
                    'Q': q_val,
                }
                logger.debug(f"准备应用 payload: {payload}")
                self.gui.target_panel.apply_variant_payload(payload)
                logger.debug("payload 已应用")
            else:
                logger.warning(f"未找到 Part '{part_name}' 的变体")
            
            self.gui._current_target_part_name = part_name
            logger.debug("=== on_target_part_changed 完成 ===")
            
        except Exception as e:
            logger.error(f"on_target_part_changed 失败: {e}", exc_info=True)
