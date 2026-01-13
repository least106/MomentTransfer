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

# 放置在 sys.path 调整之后但在其它代码之前的顶级导入
from datetime import datetime  # noqa: E402
from typing import Dict, List, Optional  # noqa: E402
from dataclasses import dataclass

import pandas as pd  # noqa: E402

from src.physics import AeroCalculator  # noqa: E402

logger = logging.getLogger(__name__)
# 在调整 sys.path 后才导入本地模块，允许导入位置非顶层的检查

# 推荐扩展名：MomentTransfer 专用批处理格式
RECOMMENDED_EXT = ".mtfmt"
SUPPORTED_EXTS = {".mtfmt", ".mtdata", ".txt", ".dat"}


def is_metadata_line(line: str) -> bool:
    """判断是否为元数据行（非数据内容的描述行）"""
    line = line.strip()
    if not line:
        return True

    # 包含中文冒号或英文冒号的描述行（英文冒号即使没有空格也视为描述）
    if "：" in line or (":" in line and not line[0].isdigit()):
        return True

    # 包含中文字符且不是纯英文单词的行
    if re.search(r"[\u4e00-\u9fff]", line) and "：" not in line:
        # 对于短而简洁的中文单词（可能为 part 名），不要误判为元数据
        tokens = line.split()
        if len(tokens) == 1 and len(line) < 20:
            return False
        # 其他包含中文但无冒号的长文本视为元数据或描述
        return True

    return False


def looks_like_special_format(
    file_path: Path, *, max_probe_lines: int = 20
) -> bool:
    """快速判断文件是否符合特殊格式。

    规则：
    1) 扩展名在推荐/支持列表
    2) 前若干行包含典型表头关键词（Alpha/CL/CD/Cm/Cx/Cy/Cz）或 part 名后跟表头
    """
    p = Path(file_path)
    suffix = p.suffix.lower()
    # CSV/Excel 始终按常规表格处理，避免因表头关键字被误判为特殊格式
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
        # 同时检测到可能的 part 标记
        for ln in lines:
            ln = (ln or "").strip()
            if ln and not is_metadata_line(ln) and not is_data_line(ln):
                return True
    return False


def is_summary_line(line: str) -> bool:
    """判断是否为汇总行（CLa Cdmin CmCL Cm0 Kmax 等）"""
    line = line.strip()
    if not line:
        return False

    # 汇总行特征：首个token不是数字，且包含特定关键词
    tokens = line.split()
    if not tokens:
        return False

    first_token = tokens[0]
    # 如果第一个token不像数字（不是负号开头或纯数字）
    if (
        not first_token.replace("-", "")
        .replace(".", "")
        .replace("+", "")
        .isdigit()
    ):
        # 检查是否包含典型的汇总指标名
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
    # 数据行特征：第一个token是数字（可能带负号）
    try:
        float(first_token)
        return True
    except ValueError:
        return False


def is_part_name_line(line: str, next_line: Optional[str] = None) -> bool:
    """
    判断是否为 part 名称行
    特征：
    1. 单独一行，内容简短
    2. 可能是纯英文单词或中文
    3. 下一行很可能是表头（包含 Alpha, CL, CD 等）
    """
    line = line.strip()
    if not line:
        return False

    # 如果是数据行或汇总行，肯定不是 part 名
    if is_data_line(line) or is_summary_line(line):
        return False

    # part 名特征：简短的文本（通常少于20个字符）
    tokens = line.split()
    if len(tokens) == 1 and len(line) < 20:
        # 中文短文本优先视为 part 名（避免被误判为元数据）
        contains_non_ascii = any(ord(ch) > 127 for ch in line)
        if contains_non_ascii and re.search(r"[\u4e00-\u9fff]", line):
            if next_line:
                next_tokens = next_line.split()
                header_keywords = ["Alpha", "CL", "CD", "Cm", "Cx", "Cy", "Cz"]
                if any(kw in next_tokens for kw in header_keywords):
                    return True
            return True

        # 如果下一行是表头，更有可能是 part 名
        if next_line:
            next_tokens = next_line.split()
            header_keywords = ["Alpha", "CL", "CD", "Cm", "Cx", "Cy", "Cz"]
            if any(kw in next_tokens for kw in header_keywords):
                return True
        return True

    return False


def _read_text_file_lines(
    file_path: Path, *, max_lines: Optional[int] = None, encodings=None
) -> List[str]:
    """尝试以多种编码读取文本文件，返回行列表。

    - 默认先尝试 `utf-8`，若失败依次尝试 `gbk` 和 `latin-1`。
    - max_lines: 若指定则只返回前若干行（用于探测）。
    """
    if encodings is None:
        encodings = ["utf-8", "gbk", "latin-1"]

    last_exc = None
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc, errors="strict") as fh:
                if max_lines is None:
                    return fh.readlines()
                lines = [fh.readline() for _ in range(max_lines)]
                return lines
        except UnicodeDecodeError as e:
            last_exc = e
            logger.debug("尝试以编码 %s 读取文件失败，切换下一编码", enc)
            continue
    # 若所有编码均失败，尝试以 latin-1 宽松读取以避免完全失败
    try:
        with open(file_path, "r", encoding="latin-1", errors="replace") as fh:
            if max_lines is None:
                return fh.readlines()
            return [fh.readline() for _ in range(max_lines)]
    except Exception as e:  # pylint: disable=broad-except
        # 最后抛出最初的 Unicode 错误或一般 IO 错误，保留原始异常上下文
        if last_exc:
            raise last_exc from e
        raise


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


def _finalize_part(current_part, current_header, current_data, result: Dict[str, pd.DataFrame]):
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
            except Exception:  # pylint: disable=broad-except
                logger.debug(
                    "列 %s 转换为数值失败，保留原始值",
                    col,
                    exc_info=True,
                )
        result[current_part] = df
        logger.info("解析 part '%s': %d 行数据", current_part, len(df))
    except ValueError as e:
        logger.warning("创建 DataFrame 失败 (part=%s): %s", current_part, e)


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

    result = {}
    current_part = None
    current_header = None
    current_data = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 跳过空行
        if not line:
            i += 1
            continue

        # 跳过元数据行
        if is_metadata_line(line):
            i += 1
            continue

        # 检查是否为 part 名称
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else None
        if is_part_name_line(line, next_line):
            # 保存上一个 part 的数据
            _finalize_part(current_part, current_header, current_data, result)

            # 开始新的 part
            current_part = line
            current_header = None
            current_data = []
            i += 1
            continue

        # 检查是否为表头行（包含 Alpha, CL 等关键词）
        if current_part and not current_header:
            tokens = line.split()
            if _tokens_looks_like_header(tokens):
                current_header = tokens
                i += 1
                continue

        # 检查是否为数据行
        if current_part and current_header and is_data_line(line):
            tokens = line.split()
            # 列数不匹配时按原先策略直接舍弃该行（不输出 DEBUG 日志以避免污染处理日志）
            if len(tokens) == len(current_header):
                current_data.append(tokens)
            i += 1
            continue

        # 检查是否为汇总行（跳过）
        if is_summary_line(line):
            i += 1
            continue

        # 其他情况：跳过
        i += 1

    # 保存最后一个 part 的数据
    _finalize_part(current_part, current_header, current_data, result)

    return result


# 复杂函数；允许过多参数/局部变量/语句，待后续重构
# 模块层面临时允许复杂度告警，后续应重构以移除这些忽略
# pylint: disable=R0913,R0914,R0915,R0912,R0911  # internal helper: 大型函数/实现，计划拆分以移除禁用
def _process_single_part(
    part_name,
    df,
    file_path,
    project_data,
    output_dir,
    part_target_mapping=None,
    part_row_selection=None,
    timestamp_format="%Y%m%d_%H%M%S",
    overwrite=False,
):
    """模块级：处理单个 part 的完整实现，返回 (out_path or None, report_entry dict)。

    该函数从原先内联实现提取，便于单元测试与重构。
    """
    source_part = part_name

    # 行选择：默认处理全部；若提供 selection，则仅处理选中的索引
    try:
        selected = None
        if isinstance(part_row_selection, dict):
            selected = part_row_selection.get(part_name)
        if selected is not None:
            selected_idx = sorted({int(x) for x in selected})
            df = df.iloc[selected_idx]
    except Exception:  # pylint: disable=broad-except
        # 容错：行选择的来源可能包含不可预期的值，回退到全量处理并记录异常上下文
        logger.debug(
            "按行过滤失败，回退为全量处理 (part=%s)",
            part_name,
            exc_info=True,
        )

    if df is None or len(df) == 0:
        msg = f"part '{part_name}' 未选择任何数据行，已跳过"
        logger.warning(msg)
        return None, {
            "part": part_name,
            "source_part": source_part,
            "target_part": (part_target_mapping or {}).get(part_name) or None,
            "status": "skipped",
            "reason": "no_rows_selected",
            "message": msg,
        }

    # Target part：优先映射；若未提供映射或未映射，则仅允许同名 Target part（由后续校验决定）
    target_part = None
    explicit_mapping_used = False
    try:
        if isinstance(part_target_mapping, dict) and part_target_mapping.get(part_name):
            target_part = part_target_mapping.get(part_name)
            explicit_mapping_used = True
        else:
            target_part = part_name
    except Exception:  # pylint: disable=broad-except
        # 容错：映射结构异常时回退为同名 target
        target_part = part_name

    # 校验 source/target part 是否存在
    if project_data is not None:
        if hasattr(project_data, "source_parts"):
            if source_part not in (getattr(project_data, "source_parts", {}) or {}):
                msg = f"来源配置中不存在 Source part '{source_part}'，已跳过该块"
                logger.warning(msg)
                return None, {
                    "part": part_name,
                    "source_part": source_part,
                    "target_part": target_part,
                    "status": "skipped",
                    "reason": "source_missing",
                    "message": msg,
                }

        if hasattr(project_data, "target_parts"):
            target_parts = getattr(project_data, "target_parts", {}) or {}
            if target_part not in target_parts:
                if explicit_mapping_used:
                    msg = f"目标配置中不存在 Target part '{target_part}'，已跳过该块"
                    reason = "target_missing"
                else:
                    msg = (
                        f"part '{part_name}' 未提供 Target 映射，且不存在同名 "
                        f"Target part '{target_part}'，已跳过该块"
                    )
                    reason = "target_not_mapped"
                logger.warning(msg)
                return None, {
                    "part": part_name,
                    "source_part": source_part,
                    "target_part": target_part,
                    "status": "skipped",
                    "reason": reason,
                    "message": msg,
                }

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
    except Exception as e:  # pylint: disable=broad-except
        # 容错：数值转换可能因列缺失或格式异常失败，记录并返回失败状态
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
        calc = AeroCalculator(project_data, source_part=source_part, target_part=target_part)
        results = calc.process_batch(forces, moments)
    except Exception as e:  # pylint: disable=broad-except
        # 容错：处理阶段捕获所有异常以避免批处理整体失败，记录详细上下文
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
            candidate = output_dir / f"{file_path.stem}_{part_name}_result_{ts}_{suffix}.csv"
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
    part_target_mapping: dict = None,
    part_row_selection: dict = None,
    timestamp_format: str = "%Y%m%d_%H%M%S",
    overwrite: bool = False,
):
    """返回一个可调用对象，用于按 (part_name, df) 处理单个 part。

    通过将上下文捕获到闭包中，避免在 `process_special_format_file` 中保留过多局部变量。
    """

    def _handle(part_name: str, df: pd.DataFrame):
        return _process_single_part(
            part_name,
            df,
            file_path,
            project_data,
            output_dir,
            part_target_mapping,
            part_row_selection,
            timestamp_format,
            overwrite,
        )

    return _handle


def _summarize_report(report: List[dict]):
    """汇总 report 列表，返回 (total, success_count, skipped_count, failed_count)。"""
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
    """封装 `process_special_format_file` 的可选参数以便内部传递。"""

    part_target_mapping: Optional[dict] = None
    part_row_selection: Optional[dict] = None
    timestamp_format: str = "%Y%m%d_%H%M%S"
    overwrite: bool = False


def _process_special_format_file_core(
    file_path: Path,
    project_data,
    output_dir: Path,
    options: ProcessOptions,
    return_report: bool = False,
):
    """核心实现：接收打包好的 `options`，减少参数个数以满足静态分析。

    该函数不改变对外行为，所有参数由外层包装器按原有签名传入并封装为 `options`。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 使用模块级工厂创建处理器，减少本函数的局部变量数量
    handle = _make_handle_single_part(
        file_path,
        project_data,
        output_dir,
        part_target_mapping=options.part_target_mapping,
        part_row_selection=options.part_row_selection,
        timestamp_format=options.timestamp_format,
        overwrite=options.overwrite,
    )

    data_dict = parse_special_format_file(file_path)
    outputs, report = _process_parts(handle, data_dict)

    # 汇总日志（直接在调用处展开，避免创建多个局部变量）
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
    part_row_selection: dict = None,
    timestamp_format: str = "%Y%m%d_%H%M%S",
    overwrite: bool = False,
    return_report: bool = False,
) -> List[
    Path
]:
    """直接处理特殊格式文件并输出结果文件，供 CLI/GUI 复用。

    约定：
    - part 名视为 Source part 名。
    - Target part 通过 `part_target_mapping` 选择；若未提供映射，则仅支持“同名 Target part”。
    - 可选参数 `part_row_selection` 支持按 part 过滤行：仅处理被选择的行索引集合。
    - 当前假定列名包含 `Cx`, `Cy`, `Cz/FN`, `CMx`, `CMy`, `CMz`。
    """
    # 保持对外签名兼容：将可选参数封装为 `ProcessOptions` 并委托给核心实现
    options = ProcessOptions(
        part_target_mapping=part_target_mapping,
        part_row_selection=part_row_selection,
        timestamp_format=timestamp_format,
        overwrite=overwrite,
    )
    return _process_special_format_file_core(
        file_path, project_data, output_dir, options, return_report=return_report
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
            part_names.append(line)

        i += 1

    return part_names


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)

    test_file = Path("data/data_tmp")
    if test_file.exists():
        print(f"解析文件: {test_file}")

        # 获取 part 名称
        parts = get_part_names(test_file)
        print(f"\n找到 {len(parts)} 个 part:")
        for part_item in parts:
            print(f"  - {part_item}")

        # 解析完整数据
        demo_data_dict = parse_special_format_file(test_file)
        print("\n解析结果:")
        for demo_part_name, demo_df in demo_data_dict.items():
            print(f"\n{demo_part_name}:")
            print(demo_df.head())
            print(f"  形状: {demo_df.shape}")
