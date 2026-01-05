"""
Part 管理模块 - 处理 Part 的添加、删除和切换
"""
import logging
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QInputDialog, QMessageBox
from src.data_loader import ProjectData

logger = logging.getLogger(__name__)


class PartManager:
    """Part 管理器 - 管理 Source 和 Target Part"""
    
    def __init__(self, gui_instance):
        """初始化 Part 管理器"""
        self.gui = gui_instance
    
    def add_source_part(self):
        """添加新的 Source Part"""
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

            # 将焦点和鼠标移动到确定按钮，方便用户直接确认
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

            # 检查重名：使用 current_config、原始字典、下拉框三重检查
            existing_names = set()
            try:
                if hasattr(self.gui, 'cmb_source_parts'):
                    existing_names.update({self.gui.cmb_source_parts.itemText(i) for i in range(self.gui.cmb_source_parts.count())})
            except Exception:
                pass
            try:
                if getattr(self.gui, '_raw_project_dict', None):
                    parts = self.gui._raw_project_dict.get('Source', {}).get('Parts', [])
                    for p in parts:
                        n = (p.get('PartName') or '').strip()
                        if n:
                            existing_names.add(n)
            except Exception:
                pass
            try:
                if hasattr(self.gui, 'current_config') and isinstance(self.gui.current_config, ProjectData):
                    existing_names.update(self.gui.current_config.source_parts.keys())
            except Exception:
                pass

            if name in existing_names:
                QMessageBox.warning(self.gui, "重复的部件名", f"Source Part \"{name}\" 已存在，请使用不同的名称。")
                return

            def _val(widget, default=0.0):
                try:
                    if hasattr(widget, "value"):
                        return float(widget.value())
                    if hasattr(widget, "text"):
                        return float(widget.text())
                except Exception:
                    pass
                return default

            # 若有原始字典，先创建占位数据，确保后续切换/保存同步
            try:
                if getattr(self.gui, '_raw_project_dict', None) is None:
                    self.gui._raw_project_dict = {"Source": {"Parts": []}, "Target": {"Parts": []}}
                parts = self.gui._raw_project_dict.setdefault('Source', {}).setdefault('Parts', [])
                parts.append({
                    "PartName": name,
                    "Variants": [{
                        "PartName": name,
                        "CoordSystem": {
                            "Orig": [_val(self.gui.src_ox), _val(self.gui.src_oy), _val(self.gui.src_oz)],
                            "X": [_val(self.gui.src_xx), _val(self.gui.src_xy), _val(self.gui.src_xz)],
                            "Y": [_val(self.gui.src_yx), _val(self.gui.src_yy), _val(self.gui.src_yz)],
                            "Z": [_val(self.gui.src_zx), _val(self.gui.src_zy), _val(self.gui.src_zz)]
                        },
                        "MomentCenter": [_val(self.gui.src_mcx), _val(self.gui.src_mcy), _val(self.gui.src_mcz)],
                        "Cref": _val(self.gui.src_cref, 1.0),
                        "Bref": _val(self.gui.src_bref, 1.0),
                        "Q": _val(self.gui.src_q, 1000.0),
                        "S": _val(self.gui.src_sref, 10.0)
                    }]
                })
                try:
                    self.gui.current_config = ProjectData.from_dict(self.gui._raw_project_dict)
                except Exception:
                    logger.debug("重建 current_config 失败", exc_info=True)
            except Exception:
                logger.debug("写入 Source 部件到原始字典失败", exc_info=True)

            # 添加到 UI
            self.gui.cmb_source_parts.addItem(name)
            self.gui.cmb_source_parts.setCurrentText(name)
            self.gui.cmb_source_parts.setVisible(True)
            self.gui._current_source_part_name = name

            QMessageBox.information(self.gui, '成功', f'Source Part "{name}" 已添加')
        
        except Exception as e:
            logger.error(f"添加 Source Part 失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'添加失败: {e}')
    
    def remove_source_part(self):
        """删除当前 Source Part"""
        try:
            if self.gui.cmb_source_parts.count() == 0:
                QMessageBox.warning(self.gui, '提示', '没有可删除的 Source Part')
                return
            
            current = self.gui.cmb_source_parts.currentText()
            resp = QMessageBox.question(
                self.gui, '确认删除',
                f'确认删除 Source Part "{current}"?',
                QMessageBox.Yes | QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return
            
            # 从下拉框移除
            idx = self.gui.cmb_source_parts.currentIndex()
            self.gui.cmb_source_parts.removeItem(idx)
            
            if self.gui.cmb_source_parts.count() == 0:
                self.gui.cmb_source_parts.setVisible(False)
            
            QMessageBox.information(self.gui, '成功', f'Source Part "{current}" 已删除')
        
        except Exception as e:
            logger.error(f"删除 Source Part 失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'删除失败: {e}')
    
    def add_target_part(self):
        """添加新的 Target Part"""
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

            existing_names = set()
            try:
                if hasattr(self.gui, 'cmb_target_parts'):
                    existing_names.update({self.gui.cmb_target_parts.itemText(i) for i in range(self.gui.cmb_target_parts.count())})
            except Exception:
                pass
            try:
                if getattr(self.gui, '_raw_project_dict', None):
                    parts = self.gui._raw_project_dict.get('Target', {}).get('Parts', [])
                    for p in parts:
                        n = (p.get('PartName') or '').strip()
                        if n:
                            existing_names.add(n)
            except Exception:
                pass
            try:
                if hasattr(self.gui, 'current_config') and isinstance(self.gui.current_config, ProjectData):
                    existing_names.update(self.gui.current_config.target_parts.keys())
            except Exception:
                pass

            if name in existing_names:
                QMessageBox.warning(self.gui, "重复的部件名", f"Target Part \"{name}\" 已存在，请使用不同的名称。")
                return

            def _val(widget, default=0.0):
                try:
                    if hasattr(widget, "value"):
                        return float(widget.value())
                    if hasattr(widget, "text"):
                        return float(widget.text())
                except Exception:
                    pass
                return default

            try:
                if getattr(self.gui, '_raw_project_dict', None) is None:
                    self.gui._raw_project_dict = {"Source": {"Parts": []}, "Target": {"Parts": []}}
                parts = self.gui._raw_project_dict.setdefault('Target', {}).setdefault('Parts', [])
                parts.append({
                    "PartName": name,
                    "Variants": [{
                        "PartName": name,
                        "CoordSystem": {
                            "Orig": [_val(self.gui.tgt_ox), _val(self.gui.tgt_oy), _val(self.gui.tgt_oz)],
                            "X": [_val(self.gui.tgt_xx), _val(self.gui.tgt_xy), _val(self.gui.tgt_xz)],
                            "Y": [_val(self.gui.tgt_yx), _val(self.gui.tgt_yy), _val(self.gui.tgt_yz)],
                            "Z": [_val(self.gui.tgt_zx), _val(self.gui.tgt_zy), _val(self.gui.tgt_zz)]
                        },
                        "MomentCenter": [_val(self.gui.tgt_mcx), _val(self.gui.tgt_mcy), _val(self.gui.tgt_mcz)],
                        "Cref": _val(self.gui.tgt_cref, 1.0),
                        "Bref": _val(self.gui.tgt_bref, 1.0),
                        "Q": _val(self.gui.tgt_q, 1000.0),
                        "S": _val(self.gui.tgt_sref, 10.0)
                    }]
                })
                try:
                    self.gui.current_config = ProjectData.from_dict(self.gui._raw_project_dict)
                except Exception:
                    logger.debug("重建 current_config 失败", exc_info=True)
            except Exception:
                logger.debug("写入 Target 部件到原始字典失败", exc_info=True)

            # 添加到 UI
            self.gui.cmb_target_parts.addItem(name)
            self.gui.cmb_target_parts.setCurrentText(name)
            self.gui.cmb_target_parts.setVisible(True)
            self.gui._current_target_part_name = name
            
            QMessageBox.information(self.gui, '成功', f'Target Part "{name}" 已添加')
        
        except Exception as e:
            logger.error(f"添加 Target Part 失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'添加失败: {e}')
    
    def remove_target_part(self):
        """删除当前 Target Part"""
        try:
            if self.gui.cmb_target_parts.count() == 0:
                QMessageBox.warning(self.gui, '提示', '没有可删除的 Target Part')
                return
            
            current = self.gui.cmb_target_parts.currentText()
            resp = QMessageBox.question(
                self.gui, '确认删除',
                f'确认删除 Target Part "{current}"?',
                QMessageBox.Yes | QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return
            
            # 从下拉框移除
            idx = self.gui.cmb_target_parts.currentIndex()
            self.gui.cmb_target_parts.removeItem(idx)
            
            if self.gui.cmb_target_parts.count() == 0:
                self.gui.cmb_target_parts.setVisible(False)
            
            QMessageBox.information(self.gui, '成功', f'Target Part "{current}" 已删除')
        
        except Exception as e:
            logger.error(f"删除 Target Part 失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'删除失败: {e}')
    
    def on_source_part_changed(self):
        """Source Part 切换事件 - 更新 UI 和表单"""
        try:
            # 先保存当前正在编辑的 Source 部件
            try:
                if hasattr(self.gui, '_save_current_source_part'):
                    self.gui._save_current_source_part()
            except Exception:
                logger.debug("保存当前 Source 部件失败", exc_info=True)

            if not hasattr(self.gui, 'current_config') or self.gui.current_config is None:
                if getattr(self.gui, '_raw_project_dict', None):
                    try:
                        self.gui.current_config = ProjectData.from_dict(self.gui._raw_project_dict)
                    except Exception:
                        return
                else:
                    return
            
            if not isinstance(self.gui.current_config, ProjectData):
                return
            
            sel = self.gui.cmb_source_parts.currentText()
            self.gui._current_source_part_name = sel
            variants = self.gui.current_config.source_parts.get(sel, [])
            max_idx = max(0, len(variants) - 1)
            self.gui.spin_source_variant.setRange(0, max_idx)
            
            if variants:
                frame = variants[0]
                cs = frame.coord_system
                mc = frame.moment_center or [0.0, 0.0, 0.0]
                cref_val = float(getattr(frame, "c_ref", 1.0) or 1.0)
                bref_val = float(getattr(frame, "b_ref", 1.0) or 1.0)
                sref_val = float(getattr(frame, "s_ref", 10.0) or 10.0)
                q_val = float(getattr(frame, "q", 1000.0) or 1000.0)
                
                # 屏蔽信号避免触发验证
                try:
                    self.gui.src_part_name.blockSignals(True)
                    self.gui.src_part_name.setText(frame.part_name)
                finally:
                    try:
                        self.gui.src_part_name.blockSignals(False)
                    except Exception:
                        pass
                
                # 更新坐标系控件
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
                    # 更新参考参数
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
        
        except Exception as e:
            logger.error(f"Source Part 切换失败: {e}")
    
    def on_target_part_changed(self):
        """Target Part 切换事件 - 更新 UI 和表单"""
        try:
            # 先保存当前正在编辑的 Target 部件
            try:
                if hasattr(self.gui, '_save_current_target_part'):
                    self.gui._save_current_target_part()
            except Exception:
                logger.debug("保存当前 Target 部件失败", exc_info=True)

            if not hasattr(self.gui, 'current_config') or self.gui.current_config is None:
                if getattr(self.gui, '_raw_project_dict', None):
                    try:
                        self.gui.current_config = ProjectData.from_dict(self.gui._raw_project_dict)
                    except Exception:
                        return
                else:
                    return
            
            if not isinstance(self.gui.current_config, ProjectData):
                return
            
            sel = self.gui.cmb_target_parts.currentText()
            self.gui._current_target_part_name = sel
            variants = self.gui.current_config.target_parts.get(sel, [])
            max_idx = max(0, len(variants) - 1)
            self.gui.spin_target_variant.setRange(0, max_idx)
            
            if variants:
                frame = variants[0]
                cs = frame.coord_system
                mc = frame.moment_center or [0.0, 0.0, 0.0]
                cref_val = float(getattr(frame, "c_ref", 1.0) or 1.0)
                bref_val = float(getattr(frame, "b_ref", 1.0) or 1.0)
                sref_val = float(getattr(frame, "s_ref", 10.0) or 10.0)
                q_val = float(getattr(frame, "q", 1000.0) or 1000.0)
                
                # 屏蔽信号
                try:
                    self.gui.tgt_part_name.blockSignals(True)
                    self.gui.tgt_part_name.setText(frame.part_name)
                finally:
                    try:
                        self.gui.tgt_part_name.blockSignals(False)
                    except Exception:
                        pass
                
                # 更新坐标系控件
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
                    # 更新参考参数
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
        
        except Exception as e:
            logger.error(f"Target Part 切换失败: {e}")
    
    def on_source_part_name_changed(self, new_text: str):
        """Source PartName 文本框变化"""
        try:
            if not hasattr(self.gui, '_raw_project_dict') or not self.gui._raw_project_dict:
                return
            
            # 更新 _raw_project_dict 中的 Part 名称
            try:
                if 'Source' in self.gui._raw_project_dict and 'Parts' in self.gui._raw_project_dict['Source']:
                    parts = self.gui._raw_project_dict['Source']['Parts']
                    if parts:
                        parts[0]['PartName'] = new_text
            except Exception:
                logger.debug("更新 Source PartName 字典失败")
        
        except Exception as e:
            logger.debug(f"Source PartName 变化处理失败: {e}")
    
    def on_target_part_name_changed(self, new_text: str):
        """Target PartName 文本框变化"""
        try:
            if not hasattr(self.gui, '_raw_project_dict') or not self.gui._raw_project_dict:
                return
            
            # 更新 _raw_project_dict 中的 Part 名称
            try:
                if 'Target' in self.gui._raw_project_dict and 'Parts' in self.gui._raw_project_dict['Target']:
                    parts = self.gui._raw_project_dict['Target']['Parts']
                    if parts:
                        parts[0]['PartName'] = new_text
            except Exception:
                logger.debug("更新 Target PartName 字典失败")
        
        except Exception as e:
            logger.debug(f"Target PartName 变化处理失败: {e}")

