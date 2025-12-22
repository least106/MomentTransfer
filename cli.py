import os
import argparse
import sys

# 标准导入 (因为 cli.py 在项目根目录，Python 会自动识别 src 包)
from src import load_data, AeroCalculator


def main():
    """CLI 主入口函数"""

    # 1. 设置默认路径
    # 获取当前脚本所在目录 (AeroTransform/)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.join(base_dir, 'data', 'input.json')
    default_output = os.path.join(base_dir, 'data', 'output_result.json')

    # 2. 参数解析
    parser = argparse.ArgumentParser(
        description='气动载荷坐标变换工具 (Single Point CLI)',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('-i', '--input', default=default_config, help='配置文件路径 (JSON)')
    parser.add_argument('-o', '--output', default=default_output, help='结果输出路径 (JSON)')

    # 允许用户在命令行直接输入 F 和 M
    parser.add_argument('--force', type=float, nargs=3, metavar=('Fx', 'Fy', 'Fz'),
                        help='输入力向量 (例如: --force 100 0 -50)')
    parser.add_argument('--moment', type=float, nargs=3, metavar=('Mx', 'My', 'Mz'),
                        help='输入力矩向量 (例如: --moment 0 500 0)')

    args = parser.parse_args()

    # 3. 交互式输入 (如果没有在命令行提供参数)
    raw_forces = args.force
    raw_moments = args.moment

    if raw_forces is None:
        print("\n--- 请输入载荷数据 (Source Frame) ---")
        try:
            f_str = input("Force  [Fx, Fy, Fz] (默认 0,0,0): ")
            raw_forces = [float(x) for x in f_str.split(",")] if f_str.strip() else [0.0, 0.0, 0.0]
        except ValueError:
            print("[错误] 格式不正确，请使用逗号分隔数字。")
            return

    if raw_moments is None:
        try:
            m_str = input("Moment [Mx, My, Mz] (默认 0,0,0): ")
            raw_moments = [float(x) for x in m_str.split(",")] if m_str.strip() else [0.0, 0.0, 0.0]
        except ValueError:
            print("[错误] 格式不正确。")
            return

    # 4. 执行计算
    print(f"\n[1] 加载配置: {args.input}")
    try:
        project_data = load_data(args.input)
        calculator = AeroCalculator(project_data)
    except Exception as e:
        print(f"[致命错误] 无法加载配置: {e}")
        return

    print("[2] 执行计算...")
    # 注意：这里调用的是 physics.py 中的 process_frame (单点包装器)
    result = calculator.process_frame(raw_forces, raw_moments)

    # 5. 打印结果
    print("-" * 40)
    print(f"输入载荷: F={raw_forces}, M={raw_moments}")
    print("-" * 40)
    print(f"转换结果 (Target: {project_data.target_config.part_name})")

    def fmt(lst):
        return [round(x, 4) for x in lst]

    print(f"Force (N)    : {fmt(result.force_transformed)}")
    print(f"Moment (N*m) : {fmt(result.moment_transformed)}")
    print("-" * 40)
    print(f"气动系数:")
    print(f"Force [Cx,Cy,Cz] : {fmt(result.coeff_force)}")
    print(f"Moment [Cl,Cm,Cn]: {fmt(result.coeff_moment)}")
    print("-" * 40)

    # (可选) 这里可以添加将单点结果写入 output.json 的逻辑
    # 为了保持代码简洁，这里仅做打印演示


if __name__ == "__main__":
    main()