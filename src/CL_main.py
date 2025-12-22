import sys
import os
import json
import argparse

# 为了确保能导入同级模块，把父目录加入路径 (处理 Python 导入路径问题)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# TODO: 考虑改用 package 运行方式（`python -m src.CL_main`）或调整项目的安装/入口点以避免修改 sys.path。

from src.data_loader import load_data
from src.physics import AeroCalculator

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='力矩坐标变换计算工具',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    parser.add_argument(
        '-i', '--input',
        default=os.path.join(base_dir, 'data', 'input.json'),
        help='输入配置文件路径 (默认: data/input.json)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default=os.path.join(base_dir, 'data', 'output_result.json'),
        help='输出结果文件路径 (默认: data/output_result.json)'
    )
    
    parser.add_argument(
        '--force',
        type=float,
        nargs=3,
        metavar=('FX', 'FY', 'FZ'),
        help='输入力 [示例: --force 100 0 1000]'
    )
    
    parser.add_argument(
        '--moment',
        type=float,
        nargs=3,
        metavar=('MX', 'MY', 'MZ'),
        help='输入力矩 [示例: --moment 0 50 0]'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细输出'
    )
    
    return parser.parse_args()


def main():
    # 解析命令行参数
    args = parse_arguments()
    
    input_file = args.input
    output_file = args.output

    print("[开始] 运行力矩变换程序...")
    print("[读取] 配置文件: %s" % input_file)

    # 2. 加载配置
    try:
        project_data = load_data(input_file)
    except Exception as e:
        print("[错误] 初始化失败: %s" % e)
        return

    # 3. 初始化物理计算核心
    calculator = AeroCalculator(project_data)
    print("[计算] 坐标系矩阵构建完成。")
    print("    - 源坐标系原点: %s" % project_data.source_coord.origin)
    print("    - 目标力矩中心: %s" % project_data.target_config.moment_center)

    # ---------------------------------------------------------
    # 输入数据：优先使用命令行参数，否则使用默认示例值
    # ---------------------------------------------------------
    if args.force and args.moment:
        raw_forces = args.force
        raw_moments = args.moment
        if args.verbose:
            print("[\u6a21\u5f0f] \u4f7f\u7528\u547d\u4ee4\u884c\u6307\u5b9a\u7684\u529b\u548c\u529b\u77e9")
    else:
        # 默认示例输入
        raw_forces = [100.0, 0.0, 1000.0]
        raw_moments = [0.0, 50.0, 0.0]
        if args.verbose:
            print("[\u6a21\u5f0f] \u4f7f\u7528\u9ed8\u8ba4\u793a\u4f8b\u8f93\u5165")

    print("-" * 40)
    print("[输入] 原始数据 (Source Frame):")
    print("    Force : %s" % raw_forces)
    print("    Moment: %s" % raw_moments)

    # 4. 执行核心计算
    result = calculator.process_frame(raw_forces, raw_moments)

    # 5. 输出结果
    print("-" * 40)
    print("[完成] 计算完成 (Target Frame):")
    
    # 格式化输出，保留4位小数
    def fmt(lst): return [round(x, 4) for x in lst]

    print("    Force (N)   : %s" % fmt(result.force_transformed))
    print("    Moment (N*m): %s" % fmt(result.moment_transformed))
    print("-" * 40)
    print("[系数] 气动系数 (Coefficients):")
    print("    Force [Cx, Cy, Cz] : %s" % fmt(result.coeff_force))
    print("    Moment [Cl, Cm, Cn]: %s" % fmt(result.coeff_moment))
    print("-" * 40)

    # 6. 保存结果到文件
    output_data = {
        "meta": {
            "part_name": project_data.target_config.part_name,
            "q": project_data.target_config.q
        },
        "input": {
            "force": raw_forces,
            "moment": raw_moments
        },
        "output": {
            "force_transformed": result.force_transformed,
            "moment_transformed": result.moment_transformed,
            "coeff_force": result.coeff_force,
            "coeff_moment": result.coeff_moment
        }
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4)
    
    print("[保存] 结果已保存至: %s" % output_file)

if __name__ == "__main__":
    main()