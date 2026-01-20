"""
结构化日志系统 - 提供 JSON 格式的结构化日志输出

支持：
1. 标准日志处理器
2. 结构化 JSON 日志格式
3. 性能指标集成
4. 上下文信息追踪
"""

import contextvars
import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredLogFormatter(logging.Formatter):
    """结构化日志格式化器 - 输出 JSON 格式的日志"""

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为 JSON"""
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # 添加异常信息
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # 添加额外字段
        if hasattr(record, "context"):
            log_record["context"] = record.context

        return json.dumps(log_record, ensure_ascii=False, default=str)


class LogContext:
    """日志上下文 - 追踪相关请求/操作（线程/协程安全）。

    使用 `contextvars.ContextVar` 存储当前上下文，避免在多线程或异步环境中混淆全局状态。
    """

    # 使用 ContextVar 保持线程/协程局部的上下文状态
    _ctx_var: contextvars.ContextVar = contextvars.ContextVar(
        "log_context", default=None
    )

    def __init__(self, context_id: str, operation: str = "", **metadata):
        """初始化上下文"""
        self.context_id = context_id
        self.operation = operation
        self.metadata = metadata
        self._token = None

    def __enter__(self):
        """进入上下文，保存 token 以便退出时恢复上级上下文。"""
        self._token = LogContext._ctx_var.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，使用 token 恢复先前的上下文。"""
        if self._token is not None:
            try:
                LogContext._ctx_var.reset(self._token)
            except Exception:
                # 保持兼容性：若 reset 失败，确保不抛出异常
                LogContext._ctx_var.set(None)

    @classmethod
    def get_current(cls) -> Optional["LogContext"]:
        """获取当前上下文（若无则返回 None）。"""
        return cls._ctx_var.get(None)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "context_id": self.context_id,
            "operation": self.operation,
            **self.metadata,
        }


class StructuredLogger:
    """结构化日志记录器 - 简化 JSON 日志的使用"""

    def __init__(self, name: str):
        """初始化记录器"""
        self.logger = logging.getLogger(name)

    def _add_context(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """添加上下文信息"""
        context_data = {}
        current_context = LogContext.get_current()

        if current_context:
            context_data["context"] = current_context.to_dict()

        if extra:
            context_data.update(extra)

        return context_data

    def info(self, message: str, **kwargs):
        """记录信息级别日志"""
        extra = self._add_context(kwargs)
        self.logger.info(message, extra=extra)

    def warning(self, message: str, **kwargs):
        """记录警告级别日志"""
        extra = self._add_context(kwargs)
        self.logger.warning(message, extra=extra)

    def error(self, message: str, **kwargs):
        """记录错误级别日志"""
        extra = self._add_context(kwargs)
        self.logger.error(message, extra=extra)

    def debug(self, message: str, **kwargs):
        """记录调试级别日志"""
        extra = self._add_context(kwargs)
        self.logger.debug(message, extra=extra)

    def log_operation(self, operation: str, success: bool, **details):
        """记录操作结果"""
        message = f"操作 {operation}: {'成功' if success else '失败'}"
        level = "info" if success else "error"
        getattr(self, level)(message, operation=operation, success=success, **details)

    def log_performance(self, operation: str, duration_ms: float, **metrics):
        """记录性能数据"""
        self.info(
            f"性能: {operation}",
            operation=operation,
            duration_ms=duration_ms,
            metrics=metrics,
        )


class LoggerFactory:
    """日志记录器工厂"""

    _loggers: Dict[str, StructuredLogger] = {}
    _initialized = False

    @classmethod
    def configure(cls, log_level: str = "INFO", json_output: bool = True):
        """配置日志系统"""
        if cls._initialized:
            return

        # 配置根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        # 清除现有处理器
        root_logger.handlers = []

        # 添加控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        if json_output:
            # 使用 JSON 格式
            formatter = StructuredLogFormatter()
        else:
            # 使用标准格式
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        cls._initialized = True

    @classmethod
    def get_logger(cls, name: str) -> StructuredLogger:
        """获取或创建日志记录器"""
        if name not in cls._loggers:
            cls._loggers[name] = StructuredLogger(name)
        return cls._loggers[name]

    @classmethod
    def reset(cls):
        """重置日志配置"""
        cls._initialized = False
        cls._loggers.clear()


@contextmanager
def log_operation_context(operation: str, context_id: str, **metadata):
    """上下文管理器 - 追踪操作执行"""
    with LogContext(context_id, operation, **metadata) as ctx:
        logger = LoggerFactory.get_logger(__name__)
        logger.info(f"开始操作: {operation}", context=ctx.to_dict())
        try:
            yield logger
            logger.info(f"完成操作: {operation}", context=ctx.to_dict())
        except Exception as e:
            logger.error(
                f"操作失败: {operation}",
                exception=str(e),
                context=ctx.to_dict(),
            )
            raise
