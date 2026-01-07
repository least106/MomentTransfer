"""
日志管理模块 - 处理 GUI 日志输出和配置
"""

import logging
from PySide6.QtWidgets import QTextEdit


class GUILogHandler(logging.Handler):
    """自定义日志处理器 - 将日志输出到 GUI 的 QTextEdit"""
    def __init__(self, text_widget: QTextEdit):
        super().__init__()
        self.text_widget = text_widget
        self.setLevel(logging.DEBUG)
    
    def emit(self, record):
        try:
            msg = self.format(record)
            # 在主线程中更新 GUI（使用 Qt 的信号机制）
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._append_text(msg))
        except Exception:
            self.handleError(record)
    
    def _append_text(self, msg):
        try:
            if self.text_widget:
                # 只显示消息，不需要前缀
                self.text_widget.append(msg)
                # 自动滚动到最后
                self.text_widget.verticalScrollBar().setValue(
                    self.text_widget.verticalScrollBar().maximum()
                )
        except Exception:
            pass


class LoggingManager:
    """日志管理器 - 配置日志系统连接到 GUI"""
    
    def __init__(self, gui):
        self.gui = gui
    
    def setup_gui_logging(self):
        """设置日志系统，将所有日志输出到 GUI 的处理日志面板"""
        try:
            text_widget = getattr(self.gui, 'txt_batch_log', None)
            if text_widget is None:
                return
            
            # 添加自定义 GUI 日志处理器
            gui_handler = GUILogHandler(text_widget)
            formatter = logging.Formatter('%(levelname)s: %(message)s')
            gui_handler.setFormatter(formatter)
            
            # 为相关的 logger 添加处理器
            loggers_to_configure = [
                logging.getLogger('src.special_format_parser'),
                logging.getLogger('src.data_loader'),
                logging.getLogger('src.physics'),
                logging.getLogger('src.batch_process'),
                logging.getLogger('gui_main'),
            ]
            
            for log in loggers_to_configure:
                # 清除之前的 StreamHandler（控制台处理器）
                for handler in log.handlers[:]:
                    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                        log.removeHandler(handler)
                log.addHandler(gui_handler)
                log.setLevel(logging.DEBUG)
                
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.debug(f"GUI logging setup failed (non-fatal): {e}", exc_info=True)
