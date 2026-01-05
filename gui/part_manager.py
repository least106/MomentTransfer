"""
Part 管理模块 - 处理 Part 的添加、删除和切换
"""
import logging
from PySide6.QtWidgets import QMessageBox, QInputDialog
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
            # 获取输入的 Part 名称
            name, ok = QInputDialog.getText(
                self.gui, 
                '添加 Source Part', 
                '输入新 Part 名称:',
                text='NewSourcePart'
            )
            if not ok or not name:
                return
            
            # 检查重名
            if (hasattr(self.gui, 'current_config') and 
                self.gui.current_config and
                isinstance(self.gui.current_config, ProjectData)):
                if name in self.gui.current_config.source_parts:
                    # Part 已存在，提示用户
                    resp = QMessageBox.question(
                        self.gui, '重名',
                        f'Source Part "{name}" 已存在。\n'
                        f'[覆盖] 替换现有\n[唯一] 自动生成唯一名\n[取消] 放弃',
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                    )
                    if resp == QMessageBox.Cancel:
                        return
                    elif resp == QMessageBox.No:
                        # 自动生成唯一名
                        i = 1
                        new_name = f"{name}_{i}"
                        while new_name in self.gui.current_config.source_parts:
                            i += 1
                            new_name = f"{name}_{i}"
                        name = new_name
            
            # 添加到 UI
            self.gui.cmb_source_parts.addItem(name)
            self.gui.cmb_source_parts.setCurrentText(name)
            self.gui.cmb_source_parts.setVisible(True)
            
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
            name, ok = QInputDialog.getText(
                self.gui,
                '添加 Target Part',
                '输入新 Part 名称:',
                text='NewTargetPart'
            )
            if not ok or not name:
                return
            
            # 检查重名
            if (hasattr(self.gui, 'current_config') and 
                self.gui.current_config and
                isinstance(self.gui.current_config, ProjectData)):
                if name in self.gui.current_config.target_parts:
                    resp = QMessageBox.question(
                        self.gui, '重名',
                        f'Target Part "{name}" 已存在。\n'
                        f'[覆盖] 替换现有\n[唯一] 自动生成唯一名\n[取消] 放弃',
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                    )
                    if resp == QMessageBox.Cancel:
                        return
                    elif resp == QMessageBox.No:
                        # 自动生成唯一名
                        i = 1
                        new_name = f"{name}_{i}"
                        while new_name in self.gui.current_config.target_parts:
                            i += 1
                            new_name = f"{name}_{i}"
                        name = new_name
            
            # 添加到 UI
            self.gui.cmb_target_parts.addItem(name)
            self.gui.cmb_target_parts.setCurrentText(name)
            self.gui.cmb_target_parts.setVisible(True)
            
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
            if not hasattr(self.gui, 'current_config') or self.gui.current_config is None:
                return
            
            if not isinstance(self.gui.current_config, ProjectData):
                return
            
            sel = self.gui.cmb_source_parts.currentText()
            variants = self.gui.current_config.source_parts.get(sel, [])
            max_idx = max(0, len(variants) - 1)
            self.gui.spin_source_variant.setRange(0, max_idx)
            
            if variants:
                frame = variants[0]
                cs = frame.coord_system
                mc = frame.moment_center or [0.0, 0.0, 0.0]
                
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
                except Exception as e:
                    logger.debug(f"设置 Source 坐标系控件失败: {e}")
        
        except Exception as e:
            logger.error(f"Source Part 切换失败: {e}")
    
    def on_target_part_changed(self):
        """Target Part 切换事件 - 更新 UI 和表单"""
        try:
            if not hasattr(self.gui, 'current_config') or self.gui.current_config is None:
                return
            
            if not isinstance(self.gui.current_config, ProjectData):
                return
            
            sel = self.gui.cmb_target_parts.currentText()
            variants = self.gui.current_config.target_parts.get(sel, [])
            max_idx = max(0, len(variants) - 1)
            self.gui.spin_target_variant.setRange(0, max_idx)
            
            if variants:
                frame = variants[0]
                cs = frame.coord_system
                mc = frame.moment_center or [0.0, 0.0, 0.0]
                
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

