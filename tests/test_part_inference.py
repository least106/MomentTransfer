"""测试 Part 推测引擎功能"""

import pytest

from src.part_inference import (
    PartInferenceResult,
    format_inference_error,
    infer_source_part,
    infer_target_part,
)


def test_exact_match():
    """测试精确匹配"""
    available = {"BodyAxis": {}, "WindAxis": {}}
    result = infer_source_part("BodyAxis", available)

    assert result.is_successful()
    assert result.part_name == "BodyAxis"
    assert result.method == "exact"
    assert result.confidence == "high"


def test_fuzzy_match_case_insensitive():
    """测试大小写不敏感的模糊匹配"""
    available = {"BodyAxis": {}, "WindAxis": {}}
    result = infer_source_part("bodyaxis", available)

    assert result.is_successful()
    assert result.part_name == "BodyAxis"
    assert result.method == "fuzzy"
    assert result.confidence == "high"


def test_fuzzy_match_with_separators():
    """测试忽略分隔符的模糊匹配"""
    available = {"BodyAxis": {}, "WindAxis": {}}
    result = infer_source_part("body_axis", available)

    assert result.is_successful()
    assert result.part_name == "BodyAxis"
    assert result.method == "fuzzy"
    assert result.confidence == "high"


def test_contains_match_query_contains_part():
    """测试包含关系匹配：query包含part名"""
    available = {"Body": {}, "Wind": {}}
    result = infer_source_part("BodyAxis", available, strategy="fuzzy")

    assert result.is_successful()
    assert result.part_name == "Body"
    assert result.method == "contains"
    assert result.confidence == "medium"


def test_contains_match_part_contains_query():
    """测试包含关系匹配：part名包含query"""
    available = {"BodyAxisSystem": {}, "WindAxisSystem": {}}
    result = infer_source_part("Body", available, strategy="fuzzy")

    assert result.is_successful()
    assert result.part_name == "BodyAxisSystem"
    assert result.method == "contains"
    assert result.confidence == "medium"


def test_single_option_auto_select():
    """测试唯一选项自动选择"""
    available = {"OnlyOne": {}}
    result = infer_source_part("SomethingElse", available)

    assert result.is_successful()
    assert result.part_name == "OnlyOne"
    assert result.method == "default"
    assert result.confidence == "medium"


def test_multiple_options_default():
    """测试多选项时的默认策略"""
    available = {"First": {}, "Second": {}, "Third": {}}
    result = infer_source_part("NoMatch", available, allow_default=True)

    assert result.is_successful()
    assert result.part_name == "First"  # 选择第一个
    assert result.method == "default"
    assert result.confidence == "low"  # 低置信度


def test_multiple_options_no_default():
    """测试禁用默认策略时推测失败"""
    available = {"First": {}, "Second": {}}
    result = infer_source_part("NoMatch", available, allow_default=False)

    assert not result.is_successful()
    assert result.part_name is None
    assert result.method == "failed"
    assert result.confidence == "none"
    assert len(result.candidates) == 2


def test_strict_strategy_no_contains_match():
    """测试strict策略不使用包含匹配"""
    available = {"BodyAxisSystem": {}}
    result = infer_source_part("Body", available, strategy="strict")

    # strict策略下，只有精确和模糊匹配，不会进行包含匹配
    # 因为只有一个选项，会使用默认策略
    assert result.is_successful()
    assert result.part_name == "BodyAxisSystem"
    assert result.method == "default"


def test_empty_available_parts():
    """测试配置中无可用part"""
    result = infer_source_part("Something", {})

    assert not result.is_successful()
    assert result.part_name is None
    assert result.method == "failed"
    assert len(result.candidates) == 0


def test_target_exact_match():
    """测试target part精确匹配（同名）"""
    available = {"BodyAxis": {}, "WindAxis": {}}
    result = infer_target_part("BodyAxis", available)

    assert result.is_successful()
    assert result.part_name == "BodyAxis"
    assert result.method == "exact"
    assert result.confidence == "high"


def test_target_fuzzy_match():
    """测试target part模糊匹配"""
    available = {"BodyAxis": {}, "WindAxis": {}}
    result = infer_target_part("body_axis", available)

    assert result.is_successful()
    assert result.part_name == "BodyAxis"
    assert result.method == "fuzzy"
    assert result.confidence == "high"


def test_target_single_option():
    """测试target唯一选项自动选择"""
    available = {"OnlyTarget": {}}
    result = infer_target_part("SomeSource", available)

    assert result.is_successful()
    assert result.part_name == "OnlyTarget"
    assert result.method == "default"


def test_format_inference_error():
    """测试错误消息格式化"""
    result = PartInferenceResult(None, "none", "failed", ["Option1", "Option2"])
    error_msg = format_inference_error("TestPart", result, "source", "--source-part")

    assert "TestPart" in error_msg
    assert "Option1" in error_msg
    assert "Option2" in error_msg
    assert "--source-part" in error_msg


def test_format_inference_error_single_candidate():
    """测试单个候选项时的错误消息"""
    result = PartInferenceResult(None, "none", "failed", ["OnlyOne"])
    error_msg = format_inference_error("TestPart", result, "source", "--source-part")

    assert "OnlyOne" in error_msg
    assert "示例" in error_msg
    assert "--source-part OnlyOne" in error_msg


def test_inference_result_is_successful():
    """测试PartInferenceResult的is_successful方法"""
    success = PartInferenceResult("SomePart", "high", "exact")
    assert success.is_successful()

    failure = PartInferenceResult(None, "none", "failed")
    assert not failure.is_successful()
