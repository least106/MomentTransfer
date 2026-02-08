"""
配置管理模块 - 处理配置的加载、保存和应用
"""

# 为了处理延迟导入/循环依赖场景，允许在文件内进行受控的 import-outside-toplevel
# pylint: disable=import-outside-toplevel, reimported

import json
import logging
import os
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QFileDialog, QMessageBox

from gui.signal_bus import ConfigLoadedEvent, SignalBus
from gui.delay_scheduler import DelayScheduler
from gui.status_message_queue import MessagePriority
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
        self._values_changed_connected = False  # 追踪是否已连接面板信号
        self._values_changed_panels = []  # 已连接的面板列表
        self._loaded_snapshot = None  # 加载时的配置快照
        self._values_changed_connected = False
        self._values_changed_panels = []
        self._loaded_snapshot = None
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
        # 连接 SignalBus Part 修改信号以追踪多路径配置修改
        try:
            self.signal_bus.partAdded.connect(self._on_part_list_changed)
            self.signal_bus.partRemoved.connect(self._on_part_list_changed)
            logger.debug("ConfigManager 已连接 SignalBus Part 修改信号")
        except Exception as e:
            logger.warning("ConfigManager 连接 Part 修改信号失败: %s", e)

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
        prefix = "src" if side in ("source", "src") else "tgt"
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

            try:
                with open(fname, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except FileNotFoundError:
                from gui.managers import report_user_error
                report_user_error(self.gui, "文件不存在", f"无法找到配置文件：{fname}")
                return
            except json.JSONDecodeError as e:
                from gui.managers import report_user_error
                report_user_error(self.gui, "配置文件格式错误", 
                                f"JSON 解析失败：{str(e)}", details=str(e))
                return
            except Exception as e:
                from gui.managers import report_user_error
                report_user_error(self.gui, "读取配置失败", 
                                f"无法读取配置文件", details=str(e))
                return

            # 保存原始字典以便编辑和写回，并同步到 gui 供 PartManager/_save_current_* 使用
            self._raw_project_dict = data
            try:
                self.gui._raw_project_dict = data
            except Exception:
                logger.debug("同步 _raw_project_dict 到 gui 失败", exc_info=True)

            # 解析为 ProjectData 与 ProjectConfigModel
            mm = getattr(self.gui, "model_manager", None)
            if mm is None:
                from gui.managers import report_user_error
                report_user_error(self.gui, "初始化错误", 
                                "ModelManager 未初始化，无法加载配置")
                logger.error("ModelManager 缺失，无法加载配置")
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
                    # 为了避免在部分接收方尚未连接时发生同步乱序，使用 DelayScheduler
                    # 将 configLoaded 的发射延迟到事件循环下一个时机（100ms），
                    # 以确保所有面板/管理器完成初始化并连接信号。
                    event = ConfigLoadedEvent(
                        model=model,
                        path=Path(fname) if fname else None,
                        source="config_manager",
                    )

                    def _emit_config_loaded():
                        try:
                            self.signal_bus.configLoaded.emit(event)
                        except Exception:
                            logger.debug("发射 configLoaded 失败", exc_info=True)

                    # 100ms 的短延迟通常足以让 UI 完成必要的连接。
                    DelayScheduler.instance().schedule(
                        "config_manager.emit_config_loaded", 100, _emit_config_loaded, replace=True
                    )
                except Exception:
                    logger.debug("调度 configLoaded 发射失败", exc_info=True)
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
                src_panel = getattr(self.gui, "source_panel", None)
                tgt_panel = getattr(self.gui, "target_panel", None)
                cached_panels = getattr(self, "_values_changed_panels", None)
                if cached_panels != (src_panel, tgt_panel):
                    self._values_changed_connected = False
                    self._values_changed_panels = (src_panel, tgt_panel)

                if not getattr(self, "_values_changed_connected", False):
                    if src_panel is not None:
                        src_panel.valuesChanged.connect(self._on_panel_values_changed)
                    if tgt_panel is not None:
                        tgt_panel.valuesChanged.connect(self._on_panel_values_changed)
                    self._values_changed_connected = True
            except Exception:
                logger.debug("连接坐标系面板信号失败", exc_info=True)

            # UX：使用统一状态消息通道，显示详细的加载信息
            try:
                # 统计 Source 和 Target Parts 数量
                source_count = len(source_part_names) if source_part_names else 0
                target_count = len(target_part_names) if target_part_names else 0
                
                # 构建详细的加载消息
                parts_info = f"{source_count} 个 Source Parts，{target_count} 个 Target Parts"
                config_name = Path(fname).name if fname else "配置"
                
                self.signal_bus.statusMessage.emit(
                    f"✓ 已加载配置：{config_name} | {parts_info}",
                    8000,  # 显示 8 秒，让用户有时间看到详细信息
                    MessagePriority.MEDIUM,  # 使用中等优先级确保用户看到
                )
            except Exception:
                logger.debug("发送加载状态提示失败（非致命）", exc_info=True)
            # 配置加载后触发文件状态刷新，让用户看到配置生效
            try:
                # 使用 SignalBus 通知其他模块配置已刷新
                # BatchManager 会监听此信号并刷新文件状态显示
                logger.info("配置加载完成，通知刷新文件状态")
                def _delayed_refresh():
                    try:
                        # 通过状态栏告知用户文件状态正在更新
                        self.signal_bus.statusMessage.emit(
                            "正在更新文件验证状态...",
                            2000,
                            MessagePriority.LOW,
                        )
                        # 等待 SignalBus 处理完 configLoaded 信号
                        # BatchManager 会监听该信号并自动调用 refresh_file_statuses()
                    except Exception as e:
                        logger.debug(f"延迟刷新状态提示失败: {e}", exc_info=True)
                DelayScheduler.instance().schedule(
                    "config_manager.delayed_refresh",
                    100,
                    _delayed_refresh,
                    replace=True,
                )
            except Exception as e:
                logger.debug(f"配置加载后刷新失败: {e}", exc_info=True)
            # 仅加载配置：不再自动应用为“全局计算器”。
            # 批处理将基于每个文件选择的 source/target part 在后台按文件创建 AeroCalculator。

            # 重置修改标志
            # 保存加载时的完整快照（包含 Part 列表）作为基线，供追踪是否已被用户修改
            try:
                self._loaded_snapshot = self.get_full_config_snapshot()
            except Exception:
                self._loaded_snapshot = None
            self._config_modified = False

            # 清除旧配置可能存留的批处理多选列表
            # 这避免用户用新配置加载后仍使用旧配置对应的文件选择
            self._clear_batch_file_selection()
        except Exception as e:
            logger.error("加载配置失败", exc_info=True)
            from gui.managers import report_user_error
            report_user_error(
                self.gui, 
                "加载失败", 
                "无法加载配置文件，请检查文件是否正确",
                details=str(e)
            )

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
        """保存配置到 JSON 文件

        改进的保存逻辑：
        1. 保存前备份状态
        2. 保存失败时明确报错，不静默进入另存为
        3. 仅在实际写入成功后才清除 _config_modified 标志
        4. 区分用户取消和保存失败

        Returns:
            bool: True 表示保存成功，False 表示保存失败或用户取消
        """
        # 保存前备份 ModelManager 状态（用于回滚）
        original_model = None
        try:
            mm = getattr(self.gui, "model_manager", None)
            if mm and hasattr(mm, "project_model"):
                # 备份当前模型（深拷贝）
                import copy

                original_model = copy.deepcopy(mm.project_model)
        except Exception:
            logger.debug("无法备份 ModelManager 状态", exc_info=True)

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

            # 同步新模型（保存前预先更新，失败时回滚）
            try:
                mm = getattr(self.gui, "model_manager", None)
                if mm is None:
                    logger.warning("ModelManager 缺失，无法同步 ProjectConfigModel")
                else:
                    model = ProjectConfigModel.from_dict(data)
                    mm.project_model = model
            except Exception as model_err:
                logger.error(
                    "保存前 ProjectConfigModel 同步失败: %s", model_err, exc_info=True
                )
                # 模型构建失败，不应该继续保存
                QMessageBox.critical(
                    self.gui,
                    "配置错误",
                    f"配置数据格式错误，无法保存:\n{model_err}",
                )
                return False

            # 优先覆盖上次加载的文件
            save_successful = False
            saved_path = None

            if self._last_loaded_config_path:
                try:
                    # 原子写入：先写临时文件，成功后再替换
                    import tempfile
                    import shutil
                    from pathlib import Path

                    target_path = Path(self._last_loaded_config_path)
                    temp_fd, temp_path = tempfile.mkstemp(
                        suffix=".json",
                        prefix="config_",
                        dir=target_path.parent,
                        text=True,
                    )
                    try:
                        # 写入临时文件
                        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)

                        # 替换原文件（原子操作）
                        shutil.move(temp_path, target_path)

                        save_successful = True
                        saved_path = target_path
                        logger.info("配置已成功保存到: %s", target_path)

                    except Exception as write_err:
                        # 清理临时文件
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception:
                            pass
                        raise write_err

                except PermissionError as perm_err:
                    # 权限错误：明确报错，询问用户是否另存为
                    logger.error(
                        "无法覆盖配置文件（权限不足）: %s", perm_err, exc_info=True
                    )

                    # 回滚模型状态
                    if original_model and mm:
                        try:
                            mm.project_model = original_model
                            logger.info("已回滚 ProjectConfigModel 到保存前状态")
                        except Exception:
                            logger.debug("回滚 ModelManager 失败", exc_info=True)

                    reply = QMessageBox.question(
                        self.gui,
                        "保存失败",
                        f"无法覆盖配置文件（权限不足）:\n{self._last_loaded_config_path}\n\n"
                        f"是否另存为到其他位置？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes,
                    )
                    if reply != QMessageBox.Yes:
                        # 用户拒绝另存为
                        return False
                    # 继续执行另存为逻辑（下方）

                except OSError as os_err:
                    # 其他文件系统错误：明确报错
                    logger.error(
                        "配置文件保存失败（文件系统错误）: %s", os_err, exc_info=True
                    )

                    # 回滚模型状态
                    if original_model and mm:
                        try:
                            mm.project_model = original_model
                            logger.info("已回滚 ProjectConfigModel 到保存前状态")
                        except Exception:
                            logger.debug("回滚 ModelManager 失败", exc_info=True)

                    QMessageBox.critical(
                        self.gui,
                        "保存失败",
                        f"无法保存配置文件:\n{self._last_loaded_config_path}\n\n"
                        f"错误: {os_err}",
                    )
                    return False

                except Exception as save_err:
                    # 其他未预期的错误
                    logger.error(
                        "配置保存失败（未知错误）: %s", save_err, exc_info=True
                    )

                    # 回滚模型状态
                    if original_model and mm:
                        try:
                            mm.project_model = original_model
                            logger.info("已回滚 ProjectConfigModel 到保存前状态")
                        except Exception:
                            logger.debug("回滚 ModelManager 失败", exc_info=True)

                    QMessageBox.critical(
                        self.gui,
                        "保存失败",
                        f"保存配置时发生错误:\n{save_err}",
                    )
                    return False

            # 如果没有上次加载路径，或覆盖失败后用户选择另存为
            if not save_successful:
                # 另存为
                fname, _ = QFileDialog.getSaveFileName(
                    self.gui, "保存配置", "config.json", "JSON Files (*.json)"
                )
                if not fname:
                    # 用户取消保存 - 回滚模型
                    if original_model and mm:
                        try:
                            mm.project_model = original_model
                            logger.info("用户取消保存，已回滚 ProjectConfigModel")
                        except Exception:
                            logger.debug("回滚 ModelManager 失败", exc_info=True)
                    return False

                try:
                    with open(fname, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)

                    save_successful = True
                    saved_path = Path(fname)
                    logger.info("配置已另存为: %s", fname)

                except Exception as save_err:
                    # 另存为失败 - 回滚并报错
                    logger.error("另存为失败: %s", save_err, exc_info=True)

                    if original_model and mm:
                        try:
                            mm.project_model = original_model
                            logger.info("另存为失败，已回滚 ProjectConfigModel")
                        except Exception:
                            logger.debug("回滚 ModelManager 失败", exc_info=True)

                    QMessageBox.critical(
                        self.gui,
                        "保存失败",
                        f"无法保存配置文件到:\n{fname}\n\n错误: {save_err}",
                    )
                    return False

            # === 保存成功：更新状态和显示提示 ===
            if save_successful and saved_path:
                QMessageBox.information(
                    self.gui,
                    "成功",
                    f"配置已保存:\n{saved_path}",
                )
                try:
                    from gui.status_message_queue import MessagePriority

                    self.signal_bus.statusMessage.emit(
                        f"已保存: {saved_path}",
                        5000,
                        MessagePriority.MEDIUM,
                    )
                except Exception:
                    logger.debug("发送保存状态消息失败（非致命）", exc_info=True)
                try:
                    self.signal_bus.configSaved.emit(saved_path)
                except Exception:
                    logger.debug("发射 configSaved 失败", exc_info=True)

                # 仅在保存成功后才重置修改标志
                self._config_modified = False
                try:
                    if hasattr(self.gui, "ui_state_manager") and getattr(
                        self.gui, "ui_state_manager"
                    ):
                        try:
                            self.gui.ui_state_manager.clear_user_modified()
                        except Exception:
                            logger.debug(
                                "通过 UIStateManager 清理操作状态失败",
                                exc_info=True,
                            )
                    else:
                        self.gui.operation_performed = False
                except Exception:
                    logger.debug("清理操作状态失败（非致命）", exc_info=True)

                return True
            else:
                # 未保存成功（逻辑不应到达这里）
                logger.error("保存逻辑错误：未保存成功但未返回 False")
                return False

        except ValueError as e:
            # 数值输入错误 - 回滚
            logger.error("配置数据验证失败: %s", e, exc_info=True)
            if original_model and mm:
                try:
                    mm.project_model = original_model
                    logger.info("验证失败，已回滚 ProjectConfigModel")
                except Exception:
                    logger.debug("回滚 ModelManager 失败", exc_info=True)

            QMessageBox.warning(self.gui, "输入错误", f"请检查数值输入:\n{str(e)}")
            return False

        except Exception as e:
            # 其他未捕获的异常 - 回滚并报错
            logger.error("配置保存失败（未预期的异常）: %s", e, exc_info=True)
            if original_model and mm:
                try:
                    mm.project_model = original_model
                    logger.info("保存失败，已回滚 ProjectConfigModel")
                except Exception:
                    logger.debug("回滚 ModelManager 失败", exc_info=True)

            QMessageBox.critical(self.gui, "保存失败", f"保存配置时发生错误:\n{e}")
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

            return {
                "Source": {"Parts": [src_part]},
                "Target": {"Parts": [tgt_part]},
            }
        except Exception:
            logger.debug("生成配置快照失败", exc_info=True)
            return None

    def get_full_config_snapshot(self):
        """获取包含完整 Part 列表的配置快照，用于追踪多路径修改。

        返回格式: {
            "source_part_names": [...],  # Source Part 列表
            "target_part_names": [...],  # Target Part 列表
            "payload": {...}             # 坐标系等其他配置（来自 get_simple_payload_snapshot）
        }
        """
        try:
            project = getattr(self.gui, "current_config", None) or getattr(
                self, "project_config_model", None
            )
            if project is None:
                return None

            # 提取 Source 和 Target 的 Part 名称列表
            source_names = []
            target_names = []
            try:
                if hasattr(project, "source_parts"):
                    source_names = sorted(list(project.source_parts.keys()))
            except Exception:
                logger.debug("无法获取 Source Part 列表", exc_info=True)

            try:
                if hasattr(project, "target_parts"):
                    target_names = sorted(list(project.target_parts.keys()))
            except Exception:
                logger.debug("无法获取 Target Part 列表", exc_info=True)

            # 获取坐标系等其他配置
            payload = self.get_simple_payload_snapshot()

            return {
                "source_part_names": source_names,
                "target_part_names": target_names,
                "payload": payload,
            }
        except Exception:
            logger.debug("生成完整配置快照失败", exc_info=True)
            return None

    def _part_list_changed_since_load(self) -> bool:
        """检查自加载后 Part 列表是否有变化。"""
        try:
            if not self._loaded_snapshot:
                return False

            current = self.get_full_config_snapshot()
            if current is None:
                return False

            current_src = current.get("source_part_names", [])
            current_tgt = current.get("target_part_names", [])

            loaded_src = self._loaded_snapshot.get("source_part_names", [])
            loaded_tgt = self._loaded_snapshot.get("target_part_names", [])

            # 比较 Part 列表
            return current_src != loaded_src or current_tgt != loaded_tgt
        except Exception:
            logger.debug("检查 Part 列表变化失败", exc_info=True)
            return False

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
        old_state = self._config_modified
        self._config_modified = modified

        # 发出配置修改状态变化信号
        if old_state != modified:
            try:
                self.signal_bus.configModified.emit(modified)
            except Exception:
                logger.debug("发出配置修改信号失败（非致命）", exc_info=True)

        # 若配置被用户修改，则同时标记为项目已被用户修改，
        # 以便启用 Project 的保存按钮（用户通常希望保存包含当前配置的项目）。
        try:
            if modified and hasattr(self, "gui") and self.gui is not None:
                try:
                    if hasattr(self.gui, "mark_user_modified") and callable(
                        self.gui.mark_user_modified
                    ):
                        self.gui.mark_user_modified()
                except Exception:
                    logger.debug("同步配置修改到项目修改标志失败", exc_info=True)
        except Exception:
            pass

    def _on_panel_values_changed(self):
        """配置面板字段变更回调（防止重复连接导致多次触发）。"""
        try:
            self.set_config_modified(True)
        except Exception:
            logger.debug("处理面板修改回调失败（非致命）", exc_info=True)

    def _on_part_list_changed(self, *args):
        """Part 列表修改回调（监听 SignalBus.partAdded / partRemoved 信号）。

        当通过 PartManager 添加或删除 Source/Target Part 时，标记配置已修改。
        若为删除操作，还需刷新文件树中对该 Part 的映射状态验证。
        """
        try:
            logger.debug("检测到 Part 列表修改: %s", args)
            self.set_config_modified(True)

            # 如果是 Part 删除事件，刷新文件树状态以检测受影响的文件
            if len(args) >= 1:
                event_type = args[0] if isinstance(args[0], str) else None
                # 检查是否为 partRemoved 信号（args[0]='Source'/'Target', args[1]=part_name）
                if event_type in ("Source", "Target") and len(args) >= 2:
                    removed_part_name = args[1]
                    self._refresh_file_tree_on_part_removed(
                        event_type, removed_part_name
                    )
        except Exception:
            logger.debug("处理 Part 修改回调失败（非致命）", exc_info=True)

    def _refresh_file_tree_on_part_removed(self, side: str, part_name: str) -> None:
        """当 Part 被删除时，刷新文件树中该 Part 的映射验证状态。

        如果文件之前因为该 Part 被映射而状态为绿色，现在需要更新状态提示
        该 Part 已不可用。

        参数：
            side: 'Source' 或 'Target'
            part_name: 被删除的 Part 名称
        """
        try:
            # 仅在有文件树且文件已加载的情况下刷新
            if not hasattr(self.gui, "file_tree") or not hasattr(
                self.gui, "_file_tree_items"
            ):
                logger.debug("文件树不可用，跳过 Part 删除后的刷新")
                return

            # 访问文件树项映射并触发重新验证
            items_dict = getattr(self.gui, "_file_tree_items", {})
            if not items_dict:
                return

            logger.debug(
                "Part 已删除（%s: %s），正在刷新文件树状态...", side, part_name
            )

            # 重新验证所有文件的配置状态
            # 通过访问 BatchManager 的验证方法进行
            batch_manager = getattr(self.gui, "batch_manager", None)
            if batch_manager is None:
                # 若无 batch_manager，尝试从其他位置获取
                model_manager = getattr(self.gui, "model_manager", None)
                if model_manager is not None:
                    batch_manager = getattr(model_manager, "batch_manager", None)

            if batch_manager is not None:
                try:
                    # 批量刷新所有已加载文件的状态
                    for file_path_str, item in items_dict.items():
                        try:
                            from pathlib import Path as PathlibPath

                            file_path = PathlibPath(file_path_str)
                            # 使用 BatchManager 的验证方法重新评估文件状态
                            status_text = batch_manager._validate_file_config(file_path)
                            item.setText(1, status_text)
                            logger.debug(
                                "已刷新文件 %s 的状态: %s", file_path_str, status_text
                            )
                        except Exception:
                            logger.debug(
                                "刷新文件 %s 状态失败（非致命）",
                                file_path_str,
                                exc_info=True,
                            )
                except Exception:
                    logger.debug("批量刷新文件状态失败（非致命）", exc_info=True)
            else:
                logger.debug("无法获取 BatchManager，跳过文件状态刷新")

            # 发送状态提示
            try:
                signal_bus = getattr(self.gui, "signal_bus", SignalBus.instance())
                signal_bus.statusMessage.emit(
                    f"Part '{part_name}' 已删除，文件映射状态已更新",
                    3000,
                    MessagePriority.MEDIUM,
                )
            except Exception:
                logger.debug("发送状态提示失败（非致命）", exc_info=True)

        except Exception:
            logger.debug("Part 删除后刷新文件树状态失败（非致命）", exc_info=True)

    def _clear_batch_file_selection(self) -> None:
        """清除批处理多选文件列表。

        在重做模式、加载新配置或重置配置时调用，确保用户不会
        误用旧的批处理选择（可能与新配置不兼容）。
        """
        try:
            # 清除 BatchManager 中的多选列表
            batch_manager = getattr(self.gui, "batch_manager", None)
            if batch_manager is not None:
                batch_manager._selected_paths = None
                logger.info("已清除批处理多选文件列表")
            else:
                logger.debug("BatchManager 不可用，无法清除多选列表")
        except Exception:
            logger.debug("清除批处理多选文件列表失败（非致命）", exc_info=True)

    def reset_config(self) -> None:
        """重置配置到初始状态（向后兼容旧接口）。

        清除加载的配置、项目模型，重置修改标志，并尝试清空界面面板显示。
        同时清除批处理多选文件列表，避免使用不兼容的旧配置。
        """
        try:
            # 清除批处理多选列表
            self._clear_batch_file_selection()
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
