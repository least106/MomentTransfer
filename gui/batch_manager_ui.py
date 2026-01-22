"""BatchManager UI 相关辅助函数模块。

此模块包含与 UI 信号连接、SignalBus 事件绑定以及快速筛选连接相关的逻辑，
设计为可由 `BatchManager` 委托调用以便拆分主模块责任。
"""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)


def connect_ui_signals(manager: Any) -> None:
    """连接文件树与 UI 回调（由 BatchManager 委托调用）。"""
    try:
        if getattr(manager, "_ui_signals_connected", False):
            return
        gui = manager.gui
        if hasattr(gui, "file_tree") and gui.file_tree is not None:

            def _connect_file_tree(signal_name: str, handler_name: str) -> None:
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
                    except Exception:
                        logger.debug(
                            f"连接 file_tree.{signal_name} 失败", exc_info=True
                        )
                except Exception:
                    logger.debug(f"连接 file_tree {signal_name} 失败", exc_info=True)

            _connect_file_tree("itemClicked", "_on_file_tree_item_clicked")
            _connect_file_tree("itemDoubleClicked", "_on_file_tree_item_clicked")
            _connect_file_tree("itemChanged", "_on_file_tree_item_changed")
        try:
            setattr(manager, "_ui_signals_connected", True)
        except Exception:
            pass
    except Exception:
        logger.debug("connect_ui_signals 失败", exc_info=True)


def connect_signal_bus_events(manager: Any) -> None:
    """将 SignalBus 的配置/part 变更事件绑定到 manager 的刷新方法（仅注册一次）。"""
    try:
        if getattr(manager, "_bus_connected", False):
            return
        gui = manager.gui
        bus = getattr(gui, "signal_bus", None)
        if bus is None:
            return
        handler = getattr(manager, "_safe_refresh_file_statuses", None)
        if callable(handler):
            try:
                bus.configLoaded.connect(handler)
            except Exception:
                pass
            try:
                bus.configApplied.connect(handler)
            except Exception:
                pass
            try:
                bus.partAdded.connect(handler)
            except Exception:
                pass
            try:
                bus.partRemoved.connect(handler)
            except Exception:
                pass
        try:
            setattr(manager, "_bus_connected", True)
        except Exception:
            pass
    except Exception:
        logger.debug("connect_signal_bus_events 失败", exc_info=True)


def connect_quick_filter(manager: Any) -> None:
    """连接快速筛选面板的变化信号到 manager 的回调。"""
    try:
        gui = manager.gui
        if hasattr(gui, "batch_panel") and hasattr(
            gui.batch_panel, "quickFilterChanged"
        ):
            handler = getattr(manager, "_on_quick_filter_changed", None)
            if callable(handler):
                try:
                    gui.batch_panel.quickFilterChanged.connect(handler)
                    logger.info("快速筛选信号连接成功")
                except Exception as e:
                    logger.error(f"连接快速筛选信号失败: {e}", exc_info=True)
            else:
                logger.warning(
                    "快速筛选信号连接失败：manager 未提供 _on_quick_filter_changed 回调"
                )
        else:
            logger.warning(
                "快速筛选信号连接失败：batch_panel 或 quickFilterChanged 不存在"
            )
    except Exception:
        logger.debug("connect_quick_filter 失败", exc_info=True)


def safe_refresh_file_statuses(manager: Any, *args, **kwargs) -> None:
    """容错包装：安全调用 manager.refresh_file_statuses。"""
    try:
        manager.refresh_file_statuses()
    except Exception:
        logger.debug("调用 refresh_file_statuses 失败", exc_info=True)
