"""
日志管理模块 - 处理 GUI 日志输出和配置
"""

# 某些 Qt 相关导入在运行时或测试下可能需要延迟执行，允许 import-outside-toplevel
# pylint: disable=import-outside-toplevel

import logging

from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import QObject, QMetaObject, Qt, Slot
from pathlib import Path
import os
import threading
import weakref


class GUILogHandler(logging.Handler):
    """自定义日志处理器 - 将日志输出到 GUI 的 QTextEdit"""

    def __init__(self, text_widget: QTextEdit):
        super().__init__()
        self.text_widget = text_widget
        self.setLevel(logging.DEBUG)
        # 缓冲高频日志，避免大量单独调度 QTimer.singleShot
        self._lock = threading.Lock()
        self._pending = []  # type: list[str]
        self._scheduled = False
        # invoker 用于保证在主线程调用 _flush_pending
        try:
            self._invoker = _Invoker(self)
        except Exception:
            self._invoker = None

    def emit(self, record):
        try:
            msg = self.format(record)
            # 缓存多条日志并仅安排一次 GUI 刷新，减少事件队列压力
            with self._lock:
                self._pending.append(msg)
                if not self._scheduled:
                    self._scheduled = True
                    # 使用 QMetaObject.invokeMethod 调度到主线程（QueuedConnection），比 QTimer 更稳健
                    if self._invoker is not None:
                        try:
                            QMetaObject.invokeMethod(self._invoker, "do_flush", Qt.QueuedConnection)
                        except Exception:
                            # 回退到 QTimer 单次调度（兼容性）
                            from PySide6.QtCore import QTimer

                            QTimer.singleShot(0, self._flush_pending)
                    else:
                        from PySide6.QtCore import QTimer

                        QTimer.singleShot(0, self._flush_pending)
        except Exception:
            self.handleError(record)

    def _append_text(self, msg):
        try:
            if self.text_widget:
                # 只显示消息，不需要前缀
                self.text_widget.append(msg)
                # 更稳健地移动光标到末尾并确保可见，比直接操作 scrollbar 更可靠
                try:
                    from PySide6.QtGui import QTextCursor

                    cursor = self.text_widget.textCursor()
                    cursor.movePosition(QTextCursor.End)
                    self.text_widget.setTextCursor(cursor)
                    try:
                        self.text_widget.ensureCursorVisible()
                    except Exception:
                        # 部分 Qt 版本可能没有该方法，回退到滚动条
                        sb = self.text_widget.verticalScrollBar()
                        sb.setValue(sb.maximum())
                except Exception:
                    # 如果 QTextCursor 操作失败，使用滚动条作为回退
                    try:
                        sb = self.text_widget.verticalScrollBar()
                        sb.setValue(sb.maximum())
                    except Exception:
                        logging.getLogger(__name__).debug(
                            "无法将日志视图滚动到末尾（非致命）", exc_info=True
                        )
        except Exception:
            logging.getLogger(__name__).debug("追加 GUI 日志失败（非致命）", exc_info=True)

    def _flush_pending(self):
        """将缓冲的日志一次性刷新到 GUI（在主线程执行）。"""
        try:
            with self._lock:
                msgs = self._pending[:]
                self._pending.clear()
                self._scheduled = False

            if not msgs:
                return

            # 合并为单条文本以减少对 QTextEdit 的多次操作
            combined = "\n".join(msgs)
            self._append_text(combined)
        except Exception:
            logging.getLogger(__name__).debug("刷新 GUI 日志缓冲失败（非致命）", exc_info=True)
        return


class LoggingManager:
    """日志管理器 - 配置日志系统连接到 GUI"""

    def __init__(self, gui):
        self.gui = gui
        # 使用 WeakKeyDictionary 优先将 text_widget 弱引用到对应的 GUILogHandler，
        # 当控件被销毁时条目会自动清理，避免内存泄漏。
        # 注意：某些 PySide/PyQt 的 QObject 不能被弱引用，因此我们保留一个回退字典。
        try:
            self._widget_handlers = weakref.WeakKeyDictionary()
            self._use_weak = True
        except Exception:
            self._widget_handlers = {}
            self._use_weak = False
        # 回退结构：id(text_widget) -> (weakref.ref(text_widget) | None, GUILogHandler)
        self._widget_handlers_fallback = {}

    def _get_handler_for_widget(self, widget):
        """返回与 widget 关联的 GUILogHandler，或 None。"""
        # 先尝试 WeakKeyDictionary（若可用）
        try:
            if self._use_weak:
                return self._widget_handlers.get(widget)
        except Exception:
            # 若 WeakKeyDictionary 出错，回退到 fallback
            self._use_weak = False

        # 回退查找：清理已失效的 weakref 条目
        dead = []
        for wid_key, (wref, handler) in list(self._widget_handlers_fallback.items()):
            if wref is None:
                # 无法弱引用，保留基于 id 的映射
                if wid_key == id(widget):
                    return handler
            else:
                obj = wref()
                if obj is None:
                    dead.append(wid_key)
                elif obj is widget:
                    return handler
        for k in dead:
            self._widget_handlers_fallback.pop(k, None)
        return None

    def _register_handler_for_widget(self, widget, handler):
        """将 handler 与 widget 关联，尽量使用 weakref 存储；若失败则使用回退映射。"""
        try:
            if self._use_weak:
                try:
                    self._widget_handlers[widget] = handler
                    return
                except TypeError:
                    # widget 不可被弱引用，切换到回退模式
                    self._use_weak = False
        except Exception:
            self._use_weak = False

        # 回退：尝试使用 weakref.ref，如果失败则保存 None
        try:
            wref = weakref.ref(widget)
        except Exception:
            wref = None
        self._widget_handlers_fallback[id(widget)] = (wref, handler)

    def setup_gui_logging(self):
        """设置日志系统，将所有日志输出到 GUI 的处理日志面板"""
        try:
            text_widget = getattr(self.gui, "txt_batch_log", None)
            if text_widget is None:
                # 如果 GUI 日志控件不存在，仍确保有文件与控制台回退日志
                self._ensure_fallback_handlers()
                return
            # 校验控件类型，确保是 QTextEdit，否则可能行为异常
            if not isinstance(text_widget, QTextEdit):
                logging.getLogger(__name__).debug(
                    "txt_batch_log 不是 QTextEdit（类型=%s），跳过 GUI 绑定", type(text_widget)
                )
                self._ensure_fallback_handlers()
                return

            # 获取或创建对应该 text_widget 的 GUILogHandler（幂等且可复用）
            gui_handler = self._get_handler_for_widget(text_widget)
            if gui_handler is None:
                gui_handler = GUILogHandler(text_widget)
                self._register_handler_for_widget(text_widget, gui_handler)
            formatter = logging.Formatter("%(levelname)s: %(message)s")
            gui_handler.setFormatter(formatter)

            # 为相关的 logger 添加处理器
            loggers_to_configure = [
                logging.getLogger("src.special_format_parser"),
                logging.getLogger("src.data_loader"),
                logging.getLogger("src.physics"),
                logging.getLogger("src.batch_process"),
                logging.getLogger("gui_main"),
            ]

            for log in loggers_to_configure:
                # 清除之前的 StreamHandler（控制台处理器）
                for handler in log.handlers[:]:
                    if isinstance(handler, logging.StreamHandler) and not isinstance(
                            handler, logging.FileHandler
                    ):
                        log.removeHandler(handler)
                # 如果已经存在相同的 GUI 处理器则跳过，保证幂等性
                if gui_handler not in log.handlers:
                    log.addHandler(gui_handler)
                # 禁止向上级传播，避免被 root handler 重复输出
                try:
                    log.propagate = False
                except Exception:
                    pass
                log.setLevel(logging.DEBUG)

            # 确保 root logger 有文件和控制台回退，以便在 GUI 崩溃或不可用时仍能记录日志
            self._ensure_fallback_handlers()

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.debug("GUI logging setup failed (non-fatal): %s", e, exc_info=True)

    def _ensure_fallback_handlers(self):
        """确保存在文件与控制台处理器，作为 GUI 输出的回退。

        日志文件位置：`~/.momenttransfer/momenttransfer.log`。
        该函数对已有处理器保持幂等性。
        """
        try:
            root = logging.getLogger()
            root.setLevel(logging.DEBUG)

            # 准备日志目录
            log_dir = Path.home() / ".momenttransfer"
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                # 若创建目录失败，则继续但不写文件
                log_dir = None

            # 添加文件处理器（如果尚未存在特定文件的 FileHandler）
            if log_dir is not None:
                log_file = str(log_dir / "momenttransfer.log")
                has_file = False
                for h in root.handlers:
                    if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == log_file:
                        has_file = True
                        break
                if not has_file:
                    try:
                        fh = logging.FileHandler(log_file, encoding="utf-8")
                        fh.setLevel(logging.DEBUG)
                        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
                        root.addHandler(fh)
                    except Exception:
                        # 无法创建文件处理器时，记录到控制台即可
                        logging.getLogger(__name__).debug("无法创建文件日志处理器（非致命）", exc_info=True)

            # 添加控制台处理器（stderr）如果不存在
            has_stream = any(isinstance(h, logging.StreamHandler) for h in root.handlers)
            if not has_stream:
                sh = logging.StreamHandler()
                sh.setLevel(logging.INFO)
                sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
                root.addHandler(sh)

        except Exception:
            # 最后保底：不要抛出异常
            logging.getLogger(__name__).debug("设置回退日志处理器失败（非致命）", exc_info=True)


class _Invoker(QObject):
    """Helper QObject 用于把 handler 的刷新请求以 queued connection 调度到主线程。"""

    def __init__(self, handler):
        super().__init__()
        try:
            self._handler_ref = weakref.ref(handler)
        except Exception:
            # 如果 handler 不可被弱引用（极少），保留直接引用
            self._handler_ref = lambda: handler

    @Slot()
    def do_flush(self):
        handler = self._handler_ref()
        if handler is None:
            return
        try:
            handler._flush_pending()
        except Exception:
            logging.getLogger(__name__).debug("通过 invoker 调度刷新失败（非致命）", exc_info=True)

