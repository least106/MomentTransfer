import os
import json
import click


# 标准导入 (因为 cli.py 在项目根目录，Python 会自动识别 src 包)
from src.data_loader import load_data
from src.physics import AeroCalculator


@click.command()
@click.option('-i', '--input', 'input_path', default=None,
              help='配置文件路径 (JSON)，默认使用项目 data/input.json')
@click.option('-o', '--output', 'output_path', default=None,
              help='结果输出路径 (JSON)，若不提供则不写文件')
@click.option('--force', type=(float, float, float), default=None,
              help='输入力向量 (例如: --force 100 0 -50)')
@click.option('--moment', type=(float, float, float), default=None,
              help='输入力矩向量 (例如: --moment 0 500 0)')
def main(input_path, output_path, force, moment):
    """气动载荷坐标变换工具（click CLI）

    支持非交互模式通过 `--force` 与 `--moment` 指定载荷。
    自动生成帮助文档（`--help`）。
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.join(base_dir, 'data', 'input.json')

    cfg_path = input_path or default_config

    raw_forces = list(force) if force is not None else None
    raw_moments = list(moment) if moment is not None else None

    if raw_forces is None:
        click.echo('\n--- 请输入载荷数据 (Source Frame) ---')
        f_str = click.prompt('Force [Fx, Fy, Fz] (逗号分隔，默认 0,0,0)', default='0,0,0')
        try:
            raw_forces = [float(x) for x in f_str.split(',')]
        except ValueError:
            click.echo('[错误] 格式不正确，请使用逗号分隔数字。')
            raise click.Abort()

    if raw_moments is None:
        m_str = click.prompt('Moment [Mx, My, Mz] (逗号分隔，默认 0,0,0)', default='0,0,0')
        try:
            raw_moments = [float(x) for x in m_str.split(',')]
        except ValueError:
            click.echo('[错误] 格式不正确。')
            raise click.Abort()

    click.echo(f"\n[1] 加载配置: {cfg_path}")
    try:
        project_data = load_data(cfg_path)
        calculator = AeroCalculator(project_data)
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        click.echo(f"[致命错误] 无法加载配置: {e}")
        click.echo("提示: 配置文件应包含对等的 'Source' 与 'Target' 节点，或至少包含旧格式的 'SourceCoordSystem' 与 'Target'。可使用 creator.py 生成兼容配置。")
        raise click.Abort()

    click.echo('[2] 执行计算...')
    result = calculator.process_frame(raw_forces, raw_moments)

    click.echo('-' * 40)
    click.echo(f"输入载荷: F={raw_forces}, M={raw_moments}")
    click.echo('-' * 40)
    click.echo(f"转换结果 (Target: {project_data.target_config.part_name})")

    def round_values(values):
        return [round(x, 4) for x in values]

    click.echo(f"Force (N)    : {round_values(result.force_transformed)}")
    click.echo(f"Moment (N*m) : {round_values(result.moment_transformed)}")
    click.echo('-' * 40)
    click.echo(f"气动系数:")
    click.echo(f"Force [Cx,Cy,Cz] : {round_values(result.coeff_force)}")
    click.echo(f"Moment [Cl,Cm,Cn]: {round_values(result.coeff_moment)}")
    click.echo('-' * 40)

    if output_path:
        out_data = {
            "input": {"force": raw_forces, "moment": raw_moments},
            "target": getattr(project_data.target_config, "part_name", None),
            "result": {
                "force_transformed": result.force_transformed,
                "moment_transformed": result.moment_transformed,
                "coeff_force": result.coeff_force,
                "coeff_moment": result.coeff_moment,
            },
        }

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                json.dump(out_data, fh, ensure_ascii=False, indent=2)
            click.echo(f"已将结果写入: {output_path}")
        except OSError as e:
            click.echo(f"[警告] 无法将结果写入 {output_path}: {e}")


if __name__ == "__main__":
    main()