"""
配置管理模块 - 处理配置的加载、保存和应用
"""
import json
import logging
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox
from src.data_loader import ProjectData
from src.physics import AeroCalculator
from gui.ui_utils import get_numeric_value

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器 - 管理配置文件的加载、保存和应用"""
    
    def __init__(self, gui_instance):
        """初始化配置管理器
        
        参数：
            gui_instance: IntegratedAeroGUI 实例，用于访问 UI 控件
        """
        self.gui = gui_instance
        self._last_loaded_config_path = None
        self._raw_project_dict = None
    
    def load_config(self):
        """加载配置文件"""
        try:
            fname, _ = QFileDialog.getOpenFileName(
                self.gui, '打开配置', '.', 'JSON Files (*.json)'
            )
            if not fname:
                return
            
            with open(fname, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 保存原始字典以便编辑和写回，并同步到 gui 供 PartManager/_save_current_* 使用
            self._raw_project_dict = data
            try:
                self.gui._raw_project_dict = data
            except Exception:
                logger.debug("同步 _raw_project_dict 到 gui 失败", exc_info=True)

            # 解析为 ProjectData
            project = ProjectData.from_dict(data)
            self.gui.current_config = project
            
            # 记录加载路径
            self._last_loaded_config_path = Path(fname)
            
            # 填充 Target 下拉列表
            self.gui.cmb_target_parts.clear()
            for part in project.target_parts.keys():
                self.gui.cmb_target_parts.addItem(part)
            
            if self.gui.cmb_target_parts.count() > 0:
                self.gui.cmb_target_parts.setVisible(True)
                first = self.gui.cmb_target_parts.currentText() or self.gui.cmb_target_parts.itemText(0)
                try:
                    self.gui._current_target_part_name = first
                except Exception:
                    pass
                variants = project.target_parts.get(first, [])
                self.gui.spin_target_variant.setRange(0, max(0, len(variants) - 1))
            
            # 填充 Source 下拉列表
            try:
                self.gui.cmb_source_parts.clear()
                for part in project.source_parts.keys():
                    self.gui.cmb_source_parts.addItem(part)
                
                if self.gui.cmb_source_parts.count() > 0:
                    self.gui.cmb_source_parts.setVisible(True)
                    firsts = self.gui.cmb_source_parts.currentText() or self.gui.cmb_source_parts.itemText(0)
                    try:
                        self.gui._current_source_part_name = firsts
                    except Exception:
                        pass
                    s_variants = project.source_parts.get(firsts, [])
                    self.gui.spin_source_variant.setRange(0, max(0, len(s_variants) - 1))
            except Exception:
                logger.debug("source_parts 填充失败", exc_info=True)
            
            # 填充 Target 表单
            self._populate_target_form(project)
            
            # 填充 Source 表单
            self._populate_source_form(project)
            
            QMessageBox.information(self.gui, "成功", f"配置已加载:\n{fname}")
            self.gui.statusBar().showMessage(f"已加载: {fname}")
            
            # 自动应用
            try:
                self.apply_config()
            except Exception:
                logger.debug("自动应用配置失败", exc_info=True)
            
            # 添加到最近项目
            try:
                self.gui.add_recent_project(fname)
            except Exception:
                logger.debug("add_recent_project 失败", exc_info=True)
        
        except Exception as e:
            QMessageBox.critical(self.gui, "加载失败", f"无法加载配置文件:\n{str(e)}")
    
    def _populate_target_form(self, project: ProjectData):
        """填充 Target 坐标系表单"""
        try:
            sel_part = self.gui.cmb_target_parts.currentText() or self.gui.cmb_target_parts.itemText(0)
            sel_variant = 0
            frame = project.get_target_part(sel_part, sel_variant)
            cs = frame.coord_system
            mc = frame.moment_center or [0.0, 0.0, 0.0]
            
            # 屏蔽信号避免触发验证
            try:
                self.gui.tgt_part_name.blockSignals(True)
                self.gui.tgt_part_name.setText(frame.part_name)
            finally:
                try:
                    self.gui.tgt_part_name.blockSignals(False)
                except Exception:
                    pass
            
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
            
            # 力矩中心
            try:
                self.gui.tgt_mcx.setValue(float(mc[0]))
                self.gui.tgt_mcy.setValue(float(mc[1]))
                self.gui.tgt_mcz.setValue(float(mc[2]))
            except Exception:
                try:
                    if hasattr(self.gui.tgt_mcx, 'setText'):
                        self.gui.tgt_mcx.setText(str(mc[0]))
                        self.gui.tgt_mcy.setText(str(mc[1]))
                        self.gui.tgt_mcz.setText(str(mc[2]))
                except Exception:
                    pass
            
            self.gui.tgt_cref.setText(str(frame.c_ref or 1.0))
            self.gui.tgt_bref.setText(str(frame.b_ref or 1.0))
            self.gui.tgt_sref.setText(str(frame.s_ref or 10.0))
            self.gui.tgt_q.setText(str(frame.q or 1000.0))
        
        except Exception as e:
            logger.debug(f"填充 Target 表单失败: {e}", exc_info=True)
    
    def _populate_source_form(self, project: ProjectData):
        """填充 Source 坐标系表单"""
        try:
            if (self.gui.cmb_source_parts.count() > 0 and 
                self.gui.cmb_source_parts.isVisible()):
                s_part = self.gui.cmb_source_parts.currentText() or self.gui.cmb_source_parts.itemText(0)
                s_variant = 0
                sframe = project.get_source_part(s_part, s_variant)
            else:
                sframe = project.source_config
            
            scs = sframe.coord_system
            smc = sframe.moment_center or [0.0, 0.0, 0.0]
            
            # 屏蔽信号
            try:
                self.gui.src_part_name.blockSignals(True)
                self.gui.src_part_name.setText(sframe.part_name)
            finally:
                try:
                    self.gui.src_part_name.blockSignals(False)
                except Exception:
                    pass
            
            self.gui.src_ox.setValue(float(scs.origin[0]))
            self.gui.src_oy.setValue(float(scs.origin[1]))
            self.gui.src_oz.setValue(float(scs.origin[2]))
            
            self.gui.src_xx.setValue(float(scs.x_axis[0]))
            self.gui.src_xy.setValue(float(scs.x_axis[1]))
            self.gui.src_xz.setValue(float(scs.x_axis[2]))
            
            self.gui.src_yx.setValue(float(scs.y_axis[0]))
            self.gui.src_yy.setValue(float(scs.y_axis[1]))
            self.gui.src_yz.setValue(float(scs.y_axis[2]))
            
            self.gui.src_zx.setValue(float(scs.z_axis[0]))
            self.gui.src_zy.setValue(float(scs.z_axis[1]))
            self.gui.src_zz.setValue(float(scs.z_axis[2]))
            
            self.gui.src_mcx.setValue(float(smc[0]))
            self.gui.src_mcy.setValue(float(smc[1]))
            self.gui.src_mcz.setValue(float(smc[2]))
            
            self.gui.src_cref.setText(str(sframe.c_ref or 1.0))
            self.gui.src_bref.setText(str(sframe.b_ref or 1.0))
            self.gui.src_sref.setText(str(sframe.s_ref or 10.0))
            
            try:
                self.gui.src_q.setText(str(sframe.q or 1000.0))
            except Exception:
                pass
        
        except Exception as e:
            logger.debug(f"填充 Source 表单失败: {e}", exc_info=True)
    
    def save_config(self):
        """保存配置到 JSON 文件"""
        try:
            # 构建 Parts 格式数据
            src_part = {
                "PartName": self.gui.src_part_name.text() if hasattr(self.gui, 'src_part_name') else "Global",
                "Variants": [{
                    "PartName": self.gui.src_part_name.text() if hasattr(self.gui, 'src_part_name') else "Global",
                    "CoordSystem": {
                        "Orig": [
                            get_numeric_value(self.gui.src_ox),
                            get_numeric_value(self.gui.src_oy),
                            get_numeric_value(self.gui.src_oz)
                        ],
                        "X": [
                            get_numeric_value(self.gui.src_xx),
                            get_numeric_value(self.gui.src_xy),
                            get_numeric_value(self.gui.src_xz)
                        ],
                        "Y": [
                            get_numeric_value(self.gui.src_yx),
                            get_numeric_value(self.gui.src_yy),
                            get_numeric_value(self.gui.src_yz)
                        ],
                        "Z": [
                            get_numeric_value(self.gui.src_zx),
                            get_numeric_value(self.gui.src_zy),
                            get_numeric_value(self.gui.src_zz)
                        ]
                    },
                    "MomentCenter": [
                        get_numeric_value(self.gui.src_mcx),
                        get_numeric_value(self.gui.src_mcy),
                        get_numeric_value(self.gui.src_mcz)
                    ],
                    "Cref": float(self.gui.src_cref.text()) if hasattr(self.gui, 'src_cref') else 1.0,
                    "Bref": float(self.gui.src_bref.text()) if hasattr(self.gui, 'src_bref') else 1.0,
                    "Q": float(self.gui.src_q.text()) if hasattr(self.gui, 'src_q') else 1000.0,
                    "S": float(self.gui.src_sref.text()) if hasattr(self.gui, 'src_sref') else 10.0
                }]
            }
            
            tgt_part = {
                "PartName": self.gui.tgt_part_name.text(),
                "Variants": [{
                    "PartName": self.gui.tgt_part_name.text(),
                    "CoordSystem": {
                        "Orig": [
                            get_numeric_value(self.gui.tgt_ox),
                            get_numeric_value(self.gui.tgt_oy),
                            get_numeric_value(self.gui.tgt_oz)
                        ],
                        "X": [
                            get_numeric_value(self.gui.tgt_xx),
                            get_numeric_value(self.gui.tgt_xy),
                            get_numeric_value(self.gui.tgt_xz)
                        ],
                        "Y": [
                            get_numeric_value(self.gui.tgt_yx),
                            get_numeric_value(self.gui.tgt_yy),
                            get_numeric_value(self.gui.tgt_yz)
                        ],
                        "Z": [
                            get_numeric_value(self.gui.tgt_zx),
                            get_numeric_value(self.gui.tgt_zy),
                            get_numeric_value(self.gui.tgt_zz)
                        ]
                    },
                    "MomentCenter": [
                        get_numeric_value(self.gui.tgt_mcx),
                        get_numeric_value(self.gui.tgt_mcy),
                        get_numeric_value(self.gui.tgt_mcz)
                    ],
                    "Cref": float(self.gui.tgt_cref.text()) if hasattr(self.gui, 'tgt_cref') else 1.0,
                    "Bref": float(self.gui.tgt_bref.text()) if hasattr(self.gui, 'tgt_bref') else 1.0,
                    "Q": float(self.gui.tgt_q.text()) if hasattr(self.gui, 'tgt_q') else 1000.0,
                    "S": float(self.gui.tgt_sref.text()) if hasattr(self.gui, 'tgt_sref') else 10.0
                }]
            }
            
            data = {
                "Source": {"Parts": [src_part]},
                "Target": {"Parts": [tgt_part]}
            }
            
            # 优先覆盖上次加载的文件
            try:
                if self._last_loaded_config_path:
                    with open(self._last_loaded_config_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                    QMessageBox.information(self.gui, "成功", f"配置已覆盖保存:\n{self._last_loaded_config_path}")
                    self.gui.statusBar().showMessage(f"已保存: {self._last_loaded_config_path}")
                    return
            except Exception:
                logger.debug("直接覆盖失败，使用另存为", exc_info=True)
            
            # 另存为
            fname, _ = QFileDialog.getSaveFileName(
                self.gui, '保存配置', 'config.json', 'JSON Files (*.json)'
            )
            if not fname:
                return
            
            with open(fname, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            QMessageBox.information(self.gui, "成功", f"配置已保存:\n{fname}")
            self.gui.statusBar().showMessage(f"已保存: {fname}")
        
        except ValueError as e:
            QMessageBox.warning(self.gui, "输入错误", f"请检查数值输入:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self.gui, "保存失败", str(e))
    
    def apply_config(self):
        """应用当前配置到计算器"""
        try:
            # 同步表格数据到独立控件（为了兼容现有的读取逻辑）
            try:
                if hasattr(self.gui, 'src_coord_table'):
                    src_coord = self.gui._get_coord_from_table(self.gui.src_coord_table)
                    # 更新独立控件的值
                    self.gui.src_ox.setValue(src_coord['Orig'][0])
                    self.gui.src_oy.setValue(src_coord['Orig'][1])
                    self.gui.src_oz.setValue(src_coord['Orig'][2])
                    self.gui.src_xx.setValue(src_coord['X'][0])
                    self.gui.src_xy.setValue(src_coord['X'][1])
                    self.gui.src_xz.setValue(src_coord['X'][2])
                    self.gui.src_yx.setValue(src_coord['Y'][0])
                    self.gui.src_yy.setValue(src_coord['Y'][1])
                    self.gui.src_yz.setValue(src_coord['Y'][2])
                    self.gui.src_zx.setValue(src_coord['Z'][0])
                    self.gui.src_zy.setValue(src_coord['Z'][1])
                    self.gui.src_zz.setValue(src_coord['Z'][2])
            except Exception as e:
                logger.debug(f"同步Source表格数据失败: {e}")
            
            try:
                if hasattr(self.gui, 'tgt_coord_table'):
                    tgt_coord = self.gui._get_coord_from_table(self.gui.tgt_coord_table)
                    # 更新独立控件的值
                    self.gui.tgt_ox.setValue(tgt_coord['Orig'][0])
                    self.gui.tgt_oy.setValue(tgt_coord['Orig'][1])
                    self.gui.tgt_oz.setValue(tgt_coord['Orig'][2])
                    self.gui.tgt_xx.setValue(tgt_coord['X'][0])
                    self.gui.tgt_xy.setValue(tgt_coord['X'][1])
                    self.gui.tgt_xz.setValue(tgt_coord['X'][2])
                    self.gui.tgt_yx.setValue(tgt_coord['Y'][0])
                    self.gui.tgt_yy.setValue(tgt_coord['Y'][1])
                    self.gui.tgt_yz.setValue(tgt_coord['Y'][2])
                    self.gui.tgt_zx.setValue(tgt_coord['Z'][0])
                    self.gui.tgt_zy.setValue(tgt_coord['Z'][1])
                    self.gui.tgt_zz.setValue(tgt_coord['Z'][2])
            except Exception as e:
                logger.debug(f"同步Target表格数据失败: {e}")
            
            # 构建数据结构
            src_part = {
                "PartName": self.gui.src_part_name.text() if hasattr(self.gui, 'src_part_name') else "Global",
                "Variants": [{
                    "PartName": self.gui.src_part_name.text() if hasattr(self.gui, 'src_part_name') else "Global",
                    "CoordSystem": {
                        "Orig": [get_numeric_value(self.gui.src_ox), get_numeric_value(self.gui.src_oy), get_numeric_value(self.gui.src_oz)],
                        "X": [get_numeric_value(self.gui.src_xx), get_numeric_value(self.gui.src_xy), get_numeric_value(self.gui.src_xz)],
                        "Y": [get_numeric_value(self.gui.src_yx), get_numeric_value(self.gui.src_yy), get_numeric_value(self.gui.src_yz)],
                        "Z": [get_numeric_value(self.gui.src_zx), get_numeric_value(self.gui.src_zy), get_numeric_value(self.gui.src_zz)]
                    },
                    "MomentCenter": [get_numeric_value(self.gui.src_mcx), get_numeric_value(self.gui.src_mcy), get_numeric_value(self.gui.src_mcz)],
                    "Cref": float(self.gui.src_cref.text()) if hasattr(self.gui, 'src_cref') else 1.0,
                    "Bref": float(self.gui.src_bref.text()) if hasattr(self.gui, 'src_bref') else 1.0,
                    "Q": float(self.gui.src_q.text()) if hasattr(self.gui, 'src_q') else 1000.0,
                    "S": float(self.gui.src_sref.text()) if hasattr(self.gui, 'src_sref') else 10.0
                }]
            }
            
            tgt_part = {
                "PartName": self.gui.tgt_part_name.text(),
                "Variants": [{
                    "PartName": self.gui.tgt_part_name.text(),
                    "CoordSystem": {
                        "Orig": [get_numeric_value(self.gui.tgt_ox), get_numeric_value(self.gui.tgt_oy), get_numeric_value(self.gui.tgt_oz)],
                        "X": [get_numeric_value(self.gui.tgt_xx), get_numeric_value(self.gui.tgt_xy), get_numeric_value(self.gui.tgt_xz)],
                        "Y": [get_numeric_value(self.gui.tgt_yx), get_numeric_value(self.gui.tgt_yy), get_numeric_value(self.gui.tgt_yz)],
                        "Z": [get_numeric_value(self.gui.tgt_zx), get_numeric_value(self.gui.tgt_zy), get_numeric_value(self.gui.tgt_zz)]
                    },
                    "MomentCenter": [get_numeric_value(self.gui.tgt_mcx), get_numeric_value(self.gui.tgt_mcy), get_numeric_value(self.gui.tgt_mcz)],
                    "Cref": float(self.gui.tgt_cref.text()) if hasattr(self.gui, 'tgt_cref') else 1.0,
                    "Bref": float(self.gui.tgt_bref.text()) if hasattr(self.gui, 'tgt_bref') else 1.0,
                    "Q": float(self.gui.tgt_q.text()) if hasattr(self.gui, 'tgt_q') else 1000.0,
                    "S": float(self.gui.tgt_sref.text()) if hasattr(self.gui, 'tgt_sref') else 10.0
                }]
            }
            
            data = {
                "Source": {"Parts": [src_part]},
                "Target": {"Parts": [tgt_part]}
            }
            
            # 解析为 ProjectData
            self.gui.current_config = ProjectData.from_dict(data)
            
            # 获取选定的 target part
            if (hasattr(self.gui, 'cmb_target_parts') and 
                self.gui.cmb_target_parts.isVisible() and 
                self.gui.cmb_target_parts.count() > 0):
                sel_part = self.gui.cmb_target_parts.currentText()
                sel_variant = 0
            else:
                sel_part = self.gui.tgt_part_name.text()
                sel_variant = 0
            
            # 创建计算器
            self.gui.calculator = AeroCalculator(
                self.gui.current_config, 
                target_part=sel_part, 
                target_variant=sel_variant
            )
            
            # 获取 source part
            try:
                if (hasattr(self.gui, 'cmb_source_parts') and 
                    self.gui.cmb_source_parts.isVisible() and 
                    self.gui.cmb_source_parts.count() > 0):
                    src_sel = self.gui.cmb_source_parts.currentText()
                else:
                    src_sel = self.gui.src_part_name.text() if hasattr(self.gui, 'src_part_name') else 'Source'
            except Exception:
                src_sel = self.gui.src_part_name.text() if hasattr(self.gui, 'src_part_name') else 'Source'
            
            tgt_sel = sel_part or (self.gui.tgt_part_name.text() if hasattr(self.gui, 'tgt_part_name') else 'Target')
            
            self.gui.lbl_status.setText(f"当前配置: [{src_sel}] -> [{tgt_sel}]")
            try:
                self.gui.lbl_status.setProperty('state', 'loaded')
            except Exception:
                pass
            
            self.gui.statusBar().showMessage(f"配置已应用: {src_sel} -> {tgt_sel}")
            
            QMessageBox.information(
                self.gui, "成功", 
                f"配置已应用!\n{src_sel} -> {tgt_sel}\n现在可以进行计算了。"
            )
            
            try:
                self.gui.update_config_preview()
            except Exception:
                logger.debug("update_config_preview 失败", exc_info=True)
        
        except ValueError as e:
            QMessageBox.warning(self.gui, "输入错误", f"请检查数值输入:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self.gui, "应用失败", f"配置应用失败:\n{str(e)}")
