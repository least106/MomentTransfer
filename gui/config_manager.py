"""
配置管理模块 - 处理配置的加载、保存和应用
"""
import json
import logging
from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import QFileDialog, QMessageBox
from src.data_loader import ProjectData
from src.models import ProjectConfig
from src.models import ProjectConfigModel
from gui.signal_bus import SignalBus
from src.physics import AeroCalculator

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器 - 管理配置文件的加载、保存和应用"""
    
    def __init__(self, gui_instance, config_panel=None):
        """初始化配置管理器
        
        参数：
            gui_instance: IntegratedAeroGUI 实例，用于访问 UI 控件
            config_panel: ConfigPanel 实例（可选），用于连接请求信号
        """
        self.gui = gui_instance
        self._last_loaded_config_path = None
        self._raw_project_dict = None
        self.project_config: Optional[ProjectConfig] = None
        try:
            self.signal_bus = getattr(gui_instance, 'signal_bus', SignalBus.instance())
        except Exception:
            self.signal_bus = SignalBus.instance()
        
        # 如果提供了 config_panel，连接请求信号
        if config_panel:
            try:
                config_panel.loadRequested.connect(self.load_config)
                config_panel.saveRequested.connect(self.save_config)
                config_panel.applyRequested.connect(self.apply_config)
                logger.debug("ConfigManager 已连接 ConfigPanel 请求信号")
            except Exception as e:
                logger.warning(f"ConfigManager 连接 ConfigPanel 信号失败: {e}")

    def _frame_to_payload(self, frame):
        """将 ProjectData 帧转换为面板可用的 payload。"""
        cs = frame.coord_system
        mc = frame.moment_center or [0.0, 0.0, 0.0]
        return {
            "PartName": frame.part_name,
            "CoordSystem": {
                "Orig": [float(cs.origin[0]), float(cs.origin[1]), float(cs.origin[2])],
                "X": [float(cs.x_axis[0]), float(cs.x_axis[1]), float(cs.x_axis[2])],
                "Y": [float(cs.y_axis[0]), float(cs.y_axis[1]), float(cs.y_axis[2])],
                "Z": [float(cs.z_axis[0]), float(cs.z_axis[1]), float(cs.z_axis[2])],
            },
            "MomentCenter": [float(mc[0]), float(mc[1]), float(mc[2])],
            "Cref": float(frame.c_ref or 1.0),
            "Bref": float(frame.b_ref or 1.0),
            "Sref": float(frame.s_ref or 10.0),
            "Q": float(frame.q or 1000.0),
        }

    def _sync_payload_to_legacy(self, payload: dict, side: str):
        """将面板数据同步到旧的隐藏控件，保持兼容。"""
        prefix = "src" if side == "source" or side == "src" else "tgt"
        coord = payload.get("CoordSystem", {})
        mc = payload.get("MomentCenter", [0.0, 0.0, 0.0])

        def _set_spin(name, idx, arr):
            spin = getattr(self.gui, name, None)
            try:
                if spin is not None:
                    spin.setValue(float(arr[idx]))
            except Exception:
                pass

        _set_spin(f"{prefix}_ox", 0, coord.get("Orig", [0, 0, 0]))
        _set_spin(f"{prefix}_oy", 1, coord.get("Orig", [0, 0, 0]))
        _set_spin(f"{prefix}_oz", 2, coord.get("Orig", [0, 0, 0]))

        _set_spin(f"{prefix}_xx", 0, coord.get("X", [1, 0, 0]))
        _set_spin(f"{prefix}_xy", 1, coord.get("X", [1, 0, 0]))
        _set_spin(f"{prefix}_xz", 2, coord.get("X", [1, 0, 0]))

        _set_spin(f"{prefix}_yx", 0, coord.get("Y", [0, 1, 0]))
        _set_spin(f"{prefix}_yy", 1, coord.get("Y", [0, 1, 0]))
        _set_spin(f"{prefix}_yz", 2, coord.get("Y", [0, 1, 0]))

        _set_spin(f"{prefix}_zx", 0, coord.get("Z", [0, 0, 1]))
        _set_spin(f"{prefix}_zy", 1, coord.get("Z", [0, 0, 1]))
        _set_spin(f"{prefix}_zz", 2, coord.get("Z", [0, 0, 1]))

        _set_spin(f"{prefix}_mcx", 0, mc)
        _set_spin(f"{prefix}_mcy", 1, mc)
        _set_spin(f"{prefix}_mcz", 2, mc)

        try:
            getattr(self.gui, f"{prefix}_cref").setText(str(payload.get("Cref", 1.0)))
            getattr(self.gui, f"{prefix}_bref").setText(str(payload.get("Bref", 1.0)))
            getattr(self.gui, f"{prefix}_sref").setText(str(payload.get("Sref", 10.0)))
            getattr(self.gui, f"{prefix}_q").setText(str(payload.get("Q", 1000.0)))
        except Exception:
            pass
    
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
            try:
                self.project_config = ProjectConfig.from_dict(data)
                setattr(self.gui, "project_config", self.project_config)
            except Exception:
                logger.debug("ProjectConfig 解析失败或同步失败", exc_info=True)
            # 新模型：ProjectConfigModel
            try:
                model = ProjectConfigModel.from_dict(data)
                setattr(self.gui, 'project_model', model)
                try:
                    self.signal_bus.configLoaded.emit(model)
                except Exception:
                    logger.debug("发射 configLoaded 失败", exc_info=True)
            except Exception:
                logger.debug("ProjectConfigModel 解析失败", exc_info=True)
            
            # 记录加载路径
            self._last_loaded_config_path = Path(fname)
            
            # 填充 Target 下拉列表
            self.gui.cmb_target_parts.clear()
            for part in project.target_parts.keys():
                self.gui.cmb_target_parts.addItem(part)
                try:
                    self.gui.target_panel.part_selector.addItem(part)
                except Exception:
                    pass
            
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
                    try:
                        self.gui.source_panel.part_selector.addItem(part)
                    except Exception:
                        pass
                
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
            payload = self._frame_to_payload(frame)
            try:
                self.gui.target_panel.apply_variant_payload(payload)
            except Exception:
                logger.debug("填充 Target 面板失败", exc_info=True)

            # 兼容旧控件
            self._sync_payload_to_legacy(payload, "tgt")
        
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
            payload = self._frame_to_payload(sframe)
            try:
                self.gui.source_panel.apply_variant_payload(payload)
            except Exception:
                logger.debug("填充 Source 面板失败", exc_info=True)

            self._sync_payload_to_legacy(payload, "src")
        
        except Exception as e:
            logger.debug(f"填充 Source 表单失败: {e}", exc_info=True)
    
    def save_config(self):
        """保存配置到 JSON 文件"""
        try:
            # 直接从面板读取 Variant 数据
            src_variant = self.gui.source_panel.to_variant_payload()
            tgt_variant = self.gui.target_panel.to_variant_payload()

            src_part = {"PartName": src_variant.get("PartName", "Global"), "Variants": [src_variant]}
            tgt_part = {"PartName": tgt_variant.get("PartName", "Target"), "Variants": [tgt_variant]}

            # 保持旧控件同步（兼容历史逻辑）
            self._sync_payload_to_legacy(src_variant, "src")
            self._sync_payload_to_legacy(tgt_variant, "tgt")

            data = {
                "Source": {"Parts": [src_part]},
                "Target": {"Parts": [tgt_part]}
            }

            try:
                self.project_config = ProjectConfig.from_dict(data)
                setattr(self.gui, "project_config", self.project_config)
            except Exception:
                logger.debug("保存前 ProjectConfig 同步失败", exc_info=True)
            # 同步新模型
            try:
                model = ProjectConfigModel.from_dict(data)
                setattr(self.gui, 'project_model', model)
            except Exception:
                logger.debug("保存前 ProjectConfigModel 同步失败", exc_info=True)
            
            # 优先覆盖上次加载的文件
            try:
                if self._last_loaded_config_path:
                    with open(self._last_loaded_config_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                    QMessageBox.information(self.gui, "成功", f"配置已覆盖保存:\n{self._last_loaded_config_path}")
                    self.gui.statusBar().showMessage(f"已保存: {self._last_loaded_config_path}")
                    try:
                        self.signal_bus.configSaved.emit(self._last_loaded_config_path)
                    except Exception:
                        logger.debug("发射 configSaved 失败", exc_info=True)
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
            try:
                from pathlib import Path
                self.signal_bus.configSaved.emit(Path(fname))
            except Exception:
                logger.debug("发射 configSaved 失败", exc_info=True)
        
        except ValueError as e:
            QMessageBox.warning(self.gui, "输入错误", f"请检查数值输入:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self.gui, "保存失败", str(e))
    
    def apply_config(self):
        """应用当前配置到计算器"""
        try:
            # 使用面板导出的数据，减少重复读取逻辑
            src_variant = self.gui.source_panel.to_variant_payload()
            tgt_variant = self.gui.target_panel.to_variant_payload()

            self._sync_payload_to_legacy(src_variant, "src")
            self._sync_payload_to_legacy(tgt_variant, "tgt")

            src_part = {"PartName": src_variant.get("PartName", "Global"), "Variants": [src_variant]}
            tgt_part = {"PartName": tgt_variant.get("PartName", "Target"), "Variants": [tgt_variant]}

            data = {
                "Source": {"Parts": [src_part]},
                "Target": {"Parts": [tgt_part]}
            }
            
            # 解析为 ProjectData
            self.gui.current_config = ProjectData.from_dict(data)

            try:
                self.project_config = ProjectConfig.from_dict(data)
                setattr(self.gui, "project_config", self.project_config)
            except Exception:
                logger.debug("应用前 ProjectConfig 同步失败", exc_info=True)
            
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
            # 发射 SignalBus 事件
            try:
                self.signal_bus.configApplied.emit()
            except Exception:
                logger.debug("发射 configApplied 失败", exc_info=True)
        
        except ValueError as e:
            QMessageBox.warning(self.gui, "输入错误", f"请检查数值输入:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self.gui, "应用失败", f"配置应用失败:\n{str(e)}")
