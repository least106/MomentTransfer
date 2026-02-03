"""错误处理辅助模块 - 提供统一的错误处理和报告功能"""

import logging
import traceback
from typing import Callable, Optional

from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


def safe_execute(
    func: Callable,
    error_title: str = "操作失败",
    error_message: str = "执行操作时出错",
    show_dialog: bool = False,
    parent=None,
    default_return=None,
):
    """
    安全执行函数，捕获异常并记录日志

    参数：
        func: 要执行的函数
        error_title: 错误对话框标题
        error_message: 错误消息
        show_dialog: 是否显示错误对话框
        parent: 父窗口（用于错误对话框）
        default_return: 发生异常时的默认返回值

    返回：
        函数执行结果或默认返回值
    """
    try:
        return func()
    except Exception as e:
        logger.debug(f"{error_message}: {e}", exc_info=True)

        if show_dialog and parent:
            try:
                from gui.managers import report_user_error

                report_user_error(parent, error_title, error_message, details=str(e))
            except Exception:
                # 如果报告失败，使用简单的消息框
                try:
                    msg_text = f"{error_message}\n\n{str(e)}"
                    QMessageBox.critical(parent, error_title, msg_text)
                except Exception:
                    pass

        return default_return


def try_or_log(
    func: Callable,
    error_message: str = "操作失败",
    log_level: int = logging.DEBUG,
    default_return=None,
):
    """
    尝试执行函数，失败时记录日志

    参数：
        func: 要执行的函数
        error_message: 错误消息
        log_level: 日志级别
        default_return: 发生异常时的默认返回值

    返回：
        函数执行结果或默认返回值
    """
    try:
        return func()
    except Exception as e:
        logger.log(log_level, f"{error_message}: {e}", exc_info=True)
        return default_return


def try_call_method(obj, method_name: str, *args, default_return=None, **kwargs):
    """
    安全调用对象的方法

    参数：
        obj: 对象
        method_name: 方法名
        *args: 位置参数
        default_return: 默认返回值
        **kwargs: 关键字参数

    返回：
        方法执行结果或默认返回值
    """
    try:
        if hasattr(obj, method_name):
            method = getattr(obj, method_name)
            if callable(method):
                return method(*args, **kwargs)
    except Exception as e:
        logger.debug(f"调用 {method_name} 失败: {e}", exc_info=True)

    return default_return


def safe_disconnect(signal):
    """
    安全断开信号连接

    参数：
        signal: 要断开的信号
    """
    try:
        signal.disconnect()
    except Exception:
        pass


def safe_block_signals(widget, blocked: bool):
    """
    安全设置组件信号阻塞状态

    参数：
        widget: 组件
        blocked: 是否阻塞
    """
    try:
        widget.blockSignals(blocked)
    except Exception:
        pass


class ErrorContext:
    """错误上下文管理器 - 用于 with 语句"""

    def __init__(
        self,
        error_message: str = "操作失败",
        log_level: int = logging.DEBUG,
        suppress: bool = True,
    ):
        """
        初始化错误上下文

        参数：
            error_message: 错误消息
            log_level: 日志级别
            suppress: 是否抑制异常
        """
        self.error_message = error_message
        self.log_level = log_level
        self.suppress = suppress

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.log(
                self.log_level,
                f"{self.error_message}: {exc_val}",
                exc_info=(exc_type, exc_val, exc_tb),
            )
            return self.suppress
        return False


def report_critical_error(
    parent, title: str, message: str, details: Optional[str] = None
):
    """
    报告严重错误

    参数：
        parent: 父窗口
        title: 错误标题
        message: 错误消息
        details: 详细信息
    """
    try:
        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle(title)
        msg.setText(message)

        if details:
            msg.setDetailedText(details)

        msg.exec()
    except Exception:
        logger.error(f"{title}: {message}", exc_info=True)


def get_error_details() -> str:
    """
    获取当前异常的详细信息

    返回：
        异常详细信息字符串
    """
    return traceback.format_exc()
