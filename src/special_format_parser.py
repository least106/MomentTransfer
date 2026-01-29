"""特殊格式数据文件解析器。

处理包含多个 part 数据块的文件，自动识别 part 名称和数据行。

约定（重要）：
- 特殊格式文件中的 part 名称视为 Source part 名称。
- Target part 仅通过 GUI/CLI 提供的映射（source->target）确定；若未提供映射，
    则仅在存在“同名 Target part”时才允许处理该块。
"""

# pylint: disable=wrong-import-position

import logging
import re
import sys

# 确保脚本运行时能找到 src 包（在引入本地 src 包之前调整 sys.path）
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from typing import Dict, List, Optional, Tuple  # noqa: E402

import pandas as pd  # noqa: E402

from src.special_format_detector import (  # noqa: E402
    _read_text_file_lines,
    _tokens_looks_like_header,
    is_data_line,
    is_metadata_line,
    is_part_name_line,
    is_summary_line,
)

logger = logging.getLogger(__name__)
# 在调整 sys.path 后才导入本地模块，允许导入位置非顶层的检查


def _normalize_column_mapping(columns: List[str]) -> Dict[str, str]:
    """为给定列名列表返回一个从原始列名到标准列名的映射。

    标准列名包括: 'Cx','Cy','Cz/FN','CMx','CMy','CMz' 等。
    此函数对常见变体进行容错处理，例如下划线替代、大小写差异、或 '/' 与 '_' 互换。
    """
    mapping = {}

    # 小写化并规范化下划线与斜杠和空格
    def norm(s: str) -> str:
        return s.strip().lower().replace("_", "/").replace(" ", "")

    canonical = {
        "cx": "Cx",
        "cy": "Cy",
        "cz/fn": "Cz/FN",
        "czfn": "Cz/FN",
        "cmx": "CMx",
        "cmy": "CMy",
        "cmz": "CMz",
        "alpha": "Alpha",
        "cl": "CL",
        "cd": "CD",
        "cm": "Cm",
    }

    for col in columns:
        key = norm(col)
        if key in canonical:
            mapping[col] = canonical[key]
        else:
            # 尝试去掉括号等特殊字符后匹配
            key2 = re.sub(r"[\(\)\[\]\-]", "", key)
            if key2 in canonical:
                mapping[col] = canonical[key2]
            else:
                mapping[col] = col

    return mapping


def _finalize_part(
    current_part, current_header, current_data, result: Dict[str, pd.DataFrame]
):
    """将当前累积的数据转换为 DataFrame 并加入 result（若数据存在）。"""
    if not (current_part and current_header and current_data):
        return
    try:
        df = pd.DataFrame(current_data, columns=current_header)
        col_map = _normalize_column_mapping(list(df.columns))
        df = df.rename(columns=col_map)
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            except (TypeError, ValueError) as exc:
                logger.debug(
                    "列 %s 转换为数值失败，保留原始值: %s",
                    col,
                    exc,
                    exc_info=True,
                )
        result[current_part] = df
        logger.info("解析 part '%s': %d 行数据", current_part, len(df))
    except ValueError as e:
        logger.warning("创建 DataFrame 失败 (part=%s): %s", current_part, e)


def _extract_parts_from_lines(
    lines: List[str], file_path: Path
) -> Dict[str, Tuple[Optional[List[str]], List[List[str]]]]:
    """从文本行中提取每个 part 的表头和原始数据行。

    返回字典: part_name -> (header_tokens, list_of_rows)
    """
    extracted_parts: Dict[str, Tuple[Optional[List[str]], List[List[str]]]] = (
        {}
    )
    current_part = None
    current_header = None
    current_data: List[List[str]] = []

    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line or is_metadata_line(line):
            continue

        next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else None
        if is_part_name_line(line, next_line):
            # 切换 part
            if current_part:
                extracted_parts[current_part] = (current_header, current_data)
            current_part = line.strip()
            current_header = None
            current_data = []
            continue

        if current_part and current_header is None:
            tokens = line.split()
            if _tokens_looks_like_header(tokens):
                current_header = tokens
                continue

        if current_part and current_header and is_data_line(line):
            tokens = line.split()
            if len(tokens) == len(current_header):
                current_data.append([t.strip() for t in tokens])
            else:
                logger.debug(
                    "跳过数据行（列数不匹配）：file=%s part=%s expected=%d got=%d line=%r",
                    file_path,
                    current_part,
                    len(current_header),
                    len(tokens),
                    line,
                )
            continue

        if is_summary_line(line):
            continue

    # 结束时保存最后一个 part
    if current_part:
        extracted_parts[current_part] = (current_header, current_data)

    return extracted_parts


def parse_special_format_file(file_path: Path) -> Dict[str, pd.DataFrame]:
    """
    解析特殊格式文件，返回 {part_name: DataFrame} 字典

    Args:
        file_path: 文件路径

    Returns:
        字典，键为 part 名称，值为对应的 DataFrame
    """
    # 该函数实现相对复杂，包含多分支与早期返回；暂保留对过多语句的忽略，后续分步重构
    # pylint: disable=R0915  # 待重构：逐步拆分此函数以移除此项
    lines = _read_text_file_lines(file_path)

    extracted = _extract_parts_from_lines(lines, file_path)
    result: Dict[str, pd.DataFrame] = {}
    for part_name, (hdr, rows) in extracted.items():
        _finalize_part(part_name, hdr, rows, result)

    return result


def process_special_format_file(
    file_path: Path,
    project_data,
    output_dir: Path,
    *,
    part_target_mapping: dict = None,
    part_source_mapping: dict = None,
    part_row_selection: dict = None,
    timestamp_format: str = "%Y%m%d_%H%M%S",
    overwrite: bool = False,
    return_report: bool = False,
):
    """兼容入口：委托给 `src.special_format_processor.process_special_format_file`。"""
    # 以下延迟导入是为避免循环导入；同时该函数参数较多，暂在此处抑制 pylint 的相关复杂度/导入位置警告。
    # pylint: disable=R0913,import-outside-toplevel
    from src.special_format_processor import process_special_format_file as _proc

    return _proc(
        file_path,
        project_data,
        output_dir,
        part_target_mapping=part_target_mapping,
        part_source_mapping=part_source_mapping,
        part_row_selection=part_row_selection,
        timestamp_format=timestamp_format,
        overwrite=overwrite,
        return_report=return_report,
    )


def get_part_names(file_path: Path) -> List[str]:
    """快速获取文件中的所有 part 名称（不解析完整数据）。

    Args:
        file_path: 文件路径

    Returns:
        part 名称列表
    """
    part_names: List[str] = []

    lines = _read_text_file_lines(file_path)

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line or is_metadata_line(line):
            i += 1
            continue

        next_line = lines[i + 1].strip() if i + 1 < len(lines) else None
        if is_part_name_line(line, next_line):
            part_names.append(line.strip())

        i += 1

    return part_names


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)

    test_file = Path("data/data_tmp")
    if test_file.exists():
        logger.info("解析文件: %s", test_file)

        # 获取 part 名称
        parts = get_part_names(test_file)
        logger.info("找到 %d 个 part:", len(parts))
        for part_item in parts:
            logger.info("  - %s", part_item)

        # 解析完整数据
        demo_data_dict = parse_special_format_file(test_file)
        logger.info("解析结果:")
        for demo_part_name, demo_df in demo_data_dict.items():
            logger.info("%s:", demo_part_name)
            try:
                logger.info("\n%s", demo_df.head().to_string())
            except (AttributeError, ValueError) as exc:
                logger.info("(无法显示 DataFrame 预览: %s)", exc)
            logger.info("  形状: %s", demo_df.shape)
