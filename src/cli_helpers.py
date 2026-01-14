"""CLI 共享帮助与验证函数

包含日志配置与几何配置加载的公共逻辑，供 `cli.py` 和 `batch.py` 复用。
"""

import json

# pylint: disable=too-many-arguments,too-many-locals
import logging
from copy import deepcopy
from pathlib import Path
from typing import Optional

from src.data_loader import ProjectData, load_data, try_load_project_data
from src.physics import AeroCalculator

# 模块级 logger，供文件中函数使用（配置由 `configure_logging` 管理）
logger = logging.getLogger("batch")


class BatchConfig:  # pylint: disable=R0902,R0903
    """批处理配置类（供 batch.py 使用，简化为固定表头语义）。"""

    def __init__(self):
        self.skip_rows = 0
        self.name_template = "{stem}_result_{timestamp}.csv"
        self.timestamp_format = "%Y%m%d_%H%M%S"
        self.overwrite = False
        self.treat_non_numeric = "zero"
        self.sample_rows = 5


def resolve_file_format(
    file_path: str,
    global_cfg: BatchConfig,
) -> BatchConfig:
    """为单个数据文件返回全局配置的深拷贝。

    参数：
        file_path: 数据文件路径（用于日志记录）
        global_cfg: 全局批处理配置

    返回值：
        global_cfg 的深拷贝
    """
    return deepcopy(global_cfg)


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
            # 仅记录调试信息，避免在关闭 handler 时抛出
            batch_logger.debug(
                "关闭日志 handler 时遇到异常（忽略）: %s", e, exc_info=True
            )

    fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

    stream_h = logging.StreamHandler()
    stream_h.setLevel(log_level)
    stream_h.setFormatter(fmt)
    batch_logger.addHandler(stream_h)

    if log_file:
        file_h = logging.FileHandler(log_file, encoding="utf-8")
        # 若指定了 log_file，文件中记录详细调试信息（包含完整堆栈）以便排查
        file_h.setLevel(logging.DEBUG)
        file_h.setFormatter(fmt)
        batch_logger.addHandler(file_h)
    # 不向根 logger 传播，避免重复日志
    batch_logger.propagate = False

    return batch_logger


# pylint: disable=too-many-arguments,too-many-locals
def load_project_calculator(
    config_path: str,
    *,
    source_part: str = None,
    source_variant: int = 0,
    target_part: str = None,
    target_variant: int = 0,
):  # pylint: disable=too-many-arguments,too-many-locals
    """加载几何/项目配置并返回 (project_data, AeroCalculator)

    支持可选的 part/variant 指定以便直接构造使用特定 variant 的计算器。
    若加载失败会抛出 ValueError，消息对用户更友好。
    """
    # pylint: disable=too-many-arguments,too-many-locals
    try:
        project_data = load_data(config_path)
        # target_part 指定将数据转换到哪个目标坐标系
        # - 配置仅 1 个 target：自动选择
        # - 配置多个 target：由调用方根据场景指定
        #   * 批处理：每个文件会指定使用的 target（普通文件用户选择，特殊文件按 part 映射）
        #   * CLI 单文件：通过 --target-part 参数指定
        if isinstance(project_data, ProjectData) and target_part is None:
            if len(project_data.target_parts) == 1:
                target_part = next(iter(project_data.target_parts.keys()))
                logger.debug("配置仅有一个 Target 坐标系，已自动选择: %s", target_part)
            else:
                logger.debug(
                    "配置包含 %d 个 Target 坐标系，未指定 target_part，"
                    "将在后续处理中根据文件类型确定",
                    len(project_data.target_parts)
                )

        calculator = AeroCalculator(
            project_data,
            source_part=source_part,
            source_variant=source_variant,
            target_part=target_part,
            target_variant=target_variant,
        )
        return project_data, calculator
    except FileNotFoundError as e:
        raise ValueError(f"配置文件未找到: {config_path}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件不是有效的 JSON: {config_path} -> {e}") from e
    except KeyError as e:
        raise ValueError(f"配置文件缺少必要字段: {e}") from e


def attempt_load_project_data(path: str, *, strict: bool = True):
    """
    便捷包装：尝试加载项目数据并根据 strict 策略返回或抛出异常。

    - 成功：返回 ProjectData
    - 失败且 strict=True：抛出 ValueError，消息友好
    - 失败且 strict=False：返回 (None, info_dict)
    """
    ok, project_data, info = try_load_project_data(path, strict=strict)
    if ok:
        return project_data
    if strict:
        # 抛出包含建议的错误，便于上层捕获并显示
        raise ValueError(
            f"加载配置失败: {info.get('message')} 建议: {info.get('suggestion')}"
        )
    return None, info
