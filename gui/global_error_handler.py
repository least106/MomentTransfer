"""全局错误处理器模块

统一管理和展示应用程序中的所有错误，提供：
- 中心化的错误接收和处理
- 统一的用户错误展示
- 错误追踪和日志记录
- 错误信号的监听和路由
"""

import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QMessageBox, QWidget

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """错误严重程度"""

    DEBUG = "debug"  # 调试信息
    INFO = "info"  # 一般信息
    WARNING = "warning"  # 警告
    ERROR = "error"  # 错误
    CRITICAL = "critical"  # 严重错误


@dataclass
class ErrorRecord:
    """错误记录"""

    timestamp: datetime
    severity: ErrorSeverity
    title: str
    message: str
    details: Optional[str] = None
    source: Optional[str] = None  # 错误来源（模块/函数名）
    traceback: Optional[str] = None
    user_notified: bool = False  # 是否已通知用户
    context: dict = field(default_factory=dict)  # 额外的上下文信息


class GlobalErrorHandler(QObject):
    """全局错误处理器（单例）

    职责：
    1. 接收来自各模块的错误信号
    2. 统一记录错误日志
    3. 根据严重程度决定是否展示给用户
    4. 提供错误历史查询
    """

    # 信号：新错误发生 (ErrorRecord)
    errorOccurred = Signal(object)

    # 信号：需要通知用户 (title, message, severity)
    userNotificationRequired = Signal(str, str, object)

    _instance: Optional["GlobalErrorHandler"] = None

    @classmethod
    def instance(cls) -> "GlobalErrorHandler":
        """获取单例"""
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            QObject.__init__(cls._instance)
            cls._instance._initialize()
        return cls._instance

    def __init__(self):
        # 禁止直接实例化，必须使用 instance()
        if GlobalErrorHandler._instance is not None:
            raise RuntimeError("GlobalErrorHandler 是单例，请使用 instance() 方法")

    def _initialize(self):
        """初始化实例（内部方法）"""
        # 错误历史（最多保留 1000 条）
        self._error_history: List[ErrorRecord] = []
        self._max_history = 1000

        # 默认的父窗口（用于显示对话框）
        self._default_parent: Optional[QWidget] = None

        # 错误通知策略（可自定义）
        self._notification_strategy: Callable[
            [ErrorRecord], bool
        ] = self._default_notification_strategy

        # 连接用户通知信号到默认处理函数
        self.userNotificationRequired.connect(self._show_error_dialog)

    def set_default_parent(self, parent: QWidget):
        """设置默认的父窗口"""
        self._default_parent = parent

    def set_notification_strategy(
        self, strategy: Callable[[ErrorRecord], bool]
    ):
        """设置自定义的错误通知策略

        Args:
            strategy: 函数，接收 ErrorRecord，返回是否需要通知用户
        """
        self._notification_strategy = strategy

    @Slot(str, str, str, str, str)
    def handle_error(
        self,
        title: str,
        message: str,
        severity: str = "error",
        details: Optional[str] = None,
        source: Optional[str] = None,
    ):
        """处理错误（槽函数）

        Args:
            title: 错误标题
            message: 错误消息
            severity: 严重程度字符串
            details: 详细信息
            source: 错误来源
        """
        try:
            severity_enum = ErrorSeverity(severity.lower())
        except ValueError:
            severity_enum = ErrorSeverity.ERROR

        self.report_error(
            title=title,
            message=message,
            severity=severity_enum,
            details=details,
            source=source,
        )

    def report_error(
        self,
        title: str,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        details: Optional[str] = None,
        source: Optional[str] = None,
        exc_info: bool = False,
        context: Optional[dict] = None,
    ) -> ErrorRecord:
        """报告错误

        Args:
            title: 错误标题
            message: 错误消息
            severity: 严重程度
            details: 详细信息
            source: 错误来源
            exc_info: 是否包含异常信息
            context: 额外的上下文信息

        Returns:
            ErrorRecord 实例
        """
        # 捕获追踪栈（如果有异常）
        tb_str = None
        if exc_info:
            try:
                tb_str = traceback.format_exc()
            except Exception:
                pass

        # 创建错误记录
        record = ErrorRecord(
            timestamp=datetime.now(),
            severity=severity,
            title=title,
            message=message,
            details=details,
            source=source,
            traceback=tb_str,
            context=context or {},
        )

        # 记录日志
        self._log_error(record)

        # 添加到历史
        self._add_to_history(record)

        # 发送错误发生信号
        self.errorOccurred.emit(record)

        # 判断是否需要通知用户
        if self._notification_strategy(record):
            record.user_notified = True
            self.userNotificationRequired.emit(title, message, severity)

        return record

    def report_exception(
        self,
        title: str,
        exception: Exception,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        source: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> ErrorRecord:
        """报告异常

        Args:
            title: 错误标题
            exception: 异常对象
            severity: 严重程度
            source: 错误来源
            context: 额外的上下文信息

        Returns:
            ErrorRecord 实例
        """
        message = str(exception)
        details = f"{type(exception).__name__}: {message}"

        return self.report_error(
            title=title,
            message=message,
            severity=severity,
            details=details,
            source=source,
            exc_info=True,
            context=context,
        )

    def report_user_error(
        self,
        parent: Optional[QWidget],
        title: str,
        message: str,
        details: Optional[str] = None,
        is_warning: bool = False,
        source: Optional[str] = None,
    ):
        """报告用户操作错误（兼容旧的 report_user_error 接口）

        Args:
            parent: 父窗口
            title: 错误标题
            message: 错误消息
            details: 详细信息
            is_warning: 是否为警告
            source: 错误来源
        """
        severity = ErrorSeverity.WARNING if is_warning else ErrorSeverity.ERROR

        # 临时设置父窗口
        original_parent = self._default_parent
        if parent is not None:
            self._default_parent = parent

        try:
            self.report_error(
                title=title,
                message=message,
                severity=severity,
                details=details,
                source=source,
            )
        finally:
            # 恢复原父窗口
            self._default_parent = original_parent

    def get_error_history(
        self, severity: Optional[ErrorSeverity] = None, limit: int = 100
    ) -> List[ErrorRecord]:
        """获取错误历史

        Args:
            severity: 过滤严重程度（None 表示所有）
            limit: 最多返回的记录数

        Returns:
            错误记录列表（按时间倒序）
        """
        history = self._error_history[::-1]  # 倒序

        if severity is not None:
            history = [r for r in history if r.severity == severity]

        return history[:limit]

    def clear_history(self):
        """清空错误历史"""
        self._error_history.clear()

    def _log_error(self, record: ErrorRecord):
        """记录错误日志"""
        log_message = f"{record.title}: {record.message}"
        if record.source:
            log_message = f"[{record.source}] {log_message}"

        # 根据严重程度选择日志级别
        if record.severity == ErrorSeverity.DEBUG:
            logger.debug(log_message)
            if record.details:
                logger.debug("详细信息: %s", record.details)
        elif record.severity == ErrorSeverity.INFO:
            logger.info(log_message)
            if record.details:
                logger.info("详细信息: %s", record.details)
        elif record.severity == ErrorSeverity.WARNING:
            logger.warning(log_message)
            if record.details:
                logger.warning("详细信息: %s", record.details)
        elif record.severity == ErrorSeverity.ERROR:
            logger.error(log_message, exc_info=record.traceback is not None)
            if record.details:
                logger.error("详细信息: %s", record.details)
        elif record.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message, exc_info=record.traceback is not None)
            if record.details:
                logger.critical("详细信息: %s", record.details)

    def _add_to_history(self, record: ErrorRecord):
        """添加到历史记录"""
        self._error_history.append(record)

        # 限制历史大小
        if len(self._error_history) > self._max_history:
            self._error_history = self._error_history[-self._max_history :]

    def _default_notification_strategy(self, record: ErrorRecord) -> bool:
        """默认的通知策略

        规则：
        - ERROR 和 CRITICAL 始终通知用户
        - WARNING 通知用户
        - INFO 和 DEBUG 不通知用户
        """
        return record.severity in (
            ErrorSeverity.ERROR,
            ErrorSeverity.CRITICAL,
            ErrorSeverity.WARNING,
        )

    @Slot(str, str, object)
    def _show_error_dialog(self, title: str, message: str, severity: ErrorSeverity):
        """显示错误对话框"""
        try:
            parent = self._default_parent

            # 根据严重程度选择图标
            if severity == ErrorSeverity.CRITICAL:
                icon = QMessageBox.Critical
            elif severity == ErrorSeverity.ERROR:
                icon = QMessageBox.Critical
            elif severity == ErrorSeverity.WARNING:
                icon = QMessageBox.Warning
            else:
                icon = QMessageBox.Information

            # 创建消息框
            msg_box = QMessageBox(parent)
            msg_box.setIcon(icon)
            msg_box.setWindowTitle(title)
            msg_box.setText(message)
            msg_box.setStandardButtons(QMessageBox.Ok)

            # 非模态显示（不阻塞主线程）
            msg_box.setModal(False)
            msg_box.show()

        except Exception as e:
            logger.error(f"显示错误对话框失败: {e}", exc_info=True)


def connect_to_signal_bus():
    """连接 SignalBus 的错误相关信号到全局错误处理器

    应在应用启动时调用一次。
    """
    try:
        from gui.signal_bus import SignalBus

        signal_bus = SignalBus.instance()
        error_handler = GlobalErrorHandler.instance()

        # 连接批处理错误信号
        signal_bus.batchError.connect(
            lambda msg: error_handler.report_error(
                title="批处理错误",
                message=msg,
                severity=ErrorSeverity.ERROR,
                source="batch",
            )
        )

        logger.info("全局错误处理器已连接到 SignalBus")

    except Exception as e:
        logger.warning(f"连接 SignalBus 失败: {e}", exc_info=True)


# 便捷函数：全局错误报告
def report_error(
    title: str,
    message: str,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    details: Optional[str] = None,
    source: Optional[str] = None,
) -> ErrorRecord:
    """便捷函数：报告错误到全局错误处理器"""
    return GlobalErrorHandler.instance().report_error(
        title=title,
        message=message,
        severity=severity,
        details=details,
        source=source,
    )


def report_exception(
    title: str,
    exception: Exception,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    source: Optional[str] = None,
) -> ErrorRecord:
    """便捷函数：报告异常到全局错误处理器"""
    return GlobalErrorHandler.instance().report_exception(
        title=title, exception=exception, severity=severity, source=source
    )
