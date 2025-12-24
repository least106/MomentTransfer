import argparse
import pandas as pd

from datetime import datetime
from pathlib import Path
import fnmatch

from src.data_loader import load_data
from src.physics import AeroCalculator


class BatchConfig:
    """批处理配置类"""
    def __init__(self):
        self.skip_rows = 0
        self.column_mappings = {
            'alpha': None,  # 迎角列
            'fx': None,     # 轴向力
            'fy': None,     # 侧向力
            'fz': None,     # 法向力
            'mx': None,     # 滚转力矩
            'my': None,     # 俯仰力矩
            'mz': None      # 偏航力矩
        }
        self.passthrough_columns = []  # 需要原样输出的列


def get_user_file_format():
    """交互式获取用户数据格式配置"""
    print("\n=== 数据格式配置 ===")
    config = BatchConfig()
    
    # 跳过行数
    skip_input = input("需要跳过的表头行数 (默认0): ").strip()
    if skip_input:
        try:
            config.skip_rows = int(skip_input)
        except ValueError:
            print("[警告] 无效输入，使用默认值0")
    
    print("\n请指定数据列位置 (从0开始计数，留空表示该列不存在):")
    
    # 可选的迎角列
    alpha_col = input("  迎角 Alpha 列号: ").strip()
    if alpha_col:
        try:
            config.column_mappings['alpha'] = int(alpha_col)
        except ValueError:
            pass
    
    # 必需的力和力矩列
    required_mappings = {
        'fx': '轴向力 Fx',
        'fy': '侧向力 Fy', 
        'fz': '法向力 Fz',
        'mx': '滚转力矩 Mx',
        'my': '俯仰力矩 My',
        'mz': '偏航力矩 Mz'
    }
    
    for key, label in required_mappings.items():
        while True:
            col_input = input(f"  {label} 列号 (必需): ").strip()
            if col_input:
                try:
                    config.column_mappings[key] = int(col_input)
                    break
                except ValueError:
                    print("    [错误] 请输入有效的列号")
            else:
                print("    [错误] 此列为必需项")
    
    # 需要保留的列
    print("\n需要原样输出的其他列 (用逗号分隔列号，如: 0,1,2):")
    passthrough = input("  列号: ").strip()
    if passthrough:
        try:
            config.passthrough_columns = [int(x.strip()) for x in passthrough.split(',')]
        except ValueError:
            print("[警告] 格式错误，将不保留额外列")
    
    return config


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
                idxs.extend(range(a_i, b_i + 1))
            except Exception:
                continue
        else:
            try:
                idxs.append(int(part) - 1)
            except Exception:
                continue
    return sorted(set(i for i in idxs if 0 <= i < n))


def read_data_with_config(file_path: str, config: BatchConfig) -> pd.DataFrame:
    """根据配置读取数据文件"""
    # 读取文件（跳过指定行数）
    ext = Path(file_path).suffix.lower()
    if ext == '.csv':
        df = pd.read_csv(file_path, header=None, skiprows=config.skip_rows)
    elif ext in {'.xls', '.xlsx', '.xlsm', '.xlsb', '.odf', '.ods', '.odt'}:
        df = pd.read_excel(file_path, header=None, skiprows=config.skip_rows)
    else:
        raise ValueError(
            f"不支持的文件类型: '{file_path}'. 仅支持 CSV (.csv) 和 Excel "
            f"(.xls, .xlsx, .xlsm, .xlsb, .odf, .ods, .odt) 文件。"
        )
    
    return df


def process_single_file(file_path: Path, calculator: AeroCalculator, 
                       config: BatchConfig, output_dir: Path) -> bool:
    """处理单个文件"""
    try:
        # 先根据配置读取数据文件
        df = read_data_with_config(file_path, config)
        # 校验列索引是否在有效范围内
        num_cols = len(df.columns)
        required_keys = ['fx', 'fy', 'fz', 'mx', 'my', 'mz']
        for key in required_keys:
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

        forces_df = df.iloc[:, [fx_i, fy_i, fz_i]].apply(pd.to_numeric, errors='coerce')
        moments_df = df.iloc[:, [mx_i, my_i, mz_i]].apply(pd.to_numeric, errors='coerce')

        # 检测并提示非数值行数量，然后以0.0替代
        nans_forces = forces_df.isna().any(axis=1).sum()
        nans_moments = moments_df.isna().any(axis=1).sum()
        if nans_forces or nans_moments:
            print(f"  [警告] 在文件 {Path(file_path).name} 中检测到 {nans_forces} 行力数据和 {nans_moments} 行力矩数据包含非数值，已将其替换为0.0。")

        forces = forces_df.fillna(0.0).to_numpy(dtype=float)
        moments = moments_df.fillna(0.0).to_numpy(dtype=float)

        # 执行计算
        print("  执行坐标变换...")
        results = calculator.process_batch(forces, moments)
        
        # 构建输出DataFrame
        output_df = pd.DataFrame()
        
        # 1. 保留原样输出的列
        for col_idx in config.passthrough_columns:
            if col_idx < len(df.columns):
                output_df[f'Col_{col_idx}'] = df.iloc[:, col_idx]
        
        # 2. 如果有迎角列，也保留
        if config.column_mappings['alpha'] is not None:
            alpha_idx = config.column_mappings['alpha']
            if alpha_idx < len(df.columns):
                output_df['Alpha'] = df.iloc[:, alpha_idx]
        
        # 3. 添加变换后的力和力矩
        output_df['Fx_new'] = results['force_transformed'][:, 0]
        output_df['Fy_new'] = results['force_transformed'][:, 1]
        output_df['Fz_new'] = results['force_transformed'][:, 2]
        
        output_df['Mx_new'] = results['moment_transformed'][:, 0]
        output_df['My_new'] = results['moment_transformed'][:, 1]
        output_df['Mz_new'] = results['moment_transformed'][:, 2]
        
        # 4. 添加无量纲系数
        output_df['Cx'] = results['coeff_force'][:, 0]
        output_df['Cy'] = results['coeff_force'][:, 1]
        output_df['Cz'] = results['coeff_force'][:, 2]
        
        output_df['Cl'] = results['coeff_moment'][:, 0]
        output_df['Cm'] = results['coeff_moment'][:, 1]
        output_df['Cn'] = results['coeff_moment'][:, 2]
        
        # 保存结果
        # 确保输出目录存在
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = output_dir / f"{file_path.stem}_result_{timestamp}.csv"
        output_df.to_csv(output_file, index=False)
        
        print(f"  ✓ 完成，结果保存至: {output_file}")
        return True
        
    except Exception as e:
        print(f"  ✗ 处理失败: {str(e)}")
        return False


def run_batch_processing_v2(config_path: str, input_path: str):
    """增强版批处理主函数"""
    print("=" * 70)
    print("气动载荷坐标变换批处理工具 v2.0")
    print("=" * 70)
    
    # 1. 加载配置（支持新版对等的 Source/Target 结构，向后兼容旧的 SourceCoordSystem）
    print(f"\n[1/5] 加载几何配置: {config_path}")
    try:
        project_data = load_data(config_path)
        calculator = AeroCalculator(project_data)
        print(f"  ✓ 配置加载成功: {project_data.target_config.part_name}")
    except Exception as e:
        print(f"  ✗ 配置加载失败: {e}\n  提示: 请检查 JSON 是否包含 Target 的 CoordSystem/MomentCenter/Q/S 或使用 GUI/creator.py 生成兼容的配置。")
        return
    
    # 2. 获取数据格式配置
    print(f"\n[2/5] 配置数据格式")
    data_config = get_user_file_format()
    
    # 3. 确定输入文件列表
    print(f"\n[3/5] 扫描输入文件")
    input_path = Path(input_path)
    files_to_process = []
    
    if input_path.is_file():
        print(f"  模式: 单文件处理")
        files_to_process = [input_path]
        output_dir = input_path.parent
    elif input_path.is_dir():
        print(f"  模式: 目录批处理")
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
    confirm = input("  确认开始处理? (y/n): ").strip().lower()
    if confirm != 'y':
        print("  已取消")
        return
    
    # 5. 批量处理
    print(f"\n[5/5] 开始批量处理...")
    success_count = 0
    
    for i, file_path in enumerate(files_to_process, 1):
        print(f"\n进度: [{i}/{len(files_to_process)}]")
        if process_single_file(file_path, calculator, data_config, output_dir):
            success_count += 1
    
    # 总结
    print("\n" + "=" * 70)
    print(f"批处理完成!")
    print(f"  成功: {success_count}/{len(files_to_process)}")
    print(f"  失败: {len(files_to_process) - success_count}/{len(files_to_process)}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MomentTransfer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  单文件处理:
    python batch_v2.py -c config.json -i data.csv
  
  目录批处理:
    python batch_v2.py -c config.json -i ./data_folder/
        """
    )
    
    parser.add_argument('-c', '--config', required=True, help="配置文件路径 (JSON)")
    parser.add_argument('-i', '--input', required=True, help="输入文件或目录路径")
    
    args = parser.parse_args()
    
    run_batch_processing_v2(args.config, args.input)