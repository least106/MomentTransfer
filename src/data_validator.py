"""
数据校验工具

包含用于检查 DataFrame 与特殊格式解析结果的简单校验逻辑，
并返回可展示给用户的可读 issue 列表。

注：本模块负责快速、轻量的检测（空表、全空列/行、编码问题等），
不替代深度的格式验证，但可用于在 UI 层及时提示用户。
"""
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def _safe_is_dataframe_like(obj) -> bool:
    try:
        # pandas DataFrame duck-typing
        return hasattr(obj, "shape") and hasattr(obj, "columns")
    except Exception:
        return False


def validate_dataframe(df, file_path: Optional[Path] = None) -> List[str]:
    """对 pandas DataFrame 进行基本校验。

    返回 issue 列表（空列表表示无问题）。可包含中文描述，供 UI 直接展示。
    """
    issues: List[str] = []
    try:
        if df is None:
            issues.append("无法读取表格或解析失败")
            return issues

        if not _safe_is_dataframe_like(df):
            issues.append("读取到的对象不是表格结构")
            return issues

        try:
            rows, cols = int(df.shape[0]), int(df.shape[1])
        except Exception:
            rows, cols = 0, 0

        if rows == 0 or cols == 0:
            issues.append("表格为空或列/行数为0")

        # 检查是否大量为空列或空行
        try:
            # 若超过50%列全为空，提示可能的数据缺失或格式问题
            empty_cols = 0
            for c in df.columns:
                try:
                    if df[c].isna().all():
                        empty_cols += 1
                except Exception:
                    pass
            if cols > 0 and empty_cols / max(1, cols) > 0.5:
                issues.append("表格有大量空列，可能格式不匹配或列分隔符错误")
        except Exception:
            logger.debug("校验空列时发生错误", exc_info=True)

        # 检查是否有所有值为空的前几行（常见带注释的文件）
        try:
            head = df.head(5)
            if head.shape[0] > 0 and head.isna().all(axis=1).all():
                issues.append("表格前几行全部为空，可能包含非结构化的头部信息或编码解析异常")
        except Exception:
            pass

    except Exception as e:
        logger.debug("validate_dataframe failed: %s", e, exc_info=True)
        issues.append("数据校验时发生内部错误")
    return issues


def validate_special_data_dict(data_dict: Optional[Dict], file_path: Optional[Path] = None) -> List[str]:
    """对特殊格式解析结果进行校验。

    data_dict 期望为 {part_name: DataFrame}
    """
    issues: List[str] = []
    try:
        if not data_dict:
            issues.append("解析结果为空：未发现任何内部部件或数据")
            return issues

        # 至少包含一个 part 且每个 part 非空
        empty_parts = []
        for k, v in (data_dict.items() if isinstance(data_dict, dict) else []):
            try:
                if v is None or (hasattr(v, "shape") and v.shape[0] == 0):
                    empty_parts.append(str(k))
            except Exception:
                empty_parts.append(str(k))
        if empty_parts:
            issues.append(f"以下部件解析为空或缺失数据：{', '.join(empty_parts)}")
    except Exception as e:
        logger.debug("validate_special_data_dict failed: %s", e, exc_info=True)
        issues.append("特殊格式数据校验时发生内部错误")
    return issues


def check_file_encoding(file_path: Path) -> List[str]:
    """尝试以常见编码读取文件的前几 KB，检测显著的解码错误并返回提示。"""
    issues: List[str] = []
    try:
        if not file_path or not file_path.exists():
            issues.append("文件不存在")
            return issues
        # 尝试 utf-8
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                _ = f.read(4096)
            return issues
        except UnicodeDecodeError:
            issues.append("文件无法用 UTF-8 解码，可能为其他编码（如 GBK/latin1）")
            # 不立即失败，尝试 latin-1 以便继续处理但提示用户
            try:
                with open(file_path, "r", encoding="latin-1") as f:
                    _ = f.read(4096)
                return issues
            except UnicodeDecodeError:
                issues.append("即使使用 latin-1 解码也失败，文件可能已损坏或为二进制格式")
                return issues
        except Exception:
            # 其他读取错误（权限等）
            issues.append("读取文件时发生错误（权限/IO）")
            return issues
    except Exception as e:
        logger.debug("check_file_encoding failed: %s", e, exc_info=True)
        issues.append("文件编码检查时发生内部错误")
        return issues
