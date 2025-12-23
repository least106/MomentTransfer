import sys
import os
import argparse
import pandas as pd
import numpy as np
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


def read_data_with_config(file_path: str, config: BatchConfig) -> pd.DataFrame:
    """根据配置读取数据文件"""
    # 读取文件（跳过指定行数）
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path, header=None, skiprows=config.skip_rows)
    else:
        df = pd.read_excel(file_path, header=None, skiprows=config.skip_rows)
    
    return df


def process_single_file(file_path: Path, calculator: AeroCalculator, 
                       config: BatchConfig, output_dir: Path) -> bool:
    """处理单个文件"""
    try:
        print(f"\n处理文件: {file_path.name}")
        
        # 读取数据
        df = read_data_with_config(str(file_path), config)
        print(f"  读取到 {len(df)} 行数据")
        
        # 提取力和力矩数据
        forces = df[[
            config.column_mappings['fx'],
            config.column_mappings['fy'],
            config.column_mappings['fz']
        ]].values
        
        moments = df[[
            config.column_mappings['mx'],
            config.column_mappings['my'],
            config.column_mappings['mz']
        ]].values
        
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
        
        files_to_process = find_matching_files(str(input_path), pattern)
        print(f"  找到 {len(files_to_process)} 个匹配文件")
        
        if not files_to_process:
            print("  [错误] 未找到匹配的文件")
            return
        
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
        description="气动载荷批处理工具 v2.0 - 支持灵活的数据格式",
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