import click
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
import numpy as np

from datetime import datetime
from pathlib import Path
import fnmatch

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
            # 自动添加序号后缀直到不冲突
            base = out_path.stem
            suf = out_path.suffix
            for i in range(1, MAX_FILE_COLLISION_RETRIES + 1):
                candidate = output_dir / f"{base}_{i}{suf}"
                if not candidate.exists():
                    out_path = candidate
                    break
            else:
                raise IOError(f"无法为输出文件找到不冲突的文件名（尝试 {MAX_FILE_COLLISION_RETRIES} 次）: {out_path}")

    # 最后检查目录是否可写
    try:
        test_path = out_path.parent / (out_path.stem + ".__writetest__")
        with open(test_path, 'w', encoding='utf-8') as _:
            pass
        test_path.unlink()
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
    # 先显式复制切片以避免链式赋值警告
    forces_df = chunk_df.iloc[:, [fx_i, fy_i, fz_i]].copy()
    for col in forces_df.columns:
        forces_df[col] = pd.to_numeric(forces_df[col], errors='coerce')

    moments_df = chunk_df.iloc[:, [mx_i, my_i, mz_i]].copy()
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
        forces = forces_df.loc[valid_idx].fillna(0.0).to_numpy(dtype=float)
        moments = moments_df.loc[valid_idx].fillna(0.0).to_numpy(dtype=float)
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
    out_df.to_csv(out_path, index=False, mode=mode, header=header, encoding='utf-8')

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
        chunk_size = None
        if config.chunksize:
            try:
                chunk_size = int(config.chunksize)
            except (ValueError, TypeError):
                chunk_size = None

        ext = Path(file_path).suffix.lower()
        use_chunks = (ext == '.csv') and chunk_size and chunk_size > 0

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

        first_chunk = True
        total_processed = 0
        total_dropped = 0
        total_non_numeric = 0

        # 块处理已提取为模块级函数 `process_df_chunk`

        # 如果是 CSV 且配置了 chunksize，则流式
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
                    calculator, config, out_path, first_chunk, logger
                )
                total_processed += proc
                total_dropped += dropped
                total_non_numeric += non_num
        else:
            # 整表处理
            proc, dropped, non_num, first_chunk = process_df_chunk(
                df, fx_i, fy_i, fz_i, mx_i, my_i, mz_i,
                calculator, config, out_path, first_chunk, logger
            )
            total_processed += proc
            total_dropped += dropped
            total_non_numeric += non_num

        logger.info(f"处理完成: 已输出 {total_processed} 行；非数值总计 {total_non_numeric} 行；丢弃 {total_dropped} 行")
        logger.info(f"结果文件: {out_path}")
        return True
        
    except Exception as e:
        logger.error(f"  ✗ 处理失败: {str(e)}", exc_info=True)
        return False


def _worker_process(args_tuple):
    """在子进程中运行单个文件的处理（用于并行）。

    args_tuple: (file_path_str, config_dict, config_path, output_dir_str)
    - config_dict: dict representation of BatchConfig (keys: skip_rows, column_mappings, passthrough_columns)
    - config_path: path to JSON config for AeroCalculator (project geometry)
    """
    try:
        # 保证在任何异常分支中都能报告文件名：优先读取 args_tuple[0]
        file_path_str = str(args_tuple[0]) if args_tuple else 'unknown'
        # unpack args (支持新增的 registry_db 可选项)
        if len(args_tuple) == 4:
            file_path_str, config_dict, project_config_path, output_dir_str = args_tuple
            registry_db = None
        else:
            file_path_str, config_dict, project_config_path, output_dir_str, registry_db = args_tuple
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
        try:
            from src.cli_helpers import resolve_file_format
            if registry_db:
                cfg = resolve_file_format(str(file_path), cfg, registry_db=registry_db)
        except Exception as e:
            # 不中断处理，但记录警告日志以便调试解析失败原因
            logging.getLogger(__name__).warning(
                "使用registry_db\"%s\"解析\"%s\"的文件格式失败，错误：%s",
                registry_db, str(file_path), e
            )

        success = process_single_file(file_path, calculator, cfg, output_dir)
        return (str(file_path), success, None)
    except Exception as e:
        # 捕获子进程中任何异常，返回失败信息以便主进程记录
        return (
            file_path_str,
            False,
            str(e)
        )
def run_batch_processing_v2(config_path: str, input_path: str, data_config: BatchConfig = None, registry_db: str = None):
    """增强版批处理主函数"""
    print("=" * 70)
    print("MomentTransfer v2.0")
    print("=" * 70)
    
    # 1. 加载配置（支持新版对等的 Source/Target 结构，向后兼容旧的 SourceCoordSystem）
    print(f"\n[1/5] 加载几何配置: {config_path}")
    try:
        project_data, calculator = load_project_calculator(config_path)
        print(f"  ✓ 配置加载成功: {project_data.target_config.part_name}")
    except Exception as e:
        print(f"  ✗ 配置加载失败: {e}\n  提示: 请检查 JSON 是否包含 Target 的 CoordSystem/MomentCenter/Q/S 或使用 GUI/creator.py 生成兼容的配置。")
        return
    
    # 2. 获取数据格式配置（交互或非交互）
    print(f"\n[2/5] 配置数据格式")
    # 若外部已提供 data_config（例如非交互模式），则使用之
    if data_config is None:
        data_config = get_user_file_format()
    
    # 3. 确定输入文件列表
    print(f"\n[3/5] 扫描输入文件")
    input_path = Path(input_path)
    files_to_process = []
    
    # 若提供了 data_config 且同时提供了 registry_db，则视为非交互自动模式，避免使用 input() 阶段
    auto_mode = (data_config is not None and registry_db is not None)

    if input_path.is_file():
        print(f"  模式: 单文件处理")
        files_to_process = [input_path]
        output_dir = input_path.parent
    elif input_path.is_dir():
        print(f"  模式: 目录批处理")
        if auto_mode:
            # 非交互自动模式：使用默认模式匹配所有 CSV 文件并全部处理
            pattern = "*.csv"
            files = find_matching_files(str(input_path), pattern)
            print(f"  自动模式下找到 {len(files)} 个匹配文件 (pattern={pattern})")
            files_to_process = files
            output_dir = input_path
        else:
            pattern = input("  文件名匹配模式 (如 *.csv, data_*.xlsx): ").strip()
            if not pattern:
                pattern = "*.csv"
            files = find_matching_files(str(input_path), pattern)
            print(f"  找到 {len(files)} 个匹配文件:")
            for i, fp in enumerate(files, start=1):
                print(f"    {i}. {fp.name}")

            sel = input("  选择要处理的文件（默认 all）: ").strip().lower()
            chosen_idxs = parse_selection(sel, len(files))
            if not chosen_idxs:
                print("  未选择有效文件，已取消")
                return

            files_to_process = [files[i] for i in chosen_idxs]
            # 输出目录默认为输入目录
            output_dir = input_path
    else:
        print(f"  [错误] 无效的输入路径: {input_path}")
        return
    
    # 4. 确认处理
    print(f"\n[4/5] 准备处理 {len(files_to_process)} 个文件")
    print(f"  输出目录: {output_dir}")
    # 若自动模式则默认确认
    if not auto_mode:
        confirm = input("  确认开始处理? (y/n): ").strip().lower()
        if confirm != 'y':
            print("  已取消")
            return
    
    # 5. 批量处理
    print(f"\n[5/5] 开始批量处理...")
    success_count = 0
    
    # 若在外部通过 CLI 提供了并行参数，会由外层主函数处理；这里保持串行以便直接调用
    for i, file_path in enumerate(files_to_process, 1):
        print(f"\n进度: [{i}/{len(files_to_process)}]")
        # 在串行模式下也优先通过 registry 或侧车/目录解析每个文件的最终配置
        try:
            from src.cli_helpers import resolve_file_format
            cfg_local = resolve_file_format(str(file_path), data_config, registry_db=registry_db)
        except Exception:
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
def main(config, input_path, pattern, format_file, non_interactive, log_file, verbose, workers, chunksize, overwrite, name_template, timestamp_format, treat_non_numeric, sample_rows, registry_db):
    """批处理入口（click 版）"""
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
                logger.info(f'找到 {len(files)} 个匹配文件')
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
                    fut = exe.submit(_worker_process, (str(fp), config_dict, config, str(output_dir), registry_db))
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
            run_batch_processing_v2(config, input_path, data_config, registry_db=registry_db)
            sys.exit(0)
    except Exception:
        logger.exception('批处理失败')
        sys.exit(5)


if __name__ == '__main__':
    main()