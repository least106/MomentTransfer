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
from src.format_registry import get_format_for_file
from src.physics import AeroCalculator

# 模块级 logger，供文件中函数使用（配置由 `configure_logging` 管理）
logger = logging.getLogger("batch")


class BatchConfig:  # pylint: disable=R0902,R0903
    """批处理配置类（供 batch.py 使用，抽取以便复用）。"""

    def __init__(self):
        self.skip_rows = 0
        self.column_mappings = {
            "alpha": None,
            "fx": None,
            "fy": None,
            "fz": None,
            "mx": None,
            "my": None,
            "mz": None,
        }
        self.passthrough_columns = []
        self.chunksize = None
        self.name_template = "{stem}_result_{timestamp}.csv"
        self.timestamp_format = "%Y%m%d_%H%M%S"
        self.overwrite = False
        self.treat_non_numeric = "zero"
        self.sample_rows = 5


def load_format_from_file(path: str) -> BatchConfig:  # pylint: disable=R0912
    """从 JSON 文件加载 BatchConfig（保留原有行为并提高错误说明）。"""
    p = Path(path)
    if not p.exists():
        # 兼容测试或从不同工作目录启动时的相对路径解析
        if not p.is_absolute():
            repo_root = Path(__file__).resolve().parents[1]
            alt = repo_root / p
            if alt.exists():
                p = alt
            else:
                raise FileNotFoundError(f"格式文件未找到: {path}")
        else:
            raise FileNotFoundError(f"格式文件未找到: {path}")
    with open(p, "r", encoding="utf-8") as fh:
        text = fh.read()
    if not text or not text.strip():
        raise ValueError(f"格式文件为空或仅包含空白: {path}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"格式文件不是有效的 JSON: {path} -> {e}") from e

    cfg = BatchConfig()
    cfg.skip_rows = int(data.get("skip_rows", 0))
    cols = data.get("columns", {})
    for k in cfg.column_mappings:
        if k in cols:
            v = cols[k]
            cfg.column_mappings[k] = int(v) if v is not None else None
    cfg.passthrough_columns = [int(x) for x in data.get("passthrough", [])]
    if "chunksize" in data:
        try:
            cfg.chunksize = int(data.get("chunksize"))
        except (TypeError, ValueError):
            cfg.chunksize = None
    if "name_template" in data:
        cfg.name_template = str(data.get("name_template"))
    if "timestamp_format" in data:
        cfg.timestamp_format = str(data.get("timestamp_format"))
    if "overwrite" in data:
        cfg.overwrite = bool(data.get("overwrite"))
    if "treat_non_numeric" in data:
        cfg.treat_non_numeric = str(data.get("treat_non_numeric"))
    if "sample_rows" in data:
        try:
            cfg.sample_rows = int(data.get("sample_rows"))
        except (TypeError, ValueError):
            cfg.sample_rows = 5
    return cfg


def get_user_file_format() -> BatchConfig:
    """交互式获取用户数据格式配置，供命令行交互使用。

    虽然这是交互函数，但放在此处可将所有与数据格式相关的逻辑集中。
    """
    logger.info("=== 数据格式配置 ===")
    config = BatchConfig()

    # 跳过行数
    skip_input = input("需要跳过的表头行数 (默认0): ").strip()
    if skip_input:
        try:
            config.skip_rows = int(skip_input)
        except ValueError:
            logger.warning("无效输入，使用默认值0")

    logger.info("请指定数据列位置 (从0开始计数，留空表示该列不存在):")

    # 可选的迎角列
    alpha_col = input("  迎角 Alpha 列号: ").strip()
    if alpha_col:
        try:
            config.column_mappings["alpha"] = int(alpha_col)
        except ValueError:
            pass

    # 必需的力和力矩列
    required_mappings = {
        "fx": "轴向力 Fx",
        "fy": "侧向力 Fy",
        "fz": "法向力 Fz",
        "mx": "滚转力矩 Mx",
        "my": "俯仰力矩 My",
        "mz": "偏航力矩 Mz",
    }

    for key, label in required_mappings.items():
        while True:
            col_input = input(f"  {label} 列号 (必需): ").strip()
            if col_input:
                try:
                    config.column_mappings[key] = int(col_input)
                    break
                except ValueError:
                    logger.error("    [错误] 请输入有效的列号")
            else:
                logger.error("    [错误] 此列为必需项")

    # 需要保留的列
    logger.info("需要原样输出的其他列 (用逗号分隔列号，如: 0,1,2):")
    passthrough = input("  列号: ").strip()
    if passthrough:
        try:
            config.passthrough_columns = [
                int(x.strip()) for x in passthrough.split(",")
            ]
        except ValueError:
            logger.warning("格式错误，将不保留额外列")

    return config


def resolve_file_format(
    file_path: str,
    global_cfg: BatchConfig,
) -> BatchConfig:
    """为单个数据文件返回全局配置的深拷贝。

    此函数不再支持 per-file 配置覆盖（sidecar/registry/目录级配置），
    确保批处理过程中使用一致的全局配置。

    参数：
        file_path: 数据文件路径（用于日志记录）
        global_cfg: 全局批处理配置

    返回值：
        global_cfg 的深拷贝
    """
    # 返回全局配置的深拷贝
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
        # 在包含多个 Target part 的情况下：
        # - CLI 层（interactive）会要求用户显式指定；
        # - 但在库/测试层面，为保持向后兼容，我们在此自动选取第一个 Part（并以日志形式提示）。
        if isinstance(project_data, ProjectData) and target_part is None:
            if len(project_data.target_parts) == 1:
                target_part = next(iter(project_data.target_parts.keys()))
            else:
                logger.warning(
                    "配置包含多个 Target part，未指定 --target-part，已自动选择第一个 Part。建议在 CLI 中显式指定。"
                )
                target_part = next(iter(project_data.target_parts.keys()))

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
