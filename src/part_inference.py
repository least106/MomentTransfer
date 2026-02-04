"""Part 推测引擎 - 智能匹配数据文件中的 part 名称到配置中的 source/target part。

提供多层级推测策略：
1. 精确匹配（同名）
2. 模糊匹配（大小写不敏感、去除特殊字符）
3. 包含关系匹配（子串匹配）
4. 默认策略（选择第一个可用项并警告）
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PartInferenceResult:
    """Part 推测结果，包含推测的part名称、置信度和推测依据。"""

    def __init__(
        self,
        part_name: Optional[str],
        confidence: str,
        method: str,
        candidates: List[str] = None,
    ):
        """
        Args:
            part_name: 推测的part名称，None表示无法推测
            confidence: 置信度等级 "high"/"medium"/"low"/"none"
            method: 推测方法 "exact"/"fuzzy"/"contains"/"default"/"failed"
            candidates: 所有候选项列表（用于错误提示）
        """
        self.part_name = part_name
        self.confidence = confidence
        self.method = method
        self.candidates = candidates or []

    def is_successful(self) -> bool:
        """是否成功推测出part名称。"""
        return self.part_name is not None

    def __repr__(self):
        return f"PartInferenceResult(part={self.part_name}, " f"confidence={self.confidence}, method={self.method})"


def _normalize_name(name: str) -> str:
    """标准化名称：转小写、去除下划线/连字符/空格。"""
    if not isinstance(name, str):
        return ""
    return re.sub(r"[_\-\s]+", "", name.lower())


def _exact_match(query: str, available_parts: Dict) -> Optional[str]:
    """精确匹配：查找完全相同的part名称（大小写敏感）。"""
    return query if query in available_parts else None


def _fuzzy_match(query: str, available_parts: Dict) -> Optional[str]:
    """模糊匹配：标准化后比较（大小写不敏感、忽略分隔符）。"""
    normalized_query = _normalize_name(query)
    if not normalized_query:
        return None

    for part_name in available_parts.keys():
        if _normalize_name(part_name) == normalized_query:
            return part_name
    return None


def _contains_match(query: str, available_parts: Dict) -> Optional[str]:
    """包含关系匹配：查找query包含part名或part名包含query的情况。"""
    normalized_query = _normalize_name(query)
    if not normalized_query:
        return None

    # 优先查找：query 包含 part名
    for part_name in available_parts.keys():
        normalized_part = _normalize_name(part_name)
        if normalized_part and normalized_part in normalized_query:
            logger.debug("包含匹配成功：'%s' 包含 '%s'", query, part_name)
            return part_name

    # 次选：part名 包含 query
    for part_name in available_parts.keys():
        normalized_part = _normalize_name(part_name)
        if normalized_part and normalized_query in normalized_part:
            logger.debug("包含匹配成功：'%s' 包含于 '%s'", query, part_name)
            return part_name

    return None


def infer_source_part(
    part_name: str,
    available_sources: Dict,
    strategy: str = "fuzzy",
    allow_default: bool = True,
) -> PartInferenceResult:
    """智能推测 source part。

    Args:
        part_name: 来自文件的 part 名称
        available_sources: 配置中的 source_parts 字典
        strategy: 推测策略 "strict"（仅精确+模糊）或 "fuzzy"（包含所有策略）
        allow_default: 无法推测时是否允许使用默认值（第一个可用项）

    Returns:
        PartInferenceResult 对象
    """
    if not available_sources:
        logger.warning("配置中无可用的 source parts")
        return PartInferenceResult(None, "none", "failed", [])

    available_names = list(available_sources.keys())

    # 策略1: 精确匹配
    result = _exact_match(part_name, available_sources)
    if result:
        logger.info("Source part 精确匹配成功：'%s' → '%s'", part_name, result)
        return PartInferenceResult(result, "high", "exact", available_names)

    # 策略2: 模糊匹配（标准化比较）
    result = _fuzzy_match(part_name, available_sources)
    if result:
        logger.info("Source part 模糊匹配成功：'%s' → '%s'", part_name, result)
        return PartInferenceResult(result, "high", "fuzzy", available_names)

    # 策略3: 包含关系匹配（仅在 fuzzy 策略时启用）
    if strategy == "fuzzy":
        result = _contains_match(part_name, available_sources)
        if result:
            logger.info("Source part 包含匹配成功：'%s' → '%s'", part_name, result)
            return PartInferenceResult(result, "medium", "contains", available_names)

    # 策略4: 默认策略（唯一选项自动选择）
    if len(available_names) == 1:
        result = available_names[0]
        logger.info(
            "Source part 唯一选项自动选择：'%s' → '%s'（配置中仅此一项）",
            part_name,
            result,
        )
        return PartInferenceResult(result, "medium", "default", available_names)

    # 策略5: 多选项默认策略（选第一个并警告）
    if allow_default and len(available_names) > 1:
        result = available_names[0]
        logger.warning(
            "Source part 无法精确匹配 '%s'，使用默认值 '%s'（可用选项：%s）",
            part_name,
            result,
            ", ".join(available_names),
        )
        return PartInferenceResult(result, "low", "default", available_names)

    # 推测失败
    logger.error(
        "无法为 '%s' 推测 source part（可用选项：%s）",
        part_name,
        ", ".join(available_names),
    )
    return PartInferenceResult(None, "none", "failed", available_names)


def infer_target_part(
    source_part: str,
    available_targets: Dict,
    file_path: Optional[Path] = None,
    strategy: str = "fuzzy",
    allow_default: bool = True,
) -> PartInferenceResult:
    """智能推测 target part。

    Args:
        source_part: 已确定的 source part 名称
        available_targets: 配置中的 target_parts 字典
        file_path: 输入文件路径（用于文件名匹配）
        strategy: 推测策略 "strict" 或 "fuzzy"
        allow_default: 无法推测时是否允许使用默认值

    Returns:
        PartInferenceResult 对象
    """
    if not available_targets:
        logger.warning("配置中无可用的 target parts")
        return PartInferenceResult(None, "none", "failed", [])

    available_names = list(available_targets.keys())

    # 策略1: 精确匹配（同名 target）
    result = _exact_match(source_part, available_targets)
    if result:
        logger.info(
            "Target part 精确匹配成功（同名）：source '%s' → target '%s'",
            source_part,
            result,
        )
        return PartInferenceResult(result, "high", "exact", available_names)

    # 策略2: 文件名匹配（如果提供了文件路径）
    if file_path:
        file_stem = file_path.stem  # 不含扩展名的文件名
        result = _fuzzy_match(file_stem, available_targets)
        if result:
            logger.info(
                "Target part 文件名匹配成功：file '%s' → target '%s'",
                file_path.name,
                result,
            )
            return PartInferenceResult(result, "medium", "fuzzy", available_names)

    # 策略3: 模糊匹配 source_part 到 target
    result = _fuzzy_match(source_part, available_targets)
    if result:
        logger.info(
            "Target part 模糊匹配成功：source '%s' → target '%s'",
            source_part,
            result,
        )
        return PartInferenceResult(result, "high", "fuzzy", available_names)

    # 策略4: 包含关系匹配
    if strategy == "fuzzy":
        result = _contains_match(source_part, available_targets)
        if result:
            logger.info(
                "Target part 包含匹配成功：source '%s' → target '%s'",
                source_part,
                result,
            )
            return PartInferenceResult(result, "medium", "contains", available_names)

    # 策略5: 唯一选项自动选择
    if len(available_names) == 1:
        result = available_names[0]
        logger.info("Target part 唯一选项自动选择：'%s'（配置中仅此一项）", result)
        return PartInferenceResult(result, "medium", "default", available_names)

    # 策略6: 多选项默认策略
    if allow_default and len(available_names) > 1:
        result = available_names[0]
        logger.warning(
            "Target part 无法精确匹配 source '%s'，使用默认值 '%s'（可用选项：%s）",
            source_part,
            result,
            ", ".join(available_names),
        )
        return PartInferenceResult(result, "low", "default", available_names)

    # 推测失败
    logger.error(
        "无法为 source '%s' 推测 target part（可用选项：%s）",
        source_part,
        ", ".join(available_names),
    )
    return PartInferenceResult(None, "none", "failed", available_names)


def infer_parts_for_file(
    part_name: str,
    project_data,
    file_path: Optional[Path] = None,
    strategy: str = "fuzzy",
    allow_default: bool = True,
) -> Tuple[PartInferenceResult, PartInferenceResult]:
    """为单个文件同时推测 source 和 target part。

    Args:
        part_name: 来自文件的 part 名称
        project_data: ProjectData 对象（含 source_parts 和 target_parts）
        file_path: 输入文件路径
        strategy: 推测策略
        allow_default: 是否允许使用默认值

    Returns:
        (source_result, target_result) 元组
    """
    source_parts = getattr(project_data, "source_parts", {}) or {}
    target_parts = getattr(project_data, "target_parts", {}) or {}

    # 推测 source part
    source_result = infer_source_part(part_name, source_parts, strategy=strategy, allow_default=allow_default)

    # 推测 target part
    if source_result.is_successful():
        target_result = infer_target_part(
            source_result.part_name,
            target_parts,
            file_path=file_path,
            strategy=strategy,
            allow_default=allow_default,
        )
    else:
        # source 推测失败，target 也无法推测
        target_result = PartInferenceResult(None, "none", "failed", list(target_parts.keys()))

    return source_result, target_result


def format_inference_error(
    part_name: str,
    result: PartInferenceResult,
    part_type: str = "source",
    suggest_param: str = "--source-part",
) -> str:
    """格式化推测失败的错误消息，提供用户可操作的建议。

    Args:
        part_name: 原始 part 名称
        result: 推测结果对象
        part_type: "source" 或 "target"
        suggest_param: 建议使用的参数名

    Returns:
        格式化的错误消息字符串
    """
    if result.is_successful():
        return ""

    if not result.candidates:
        return f"配置中无可用的 {part_type} part"

    candidates_str = ", ".join(result.candidates)
    error_msg = (
        f"无法为 '{part_name}' 推测 {part_type} part\n"
        f"可用选项：{candidates_str}\n"
        f"建议：使用 {suggest_param} <part名称> 参数明确指定"
    )

    # 如果只有一个候选且推测失败，给出更具体的建议
    if len(result.candidates) == 1:
        error_msg += f"\n示例：{suggest_param} {result.candidates[0]}"

    return error_msg


__all__ = [
    "PartInferenceResult",
    "infer_source_part",
    "infer_target_part",
    "infer_parts_for_file",
    "format_inference_error",
]
