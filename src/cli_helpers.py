"""CLI 共享帮助与验证函数

包含日志配置与几何配置加载的公共逻辑，供 `cli.py` 和 `batch.py` 复用。
"""

import json

# pylint: disable=too-many-arguments,too-many-locals
import logging
from pathlib import Path
from copy import deepcopy
from typing import Optional

from src.data_loader import ProjectData, load_data, try_load_project_data
from src.physics import AeroCalculator
from src.format_registry import get_format_for_file

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
    print("\n=== 数据格式配置 ===")
    config = BatchConfig()

    # 跳过行数
    skip_input = input("需要跳过的表头行数 (默认0): ").strip()
    if skip_input:
        try:
            config.skip_rows = int(skip_input)
        except ValueError:
            print("[警告] 无效输入，使用默认值0")

    print("\n请指定数据列位置 (从0开始计数，留空表示该列不存在):")

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
                    print("    [错误] 请输入有效的列号")
            else:
                print("    [错误] 此列为必需项")

    # 需要保留的列
    print("\n需要原样输出的其他列 (用逗号分隔列号，如: 0,1,2):")
    passthrough = input("  列号: ").strip()
    if passthrough:
        try:
            config.passthrough_columns = [
                int(x.strip()) for x in passthrough.split(",")
            ]
        except ValueError:
            print("[警告] 格式错误，将不保留额外列")

    return config


def resolve_file_format(
    file_path: str,
    global_cfg: BatchConfig,
    *,
    enable_sidecar: bool = False,
    registry_db: str = None,
    sidecar_suffixes=(".format.json", ".json"),
    dir_default_name="format.json",
) -> BatchConfig:
    """为单个数据文件解析并返回最终的 BatchConfig。

    **重要变化**: 默认情况下（`enable_sidecar=False`）不会查询 file-sidecar、目录级 `format.json` 或 registry，
    而是直接返回 `global_cfg` 的深拷贝（推荐用于生产）。当需要按文件覆盖配置以做示例或调试
    时，可将 `enable_sidecar=True` 并提供相应的侧车/目录/registry 资源来启用原始行为。

    返回的是一个 `BatchConfig` 的深拷贝，基于 `global_cfg` ，并由本地配置覆盖相应字段（仅当
    enable_sidecar=True 时才会执行覆盖逻辑）。
    """
    p = Path(file_path)
    # 开始于全局配置的拷贝
    cfg = deepcopy(global_cfg)

    # 若未启用侧车/目录/registry 策略，则直接返回 global_cfg 的拷贝（生产默认行为）
    if not enable_sidecar:
        return cfg

    # 以下为原有的侧车/目录/registry 查找逻辑（仅在 enable_sidecar=True 时执行）

    # 0) 优先查询 registry（若提供）
    if registry_db:
        try:
            reg_fmt = get_format_for_file(registry_db, file_path)
            if reg_fmt:
                local = load_format_from_file(str(reg_fmt))
                _merge_batch_config(cfg, local)
                return cfg
        except (OSError, ValueError) as exc:
            # registry 查询失败时不阻塞，降级到本地侧车/目录/全局策略，但记录具体原因便于排查
            logger.warning(
                "Registry lookup failed for file %r with registry_db %r: %s",
                file_path,
                registry_db,
                exc,
            )

    # 1) 检查 file-sidecar
    stem = p.stem
    parent = p.parent
    for suf in sidecar_suffixes:
        candidate = parent / f"{stem}{suf}"
        if candidate.exists():
            local = load_format_from_file(str(candidate))
            # 覆盖 cfg
            _merge_batch_config(cfg, local)
            return cfg

    # 2) 检查目录级默认
    dir_candidate = parent / dir_default_name
    if dir_candidate.exists():
        local = load_format_from_file(str(dir_candidate))
        _merge_batch_config(cfg, local)
        return cfg

    # 3) 否则返回全局（已拷贝）
    return cfg


def _merge_batch_config(dst: BatchConfig, src: BatchConfig) -> None:
    """把 src 的非空/非默认字段合并到 dst（就地修改 dst）。"""
    # 简单策略：直接覆盖字段（列映射中以非 None 值覆盖）
    dst.skip_rows = int(src.skip_rows)
    for k, v in src.column_mappings.items():
        if v is not None:
            dst.column_mappings[k] = int(v)
    if src.passthrough_columns:
        dst.passthrough_columns = list(src.passthrough_columns)
    dst.chunksize = src.chunksize
    dst.name_template = src.name_template
    dst.timestamp_format = src.timestamp_format
    dst.overwrite = bool(src.overwrite)
    dst.treat_non_numeric = src.treat_non_numeric
    dst.sample_rows = int(src.sample_rows)


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
        except Exception as e:  # pylint: disable=broad-except
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
