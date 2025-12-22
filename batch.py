import sys
import os
import argparse
import pandas as pd
import numpy as np
from datetime import datetime

# 假设我们在项目根目录运行，使用标准包导入
from src.data_loader import load_data
from src.physics import AeroCalculator


def run_batch_processing(config_path, input_csv, output_csv):
    print(f"--- 启动批处理模式 ---")

    # 1. 加载配置
    print(f"[1/4] 加载几何配置: {config_path}")
    try:
        project_data = load_data(config_path)
        calculator = AeroCalculator(project_data)
    except Exception as e:
        print(f"[错误] 配置加载失败: {e}")
        return

    # 2. 读取 Excel/CSV 数据
    print(f"[2/4] 读取工况数据: {input_csv}")
    try:
        if input_csv.endswith('.csv'):
            df = pd.read_csv(input_csv)
        elif input_csv.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(input_csv)
        else:
            raise ValueError("不支持的文件格式，请使用 .csv 或 .xlsx")
    except Exception as e:
        print(f"[错误] 数据文件读取失败: {e}")
        return

    # 3. 提取数据列 (列名映射)
    # 假设用户列名可能是 'Fx', 'Force_X', 'FX (N)' 等，这里做一个简单的模糊匹配或强制指定
    # 简单起见，我们要求输入文件必须包含以下列头(不区分大小写)
    required_cols = {
        'fx': ['fx', 'force_x', 'f_x'],
        'fy': ['fy', 'force_y', 'f_y'],
        'fz': ['fz', 'force_z', 'f_z'],
        'mx': ['mx', 'moment_x', 'm_x'],
        'my': ['my', 'moment_y', 'm_y'],
        'mz': ['mz', 'moment_z', 'm_z']
    }

    # 辅助函数：找列名
    col_map = {}
    df_cols_lower = [c.lower() for c in df.columns]

    for key, candidates in required_cols.items():
        found = False
        for cand in candidates:
            if cand in df_cols_lower:
                real_col_name = df.columns[df_cols_lower.index(cand)]
                col_map[key] = real_col_name
                found = True
                break
        if not found:
            print(f"[错误] 找不到列: {key} (尝试过: {candidates})")
            return

    print(f"    -> 识别到 {len(df)} 个工况")

    # 提取 Numpy 数组
    forces_in = df[[col_map['fx'], col_map['fy'], col_map['fz']]].values
    moments_in = df[[col_map['mx'], col_map['my'], col_map['mz']]].values

    # 4. 核心计算 (向量化)
    print(f"[3/4] 执行物理计算...")
    results = calculator.process_batch(forces_in, moments_in)

    # 5. 合并结果
    # 处理输出路径：如果用户传入的是目录，则在该目录下使用源文件名+时间戳作为输出文件名
    # 如果用户传入的是文件，则直接使用该文件，但仅接受 .csv 或 .xlsx
    print(f"[4/4] 写入结果: {output_csv}")

    # 判定输出目标是目录的几种情况
    is_dir = False
    if os.path.isdir(output_csv) or output_csv.endswith(os.sep) or output_csv.endswith('/') or output_csv.endswith('\\'):
        is_dir = True
    # 如果是目录但不存在，尝试创建目录
    if is_dir and not os.path.exists(output_csv):
        try:
            os.makedirs(output_csv, exist_ok=True)
        except Exception as e:
            print(f"[错误] 无法创建输出目录: {e}")
            return

    if is_dir:
        src_basename = os.path.splitext(os.path.basename(input_csv))[0]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(output_csv, f"{src_basename}_{timestamp}.csv")
        out_ext = '.csv'
    else:
        output_file = output_csv
        out_ext = os.path.splitext(output_file)[1].lower()

    # 仅支持 csv 和 excel 输出
    if out_ext not in ['.csv', '.xls', '.xlsx']:
        print("[错误] 不支持的输出格式。仅支持 .csv 或 .xlsx，请提供正确的文件名或目录。")
        return

    # 添加新列
    suffix = "_new"
    df[f'Fx{suffix}'] = results['force_transformed'][:, 0]
    df[f'Fy{suffix}'] = results['force_transformed'][:, 1]
    df[f'Fz{suffix}'] = results['force_transformed'][:, 2]

    df[f'Mx{suffix}'] = results['moment_transformed'][:, 0]
    df[f'My{suffix}'] = results['moment_transformed'][:, 1]
    df[f'Mz{suffix}'] = results['moment_transformed'][:, 2]

    df['Cx'] = results['coeff_force'][:, 0]
    df['Cy'] = results['coeff_force'][:, 1]
    df['Cz'] = results['coeff_force'][:, 2]

    df['Cl'] = results['coeff_moment'][:, 0]
    df['Cm'] = results['coeff_moment'][:, 1]
    df['Cn'] = results['coeff_moment'][:, 2]

    # 保存文件，捕获并以简洁信息提示异常
    try:
        if out_ext == '.csv':
            df.to_csv(output_file, index=False)
        else:
            # 对于 excel，使用 to_excel
            df.to_excel(output_file, index=False)
    except Exception as e:
        print(f"[错误] 写入输出文件失败：{e}")
        return

    print(f"--- 完成: {output_file} ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="气动载荷批处理工具")
    parser.add_argument('-c', '--config', required=True, help="input.json 配置文件路径")
    parser.add_argument('-i', '--input', required=True, help="输入数据文件 (.csv/.xlsx)")
    parser.add_argument('-o', '--output', required=True, help="输出结果文件路径")

    args = parser.parse_args()

    run_batch_processing(args.config, args.input, args.output)