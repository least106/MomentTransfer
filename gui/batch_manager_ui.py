"""BatchManager UI 相关辅助函数模块。

此模块包含与 UI 信号连接、SignalBus 事件绑定以及快速筛选连接相关的逻辑，
设计为可由 `BatchManager` 委托调用以便拆分主模块责任。
"""

import logging
from typing import Any

from gui.status_message_queue import MessagePriority

logger = logging.getLogger(__name__)

try:
    from gui.managers import _report_ui_exception
except Exception:
    _report_ui_exception = None


def _notify_nonfatal(manager: Any, message: str) -> None:
    """统一的非致命提示：日志+可选 UI 提示。"""
    try:
        logger.warning(message)
    except Exception:
        pass
    try:
        gui = getattr(manager, "gui", None)
        if _report_ui_exception and gui is not None:
            _report_ui_exception(gui, message)
    except Exception:
        logger.debug("非致命提示失败（忽略）", exc_info=True)


def connect_ui_signals(manager: Any) -> bool:
    """连接文件树与 UI 回调（由 BatchManager 委托调用）。

    返回 True 表示至少建立了一次成功连接；返回 False 表示尚未建立任何连接。
    仅在至少一次成功连接后才设置 manager._ui_signals_connected 为 True。
    """
    try:
        if getattr(manager, "_ui_signals_connected", False):
            return True
        gui = manager.gui
        made_connection = False
        def _connect_file_tree(signal_name: str, handler_name: str) -> None:
            nonlocal made_connection
            try:
                bm = getattr(gui, "batch_manager", None) or manager
                handler = getattr(bm, handler_name, None)
                if not callable(handler):
                    return
                sig = getattr(gui.file_tree, signal_name, None)
                if sig is None:
                    return
                try:
                    sig.connect(handler)
                    made_connection = True
                except Exception:
                    logger.debug(
                        f"连接 file_tree.{signal_name} 失败", exc_info=True
                    )
            except Exception:
                logger.debug(f"连接 file_tree {signal_name} 失败", exc_info=True)

        if hasattr(gui, "file_tree") and gui.file_tree is not None:
            # 同时连接单击与双击：部分平台/样式可能只触发单击或双击事件之一
            # 但在处理器内部已有旧 selector 清理逻辑以避免重复创建控件
            _connect_file_tree("itemClicked", "_on_file_tree_item_clicked")
            _connect_file_tree("itemDoubleClicked", "_on_file_tree_item_clicked")
            _connect_file_tree("itemChanged", "_on_file_tree_item_changed")
        else:
            try:
                if not getattr(manager, "_file_tree_missing_warned", False):
                    _notify_nonfatal(manager, "文件树未就绪，无法连接文件树信号")
                    manager._file_tree_missing_warned = True
            except Exception:
                _notify_nonfatal(manager, "文件树未就绪，无法连接文件树信号")

        if made_connection:
            try:
                setattr(manager, "_ui_signals_connected", True)
            except Exception:
                pass
        else:
            _notify_nonfatal(manager, "未能连接任何文件树信号")
        return bool(made_connection)
    except Exception:
        logger.debug("connect_ui_signals 失败", exc_info=True)
        _notify_nonfatal(manager, "连接文件树信号失败")
        return False


def connect_signal_bus_events(manager: Any) -> bool:
    """将 SignalBus 的配置/part 变更事件绑定到 manager 的刷新方法（仅注册一次）。"""
    try:
        if getattr(manager, "_bus_connected", False):
            return True
        gui = manager.gui
        bus = getattr(gui, "signal_bus", None)
        if bus is None:
            _notify_nonfatal(manager, "事件总线未就绪，无法绑定状态刷新信号")
            return False
        handler = getattr(manager, "_safe_refresh_file_statuses", None)
        made = False
        if callable(handler):
            try:
                bus.configLoaded.connect(handler)
                made = True
            except Exception:
                pass
            try:
                bus.configApplied.connect(handler)
                made = True
            except Exception:
                pass
            try:
                bus.partAdded.connect(handler)
                made = True
            except Exception:
                pass
            try:
                bus.partRemoved.connect(handler)
                made = True
            except Exception:
                pass
            try:
                bus.sourcePartChanged.connect(handler)
                made = True
            except Exception:
                pass
            try:
                bus.targetPartChanged.connect(handler)
                made = True
            except Exception:
                pass
        else:
            _notify_nonfatal(manager, "缺少 _safe_refresh_file_statuses 回调")
        if made:
            try:
                setattr(manager, "_bus_connected", True)
            except Exception:
                pass
        else:
            _notify_nonfatal(manager, "未能连接任何 SignalBus 事件")
        return bool(made)
    except Exception:
        logger.debug("connect_signal_bus_events 失败", exc_info=True)
        _notify_nonfatal(manager, "绑定 SignalBus 事件失败")
        return False


def connect_quick_filter(manager: Any) -> None:
    """连接快速筛选面板的变化信号到 manager 的回调。"""
    try:
        gui = manager.gui
        made = False
        if hasattr(gui, "batch_panel") and hasattr(
            gui.batch_panel, "quickFilterChanged"
        ):
            handler = getattr(manager, "_on_quick_filter_changed", None)
            if callable(handler):
                try:
                    gui.batch_panel.quickFilterChanged.connect(handler)
                    logger.info("快速筛选信号连接成功")
                    made = True
                except Exception as e:
                    logger.error(f"连接快速筛选信号失败: {e}", exc_info=True)
                    _notify_nonfatal(manager, "连接快速筛选信号失败")
            else:
                logger.warning(
                    "快速筛选信号连接失败：manager 未提供 _on_quick_filter_changed 回调"
                )
                _notify_nonfatal(manager, "未提供快速筛选回调，无法连接信号")
        else:
            logger.debug(
                "快速筛选信号连接失败：batch_panel 或 quickFilterChanged 不存在"
            )
            _notify_nonfatal(manager, "快速筛选组件未就绪，无法连接信号")
        return bool(made)
    except Exception:
        logger.debug("connect_quick_filter 失败", exc_info=True)
        _notify_nonfatal(manager, "连接快速筛选信号失败")
        return False


def safe_refresh_file_statuses(manager: Any, *args, **kwargs) -> None:
    """容错包装：安全调用 manager.refresh_file_statuses。

    当配置或 parts 发生变化时，通过 SignalBus 触发此方法，
    自动刷新文件树中所有文件的验证状态显示。
    """
    try:
        logger.info("响应配置/Part变更，刷新文件验证状态")
        manager.refresh_file_statuses()
        # 刷新完成后通知用户
        try:
            from gui.signal_bus import SignalBus

            bus = SignalBus.instance()
            bus.statusMessage.emit(
                "文件验证状态已更新",
                3000,
                MessagePriority.LOW,
            )
        except Exception:
            logger.debug("发送状态更新消息失败", exc_info=True)
    except Exception:
        logger.debug("调用 refresh_file_statuses 失败", exc_info=True)
