import os
import json
import sys
import click
from typing import Any


# 标准导入 (因为 cli.py 在项目根目录，Python 会自动识别 src 包)
from src.cli_helpers import load_project_calculator, configure_logging
from src.registry_cli import registry as registry_cmd


def _make_serializable(v: Any) -> Any:
    """将 numpy/其它可转为 list 的对象转为 Python 原生结构，便于 json.dump。"""
    try:
        if hasattr(v, 'tolist'):
            return v.tolist()
    except Exception:
        pass
    return v


def prompt_vector(label: str, default=(0.0, 0.0, 0.0)) -> list:
    """交互式提示用户输入三元向量，支持逗号或空格分隔，出错时可重试。"""
    def fmt_def(d):
        return ",".join(str(x) for x in d)

    while True:
        s = click.prompt(f"{label} (逗号或空格分隔，默认 {fmt_def(default)})", default=fmt_def(default))
        # 支持逗号或空格分隔
        parts = [p for p in s.replace(',', ' ').split() if p]
        if len(parts) != 3:
            click.echo('[错误] 请输入三个数，格式示例: 100 0 -50 或 100,0,-50')
            continue
        try:
            vals = [float(x) for x in parts]
            return vals
        except ValueError:
            click.echo('[错误] 包含无法解析为数字的项，请重试。')
            continue


@click.group()
@click.option('--verbose', is_flag=True, help='增加日志详细程度')
@click.option('--log-file', default=None, help='将日志写入指定文件')
@click.pass_context
def cli(ctx, verbose, log_file):
    """MomentTransfer CLI 主入口（包含子命令）。"""
    ctx.ensure_object(dict)
    ctx.obj['logger'] = configure_logging(log_file, verbose)


@cli.command(name='run')
# 新增明确的 -c/--config 选项，保留 -i/--input 作为向后兼容的别名（标注为已弃用）
@click.option('-c', '--config', 'config_path', default=None,
              help='配置文件路径 (JSON)，默认使用项目 data/input.json')
@click.option('-i', '--input', 'input_path', default=None,
              help='（已弃用）配置文件路径，使用 -c/--config 替代')
@click.option('-o', '--output', 'output_path', default=None,
              help='结果输出路径 (JSON)，若不提供则不写文件')
@click.option('--force', type=(float, float, float), default=None,
              help='输入力向量 (例如: --force 100 0 -50)')
@click.option('--moment', type=(float, float, float), default=None,
              help='输入力矩向量 (例如: --moment 0 500 0)')
@click.pass_context
def main(ctx, config_path, input_path, output_path, force, moment):
    """气动载荷坐标变换工具（click CLI）

    支持非交互模式通过 `--force` 与 `--moment` 指定载荷。
    自动生成帮助文档（`--help`）。
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.join(base_dir, 'data', 'input.json')

    # 优先使用 -c/--config，其次兼容 -i/--input
    cfg_path = config_path or input_path

    # 非交互脚本调用（stdin 非 tty）时强制要求显式提供 config/input
    interactive = sys.stdin.isatty()
    if not cfg_path and not interactive:
        err = {"error": True, "message": "非交互模式下必须提供 --config/-c 或 --input/-i", "code": 2}
        sys.stderr.write(json.dumps(err, ensure_ascii=False) + "\n")
        sys.exit(2)

    # 回退到默认配置仅在交互模式下允许
    if not cfg_path:
        cfg_path = default_config

    # 在尝试加载前先检查配置文件是否存在，给出机器可读错误
    if not os.path.exists(cfg_path):
        err = {"error": True, "message": f"配置文件未找到: {cfg_path}", "hint": "使用 -c/--config 指定配置文件，或运行 creator.py 生成 data/input.json", "code": 3}
        sys.stderr.write(json.dumps(err, ensure_ascii=False) + "\n")
        sys.exit(3)

    raw_forces = list(force) if force is not None else None
    raw_moments = list(moment) if moment is not None else None

    if raw_forces is None:
        click.echo('\n--- 请输入载荷数据 (Source Frame) ---')
        raw_forces = prompt_vector('Force [Fx, Fy, Fz]')

    if raw_moments is None:
        raw_moments = prompt_vector('Moment [Mx, My, Mz]')

    click.echo(f"\n[1] 加载配置: {cfg_path}")
    try:
        project_data, calculator = load_project_calculator(cfg_path)
    except Exception as e:
        err = {"error": True, "message": f"无法加载配置: {str(e)}", "hint": "配置文件应包含对等的 'Source' 与 'Target' 节点，或使用 creator.py 生成兼容的配置。", "code": 4}
        sys.stderr.write(json.dumps(err, ensure_ascii=False) + "\n")
        sys.exit(4)

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
                "force_transformed": _make_serializable(result.force_transformed),
                "moment_transformed": _make_serializable(result.moment_transformed),
                "coeff_force": _make_serializable(result.coeff_force),
                "coeff_moment": _make_serializable(result.coeff_moment),
            },
        }

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                json.dump(out_data, fh, ensure_ascii=False, indent=2)
            click.echo(f"已将结果写入: {output_path}")
        except OSError as e:
            click.echo(f"[警告] 无法将结果写入 {output_path}: {e}")


cli = click.Group()
cli.add_command(main, name='run')
cli.add_command(registry_cmd, name='registry')

if __name__ == "__main__":
    cli()