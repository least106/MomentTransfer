"""
配置管理模块 - 处理配置的加载、保存和应用
"""

import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QFileDialog, QMessageBox

from gui.signal_bus import SignalBus
from src.data_loader import ProjectData
from src.models import ProjectConfigModel

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
        # 统一使用 ProjectConfigModel
        self.project_config_model: Optional[ProjectConfigModel] = None
        try:
            self.signal_bus = getattr(gui_instance, "signal_bus", SignalBus.instance())
        except Exception:
            self.signal_bus = SignalBus.instance()

        # 如果提供了 config_panel，连接请求信号
        if config_panel:
            try:
                config_panel.loadRequested.connect(self.load_config)
                config_panel.saveRequested.connect(self.save_config)
                # 已移除：config_panel 不再发出 applyRequested（应用配置）信号，
                # 配置的“应用”语义已变更为直接保存/更新模型并由批处理按需创建计算器。
                logger.debug("ConfigManager 已连接 ConfigPanel 请求信号")
            except Exception as e:
                logger.warning(f"ConfigManager 连接 ConfigPanel 信号失败: {e}")

    def _frame_to_payload(self, frame):
        """将 ProjectData 帧转换为面板可用的 payload。"""
        cs = frame.coord_system
        # 处理 moment_center：可能是数组、列表或 None（避免数组真值判断错误）
        mc = frame.moment_center
        if mc is None:
            mc = [0.0, 0.0, 0.0]
        else:
            try:
                mc = (
                    [float(mc[0]), float(mc[1]), float(mc[2])]
                    if hasattr(mc, "__getitem__")
                    else [0.0, 0.0, 0.0]
                )
            except Exception:
                mc = [0.0, 0.0, 0.0]

        return {
            "PartName": frame.part_name,
            "CoordSystem": {
                "Orig": [
                    float(cs.origin[0]),
                    float(cs.origin[1]),
                    float(cs.origin[2]),
                ],
                "X": [
                    float(cs.x_axis[0]),
                    float(cs.x_axis[1]),
                    float(cs.x_axis[2]),
                ],
                "Y": [
                    float(cs.y_axis[0]),
                    float(cs.y_axis[1]),
                    float(cs.y_axis[2]),
                ],
                "Z": [
                    float(cs.z_axis[0]),
                    float(cs.z_axis[1]),
                    float(cs.z_axis[2]),
                ],
            },
            "MomentCenter": mc,
            "Cref": float(frame.c_ref or 1.0),
            "Bref": float(frame.b_ref or 1.0),
            "Sref": float(frame.s_ref or 10.0),
            "Q": float(frame.q or 1000.0),
        }

    def _sync_payload_to_legacy(self, payload: dict, side: str):
        """同步必要字段到面板输入（旧隐藏控件已移除）。"""
        prefix = "src" if side == "source" or side == "src" else "tgt"
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
                self.gui, "打开配置", ".", "JSON Files (*.json)"
            )
            if not fname:
                return

            with open(fname, "r", encoding="utf-8") as f:
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
            # 新模型：ProjectConfigModel
            try:
                model = ProjectConfigModel.from_dict(data)
                setattr(self.gui, "project_model", model)
                try:
                    self.signal_bus.configLoaded.emit(model)
                except Exception:
                    logger.debug("发射 configLoaded 失败", exc_info=True)
            except Exception:
                logger.debug("ProjectConfigModel 解析失败", exc_info=True)

            # 记录加载路径
            self._last_loaded_config_path = Path(fname)

            # 填充 Target 下拉列表（统一通过面板接口，避免重复添加）
            self.gui.target_panel.part_selector.clear()
            target_part_names = list(project.target_parts.keys())
            for part in target_part_names:
                self.gui.target_panel.part_selector.addItem(part)
            try:
                self.gui.target_panel.update_part_list(target_part_names)
            except Exception:
                logger.debug("target_panel.update_part_list 失败", exc_info=True)

            if self.gui.target_panel.part_selector.count() > 0:
                self.gui.target_panel.part_selector.setVisible(True)
                first = (
                    self.gui.target_panel.part_selector.currentText()
                    or self.gui.target_panel.part_selector.itemText(0)
                )
                try:
                    self.gui.target_panel._current_part_name = first
                except Exception:
                    pass
                # 同步面板当前选择
                try:
                    self.gui.target_panel.part_selector.blockSignals(True)
                    self.gui.target_panel.part_selector.setCurrentText(first)
                finally:
                    try:
                        self.gui.target_panel.part_selector.blockSignals(False)
                    except Exception:
                        pass

            # 填充 Source 下拉列表（统一通过面板接口，避免重复添加）
            try:
                self.gui.source_panel.part_selector.clear()
                source_part_names = list(project.source_parts.keys())
                for part in source_part_names:
                    self.gui.source_panel.part_selector.addItem(part)
                try:
                    self.gui.source_panel.update_part_list(source_part_names)
                except Exception:
                    logger.debug("source_panel.update_part_list 失败", exc_info=True)

                if self.gui.source_panel.part_selector.count() > 0:
                    self.gui.source_panel.part_selector.setVisible(True)
                    firsts = (
                        self.gui.source_panel.part_selector.currentText()
                        or self.gui.source_panel.part_selector.itemText(0)
                    )
                    try:
                        self.gui.source_panel._current_part_name = firsts
                    except Exception:
                        pass
                    # 同步面板当前选择
                    try:
                        self.gui.source_panel.part_selector.blockSignals(True)
                        self.gui.source_panel.part_selector.setCurrentText(firsts)
                    finally:
                        try:
                            self.gui.source_panel.part_selector.blockSignals(False)
                        except Exception:
                            pass
            except Exception:
                logger.debug("source_parts 填充失败", exc_info=True)

            # 填充 Target 表单
            self._populate_target_form(project)

            # 填充 Source 表单
            self._populate_source_form(project)

            QMessageBox.information(self.gui, "成功", f"配置已加载:\n{fname}")
            self.gui.statusBar().showMessage(f"已加载: {fname}")

            # 仅加载配置：不再自动应用为“全局计算器”。
            # 批处理将基于每个文件选择的 source/target part 在后台按文件创建 AeroCalculator。

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
            sel_part = (
                self.gui.target_panel.part_selector.currentText()
                or self.gui.target_panel.part_selector.itemText(0)
            )
            sel_variant = 0
            frame = project.get_target_part(sel_part, sel_variant)
            payload = self._frame_to_payload(frame)
            try:
                self.gui.target_panel.apply_variant_payload(payload)
            except Exception:
                logger.debug("填充 Target 面板失败", exc_info=True)

            # 同步到面板已完成，无需同步隐藏控件

        except Exception as e:
            logger.debug(f"填充 Target 表单失败: {e}", exc_info=True)

    def _populate_source_form(self, project: ProjectData):
        """填充 Source 坐标系表单"""
        try:
            if (
                self.gui.source_panel.part_selector.count() > 0
                and self.gui.source_panel.part_selector.isVisible()
            ):
                s_part = (
                    self.gui.source_panel.part_selector.currentText()
                    or self.gui.source_panel.part_selector.itemText(0)
                )
                s_variant = 0
                sframe = project.get_source_part(s_part, s_variant)
            else:
                sframe = project.source_config
            payload = self._frame_to_payload(sframe)
            try:
                self.gui.source_panel.apply_variant_payload(payload)
            except Exception:
                logger.debug("填充 Source 面板失败", exc_info=True)

            # 同步到面板已完成，无需同步隐藏控件

        except Exception as e:
            logger.debug(f"填充 Source 表单失败: {e}", exc_info=True)

    def save_config(self):
        """保存配置到 JSON 文件"""
        try:
            # 直接从面板读取 Variant 数据
            src_variant = self.gui.source_panel.to_variant_payload()
            tgt_variant = self.gui.target_panel.to_variant_payload()

            src_part = {
                "PartName": src_variant.get("PartName", "Global"),
                "Variants": [src_variant],
            }
            tgt_part = {
                "PartName": tgt_variant.get("PartName", "Target"),
                "Variants": [tgt_variant],
            }

            # 直接使用面板数据，无需同步隐藏控件

            data = {
                "Source": {"Parts": [src_part]},
                "Target": {"Parts": [tgt_part]},
            }

            # 同步新模型
            try:
                model = ProjectConfigModel.from_dict(data)
                setattr(self.gui, "project_model", model)
            except Exception:
                logger.debug("保存前 ProjectConfigModel 同步失败", exc_info=True)

            # 优先覆盖上次加载的文件
            try:
                if self._last_loaded_config_path:
                    with open(
                        self._last_loaded_config_path, "w", encoding="utf-8"
                    ) as f:
                        json.dump(data, f, indent=2)
                    QMessageBox.information(
                        self.gui,
                        "成功",
                        f"配置已覆盖保存:\n{self._last_loaded_config_path}",
                    )
                    self.gui.statusBar().showMessage(
                        f"已保存: {self._last_loaded_config_path}"
                    )
                    try:
                        self.signal_bus.configSaved.emit(self._last_loaded_config_path)
                    except Exception:
                        logger.debug("发射 configSaved 失败", exc_info=True)
                    return
            except Exception:
                logger.debug("直接覆盖失败，使用另存为", exc_info=True)

            # 另存为
            fname, _ = QFileDialog.getSaveFileName(
                self.gui, "保存配置", "config.json", "JSON Files (*.json)"
            )
            if not fname:
                return

            with open(fname, "w", encoding="utf-8") as f:
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
            # 关键：apply_config 不能把多 Part 配置“缩成”单一 Part。
            # 否则用户切换下拉时会找不到其它 Part 的变体。

            # 先把当前面板上的编辑保存回模型（仅更新当前选择的 Part，不影响其它 Part）
            try:
                pm = getattr(self.gui, "part_manager", None)
                if pm:
                    pm.save_current_source_part()
                    pm.save_current_target_part()
            except Exception:
                logger.debug("apply_config: 保存当前 Part 失败", exc_info=True)

            # 以完整 ProjectConfigModel 生成 ProjectData
            data = None
            try:
                model = getattr(self.gui, "project_model", None)
                if model:
                    data = model.to_dict()
            except Exception:
                logger.debug("apply_config: 从 project_model 导出失败", exc_info=True)

            if data is None:
                # 回退：仅当没有模型时，才用面板构造最小配置
                src_variant = self.gui.source_panel.to_variant_payload()
                tgt_variant = self.gui.target_panel.to_variant_payload()
                src_part = {
                    "PartName": src_variant.get("PartName", "Global"),
                    "Variants": [src_variant],
                }
                tgt_part = {
                    "PartName": tgt_variant.get("PartName", "Target"),
                    "Variants": [tgt_variant],
                }
                data = {
                    "Source": {"Parts": [src_part]},
                    "Target": {"Parts": [tgt_part]},
                }
                try:
                    setattr(
                        self.gui,
                        "project_model",
                        ProjectConfigModel.from_dict(data),
                    )
                except Exception:
                    logger.debug(
                        "apply_config: 回退构造 ProjectConfigModel 失败",
                        exc_info=True,
                    )

            self.gui.current_config = ProjectData.from_dict(data)

            # 不再创建“全局 calculator”，避免批处理对所有文件套用同一组 source/target。
            # 现在的语义是：用户在文件列表为每个文件（或每个 source part）选择 target，
            # 批处理线程会按文件动态创建 AeroCalculator。
            try:
                self.gui.calculator = None
            except Exception:
                pass

            try:
                self.gui.statusBar().showMessage(
                    "配置已更新：请在文件列表为每个文件选择 source/target"
                )
            except Exception:
                pass

            try:
                QMessageBox.information(
                    self.gui,
                    "成功",
                    "配置已更新！\n请在文件列表为每个文件选择 source/target 后再运行批处理。",
                )
            except Exception:
                pass

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
