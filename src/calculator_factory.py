"""项目/计算器加载工厂（拆分自 src.cli_helpers）
"""

import json
import logging

from src.data_loader import ProjectData, load_data, try_load_project_data
from src.physics import AeroCalculator

logger = logging.getLogger("batch")


# pylint: disable=too-many-arguments,too-many-locals
def load_project_calculator(
    config_path: str,
    *,
    source_part: str = None,
    source_variant: int = 0,
    target_part: str = None,
    target_variant: int = 0,
):
    """加载几何/项目配置并返回 (project_data, AeroCalculator)

    支持可选的 part/variant 指定以便直接构造使用特定 variant 的计算器。
    若加载失败会抛出 ValueError，消息对用户更友好。
    """
    try:
        project_data = load_data(config_path)
        if isinstance(project_data, ProjectData) and target_part is None:
            if len(project_data.target_parts) == 1:
                target_part = next(iter(project_data.target_parts.keys()))
                logger.debug(
                    "配置仅有一个 Target 坐标系，已自动选择: %s", target_part
                )
            else:
                logger.debug(
                    "配置包含 %d 个 Target 坐标系，未指定 target_part，"
                    "将在后续处理中根据文件类型确定",
                    len(project_data.target_parts),
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
        raise ValueError(
            f"配置文件不是有效的 JSON: {config_path} -> {e}"
        ) from e
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
        raise ValueError(
            f"加载配置失败: {info.get('message')} 建议: {info.get('suggestion')}"
        )
    return None, info
