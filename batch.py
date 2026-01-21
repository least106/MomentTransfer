import fnmatch
import json
import logging
import os
import pickle
import sys
import tempfile
import time
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import click
import numpy as np
import pandas as pd

try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None
try:
    import portalocker
except ImportError:
    portalocker = None


from src.cli_helpers import (
    BatchConfig,
    configure_logging,
    load_project_calculator,
    resolve_file_format,
)
from src.physics import AeroCalculator
from src.special_format_detector import looks_like_special_format
from src.special_format_processor import process_special_format_file


def _error_exit_json(message: str, code: int = 2, hint: str = None):
    """模块级错误退出工具：向 stderr 输出 JSON 并退出（供 CLI 调用）。"""
    payload = {"error": True, "message": message, "code": code}
    if hint:
        payload["hint"] = hint
    try:
        sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        logger = logging.getLogger("batch")
        logger.error("无法写入错误到 stderr: %s", payload)
    sys.exit(code)


# 最大文件名冲突重试次数（避免魔法数字）
MAX_FILE_COLLISION_RETRIES = 1000

# 默认的最大冲突重试次数（用于输出名占位尝试，便于调整）
DEFAULT_MAX_COLLISION_TRIALS = 20

# 通用重试次数（用于写入和替换等操作）
SHARED_RETRY_ATTEMPTS = 3

# 写入失败时的退避秒数序列（按尝试次数选取）
WRITE_RETRY_BACKOFF_SECONDS = [0.1, 0.5, 1.0]

# os.replace 替换失败时的退避策略（目前与写入退避一致）
REPLACE_RETRY_BACKOFFS = WRITE_RETRY_BACKOFF_SECONDS

# 默认记录非数值示例的行数（CLI 帮助文字中的默认值）
DEFAULT_SAMPLE_ROWS = 5


def generate_output_path(
    file_path: Path,
    output_dir: Path,
    cfg: BatchConfig,
    create_placeholder: bool = True,
) -> Path:
    """根据模板与时间戳生成输出路径，处理冲突和可写性检查。

    如果 `create_placeholder` 为 False，此函数仅计算并返回一个可用的输出路径（不在磁盘上创建占位文件），
    这在 dry-run 或预览场景中很有用以避免产生空文件。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = file_path.stem
    timestamp = datetime.now().strftime(cfg.timestamp_format)
    name = cfg.name_template.format(stem=stem, timestamp=timestamp)
    out_path = output_dir / name
    logger = logging.getLogger("batch")

    base = out_path.stem
    suf = out_path.suffix

    # 优先尝试原始名字；若已存在且不覆盖则通过原子创建占位文件避免 check-then-create 的竞态
    max_trials = min(DEFAULT_MAX_COLLISION_TRIALS, MAX_FILE_COLLISION_RETRIES)
    candidate = out_path

    # 如果用户允许覆盖并且已存在目标文件，先处理覆盖语义（不在 dry-run 时删除）
    if cfg.overwrite and candidate.exists() and create_placeholder:
        try:
            candidate.unlink()
        except Exception as e:
            raise IOError(f"无法覆盖已存在的输出文件: {candidate} -> {e}") from e

    # 如果不需要在磁盘上创建占位文件（例如 dry-run），仅计算一个不会冲突的名称并返回
    if not create_placeholder:
        chosen = None
        for i in range(0, max_trials + 1):
            if i == 0:
                c = output_dir / name
            else:
                c = output_dir / f"{base}_{i}{suf}"
            if cfg.overwrite or not c.exists():
                chosen = c
                break
        if chosen is None:
            unique = uuid.uuid4().hex
            chosen = output_dir / f"{base}_{unique}{suf}"
        return chosen

    # 尝试以 O_EXCL 原子方式创建占位文件以预占名字，避免并发冲突（默认行为）
    created = False
    for i in range(0, max_trials + 1):
        if i == 0:
            candidate = output_dir / name
        else:
            candidate = output_dir / f"{base}_{i}{suf}"

        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            # 在 Windows 上，文本模式参数不适用；直接使用 os.open
            fd = os.open(str(candidate), flags, 0o666)
            os.close(fd)
            created = True
            if i > 0:
                logger.debug("为避免冲突，使用候选输出名: %s", candidate.name)
            break
        except FileExistsError:
            continue
        except PermissionError as pe:
            logger.warning(
                "无法在路径创建占位文件: %s（尝试 %d/%d）：%s",
                candidate,
                i + 1,
                max_trials + 1,
                pe,
                exc_info=True,
            )
            break
        except OSError as oe:
            logger.warning(
                "尝试创建占位文件 %s 时出错（尝试 %d/%d）：%s",
                candidate,
                i + 1,
                max_trials + 1,
                oe,
            )
            continue

    if not created:
        # 回退到 UUID 名称并尝试一次创建（若失败则抛出）
        unique = uuid.uuid4().hex
        candidate = output_dir / f"{base}_{unique}{suf}"
        try:
            fd = os.open(str(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
            os.close(fd)
            logger.debug("使用 UUID 回退输出名: %s", candidate.name)
        except Exception as e:
            # 最终尝试失败：不可写或权限不足
            raise IOError(f"无法在输出目录创建唯一输出文件: {candidate} -> {e}") from e

    # 确保路径可写性（占位创建已验证），返回已占位的路径
    return candidate


def process_df_chunk(
    chunk_df: pd.DataFrame,
    calculator: AeroCalculator,
    cfg: BatchConfig,
    out_path: Path,
    first_chunk: bool,
    logger,
) -> tuple:
    """处理数据块并写入 out_path，支持系数或有量纲输入表头。

    返回 (processed_rows, dropped_rows, non_numeric_count, first_chunk_flag)
    """
    # 统一列名（忽略大小写和前后空格）
    col_map = {str(c).strip().lower(): c for c in chunk_df.columns}

    has_dimensional = all(k in col_map for k in ["fx", "fy", "fz", "mx", "my", "mz"])
    coeff_normal_key = "cz" if "cz" in col_map else "fn" if "fn" in col_map else None
    has_coeff = coeff_normal_key is not None and all(
        k in col_map for k in ["cx", "cy", "cmx", "cmy", "cmz"]
    )

    if not has_dimensional and not has_coeff:
        raise ValueError(
            "输入表缺少必要列，至少需要 Fx/Fy/Fz/Mx/My/Mz 或 Cx/Cy/Cz(CM)/CMx/CMy/CMz"
        )

    alpha_col_name = col_map.get("alpha")

    # 统一转换为浮点并检测非数值
    if has_dimensional:
        cols = [
            col_map["fx"],
            col_map["fy"],
            col_map["fz"],
            col_map["mx"],
            col_map["my"],
            col_map["mz"],
        ]
        numeric_df = chunk_df[cols].apply(pd.to_numeric, errors="coerce")
        forces_df = numeric_df.iloc[:, :3]
        moments_df = numeric_df.iloc[:, 3:]
    else:
        cols = [
            col_map["cx"],
            col_map["cy"],
            col_map[coeff_normal_key],
            col_map["cmx"],
            col_map["cmy"],
            col_map["cmz"],
        ]
        numeric_df = chunk_df[cols].apply(pd.to_numeric, errors="coerce")
        coeff_force_df = numeric_df.iloc[:, :3]
        coeff_moment_df = numeric_df.iloc[:, 3:]

        try:
            q = calculator.target_frame.q
            s_ref = calculator.target_frame.s_ref
            c_ref = calculator.target_frame.c_ref
            b_ref = calculator.target_frame.b_ref
        except Exception as e:  # pragma: no cover - 防御性日志
            raise ValueError(f"无法从计算器获取参考值: {e}") from e

        forces_df = coeff_force_df * (q * s_ref)
        moments_df = pd.DataFrame(
            {
                "mx": coeff_moment_df.iloc[:, 0] * (q * s_ref * b_ref),
                "my": coeff_moment_df.iloc[:, 1] * (q * s_ref * c_ref),
                "mz": coeff_moment_df.iloc[:, 2] * (q * s_ref * b_ref),
            }
        )

    mask_non_numeric = forces_df.isna().any(axis=1) | moments_df.isna().any(axis=1)
    mask_array = mask_non_numeric.to_numpy()
    n_non = int(mask_non_numeric.sum())
    dropped = 0

    if n_non:
        # 记录示例行用于诊断
        sample_rows_val = (
            cfg.sample_rows if cfg.sample_rows is not None else DEFAULT_SAMPLE_ROWS
        )
        samp_n = min(int(sample_rows_val), n_non)
        if samp_n > 0:
            idxs = list(np.where(mask_array)[0][:samp_n])
            examples = [chunk_df.iloc[idx].to_dict() for idx in idxs]
            if n_non > samp_n:
                logger.warning(
                    "文件 %s: 共 %d 行非数值，仅记录前 %d 条示例: %s",
                    out_path.name,
                    n_non,
                    samp_n,
                    examples,
                )
            else:
                logger.warning(
                    "文件 %s: 共 %d 行非数值，示例: %s",
                    out_path.name,
                    n_non,
                    examples,
                )

    # 根据配置处理非数值行
    if cfg.treat_non_numeric == "drop":
        valid_idx = ~mask_non_numeric
        if valid_idx.sum() == 0:
            # 全部丢弃
            dropped = len(chunk_df)
            return 0, dropped, n_non, first_chunk
        forces = forces_df.loc[valid_idx].to_numpy(dtype=float)
        moments = moments_df.loc[valid_idx].to_numpy(dtype=float)
        data_df = chunk_df.loc[valid_idx].reset_index(drop=True)
    elif cfg.treat_non_numeric == "nan":
        # 保留 NaN，让后续计算和结果中体现为 NaN
        forces = forces_df.to_numpy(dtype=float)
        moments = moments_df.to_numpy(dtype=float)
        data_df = chunk_df.reset_index(drop=True)
    else:
        # 默认或 'zero' 策略：将非数值按 0 处理
        forces = forces_df.fillna(0.0).to_numpy(dtype=float)
        moments = moments_df.fillna(0.0).to_numpy(dtype=float)
        data_df = chunk_df.reset_index(drop=True)

    logger.info("  执行坐标变换... 行数=%d", len(forces))
    results = calculator.process_batch(forces, moments)

    # 使用向量化方式构建输出 DataFrame，避免逐列赋值
    # 创建字典：所有结果列直接从 numpy 数组列映射
    out_data = {
        "Fx_new": results["force_transformed"][:, 0],
        "Fy_new": results["force_transformed"][:, 1],
        "Fz_new": results["force_transformed"][:, 2],
        "Mx_new": results["moment_transformed"][:, 0],
        "My_new": results["moment_transformed"][:, 1],
        "Mz_new": results["moment_transformed"][:, 2],
        "Cx": results["coeff_force"][:, 0],
        "Cy": results["coeff_force"][:, 1],
        "Cz": results["coeff_force"][:, 2],
        "Cl": results["coeff_moment"][:, 0],
        "Cm": results["coeff_moment"][:, 1],
        "Cn": results["coeff_moment"][:, 2],
    }

    # 添加 alpha 列（如果存在 Alpha 表头）
    if alpha_col_name and alpha_col_name in chunk_df.columns:
        alpha_series = chunk_df[alpha_col_name].reset_index(drop=True)
        if cfg.treat_non_numeric == "drop" and n_non:
            alpha_series = alpha_series.loc[data_df.index].reset_index(drop=True)
        out_data["Alpha"] = alpha_series

    # 一次性从字典构建 DataFrame（远比逐列赋值高效）
    out_df = pd.DataFrame(out_data)

    # 对于 'nan' 策略，将原始存在缺失的行对应计算列置为 NaN（向量化）
    if cfg.treat_non_numeric == "nan" and n_non > 0:
        # 使用 NumPy 的高效布尔掩码而非逐行 loc
        comp_cols = [
            "Fx_new",
            "Fy_new",
            "Fz_new",
            "Mx_new",
            "My_new",
            "Mz_new",
            "Cx",
            "Cy",
            "Cz",
            "Cl",
            "Cm",
            "Cn",
        ]
        out_df.loc[mask_array, comp_cols] = np.nan

    mode = "w" if first_chunk else "a"
    header = first_chunk

    # 确保父目录存在
    out_path.parent.mkdir(parents=True, exist_ok=True)

    open_mode = "w" if mode == "w" else "a"

    # 写入重试参数（使用模块级常量）
    last_exc = None

    # 对于 append 模式，直接在目标文件上以二进制追加写入（减少替换竞争）
    if mode == "a":
        csv_bytes = out_df.to_csv(index=False, header=header, encoding="utf-8").encode(
            "utf-8"
        )
        for attempt in range(1, SHARED_RETRY_ATTEMPTS + 1):
            try:
                # 以二进制追加打开并尝试加锁写入（首选 portalocker；若不可用，回退到 lockfile 方案）
                if portalocker:
                    with open(out_path, "ab") as f:
                        try:
                            try:
                                portalocker.lock(f, portalocker.LOCK_EX)
                            except Exception as le:
                                logger.debug(
                                    "portalocker.lock 失败，继续以无锁追加写入：%s",
                                    le,
                                )
                        except Exception:
                            logger.exception("尝试加锁时发生意外异常（忽略并继续写入）")

                        try:
                            f.write(csv_bytes)
                            f.flush()
                            try:
                                os.fsync(f.fileno())
                            except Exception:
                                pass
                        finally:
                            try:
                                portalocker.unlock(f)
                            except Exception:
                                logger.debug("portalocker.unlock 失败（忽略）")
                else:
                    # 回退：使用一个简单的 lockfile 来序列化对目标文件的 append 操作
                    lock_path = out_path.with_suffix(out_path.suffix + ".lock")
                    lock_acquired = False
                    lock_fd = None
                    try:
                        # 尝试创建 lockfile（O_EXCL 确保原子性）
                        lock_fd = os.open(
                            str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR
                        )
                        lock_acquired = True
                    except FileExistsError:
                        # 竞争中无法立即获取锁，等待并重试
                        waited = 0.0
                        while waited < WRITE_RETRY_BACKOFF_SECONDS[-1]:
                            time.sleep(0.01)
                            waited += 0.01
                            try:
                                lock_fd = os.open(
                                    str(lock_path),
                                    os.O_CREAT | os.O_EXCL | os.O_RDWR,
                                )
                                lock_acquired = True
                                break
                            except FileExistsError:
                                continue

                    if not lock_acquired:
                        # 最后一搏：在无锁的情况下直接追加（best-effort）
                        with open(out_path, "ab") as f:
                            f.write(csv_bytes)
                            f.flush()
                            try:
                                os.fsync(f.fileno())
                            except Exception:
                                pass
                    else:
                        try:
                            with open(out_path, "ab") as f:
                                f.write(csv_bytes)
                                f.flush()
                                try:
                                    os.fsync(f.fileno())
                                except Exception:
                                    pass
                        finally:
                            try:
                                os.close(lock_fd)
                            except Exception:
                                pass
                            try:
                                if lock_path.exists():
                                    lock_path.unlink()
                            except Exception:
                                logger.debug("无法删除 lockfile：%s（忽略）", lock_path)
                # 成功写入
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                logger.warning(
                    "追加写入 %s 失败（尝试 %d/%d）：%s",
                    out_path.name,
                    attempt,
                    SHARED_RETRY_ATTEMPTS,
                    e,
                )
                if attempt < SHARED_RETRY_ATTEMPTS:
                    time.sleep(
                        WRITE_RETRY_BACKOFF_SECONDS[
                            min(
                                attempt - 1,
                                len(WRITE_RETRY_BACKOFF_SECONDS) - 1,
                            )
                        ]
                    )
                else:
                    logger.exception("追加写入失败，达到最大重试次数")

        if last_exc is not None:
            raise last_exc

    else:
        # 使用临时文件并替换以实现原子写入（用于首次写入或覆盖）
        for attempt in range(1, SHARED_RETRY_ATTEMPTS + 1):
            try:
                with open(out_path, open_mode, encoding="utf-8", newline="") as f:
                    try:
                        if portalocker:
                            try:
                                portalocker.lock(f, portalocker.LOCK_EX)
                            except Exception as le:
                                logger.debug(
                                    "portalocker.lock 失败，继续以无锁模式写入：%s",
                                    le,
                                )
                        else:
                            logger.debug(
                                "portalocker 不可用，跳过文件锁（best-effort 写入）: %s",
                                out_path,
                            )
                    except Exception:
                        logger.exception("尝试加锁时发生意外异常（忽略并继续写入）")

                    try:
                        out_df.to_csv(f, index=False, header=header, encoding="utf-8")
                        f.flush()
                        try:
                            os.fsync(f.fileno())
                        except Exception:
                            pass

                        last_exc = None
                        break
                    finally:
                        if portalocker:
                            try:
                                portalocker.unlock(f)
                            except Exception:
                                logger.debug("portalocker.unlock 失败（忽略）")

            except Exception as e:
                last_exc = e
                if isinstance(e, PermissionError):
                    logger.warning(
                        "写入临时文件 %s 遇到 PermissionError（尝试 %d/%d），将重试：%s",
                        out_path.name,
                        attempt,
                        SHARED_RETRY_ATTEMPTS,
                        e,
                        exc_info=True,
                    )
                else:
                    logger.error(
                        "写入临时文件 %s 失败（尝试 %d/%d）：%s",
                        out_path.name,
                        attempt,
                        SHARED_RETRY_ATTEMPTS,
                        e,
                    )

                if attempt < SHARED_RETRY_ATTEMPTS:
                    time.sleep(
                        WRITE_RETRY_BACKOFF_SECONDS[
                            min(
                                attempt - 1,
                                len(WRITE_RETRY_BACKOFF_SECONDS) - 1,
                            )
                        ]
                    )
                else:
                    logger.exception("写入失败，达到最大重试次数")

        if last_exc is not None:
            raise last_exc

    processed = len(out_df)
    first_chunk = False
    return processed, dropped, n_non, first_chunk


def find_matching_files(directory: str, pattern: str) -> list:
    """在目录中查找匹配模式的文件，支持分号分隔的多模式。"""
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"路径不是有效目录: {directory}")

    # 允许 pattern 形如 "*.csv;*.mtfmt;*.mtdata"
    patterns = [p.strip() for p in pattern.split(";") if p.strip()]
    if not patterns:
        patterns = [pattern]

    matched_files = []
    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue
        if any(fnmatch.fnmatch(file_path.name, pat) for pat in patterns):
            matched_files.append(file_path)

    return sorted(matched_files)


def read_data_with_config(file_path: Path, config: BatchConfig) -> pd.DataFrame:
    """根据 `config` 读取整个数据表（非流式模式）。

    返回 pandas DataFrame，读取首行为表头。
    """
    p = Path(file_path)
    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p, header=0, skiprows=config.skip_rows)
    elif ext in {".xls", ".xlsx", ".xlsm", ".xlsb", ".odf", ".ods", ".odt"}:
        return pd.read_excel(p, header=0, skiprows=config.skip_rows)
    else:
        raise ValueError(
            f"不支持的文件类型: '{file_path}'. 仅支持 CSV (.csv) 和 Excel "
            f"(.xls, .xlsx, .xlsm, .xlsb, .odf, .ods, .odt) 文件。"
        )


def process_single_file(
    file_path: Path,
    calculator: AeroCalculator,
    config: BatchConfig,
    output_dir: Path,
    project_data=None,
    source_part: str = None,
    target_part: str = None,
    selected_rows: set = None,
) -> bool:
    """处理单个文件（支持 chunked CSV）。

    实现要点：
    - 使用临时文件写入，完成后原子替换到目标文件；
    - 在写入开始写入 `.partial`，成功时写入 `.complete`；
    - 在异常时清理临时并在 partial 中记录错误信息。
    - 支持每文件指定 source/target part 和行过滤

    参数：
    - source_part: 该文件使用的 source part（若提供则覆盖全局设置）
    - target_part: 该文件使用的 target part（若提供则覆盖全局设置）
    - selected_rows: 要处理的行索引集合，若为 None 则处理全部
    """
    logger = logging.getLogger("batch")

    # 若提供了 project_data 和文件级的 source/target，创建独立的计算器
    calculator_to_use = calculator
    if project_data is not None and (
        source_part is not None or target_part is not None
    ):
        try:
            # 如果未指定则使用唯一的 part（若存在）或抛出错误
            source_names = list(
                (getattr(project_data, "source_parts", {}) or {}).keys()
            )
            target_names = list(
                (getattr(project_data, "target_parts", {}) or {}).keys()
            )

            actual_source = source_part
            actual_target = target_part

            # 允许唯一 part 自动推断
            if not actual_source and len(source_names) == 1:
                actual_source = str(source_names[0])
            if not actual_target and len(target_names) == 1:
                actual_target = str(target_names[0])

            if not actual_source or not actual_target:
                raise ValueError(
                    f"文件 {file_path.name} 未指定 source/target part，且无法唯一推断"
                )

            # 为此文件创建独立的计算器
            calculator_to_use = AeroCalculator(
                project_data,
                source_part=actual_source,
                target_part=actual_target,
            )
            logger.debug(
                f"为文件 {file_path.name} 创建独立计算器: source={actual_source}, target={actual_target}"
            )
        except Exception as e:
            logger.error("为文件 %s 创建计算器失败: %s", file_path.name, e)
            raise

    # 特殊格式路径：直接用专用解析器处理并按 part 输出
    if project_data is not None and looks_like_special_format(file_path):
        try:
            outputs = process_special_format_file(
                file_path,
                project_data,
                output_dir,
                timestamp_format=config.timestamp_format,
                overwrite=config.overwrite,
            )
            if not outputs:
                logger.warning(
                    "特殊格式文件 %s 未产生输出，可能因缺少匹配的 Target part 或列缺失",
                    file_path.name,
                )
                return False
            logger.info(
                "特殊格式文件 %s 已处理，生成 %d 个 part 输出",
                file_path.name,
                len(outputs),
            )
            return True
        except Exception as exc:
            logger.error(
                "处理特殊格式文件 %s 失败: %s",
                file_path.name,
                exc,
                exc_info=True,
            )
            return False

    # 非流式：读取整表并可选行选择
    df = read_data_with_config(file_path, config)

    # 若提供了行选择，则应用过滤
    if selected_rows is not None and len(selected_rows) > 0:
        selected_rows_sorted = sorted(int(x) for x in set(selected_rows))
        df = df.iloc[selected_rows_sorted].reset_index(drop=True)
        logger.debug("按行选择过滤: %d 行", len(selected_rows_sorted))

    out_path = generate_output_path(file_path, output_dir, config)
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=out_path.name + ".", dir=str(out_path.parent), text=True
    )
    os.close(temp_fd)
    temp_out_path = Path(temp_name)

    partial_flag = out_path.with_name(out_path.name + ".partial")
    complete_flag = out_path.with_name(out_path.name + ".complete")
    try:
        partial_flag.write_text(datetime.now().isoformat())
    except Exception:
        pass

    first_chunk = True
    total_processed = 0
    total_dropped = 0
    total_non_numeric = 0

    try:
        proc, dropped, non_num, first_chunk = process_df_chunk(
            df,
            calculator_to_use,
            config,
            temp_out_path,
            first_chunk,
            logger,
        )
        total_processed += proc
        total_dropped += dropped
        total_non_numeric += non_num

        # 完成后使用 os.replace 做原子替换（跨平台），并提供重试/退避策略以应对并发场景
        replace_attempts = SHARED_RETRY_ATTEMPTS
        replace_backoffs = REPLACE_RETRY_BACKOFFS
        replaced = False
        replace_err = None
        for ri in range(1, replace_attempts + 1):
            try:
                os.replace(str(temp_out_path), str(out_path))
                replaced = True
                break
            except Exception as e:
                replace_err = e
                if isinstance(e, PermissionError):
                    logger.warning(
                        "os.replace 被拒绝（PermissionError）: %s -> %s（%d/%d），将重试：%s",
                        temp_out_path.name,
                        out_path.name,
                        ri,
                        replace_attempts,
                        e,
                        exc_info=True,
                    )
                else:
                    logger.warning(
                        "尝试用 os.replace 替换 %s -> %s 失败（%d/%d）：%s",
                        temp_out_path.name,
                        out_path.name,
                        ri,
                        replace_attempts,
                        e,
                    )
                if ri < replace_attempts:
                    time.sleep(replace_backoffs[min(ri - 1, len(replace_backoffs) - 1)])
        if not replaced:
            # 若替换失败，抛出并由外层 except 捕获以进行清理和记录
            if replace_err is None:
                raise RuntimeError(
                    f"os.replace 替换失败: {temp_out_path} -> {out_path}（无异常信息）"
                )
            raise replace_err

        try:
            if partial_flag.exists():
                partial_flag.unlink()
        except Exception:
            pass
        try:
            complete_flag.write_text(datetime.now().isoformat())
        except Exception:
            pass

        logger.info(
            f"处理完成: 已输出 {total_processed} 行；非数值总计 {total_non_numeric} 行；丢弃 {total_dropped} 行"
        )
        logger.info("结果文件: %s", out_path)
        return True

    except Exception as e:
        try:
            if temp_out_path.exists():
                temp_out_path.unlink()
        except Exception:
            pass
        try:
            partial_flag.write_text(f"error: {str(e)}\n{traceback.format_exc()}")
        except Exception:
            pass
        logger.error("  ✗ 处理失败: %s", str(e), exc_info=True)
        return False


def _worker_process(args):
    """在子进程中运行单个文件的处理（用于并行）。

    args_tuple: (file_path_str, config_dict, config_path, output_dir_str)
    - config_dict: dict representation of BatchConfig (keys: skip_rows, name_template, timestamp_format, overwrite)
    - config_path: path to JSON config for AeroCalculator (project geometry)
    """
    try:
        # 期望 args 为 dict，包含明确字段，减少位置参数易碎性
        if not isinstance(args, dict):
            raise ValueError(
                "子进程参数必须为 dict，推荐键: file_path, config_dict, project_config_path, output_dir, registry_db, strict"
            )

        file_path_str = args.get("file_path", "<unknown>")
        config_dict = args.get("config_dict")
        project_config_path = args.get("project_config_path")
        output_dir_str = args.get("output_dir")
        registry_db = args.get("registry_db", None)
        strict = bool(args.get("strict", False))

        if not all(
            [
                file_path_str,
                config_dict is not None,
                project_config_path,
                output_dir_str is not None,
            ]
        ):
            raise ValueError(
                "子进程参数不完整，至少需要 file_path, config_dict, project_config_path, output_dir"
            )

        file_path = Path(file_path_str)
        output_dir = Path(output_dir_str)

        # 进程内缓存：避免对大量小文件重复加载配置带来的开销
        # 若调用方传入序列化的计算器（calculator_pickle），优先使用并缓存
        # 否则：若当前进程已缓存相同 project_config_path 的计算器，则重用
        # 否则按需加载一次并缓存
        global _WORKER_CALCULATOR, _WORKER_PROJECT_PATH, _WORKER_PROJECT_DATA
        try:
            _WORKER_CALCULATOR
        except NameError:
            _WORKER_CALCULATOR = None
            _WORKER_PROJECT_PATH = None
            _WORKER_PROJECT_DATA = None

        project_data = None
        calculator = None

        # 支持传入序列化对象（caller 可通过 pickle.dumps((project_data, calculator)) 传入 bytes）
        calc_pickle = args.get("calculator_pickle")
        if calc_pickle:
            try:
                project_data, calculator = pickle.loads(calc_pickle)
                _WORKER_CALCULATOR = calculator
                _WORKER_PROJECT_PATH = project_config_path
                _WORKER_PROJECT_DATA = project_data
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning(
                    "反序列化传入的 calculator 失败，回退到按路径加载: %s", e
                )

        if calculator is None:
            if (
                _WORKER_CALCULATOR is not None
                and project_config_path == _WORKER_PROJECT_PATH
            ):
                # 重用已缓存的计算器
                calculator = _WORKER_CALCULATOR
                project_data = _WORKER_PROJECT_DATA
            else:
                # 仅在必要时加载一次并缓存到进程全局变量
                project_data, calculator = load_project_calculator(project_config_path)
                _WORKER_CALCULATOR = calculator
                _WORKER_PROJECT_PATH = project_config_path
                _WORKER_PROJECT_DATA = project_data

        # 构造 BatchConfig
        cfg = BatchConfig()
        cfg.skip_rows = int(config_dict.get("skip_rows", 0))
        cfg.name_template = config_dict.get("name_template", cfg.name_template)
        cfg.timestamp_format = config_dict.get("timestamp_format", cfg.timestamp_format)
        cfg.overwrite = bool(config_dict.get("overwrite", cfg.overwrite))
        cfg.treat_non_numeric = config_dict.get(
            "treat_non_numeric", cfg.treat_non_numeric
        )
        cfg.sample_rows = config_dict.get("sample_rows", cfg.sample_rows)

        # 使用全局配置处理每个文件（不再支持 per-file 覆盖）
        try:
            from src.cli_helpers import resolve_file_format

            cfg = resolve_file_format(str(file_path), cfg)
        except Exception as e:
            logger = logging.getLogger(__name__)
            if strict:
                # 严格模式下：解析失败视为致命错误，交由上层统一处理
                logger.warning(
                    '处理文件"%s"时配置解析失败，错误：%s',
                    str(file_path),
                    e,
                )
                raise
            else:
                # 非严格模式：记录警告并回退到全局配置
                logger.warning(
                    "处理文件 '%s' 时配置解析失败，使用全局配置：%s",
                    str(file_path),
                    e,
                )

        success = process_single_file(
            file_path, calculator, cfg, output_dir, project_data
        )
        return (str(file_path), success, None)
    except Exception:
        # 捕获子进程中任何异常，返回失败信息以便主进程记录
        tb = traceback.format_exc()
        return (file_path_str, False, tb)


def run_batch_processing(
    config_path: str,
    input_path: str,
    data_config: BatchConfig = None,
    strict: bool = False,
    dry_run: bool = False,
    show_progress: bool = False,
    output_json: str = None,
    summary: bool = False,
    target_part: str = None,
    target_variant: int = 0,
    file_source_target_map: dict = None,
    file_row_selection: dict = None,
):
    """批处理主函数"""
    logger = logging.getLogger("batch")

    logger.info("%s", "=" * 70)
    logger.info("MomentTransfer Batch Processing")
    logger.info("%s", "=" * 70)
    logger.info("[1/5] 加载几何配置: %s", config_path)
    try:
        project_data, calculator = load_project_calculator(
            config_path, target_part=target_part, target_variant=target_variant
        )
        # 显示实际使用的 Target part 名称
        used_target = getattr(calculator, "target_frame", None)
        used_target_name = (
            getattr(used_target, "part_name", None) if used_target is not None else None
        )
        logger.info("  ✓ 配置加载成功: %s", used_target_name)
    except Exception as e:
        logger.error("  ✗ 配置加载失败: %s", e)
        logger.error(
            "  提示: 请检查 JSON 是否包含 Target 的 CoordSystem/MomentCenter/Q/S 或使用 GUI/creator.py 生成兼容的配置。"
        )
        return

    # 2. 构造数据格式配置（固定表头语义）
    logger.info("[2/5] 配置数据格式")
    if data_config is None:
        data_config = BatchConfig()

    # 3. 确定输入文件列表
    logger.info("[3/5] 扫描输入文件")
    input_path = Path(input_path)
    files_to_process = []

    # 若提供了 data_config 且同时提供了 registry_db，则视为非交互自动模式，避免使用 input() 阶段

    if input_path.is_file():
        logger.info("  模式: 单文件处理")
        files_to_process = [input_path]
        output_dir = input_path.parent
    elif input_path.is_dir():
        logger.info("  模式: 目录批处理")
        # 使用默认模式匹配所有常见数据文件
        pattern = "*.csv;*.xlsx;*.xls;*.mtfmt;*.mtdata;*.txt;*.dat"
        files = find_matching_files(str(input_path), pattern)
        logger.info("  找到 %d 个匹配文件", len(files))
        files_to_process = files
        output_dir = input_path
    else:
        logger.error("  [错误] 无效的输入路径: %s", input_path)

    # 4. 验证
    logger.info("[4/5] 准备处理 %d 个文件", len(files_to_process))
    logger.info("  输出目录: %s", output_dir)

    # 5. 批量处理
    logger.info("[5/5] 开始批量处理...")
    success_count = 0

    # Dry-run: 仅打印将处理的文件、解析的格式与目标输出路径，然后返回
    if dry_run:
        logger.info("Dry-run 模式：不写入文件，仅显示解析结果。")
        for fp in files_to_process:
            cfg_local = resolve_file_format(str(fp), data_config)
            out_path = generate_output_path(
                fp, output_dir, cfg_local, create_placeholder=False
            )
            logger.info(
                "将处理: %s -> %s",
                fp,
                out_path,
            )
        return

    # 若在外部通过 CLI 提供了并行参数，会由外层主函数处理；这里保持串行以便直接调用
    # 记录开始时间以便估算 ETA
    start_time = datetime.now()
    # 确保收集结果的容器始终存在，避免在空文件列表下引用未定义变量
    results = []
    for i, file_path in enumerate(files_to_process, 1):
        logger.info("进度: [%d/%d] %s", i, len(files_to_process), file_path.name)
        # 使用全局配置处理每个文件
        cfg_local = resolve_file_format(str(file_path), data_config)

        # 获取该文件的 source/target part 映射（若提供）
        file_source = None
        file_target = None
        if file_source_target_map and str(file_path) in file_source_target_map:
            mapping = file_source_target_map[str(file_path)]
            file_source = mapping.get("source")
            file_target = mapping.get("target")

        # 获取该文件的行选择（若提供）
        selected_rows = None
        if file_row_selection and str(file_path) in file_row_selection:
            selected_rows = file_row_selection[str(file_path)]

        t0 = datetime.now()
        ok = process_single_file(
            file_path,
            calculator,
            cfg_local,
            output_dir,
            project_data,
            source_part=file_source,
            target_part=file_target,
            selected_rows=selected_rows,
        )
        elapsed = (datetime.now() - t0).total_seconds()
        if ok:
            success_count += 1

        # 收集结果以支持 --output-json/--summary
        results.append(
            {
                "file": str(file_path),
                "success": bool(ok),
                "elapsed_sec": round(elapsed, 3),
            }
        )

        # 总是记录每文件耗时，便于 log-file 中查看详情
        logger.info(
            "文件 %s 处理完成: 成功=%s, 耗时=%.2fs",
            file_path.name,
            ok,
            elapsed,
        )

        # 若开启进度显示，则打印稳定的 ETA 估算（基于平均每文件耗时）
        if show_progress:
            files_done = i
            files_left = len(files_to_process) - files_done
            avg_per_file = (datetime.now() - start_time).total_seconds() / files_done
            eta_seconds = int(avg_per_file * files_left)
            logger.info(
                "已完成 %d/%d，累计耗时 %.1fs，本文件耗时 %.2fs，平均 %.2fs/文件，预计剩余 %ds",
                files_done,
                len(files_to_process),
                (datetime.now() - start_time).total_seconds(),
                elapsed,
                avg_per_file,
                eta_seconds,
            )
            # 同步向 stdout 输出可机器解析的进度行（JSON），便于监控系统采集
            try:
                prog = {
                    "completed": files_done,
                    "total": len(files_to_process),
                    "file": str(file_path.name),
                    "success": bool(ok),
                    "elapsed_sec": round(elapsed or 0.0, 3),
                    "avg_sec": round(avg_per_file or 0.0, 3),
                    "eta_sec": eta_seconds,
                }
                # 进度 JSON 写入 stdout 以便外部监控程序解析
                print(json.dumps(prog, ensure_ascii=False))
                sys.stdout.flush()
            except Exception:
                try:
                    logger.info(
                        "[%d/%d] %s success=%s elapsed=%.2fs eta=%ds",
                        files_done,
                        len(files_to_process),
                        file_path.name,
                        ok,
                        elapsed,
                        eta_seconds,
                    )
                except Exception:
                    pass

    # 总结
    logger.info("%s", "\n" + "=" * 70)
    logger.info("批处理完成!")
    logger.info("  成功: %d/%d", success_count, len(files_to_process))
    logger.info(
        "  失败: %d/%d",
        len(files_to_process) - success_count,
        len(files_to_process),
    )
    logger.info("%s", "=" * 70)

    # 写出 JSON 汇总（若请求）
    if output_json:
        try:
            results  # 确保 results 已定义；若未定义则回退为空列表
        except NameError:
            results = []
        summary_payload = {
            "total": len(files_to_process),
            "success": success_count,
            "fail": len(files_to_process) - success_count,
            "files": results,
        }
        try:
            with open(output_json, "w", encoding="utf-8") as fh:
                json.dump(summary_payload, fh, ensure_ascii=False, indent=2)
            logger.info("已将处理结果写入 %s", output_json)
        except Exception:
            logger.exception("写入 output_json 失败")

    if summary:
        try:
            print(
                json.dumps(
                    {
                        "total": len(files_to_process),
                        "success": success_count,
                        "fail": len(files_to_process) - success_count,
                    },
                    ensure_ascii=False,
                )
            )
        except Exception:
            logger.exception("打印 summary 失败")


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("-c", "--config", "config", required=True, help="配置文件路径 (JSON)")
@click.option("-i", "--input", "input_path", required=True, help="输入文件或目录路径")
@click.option(
    "-p",
    "--pattern",
    default=None,
    help='文件匹配模式（目录模式下），支持分号分隔多模式，如 "*.csv;*.mtfmt"',
)
@click.option("--log-file", "log_file", default=None, help="将日志写入指定文件")
@click.option("--verbose", "verbose", is_flag=True, help="增加日志详细程度")
@click.option(
    "--workers",
    "workers",
    type=int,
    default=1,
    help="并行工作进程数（默认为1，表示串行）",
)
@click.option(
    "--overwrite",
    "overwrite",
    is_flag=True,
    help="若输出文件存在则覆盖（默认会自动改名避免冲突）",
)
@click.option(
    "--name-template",
    "name_template",
    default=None,
    help="输出文件名模板，支持 {stem} 和 {timestamp} 占位符",
)
@click.option(
    "--timestamp-format",
    "timestamp_format",
    default=None,
    help="时间戳格式，用于 {timestamp} 占位符，默认 %%Y%%m%%d_%%H%%M%%S",
)
@click.option(
    "--treat-non-numeric",
    "treat_non_numeric",
    type=click.Choice(["zero", "nan", "drop"]),
    default=None,
    help="如何处理非数值输入: zero|nan|drop",
)
@click.option(
    "--sample-rows",
    "sample_rows",
    type=int,
    default=None,
    help="记录非数值示例的行数上限 (默认5)",
)
@click.option(
    "--target-part",
    "target_part",
    default=None,
    help="目标 part 名称（必须指定或通过参数提供）",
)
@click.option(
    "--target-variant",
    "target_variant",
    type=int,
    default=0,
    help="目标 variant 索引（从0开始，默认0）",
)
@click.option(
    "--strict",
    "strict",
    is_flag=True,
    help="格式解析失败时终止（默认回退到全局配置）",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="仅解析并显示将处理的文件与输出路径，但不实际写入",
)
@click.option(
    "--progress",
    "show_progress",
    is_flag=True,
    help="显示处理进度与 ETA（串行/并行均支持）",
)
@click.option(
    "--output-json",
    "output_json",
    default=None,
    help="将处理结果以 JSON 写入指定文件",
)
@click.option(
    "--summary",
    "summary",
    is_flag=True,
    help="在结束时打印简要的 JSON 汇总（机器可读）",
)
def main(**cli_options):
    """批处理入口（click 版）"""
    # 将 CLI 选项解包为原来的局部变量，保持后续逻辑不变
    config = cli_options.get("config")
    input_path = cli_options.get("input_path")
    pattern = cli_options.get("pattern")
    log_file = cli_options.get("log_file")
    verbose = cli_options.get("verbose")
    workers = cli_options.get("workers")
    overwrite = cli_options.get("overwrite")
    name_template = cli_options.get("name_template")
    timestamp_format = cli_options.get("timestamp_format")
    treat_non_numeric = cli_options.get("treat_non_numeric")
    sample_rows = cli_options.get("sample_rows")
    target_part = cli_options.get("target_part")
    target_variant = cli_options.get("target_variant")
    strict = cli_options.get("strict")
    dry_run = cli_options.get("dry_run")
    show_progress = cli_options.get("show_progress")
    output_json = cli_options.get("output_json")
    summary = cli_options.get("summary")
    # 配置 logging（通过共享 helper）
    logger = configure_logging(log_file, verbose)
    # 读取数据格式配置
    data_config = BatchConfig()

    # 命令行参数覆盖默认设置
    if overwrite:
        data_config.overwrite = True
    if name_template:
        data_config.name_template = name_template
    if timestamp_format:
        data_config.timestamp_format = timestamp_format
    if treat_non_numeric:
        data_config.treat_non_numeric = treat_non_numeric
    if sample_rows is not None:
        data_config.sample_rows = sample_rows

    # 根据 pattern 参数或交互获取 pattern
    pat = pattern or "*.csv;*.xlsx;*.xls;*.mtfmt;*.mtdata;*.txt;*.dat"

    # 并行处理支持：若 workers>1，则使用 ProcessPoolExecutor
    try:
        if workers > 1:
            logger.info("并行处理模式: workers=%d", workers)
            # 构造文件列表
            input_path_obj = Path(input_path)
            files_to_process = []
            output_dir = None
            if input_path_obj.is_file():
                files_to_process = [input_path_obj]
                output_dir = input_path_obj.parent
            elif input_path_obj.is_dir():
                pat_use = pat
                files = find_matching_files(str(input_path_obj), pat_use)
                # 并行模式下不提供交互选择：自动处理所有匹配到的文件
                # 选择 all
                chosen_idxs = list(range(len(files)))
                files_to_process = [files[i] for i in chosen_idxs]
                output_dir = input_path_obj
            else:
                _error_exit_json(f"无效的输入路径: {input_path}", code=4)

            # 准备并行任务参数（将 data_config 序列化为 dict）
            config_dict = {
                "skip_rows": data_config.skip_rows,
                "name_template": data_config.name_template,
                "timestamp_format": data_config.timestamp_format,
                "overwrite": data_config.overwrite,
                "treat_non_numeric": data_config.treat_non_numeric,
                "sample_rows": data_config.sample_rows,
            }

            with ProcessPoolExecutor(max_workers=workers) as exe:
                futures = {}
                start_times = {}
                results = []
                for fp in files_to_process:
                    worker_args = {
                        "file_path": str(fp),
                        "config_dict": config_dict,
                        "project_config_path": config,
                        "output_dir": str(output_dir),
                        "strict": strict,
                    }
                    fut = exe.submit(_worker_process, worker_args)
                    futures[fut] = fp
                    start_times[fut] = datetime.now()

                success_count = 0
                # 统计完成的任务以计算平均耗时并估算 ETA
                completed = 0
                total = len(futures)
                elapsed_sum = 0.0
                for fut in as_completed(futures):
                    fp = futures[fut]
                    st = start_times.get(fut, None)
                    try:
                        file_str, ok, err = fut.result()
                        endt = datetime.now()
                        elapsed = (endt - st).total_seconds() if st else None
                        if elapsed is not None:
                            elapsed_sum += elapsed
                            completed += 1
                        avg = (elapsed_sum / completed) if completed else None
                        remaining = total - completed
                        eta = int(avg * remaining) if avg is not None else None

                        # 收集并记录
                        results.append(
                            {
                                "file": file_str,
                                "success": bool(ok),
                                "error": err,
                                "elapsed_sec": round(elapsed or 0.0, 3),
                            }
                        )

                        if ok:
                            logger.info(
                                "处理成功: %s (耗时: %.2fs)",
                                file_str,
                                elapsed if elapsed else 0.0,
                            )
                            success_count += 1
                        else:
                            logger.error(
                                "处理失败: %s 错误: %s (耗时: %.2fs)",
                                file_str,
                                err,
                                elapsed if elapsed else 0.0,
                            )

                        # 当请求进度显示时，记录 ETA 与平均每文件耗时
                        if show_progress and eta is not None:
                            logger.info(
                                "已完成 %d/%d，平均每文件耗时 %.2fs，预计剩余 %ds",
                                completed,
                                total,
                                avg,
                                eta,
                            )
                            # 同步向 stdout 输出可机器解析的进度行（JSON），便于监控系统采集
                            try:
                                prog = {
                                    "completed": completed,
                                    "total": total,
                                    "file": file_str,
                                    "success": bool(ok),
                                    "elapsed_sec": round(elapsed or 0.0, 3),
                                    "avg_sec": round(avg or 0.0, 3),
                                    "eta_sec": eta,
                                }
                                print(json.dumps(prog, ensure_ascii=False))
                                sys.stdout.flush()
                            except Exception:
                                # 回退到日志输出
                                try:
                                    logger.info(
                                        "[%d/%d] %s success=%s elapsed=%.2fs eta=%ds",
                                        completed,
                                        total,
                                        file_str,
                                        ok,
                                        elapsed,
                                        eta,
                                    )
                                except Exception:
                                    pass
                        else:
                            logger.info("已完成 %d/%d", completed, total)
                            if show_progress:
                                try:
                                    print(
                                        json.dumps(
                                            {
                                                "completed": completed,
                                                "total": total,
                                            },
                                            ensure_ascii=False,
                                        )
                                    )
                                    sys.stdout.flush()
                                except Exception:
                                    # 忽略无法写 stdout 的情况
                                    pass

                    except Exception:
                        logger.exception("任务异常: %s", fp)

            # 写出 JSON 汇总（若请求）
            if output_json:
                summary_payload = {
                    "total": len(files_to_process),
                    "success": success_count,
                    "fail": len(files_to_process) - success_count,
                    "files": results,
                }
                try:
                    with open(output_json, "w", encoding="utf-8") as fh:
                        json.dump(summary_payload, fh, ensure_ascii=False, indent=2)
                    logger.info("已将处理结果写入 %s", output_json)
                except Exception:
                    logger.exception("写入 output_json 失败")

            if summary:
                # summary 以 JSON 输出到 stdout 以便脚本化处理
                print(
                    json.dumps(
                        {
                            "total": len(files_to_process),
                            "success": success_count,
                            "fail": len(files_to_process) - success_count,
                        },
                        ensure_ascii=False,
                    )
                )

            logger.info(
                "并行处理完成: 成功 %d/%d", success_count, len(files_to_process)
            )
            sys.exit(0 if success_count == len(files_to_process) else 1)

        else:
            # 串行模式：调用批处理函数
            run_batch_processing(
                config,
                input_path,
                data_config,
                strict=strict,
                dry_run=dry_run,
                show_progress=show_progress,
                output_json=output_json,
                summary=summary,
                target_part=target_part,
                target_variant=target_variant,
                file_source_target_map=None,
                file_row_selection=None,
            )
            sys.exit(0)
    except Exception:
        logger.exception("批处理失败")
        sys.exit(5)


if __name__ == "__main__":
    main()
