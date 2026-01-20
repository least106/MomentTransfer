"""特殊格式检测与探测工具。

负责判断文件是否为特殊格式，以及识别文件中的元数据/表头/数据/part 名行。
"""

import logging
import re
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# 推荐/支持的扩展名常量
RECOMMENDED_EXT = ".mtfmt"
SUPPORTED_EXTS = {".mtfmt", ".mtdata", ".txt", ".dat"}


def _read_text_file_lines(
    file_path: Path,
    *,
    max_lines: Optional[int] = None,
    encodings: Optional[List[str]] = None,
) -> List[str]:
    """尝试以多种编码读取文本文件，返回行列表。

    - 默认先尝试 `utf-8`，若失败依次尝试 `gbk` 和 `latin-1`。
    - max_lines: 若指定则只返回前若干行（用于探测）。
    """
    # 类型声明：encodings 可选且为字符串列表
    if encodings is None:
        encodings = ["utf-8", "gbk", "latin-1"]

    last_exc = None
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc, errors="strict") as fh:
                if max_lines is None:
                    return fh.readlines()
                # 读取全部并截取前若干行以避免产生空字符串占位
                return fh.readlines()[:max_lines]
        except UnicodeDecodeError as e:
            last_exc = e
            logger.debug("尝试以编码 %s 读取文件失败，切换下一编码", enc)
            continue
        except FileNotFoundError:
            raise
        except OSError as e:
            # 对于其他 I/O 错误，记录并重新抛出
            logger.debug("读取文件时遇到 I/O 错误: %s", e)
            raise

    # 最后保险回退：使用 latin-1 并允许替换不可解码字节
    try:
        with open(file_path, "r", encoding="latin-1", errors="replace") as fh:
            if max_lines is None:
                return fh.readlines()
            return fh.readlines()[:max_lines]
    except OSError:
        # 若此前有解码错误，优先抛出该错误以便上层判断编码问题
        if last_exc:
            raise last_exc
        raise


def _tokens_looks_like_header(tokens: List[str]) -> bool:
    """判断一组 token 是否像表头（包含 Alpha/CL/CD/Cm/Cx/Cy/Cz 等关键词）。"""
    if not tokens:
        return False
    header_keywords = ["Alpha", "CL", "CD", "Cm", "Cx", "Cy", "Cz"]
    hk_lower = [h.lower() for h in header_keywords]
    for t in tokens:
        tl = t.lower()
        if any(h in tl for h in hk_lower):
            return True
    return False


def is_metadata_line(line: str) -> bool:
    """判断是否为元数据行（非数据内容的描述行）"""
    line = line.strip()
    # 空行不视为元数据，以避免解析器误跳过可能紧随其后的数据行
    if not line:
        return False

    if "：" in line or (":" in line and not line[0].isdigit()):
        return True

    if re.search(r"[\u4e00-\u9fff]", line) and "：" not in line:
        tokens = line.split()
        if len(tokens) == 1 and len(line) < 20:
            return False
        return True

    return False


def is_summary_line(line: str) -> bool:
    """判断是否为汇总行（CLa Cdmin CmCL Cm0 Kmax 等）"""
    line = line.strip()
    if not line:
        return False

    tokens = line.split()
    if not tokens:
        return False

    first_token = tokens[0]
    if not first_token.replace("-", "").replace(".", "").replace("+", "").isdigit():
        summary_keywords = ["CLa", "Cdmin", "CmCL", "Cm0", "Kmax", "Alpha"]
        if any(kw in line for kw in summary_keywords):
            return True

    return False


def is_data_line(line: str) -> bool:
    """判断是否为数据行（以数字开头的行）"""
    line = line.strip()
    if not line:
        return False

    tokens = line.split()
    if not tokens:
        return False

    first_token = tokens[0]
    try:
        float(first_token)
        return True
    except ValueError:
        return False


def is_part_name_line(line: str, next_line: Optional[str] = None) -> bool:
    """判断是否为 part 名称行。

    特征：
    1. 单独一行，内容简短
    2. 可能是纯英文单词或中文
    3. 下一行很可能是表头（包含 Alpha, CL, CD 等）
    """
    line = line.strip()
    if not line or is_data_line(line) or is_summary_line(line):
        return False

    tokens = line.split()

    # 若自身像表头则不是 part 名
    if _tokens_looks_like_header(tokens):
        return False

    # 若下一行明显是表头，则当前行很可能是 part 名
    if next_line:
        next_tokens = next_line.split()
        if _tokens_looks_like_header(next_tokens):
            # 若为较长的中文描述，则即便下一行是表头也不视为 part
            contains_chinese = bool(re.search(r"[\u4e00-\u9fff]", line))
            if contains_chinese and len(line) >= 20:
                return False
            return True

    # 短文本（<20 字符）通常可视为 part 名；较长中文视为描述
    if len(line) < 20:
        return True

    contains_chinese = bool(re.search(r"[\u4e00-\u9fff]", line))
    if contains_chinese:
        return False

    # 对于非中文且较长的多 token 文本，默认不视为 part 名
    return False


def looks_like_special_format(file_path: Path, *, max_probe_lines: int = 20) -> bool:
    """快速判断文件是否符合特殊格式。"""
    p = Path(file_path)
    suffix = p.suffix.lower()
    if suffix in {".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".xlsb"}:
        return False

    if suffix in SUPPORTED_EXTS:
        return True

    try:
        lines = _read_text_file_lines(p, max_lines=max_probe_lines)
    except OSError:
        return False

    tokens = " ".join(lines)
    tokens_lower = tokens.lower()
    header_keywords = ["Alpha", "CL", "CD", "Cm", "Cx", "Cy", "Cz", "Cz/FN"]
    if any(kw.lower() in tokens_lower for kw in header_keywords):
        for ln in lines:
            ln = (ln or "").strip()
            if ln and not is_metadata_line(ln) and not is_data_line(ln):
                return True
    return False


__all__ = [
    "RECOMMENDED_EXT",
    "SUPPORTED_EXTS",
    "is_metadata_line",
    "is_summary_line",
    "is_data_line",
    "is_part_name_line",
    "looks_like_special_format",
]
