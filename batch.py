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
try:
    import fcntl
except Exception:
    fcntl = None
try:
    import msvcrt
except Exception:
    msvcrt = None

# 最大文件名冲突重试次数（避免魔法数字）
MAX_FILE_COLLISION_RETRIES = 1000

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



def generate_output_path(file_path: Path, output_dir: Path, cfg: BatchConfig) -> Path:
    """根据模板与时间戳生成输出路径，处理冲突和可写性检查。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = file_path.stem
    timestamp = datetime.now().strftime(cfg.timestamp_format)
    name = cfg.name_template.format(stem=stem, timestamp=timestamp)
    out_path = output_dir / name

    if out_path.exists():
        if cfg.overwrite:
            # 尝试删除旧文件以便后续写入（若无法删除则抛出）
            try:
                out_path.unlink()
            except OSError as e:
                raise IOError(f"无法覆盖已存在的输出文件: {out_path} -> {e}")
        else:
            # 自动添加唯一后缀以减少并发冲突（优先短序号尝试，然后回退到 UUID）
            base = out_path.stem
            suf = out_path.suffix
            found = False
            for i in range(1, min(20, MAX_FILE_COLLISION_RETRIES) + 1):
                candidate = output_dir / f"{base}_{i}{suf}"
                if not candidate.exists():
                    out_path = candidate
                    found = True
                    break
            if not found:
                # 回退到 UUID 保证唯一性，适用于高并发场景
                unique = uuid.uuid4().hex
                out_path = output_dir / f"{base}_{unique}{suf}"

    # 最后检查目录是否可写 — 使用 mkstemp 生成唯一临时文件以避免并发冲突
    try:
        fd, test_path = tempfile.mkstemp(prefix=out_path.stem + ".__writetest__", dir=str(out_path.parent), text=True)
        os.close(fd)
        os.remove(test_path)
    except (OSError, IOError, PermissionError) as e:
        raise IOError(f"无法在输出目录写入文件: {out_path.parent} -> {e}") from e

    return out_path


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
    # 一次性按位置提取所有 6 列并复制，避免多次切片与复制
    selected_cols = chunk_df.iloc[:, [fx_i, fy_i, fz_i, mx_i, my_i, mz_i]].copy()
    forces_df = selected_cols.iloc[:, :3]
    moments_df = selected_cols.iloc[:, 3:]
    for col in forces_df.columns:
        forces_df[col] = pd.to_numeric(forces_df[col], errors='coerce')
    for col in moments_df.columns:
        moments_df[col] = pd.to_numeric(moments_df[col], errors='coerce')
    mask_non_numeric = forces_df.isna().any(axis=1) | moments_df.isna().any(axis=1)
    # 为避免后续 index 对齐问题，使用 numpy 布尔数组作为掩码
    mask_array = mask_non_numeric.to_numpy()
    n_non = int(mask_non_numeric.sum())
    dropped = 0

    if n_non:
        # 记录示例行用于诊断
        samp_n = min(cfg.sample_rows, n_non)
        if samp_n > 0:
            idxs = list(np.where(mask_array)[0][:samp_n])
            for idx in idxs:
                # 注意 chunk_df 可能保留原始索引，因此使用 iloc 按位置访问示例
                logger.warning(f"文件 {out_path.name} 非数值示例（chunk 内行 {idx}）: {chunk_df.iloc[idx].to_dict()}")

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

    # 构建输出 DataFrame，与 data_df 行对齐
    out_df = pd.DataFrame()
    for col_idx in cfg.passthrough_columns:
        if col_idx < len(data_df.columns):
            out_df[f'Col_{col_idx}'] = data_df.iloc[:, col_idx]

    if cfg.column_mappings.get('alpha') is not None:
        aidx = cfg.column_mappings['alpha']
        if aidx < len(data_df.columns):
            out_df['Alpha'] = data_df.iloc[:, aidx]

    out_df['Fx_new'] = results['force_transformed'][:, 0]
    out_df['Fy_new'] = results['force_transformed'][:, 1]
    out_df['Fz_new'] = results['force_transformed'][:, 2]

    out_df['Mx_new'] = results['moment_transformed'][:, 0]
    out_df['My_new'] = results['moment_transformed'][:, 1]
    out_df['Mz_new'] = results['moment_transformed'][:, 2]

    out_df['Cx'] = results['coeff_force'][:, 0]
    out_df['Cy'] = results['coeff_force'][:, 1]
    out_df['Cz'] = results['coeff_force'][:, 2]

    out_df['Cl'] = results['coeff_moment'][:, 0]
    out_df['Cm'] = results['coeff_moment'][:, 1]
    out_df['Cn'] = results['coeff_moment'][:, 2]

    # 对于 'nan' 策略，将原始存在缺失的行对应计算列置为 NaN
    if cfg.treat_non_numeric == 'nan' and n_non > 0:
        comp_cols = ['Fx_new', 'Fy_new', 'Fz_new', 'Mx_new', 'My_new', 'Mz_new', 'Cx', 'Cy', 'Cz', 'Cl', 'Cm', 'Cn']
        out_df.loc[mask_array, comp_cols] = np.nan

    mode = 'w' if first_chunk else 'a'
    header = first_chunk

    # 将 DataFrame 序列化为 CSV 文本，然后以文件描述符方式写入以支持 flush+fsync
    csv_text = out_df.to_csv(index=False, header=header, encoding='utf-8')

    # 确保父目录存在
    out_path.parent.mkdir(parents=True, exist_ok=True)

    open_mode = 'w' if mode == 'w' else 'a'
    # 以文本模式打开，写入后立即 flush 并 fsync，必要时尝试加锁（平台相关）
    f = open(out_path, open_mode, encoding='utf-8', newline='')
    try:
        # 尝试获取文件锁，若失败则继续（best-effort）
        try:
            if os.name == 'nt' and msvcrt:
                # Windows: 锁定从当前位置起的 1 字节（尽管不是完美，但能阻止交叉写入）
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            elif fcntl:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass

        f.write(csv_text)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            # 某些平台或文件系统上可能不支持 fsync，忽略该错误
            pass

    finally:
        # 释放文件锁（best-effort）并关闭文件
        try:
            if os.name == 'nt' and msvcrt:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            elif fcntl:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
        finally:
            f.close()

    processed = len(out_df)
    first_chunk = False
    return processed, dropped, n_non, first_chunk


def find_matching_files(directory: str, pattern: str) -> list:
    """在目录中查找匹配模式的文件"""
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"路径不是有效目录: {directory}")
    
    matched_files = []
    for file_path in directory.rglob('*'):
        if file_path.is_file() and fnmatch.fnmatch(file_path.name, pattern):
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
                       config: BatchConfig, output_dir: Path) -> bool:
    """处理单个文件"""
    try:
        logger = logging.getLogger('batch')
        # 检查文件类型与是否启用 chunksize（仅对 CSV 有效）
        # 安全解析 chunksize，避免非数值字符串导致 ValueError 
        if config.chunksize:
            try:
                config.chunksize = int(config.chunksize)
            except (ValueError, TypeError):
                config.chunksize = None

        ext = Path(file_path).suffix.lower()
        use_chunks = (ext == '.csv') and config.chunksize and config.chunksize > 0

        # 若未使用流式，则一次性读取完整表格用于后续处理与列验证
        if not use_chunks:
            df = read_data_with_config(file_path, config)
            # 校验列索引是否在有效范围内
            num_cols = len(df.columns)
            for key in REQUIRED_KEYS:
                col_idx = config.column_mappings.get(key)
                if col_idx is None:
                    raise ValueError(f"列映射缺失: '{key}' 未配置")
                if not (0 <= col_idx < num_cols):
                    raise ValueError(
                        f"列索引越界: column_mappings['{key}'] = {col_idx}, "
                        f"但当前数据仅有 {num_cols} 列"
                    )
        
        # 提取力和力矩数据（按列位置索引），并转换为数值数组
        fx_i = config.column_mappings['fx']
        fy_i = config.column_mappings['fy']
        fz_i = config.column_mappings['fz']
        mx_i = config.column_mappings['mx']
        my_i = config.column_mappings['my']
        mz_i = config.column_mappings['mz']
        # 读取并处理（支持 CSV chunksize 流式）

        # 生成输出路径（按模板与冲突策略）
        out_path = generate_output_path(file_path, output_dir, config)

        # 使用临时文件写入，最终原子替换为 out_path（避免并发或部分写入）
        temp_fd, temp_name = tempfile.mkstemp(prefix=out_path.name + '.', dir=str(out_path.parent), text=True)
        os.close(temp_fd)
        temp_out_path = Path(temp_name)

        first_chunk = True
        total_processed = 0
        total_dropped = 0
        total_non_numeric = 0

        # 块处理已提取为模块级函数 `process_df_chunk`

        # 如果是 CSV 且配置了 chunksize，则流式
        try:
            if use_chunks:
            reader = pd.read_csv(file_path, header=None, skiprows=config.skip_rows, chunksize=int(config.chunksize))
            try:
                first = next(reader)
            except StopIteration:
                logger.warning(f"文件 {file_path} 为空，跳过处理")
                return False

            # 使用首块校验列数
            num_cols = len(first.columns)
            # 验证列索引在首块中是否有效
            for key in REQUIRED_KEYS:
                col_idx = config.column_mappings.get(key)
                if col_idx is None:
                    raise ValueError(f"列映射缺失: '{key}' 未配置")
                if not (0 <= col_idx < num_cols):
                    raise ValueError(
                        f"列索引越界: column_mappings['{key}'] = {col_idx}, 但数据仅有 {num_cols} 列"
                    )

            # 处理首块
            proc, dropped, non_num, first_chunk = process_df_chunk(
                first, fx_i, fy_i, fz_i, mx_i, my_i, mz_i,
                calculator, config, out_path, first_chunk, logger
            )
            total_processed += proc
            total_dropped += dropped
            total_non_numeric += non_num

            # 处理剩余块
            for chunk in reader:
                proc, dropped, non_num, first_chunk = process_df_chunk(
                    chunk, fx_i, fy_i, fz_i, mx_i, my_i, mz_i,
                    calculator, config, temp_out_path, first_chunk, logger
                )
                total_processed += proc
                total_dropped += dropped
                total_non_numeric += non_num
            else:
                # 整表处理
                proc, dropped, non_num, first_chunk = process_df_chunk(
                    df, fx_i, fy_i, fz_i, mx_i, my_i, mz_i,
                    calculator, config, temp_out_path, first_chunk, logger
                )
            total_processed += proc
            total_dropped += dropped
            total_non_numeric += non_num

            # 在所有块写入完成后，原子替换到目标文件
            try:
                shutil.move(str(temp_out_path), str(out_path))
            except Exception:
                # 在某些平台上 move 不是原子操作，尝试 os.replace
                try:
                    os.replace(str(temp_out_path), str(out_path))
                except Exception as e:
                    logger.error("将临时文件移动到目标位置失败: %s", e, exc_info=True)
                    raise

            logger.info(f"处理完成: 已输出 {total_processed} 行；非数值总计 {total_non_numeric} 行；丢弃 {total_dropped} 行")
            logger.info(f"结果文件: {out_path}")
            return True

        except Exception as e:
            # 发生错误时尝试清理临时文件
            try:
                if temp_out_path.exists():
                    temp_out_path.unlink()
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

        # 重新加载计算器（每个进程独立），使用共享 helper 以统一错误信息
        project_data, calculator = load_project_calculator(project_config_path)

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
                cfg = resolve_file_format(str(file_path), cfg, registry_db=registry_db)
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

        success = process_single_file(file_path, calculator, cfg, output_dir)
        return (str(file_path), success, None)
    except Exception as e:
        # 捕获子进程中任何异常，返回失败信息以便主进程记录
        tb = traceback.format_exc()
        return (
            file_path_str,
            False,
            tb
        )
def run_batch_processing_v2(config_path: str, input_path: str, data_config: BatchConfig = None, registry_db: str = None, strict: bool = False):
    """增强版批处理主函数

    使用 `logger` 输出运行信息；若 `strict` 为 True，则在 registry/format 解析失败时中止。
    """
    logger = logging.getLogger('batch')
    logger.info("%s", "=" * 70)
    logger.info("MomentTransfer v2.0")
    logger.info("%s", "=" * 70)
    
    # 1. 加载配置（支持新版对等的 Source/Target 结构，向后兼容旧的 SourceCoordSystem）
    logger.info("[1/5] 加载几何配置: %s", config_path)
    try:
        project_data, calculator = load_project_calculator(config_path)
        logger.info("  ✓ 配置加载成功: %s", project_data.target_config.part_name)
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
            pattern = "*.csv"
            files = find_matching_files(str(input_path), pattern)
            logger.info("  自动模式下找到 %d 个匹配文件 (pattern=%s)", len(files), pattern)
            files_to_process = files
            output_dir = input_path
        else:
            pattern = input("  文件名匹配模式 (如 *.csv, data_*.xlsx): ").strip()
            if not pattern:
                pattern = "*.csv"
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
    
    # 若在外部通过 CLI 提供了并行参数，会由外层主函数处理；这里保持串行以便直接调用
    for i, file_path in enumerate(files_to_process, 1):
        logger.info("进度: [%d/%d]", i, len(files_to_process))
        # 在串行模式下也优先通过 registry 或侧车/目录解析每个文件的最终配置
        try:
            from src.cli_helpers import resolve_file_format
            cfg_local = resolve_file_format(str(file_path), data_config, registry_db=registry_db)
        except Exception:
            # 解析失败：记录并根据 strict 决定是否中止
            logger.warning("解析文件 %s 的格式失败，使用全局配置作为回退。", file_path)
            if strict and non_interactive_mode:
                logger.error("strict 模式下解析失败，终止批处理。")
                return
            cfg_local = data_config

        if process_single_file(file_path, calculator, cfg_local, output_dir):
            success_count += 1
    
    # 总结
    print("\n" + "=" * 70)
    print(f"批处理完成!")
    print(f"  成功: {success_count}/{len(files_to_process)}")
    print(f"  失败: {len(files_to_process) - success_count}/{len(files_to_process)}")
    print("=" * 70)


@click.command()
@click.option('-c', '--config', 'config', required=True, help='配置文件路径 (JSON)')
@click.option('-i', '--input', 'input_path', required=True, help='输入文件或目录路径')
@click.option('-p', '--pattern', default=None, help='文件匹配模式（目录模式下），如 "*.csv"')
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
@click.option('--registry-db', 'registry_db', default=None, help='SQLite registry 数据库路径（优先用于按文件映射格式）')
@click.option('--strict', 'strict', is_flag=True, help='非交互模式下 registry/format 解析失败时终止（默认回退到全局配置）')
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
    registry_db = cli_options.get('registry_db')
    strict = cli_options.get('strict')
    # 配置 logging（通过共享 helper）
    logger = configure_logging(log_file, verbose)

    # 读取数据格式配置
    if non_interactive:
        # 放宽约束：当未提供 global format_file，但提供了 registry_db 或依赖侧车/目录默认时，允许继续运行。
        if not format_file and not registry_db:
            logger.error('--non-interactive 模式下必须提供 --format-file 或 --registry-db 用于解析每个文件的格式')
            sys.exit(2)

        if format_file:
            try:
                data_config = load_format_from_file(format_file)
                logger.info(f'使用格式文件: {format_file}')
            except Exception as e:
                logger.exception('读取格式文件失败')
                sys.exit(3)
        else:
            # 未提供全局格式文件：使用默认 BatchConfig 作为全局基准，具体文件的最终配置由 registry / sidecar / 目录 默认覆盖
            data_config = BatchConfig()
            logger.info('非交互模式且未提供 --format-file，使用默认 BatchConfig 并依赖 registry/sidecar/目录默认进行每文件解析')
    else:
        # 交互式
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
                        pat_use = '*.csv'
                        logger.info("非交互模式：使用默认文件匹配模式 '*.csv'")
                    else:
                        pat_use = input('文件名匹配模式 (如 *.csv, default *.csv): ').strip() or '*.csv'
                files = find_matching_files(str(input_path_obj), pat_use)
                # 并行模式下不提供交互选择：自动处理所有匹配到的文件
                # 选择 all
                chosen_idxs = list(range(len(files)))
                files_to_process = [files[i] for i in chosen_idxs]
                output_dir = input_path_obj
            else:
                logger.error(f'无效的输入路径: {input_path}')
                sys.exit(4)

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
                for fp in files_to_process:
                    worker_args = {
                        'file_path': str(fp),
                        'config_dict': config_dict,
                        'project_config_path': config,
                        'output_dir': str(output_dir),
                        'registry_db': registry_db,
                        'strict': strict,
                    }
                    fut = exe.submit(_worker_process, worker_args)
                    futures[fut] = fp

                success_count = 0
                for fut in as_completed(futures):
                    fp = futures[fut]
                    try:
                        file_str, ok, err = fut.result()
                        if ok:
                            logger.info(f'处理成功: {file_str}')
                            success_count += 1
                        else:
                            logger.error(f'处理失败: {file_str} 错误: {err}')
                    except Exception as e:
                        logger.exception(f'任务异常: {fp}')

            logger.info(f'并行处理完成: 成功 {success_count}/{len(files_to_process)}')
            sys.exit(0 if success_count == len(files_to_process) else 1)

        else:
            # 串行模式：委托原有 run_batch_processing_v2（交互或已读取 data_config）
            run_batch_processing_v2(config, input_path, data_config, registry_db=registry_db, strict=strict)
            sys.exit(0)
    except Exception:
        logger.exception('批处理失败')
        sys.exit(5)


if __name__ == '__main__':
    main()