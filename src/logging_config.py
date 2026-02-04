"""日志配置模块（拆分自 src.cli_helpers）
"""

import logging
from typing import Optional


def configure_logging(log_file: Optional[str], verbose: bool) -> logging.Logger:
    """配置并返回名为 `batch` 的 logger。

    实现要点：
    - 不调用 `logging.basicConfig()` 以避免影响全局根 logger。
    - 配置并返回专用的 `batch` logger。
    - 每次调用会重置该 logger 的 handlers（避免重复添加）。
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    batch_logger = logging.getLogger("batch")
    batch_logger.setLevel(log_level)

    # 清理已有 handlers（如果有），避免重复输出或多次添加
    for h in list(batch_logger.handlers):
        batch_logger.removeHandler(h)
        try:
            h.close()
        except (OSError, RuntimeError) as e:
            batch_logger.debug("关闭日志 handler 时遇到异常（忽略）: %s", e, exc_info=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

    stream_h = logging.StreamHandler()
    stream_h.setLevel(log_level)
    stream_h.setFormatter(fmt)
    batch_logger.addHandler(stream_h)

    if log_file:
        file_h = logging.FileHandler(log_file, encoding="utf-8")
        file_h.setLevel(logging.DEBUG)
        file_h.setFormatter(fmt)
        batch_logger.addHandler(file_h)

    batch_logger.propagate = False

    return batch_logger
