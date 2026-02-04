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
                init_mgr = getattr(self.main_window, "initialization_manager", None)
                if init_mgr:
                    init_mgr.trigger_initial_layout_update()
                    init_mgr.finalize_initialization()
                else:
                    # 回退到旧方式
                    QTimer.singleShot(50, self.main_window.update_button_layout)
                    QTimer.singleShot(120, self.main_window._force_layout_refresh)
                    QTimer.singleShot(
                        150,
                        lambda: setattr(self.main_window, "_is_initializing", False),
                    )
            except Exception:
                logger.debug("showEvent scheduling failed", exc_info=True)
                self.main_window._is_initializing = False

    def on_resize_event(self, event):
        """处理窗口大小调整事件"""
        try:
            if hasattr(self.main_window, "layout_manager") and self.main_window.layout_manager:
                self.main_window.layout_manager.on_resize_event(event)
        except AttributeError:
            logger.debug("LayoutManager 未初始化")
        except Exception:
            logger.debug("resizeEvent 处理失败", exc_info=True)

    def on_close_event(self, event):
        """处理窗口关闭事件"""
        try:
            # UX: 在关闭前确认是否有未保存的改动，优雅询问用户
            try:
                mw = self.main_window
                has_unsaved = False
                try:
                    func_has = getattr(mw, "_has_unsaved_changes", None)
                    if callable(func_has):
                        has_unsaved = bool(func_has())
                except Exception:
                    has_unsaved = False

                if has_unsaved:
                    func_confirm = getattr(mw, "_confirm_save_discard_cancel", None)
                    if callable(func_confirm):
                        proceed = False
                        try:
                            proceed = bool(func_confirm("关闭窗口"))
                        except Exception:
                            proceed = False
                        if not proceed:
                            try:
                                if event is not None and hasattr(event, "ignore"):
                                    event.ignore()
                            except Exception:
                                pass
                            return
            except Exception:
                # 忽略此处错误，继续后续关闭流程
                logger.debug("关闭前未保存检查失败（非致命）", exc_info=True)

            # 优先从 main_window.batch_manager 找到 batch_thread，然后回退到 main_window.batch_thread
            batch_thread = None
            try:
                bm = getattr(self.main_window, "batch_manager", None)
                if bm is not None:
                    batch_thread = getattr(bm, "batch_thread", None)
            except Exception:
                batch_thread = None
            if batch_thread is None:
                batch_thread = getattr(self.main_window, "batch_thread", None)

            if batch_thread is not None and batch_thread.isRunning():
                try:
                    batch_thread.request_stop()
                    # wait 1s 最多等待；若用户在此期间按下 Ctrl+C，会触发 KeyboardInterrupt
                    try:
                        batch_thread.wait(1000)
                    except KeyboardInterrupt:
                        # 在控制台中按 Ctrl+C 时优雅中断等待，继续清理并关闭
                        logger.info("收到中断信号(Ctrl+C)，正在强制停止批处理线程")
                except Exception:
                    logger.debug("批处理线程停止失败", exc_info=True)

            # 关闭可视化窗口
            if hasattr(self.main_window, "visualization_window") and self.main_window.visualization_window:
                try:
                    self.main_window.visualization_window.close()
                except Exception:
                    logger.debug("可视化窗口关闭失败", exc_info=True)

            logger.info("主窗口已关闭")
        except Exception as e:
            logger.error("closeEvent 处理失败: %s", e, exc_info=True)
