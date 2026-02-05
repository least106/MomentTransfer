"""
MomentConversion GUI 主窗口模块
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
import sys
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEventLoop, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QWidget,
    QVBoxLayout,
)

from gui.dialog_helpers import (
    show_error_dialog,
    show_info_dialog,
    show_yes_no_cancel_dialog,
)

# 导入事件和日志管理器
from gui.event_manager import EventManager
from gui.initialization_manager import InitializationManager

# 从模块化包导入组件
# Mpl3DCanvas 延迟加载以加快启动速度（在首次调用show_visualization时加载）
from gui.log_manager import LoggingManager
from gui.managers import FileSelectionManager, ModelManager, UIStateManager

# 导入面板组件
from gui.panels import ConfigPanel, OperationPanel, PartMappingPanel

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
        self.setWindowTitle("MomentConversion")
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

        # 状态消息管理器占位符（在初始化时创建）
        self.status_message_manager = None

        # 状态消息队列：处理优先级与多来源竞争
        try:
            from gui.status_message_queue import StatusMessageQueue

            self._status_message_queue = StatusMessageQueue()
        except Exception:
            self._status_message_queue = None
            logger.debug("初始化状态消息队列失败（非致命）", exc_info=True)

        # 管理器占位（将由 InitializationManager 初始化）
        self.config_manager = None
        self.part_manager = None
        self.batch_manager = None
        self.layout_manager = None

        # 面板注册表：集中管理面板实例，避免多处重复赋值
        self._panels = {}
        # 继续执行剩余的初始化逻辑（因代码结构调整，这里调用专用方法完成）
        try:
            # 延迟调用，以便下面定义的方法可用
            self._finish_init()
        except Exception:
            logger.debug("_finish_init 调用失败（非致命）", exc_info=True)

    def register_panel(self, name: str, widget, *, overwrite: bool = False) -> None:
        """集中注册面板并在需要时警告重复赋值。

        - `name` 是属性名（例如 'operation_panel' 或 'config_panel'）。
        - 若已有同名面板且 `overwrite` 为 False，则记录警告并保持原值。
        - 同时以属性形式保留向后兼容性（`self.<name>`）。
        """
        try:
            if not name or not isinstance(name, str):
                return
            # 类型校验：必须是 QWidget 或其子类
            try:
                if widget is None or not isinstance(widget, QWidget):
                    logger.warning(
                        "register_panel ignored: '%s' is not QWidget (got=%r)",
                        name,
                        type(widget),
                    )
                    return
            except Exception:
                logger.debug("register_panel 类型检查失败（非致命）", exc_info=True)
                return
            existing = self._panels.get(name, None)
            if existing is not None and not overwrite:
                logger.warning(
                    "attempt to re-register panel '%s' ignored (existing=%r)",
                    name,
                    type(existing),
                )
                return
            # 保存到内部映射并设置为属性以保持兼容
            self._panels[name] = widget
            try:
                setattr(self, name, widget)
            except Exception:
                logger.debug("无法将面板 %s 设置为属性（非致命）", name, exc_info=True)
        except Exception:
            logger.debug("register_panel failed for %s", name, exc_info=True)

    def _finish_init(self):
        """Finish initialization steps extracted from original __init__."""
        # 简化与稳定化的初始化序列：保持最小防护以减少嵌套 try/except 导致的缩进错误。
        # 设定兼容回退字段与管理器引用
        try:
            self._legacy_data_loaded = False
            self._legacy_config_loaded = False
            self._legacy_operation_performed = False
            self.initialization_manager = InitializationManager(self)
            self.event_manager = EventManager(self)
            self._status_priority = 0
            self._status_clear_timer = None
            self._status_token = None
        except Exception:
            logger.debug("setting basic init fields failed", exc_info=True)

        # 调用 setup_ui 并保证异常被记录，但不阻止后续步骤
        try:
            self.initialization_manager.setup_ui()
        except Exception:
            logger.exception("InitializationManager.setup_ui() failed")

        for name in ("setup_managers", "setup_logging", "bind_post_ui_signals"):
            try:
                fn = getattr(self.initialization_manager, name, None)
                if callable(fn):
                    fn()
            except Exception:
                logger.debug(f"{name} failed (non-fatal)", exc_info=True)

        # 回退：确保至少有一个 central widget
        try:
            if not bool(self.centralWidget()):
                from PySide6.QtWidgets import QVBoxLayout, QWidget

                fallback = QWidget()
                try:
                    fallback.setLayout(QVBoxLayout())
                except Exception:
                    pass
                try:
                    self.setCentralWidget(fallback)
                except Exception:
                    try:
                        self.central_widget = fallback
                    except Exception:
                        logger.debug("无法设置回退 central_widget", exc_info=True)
                try:
                    if getattr(self, "initialization_manager", None):
                        try:
                            self.initialization_manager._hide_initializing_overlay()
                        except Exception:
                            logger.debug("回退时隐藏初始化遮罩失败", exc_info=True)
                except Exception:
                    pass
                logger.info("已创建回退 central_widget 以避免空白界面")
        except Exception:
            logger.debug("post-init central_widget diagnostic failed", exc_info=True)

        # 连接 SignalBus 的统一状态消息信号，用于协调各处的状态提示
        try:
            sb = (
                getattr(self, "signal_bus", None)
                or __import__(
                    "gui.signal_bus", fromlist=["SignalBus"]
                ).SignalBus.instance()
            )
            try:
                sb.statusMessage.connect(self._on_status_message)
            except Exception:
                logger.debug("连接 statusMessage 信号失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("获取 SignalBus 失败（非致命）", exc_info=True)

        # 确保 statusBar 存在：不要用 hasattr(self, "statusBar")，该方法总是存在
        try:
            try:
                sb = self.statusBar()
            except Exception:
                sb = None
            if sb is None:
                from PySide6.QtWidgets import QStatusBar

                try:
                    self.setStatusBar(QStatusBar(self))
                except Exception:
                    logger.debug("设置 QStatusBar 失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("确保 statusBar 存在失败（非致命）", exc_info=True)

        # 初始化期间发生的非致命通知入队，初始化结束后再尝试展示
        try:
            self._pending_init_notifications = []
        except Exception:
            self._pending_init_notifications = []

        # 初始化完成：解除初始化保护并刷新挂起通知
        try:
            self._is_initializing = False
            # 隐藏可能残留的初始化遮罩（某些启动路径会在 InitializationManager 中创建遮罩）
            try:
                if getattr(self, "initialization_manager", None):
                    self.initialization_manager._hide_initializing_overlay()
            except Exception:
                logger.debug("隐藏初始化遮罩失败（非致命）", exc_info=True)

            try:
                if getattr(self, "_pending_init_notifications", None):
                    self._flush_init_notifications()
            except Exception:
                logger.debug("刷新初始化挂起通知失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("设置 _is_initializing=False 失败（非致命）", exc_info=True)

    def _init_notification_container(self) -> None:
        """初始化状态栏通知容器（首次调用时）。专用容器管理通知按钮，避免残留与占位问题。"""
        try:
            if getattr(self, "_notification_container", None) is not None:
                return
            from PySide6.QtWidgets import QHBoxLayout, QWidget

            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            self._notification_container = container
            self._notification_layout = layout
            try:
                self.statusBar().addPermanentWidget(container)
            except Exception:
                logger.debug("添加通知容器到状态栏失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("初始化通知容器失败（非致命）", exc_info=True)

    def _flush_init_notifications(self):
        """在初始化完成后展示或记录在初始化期间积累的通知。"""
        try:
            pending = getattr(self, "_pending_init_notifications", None) or []
            remaining = []
            for item in pending:
                try:
                    summary, details, duration_ms, button_text = item
                except Exception:
                    # 非法条目跳过并记录
                    logger.debug("初始化通知条目格式非法，已跳过: %r", item)
                    continue

                try:
                    sb = None
                    try:
                        sb = self.statusBar()
                    except Exception:
                        sb = None

                    # 仅当窗口可见且 statusBar 可用时直接展示
                    if self.isVisible() and sb is not None:
                        try:
                            self.notify_nonmodal(
                                summary=summary,
                                details=details,
                                duration_ms=duration_ms,
                                button_text=button_text,
                            )
                            # 已展示，跳过重试队列
                            continue
                        except Exception:
                            logger.debug(
                                "显示初始化通知失败，回退为日志记录", exc_info=True
                            )

                    # 若无法展示，保留到 remaining 以便稍后在 showEvent 中重试
                    remaining.append(item)
                except Exception:
                    # 若处理单条通知时发生不可预期的错误，记录并继续处理其他条目
                    logger.debug("处理挂起通知时发生错误（非致命）", exc_info=True)

            # 将未能展示的通知保留在队列中，避免丢失；限制队列长度以防内存无限增长
            try:
                max_keep = 50
                if len(remaining) > max_keep:
                    logger.warning(
                        "初始化通知队列过长（%d），丢弃最旧的 %d 条。",
                        len(remaining),
                        len(remaining) - max_keep,
                    )
                    remaining = remaining[-max_keep:]
                self._pending_init_notifications = remaining
            except Exception:
                # 最后兜底：若无法修改属性，记录并清空局部变量
                logger.debug(
                    "无法更新 _pending_init_notifications 引用（非致命）", exc_info=True
                )
        except Exception:
            logger.debug("刷新初始化通知队列失败（非致命）", exc_info=True)

    def _reset_status_clear_timer(self) -> None:
        """停止并释放状态栏清理定时器（集中管理，避免多处重复清理）。"""
        try:
            t_old = getattr(self, "_status_clear_timer", None)
            if t_old is None:
                return
            try:
                t_old.stop()
            except Exception:
                logger.debug("停止旧状态清理定时器失败（非致命）", exc_info=True)
            try:
                t_old.deleteLater()
            except Exception:
                logger.debug("释放旧状态清理定时器失败（非致命）", exc_info=True)
            self._status_clear_timer = None
        except Exception:
            logger.debug("重置状态清理定时器失败（非致命）", exc_info=True)

    def _clear_status_state(self) -> None:
        """清理状态栏 token 与 timer，保证原子替换。"""
        try:
            self._reset_status_clear_timer()
        except Exception:
            pass
        try:
            self._status_token = None
        except Exception:
            logger.debug("清理状态 token 失败（非致命）", exc_info=True)

    def _start_status_timer(self, timeout_ms: int, token: str) -> None:
        """为当前 token 启动状态栏清理定时器。"""
        try:
            t = QTimer(self)
            t.setSingleShot(True)
            t.timeout.connect(lambda tok=token: self._clear_status_if_token(tok))
            t.start(int(timeout_ms))
            self._status_clear_timer = t
        except Exception:
            logger.debug("启动状态清理定时器失败（非致命）", exc_info=True)

    def _on_status_message(self, message: str, timeout_ms: int, priority: int) -> None:
        """统一处理状态消息：按优先级显示，并在超时后清理。

        使用队列机制确保：
        - 高优先级消息不被低优先级覆盖
        - 并发消息按优先级与时间戳排序
        - 消息超时后自动清理并显示下一条
        """
        try:
            # 确保有队列
            if self._status_message_queue is None:
                return

            from gui.status_message_queue import StatusMessage

            # 创建新消息对象
            new_msg = StatusMessage(
                text=message,
                timeout_ms=int(timeout_ms) if timeout_ms else 0,
                priority=int(priority) if priority is not None else 0,
                source="signal",
            )

            # 检查是否应接受此消息
            should_accept, interrupt_token = (
                self._status_message_queue.should_accept_message(new_msg)
            )
            if not should_accept:
                # 新消息优先级低，加入队列但不显示
                self._status_message_queue.add_message(
                    message, timeout_ms, priority, "signal"
                )
                return

            # 如果需要中断当前消息，清除其定时器
            if interrupt_token is not None:
                try:
                    t_old = getattr(self, "_status_clear_timer", None)
                    if t_old is not None:
                        try:
                            t_old.stop()
                        except Exception:
                            pass
                except Exception:
                    logger.debug("清除旧定时器失败（非致命）", exc_info=True)

            # 添加消息到队列
            self._status_message_queue.add_message(
                message, timeout_ms, priority, "signal"
            )

            # 显示当前应显示的消息（队列顶部）
            msg_to_display = self._status_message_queue.get_next_message()
            if msg_to_display is not None:
                self._display_status_message(msg_to_display)
        except Exception:
            logger.debug("处理 statusMessage 信号失败", exc_info=True)

    def _display_status_message(self, msg) -> None:
        """显示指定的状态消息并设置超时。

        Args:
            msg: StatusMessage 对象
        """
        try:
            # 记录当前显示的消息
            self._status_message_queue.set_current_message(msg)

            # 在状态栏显示消息
            try:
                sb = self.statusBar()
                if sb is not None:
                    sb.showMessage(msg.text)
            except Exception:
                logger.debug("显示状态栏消息失败", exc_info=True)

            # 设置超时定时器
            if msg.timeout_ms > 0:
                try:
                    self._start_status_timer(msg.timeout_ms, msg.token)
                except Exception:
                    logger.debug("设置状态清理定时器失败（非致命）", exc_info=True)
            else:
                # 永久显示，不设置定时器
                pass
        except Exception:
            logger.debug("显示状态消息失败（非致命）", exc_info=True)

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
                self._clear_status_state()
            except Exception:
                pass
        except Exception:
            logger.debug("清理状态消息失败", exc_info=True)

    def _clear_status_if_token(self, token: str) -> None:
        """按 token 清理消息，然后显示队列中的下一条消息（如果有的话）。"""
        try:
            # 检查队列是否存在
            if self._status_message_queue is None:
                # 回退到旧的清理逻辑
                cur_tok = getattr(self, "_status_token", None)
                if cur_tok != token:
                    return
                try:
                    sb = self.statusBar()
                    if sb is not None:
                        sb.clearMessage()
                except Exception:
                    logger.debug("清理状态栏消息失败（非致命）", exc_info=True)
                return

            # 检查是否是当前显示的消息的 token
            if not self._status_message_queue.message_is_current(token):
                return

            # 从队列中移除此消息
            self._status_message_queue.remove_message(token)

            # 显示队列中的下一条消息
            next_msg = self._status_message_queue.get_next_message()
            if next_msg is not None:
                self._display_status_message(next_msg)
            else:
                # 队列为空，清空状态栏
                try:
                    sb = self.statusBar()
                    if sb is not None:
                        sb.clearMessage()
                except Exception:
                    logger.debug("清理状态栏消息失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("按 token 清理状态消息失败", exc_info=True)

    def set_config_panel_visible(self, visible: bool) -> None:
        """按流程显示/隐藏配置编辑器，减少初始化干扰。"""
        # 将具体实现委托给 UIStateManager，主窗口保留向后兼容行为
        try:
            self.ui_state_manager.set_config_panel_visible(visible)
        except Exception:
            logger.debug("set_config_panel_visible failed", exc_info=True)

    # 属性代理：将局部标志代理到 `UIStateManager`，使 `UIStateManager` 成为单一可信来源。
    @property
    def data_loaded(self) -> bool:
        try:
            if getattr(self, "ui_state_manager", None):
                try:
                    return bool(self.ui_state_manager.is_data_loaded())
                except Exception:
                    return bool(getattr(self, "_legacy_data_loaded", False))
            return bool(getattr(self, "_legacy_data_loaded", False))
        except Exception:
            return False

    @data_loaded.setter
    def data_loaded(self, val: bool) -> None:
        """设置数据加载标志。委托给 UIStateManager，避免回写递归。"""
        try:
            if getattr(self, "ui_state_manager", None):
                try:
                    # 直接更新 UIStateManager 内部状态，不依赖属性写回
                    self.ui_state_manager.set_data_loaded(bool(val))
                    return
                except Exception:
                    logger.debug(
                        "ui_state_manager.set_data_loaded failed in setter",
                        exc_info=True,
                    )
            # 回退：使用 object.__setattr__ 直接修改本地字段，避免属性递归
            try:
                object.__setattr__(self, "_legacy_data_loaded", bool(val))
            except Exception:
                pass
        except Exception:
            logger.debug("setting data_loaded failed", exc_info=True)

    @property
    def config_loaded(self) -> bool:
        try:
            if getattr(self, "ui_state_manager", None):
                try:
                    return bool(self.ui_state_manager.is_config_loaded())
                except Exception:
                    return bool(getattr(self, "_legacy_config_loaded", False))
            return bool(getattr(self, "_legacy_config_loaded", False))
        except Exception:
            return False

    @config_loaded.setter
    def config_loaded(self, val: bool) -> None:
        """设置配置加载标志。委托给 UIStateManager，避免回写递归。"""
        try:
            if getattr(self, "ui_state_manager", None):
                try:
                    self.ui_state_manager.set_config_loaded(bool(val))
                    return
                except Exception:
                    logger.debug(
                        "ui_state_manager.set_config_loaded failed in setter",
                        exc_info=True,
                    )
            # 回退：使用 object.__setattr__ 直接修改本地字段，避免属性递归
            try:
                object.__setattr__(self, "_legacy_config_loaded", bool(val))
            except Exception:
                pass
        except Exception:
            logger.debug("setting config_loaded failed", exc_info=True)

    @property
    def operation_performed(self) -> bool:
        try:
            if getattr(self, "ui_state_manager", None):
                try:
                    return bool(self.ui_state_manager.is_operation_performed())
                except Exception:
                    return bool(getattr(self, "_legacy_operation_performed", False))
            return bool(getattr(self, "_legacy_operation_performed", False))
        except Exception:
            return False

    @operation_performed.setter
    def operation_performed(self, val: bool) -> None:
        """设置操作执行标志。委托给 UIStateManager，避免回写递归。"""
        try:
            if getattr(self, "ui_state_manager", None):
                try:
                    self.ui_state_manager.set_operation_performed(bool(val))
                    return
                except Exception:
                    logger.debug(
                        "ui_state_manager.set_operation_performed failed in setter",
                        exc_info=True,
                    )
            # 回退：使用 object.__setattr__ 直接修改本地字段，避免属性递归
            try:
                object.__setattr__(self, "_legacy_operation_performed", bool(val))
            except Exception:
                pass
        except Exception:
            logger.debug("setting operation_performed failed", exc_info=True)

    def mark_data_loaded(self) -> None:
        """标记已加载数据文件并刷新控件状态"""
        try:
            # 统一入口：通过属性写入（属性会代理到 UIStateManager 或回退字段）
            self.data_loaded = True
            self._refresh_controls_state()
        except Exception:
            logger.debug("mark_data_loaded failed", exc_info=True)

    def mark_config_loaded(self) -> None:
        """标记已加载配置并刷新控件状态"""
        try:
            # 统一入口：通过属性写入（属性会代理到 UIStateManager 或回退字段）
            self.config_loaded = True
            self._refresh_controls_state()
        except Exception:
            logger.debug("mark_config_loaded failed", exc_info=True)

    def mark_user_modified(self) -> None:
        """标记为用户已修改（用于启用保存按钮）。

        与 data_loaded/config_loaded 区分，避免仅加载即启用保存。
        """
        try:
            # 统一入口：通过属性写入（属性会代理到 UIStateManager 或回退字段）
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

    def create_part_mapping_panel(self):
        """创建文件 Part 映射面板（由 InitializationManager 调用）"""
        panel = PartMappingPanel(self)
        return panel

    def _select_all_files(self):
        """委托给 BatchManager 全选文件（兼容旧接口）。"""
        try:
            if self.batch_manager:
                try:
                    self.batch_manager.select_all_files()
                except Exception:
                    logger.debug(
                        "batch_manager.select_all_files 调用失败", exc_info=True
                    )
        except Exception:
            logger.debug("_select_all_files failed", exc_info=True)

    def _select_none_files(self):
        """委托给 BatchManager 全不选文件（兼容旧接口）。"""
        try:
            if self.batch_manager:
                try:
                    self.batch_manager.select_none_files()
                except Exception:
                    logger.debug(
                        "batch_manager.select_none_files 调用失败", exc_info=True
                    )
        except Exception:
            logger.debug("_select_none_files failed", exc_info=True)

    def _invert_file_selection(self):
        """委托给 BatchManager 反选文件（兼容旧接口）。"""
        try:
            if self.batch_manager:
                try:
                    self.batch_manager.invert_file_selection()
                except Exception:
                    logger.debug(
                        "batch_manager.invert_file_selection 调用失败", exc_info=True
                    )
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
                    logger.debug(
                        "batch_manager.open_quick_select_dialog 调用失败", exc_info=True
                    )

            # 回退：若存在 file_selection_manager，使用其快速选择逻辑
            try:
                fsm = getattr(self, "file_selection_manager", None)
                if fsm and hasattr(fsm, "open_quick_select_dialog"):
                    try:
                        fsm.open_quick_select_dialog()
                        return
                    except Exception:
                        logger.debug(
                            "file_selection_manager.open_quick_select_dialog 调用失败",
                            exc_info=True,
                        )
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
    # 已移除全局数据格式配置功能（改为按文件/目录自动识别）

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
            from datetime import datetime

            from PySide6.QtWidgets import QFileDialog

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
                            show_info_dialog(self, "成功", f"项目已保存到: {saved_fp}")
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
                    logger.debug(
                        "直接保存当前项目失败，退回到另存为对话", exc_info=True
                    )

            # 另存为：预填当前路径或建议文件名 project_YYYYMMDD.mtproject
            default_dir = ""
            pm = getattr(self, "project_manager", None)
            ext = (
                getattr(pm.__class__, "PROJECT_FILE_EXTENSION", ".mtproject")
                if pm
                else ".mtproject"
            )
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
            start_path = (
                str(Path(default_dir) / suggested) if default_dir else suggested
            )
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存Project文件",
                start_path,
                "MomentConversion Project (*.mtproject);;All Files (*)",
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
                            show_info_dialog(self, "成功", f"项目已保存到: {saved_fp}")
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

                    self.project_manager.save_project_async(
                        Path(file_path), on_finished=_on_saved2
                    )
        except Exception as e:
            logger.error("保存Project失败: %s", e)
            try:
                if hasattr(self, "notify_nonmodal") and callable(self.notify_nonmodal):
                    self.notify_nonmodal(
                        summary="保存项目失败",
                        details=f"保存Project失败: {e}",
                        duration_ms=10000,
                    )
                else:
                    self.statusBar().showMessage(f"保存Project失败: {e}", 10000)
            except Exception:
                logger.debug("无法显示保存失败对话框（非致命）", exc_info=True)

    def _new_project(self):
        """创建新Project"""
        try:
            # create_new_project 内部已经处理保存确认逻辑
            if self.project_manager:
                if self.project_manager.create_new_project(skip_confirm=False):
                    # 不再弹出成功对话框，状态横幅已显示
                    try:
                        self.signal_bus.statusMessage.emit(
                            "新项目已创建", 3000, 1  # MessagePriority.MEDIUM
                        )
                    except Exception:
                        logger.debug("发送状态消息失败（非致命）", exc_info=True)
        except Exception as e:
            logger.error("创建新Project失败: %s", e)
            show_error_dialog(self, "错误", f"创建新项目失败: {e}")

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
                "MomentConversion Project (*.mtproject);;All Files (*)",
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
                            show_info_dialog(self, "成功", f"项目已加载: {loaded_fp}")
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

                    self.project_manager.load_project_async(
                        Path(file_path), on_finished=_on_loaded
                    )
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
                                return bool(
                                    self.ui_state_manager.is_operation_performed()
                                )
                            except Exception:
                                return bool(getattr(self, "operation_performed", False))
                        return bool(getattr(self, "operation_performed", False))
                    return current != last
                except Exception:
                    logger.debug(
                        "比较项目状态时出错，退回到 UI 标志检测", exc_info=True
                    )
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
            def _wait_for_async_save(start_async, dlg, timeout_ms: int = 15000) -> bool:
                """等待异步保存完成，带超时保护。"""
                loop = QEventLoop()
                result = {"saved": False, "timed_out": False}
                timer = QTimer(self)
                timer.setSingleShot(True)

                def _on_timeout():
                    result["timed_out"] = True
                    try:
                        dlg.close()
                    except Exception:
                        pass
                    try:
                        loop.quit()
                    except Exception:
                        pass

                timer.timeout.connect(_on_timeout)
                timer.start(int(timeout_ms))

                def _on_saved(success, saved_fp):
                    try:
                        result["saved"] = bool(success)
                    except Exception:
                        result["saved"] = False
                    try:
                        timer.stop()
                    except Exception:
                        pass
                    try:
                        dlg.close()
                    except Exception:
                        pass
                    if success:
                        show_info_dialog(self, "成功", f"项目已保存到: {saved_fp}")
                    else:
                        show_error_dialog(self, "错误", "项目保存失败")
                    try:
                        loop.quit()
                    except Exception:
                        pass

                try:
                    start_async(_on_saved)
                    loop.exec()
                except Exception:
                    logger.exception("异步保存项目失败")
                    try:
                        dlg.close()
                    except Exception:
                        pass
                    return False

                if result.get("timed_out"):
                    show_error_dialog(self, "错误", "项目保存超时，请重试")
                    return False
                return bool(result.get("saved"))

            msg = QMessageBox(self)
            msg.setWindowTitle("未保存更改")
            msg.setText(f"检测到未保存的更改。是否在执行“{intent}”前保存更改？")
            # UX：这里的“放弃”语义应为“本次不保存仍继续”，而不是立刻把未保存标记清掉。
            # 否则若用户后续取消“打开文件”对话框，或“打开/新建”失败，会导致未保存状态被错误清除。
            msg.setInformativeText(
                "保存：保存更改并继续；放弃：本次不保存并继续；取消：返回。"
            )
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
                            ok = _wait_for_async_save(
                                lambda cb: pm.save_project_async(cur_fp, on_finished=cb),
                                dlg,
                            )
                            if not ok:
                                return False

                        else:
                            # 否则弹出另存为对话并异步保存
                            try:
                                from PySide6.QtWidgets import QFileDialog

                                pm = getattr(self, "project_manager", None)
                                ext = (
                                    getattr(
                                        pm.__class__,
                                        "PROJECT_FILE_EXTENSION",
                                        ".mtproject",
                                    )
                                    if pm
                                    else ".mtproject"
                                )
                                suggested = (
                                    f"project_{datetime.now().strftime('%Y%m%d')}{ext}"
                                )
                                start = str(Path.cwd() / suggested)
                                save_path, _ = QFileDialog.getSaveFileName(
                                    self,
                                    "保存 Project 文件",
                                    start,
                                    "MomentConversion Project (*.mtproject);;All Files (*)",
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
                                ok = _wait_for_async_save(
                                    lambda cb: pm.save_project_async(
                                        Path(save_path), on_finished=cb
                                    ),
                                    dlg,
                                )
                                if not ok:
                                    return False
                            except Exception:
                                logger.debug(
                                    "另存为对话或保存过程中出错", exc_info=True
                                )
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
                    _report_ui_exception(
                        self, "未保存更改对话弹出失败（已自动取消操作）"
                    )
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
                show_info_dialog(
                    self,
                    "功能暂不可用",
                    "系统尚未就绪（正在初始化或管理器未启动），请稍候再试。",
                )
                return

            # 检查配置是否被修改
            if self.config_manager and self.config_manager.is_config_modified():
                # 配置已修改，弹出对话框确认用户是否继续或先保存
                result = show_yes_no_cancel_dialog(
                    self,
                    "未保存的配置",
                    "检测到配置文件有未保存的修改。\n\n是否保存配置后再运行批处理？",
                )

                if result == "yes":
                    # 用户选择保存，先保存配置
                    if self.config_manager.save_config():
                        # 保存成功，继续批处理
                        self.batch_manager.run_batch_processing()
                    else:
                        # 保存失败或用户取消，不继续批处理
                        logger.warning("用户取消保存配置或保存失败，批处理已中止")
                        return
                elif result == "no":
                    # 用户选择不保存，继续使用当前未保存配置运行批处理
                    logger.warning("批处理将使用未保存的配置")
                    try:
                        self.statusBar().showMessage(
                            "警告：批处理将使用当前未保存的配置", 5000
                        )
                    except Exception:
                        pass
                    self.batch_manager.run_batch_processing()
                else:
                    # 用户取消，不运行批处理
                    logger.info("用户取消了批处理")
                    return
            else:
                # 配置未修改，直接运行批处理
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
                    handled = bool(self.batch_manager.on_batch_error(error_msg))
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
            logger.debug("on_batch_error top-level delegation failed", exc_info=True)

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
                    "建议：检查输入文件的格式定义与解析规则，"
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
                    logger.debug("复制错误到剪贴板失败（非致命）", exc_info=True)

            def _open_log():
                try:
                    from pathlib import Path

                    # 优先通过 LoggingManager 获取日志路径（若可用）
                    try:
                        from gui.log_manager import LoggingManager

                        lm = LoggingManager(self)
                        log_file = lm.get_log_file_path() or (
                            Path.home() / ".momentconversion" / "momentconversion.log"
                        )
                    except Exception:
                        log_file = (
                            Path.home() / ".momentconversion" / "momentconversion.log"
                        )

                    log_dir = log_file.parent
                    if log_file.exists():
                        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_file)))
                    elif log_dir.exists():
                        # 若日志文件不存在但目录存在，打开目录以便用户查看或收集日志
                        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir)))
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

    def _reset_notification_timer(self) -> None:
        """停止并释放非模态通知定时器（集中管理）。"""
        try:
            t_old = getattr(self, "_notification_timer", None)
            if t_old is None:
                return
            try:
                t_old.stop()
            except Exception:
                logger.debug("停止通知定时器失败（非致命）", exc_info=True)
            try:
                t_old.deleteLater()
            except Exception:
                logger.debug("释放通知定时器失败（非致命）", exc_info=True)
            self._notification_timer = None
        except Exception:
            logger.debug("重置通知定时器失败（非致命）", exc_info=True)

    def _clear_notification_state(self) -> None:
        """清理非模态通知的按钮、token 与 timer。从容器布局中移除并释放按钮。"""
        try:
            old = getattr(self, "_notification_btn", None)
            if old is not None:
                try:
                    layout = getattr(self, "_notification_layout", None)
                    if layout is not None:
                        try:
                            layout.removeWidget(old)
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    old.deleteLater()
                except Exception:
                    pass
                self._notification_btn = None
        except Exception:
            logger.debug("清理旧通知按钮失败（非致命）", exc_info=True)
        try:
            self._reset_notification_timer()
        except Exception:
            pass
        try:
            self._notification_token = None
        except Exception:
            pass

    def _remove_nonmodal_notification(self, token: str, summary: str) -> None:
        """按 token 清理非模态通知，从容器布局移除并释放。避免清理到新消息。"""
        try:
            cur_tok = getattr(self, "_notification_token", None)
            if cur_tok != token:
                return
            # 从容器布局移除按钮
            try:
                btn = getattr(self, "_notification_btn", None)
                if btn is not None:
                    try:
                        layout = getattr(self, "_notification_layout", None)
                        if layout is not None:
                            try:
                                layout.removeWidget(btn)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    try:
                        btn.deleteLater()
                    except Exception:
                        pass
                    self._notification_btn = None
            except Exception:
                logger.debug("清除非模态通知按钮失败（非致命）", exc_info=True)
            # 不直接清理状态栏，避免与队列消息互相干扰
            # 停止并清理定时器
            try:
                self._reset_notification_timer()
            except Exception:
                pass
            # 清理 token
            try:
                self._notification_token = None
            except Exception:
                pass
        except Exception:
            logger.debug("清理非模态通知失败（非致命）", exc_info=True)

    def _start_notification_timer(
        self, duration_ms: int, token: str, summary: str
    ) -> None:
        """启动非模态通知计时器。"""
        try:
            t = QTimer(self)
            t.setSingleShot(True)
            t.timeout.connect(
                lambda tok=token, summ=summary: self._remove_nonmodal_notification(
                    tok, summ
                )
            )
            t.start(int(duration_ms))
            self._notification_timer = t
        except Exception:
            logger.debug(
                "notification timer creation failed (non-fatal)",
                exc_info=True,
            )

    def notify_nonmodal(
        self,
        summary: str,
        details: str = None,
        duration_ms: int = 120000,
        button_text: str = "查看详情",
    ) -> None:
        """统一的非模态通知：在状态栏显示 summary，并提供查看 details 的非模态入口。

        使用专用容器 widget 管理通知按钮，避免状态栏空间残留与占位问题。
        """
        try:
            # 清理旧通知状态（按钮、token、timer）
            try:
                self._clear_notification_state()
            except Exception:
                pass

            if details is None:
                try:
                    from gui.signal_bus import SignalBus
                    from gui.status_message_queue import MessagePriority

                    SignalBus.instance().statusMessage.emit(
                        summary,
                        int(duration_ms),
                        MessagePriority.MEDIUM,
                    )
                    return
                except Exception:
                    logger.debug(
                        "statusMessage emit failed (non-fatal)",
                        exc_info=True,
                    )

            btn = QPushButton(button_text, self)
            btn.setToolTip(summary)
            btn.clicked.connect(lambda: self._show_non_modal_error_details(details))
            # 生成唯一 token 以绑定该条通知
            try:
                token = uuid.uuid4().hex
                self._notification_token = token
            except Exception:
                token = None
            self._notification_btn = btn
            # 添加按钮到容器（而非直接 addPermanentWidget）
            try:
                # 初始化容器（首次调用时）
                self._init_notification_container()
                layout = getattr(self, "_notification_layout", None)
                if layout is not None:
                    layout.addWidget(btn)
                else:
                    # 容器未成功初始化，回退：仅显示消息
                    try:
                        from gui.signal_bus import SignalBus
                        from gui.status_message_queue import MessagePriority

                        SignalBus.instance().statusMessage.emit(
                            summary,
                            int(duration_ms),
                            MessagePriority.MEDIUM,
                        )
                    except Exception:
                        self.statusBar().showMessage(summary)
            except Exception:
                logger.debug("添加通知按钮到容器失败，回退为消息显示", exc_info=True)
                try:
                    from gui.signal_bus import SignalBus
                    from gui.status_message_queue import MessagePriority

                    SignalBus.instance().statusMessage.emit(
                        summary,
                        int(duration_ms),
                        MessagePriority.MEDIUM,
                    )
                except Exception:
                    pass

            # 启动定时器自动移除
            try:
                if token is not None:
                    self._start_notification_timer(duration_ms, token, summary)
            except Exception:
                pass

            # 通过统一通道显示主消息（与按钮移除计时保持一致）
            try:
                from gui.signal_bus import SignalBus
                from gui.status_message_queue import MessagePriority

                SignalBus.instance().statusMessage.emit(
                    summary,
                    int(duration_ms),
                    MessagePriority.MEDIUM,
                )
            except Exception:
                logger.debug(
                    "statusMessage emit failed after adding button (non-fatal)",
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
        """在窗口首次显示后触发初始化（简化版：移除诊断输出）"""
        try:
            init_mgr = getattr(self, "initialization_manager", None)
            if init_mgr is not None:
                overlay = getattr(init_mgr, "_init_overlay", None)
                if overlay is not None:
                    try:
                        init_mgr._hide_initializing_overlay()
                    except Exception:
                        try:
                            # 兜底尝试再次隐藏
                            init_mgr._hide_initializing_overlay()
                        except Exception:
                            pass
            # 若 central_widget 属性尚未回填，则尝试回填为 Qt 层的 centralWidget()
            try:
                cw_attr = getattr(self, "central_widget", None)
                try:
                    cw_qt = self.centralWidget()
                except Exception:
                    cw_qt = None
                if cw_attr is None and cw_qt is not None:
                    try:
                        self.central_widget = cw_qt
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

        if hasattr(self, "event_manager") and self.event_manager:
            self.event_manager.on_show_event(event)

        # 尝试展示在初始化期间积累的通知（若有）
        try:
            if getattr(self, "_pending_init_notifications", None):
                try:
                    self._flush_init_notifications()
                except Exception:
                    pass
        except Exception:
            pass

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
            logger.debug("_force_layout_refresh delegated call failed", exc_info=True)

    def _refresh_layouts(self):
        """委托给 LayoutManager 刷新布局与按钮布局"""
        try:
            if hasattr(self, "layout_manager") and self.layout_manager:
                try:
                    self.layout_manager.refresh_layouts()
                finally:
                    self.layout_manager.update_button_layout()
        except Exception:
            logger.debug("_refresh_layouts delegated call failed", exc_info=True)

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
            logger.debug("GUI logging setup failed (non-fatal): %s", e, exc_info=True)

    def _set_controls_locked(self, locked: bool):
        """锁定或解锁与配置相关的控件，防止用户在批处理运行期间修改配置。

        locked=True 时禁用；locked=False 时恢复。此方法尽量保持幂等并静默忽略缺失控件。
        """
        try:
            if hasattr(self, "ui_state_manager") and self.ui_state_manager:
                self.ui_state_manager.set_controls_locked(locked)
        except Exception:
            logger.debug("_set_controls_locked delegation failed", exc_info=True)


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
                    traceback.format_exception(exc_type, exc_value, traceback_obj)
                )
            except Exception:
                tb_text = f"{exc_type.__name__}: {exc_value}"
            logger.debug("初始化期间捕获异常（被抑制）: %s", tb_text)

            # 使用统一的非模态通知入口展示初始化错误；若 UI 未就绪则入队等待
            try:
                can_show = False
                try:
                    can_show = bool(
                        main_window.isVisible()
                        and getattr(main_window, "statusBar", None) is not None
                    )
                except Exception:
                    can_show = False

                if can_show:
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
                else:
                    try:
                        # 入队：待初始化结束后由主窗口刷新
                        q = getattr(main_window, "_pending_init_notifications", None)
                        if q is None:
                            try:
                                main_window._pending_init_notifications = []
                                q = main_window._pending_init_notifications
                            except Exception:
                                q = []
                        try:
                            q.append(
                                (
                                    "初始化异常，查看详情",
                                    tb_text,
                                    300000,
                                    "查看初始化错误",
                                )
                            )
                        except Exception:
                            logger.debug("入队初始化通知失败（非致命）", exc_info=True)
                    except Exception:
                        logger.debug("无法入队初始化通知（非致命）", exc_info=True)
            except Exception:
                logger.debug("在处理初始化异常通知时发生错误（非致命）", exc_info=True)

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

                key_path = (
                    r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"
                )
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
