"""
配置管理模块 - 处理配置的加载、保存和应用
"""

# 为了处理延迟导入/循环依赖场景，允许在文件内进行受控的 import-outside-toplevel
# pylint: disable=import-outside-toplevel, reimported

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
        self._config_modified = False  # 追踪配置是否被修改
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
                logger.warning("ConfigManager 连接 ConfigPanel 信号失败: %s", e)

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

            # 解析为 ProjectData 与 ProjectConfigModel
            mm = getattr(self.gui, "model_manager", None)
            if mm is None:
                logger.warning("ModelManager 缺失，无法加载配置")
                return

            project = ProjectData.from_dict(data)
            mm.current_config = project
            # 同步到 gui 顶层属性，确保其他模块（如 BatchManager）能通过
            # `self.gui.current_config` 或 `self.gui.project_model` 访问到最新数据。
            try:
                self.gui.current_config = project
            except Exception:
                logger.debug("同步 current_config 到 gui 失败", exc_info=True)

            try:
                model = ProjectConfigModel.from_dict(data)
                mm.project_model = model
                try:
                    self.gui.project_model = model
                except Exception:
                    logger.debug("同步 project_model 到 gui 失败", exc_info=True)
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

            # 连接坐标系面板的修改信号
            try:
                self.gui.source_panel.valuesChanged.connect(
                    lambda: self.set_config_modified(True)
                )
                self.gui.target_panel.valuesChanged.connect(
                    lambda: self.set_config_modified(True)
                )
            except Exception:
                logger.debug("连接坐标系面板信号失败", exc_info=True)

            QMessageBox.information(self.gui, "成功", f"配置已加载:\n{fname}")
            self.gui.statusBar().showMessage(f"已加载: {fname}")

            # 仅加载配置：不再自动应用为“全局计算器”。
            # 批处理将基于每个文件选择的 source/target part 在后台按文件创建 AeroCalculator。

            # 重置修改标志
            self._config_modified = False
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
            logger.debug("填充 Target 表单失败: %s", e, exc_info=True)

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
            logger.debug("填充 Source 表单失败: %s", e, exc_info=True)

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
                mm = getattr(self.gui, "model_manager", None)
                if mm is None:
                    logger.warning("ModelManager 缺失，无法同步 ProjectConfigModel")
                else:
                    model = ProjectConfigModel.from_dict(data)
                    mm.project_model = model
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

                    # 重置修改标志
                    self._config_modified = False
                    return True
            except Exception:
                logger.debug("直接覆盖失败，使用另存为", exc_info=True)

            # 另存为
            fname, _ = QFileDialog.getSaveFileName(
                self.gui, "保存配置", "config.json", "JSON Files (*.json)"
            )
            if not fname:
                # 用户取消保存
                return False

            with open(fname, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            QMessageBox.information(self.gui, "成功", f"配置已保存:\n{fname}")
            self.gui.statusBar().showMessage(f"已保存: {fname}")
            try:
                from pathlib import Path

                self.signal_bus.configSaved.emit(Path(fname))
            except Exception:
                logger.debug("发射 configSaved 失败", exc_info=True)

            # 重置修改标志
            self._config_modified = False
            return True

        except ValueError as e:
            QMessageBox.warning(self.gui, "输入错误", f"请检查数值输入:\n{str(e)}")
            return False
        except Exception as e:
            QMessageBox.critical(self.gui, "保存失败", str(e))
            return False
        # 默认返回 False（若未显式返回 True 则视为未保存成功）
        return False

    def get_simple_payload_snapshot(self):
        """返回当前已加载配置的简化快照，格式与 `save_config` 使用的 data 保持一致。

        返回 None 表示没有可比较的已加载配置。
        """
        try:
            project = getattr(self.gui, "current_config", None) or getattr(
                self, "project_config_model", None
            )
            if project is None:
                return None

            # project 可能是 ProjectData 或 ProjectConfigModel；优先使用 ProjectData
            src_payload = None
            tgt_payload = None
            try:
                # 若为 ProjectData，使用 get_source_part/get_target_part
                src_names = (
                    list(project.source_parts.keys())
                    if hasattr(project, "source_parts")
                    else []
                )
                if src_names:
                    frame = project.get_source_part(src_names[0], 0)
                else:
                    frame = getattr(project, "source_config", None)
                if frame is not None:
                    src_payload = self._frame_to_payload(frame)
            except Exception:
                src_payload = None

            try:
                tgt_names = (
                    list(project.target_parts.keys())
                    if hasattr(project, "target_parts")
                    else []
                )
                if tgt_names:
                    frame = project.get_target_part(tgt_names[0], 0)
                else:
                    frame = None
                if frame is not None:
                    tgt_payload = self._frame_to_payload(frame)
            except Exception:
                tgt_payload = None

            if src_payload is None and tgt_payload is None:
                return None

            src_part = (
                {
                    "PartName": src_payload.get("PartName", "Global"),
                    "Variants": [src_payload],
                }
                if src_payload
                else {"PartName": "Global", "Variants": []}
            )
            tgt_part = (
                {
                    "PartName": tgt_payload.get("PartName", "Target"),
                    "Variants": [tgt_payload],
                }
                if tgt_payload
                else {"PartName": "Target", "Variants": []}
            )

            return {"Source": {"Parts": [src_part]}, "Target": {"Parts": [tgt_part]}}
        except Exception:
            logger.debug("生成配置快照失败", exc_info=True)
            return None

    def apply_config(self):
        """已移除：原用于将配置应用为全局 calculator 的逻辑。

        当前代码库已改为在批处理运行时按文件创建计算器，
        因此通过此方法“应用配置”的语义已废弃。

        为保持向后兼容，保留该方法签名但不执行任何变更操作，仅记录调试信息。
        """
        logger.debug("ConfigManager.apply_config 已被移除（no-op）")

    def is_config_modified(self):
        """返回配置是否被修改"""
        return self._config_modified

    def set_config_modified(self, modified: bool):
        """设置配置修改状态"""
        self._config_modified = modified

    def reset_config(self) -> None:
        """重置配置到初始状态（向后兼容旧接口）。

        清除加载的配置、项目模型，重置修改标志，并尝试清空界面面板显示。
        """
        try:
            self._last_loaded_config_path = None
            self._raw_project_dict = None
            self.project_config_model = None
            self._config_modified = False
            try:
                if hasattr(self.gui, "current_config"):
                    self.gui.current_config = None
            except Exception:
                pass
            try:
                if hasattr(self.gui, "project_model"):
                    self.gui.project_model = None
            except Exception:
                pass

            # 尝试清空 ConfigPanel 的面板内容
            try:
                panel = getattr(self.gui, "config_panel", None)
                if panel is not None:
                    try:
                        if hasattr(panel, "source_panel") and hasattr(
                            panel.source_panel, "apply_variant_payload"
                        ):
                            panel.source_panel.apply_variant_payload(
                                {
                                    "PartName": "",
                                    "CoordSystem": {
                                        "Orig": [0, 0, 0],
                                        "X": [1, 0, 0],
                                        "Y": [0, 1, 0],
                                        "Z": [0, 0, 1],
                                    },
                                    "MomentCenter": [0, 0, 0],
                                    "Cref": 1.0,
                                    "Bref": 1.0,
                                    "Sref": 10.0,
                                    "Q": 1000.0,
                                }
                            )
                        if hasattr(panel, "target_panel") and hasattr(
                            panel.target_panel, "apply_variant_payload"
                        ):
                            panel.target_panel.apply_variant_payload(
                                {
                                    "PartName": "",
                                    "CoordSystem": {
                                        "Orig": [0, 0, 0],
                                        "X": [1, 0, 0],
                                        "Y": [0, 1, 0],
                                        "Z": [0, 0, 1],
                                    },
                                    "MomentCenter": [0, 0, 0],
                                    "Cref": 1.0,
                                    "Bref": 1.0,
                                    "Sref": 10.0,
                                    "Q": 1000.0,
                                }
                            )
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            logger.debug("reset_config failed", exc_info=True)
