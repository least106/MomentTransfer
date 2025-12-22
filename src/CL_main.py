import sys
import os
import json

# 为了确保能导入同级模块，把父目录加入路径 (处理 Python 导入路径问题)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# TODO: 考虑改用 package 运行方式（`python -m src.CL_main`）或调整项目的安装/入口点以避免修改 sys.path。
# TODO: 增加 argparse 支持以允许从命令行传入 input/output 文件路径与日志级别，并添加集成测试覆盖。

from src.data_loader import load_data
from src.physics import AeroCalculator

def main():
    # 1. 定义文件路径
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_file = os.path.join(base_dir, 'data', 'input.json')
    output_file = os.path.join(base_dir, 'data', 'output_result.json')

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
    # 模拟输入数据 (在真实项目中，这里会是一个循环，读取CSV文件)
    # 假设这是天平测得的一组原始数据
    # Force: 100N 阻力, 0N 侧力, 1000N 升力
    # Moment: 0, 50, 0
    # ---------------------------------------------------------
    # TODO: 现在这里使用了硬编码的示例输入。后续应改为从文件、STDIN 或测试钩子读取输入数据，并添加可重复的集成测试。
    raw_forces = [100.0, 0.0, 1000.0]
    raw_moments = [0.0, 50.0, 0.0]

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