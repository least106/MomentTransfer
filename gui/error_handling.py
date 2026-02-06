"""错误处理辅助模块 - 提供统一的错误处理和报告功能"""

import logging
import traceback
from typing import Callable, Optional

from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


def report_nonfatal_error(message: str, exception: Optional[Exception] = None):
    """
    报告非致命错误，让用户可见（通过状态栏提示）
    
    替代原先的 logger.debug("XX失败（非致命）")
    
    参数：
        message: 错误消息
        exception: 异常对象（可选）
    """
    details = str(exception) if exception else None
    logger.debug(f"{message}: {details}", exc_info=exception is not None)
    
    try:
        from gui.global_error_handler import GlobalErrorHandler, ErrorSeverity
        GlobalErrorHandler.instance().report_error(
            title="操作警告",
            message=message,
            severity=ErrorSeverity.WARNING,
            details=details,
            exc_info=exception is not None
        )
    except Exception as e:
        logger.debug(f"报告非致命错误失败: {e}")


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

        # 统一通过 GlobalErrorHandler 报告
        try:
            from gui.global_error_handler import GlobalErrorHandler, ErrorSeverity
            
            severity = ErrorSeverity.ERROR if show_dialog else ErrorSeverity.WARNING
            GlobalErrorHandler.instance().report_error(
                title=error_title,
                message=error_message,
                severity=severity,
                details=str(e),
                exc_info=True
            )
        except Exception:
            # 降级处理：使用传统方式
            if show_dialog and parent:
                try:
                    from gui.managers import report_user_error
                    report_user_error(parent, error_title, error_message, details=str(e))
                except Exception:
                    pass

        return default_return


def try_or_log(
    func: Callable,
    error_message: str = "操作失败",
    log_level: int = logging.DEBUG,
    default_return=None,
    notify_user: bool = True,
):
    """
    尝试执行函数，失败时记录日志

    参数：
        func: 要执行的函数
        error_message: 错误消息
        log_level: 日志级别
        default_return: 发生异常时的默认返回值
        notify_user: 是否通过 GlobalErrorHandler 通知用户（默认 True）

    返回：
        函数执行结果或默认返回值
    """
    try:
        return func()
    except Exception as e:
        logger.log(log_level, f"{error_message}: {e}", exc_info=True)
        
        # 通过 GlobalErrorHandler 让错误对用户可见
        if notify_user:
            try:
                from gui.global_error_handler import GlobalErrorHandler, ErrorSeverity
                GlobalErrorHandler.instance().report_error(
                    title="操作异常",
                    message=error_message,
                    severity=ErrorSeverity.WARNING,
                    details=str(e),
                    exc_info=True
                )
            except Exception:
                pass
        
        return default_return


def try_call_method(obj, method_name: str, *args, default_return=None, notify_user: bool = True, **kwargs):
    """
    安全调用对象的方法

    参数：
        obj: 对象
        method_name: 方法名
        *args: 位置参数
        default_return: 默认返回值
        notify_user: 是否通过 GlobalErrorHandler 通知用户（默认 True）
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
        
        # 通过 GlobalErrorHandler 让错误对用户可见
        if notify_user:
            try:
                from gui.global_error_handler import GlobalErrorHandler, ErrorSeverity
                GlobalErrorHandler.instance().report_error(
                    title="方法调用失败",
                    message=f"调用 {method_name} 时出错",
                    severity=ErrorSeverity.WARNING,
                    details=str(e),
                    exc_info=True
                )
            except Exception:
                pass

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
    报告严重错误（统一路由到 GlobalErrorHandler）

    参数：
        parent: 父窗口
        title: 错误标题
        message: 错误消息
        details: 详细信息
    """
    try:
        from gui.global_error_handler import GlobalErrorHandler, ErrorSeverity
        
        GlobalErrorHandler.instance().report_error(
            title=title,
            message=message,
            severity=ErrorSeverity.CRITICAL,
            details=details,
            exc_info=False
        )
    except Exception as e:
        logger.debug(f"通过 GlobalErrorHandler 报告错误失败: {e}", exc_info=True)
        # 降级到传统 QMessageBox
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
