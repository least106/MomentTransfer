"""
MomentTransfer GUI 主窗口模块
向后兼容入口：从 gui 包导入模块化的组件

重构说明：
- Mpl3DCanvas -> gui/canvas.py
- ExperimentalDialog -> gui/dialogs.py
- BatchProcessThread -> gui/batch_thread.py
- IntegratedAeroGUI -> 保留在此文件（待进一步拆分）
"""

# 某些模块为延迟加载以加快启动速度，接受受控的 import-outside-toplevel
# pylint: disable=import-outside-toplevel

import logging
import uuid
import sys
import traceback
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtCore import QEventLoop
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QProgressDialog,
)

from gui.event_manager import EventManager
from gui.initialization_manager import InitializationManager

# 从模块化包导入组件
# Mpl3DCanvas 延迟加载以加快启动速度（在首次调用show_visualization时加载）
from gui.log_manager import LoggingManager
from gui.managers import FileSelectionManager, ModelManager, UIStateManager

# 导入面板组件
from gui.panels import ConfigPanel, OperationPanel

# 导入管理器和工具
from gui.signal_bus import SignalBus

logger = logging.getLogger(__name__)

try:
    from gui.managers import _report_ui_exception
except Exception:
    _report_ui_exception = None

# 主题常量（便于代码中引用）
THEME_MAIN = "#0078d7"
THEME_ACCENT = "#28a745"
THEME_DANGER = "#ff6b6b"
THEME_BG = "#f7f9fb"
LAYOUT_MARGIN = 12
LAYOUT_SPACING = 8


class IntegratedAeroGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        # 基本属性
        self.setWindowTitle("MomentTransfer")
        self.resize(1500, 900)

        # 初始化标志
        self._is_initializing = True

        # 核心数据（移到 ModelManager）
        self.signal_bus = SignalBus.instance()
        self.data_config = None
        self.visualization_window = None

        # 管理器化的状态：文件选择、模型、UI 状态
        self.file_selection_manager = FileSelectionManager(self)
        self.model_manager = ModelManager(self)

        self.ui_state_manager = UIStateManager(self)

        # 管理器占位（将由 InitializationManager 初始化）
        self.config_manager = None
        self.part_manager = None
        self.batch_manager = None
        self.layout_manager = None

        # UI 状态标志
        self.data_loaded = False
        self.config_loaded = False
        self.operation_performed = False

        # 新管理器
        self.initialization_manager = InitializationManager(self)
        self.event_manager = EventManager(self)

        # 本地状态消息优先级（更高优先级不会被低优先级覆盖）
        self._status_priority = 0
        self._status_clear_timer = None
        self._status_token = None

        # 执行初始化
        self.initialization_manager.setup_ui()
        self.initialization_manager.setup_managers()
        self.initialization_manager.setup_logging()
        self.initialization_manager.bind_post_ui_signals()

        # 连接 SignalBus 的统一状态消息信号，用于协调各处的状态提示
        try:
            sb = getattr(self, "signal_bus", None) or __import__("gui.signal_bus", fromlist=["SignalBus"]).SignalBus.instance()
            try:
                sb.statusMessage.connect(self._on_status_message)
            except Exception:
                logger.debug("连接 statusMessage 信号失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("获取 SignalBus 失败（非致命）", exc_info=True)

        # 确保 statusBar 存在
        try:
            if not hasattr(self, "statusBar"):
                self.setStatusBar(self.statusBar())
        except Exception:
            logger.debug("确保 statusBar 存在失败（非致命）", exc_info=True)

    def _on_status_message(self, message: str, timeout_ms: int, priority: int) -> None:
        """统一处理状态消息：按优先级显示，并在超时后清理。

        更高优先级的消息不会被低优先级覆盖。
        """
        try:
            # 获取当前优先级
            try:
                cur_pr = int(getattr(self, "_status_priority", 0))
            except Exception:
                cur_pr = 0

            # 若 incoming 优先级低于当前且已有未过期消息，则忽略
            try:
                t_old = getattr(self, "_status_clear_timer", None)
                if int(priority) < cur_pr and t_old is not None and getattr(t_old, "isActive", lambda: False)():
                    return
            except Exception:
                # 任何判定失败时不阻止显示新消息
                pass

            # 停止并清理已有定时器（我们将在下面根据新消息重建），并清除旧 token
            try:
                t_old = getattr(self, "_status_clear_timer", None)
                if t_old is not None:
                    try:
                        t_old.stop()
                    except Exception:
                        logger.debug("停止旧状态清理定时器失败（非致命）", exc_info=True)
                    self._status_clear_timer = None
                try:
                    self._status_token = None
                except Exception:
                    pass
            except Exception:
                logger.debug("清理旧状态定时器时发生异常（非致命）", exc_info=True)

            # 立刻在状态栏显示消息（由我们控制何时清理）
            try:
                sb = self.statusBar()
                if sb is not None:
                    sb.showMessage(message)
            except Exception:
                logger.debug("显示状态栏消息失败", exc_info=True)

            # 设置当前优先级（用于后续清理判断）
            try:
                self._status_priority = int(priority) if priority is not None else 0
            except Exception:
                self._status_priority = 0

            # 若指定了超时，使用单个临时 QTimer 在超时后按 token 清理（避免仅通过 priority 字符串比较）
            try:
                if timeout_ms and int(timeout_ms) > 0:
                    from PySide6.QtCore import QTimer

                    timeout_val = int(timeout_ms)
                    token = uuid.uuid4().hex
                    # 保存 token 用于后续比较
                    try:
                        self._status_token = token
                    except Exception:
                        logger.debug("设置状态 token 失败（非致命）", exc_info=True)

                    t = QTimer(self)
                    t.setSingleShot(True)
                    # 捕获 token，比较 token 一致性以决定是否清理
                    t.timeout.connect(lambda tok=token: self._clear_status_if_token(tok))
                    try:
                        t.start(timeout_val)
                    except Exception:
                        logger.debug("启动状态清理定时器失败（非致命）", exc_info=True)
                    self._status_clear_timer = t
            except Exception:
                logger.debug("设置状态清理定时器失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("处理 statusMessage 信号失败", exc_info=True)

    def _clear_status_if_priority(self, priority_to_clear: int) -> None:
        try:
            if getattr(self, "_status_priority", 0) != priority_to_clear:
                return
            try:
                sb = self.statusBar()
                if sb is not None:
                    sb.clearMessage()
            except Exception:
                logger.debug("清理状态栏消息失败（非致命）", exc_info=True)
            try:
                self._status_priority = 0
            except Exception:
                logger.debug("重置状态优先级失败（非致命）", exc_info=True)
            try:
                self._status_clear_timer = None
            except Exception:
                logger.debug("清除状态定时器引用失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("清理状态消息失败", exc_info=True)

    def _clear_status_if_token(self, token: str) -> None:
        try:
            cur_tok = getattr(self, "_status_token", None)
            if cur_tok != token:
                return
            try:
                sb = self.statusBar()
                if sb is not None:
                    sb.clearMessage()
            except Exception:
                logger.debug("按 token 清理状态栏消息失败（非致命）", exc_info=True)
            try:
                self._status_priority = 0
            except Exception:
                logger.debug("按 token 重置状态优先级失败（非致命）", exc_info=True)
            try:
                self._status_clear_timer = None
            except Exception:
                logger.debug("按 token 清除状态定时器引用失败（非致命）", exc_info=True)
            try:
                self._status_token = None
            except Exception:
                logger.debug("清除状态 token 失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("按 token 清理状态消息失败", exc_info=True)


    def set_config_panel_visible(self, visible: bool) -> None:
        """按流程显示/隐藏配置编辑器，减少初始化干扰。"""
        # 将具体实现委托给 UIStateManager，主窗口保留向后兼容行为
        try:
            self.ui_state_manager.set_config_panel_visible(visible)
        except Exception:
            logger.debug("set_config_panel_visible failed", exc_info=True)

    def mark_data_loaded(self) -> None:
        """标记已加载数据文件并刷新控件状态"""
        try:
            # 委托给 UIStateManager 以集中管理状态变化
            if hasattr(self, "ui_state_manager") and self.ui_state_manager:
                try:
                    self.ui_state_manager.set_data_loaded(True)
                    return
                except Exception:
                    logger.debug(
                        "ui_state_manager.set_data_loaded 调用失败，回退到直接设置",
                        exc_info=True,
                    )

            self.data_loaded = True
            self._refresh_controls_state()
        except Exception:
            logger.debug("mark_data_loaded failed", exc_info=True)

    def mark_config_loaded(self) -> None:
        """标记已加载配置并刷新控件状态"""
        try:
            if hasattr(self, "ui_state_manager") and self.ui_state_manager:
                try:
                    self.ui_state_manager.set_config_loaded(True)
                    return
                except Exception:
                    logger.debug(
                        "ui_state_manager.set_config_loaded 调用失败，回退到直接设置",
                        exc_info=True,
                    )

            self.config_loaded = True
            self._refresh_controls_state()
        except Exception:
            logger.debug("mark_config_loaded failed", exc_info=True)

    def mark_user_modified(self) -> None:
        """标记为用户已修改（用于启用保存按钮）。

        与 data_loaded/config_loaded 区分，避免仅加载即启用保存。
        """
        try:
            if hasattr(self, "ui_state_manager") and self.ui_state_manager:
                try:
                    self.ui_state_manager.mark_user_modified()
                    return
                except Exception:
                    logger.debug(
                        "ui_state_manager.mark_user_modified 调用失败，回退到直接设置",
                        exc_info=True,
                    )

            self.operation_performed = True
            self._refresh_controls_state()
        except Exception:
            logger.debug("mark_user_modified failed", exc_info=True)

    def _refresh_controls_state(self) -> None:
        """根据当前状态标志启用/禁用按钮与选项卡。"""
        try:
            # 集中化状态管理：始终通过 UIStateManager 负责控件状态刷新。
            if hasattr(self, "ui_state_manager") and self.ui_state_manager:
                self.ui_state_manager.refresh_controls_state()
                return
            # 若缺少 UIStateManager，记录错误以便诊断（保守地不做本地回退）
            logger.error("无法刷新控件状态：UIStateManager 不存在")
        except Exception:
            logger.exception("_refresh_controls_state failed")

    def create_config_panel(self):
        """创建配置编辑器面板（由 InitializationManager 调用）"""
        panel = ConfigPanel(self)

        # 保存面板引用
        self.source_panel = panel.source_panel
        self.target_panel = panel.target_panel

        return panel

    def _select_all_files(self):
        """委托给 BatchManager 全选文件（兼容旧接口）。"""
        try:
            if self.batch_manager:
                try:
                    self.batch_manager.select_all_files()
                except Exception:
                    logger.debug("batch_manager.select_all_files 调用失败", exc_info=True)
        except Exception:
            logger.debug("_select_all_files failed", exc_info=True)

    def _select_none_files(self):
        """委托给 BatchManager 全不选文件（兼容旧接口）。"""
        try:
            if self.batch_manager:
                try:
                    self.batch_manager.select_none_files()
                except Exception:
                    logger.debug("batch_manager.select_none_files 调用失败", exc_info=True)
        except Exception:
            logger.debug("_select_none_files failed", exc_info=True)

    def _invert_file_selection(self):
        """委托给 BatchManager 反选文件（兼容旧接口）。"""
        try:
            if self.batch_manager:
                try:
                    self.batch_manager.invert_file_selection()
                except Exception:
                    logger.debug("batch_manager.invert_file_selection 调用失败", exc_info=True)
        except Exception:
            logger.debug("_invert_file_selection failed", exc_info=True)

    def _quick_select(self):
        """打开快速选择对话（兼容旧接口）。"""
        try:
            if self.batch_manager:
                try:
                    self.batch_manager.open_quick_select_dialog()
                    return
                except Exception:
                    logger.debug("batch_manager.open_quick_select_dialog 调用失败", exc_info=True)

            # 回退：若存在 file_selection_manager，使用其快速选择逻辑
            try:
                fsm = getattr(self, "file_selection_manager", None)
                if fsm and hasattr(fsm, "open_quick_select_dialog"):
                    try:
                        fsm.open_quick_select_dialog()
                        return
                    except Exception:
                        logger.debug("file_selection_manager.open_quick_select_dialog 调用失败", exc_info=True)
            except Exception:
                logger.debug("快速选择回退调用失败", exc_info=True)
        except Exception:
            logger.debug("_quick_select failed", exc_info=True)

    def create_operation_panel(self):
        """创建批量处理面板（委托 OperationPanel 组件），并保持旧属性兼容。"""
        panel = OperationPanel(
            parent=self,
            on_batch_start=self.run_batch_processing,
            on_browse=self.browse_batch_input,
            on_select_all=self._select_all_files,
            on_select_none=self._select_none_files,
            on_invert_selection=self._invert_file_selection,
            on_quick_select=self._quick_select,
            on_save_project=self._on_save_project,
        )

        # 兼容旧属性映射
        try:
            panel.attach_legacy_aliases(self)
        except Exception:
            logger.debug("attach_legacy_aliases 失败", exc_info=True)

        # 返回创建的面板（面板内部会触发对应回调；此处不应包含与保存/未保存提示无关的流程）
        return panel

    def save_config(self):
        """保存配置到JSON - 委托给 ConfigManager"""
        try:
            self.config_manager.save_config()
        except AttributeError:
            # 如果管理器未初始化，记录警告
            logger.warning("ConfigManager 未初始化，无法保存配置")
        except Exception as e:
            logger.error("保存配置失败: %s", e)

    def load_config(self):
        """加载配置：委托给 ConfigManager（兼容旧接口）。"""
        try:
            cm = getattr(self, "config_manager", None)
            if cm and hasattr(cm, "load_config"):
                try:
                    cm.load_config()
                    return
                except Exception:
                    logger.debug("ConfigManager.load_config 调用失败", exc_info=True)
            logger.warning("ConfigManager 未初始化或不支持 load_config")
        except Exception:
            logger.exception("load_config failed")

    def apply_config(self):
        # 已移除：应用配置的交互逻辑。
        # 该方法曾用于把面板配置应用为“全局 calculator”，
        # 当前语义改为由批处理在运行时按文件创建计算器，
        # 因此不再支持通过此入口应用配置。
        logger.debug("apply_config 已被移除（no-op）")

    # 配置格式方法委托给 ConfigManager
    # 已移除全局数据格式配置功能（改为 per-file sidecar / registry 机制）

    def browse_batch_input(self):
        """选择输入文件或目录 - 委托给 BatchManager"""
        try:
            self.batch_manager.browse_batch_input()
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error("浏览批处理输入失败: %s", e)

    def _scan_and_populate_files(self, chosen_path):
        """扫描所选路径并刷新文件列表（委托给 BatchManager）。"""
        try:
            self.batch_manager.scan_and_populate_files(chosen_path)
        except Exception:
            logger.debug(
                "_scan_and_populate_files delegated call failed", exc_info=True
            )

    def _on_save_project(self):
        """保存Project（打开选择文件对话框）"""
        try:
            from PySide6.QtWidgets import QFileDialog
            from datetime import datetime

            # 若已有当前项目文件路径则后台保存（显示等待对话）
            if getattr(self, "project_manager", None) and getattr(
                self.project_manager, "current_project_file", None
            ):
                try:
                    fp = self.project_manager.current_project_file

                    dlg = QProgressDialog("正在保存项目…", None, 0, 0, self)
                    dlg.setWindowModality(Qt.WindowModal)
                    try:
                        dlg.setCancelButton(None)
                    except Exception:
                        pass
                    dlg.setMinimumDuration(0)
                    dlg.show()

                    def _on_saved(success, saved_fp):
                        try:
                            dlg.close()
                        except Exception:
                            pass
                        if success:
                            try:
                                QMessageBox.information(
                                    self, "成功", f"项目已保存到: {saved_fp}"
                                )
                            except Exception:
                                logger.debug(
                                    "无法显示保存成功提示", exc_info=True
                                )
                        else:
                            # UX：ProjectManager.save_project 内部已负责向用户展示失败原因。
                            # 这里避免重复弹窗，仅做轻量提示。
                            try:
                                self.statusBar().showMessage(
                                    "项目保存失败（详情请查看提示/日志）", 5000
                                )
                            except Exception:
                                logger.debug(
                                    "无法在状态栏提示保存失败（非致命）",
                                    exc_info=True,
                                )

                    self.project_manager.save_project_async(fp, on_finished=_on_saved)
                    return
                except Exception:
                    logger.debug("直接保存当前项目失败，退回到另存为对话", exc_info=True)

            # 另存为：预填当前路径或建议文件名 project_YYYYMMDD.mtproject
            default_dir = ""
            pm = getattr(self, "project_manager", None)
            ext = getattr(pm.__class__, "PROJECT_FILE_EXTENSION", ".mtproject") if pm else ".mtproject"
            suggested = f"project_{datetime.now().strftime('%Y%m%d')}{ext}"
            try:
                pm = getattr(self, "project_manager", None)
                if pm and getattr(pm, "current_project_file", None):
                    cur = pm.current_project_file
                    default_dir = str(cur.parent)
                else:
                    # 尝试使用工作目录
                    default_dir = str(Path.cwd())
            except Exception:
                default_dir = ""

            # 打开保存文件对话框（预填路径+建议名）
            start_path = str(Path(default_dir) / suggested) if default_dir else suggested
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存Project文件",
                start_path,
                "MomentTransfer Project (*.mtproject);;All Files (*)",
            )

            if file_path:
                if self.project_manager:
                    dlg = QProgressDialog("正在保存项目…", None, 0, 0, self)
                    dlg.setWindowModality(Qt.WindowModal)
                    try:
                        dlg.setCancelButton(None)
                    except Exception:
                        pass
                    dlg.setMinimumDuration(0)
                    dlg.show()

                    def _on_saved2(success, saved_fp):
                        try:
                            dlg.close()
                        except Exception:
                            pass
                        if success:
                            try:
                                QMessageBox.information(
                                    self, "成功", f"项目已保存到: {saved_fp}"
                                )
                            except Exception as e:
                                logger.debug(
                                    "无法显示保存成功提示: %s", e, exc_info=True
                                )
                        else:
                            # UX：ProjectManager.save_project 内部已负责向用户展示失败原因。
                            # 这里避免重复弹窗，仅做轻量提示。
                            try:
                                self.statusBar().showMessage(
                                    "项目保存失败（详情请查看提示/日志）", 5000
                                )
                            except Exception:
                                logger.debug(
                                    "无法在状态栏提示保存失败（非致命）",
                                    exc_info=True,
                                )

                    self.project_manager.save_project_async(Path(file_path), on_finished=_on_saved2)
        except Exception as e:
            logger.error("保存Project失败: %s", e)
            try:
                QMessageBox.critical(self, "错误", f"保存Project失败: {e}")
            except Exception:
                logger.debug("无法显示保存失败对话框（非致命）", exc_info=True)

    def _new_project(self):
        """创建新Project"""
        try:
            # 在新建前检测是否有未保存更改
            if self._has_unsaved_changes():
                proceed = self._confirm_save_discard_cancel("创建新项目")
                if not proceed:
                    return

            if self.project_manager:
                if self.project_manager.create_new_project():
                    try:
                        QMessageBox.information(self, "成功", "新项目已创建")
                    except Exception as e:
                        logger.debug(
                            "无法显示新项目提示: %s", e, exc_info=True
                        )
        except Exception as e:
            logger.error("创建新Project失败: %s", e)

    def _open_project(self):
        """打开Project文件"""
        try:
            # 在打开前检测是否有未保存更改
            if self._has_unsaved_changes():
                proceed = self._confirm_save_discard_cancel("打开项目")
                if not proceed:
                    return

            from pathlib import Path

            from PySide6.QtWidgets import QFileDialog

            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "打开Project文件",
                "",
                "MomentTransfer Project (*.mtproject);;All Files (*)",
            )

            if file_path:
                if self.project_manager:
                    dlg = QProgressDialog("正在加载项目…", None, 0, 0, self)
                    dlg.setWindowModality(Qt.WindowModal)
                    try:
                        dlg.setCancelButton(None)
                    except Exception:
                        pass
                    dlg.setMinimumDuration(0)
                    dlg.show()

                    def _on_loaded(success, loaded_fp):
                        try:
                            dlg.close()
                        except Exception:
                            pass
                        if success:
                            try:
                                QMessageBox.information(
                                    self, "成功", f"项目已加载: {loaded_fp}"
                                )
                            except Exception as e:
                                logger.debug(
                                    "无法显示加载成功提示: %s", e, exc_info=True
                                )
                        else:
                            # UX：ProjectManager.load_project 内部会对解析失败/版本不匹配等情况弹窗说明。
                            # 这里避免重复弹窗，仅做轻量提示。
                            try:
                                self.statusBar().showMessage(
                                    "项目加载失败（详情请查看提示/日志）", 5000
                                )
                            except Exception:
                                logger.debug(
                                    "无法在状态栏提示加载失败（非致命）",
                                    exc_info=True,
                                )

                    self.project_manager.load_project_async(Path(file_path), on_finished=_on_loaded)
        except Exception as e:
            logger.error("打开Project失败: %s", e)

    def _has_unsaved_changes(self) -> bool:
        """检测当前是否存在未保存的更改。

        优先使用 ProjectManager 的 last_saved_state 与当前收集状态比较；
        若 ProjectManager 不可用或 last_saved_state 缺失，回退到 UI 状态管理器或 `operation_performed` 标志。
        """
        try:
            pm = getattr(self, "project_manager", None)
            if pm:
                try:
                    current = pm._collect_current_state()
                    last = getattr(pm, "last_saved_state", None)
                    if last is None:
                        # 若没有 last_saved_state，退回到 UI 标志
                        if hasattr(self, "ui_state_manager") and self.ui_state_manager:
                            try:
                                return bool(self.ui_state_manager.is_operation_performed())
                            except Exception:
                                return bool(getattr(self, "operation_performed", False))
                        return bool(getattr(self, "operation_performed", False))
                    return current != last
                except Exception:
                    logger.debug("比较项目状态时出错，退回到 UI 标志检测", exc_info=True)
            # 回退检测
            if hasattr(self, "ui_state_manager") and self.ui_state_manager:
                try:
                    return bool(self.ui_state_manager.is_operation_performed())
                except Exception:
                    return bool(getattr(self, "operation_performed", False))
            return bool(getattr(self, "operation_performed", False))
        except Exception:
            logger.debug("检测未保存更改失败，默认返回 False", exc_info=True)
            return False

    def _confirm_save_discard_cancel(self, intent: str) -> bool:
        """在检测到未保存更改时弹出三选对话：保存 / 放弃 / 取消。

        返回 True 表示继续执行 intent（保存或放弃后），False 表示取消操作。
        """
        try:
            msg = QMessageBox(self)
            msg.setWindowTitle("未保存更改")
            msg.setText(f"检测到未保存的更改。是否在执行“{intent}”前保存更改？")
            # UX：这里的“放弃”语义应为“本次不保存仍继续”，而不是立刻把未保存标记清掉。
            # 否则若用户后续取消“打开文件”对话框，或“打开/新建”失败，会导致未保存状态被错误清除。
            msg.setInformativeText("保存：保存更改并继续；放弃：本次不保存并继续；取消：返回。")
            btn_save = msg.addButton("保存", QMessageBox.AcceptRole)
            btn_discard = msg.addButton("放弃", QMessageBox.DestructiveRole)
            btn_cancel = msg.addButton("取消", QMessageBox.RejectRole)
            try:
                msg.setIcon(QMessageBox.Warning)
            except Exception:
                pass
            # 防止误触 Enter 导致丢失数据；Esc 始终等价于“取消”
            try:
                # 默认按钮设为取消，降低误操作风险（回车不应意外触发保存）
                msg.setDefaultButton(btn_cancel)
            except Exception:
                pass
            try:
                msg.setEscapeButton(btn_cancel)
            except Exception:
                pass
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == btn_save:
                # 改为使用异步保存以避免阻塞主线程；在等待期间显示模态进度对话并用
                # QEventLoop 保持界面响应。
                try:
                    pm = getattr(self, "project_manager", None)
                    if pm:
                        # 若已有当前项目文件，使用异步保存并等待回调
                        cur_fp = getattr(pm, "current_project_file", None)
                        if cur_fp:
                            dlg = QProgressDialog("正在保存项目…", None, 0, 0, self)
                            dlg.setWindowModality(Qt.WindowModal)
                            try:
                                dlg.setCancelButton(None)
                            except Exception:
                                pass
                            dlg.setMinimumDuration(0)
                            dlg.show()

                            loop = QEventLoop()
                            result = {"saved": False}

                            def _on_saved_async(success, saved_fp):
                                try:
                                    result["saved"] = bool(success)
                                except Exception:
                                    result["saved"] = False
                                try:
                                    dlg.close()
                                except Exception:
                                    pass
                                if success:
                                    try:
                                        QMessageBox.information(
                                            self, "成功", f"项目已保存到: {saved_fp}"
                                        )
                                    except Exception:
                                        logger.debug(
                                            "无法显示保存成功提示", exc_info=True
                                        )
                                else:
                                    try:
                                        QMessageBox.critical(
                                            self, "错误", "项目保存失败"
                                        )
                                    except Exception:
                                        logger.debug(
                                            "无法显示保存失败对话框（非致命）",
                                            exc_info=True,
                                        )
                                try:
                                    loop.quit()
                                except Exception:
                                    pass

                            try:
                                pm.save_project_async(cur_fp, on_finished=_on_saved_async)
                                loop.exec()
                            except Exception:
                                logger.exception("异步保存项目失败")
                                try:
                                    dlg.close()
                                except Exception:
                                    pass
                                return False

                            if not result.get("saved"):
                                return False

                        else:
                            # 否则弹出另存为对话并异步保存
                            try:
                                from PySide6.QtWidgets import QFileDialog

                                pm = getattr(self, "project_manager", None)
                                ext = getattr(pm.__class__, "PROJECT_FILE_EXTENSION", ".mtproject") if pm else ".mtproject"
                                suggested = f"project_{datetime.now().strftime('%Y%m%d')}{ext}"
                                start = str(Path.cwd() / suggested)
                                save_path, _ = QFileDialog.getSaveFileName(
                                    self,
                                    "保存 Project 文件",
                                    start,
                                    "MomentTransfer Project (*.mtproject);;All Files (*)",
                                )
                                if not save_path:
                                    # 用户取消另存为，视为未完成保存 -> 取消原操作
                                    return False

                                dlg = QProgressDialog("正在保存项目…", None, 0, 0, self)
                                dlg.setWindowModality(Qt.WindowModal)
                                try:
                                    dlg.setCancelButton(None)
                                except Exception:
                                    pass
                                dlg.setMinimumDuration(0)
                                dlg.show()

                                loop = QEventLoop()
                                result = {"saved": False}

                                def _on_saved2(success, saved_fp):
                                    try:
                                        result["saved"] = bool(success)
                                    except Exception:
                                        result["saved"] = False
                                    try:
                                        dlg.close()
                                    except Exception:
                                        pass
                                    if success:
                                        try:
                                            QMessageBox.information(
                                                self, "成功", f"项目已保存到: {saved_fp}"
                                            )
                                        except Exception:
                                            logger.debug(
                                                "无法显示保存成功提示: %s",
                                                exc_info=True,
                                            )
                                    else:
                                        try:
                                            QMessageBox.critical(
                                                self, "错误", "项目保存失败"
                                            )
                                        except Exception:
                                            logger.debug(
                                                "无法显示保存失败对话框（非致命）",
                                                exc_info=True,
                                            )
                                    try:
                                        loop.quit()
                                    except Exception:
                                        pass

                                try:
                                    pm.save_project_async(Path(save_path), on_finished=_on_saved2)
                                    loop.exec()
                                except Exception:
                                    logger.exception("异步另存为保存失败")
                                    try:
                                        dlg.close()
                                    except Exception:
                                        pass
                                    return False

                                if not result.get("saved"):
                                    return False
                            except Exception:
                                logger.debug("另存为对话或保存过程中出错", exc_info=True)
                                return False
                    else:
                        # 没有 ProjectManager 时回退到调用原始保存逻辑（可能弹出对话）
                        try:
                            self._on_save_project()
                        except Exception:
                            logger.debug("调用 _on_save_project 失败", exc_info=True)
                except Exception:
                    logger.debug("保存分支处理失败", exc_info=True)
                    return False

                # 保存后再次检测是否仍有未保存更改（用户可能取消了保存）
                return not self._has_unsaved_changes()
            if clicked == btn_discard:
                # “放弃”=本次不保存并继续：不要在这里修改 last_saved_state / UI 标志。
                # 让后续 intent（打开/新建/退出）真正成功后再由对应流程清理状态，
                # 避免“用户取消文件选择/加载失败但未保存状态被清掉”的 UX 逻辑漏洞。
                return True
            # 取消
            return False
        except Exception:
            try:
                if _report_ui_exception:
                    _report_ui_exception(self, "未保存更改对话弹出失败（已自动取消操作）")
            except Exception:
                logger.debug("报告未保存对话失败时出错", exc_info=True)
            logger.debug("弹出未保存对话失败，默认取消操作", exc_info=True)
            return False

    def run_batch_processing(self):
        """运行批处理 - 委托给 BatchManager"""
        try:
            # 保护性检查：确保关键管理器已初始化，避免在初始化期间触发批处理
            if not getattr(self, "batch_manager", None) or not getattr(
                self, "config_manager", None
            ):
                try:
                    QMessageBox.information(
                        self,
                        "功能暂不可用",
                        "系统尚未就绪（正在初始化或管理器未启动），请稍候再试。",
                    )
                except Exception:
                    try:
                        from gui.managers import _report_ui_exception

                        _report_ui_exception(self, "显示未就绪提示失败（非致命）")
                    except Exception:
                        logger.debug("显示未就绪提示失败（非致命）", exc_info=True)
                return

            # 检查配置是否被修改
            if (
                self.config_manager
                and self.config_manager.is_config_modified()
            ):
                reply = QMessageBox.question(
                    self,
                    "配置已修改",
                    "检测到配置已修改但未保存。\n\n是否要保存修改的配置后再进行批处理？",
                    QMessageBox.Save
                    | QMessageBox.Discard
                    | QMessageBox.Cancel,
                    # 默认选择改为取消，避免误触导致直接保存并覆盖配置
                    QMessageBox.Cancel,
                )

                # 用户选择保存：尝试保存并仅在成功后继续
                if reply == QMessageBox.Save:
                    try:
                        saved = self.config_manager.save_config()
                    except Exception as e:
                        logger.error(
                            "保存配置时发生异常: %s", e, exc_info=True
                        )
                        saved = False

                    # 如果保存失败，允许用户重试、继续（不保存）或取消操作
                    if not saved:
                        try:
                            while True:
                                mb = QMessageBox(self)
                                mb.setWindowTitle("保存失败")
                                mb.setText("配置保存失败。请选择操作：")
                                mb.setInformativeText(
                                    "可以重试保存、继续（不保存）或取消批处理启动。"
                                )
                                btn_retry = mb.addButton(
                                    "重试", QMessageBox.AcceptRole
                                )
                                btn_continue = mb.addButton(
                                    "继续（不保存）",
                                    QMessageBox.DestructiveRole,
                                )
                                btn_cancel = mb.addButton("取消", QMessageBox.RejectRole)
                                # 默认设为取消以提供最安全的选项
                                mb.setDefaultButton(btn_cancel)
                                mb.exec()

                                clicked = mb.clickedButton()
                                if clicked == btn_retry:
                                    try:
                                        saved = (
                                            self.config_manager.save_config()
                                        )
                                    except Exception as e:
                                        logger.error(
                                            "重试保存时发生异常: %s",
                                            e,
                                            exc_info=True,
                                        )
                                        saved = False
                                    if saved:
                                        logger.debug(
                                            "重试保存成功，继续执行批处理"
                                        )
                                        break
                                    # 否则循环继续，允许再次重试/选择其他操作
                                elif clicked == btn_continue:
                                    logger.warning(
                                        "用户选择继续而不保存配置，批处理将使用未保存的配置运行"
                                    )
                                    break
                                else:
                                    logger.debug(
                                        "用户取消了批处理启动（保存失败后）"
                                    )
                                    return
                        except Exception:
                            logger.debug(
                                "保存失败处理对话异常，已取消批处理",
                                exc_info=True,
                            )
                            return

                    else:
                        logger.debug("配置已保存，继续执行批处理")

                # 用户选择取消：中断批处理
                elif reply == QMessageBox.Cancel:
                    logger.debug("用户取消批处理启动（选择取消保存）")
                    return

            # 运行批处理（配置未修改或用户选择丢弃/已保存）
            self.batch_manager.run_batch_processing()
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error("运行批处理失败: %s", e)


    def on_batch_finished(self, message):
        """批处理完成 - 委托给 BatchManager"""
        try:
            self.batch_manager.on_batch_finished(message)
        except AttributeError:
            logger.warning("BatchManager 未初始化")
        except Exception as e:
            logger.error("处理批处理完成事件失败: %s", e)

    def on_batch_error(self, error_msg):
        """批处理出错 - 委托给 BatchManager"""
        handled = False
        try:
            if self.batch_manager:
                try:
                    # 如果 BatchManager 在内部已经展示了错误（modal/非modal），
                    # 则它应返回 True，表示主窗口无需重复提示。
                    handled = bool(
                        self.batch_manager.on_batch_error(error_msg)
                    )
                except Exception as e:
                    logger.error("处理批处理错误事件失败: %s", e)
                    try:
                        if hasattr(self, "btn_cancel"):
                            self.btn_cancel.setVisible(False)
                            self.btn_cancel.setEnabled(False)
                    except Exception:
                        logger.debug(
                            "Failed to hide/disable cancel button after error",
                            exc_info=True,
                        )
            else:
                logger.warning("BatchManager 未初始化")
        except Exception:
            logger.debug(
                "on_batch_error top-level delegation failed", exc_info=True
            )

        # 如果 manager 已经处理错误，则不再由主窗口重复展示提示
        if handled:
            return

        # 友好的错误提示，包含可行建议（主窗口退回的展示）
        try:
            # 使用统一的模态通知（严重错误需用户确认）
            self.notify_modal(
                title="处理失败",
                message="批处理过程中发生错误，已记录到日志。请检查输入文件与格式定义。",
                informative=(
                    "建议：检查 per-file 格式定义（<文件名>.format.json / 同目录 format.json / registry），"
                    "以及 Target 配置中的 MomentCenter/Q/S。"
                ),
                detailed=str(error_msg),
                icon=QMessageBox.Critical,
            )
        except Exception:
            logger.debug("无法显示错误对话框（非致命）", exc_info=True)

        # 非阻塞通知：在状态栏添加“查看详情”按钮，点击打开非模态详情对话框
        try:
            # 使用统一的非模态通知（信息性/可稍后查看）
            self.notify_nonmodal(
                summary="批处理出错 — 点击 '查看详情' 获取更多信息",
                details=str(error_msg),
                duration_ms=120000,
                button_text="查看详情",
            )
        except Exception:
            logger.debug("设置非阻塞错误通知失败（非致命）", exc_info=True)

    def _show_non_modal_error_details(self, error_msg: str) -> None:
        """在非模态对话框中显示错误详情，提供复制与打开日志的功能。"""
        try:
            dlg = QDialog(self)
            dlg.setWindowTitle("错误详情")
            dlg.setModal(False)
            dlg.setAttribute(Qt.WA_DeleteOnClose, True)

            layout = QVBoxLayout(dlg)
            text = QPlainTextEdit(dlg)
            text.setReadOnly(True)
            text.setPlainText(error_msg)
            layout.addWidget(text)

            btn_layout = QHBoxLayout()
            copy_btn = QPushButton("复制错误", dlg)
            open_log_btn = QPushButton("打开日志文件", dlg)
            close_btn = QPushButton("关闭", dlg)

            btn_layout.addWidget(copy_btn)
            btn_layout.addWidget(open_log_btn)
            btn_layout.addStretch(1)
            btn_layout.addWidget(close_btn)
            layout.addLayout(btn_layout)

            def _copy():
                try:
                    QApplication.clipboard().setText(str(error_msg))
                except Exception:
                    logger.debug(
                        "复制错误到剪贴板失败（非致命）", exc_info=True
                    )

            def _open_log():
                try:
                    from pathlib import Path

                    # 优先通过 LoggingManager 获取日志路径（若可用）
                    try:
                        from gui.log_manager import LoggingManager

                        lm = LoggingManager(self)
                        log_file = lm.get_log_file_path() or (
                            Path.home()
                            / ".momenttransfer"
                            / "momenttransfer.log"
                        )
                    except Exception:
                        log_file = (
                            Path.home()
                            / ".momenttransfer"
                            / "momenttransfer.log"
                        )

                    log_dir = log_file.parent
                    if log_file.exists():
                        QDesktopServices.openUrl(
                            QUrl.fromLocalFile(str(log_file))
                        )
                    elif log_dir.exists():
                        # 若日志文件不存在但目录存在，打开目录以便用户查看或收集日志
                        QDesktopServices.openUrl(
                            QUrl.fromLocalFile(str(log_dir))
                        )
                    else:
                        try:
                            QMessageBox.information(
                                dlg,
                                "日志未找到",
                                f"未找到日志文件: {log_file}\n日志目录: {log_dir}",
                            )
                        except Exception:
                            logger.debug(
                                "无法显示日志未找到提示（非致命）",
                                exc_info=True,
                            )
                except Exception:
                    logger.debug("打开日志文件失败（非致命）", exc_info=True)

            copy_btn.clicked.connect(_copy)
            open_log_btn.clicked.connect(_open_log)
            close_btn.clicked.connect(dlg.close)

            dlg.resize(700, 400)
            dlg.show()
        except Exception:
            logger.debug("显示非模态错误详情失败（非致命）", exc_info=True)

    def notify_modal(
        self,
        title: str,
        message: str,
        informative: str = None,
        detailed: str = None,
        icon=QMessageBox.Information,
    ) -> None:
        """统一的模态通知接口：用于致命或需要用户立刻决定的场景。"""
        try:
            dlg = QMessageBox(self)
            dlg.setIcon(icon)
            dlg.setWindowTitle(title)
            dlg.setText(message)
            if informative:
                dlg.setInformativeText(informative)
            if detailed:
                dlg.setDetailedText(detailed)
            dlg.exec()
        except Exception:
            logger.debug("notify_modal failed (non-fatal)", exc_info=True)

    def notify_nonmodal(
        self,
        summary: str,
        details: str = None,
        duration_ms: int = 120000,
        button_text: str = "查看详情",
    ) -> None:
        """统一的非模态通知：在状态栏显示 summary，并提供查看 details 的非模态入口。"""
        try:
            # 清理旧按钮及其 token
            try:
                old = getattr(self, "_notification_btn", None)
                if old is not None:
                    try:
                        self.statusBar().removeWidget(old)
                    except Exception:
                        old.setVisible(False)
                    try:
                        del self._notification_btn
                    except Exception:
                        pass
                try:
                    # 清理旧的通知 token（若存在）
                    if hasattr(self, "_notification_token"):
                        self._notification_token = None
                except Exception:
                    pass
            except Exception:
                pass

            if details is None:
                try:
                    # UX：非模态提示应在一定时间后自动消失，避免长期占用状态栏主消息区
                    self.statusBar().showMessage(summary, int(duration_ms))
                    return
                except Exception:
                    logger.debug(
                        "statusBar showMessage failed (non-fatal)",
                        exc_info=True,
                    )

            btn = QPushButton(button_text, self)
            btn.setToolTip(summary)
            btn.clicked.connect(lambda: self._show_non_modal_error_details(details))
            # 生成唯一 token 以绑定该条通知，避免基于 summary 字符串的比较冲突
            try:
                token = uuid.uuid4().hex
                setattr(self, "_notification_token", token)
                try:
                    setattr(btn, "_notify_token", token)
                except Exception:
                    # 不影响主要行为
                    pass
            except Exception:
                token = None
            self._notification_btn = btn
            try:
                self.statusBar().addPermanentWidget(btn)
            except Exception:
                try:
                    self.statusBar().showMessage(summary)
                except Exception:
                    logger.debug(
                        "statusBar fallback failed (non-fatal)", exc_info=True
                    )

            # 自动移除按钮
            def _remove():
                try:
                    b = getattr(self, "_notification_btn", None)
                    # 仅当 token 与当前保存的一致时才清理该通知，避免冲突
                    try:
                        cur_tok = getattr(self, "_notification_token", None)
                    except Exception:
                        cur_tok = None

                    if token is not None and cur_tok != token:
                        return

                    if b is not None:
                        try:
                            self.statusBar().removeWidget(b)
                        except Exception:
                            b.setVisible(False)
                        try:
                            del self._notification_btn
                        except Exception:
                            pass

                    try:
                        # 仅在当前显示的消息仍然是本通知时才清理
                        if getattr(self.statusBar(), "currentMessage", None):
                            cur = self.statusBar().currentMessage()
                        else:
                            cur = None
                        if cur == summary:
                            self.statusBar().clearMessage()
                    except Exception:
                        pass
                    try:
                        if hasattr(self, "_notification_token"):
                            self._notification_token = None
                    except Exception:
                        pass
                except Exception:
                    logger.debug(
                        "清除非模态通知按钮失败（非致命）", exc_info=True
                    )

            try:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(_remove)
                timer.start(duration_ms)
            except Exception:
                logger.debug(
                    "notification timer creation failed (non-fatal)",
                    exc_info=True,
                )

            try:
                # UX：与按钮移除计时保持一致
                self.statusBar().showMessage(summary, int(duration_ms))
            except Exception:
                logger.debug(
                    "statusBar showMessage failed after adding button (non-fatal)",
                    exc_info=True,
                )
        except Exception:
            logger.debug("notify_nonmodal failed (non-fatal)", exc_info=True)

    BUTTON_LAYOUT_THRESHOLD = 720

    def update_button_layout(self, threshold=None):
        """根据窗口宽度在网格中切换按钮位置 - 委托给 LayoutManager"""
        try:
            self.layout_manager.update_button_layout(threshold)
        except AttributeError:
            logger.warning("LayoutManager 未初始化")
        except Exception as e:
            logger.error("更新按钮布局失败: %s", e)

    # 事件处理方法委托给 EventManager
    def resizeEvent(self, event):
        """窗口大小改变事件"""
        if hasattr(self, "event_manager") and self.event_manager:
            self.event_manager.on_resize_event(event)
        return super().resizeEvent(event)

    def showEvent(self, event):
        """在窗口首次显示后触发初始化"""
        if hasattr(self, "event_manager") and self.event_manager:
            self.event_manager.on_show_event(event)
        return super().showEvent(event)

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        if hasattr(self, "event_manager") and self.event_manager:
            self.event_manager.on_close_event(event)
        return super().closeEvent(event)

    def _force_layout_refresh(self):
        """委托给 LayoutManager.force_layout_refresh()"""
        try:
            if hasattr(self, "layout_manager") and self.layout_manager:
                self.layout_manager.force_layout_refresh()
        except Exception:
            logger.debug(
                "_force_layout_refresh delegated call failed", exc_info=True
            )

    def _refresh_layouts(self):
        """委托给 LayoutManager 刷新布局与按钮布局"""
        try:
            if hasattr(self, "layout_manager") and self.layout_manager:
                try:
                    self.layout_manager.refresh_layouts()
                finally:
                    self.layout_manager.update_button_layout()
        except Exception:
            logger.debug(
                "_refresh_layouts delegated call failed", exc_info=True
            )

    # ----- 辅助方法：配置预览已委托给 ConfigManager -----

    def _add_source_part(self):
        """添加 Source Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, "_is_initializing", False):
            return
        try:
            self.part_manager.add_source_part()
        except Exception as e:
            logger.error("添加 Source Part 失败: %s", e)

    def _remove_source_part(self):
        """删除当前 Source Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, "_is_initializing", False):
            return
        try:
            self.part_manager.remove_source_part()
        except Exception as e:
            logger.error("删除 Source Part 失败: %s", e)

    def _add_target_part(self):
        """添加 Target Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, "_is_initializing", False):
            return
        try:
            self.part_manager.add_target_part()
        except Exception as e:
            logger.error("添加 Target Part 失败: %s", e)

    def _remove_target_part(self):
        """删除当前 Target Part - 委托给 PartManager，移除旧 fallback。"""
        if getattr(self, "_is_initializing", False):
            return
        try:
            self.part_manager.remove_target_part()
        except Exception as e:
            logger.error("删除 Target Part 失败: %s", e)

    def _on_src_partname_changed(self, new_text: str):
        """Part Name 文本框变化 - 委托给 PartManager"""
        if getattr(self, "_is_initializing", False):
            return
        if self.part_manager:
            self.part_manager.on_source_part_name_changed(new_text)

    def _on_tgt_partname_changed(self, new_text: str):
        """Part Name 文本框变化 - 委托给 PartManager"""
        if getattr(self, "_is_initializing", False):
            return
        if self.part_manager:
            self.part_manager.on_target_part_name_changed(new_text)

    # 批处理控制方法委托给 BatchManager
    def request_cancel_batch(self):
        if self.batch_manager:
            self.batch_manager.request_cancel_batch()

    def _setup_gui_logging(self):
        """设置日志系统，将所有日志输出到 GUI 的处理日志面板"""
        try:
            logging_manager = LoggingManager(self)
            logging_manager.setup_gui_logging()
        except Exception as e:
            logger.debug(
                "GUI logging setup failed (non-fatal): %s", e, exc_info=True
            )

    def _set_controls_locked(self, locked: bool):
        """锁定或解锁与配置相关的控件，防止用户在批处理运行期间修改配置。

        locked=True 时禁用；locked=False 时恢复。此方法尽量保持幂等并静默忽略缺失控件。
        """
        try:
            if hasattr(self, "ui_state_manager") and self.ui_state_manager:
                self.ui_state_manager.set_controls_locked(locked)
        except Exception:
            logger.debug(
                "_set_controls_locked delegation failed", exc_info=True
            )


def _initialize_exception_hook():
    """设置初始化期间的异常钩子，用于在初始化期间阻止异常弹窗"""
    original_excepthook = sys.excepthook

    def custom_excepthook(exc_type, exc_value, traceback_obj):
        """在初始化期间，仅记录异常而不显示弹窗"""
        # 获取当前正在执行的主窗口实例（如果存在）
        main_window = None
        for obj in list(QApplication.topLevelWidgets()):
            if isinstance(obj, IntegratedAeroGUI):
                main_window = obj
                break

        # 如果主窗口正在初始化，记录异常但不显示弹窗
        if main_window and getattr(main_window, "_is_initializing", False):
            # 记录完整 traceback 到日志
            try:
                tb_text = "".join(
                    traceback.format_exception(
                        exc_type, exc_value, traceback_obj
                    )
                )
            except Exception:
                tb_text = f"{exc_type.__name__}: {exc_value}"
            logger.debug("初始化期间捕获异常（被抑制）: %s", tb_text)

            # 使用统一的非模态通知入口展示初始化错误
            try:
                main_window.notify_nonmodal(
                    summary="初始化异常，查看详情",
                    details=tb_text,
                    duration_ms=300000,
                    button_text="查看初始化错误",
                )
            except Exception:
                logger.debug(
                    "在状态栏显示初始化错误入口失败（非致命）", exc_info=True
                )

            return

        # 否则使用原始钩子显示异常
        original_excepthook(exc_type, exc_value, traceback_obj)

    sys.excepthook = custom_excepthook


def main():
    # 设置初始化异常钩子
    _initialize_exception_hook()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # 设置统一字体与样式表（styles.qss）以实现统一主题与可维护的样式
    try:
        from PySide6.QtGui import QFont

        app.setFont(QFont("Segoe UI", 10))
    except Exception:
        logger.debug("设置应用字体失败（非致命）", exc_info=True)
    # 按系统主题自动加载明/暗样式
    try:

        def _is_windows_dark_mode() -> bool:
            try:
                import platform

                if platform.system().lower() != "windows":
                    return False
                import winreg

                key_path = r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    # 0 表示暗色，1 表示浅色
                    val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                    return int(val) == 0
            except Exception:
                return False

        base_dir = Path(__file__).resolve().parent.parent
        dark = _is_windows_dark_mode()
        qss_file = base_dir / ("styles.dark.qss" if dark else "styles.qss")
        if qss_file.exists():
            with open(qss_file, "r", encoding="utf-8") as fh:
                app.setStyleSheet(fh.read())
        elif dark:
            # 兜底：若无暗色QSS，应用深色调色板
            from PySide6.QtGui import QColor, QPalette

            pal = QPalette()
            pal.setColor(QPalette.Window, QColor(45, 45, 48))
            pal.setColor(QPalette.WindowText, QColor(230, 230, 230))
            pal.setColor(QPalette.Base, QColor(37, 37, 38))
            pal.setColor(QPalette.AlternateBase, QColor(45, 45, 48))
            pal.setColor(QPalette.ToolTipBase, QColor(45, 45, 48))
            pal.setColor(QPalette.ToolTipText, QColor(230, 230, 230))
            pal.setColor(QPalette.Text, QColor(230, 230, 230))
            pal.setColor(QPalette.Button, QColor(45, 45, 48))
            pal.setColor(QPalette.ButtonText, QColor(230, 230, 230))
            pal.setColor(QPalette.BrightText, QColor(255, 0, 0))
            pal.setColor(QPalette.Highlight, QColor(0, 120, 215))
            pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
            app.setPalette(pal)
    except Exception:
        logger.debug("自动主题加载失败（忽略）", exc_info=True)
    window = IntegratedAeroGUI()
    window.show()
    try:
        sys.exit(app.exec())
    except Exception as e:
        logger.error("运行失败: %s", e)
    finally:
        logger.info("收到中断信号(Ctrl+C)，正在退出应用")
