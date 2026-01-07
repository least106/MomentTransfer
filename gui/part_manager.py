"""
Part 管理模块 - 处理 Part 的添加、删除和切换
"""
import logging
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QInputDialog, QMessageBox
from src.data_loader import ProjectData
from src.models import ProjectConfig, Part, Variant
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

    # ===== 辅助方法 =====
    def _ensure_project_config(self) -> bool:
        """确保 gui 持有 ProjectConfig，必要时创建空模型。"""
        if getattr(self.gui, "project_config", None) is None:
            try:
                self.gui.project_config = ProjectConfig()
            except Exception:
                logger.debug("创建 ProjectConfig 失败", exc_info=True)
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
        """优先从 ProjectConfig 读取变体，缺失时回退到 legacy ProjectData。"""
        variants = []
        if self._ensure_project_config():
            parts = self.gui.project_config.source_parts if is_source else self.gui.project_config.target_parts
            part = parts.get(part_name)
            if part:
                variants = part.variants

        if not variants:
            cfg = getattr(self.gui, "current_config", None)
            if isinstance(cfg, ProjectData):
                parts = cfg.source_parts if is_source else cfg.target_parts
                variants = parts.get(part_name, [])

        return variants

    @staticmethod
    def _read_variant_fields(variant):
        """抽取变体字段，兼容新旧模型属性名。"""
        cs = getattr(variant, "coord_system", None)
        mc = getattr(variant, "moment_center", None) or getattr(cs, "moment_center", [0.0, 0.0, 0.0])
        part_name = getattr(variant, "part_name", getattr(variant, "name", ""))
        cref_val = float(getattr(variant, "cref", getattr(variant, "c_ref", 1.0)) or 1.0)
        bref_val = float(getattr(variant, "bref", getattr(variant, "b_ref", 1.0)) or 1.0)
        sref_val = float(getattr(variant, "sref", getattr(variant, "s_ref", 10.0)) or 10.0)
        q_val = float(getattr(variant, "q", 1000.0) or 1000.0)
        return part_name, cs, mc, cref_val, bref_val, sref_val, q_val

    def _rename_part(self, new_text: str, is_source: bool):
        """重命名当前选中部件，保持 ProjectConfig 与 UI 一致。"""
        if not new_text:
            return
        if not self._ensure_project_config():
            return

        parts = self.gui.project_config.source_parts if is_source else self.gui.project_config.target_parts
        current_name = self.gui._current_source_part_name if is_source else self.gui._current_target_part_name
        if not current_name:
            return

        part = parts.get(current_name)
        if part is None or new_text == current_name:
            return

        parts.pop(current_name, None)
        part.name = new_text
        for variant in part.variants:
            try:
                variant.part_name = new_text
            except Exception:
                pass
        parts[new_text] = part

        try:
            combo = self.gui.cmb_source_parts if is_source else self.gui.cmb_target_parts
            idx = combo.findText(current_name)
            if idx >= 0:
                combo.setItemText(idx, new_text)
                combo.setCurrentText(new_text)
        except Exception:
            logger.debug("更新部件下拉框名称失败", exc_info=True)

        if is_source:
            self.gui._current_source_part_name = new_text
        else:
            self.gui._current_target_part_name = new_text

        self._sync_legacy_dict()

    def _sync_legacy_dict(self):
        """将 project_config 回写到 _raw_project_dict 与 current_config 以兼容旧流程。"""
        if not self._ensure_project_config():
            return
        try:
            raw = self.gui.project_config.to_dict()
            self.gui._raw_project_dict = raw
            try:
                self.gui.current_config = ProjectData.from_dict(raw)
            except Exception:
                logger.debug("重建 current_config 失败", exc_info=True)
        except Exception:
            logger.debug("回写 legacy 字典失败", exc_info=True)

    # ===== Source 管理 =====
    def add_source_part(self):
        """添加新的 Source Part"""
        if getattr(self.gui, '_is_initializing', False):
            logger.debug("初始化期间跳过 add_source_part")
            return
        if not self._ensure_project_config():
            return
        try:
            default_name = "NewSourcePart"
            try:
                text_val = getattr(self.gui, "src_part_name", None)
                if text_val:
                    val = text_val.text().strip()
                    if val:
                        default_name = val
            except Exception:
                pass

            dialog = QInputDialog(self.gui)
            dialog.setInputMode(QInputDialog.TextInput)
            dialog.setWindowTitle("添加 Source Part")
            dialog.setLabelText("输入新 Part 名称:")
            dialog.setTextValue(default_name)

            try:
                button_box = dialog.findChild(QDialogButtonBox)
                if button_box:
                    ok_btn = button_box.button(QDialogButtonBox.Ok)
                    if ok_btn:
                        ok_btn.setAutoDefault(True)
                        ok_btn.setDefault(True)
                        ok_btn.setFocus()
                        center = ok_btn.mapToGlobal(ok_btn.rect().center())
                        QCursor.setPos(center)
            except Exception:
                logger.debug("设置确定按钮焦点或光标失败", exc_info=True)

            result = dialog.exec()
            name = dialog.textValue().strip()
            if result != QDialog.Accepted or not name:
                return

            existing = set(self.gui.project_config.source_parts.keys())
            name = self._unique_name(name, existing)

            try:
                payload = self.gui.source_panel.to_variant_payload(name)
                variant = Variant.from_dict(payload)
            except Exception:
                logger.debug("读取 Source 面板数据失败，使用默认变体", exc_info=True)
                variant = Variant.from_dict({"PartName": name, "CoordSystem": {}})

            part = Part(name=name, variants=[variant])
            self.gui.project_config.source_parts[name] = part

            try:
                self.gui.cmb_source_parts.addItem(name)
                self.gui.cmb_source_parts.setCurrentText(name)
                self.gui.cmb_source_parts.setVisible(True)
            except Exception:
                logger.debug("更新 Source 下拉框失败", exc_info=True)
            self.gui._current_source_part_name = name

            self._sync_legacy_dict()
            # 发射 SignalBus 事件
            try:
                self.signal_bus.partAdded.emit('Source', name)
            except Exception:
                logger.debug("发射 partAdded 信号失败", exc_info=True)
            QMessageBox.information(self.gui, '成功', f'Source Part "{name}" 已添加')
        except Exception as e:
            logger.error(f"添加 Source Part 失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'添加失败: {e}')

    def remove_source_part(self):
        """删除当前 Source Part"""
        if not self._ensure_project_config():
            return
        try:
            name = self.gui.cmb_source_parts.currentText()
        except Exception:
            name = None
        if not name:
            QMessageBox.warning(self.gui, '提示', '没有可删除的 Source Part')
            return
        try:
            self.gui.project_config.source_parts.pop(name, None)

            try:
                idx = self.gui.cmb_source_parts.currentIndex()
                if idx >= 0:
                    self.gui.cmb_source_parts.removeItem(idx)
            except Exception:
                logger.debug("更新 Source 部件下拉框失败", exc_info=True)

            self.gui._current_source_part_name = None
            try:
                self.gui.src_coord_table.clearContents()
            except Exception:
                pass
            try:
                if self.gui.cmb_source_parts.count() == 0:
                    self.gui.cmb_source_parts.setVisible(False)
            except Exception:
                pass

            self._sync_legacy_dict()
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
    def add_target_part(self):
        """添加新 Target Part"""
        if getattr(self.gui, '_is_initializing', False):
            logger.debug("初始化期间跳过 add_target_part")
            return
        if not self._ensure_project_config():
            return
        try:
            default_name = "NewTargetPart"
            try:
                text_val = getattr(self.gui, "tgt_part_name", None)
                if text_val:
                    val = text_val.text().strip()
                    if val:
                        default_name = val
            except Exception:
                pass

            dialog = QInputDialog(self.gui)
            dialog.setInputMode(QInputDialog.TextInput)
            dialog.setWindowTitle("添加 Target Part")
            dialog.setLabelText("输入新 Part 名称:")
            dialog.setTextValue(default_name)

            try:
                button_box = dialog.findChild(QDialogButtonBox)
                if button_box:
                    ok_btn = button_box.button(QDialogButtonBox.Ok)
                    if ok_btn:
                        ok_btn.setAutoDefault(True)
                        ok_btn.setDefault(True)
                        ok_btn.setFocus()
                        center = ok_btn.mapToGlobal(ok_btn.rect().center())
                        QCursor.setPos(center)
            except Exception:
                logger.debug("设置确定按钮焦点或光标失败", exc_info=True)

            result = dialog.exec()
            name = dialog.textValue().strip()
            if result != QDialog.Accepted or not name:
                return

            existing = set(self.gui.project_config.target_parts.keys())
            name = self._unique_name(name, existing)

            try:
                payload = self.gui.target_panel.to_variant_payload(name)
                variant = Variant.from_dict(payload)
            except Exception:
                logger.debug("读取 Target 面板数据失败，使用默认变体", exc_info=True)
                variant = Variant.from_dict({"PartName": name, "CoordSystem": {}})

            part = Part(name=name, variants=[variant])
            self.gui.project_config.target_parts[name] = part

            try:
                self.gui.cmb_target_parts.addItem(name)
                self.gui.cmb_target_parts.setCurrentText(name)
                self.gui.cmb_target_parts.setVisible(True)
            except Exception:
                logger.debug("更新 Target 下拉框失败", exc_info=True)
            self.gui._current_target_part_name = name

            self._sync_legacy_dict()
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
        """删除当前 Target Part"""
        if not self._ensure_project_config():
            return
        try:
            name = self.gui.cmb_target_parts.currentText()
        except Exception:
            name = None
        if not name:
            QMessageBox.warning(self.gui, '提示', '当前没有可删除的 Target Part')
            return
        try:
            self.gui.project_config.target_parts.pop(name, None)

            try:
                idx = self.gui.cmb_target_parts.currentIndex()
                if idx >= 0:
                    self.gui.cmb_target_parts.removeItem(idx)
            except Exception:
                logger.debug("更新 Target 部件下拉框失败", exc_info=True)

            self.gui._current_target_part_name = None
            self.gui._current_target_variant = None

            try:
                self.gui.tgt_table.clearContents()
            except Exception:
                pass
            try:
                if self.gui.cmb_target_parts.count() == 0:
                    self.gui.cmb_target_parts.setVisible(False)
            except Exception:
                pass

            self._sync_legacy_dict()
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
            sel = getattr(self.gui, "_current_source_part_name", None) or self.gui.cmb_source_parts.currentText()
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

            try:
                self.gui.src_ox.setValue(float(cs.origin[0]))
                self.gui.src_oy.setValue(float(cs.origin[1]))
                self.gui.src_oz.setValue(float(cs.origin[2]))
                self.gui.src_xx.setValue(float(cs.x_axis[0]))
                self.gui.src_xy.setValue(float(cs.x_axis[1]))
                self.gui.src_xz.setValue(float(cs.x_axis[2]))
                self.gui.src_yx.setValue(float(cs.y_axis[0]))
                self.gui.src_yy.setValue(float(cs.y_axis[1]))
                self.gui.src_yz.setValue(float(cs.y_axis[2]))
                self.gui.src_zx.setValue(float(cs.z_axis[0]))
                self.gui.src_zy.setValue(float(cs.z_axis[1]))
                self.gui.src_zz.setValue(float(cs.z_axis[2]))
                self.gui.src_mcx.setValue(float(mc[0]))
                self.gui.src_mcy.setValue(float(mc[1]))
                self.gui.src_mcz.setValue(float(mc[2]))
                if hasattr(self.gui.src_cref, "setValue"):
                    self.gui.src_cref.setValue(cref_val)
                if hasattr(self.gui.src_bref, "setValue"):
                    self.gui.src_bref.setValue(bref_val)
                if hasattr(self.gui.src_sref, "setValue"):
                    self.gui.src_sref.setValue(sref_val)
                if hasattr(self.gui.src_q, "setValue"):
                    self.gui.src_q.setValue(q_val)
                if hasattr(self.gui.src_cref, "setText"):
                    self.gui.src_cref.setText(str(cref_val))
                if hasattr(self.gui.src_bref, "setText"):
                    self.gui.src_bref.setText(str(bref_val))
                if hasattr(self.gui.src_sref, "setText"):
                    self.gui.src_sref.setText(str(sref_val))
                if hasattr(self.gui.src_q, "setText"):
                    self.gui.src_q.setText(str(q_val))
            except Exception as e:
                logger.debug(f"设置 Source 变体控件失败: {e}")

            try:
                coord_dict = {
                    'Orig': [cs.origin[0], cs.origin[1], cs.origin[2]],
                    'X': [cs.x_axis[0], cs.x_axis[1], cs.x_axis[2]],
                    'Y': [cs.y_axis[0], cs.y_axis[1], cs.y_axis[2]],
                    'Z': [cs.z_axis[0], cs.z_axis[1], cs.z_axis[2]],
                    'MomentCenter': mc
                }
                self.gui._set_coord_to_table(self.gui.src_coord_table, coord_dict)
            except Exception as e:
                logger.debug(f"同步 Source 变体坐标到表格失败: {e}")
        except Exception as e:
            logger.error(f"Source 变体切换失败: {e}")

    def on_target_variant_changed(self, idx: int):
        """Target 变体索引变化事件：根据索引更新 UI。"""
        try:
            sel = getattr(self.gui, "_current_target_part_name", None) or self.gui.cmb_target_parts.currentText()
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

            try:
                self.gui.tgt_ox.setValue(float(cs.origin[0]))
                self.gui.tgt_oy.setValue(float(cs.origin[1]))
                self.gui.tgt_oz.setValue(float(cs.origin[2]))
                self.gui.tgt_xx.setValue(float(cs.x_axis[0]))
                self.gui.tgt_xy.setValue(float(cs.x_axis[1]))
                self.gui.tgt_xz.setValue(float(cs.x_axis[2]))
                self.gui.tgt_yx.setValue(float(cs.y_axis[0]))
                self.gui.tgt_yy.setValue(float(cs.y_axis[1]))
                self.gui.tgt_yz.setValue(float(cs.y_axis[2]))
                self.gui.tgt_zx.setValue(float(cs.z_axis[0]))
                self.gui.tgt_zy.setValue(float(cs.z_axis[1]))
                self.gui.tgt_zz.setValue(float(cs.z_axis[2]))
                self.gui.tgt_mcx.setValue(float(mc[0]))
                self.gui.tgt_mcy.setValue(float(mc[1]))
                self.gui.tgt_mcz.setValue(float(mc[2]))
                if hasattr(self.gui.tgt_cref, "setValue"):
                    self.gui.tgt_cref.setValue(cref_val)
                if hasattr(self.gui.tgt_bref, "setValue"):
                    self.gui.tgt_bref.setValue(bref_val)
                if hasattr(self.gui.tgt_sref, "setValue"):
                    self.gui.tgt_sref.setValue(sref_val)
                if hasattr(self.gui.tgt_q, "setValue"):
                    self.gui.tgt_q.setValue(q_val)
                if hasattr(self.gui.tgt_cref, "setText"):
                    self.gui.tgt_cref.setText(str(cref_val))
                if hasattr(self.gui.tgt_bref, "setText"):
                    self.gui.tgt_bref.setText(str(bref_val))
                if hasattr(self.gui.tgt_sref, "setText"):
                    self.gui.tgt_sref.setText(str(sref_val))
                if hasattr(self.gui.tgt_q, "setText"):
                    self.gui.tgt_q.setText(str(q_val))
            except Exception as e:
                logger.debug(f"设置 Target 变体控件失败: {e}")

            try:
                coord_dict = {
                    'Orig': [cs.origin[0], cs.origin[1], cs.origin[2]],
                    'X': [cs.x_axis[0], cs.x_axis[1], cs.x_axis[2]],
                    'Y': [cs.y_axis[0], cs.y_axis[1], cs.y_axis[2]],
                    'Z': [cs.z_axis[0], cs.z_axis[1], cs.z_axis[2]],
                    'MomentCenter': mc
                }
                self.gui._set_coord_to_table(self.gui.tgt_coord_table, coord_dict)
            except Exception as e:
                logger.debug(f"同步 Target 变体坐标到表格失败: {e}")
        except Exception as e:
            logger.error(f"Target 变体切换失败: {e}")
    def on_source_part_changed(self):
        """Source Part 切换事件 - 更新 UI 和表单"""
        try:
            try:
                if hasattr(self.gui, '_save_current_source_part'):
                    self.gui._save_current_source_part()
            except Exception:
                logger.debug("保存当前 Source 部件失败", exc_info=True)

            sel = self.gui.cmb_source_parts.currentText()
            self.gui._current_source_part_name = sel
            variants = self._get_variants(sel, is_source=True)
            max_idx = max(0, len(variants) - 1)
            self.gui.spin_source_variant.setRange(0, max_idx)

            if variants:
                frame = variants[0]
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

                try:
                    self.gui.src_ox.setValue(float(cs.origin[0]))
                    self.gui.src_oy.setValue(float(cs.origin[1]))
                    self.gui.src_oz.setValue(float(cs.origin[2]))
                    self.gui.src_xx.setValue(float(cs.x_axis[0]))
                    self.gui.src_xy.setValue(float(cs.x_axis[1]))
                    self.gui.src_xz.setValue(float(cs.x_axis[2]))
                    self.gui.src_yx.setValue(float(cs.y_axis[0]))
                    self.gui.src_yy.setValue(float(cs.y_axis[1]))
                    self.gui.src_yz.setValue(float(cs.y_axis[2]))
                    self.gui.src_zx.setValue(float(cs.z_axis[0]))
                    self.gui.src_zy.setValue(float(cs.z_axis[1]))
                    self.gui.src_zz.setValue(float(cs.z_axis[2]))
                    self.gui.src_mcx.setValue(float(mc[0]))
                    self.gui.src_mcy.setValue(float(mc[1]))
                    self.gui.src_mcz.setValue(float(mc[2]))
                    if hasattr(self.gui.src_cref, "setValue"):
                        self.gui.src_cref.setValue(cref_val)
                    if hasattr(self.gui.src_bref, "setValue"):
                        self.gui.src_bref.setValue(bref_val)
                    if hasattr(self.gui.src_sref, "setValue"):
                        self.gui.src_sref.setValue(sref_val)
                    if hasattr(self.gui.src_q, "setValue"):
                        self.gui.src_q.setValue(q_val)
                    if hasattr(self.gui.src_cref, "setText"):
                        self.gui.src_cref.setText(str(cref_val))
                    if hasattr(self.gui.src_bref, "setText"):
                        self.gui.src_bref.setText(str(bref_val))
                    if hasattr(self.gui.src_sref, "setText"):
                        self.gui.src_sref.setText(str(sref_val))
                    if hasattr(self.gui.src_q, "setText"):
                        self.gui.src_q.setText(str(q_val))
                except Exception as e:
                    logger.debug(f"设置 Source 坐标系控件失败: {e}")

                try:
                    coord_dict = {
                        'Orig': [cs.origin[0], cs.origin[1], cs.origin[2]],
                        'X': [cs.x_axis[0], cs.x_axis[1], cs.x_axis[2]],
                        'Y': [cs.y_axis[0], cs.y_axis[1], cs.y_axis[2]],
                        'Z': [cs.z_axis[0], cs.z_axis[1], cs.z_axis[2]],
                        'MomentCenter': mc
                    }
                    self.gui._set_coord_to_table(self.gui.src_coord_table, coord_dict)
                except Exception as e:
                    logger.debug(f"同步 Source 坐标到表格失败: {e}")

        except Exception as e:
            logger.error(f"Source Part 切换失败: {e}")

    def on_target_part_changed(self):
        """Target Part 切换事件 - 更新 UI 和表单"""
        try:
            try:
                if hasattr(self.gui, '_save_current_target_part'):
                    self.gui._save_current_target_part()
            except Exception:
                logger.debug("保存当前 Target 部件失败", exc_info=True)

            sel = self.gui.cmb_target_parts.currentText()
            self.gui._current_target_part_name = sel
            variants = self._get_variants(sel, is_source=False)
            max_idx = max(0, len(variants) - 1)
            self.gui.spin_target_variant.setRange(0, max_idx)

            if variants:
                frame = variants[0]
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

                try:
                    self.gui.tgt_ox.setValue(float(cs.origin[0]))
                    self.gui.tgt_oy.setValue(float(cs.origin[1]))
                    self.gui.tgt_oz.setValue(float(cs.origin[2]))
                    self.gui.tgt_xx.setValue(float(cs.x_axis[0]))
                    self.gui.tgt_xy.setValue(float(cs.x_axis[1]))
                    self.gui.tgt_xz.setValue(float(cs.x_axis[2]))
                    self.gui.tgt_yx.setValue(float(cs.y_axis[0]))
                    self.gui.tgt_yy.setValue(float(cs.y_axis[1]))
                    self.gui.tgt_yz.setValue(float(cs.y_axis[2]))
                    self.gui.tgt_zx.setValue(float(cs.z_axis[0]))
                    self.gui.tgt_zy.setValue(float(cs.z_axis[1]))
                    self.gui.tgt_zz.setValue(float(cs.z_axis[2]))
                    self.gui.tgt_mcx.setValue(float(mc[0]))
                    self.gui.tgt_mcy.setValue(float(mc[1]))
                    self.gui.tgt_mcz.setValue(float(mc[2]))
                    if hasattr(self.gui.tgt_cref, "setValue"):
                        self.gui.tgt_cref.setValue(cref_val)
                    if hasattr(self.gui.tgt_bref, "setValue"):
                        self.gui.tgt_bref.setValue(bref_val)
                    if hasattr(self.gui.tgt_sref, "setValue"):
                        self.gui.tgt_sref.setValue(sref_val)
                    if hasattr(self.gui.tgt_q, "setValue"):
                        self.gui.tgt_q.setValue(q_val)
                    if hasattr(self.gui.tgt_cref, "setText"):
                        self.gui.tgt_cref.setText(str(cref_val))
                    if hasattr(self.gui.tgt_bref, "setText"):
                        self.gui.tgt_bref.setText(str(bref_val))
                    if hasattr(self.gui.tgt_sref, "setText"):
                        self.gui.tgt_sref.setText(str(sref_val))
                    if hasattr(self.gui.tgt_q, "setText"):
                        self.gui.tgt_q.setText(str(q_val))
                except Exception as e:
                    logger.debug(f"设置 Target 坐标系控件失败: {e}")

                try:
                    coord_dict = {
                        'Orig': [cs.origin[0], cs.origin[1], cs.origin[2]],
                        'X': [cs.x_axis[0], cs.x_axis[1], cs.x_axis[2]],
                        'Y': [cs.y_axis[0], cs.y_axis[1], cs.y_axis[2]],
                        'Z': [cs.z_axis[0], cs.z_axis[1], cs.z_axis[2]],
                        'MomentCenter': mc
                    }
                    self.gui._set_coord_to_table(self.gui.tgt_coord_table, coord_dict)
                except Exception as e:
                    logger.debug(f"同步 Target 坐标到表格失败: {e}")

        except Exception as e:
            logger.error(f"Target Part 切换失败: {e}")

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
