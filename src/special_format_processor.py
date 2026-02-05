"""特殊格式处理模块。

负责将解析后的特殊格式数据按 part 调用 AeroCalculator 计算并输出结果。
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from src.part_inference import format_inference_error, infer_parts_for_file
from src.physics import AeroCalculator

logger = logging.getLogger(__name__)

_PART_PROCESS_KEYS = (
    "part_target_mapping",
    "part_source_mapping",
    "part_row_selection",
    "timestamp_format",
    "overwrite",
)


def _collect_part_kwargs(values: Dict[str, object]) -> Dict[str, object]:
    """从给定字典中提取与 part 处理相关的参数。"""
    return {key: values.get(key) for key in _PART_PROCESS_KEYS}


# pylint: disable=R0913,R0914,R0915,R0912,R0911
# 这些函数将在后续迭代中进一步拆分和精简，以降低复杂度。
def _process_single_part(
    part_name,
    df,
    *,
    file_path,
    project_data,
    output_dir,
    part_target_mapping=None,
    part_source_mapping=None,
    part_row_selection=None,
    timestamp_format="%Y%m%d_%H%M%S",
    overwrite=False,
):
    """处理单个 part，返回 (out_path or None, report_entry)。

    Args:
        part_name: 内部部件名
        df: 该部件的数据
        file_path: 输入文件路径
        project_data: 项目配置
        output_dir: 输出目录
        part_target_mapping: 内部部件名 -> target部件名的映射
        part_source_mapping: 内部部件名 -> source部件名的映射（新增）
        part_row_selection: 行选择缓存
        timestamp_format: 时间戳格式
        overwrite: 是否覆盖
    """
    # Part 推测逻辑：优先使用显式映射，否则使用智能推测
    source_part = None
    target_part = None
    explicit_source_mapping = False
    explicit_target_mapping = False

    # 1. 检查是否有显式的 source 映射
    try:
        if isinstance(part_source_mapping, dict) and part_source_mapping.get(part_name):
            source_part = part_source_mapping.get(part_name)
            explicit_source_mapping = True
            logger.debug("使用显式 source 映射：'%s' → '%s'", part_name, source_part)
    except (TypeError, AttributeError):
        pass

    # 2. 检查是否有显式的 target 映射
    try:
        if isinstance(part_target_mapping, dict) and part_target_mapping.get(part_name):
            target_part = part_target_mapping.get(part_name)
            explicit_target_mapping = True
            logger.debug("使用显式 target 映射：'%s' → '%s'", part_name, target_part)
    except (TypeError, AttributeError):
        pass

    # 3. 如果没有显式映射，使用智能推测
    if not explicit_source_mapping or not explicit_target_mapping:
        if project_data is not None:
            source_result, target_result = infer_parts_for_file(
                part_name,
                project_data,
                file_path=file_path,
                strategy="fuzzy",
                allow_default=True,
            )

            # 使用推测的 source（如果没有显式映射）
            if not explicit_source_mapping:
                if source_result.is_successful():
                    source_part = source_result.part_name
                    logger.info(
                        "智能推测 source part：'%s' → '%s' (方法=%s, 置信度=%s)",
                        part_name,
                        source_part,
                        source_result.method,
                        source_result.confidence,
                    )
                else:
                    # 若项目中没有任何 source parts，则视为 source 缺失
                    if not getattr(project_data, "source_parts", None):
                        error_msg = "配置中无可用的 source part"
                        logger.error(error_msg)
                        return None, {
                            "part": part_name,
                            "source_part": None,
                            "target_part": target_part,
                            "status": "skipped",
                            "reason": "source_missing",
                            "message": error_msg,
                        }
                    error_msg = format_inference_error(
                        part_name, source_result, "source", "--source-part"
                    )
                    logger.error(error_msg)
                    return None, {
                        "part": part_name,
                        "source_part": None,
                        "target_part": target_part,
                        "status": "failed",
                        "reason": "source_inference_failed",
                        "message": error_msg,
                        "candidates": source_result.candidates,
                    }

            # 使用推测的 target（如果没有显式映射）
            if not explicit_target_mapping:
                if target_result.is_successful():
                    target_part = target_result.part_name
                    logger.info(
                        "智能推测 target part：'%s' → '%s' (方法=%s, 置信度=%s)",
                        part_name,
                        target_part,
                        target_result.method,
                        target_result.confidence,
                    )
                else:
                    # 若项目中没有任何 target parts，视为未映射（可跳过）
                    if not getattr(project_data, "target_parts", None):
                        error_msg = "配置中无可用的 target part"
                        logger.error(error_msg)
                        return None, {
                            "part": part_name,
                            "source_part": source_part,
                            "target_part": None,
                            "status": "skipped",
                            "reason": "target_not_mapped",
                            "message": error_msg,
                        }
                    error_msg = format_inference_error(
                        part_name, target_result, "target", "--target-part"
                    )
                    logger.error(error_msg)
                    return None, {
                        "part": part_name,
                        "source_part": source_part,
                        "target_part": None,
                        "status": "failed",
                        "reason": "target_inference_failed",
                        "message": error_msg,
                        "candidates": target_result.candidates,
                    }

    # 行过滤逻辑（保持不变）
    try:
        selected = None
        if isinstance(part_row_selection, dict):
            selected = part_row_selection.get(part_name)
        if selected is not None:
            selected_idx = sorted({int(x) for x in selected})
            df = df.iloc[selected_idx]
    except (TypeError, ValueError, KeyError) as exc:
        logger.debug(
            "按行过滤失败，回退为全量处理 (part=%s): %s",
            part_name,
            exc,
            exc_info=True,
        )

    if df is None or len(df) == 0:
        msg = f"part '{part_name}' 未选择任何数据行，已跳过"
        logger.warning(msg)
        return None, {
            "part": part_name,
            "source_part": source_part,
            "target_part": target_part,
            "status": "skipped",
            "reason": "no_rows_selected",
            "message": msg,
        }

    # 移除旧的 target_part 推测逻辑（已被上面的智能推测替代）
    # 智能推测已经确保 source_part 和 target_part 都存在于配置中

    required_cols = ["Cx", "Cy", "Cz/FN", "CMx", "CMy", "CMz"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        msg = f"part '{part_name}' 缺少必需列 {missing}，已跳过"
        logger.warning(msg)
        return None, {
            "part": part_name,
            "status": "skipped",
            "reason": "missing_columns",
            "message": msg,
            "missing": missing,
        }

    try:
        cx = pd.to_numeric(df["Cx"], errors="coerce")
        cy = pd.to_numeric(df["Cy"], errors="coerce")
        cz = pd.to_numeric(df["Cz/FN"], errors="coerce")
        cmx = pd.to_numeric(df["CMx"], errors="coerce")
        cmy = pd.to_numeric(df["CMy"], errors="coerce")
        cmz = pd.to_numeric(df["CMz"], errors="coerce")
    except (KeyError, TypeError, ValueError) as e:
        msg = f"part '{part_name}' 数值转换失败: {e}"
        logger.warning(msg)
        return None, {
            "part": part_name,
            "status": "failed",
            "reason": "numeric_conversion_failed",
            "message": msg,
            "error": str(e),
        }

    forces = pd.concat([cx, cy, cz], axis=1).to_numpy()
    moments = pd.concat([cmx, cmy, cmz], axis=1).to_numpy()

    try:
        if project_data is None:
            msg = f"缺少 ProjectData，无法为 part '{part_name}' 构建 AeroCalculator，已跳过"
            logger.warning(msg)
            return None, {
                "part": part_name,
                "status": "skipped",
                "reason": "no_project_data",
                "message": msg,
            }
        # 构建 AeroCalculator 可能在 project_data 中找不到 target 时抛出 KeyError
        try:
            calc = AeroCalculator(
                project_data, source_part=source_part, target_part=target_part
            )
        except KeyError as e:
            msg = f"part '{part_name}' 的 target 部件不存在: {e}，已跳过"
            logger.warning(msg)
            return None, {
                "part": part_name,
                "source_part": source_part,
                "target_part": target_part,
                "status": "skipped",
                "reason": "target_missing",
                "message": msg,
            }

        results = calc.process_batch(forces, moments)
    except (ValueError, RuntimeError, TypeError) as e:
        msg = f"part '{part_name}' 处理失败: {e}"
        logger.warning(msg, exc_info=True)
        return None, {
            "part": part_name,
            "source_part": source_part,
            "target_part": target_part,
            "status": "failed",
            "reason": "processing_failed",
            "message": msg,
            "error": str(e),
        }

    out_df = df.copy()
    out_df["Fx_new"] = results["force_transformed"][:, 0]
    out_df["Fy_new"] = results["force_transformed"][:, 1]
    out_df["Fz_new"] = results["force_transformed"][:, 2]
    out_df["Mx_new"] = results["moment_transformed"][:, 0]
    out_df["My_new"] = results["moment_transformed"][:, 1]
    out_df["Mz_new"] = results["moment_transformed"][:, 2]
    out_df["Cx_new"] = results["coeff_force"][:, 0]
    out_df["Cy_new"] = results["coeff_force"][:, 1]
    out_df["Cz_new"] = results["coeff_force"][:, 2]
    out_df["Cl_new"] = results["coeff_moment"][:, 0]
    out_df["Cm_new"] = results["coeff_moment"][:, 1]
    out_df["Cn_new"] = results["coeff_moment"][:, 2]

    ts = datetime.now().strftime(timestamp_format)
    out_path = output_dir / f"{file_path.stem}_{part_name}_result_{ts}.csv"
    if out_path.exists() and not overwrite:
        suffix = 1
        while True:
            candidate = (
                output_dir / f"{file_path.stem}_{part_name}_result_{ts}_{suffix}.csv"
            )
            if not candidate.exists():
                out_path = candidate
                break
            suffix += 1

    out_df.to_csv(out_path, index=False)
    msg = f"part '{part_name}' 输出: {out_path.name}"
    logger.info(msg)
    return out_path, {
        "part": part_name,
        "source_part": source_part,
        "target_part": target_part,
        "status": "success",
        "message": msg,
        "out_path": str(out_path),
    }


def _make_handle_single_part(
    file_path: Path,
    project_data,
    output_dir: Path,
    *,
    part_target_mapping: dict = None,
    part_source_mapping: dict = None,
    part_row_selection: dict = None,
    timestamp_format: str = "%Y%m%d_%H%M%S",
    overwrite: bool = False,
):
    """返回一个可调用对象，用于按 (part_name, df) 处理单个 part。"""

    part_kwargs = _collect_part_kwargs(locals())

    def _handle(part_name: str, df):
        return _process_single_part(
            part_name,
            df,
            file_path=file_path,
            project_data=project_data,
            output_dir=output_dir,
            **part_kwargs,
        )

    return _handle


def _summarize_report(report: List[dict]):
    """汇总 report 列表，返回统计信息元组。"""
    total = len(report)
    success_count = sum(1 for r in report if r.get("status") == "success")
    skipped_count = sum(1 for r in report if r.get("status") == "skipped")
    failed_count = sum(1 for r in report if r.get("status") == "failed")
    return total, success_count, skipped_count, failed_count


def _process_parts(handle, data_dict: Dict[str, pd.DataFrame]):
    """处理多个 part，返回 (outputs, report)。"""
    outputs: List[Path] = []
    report: List[dict] = []
    for part_name, df in data_dict.items():
        out_path, entry = handle(part_name, df)
        if out_path:
            outputs.append(out_path)
        report.append(entry)
    return outputs, report


@dataclass
class ProcessOptions:
    """封装 process_special_format_file 的可选参数。"""

    part_target_mapping: Optional[dict] = None
    part_source_mapping: Optional[dict] = None
    part_row_selection: Optional[dict] = None
    timestamp_format: str = "%Y%m%d_%H%M%S"
    overwrite: bool = False


def _process_special_format_file_core(
    file_path: Path,
    project_data,
    output_dir: Path,
    options: ProcessOptions,
    parse_func: Callable[[Path], Dict[str, pd.DataFrame]],
    return_report: bool = False,
):
    """核心实现：接收打包好的 options，减少参数个数。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    handle = _make_handle_single_part(
        file_path,
        project_data,
        output_dir,
        **_collect_part_kwargs(vars(options)),
    )
    data_dict = parse_func(file_path)
    outputs, report = _process_parts(handle, data_dict)

    logger.info(
        "文件 %s 处理完成：%d 个 part（%d 成功，%d 跳过，%d 失败）",
        file_path.name,
        *_summarize_report(report),
    )

    if return_report:
        return outputs, report

    return outputs


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
    parse_func: Optional[Callable[[Path], Dict[str, pd.DataFrame]]] = None,
) -> List[Path]:
    """处理特殊格式文件并输出结果文件，供 CLI/GUI 复用。

    Args:
        file_path: 输入文件路径
        project_data: 项目配置
        output_dir: 输出目录
        part_target_mapping: 内部部件名 -> target部件名的映射
        part_source_mapping: 内部部件名 -> source部件名的映射（新增）
        part_row_selection: 行选择缓存
        timestamp_format: 时间戳格式
        overwrite: 是否覆盖已存在的输出文件
        return_report: 是否返回处理报告
        parse_func: 解析函数（需传入 src.special_format_parser.parse_special_format_file）
    """
    if parse_func is None:
        raise ValueError("parse_func 不能为空，请传入 parse_special_format_file")

    options = ProcessOptions(**_collect_part_kwargs(locals()))
    return _process_special_format_file_core(
        file_path,
        project_data,
        output_dir,
        options,
        parse_func,
        return_report=return_report,
    )


__all__ = [
    "process_special_format_file",
    "ProcessOptions",
    "_process_special_format_file_core",
]
