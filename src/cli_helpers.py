"""兼容性导出：将旧有 `src.cli_helpers` 的公共符号重导出自新拆分模块。

该文件旨在作为向后兼容的 shim，允许逐步重构而不破坏大量导入点。
"""

from typing import Any
import logging

# 直接从拆分后的模块导入符号并重导出
from src.batch_config import BatchConfig, resolve_file_format
from src.logging_config import configure_logging
from src.calculator_factory import load_project_calculator, attempt_load_project_data

# 保留模块级 logger 以兼容现有代码使用 logging.getLogger("batch") 之外的直接引用
logger = logging.getLogger("batch")

__all__ = [
    "BatchConfig",
    "resolve_file_format",
    "configure_logging",
    "load_project_calculator",
    "attempt_load_project_data",
    "logger",
]
