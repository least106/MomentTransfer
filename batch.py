import click
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
import numpy as np

from datetime import datetime
from pathlib import Path
import fnmatch
import uuid
import traceback
import tempfile
import os
import shutil
import time
import json
import pickle
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


def _error_exit_json(message: str, code: int = 2, hint: str = None):
    """模块级错误退出工具：向 stderr 输出 JSON 并退出（供 CLI 调用）。"""
    payload = {"error": True, "message": message, "code": code}
    if hint:
        payload['hint'] = hint
    try:
        sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        logger = logging.getLogger('batch')
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

# 必需列键常量
REQUIRED_KEYS = ['fx', 'fy', 'fz', 'mx', 'my', 'mz']


from src.physics import AeroCalculator

from src.cli_helpers import (
    configure_logging,
    load_project_calculator,
    BatchConfig,
    load_format_from_file,
    get_user_file_format,
    resolve_file_format,
)

from src.special_format_parser import (
    looks_like_special_format,
    process_special_format_file,
    RECOMMENDED_EXT,
)



def generate_output_path(file_path: Path, output_dir: Path, cfg: BatchConfig, create_placeholder: bool = True) -> Path:
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
    logger = logging.getLogger('batch')

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
    last_err = None
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
            last_err = None
            continue
        except PermissionError as pe:
            last_err = pe
            logger.warning("无法在路径创建占位文件: %s（尝试 %d/%d）：%s", candidate, i + 1, max_trials + 1, pe, exc_info=True)
            break
        except OSError as oe:
            last_err = oe
            logger.warning("尝试创建占位文件 %s 时出错（尝试 %d/%d）：%s", candidate, i + 1, max_trials + 1, oe)
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


def process_df_chunk(chunk_df: pd.DataFrame,
                     fx_i: int, fy_i: int, fz_i: int,
                     mx_i: int, my_i: int, mz_i: int,
                     calculator: AeroCalculator,
                     cfg: BatchConfig,
                     out_path: Path,
                     first_chunk: bool,
                     logger) -> tuple:
    """模块级函数：处理单个数据块并将结果写入 out_path。

    返回 (processed_rows, dropped_rows, non_numeric_count, first_chunk_flag)
    """
    # 在使用位置索引前，先校验传入的列索引是否在当前 chunk 的列范围内
    num_cols = chunk_df.shape[1]
    index_specs = [
        ("fx", fx_i),
        ("fy", fy_i),
        ("fz", fz_i),
        ("mx", mx_i),
        ("my", my_i),
        ("mz", mz_i),
    ]
    invalid = [(name, idx) for name, idx in index_specs if idx < 0 or idx >= num_cols]
    if invalid:
        logger.error(
            "文件 %s: 列索引超出范围（chunk 仅有 %d 列）：%s",
            out_path.name,
            num_cols,
            ", ".join(f"{name}_i={idx}" for name, idx in invalid),
        )
        raise IndexError(
            f"Column index out of range for chunk_df with {num_cols} columns: "
            + ", ".join(f"{name}_i={idx}" for name, idx in invalid)
        )
    # 解析力/力矩列并检测非数值
    # 一次性按位置提取所有 6 列，使用向量化操作而非逐列循环
    selected_cols = chunk_df.iloc[:, [fx_i, fy_i, fz_i, mx_i, my_i, mz_i]].copy()
    # 使用向量化的 apply 替换逐列 pd.to_numeric 循环（性能提升 2-3 倍）
    selected_cols = selected_cols.apply(pd.to_numeric, errors='coerce')
    forces_df = selected_cols.iloc[:, :3]
    moments_df = selected_cols.iloc[:, 3:]
    mask_non_numeric = forces_df.isna().any(axis=1) | moments_df.isna().any(axis=1)
    # 为避免后续 index 对齐问题，使用 numpy 布尔数组作为掩码
    mask_array = mask_non_numeric.to_numpy()
    n_non = int(mask_non_numeric.sum())
    dropped = 0

    if n_non:
        # 记录示例行用于诊断
        sample_rows_val = cfg.sample_rows if cfg.sample_rows is not None else DEFAULT_SAMPLE_ROWS
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
    if cfg.treat_non_numeric == 'drop':
        valid_idx = ~mask_non_numeric
        if valid_idx.sum() == 0:
            # 全部丢弃
            dropped = len(chunk_df)
            return 0, dropped, n_non, first_chunk
        forces = forces_df.loc[valid_idx].to_numpy(dtype=float)
        moments = moments_df.loc[valid_idx].to_numpy(dtype=float)
        data_df = chunk_df.loc[valid_idx].reset_index(drop=True)
    elif cfg.treat_non_numeric == 'nan':
        # 保留 NaN，让后续计算和结果中体现为 NaN
        forces = forces_df.to_numpy(dtype=float)
        moments = moments_df.to_numpy(dtype=float)
        data_df = chunk_df.reset_index(drop=True)
    else:
        # 默认或 'zero' 策略：将非数值按 0 处理
        forces = forces_df.fillna(0.0).to_numpy(dtype=float)
        moments = moments_df.fillna(0.0).to_numpy(dtype=float)
        data_df = chunk_df.reset_index(drop=True)

    logger.info(f"  执行坐标变换... 行数={len(forces)}")
    results = calculator.process_batch(forces, moments)

    # 使用向量化方式构建输出 DataFrame，避免逐列赋值
    # 创建字典：所有结果列直接从 numpy 数组列映射
    out_data = {
        'Fx_new': results['force_transformed'][:, 0],
        'Fy_new': results['force_transformed'][:, 1],
        'Fz_new': results['force_transformed'][:, 2],
        'Mx_new': results['moment_transformed'][:, 0],
        'My_new': results['moment_transformed'][:, 1],
        'Mz_new': results['moment_transformed'][:, 2],
        'Cx': results['coeff_force'][:, 0],
        'Cy': results['coeff_force'][:, 1],
        'Cz': results['coeff_force'][:, 2],
        'Cl': results['coeff_moment'][:, 0],
        'Cm': results['coeff_moment'][:, 1],
        'Cn': results['coeff_moment'][:, 2],
    }
    
    # 添加 passthrough 列（向量化）
    for col_idx in cfg.passthrough_columns:
        if col_idx < len(data_df.columns):
            out_data[f'Col_{col_idx}'] = data_df.iloc[:, col_idx].values
    
    # 添加 alpha 列（如果配置）
    if cfg.column_mappings.get('alpha') is not None:
        aidx = cfg.column_mappings['alpha']
        if aidx < len(data_df.columns):
            out_data['Alpha'] = data_df.iloc[:, aidx].values
    
    # 一次性从字典构建 DataFrame（远比逐列赋值高效）
    out_df = pd.DataFrame(out_data)

    # 对于 'nan' 策略，将原始存在缺失的行对应计算列置为 NaN（向量化）
    if cfg.treat_non_numeric == 'nan' and n_non > 0:
        # 使用 NumPy 的高效布尔掩码而非逐行 loc
        comp_cols = ['Fx_new', 'Fy_new', 'Fz_new', 'Mx_new', 'My_new', 'Mz_new', 'Cx', 'Cy', 'Cz', 'Cl', 'Cm', 'Cn']
        out_df.loc[mask_array, comp_cols] = np.nan

    mode = 'w' if first_chunk else 'a'
    header = first_chunk

    # 确保父目录存在
    out_path.parent.mkdir(parents=True, exist_ok=True)

    open_mode = 'w' if mode == 'w' else 'a'

    # 写入重试参数（使用模块级常量）
    last_exc = None

    # 对于 append 模式，直接在目标文件上以二进制追加写入（减少替换竞争）
    if mode == 'a':
        csv_bytes = out_df.to_csv(index=False, header=header, encoding='utf-8').encode('utf-8')
        for attempt in range(1, SHARED_RETRY_ATTEMPTS + 1):
            try:
                # 以二进制追加打开并尝试加锁写入（若可用）
                with open(out_path, 'ab') as f:
                    try:
                        if portalocker:
                            try:
                                portalocker.lock(f, portalocker.LOCK_EX)
                            except Exception as le:
                                logger.debug("portalocker.lock 失败，继续以无锁追加写入：%s", le)
                        else:
                            logger.debug("portalocker 不可用，按附加模式直接写入（best-effort）: %s", out_path)
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
                        if portalocker:
                            try:
                                portalocker.unlock(f)
                            except Exception:
                                logger.debug("portalocker.unlock 失败（忽略）")
                # 成功写入
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                logger.warning("追加写入 %s 失败（尝试 %d/%d）：%s", out_path.name, attempt, SHARED_RETRY_ATTEMPTS, e)
                if attempt < SHARED_RETRY_ATTEMPTS:
                    time.sleep(WRITE_RETRY_BACKOFF_SECONDS[min(attempt-1, len(WRITE_RETRY_BACKOFF_SECONDS)-1)])
                else:
                    logger.exception("追加写入失败，达到最大重试次数")

        if last_exc is not None:
            raise last_exc

    else:
        # 使用临时文件并替换以实现原子写入（用于首次写入或覆盖）
        for attempt in range(1, SHARED_RETRY_ATTEMPTS + 1):
            try:
                with open(out_path, open_mode, encoding='utf-8', newline='') as f:
                    try:
                        if portalocker:
                            try:
                                portalocker.lock(f, portalocker.LOCK_EX)
                            except Exception as le:
                                logger.debug("portalocker.lock 失败，继续以无锁模式写入：%s", le)
                        else:
                            logger.debug("portalocker 不可用，跳过文件锁（best-effort 写入）: %s", out_path)
                    except Exception:
                        logger.exception("尝试加锁时发生意外异常（忽略并继续写入）")

                    try:
                        out_df.to_csv(f, index=False, header=header, encoding='utf-8')
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
                    logger.warning("写入临时文件 %s 遇到 PermissionError（尝试 %d/%d），将重试：%s", out_path.name, attempt, SHARED_RETRY_ATTEMPTS, e, exc_info=True)
                else:
                    logger.error("写入临时文件 %s 失败（尝试 %d/%d）：%s", out_path.name, attempt, SHARED_RETRY_ATTEMPTS, e)

                if attempt < SHARED_RETRY_ATTEMPTS:
                    time.sleep(WRITE_RETRY_BACKOFF_SECONDS[min(attempt-1, len(WRITE_RETRY_BACKOFF_SECONDS)-1)])
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
    patterns = [p.strip() for p in pattern.split(';') if p.strip()]
    if not patterns:
        patterns = [pattern]

    matched_files = []
    for file_path in directory.rglob('*'):
        if not file_path.is_file():
            continue
        if any(fnmatch.fnmatch(file_path.name, pat) for pat in patterns):
            matched_files.append(file_path)

    return sorted(matched_files)


def parse_selection(sel_str: str, n: int) -> list:
    """解析用户选择的文件索引字符串，支持 all、逗号分隔和区间（如 2-4）。

    返回有效的 0-based 索引列表（已排序且去重）。
    """
    if not sel_str or sel_str in ('all', 'a'):
        return list(range(n))
    parts = [s.strip() for s in sel_str.split(',') if s.strip()]
    idxs = []
    for part in parts:
        if '-' in part:
            try:
                a, b = part.split('-', 1)
                a_i = int(a) - 1
                b_i = int(b) - 1
                # 限界检查将在后面进行
                idxs.extend(range(a_i, b_i + 1))
            except (ValueError, TypeError):
                logging.warning("批处理文件选择解析时忽略了无效区间片段 '%s'（原始输入: '%s'）。", part, sel_str)
                continue
        else:
            try:
                idxs.append(int(part) - 1)
            except (ValueError, TypeError):
                logging.warning("批处理文件选择解析时忽略了无效索引片段 '%s'（原始输入: '%s'）。", part, sel_str)

    # 规范化：去重、排序，并限定在 [0, n-1]
    valid = sorted({i for i in idxs if 0 <= i < n})
    return valid


def read_data_with_config(file_path: Path, config: BatchConfig) -> pd.DataFrame:
    """根据 `config` 读取整个数据表（非流式模式）。

    返回 pandas DataFrame（不做列名解析，使用 header=None）。
    """
    p = Path(file_path)
    ext = p.suffix.lower()
    if ext == '.csv':
        return pd.read_csv(p, header=None, skiprows=config.skip_rows)
    elif ext in {'.xls', '.xlsx', '.xlsm', '.xlsb', '.odf', '.ods', '.odt'}:
        return pd.read_excel(p, header=None, skiprows=config.skip_rows)
    else:
        raise ValueError(
            f"不支持的文件类型: '{file_path}'. 仅支持 CSV (.csv) 和 Excel "
            f"(.xls, .xlsx, .xlsm, .xlsb, .odf, .ods, .odt) 文件。"
        )


def process_single_file(file_path: Path, calculator: AeroCalculator,
                       config: BatchConfig, output_dir: Path,
                       project_data=None) -> bool:
    """处理单个文件（支持 chunked CSV）。

    实现要点：
    - 使用临时文件写入，完成后原子替换到目标文件；
    - 在写入开始写入 `.partial`，成功时写入 `.complete`；
    - 在异常时清理临时并在 partial 中记录错误信息。
    """
    logger = logging.getLogger('batch')

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
                logger.warning("特殊格式文件 %s 未产生输出，可能因缺少匹配的 Target part 或列缺失", file_path.name)
                return False
            logger.info("特殊格式文件 %s 已处理，生成 %d 个 part 输出", file_path.name, len(outputs))
            return True
        except Exception as exc:
            logger.error("处理特殊格式文件 %s 失败: %s", file_path.name, exc, exc_info=True)
            return False

    # 安全解析 chunksize
    if config.chunksize:
        try:
            config.chunksize = int(config.chunksize)
        except (ValueError, TypeError):
            config.chunksize = None

    ext = Path(file_path).suffix.lower()
    use_chunks = (ext == '.csv') and config.chunksize and config.chunksize > 0

    # 若非流式，先读取整表以便列索引校验
    df = None
    if not use_chunks:
        df = read_data_with_config(file_path, config)
        num_cols = len(df.columns)
        for key in REQUIRED_KEYS:
            col_idx = config.column_mappings.get(key)
            if col_idx is None:
                raise ValueError(f"列映射缺失: '{key}' 未配置")
            if not (0 <= col_idx < num_cols):
                raise ValueError(f"列索引越界: column_mappings['{key}'] = {col_idx}, 但当前数据仅有 {num_cols} 列")

    fx_i = config.column_mappings['fx']
    fy_i = config.column_mappings['fy']
    fz_i = config.column_mappings['fz']
    mx_i = config.column_mappings['mx']
    my_i = config.column_mappings['my']
    mz_i = config.column_mappings['mz']

    out_path = generate_output_path(file_path, output_dir, config)
    temp_fd, temp_name = tempfile.mkstemp(prefix=out_path.name + '.', dir=str(out_path.parent), text=True)
    os.close(temp_fd)
    temp_out_path = Path(temp_name)

    partial_flag = out_path.with_name(out_path.name + '.partial')
    complete_flag = out_path.with_name(out_path.name + '.complete')
    try:
        partial_flag.write_text(datetime.now().isoformat())
    except Exception:
        pass

    first_chunk = True
    total_processed = 0
    total_dropped = 0
    total_non_numeric = 0

    try:
        if use_chunks:
            reader = pd.read_csv(file_path, header=None, skiprows=config.skip_rows, chunksize=int(config.chunksize))
            try:
                first = next(reader)
            except StopIteration:
                logger.warning(f"文件 {file_path} 为空，跳过处理")
                if temp_out_path.exists():
                    try:
                        temp_out_path.unlink()
                    except Exception:
                        pass
                return False

            # 校验首块列数
            num_cols = len(first.columns)
            for key in REQUIRED_KEYS:
                col_idx = config.column_mappings.get(key)
                if col_idx is None or not (0 <= col_idx < num_cols):
                    raise ValueError(f"列映射缺失或越界: {key} -> {col_idx}")

            proc, dropped, non_num, first_chunk = process_df_chunk(
                first, fx_i, fy_i, fz_i, mx_i, my_i, mz_i, calculator, config, temp_out_path, first_chunk, logger
            )
            total_processed += proc
            total_dropped += dropped
            total_non_numeric += non_num

            for chunk in reader:
                proc, dropped, non_num, first_chunk = process_df_chunk(
                    chunk, fx_i, fy_i, fz_i, mx_i, my_i, mz_i, calculator, config, temp_out_path, first_chunk, logger
                )
                total_processed += proc
                total_dropped += dropped
                total_non_numeric += non_num
        else:
            proc, dropped, non_num, first_chunk = process_df_chunk(
                df, fx_i, fy_i, fz_i, mx_i, my_i, mz_i, calculator, config, temp_out_path, first_chunk, logger
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
                    logger.warning("os.replace 被拒绝（PermissionError）: %s -> %s（%d/%d），将重试：%s", temp_out_path.name, out_path.name, ri, replace_attempts, e, exc_info=True)
                else:
                    logger.warning("尝试用 os.replace 替换 %s -> %s 失败（%d/%d）：%s", temp_out_path.name, out_path.name, ri, replace_attempts, e)
                if ri < replace_attempts:
                    time.sleep(replace_backoffs[min(ri-1, len(replace_backoffs)-1)])
        if not replaced:
            # 若替换失败，抛出并由外层 except 捕获以进行清理和记录
            if replace_err is None:
                raise RuntimeError(f"os.replace 替换失败: {temp_out_path} -> {out_path}（无异常信息）")
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

        logger.info(f"处理完成: 已输出 {total_processed} 行；非数值总计 {total_non_numeric} 行；丢弃 {total_dropped} 行")
        logger.info(f"结果文件: {out_path}")
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
        logger.error(f"  ✗ 处理失败: {str(e)}", exc_info=True)
        return False


def _worker_process(args):
    """在子进程中运行单个文件的处理（用于并行）。

    args_tuple: (file_path_str, config_dict, config_path, output_dir_str)
    - config_dict: dict representation of BatchConfig (keys: skip_rows, column_mappings, passthrough_columns)
    - config_path: path to JSON config for AeroCalculator (project geometry)
    """
    try:
        # 期望 args 为 dict，包含明确字段，减少位置参数易碎性
        if not isinstance(args, dict):
            raise ValueError("子进程参数必须为 dict，推荐键: file_path, config_dict, project_config_path, output_dir, registry_db, strict")

        file_path_str = args.get('file_path', '<unknown>')
        config_dict = args.get('config_dict')
        project_config_path = args.get('project_config_path')
        output_dir_str = args.get('output_dir')
        registry_db = args.get('registry_db', None)
        strict = bool(args.get('strict', False))

        if not all([file_path_str, config_dict is not None, project_config_path, output_dir_str is not None]):
            raise ValueError("子进程参数不完整，至少需要 file_path, config_dict, project_config_path, output_dir")

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
        calc_pickle = args.get('calculator_pickle')
        if calc_pickle:
            try:
                project_data, calculator = pickle.loads(calc_pickle)
                _WORKER_CALCULATOR = calculator
                _WORKER_PROJECT_PATH = project_config_path
                _WORKER_PROJECT_DATA = project_data
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning("反序列化传入的 calculator 失败，回退到按路径加载: %s", e)

        if calculator is None:
            if _WORKER_CALCULATOR is not None and project_config_path == _WORKER_PROJECT_PATH:
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
        cfg.skip_rows = int(config_dict.get('skip_rows', 0))
        cfg.column_mappings.update(config_dict.get('column_mappings', {}))
        cfg.passthrough_columns = config_dict.get('passthrough_columns', [])
        cfg.chunksize = config_dict.get('chunksize', None)
        cfg.name_template = config_dict.get('name_template', cfg.name_template)
        cfg.timestamp_format = config_dict.get('timestamp_format', cfg.timestamp_format)
        cfg.overwrite = bool(config_dict.get('overwrite', cfg.overwrite))
        cfg.treat_non_numeric = config_dict.get('treat_non_numeric', cfg.treat_non_numeric)
        cfg.sample_rows = config_dict.get('sample_rows', cfg.sample_rows)

        # 若提供了 registry_db，则尝试按文件解析最终配置
        if registry_db:
            try:
                from src.cli_helpers import resolve_file_format
                # 从传入的 args 中读取 enable_sidecar 标志（默认为 False）
                enable_sidecar = bool(args.get('enable_sidecar', False))
                cfg = resolve_file_format(str(file_path), cfg, enable_sidecar=enable_sidecar, registry_db=registry_db)
            except Exception as e:
                logger = logging.getLogger(__name__)
                if strict:
                    # 严格模式下：解析失败视为致命错误，交由上层统一处理
                    logger.warning(
                        "使用registry_db\"%s\"解析\"%s\"的文件格式失败，错误：%s",
                        registry_db, str(file_path), e
                    )
                    raise
                else:
                    # 非严格模式：记录警告并回退到全局配置
                    logger.warning(
                        "Registry lookup failed for '%s' with registry_db '%s', falling back to global config: %s",
                        str(file_path), registry_db, e
                    )

        success = process_single_file(file_path, calculator, cfg, output_dir, project_data)
        return (str(file_path), success, None)
    except Exception as e:
        # 捕获子进程中任何异常，返回失败信息以便主进程记录
        tb = traceback.format_exc()
        return (
            file_path_str,
            False,
            tb
        )
def run_batch_processing_v2(config_path: str, input_path: str, data_config: BatchConfig = None, registry_db: str = None, strict: bool = False, enable_sidecar: bool = False, dry_run: bool = False, show_progress: bool = False, output_json: str = None, summary: bool = False, target_part: str = None, target_variant: int = 0):
    """增强版批处理主函数

    使用 `logger` 输出运行信息；若 `strict` 为 True，则在 registry/format 解析失败时中止。
    """
    logger = logging.getLogger('batch')

    # 使用模块级的 _error_exit_json 工具进行错误退出（已在模块顶部定义）
    logger.info("%s", "=" * 70)
    logger.info("MomentTransfer v2.0")
    logger.info("%s", "=" * 70)
    
    # 1. 加载配置（支持新版对等的 Source/Target 结构，向后兼容旧的 SourceCoordSystem）
    logger.info("[1/5] 加载几何配置: %s", config_path)
    try:
        project_data, calculator = load_project_calculator(config_path, target_part=target_part, target_variant=target_variant)
        # 显示实际使用的 Target part 名称
        used_target = getattr(calculator, 'target_frame', None)
        used_target_name = getattr(used_target, 'part_name', None) if used_target is not None else None
        logger.info("  ✓ 配置加载成功: %s", used_target_name)
    except Exception as e:
        logger.error("  ✗ 配置加载失败: %s", e)
        logger.error("  提示: 请检查 JSON 是否包含 Target 的 CoordSystem/MomentCenter/Q/S 或使用 GUI/creator.py 生成兼容的配置。")
        return
    
    # 2. 获取数据格式配置（交互或非交互）
    logger.info("[2/5] 配置数据格式")
    # 若外部已提供 data_config（例如非交互模式），则使用之
    if data_config is None:
        data_config = get_user_file_format()
    
    # 3. 确定输入文件列表
    logger.info("[3/5] 扫描输入文件")
    input_path = Path(input_path)
    files_to_process = []
    
    # 若提供了 data_config 且同时提供了 registry_db，则视为非交互自动模式，避免使用 input() 阶段
    non_interactive_mode = (data_config is not None and registry_db is not None)

    if input_path.is_file():
        logger.info("  模式: 单文件处理")
        files_to_process = [input_path]
        output_dir = input_path.parent
    elif input_path.is_dir():
        logger.info("  模式: 目录批处理")
        if non_interactive_mode:
            # 非交互自动模式：使用默认模式匹配所有 CSV 文件并全部处理
            pattern = "*.csv;*.xlsx;*.xls;*.mtfmt;*.mtdata;*.txt;*.dat"
            files = find_matching_files(str(input_path), pattern)
            logger.info("  自动模式下找到 %d 个匹配文件 (pattern=%s)", len(files), pattern)
            files_to_process = files
            output_dir = input_path
        else:
            pattern = input("  文件名匹配模式 (如 *.csv;*.mtfmt): ").strip()
            if not pattern:
                pattern = "*.csv;*.xlsx;*.xls;*.mtfmt;*.mtdata;*.txt;*.dat"
            files = find_matching_files(str(input_path), pattern)
            logger.info("  找到 %d 个匹配文件:", len(files))
            for i, fp in enumerate(files, start=1):
                logger.info("    %d. %s", i, fp.name)

            sel = input("  选择要处理的文件（默认 all）: ").strip().lower()
            chosen_idxs = parse_selection(sel, len(files))
            if not chosen_idxs:
                logger.info("  未选择有效文件，已取消")
                return

            files_to_process = [files[i] for i in chosen_idxs]
            # 输出目录默认为输入目录
            output_dir = input_path
    else:
        print(f"  [错误] 无效的输入路径: {input_path}")
        logger.error("  [错误] 无效的输入路径: %s", input_path)
    
    # 4. 确认处理
    logger.info("[4/5] 准备处理 %d 个文件", len(files_to_process))
    logger.info("  输出目录: %s", output_dir)
    # 若自动模式则默认确认
    if not non_interactive_mode:
        confirm = input("  确认开始处理? (y/n): ").strip().lower()
        if confirm != 'y':
            logger.info("  已取消")
            return
    
    # 5. 批量处理
    logger.info("[5/5] 开始批量处理...")
    success_count = 0

    # Dry-run: 仅打印将处理的文件、解析的格式与目标输出路径，然后返回
    if dry_run:
        logger.info("Dry-run 模式：不写入文件，仅显示解析结果。")
        for fp in files_to_process:
            try:
                from src.cli_helpers import resolve_file_format
                cfg_local = resolve_file_format(str(fp), data_config, enable_sidecar=enable_sidecar, registry_db=registry_db)
            except Exception as e:
                logger.warning("解析文件 %s 的格式失败：%s", fp, e)
                cfg_local = data_config
            out_path = generate_output_path(fp, output_dir, cfg_local, create_placeholder=False)
            logger.info("将处理: %s -> %s (format: %s)", fp, out_path, cfg_local.column_mappings)
        return
    
    # 若在外部通过 CLI 提供了并行参数，会由外层主函数处理；这里保持串行以便直接调用
    # 记录开始时间以便估算 ETA
    start_time = datetime.now()
    # 确保收集结果的容器始终存在，避免在空文件列表下引用未定义变量
    results = []
    for i, file_path in enumerate(files_to_process, 1):
        logger.info("进度: [%d/%d] %s", i, len(files_to_process), file_path.name)
        # 在串行模式下也优先通过 registry 或侧车/目录解析每个文件的最终配置
        try:
            from src.cli_helpers import resolve_file_format
            cfg_local = resolve_file_format(str(file_path), data_config, enable_sidecar=bool(registry_db), registry_db=registry_db)
        except Exception:
            # 解析失败：记录并根据 strict 决定是否中止
            logger.warning("解析文件 %s 的格式失败，使用全局配置作为回退。", file_path)
            if strict and non_interactive_mode:
                logger.error("strict 模式下解析失败，终止批处理。")
                return
            cfg_local = data_config

        t0 = datetime.now()
        ok = process_single_file(file_path, calculator, cfg_local, output_dir, project_data)
        elapsed = (datetime.now() - t0).total_seconds()
        if ok:
            success_count += 1

        # 收集结果以支持 --output-json/--summary
        results.append({
            'file': str(file_path),
            'success': bool(ok),
            'elapsed_sec': round(elapsed, 3)
        })

        # 总是记录每文件耗时，便于 log-file 中查看详情
        logger.info("文件 %s 处理完成: 成功=%s, 耗时=%.2fs", file_path.name, ok, elapsed)

        # 若开启进度显示，则打印稳定的 ETA 估算（基于平均每文件耗时）
        if show_progress:
            files_done = i
            files_left = len(files_to_process) - files_done
            avg_per_file = (datetime.now() - start_time).total_seconds() / files_done
            eta_seconds = int(avg_per_file * files_left)
            logger.info("已完成 %d/%d，累计耗时 %.1fs，本文件耗时 %.2fs，平均 %.2fs/文件，预计剩余 %ds", files_done, len(files_to_process), (datetime.now() - start_time).total_seconds(), elapsed, avg_per_file, eta_seconds)
            # 同步向 stdout 输出可机器解析的进度行（JSON），便于监控系统采集
            try:
                prog = {
                    'completed': files_done,
                    'total': len(files_to_process),
                    'file': str(file_path.name),
                    'success': bool(ok),
                    'elapsed_sec': round(elapsed or 0.0, 3),
                    'avg_sec': round(avg_per_file or 0.0, 3),
                    'eta_sec': eta_seconds
                }
                print(json.dumps(prog, ensure_ascii=False))
                sys.stdout.flush()
            except Exception:
                try:
                    print(f"[{files_done}/{len(files_to_process)}] {file_path.name} success={ok} elapsed={elapsed:.2f}s eta={eta_seconds}s")
                    sys.stdout.flush()
                except Exception:
                    pass
    
    # 总结
    print("\n" + "=" * 70)
    print(f"批处理完成!")
    print(f"  成功: {success_count}/{len(files_to_process)}")
    print(f"  失败: {len(files_to_process) - success_count}/{len(files_to_process)}")
    print("=" * 70)

    # 写出 JSON 汇总（若请求）
    if output_json:
        try:
            results  # 确保 results 已定义；若未定义则回退为空列表
        except NameError:
            results = []
        summary_payload = {
            'total': len(files_to_process),
            'success': success_count,
            'fail': len(files_to_process) - success_count,
            'files': results
        }
        try:
            with open(output_json, 'w', encoding='utf-8') as fh:
                json.dump(summary_payload, fh, ensure_ascii=False, indent=2)
            logger.info('已将处理结果写入 %s', output_json)
        except Exception:
            logger.exception('写入 output_json 失败')

    if summary:
        try:
            print(json.dumps({'total': len(files_to_process), 'success': success_count, 'fail': len(files_to_process) - success_count}, ensure_ascii=False))
        except Exception:
            logger.exception('打印 summary 失败')


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('-c', '--config', 'config', required=True, help='配置文件路径 (JSON)')
@click.option('-i', '--input', 'input_path', required=True, help='输入文件或目录路径')
@click.option('-p', '--pattern', default=None, help='文件匹配模式（目录模式下），支持分号分隔多模式，如 "*.csv;*.mtfmt"')
@click.option('-f', '--format-file', 'format_file', default=None, help='数据格式 JSON 文件路径（包含 skip_rows, columns, passthrough）')
@click.option('--non-interactive', 'non_interactive', is_flag=True, help='以非交互模式运行（必须提供 --format-file）')
@click.option('--log-file', 'log_file', default=None, help='将日志写入指定文件')
@click.option('--verbose', 'verbose', is_flag=True, help='增加日志详细程度')
@click.option('--workers', 'workers', type=int, default=1, help='并行工作进程数（默认为1，表示串行）')
@click.option('--chunksize', 'chunksize', type=int, default=None, help='CSV 流式读取块大小（行数），若未设置则一次性读取整个文件')
@click.option('--overwrite', 'overwrite', is_flag=True, help='若输出文件存在则覆盖（默认会自动改名避免冲突）')
@click.option('--name-template', 'name_template', default=None, help='输出文件名模板，支持 {stem} 和 {timestamp} 占位符')
@click.option('--timestamp-format', 'timestamp_format', default=None, help='时间戳格式，用于 {timestamp} 占位符，默认 %%Y%%m%%d_%%H%%M%%S')
@click.option('--treat-non-numeric', 'treat_non_numeric', type=click.Choice(['zero','nan','drop']), default=None, help='如何处理非数值输入: zero|nan|drop')
@click.option('--sample-rows', 'sample_rows', type=int, default=None, help='记录非数值示例的行数上限 (默认5)')
@click.option('--target-part', 'target_part', default=None, help='目标 part 名称（必须指定或通过参数提供）')
@click.option('--target-variant', 'target_variant', type=int, default=0, help='目标 variant 索引（从0开始，默认0）')
@click.option('--enable-sidecar', 'enable_sidecar', is_flag=True, default=False, help='启用 per-file 覆盖（file-sidecar / dir-default / registry），默认关闭')
@click.option('--registry-db', 'registry_db', default=None, help='(实验) SQLite registry 数据库路径（仅在启用 per-file 覆盖时使用）', hidden=True)
@click.option('--strict', 'strict', is_flag=True, help='非交互模式下 registry/format 解析失败时终止（默认回退到全局配置）')
@click.option('--dry-run', 'dry_run', is_flag=True, help='仅解析并显示将处理的文件与输出路径，但不实际写入')
@click.option('--progress', 'show_progress', is_flag=True, help='显示处理进度与 ETA（串行/并行均支持）')
@click.option('--output-json', 'output_json', default=None, help='将处理结果以 JSON 写入指定文件')
@click.option('--summary', 'summary', is_flag=True, help='在结束时打印简要的 JSON 汇总（机器可读）')
def main(**cli_options):
    """批处理入口（click 版）"""
    # 将 CLI 选项解包为原来的局部变量，保持后续逻辑不变
    config = cli_options.get('config')
    input_path = cli_options.get('input_path')
    pattern = cli_options.get('pattern')
    format_file = cli_options.get('format_file')
    non_interactive = cli_options.get('non_interactive')
    log_file = cli_options.get('log_file')
    verbose = cli_options.get('verbose')
    workers = cli_options.get('workers')
    chunksize = cli_options.get('chunksize')
    overwrite = cli_options.get('overwrite')
    name_template = cli_options.get('name_template')
    timestamp_format = cli_options.get('timestamp_format')
    treat_non_numeric = cli_options.get('treat_non_numeric')
    sample_rows = cli_options.get('sample_rows')
    target_part = cli_options.get('target_part')
    target_variant = cli_options.get('target_variant')
    enable_sidecar = cli_options.get('enable_sidecar')
    registry_db = cli_options.get('registry_db')
    strict = cli_options.get('strict')
    dry_run = cli_options.get('dry_run')
    show_progress = cli_options.get('show_progress')
    output_json = cli_options.get('output_json')
    summary = cli_options.get('summary')
    # 配置 logging（通过共享 helper）
    logger = configure_logging(log_file, verbose)
    # 读取数据格式配置
    data_config = None
    # 优先使用命令行提供的格式文件（无论是否为非交互模式）以避免不必要的交互
    if format_file:
        try:
            data_config = load_format_from_file(format_file)
            logger.info(f'使用格式文件: {format_file}')
        except Exception as e:
            logger.exception('读取格式文件失败')
            _error_exit_json(f"读取格式文件失败: {e}", code=3)

    if non_interactive and data_config is None:
        # 非交互模式下要求提供全局格式文件或启用 per-file 覆盖策略（enable_sidecar）
        if not enable_sidecar and not registry_db:
            _error_exit_json("--non-interactive 模式下必须提供 --format-file 或启用 per-file 覆盖（--enable-sidecar）", code=2,
                             hint="传入 --format-file 或 --enable-sidecar（可选同时传入 --registry-db）以在非交互模式下解析每个文件的格式。")
        # 未提供全局格式文件：使用默认 BatchConfig 作为全局基准，具体文件的最终配置由 sidecar/dir-default/registry 覆盖（仅当 enable_sidecar=True 时）
        data_config = BatchConfig()
        logger.info('非交互模式且未提供 --format-file，使用默认 BatchConfig 并依赖 per-file 覆盖策略进行每文件解析（若已启用）')

    if data_config is None:
        # 交互式获取格式配置
        data_config = get_user_file_format()

    # 命令行参数覆盖格式文件中的设置（若提供）
    if chunksize is not None:
        data_config.chunksize = chunksize
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
    if pattern:
        pat = pattern
    else:
        pat = None

    # 并行处理支持：若 workers>1，则使用 ProcessPoolExecutor
    try:
        if workers > 1:
            logger.info(f'并行处理模式: workers={workers}')
            # 构造文件列表
            input_path_obj = Path(input_path)
            files_to_process = []
            output_dir = None
            if input_path_obj.is_file():
                files_to_process = [input_path_obj]
                output_dir = input_path_obj.parent
            elif input_path_obj.is_dir():
                if pat:
                    pat_use = pat
                else:
                    if non_interactive:
                        pat_use = '*.csv;*.xlsx;*.xls;*.mtfmt;*.mtdata;*.txt;*.dat'
                        logger.info("非交互模式：使用默认文件匹配模式 '%s'", pat_use)
                    else:
                        pat_use = input('文件名匹配模式 (如 *.csv;*.mtfmt，默认包含 csv/xlsx/mtfmt): ').strip() or '*.csv;*.xlsx;*.xls;*.mtfmt;*.mtdata;*.txt;*.dat'
                files = find_matching_files(str(input_path_obj), pat_use)
                # 并行模式下不提供交互选择：自动处理所有匹配到的文件
                # 选择 all
                chosen_idxs = list(range(len(files)))
                files_to_process = [files[i] for i in chosen_idxs]
                output_dir = input_path_obj
            else:
                _error_exit_json(f'无效的输入路径: {input_path}', code=4)

            # 准备并行任务参数（将 data_config 序列化为 dict）
            config_dict = {
                'skip_rows': data_config.skip_rows,
                'column_mappings': data_config.column_mappings,
                'passthrough_columns': data_config.passthrough_columns,
                'chunksize': data_config.chunksize,
                'name_template': data_config.name_template,
                'timestamp_format': data_config.timestamp_format,
                'overwrite': data_config.overwrite,
                'treat_non_numeric': data_config.treat_non_numeric,
                'sample_rows': data_config.sample_rows,
            }


            with ProcessPoolExecutor(max_workers=workers) as exe:
                futures = {}
                start_times = {}
                results = []
                for fp in files_to_process:
                    worker_args = {
                        'file_path': str(fp),
                        'config_dict': config_dict,
                        'project_config_path': config,
                        'output_dir': str(output_dir),
                        'registry_db': registry_db,
                        'strict': strict,
                        'enable_sidecar': enable_sidecar,
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
                        results.append({
                            'file': file_str,
                            'success': bool(ok),
                            'error': err,
                            'elapsed_sec': round(elapsed or 0.0, 3)
                        })

                        if ok:
                            logger.info("处理成功: %s (耗时: %.2fs)", file_str, elapsed if elapsed else 0.0)
                            success_count += 1
                        else:
                            logger.error("处理失败: %s 错误: %s (耗时: %.2fs)", file_str, err, elapsed if elapsed else 0.0)

                        # 当请求进度显示时，记录 ETA 与平均每文件耗时
                        if show_progress and eta is not None:
                            logger.info("已完成 %d/%d，平均每文件耗时 %.2fs，预计剩余 %ds", completed, total, avg, eta)
                            # 同步向 stdout 输出可机器解析的进度行（JSON），便于监控系统采集
                            try:
                                prog = {
                                    'completed': completed,
                                    'total': total,
                                    'file': file_str,
                                    'success': bool(ok),
                                    'elapsed_sec': round(elapsed or 0.0, 3),
                                    'avg_sec': round(avg or 0.0, 3),
                                    'eta_sec': eta
                                }
                                print(json.dumps(prog, ensure_ascii=False))
                                sys.stdout.flush()
                            except Exception:
                                # 回退到简单文本输出
                                try:
                                    print(f"[{completed}/{total}] {file_str} success={ok} elapsed={elapsed:.2f}s eta={eta}s")
                                    sys.stdout.flush()
                                except Exception:
                                    pass
                        else:
                            logger.info("已完成 %d/%d", completed, total)
                            if show_progress:
                                try:
                                    print(json.dumps({'completed': completed, 'total': total}, ensure_ascii=False))
                                    sys.stdout.flush()
                                except Exception:
                                    pass

                    except Exception as e:
                        logger.exception("任务异常: %s", fp)

            # 写出 JSON 汇总（若请求）
            if output_json:
                summary_payload = {
                    'total': len(files_to_process),
                    'success': success_count,
                    'fail': len(files_to_process) - success_count,
                    'files': results
                }
                try:
                    with open(output_json, 'w', encoding='utf-8') as fh:
                        json.dump(summary_payload, fh, ensure_ascii=False, indent=2)
                    logger.info('已将处理结果写入 %s', output_json)
                except Exception:
                    logger.exception('写入 output_json 失败')

            if summary:
                print(json.dumps({'total': len(files_to_process), 'success': success_count, 'fail': len(files_to_process) - success_count}, ensure_ascii=False))

            logger.info(f'并行处理完成: 成功 {success_count}/{len(files_to_process)}')
            sys.exit(0 if success_count == len(files_to_process) else 1)

        else:
            # 串行模式：委托原有 run_batch_processing_v2（交互或已读取 data_config）
            run_batch_processing_v2(
                config,
                input_path,
                data_config,
                registry_db=registry_db,
                strict=strict,
                enable_sidecar=enable_sidecar,
                dry_run=dry_run,
                show_progress=show_progress,
                output_json=output_json,
                summary=summary,
                target_part=target_part,
                target_variant=target_variant,
            )
            sys.exit(0)
    except Exception:
        logger.exception('批处理失败')
        sys.exit(5)


if __name__ == '__main__':
    main()