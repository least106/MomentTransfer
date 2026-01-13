"""
事件管理器 - 处理主窗口的所有事件（showEvent, resizeEvent, closeEvent 等）
"""

import logging
from PySide6.QtCore import QTimer

logger = logging.getLogger(__name__)


class EventManager:
    """管理主窗口事件处理"""

    def __init__(self, main_window):
        self.main_window = main_window
        self._show_event_fired = False

    def on_show_event(self, event):
        """处理窗口显示事件"""
        if not self._show_event_fired:
            self._show_event_fired = True
            try:
                # 触发初始布局更新
                init_mgr = getattr(
                    self.main_window, "initialization_manager", None
                )
                if init_mgr:
                    init_mgr.trigger_initial_layout_update()
                    init_mgr.finalize_initialization()
                else:
                    # 回退到旧方式
                    QTimer.singleShot(
                        50, self.main_window.update_button_layout
                    )
                    QTimer.singleShot(
                        120, self.main_window._force_layout_refresh
                    )
                    QTimer.singleShot(
                        150,
                        lambda: setattr(
                            self.main_window, "_is_initializing", False
                        ),
                    )
            except Exception:
                logger.debug("showEvent scheduling failed", exc_info=True)
                self.main_window._is_initializing = False

    def on_resize_event(self, event):
        """处理窗口大小调整事件"""
        try:
            if (
                hasattr(self.main_window, "layout_manager")
                and self.main_window.layout_manager
            ):
                self.main_window.layout_manager.on_resize_event(event)
        except AttributeError:
            logger.debug("LayoutManager 未初始化")
        except Exception:
            logger.debug("resizeEvent 处理失败", exc_info=True)

    def on_close_event(self, event):
        """处理窗口关闭事件"""
        try:
            # 如果批处理正在进行中，先停止它
            batch_thread = getattr(self.main_window, "batch_thread", None)
            if batch_thread is not None and batch_thread.isRunning():
                try:
                    batch_thread.request_stop()
                    batch_thread.wait(1000)
                except Exception:
                    logger.debug("批处理线程停止失败", exc_info=True)

            # 关闭可视化窗口
            if (
                hasattr(self.main_window, "visualization_window")
                and self.main_window.visualization_window
            ):
                try:
                    self.main_window.visualization_window.close()
                except Exception:
                    logger.debug("可视化窗口关闭失败", exc_info=True)

            logger.info("主窗口已关闭")
        except Exception as e:
            logger.error(f"closeEvent 处理失败: {e}", exc_info=True)
