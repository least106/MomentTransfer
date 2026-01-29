"""
MomentTransfer CLI - 单帧坐标变换工具

使用示例：
    python -m cli run --config data/input.json --force 100 0 -50 --moment 0 500 0
    python -m cli run -c data/input.json --force 100 0 -50 --moment 0 500 0 -o output.json
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

import click

from src.data_loader import load_data
from src.physics import AeroCalculator


def _make_serializable(v: Any) -> Any:
    """将 numpy 数组转为 Python 原生 list 结构，便于 JSON 序列化。"""
    try:
        if hasattr(v, "tolist"):
            return v.tolist()
    except Exception:
        pass
    return v


@click.group()
@click.option("--verbose", is_flag=True, help="增加日志详细程度")
def cli(verbose):
    """MomentTransfer 命令行工具"""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)


@cli.command(name="run")
@click.option(
    "-c",
    "--config",
    "config_path",
    required=True,
    help="配置文件路径 (JSON)。示例: -c data/input.json",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    default=None,
    help="结果输出文件路径 (JSON)。若不提供则仅打印到屏幕",
)
@click.option(
    "--force",
    type=(float, float, float),
    required=True,
    help="输入力向量，格式: Fx Fy Fz (例: --force 100 0 -50)",
)
@click.option(
    "--moment",
    type=(float, float, float),
    required=True,
    help="输入力矩向量，格式: Mx My Mz (例: --moment 0 500 0)",
)
@click.option(
    "--target-part",
    default=None,
    help="目标 part 名称（可选，多 part 时指定）",
)
@click.option(
    "--target-variant", type=int, default=0, help="目标 variant 索引，默认 0"
)
def run(config_path, output_path, force, moment, target_part, target_variant):
    """执行单帧坐标变换

    \b
    示例：
        python -m cli run -c config.json --force 100 0 -50 --moment 0 500 0
        python -m cli run -c config.json --force 100 0 -50 --moment 0 500 0 -o result.json
    """
    try:
        # 加载配置
        config_path = Path(config_path)
        if not config_path.exists():
            click.echo(f"错误：配置文件不存在 {config_path}", err=True)
            sys.exit(1)

        click.echo(f"[1] 加载配置: {config_path}")
        project_data = load_data(str(config_path))

        # 创建计算器
        click.echo("[2] 初始化计算器...")
        calculator = AeroCalculator(
            project_data,
            target_part=target_part,
            target_variant=target_variant,
        )

        # 执行计算
        click.echo("[3] 执行坐标变换...")
        forces = list(force)
        moments = list(moment)
        result = calculator.process_frame(forces, moments)

        # 输出结果
        click.echo("\n" + "=" * 60)
        click.echo(f"输入载荷: F = {forces}, M = {moments}")

        def fmt_vector(v):
            return [round(x, 6) for x in v]

        click.echo("\n转换结果:")
        click.echo(f"  力 (N)     : {fmt_vector(result.force_transformed)}")
        click.echo(f"  力矩 (N·m) : {fmt_vector(result.moment_transformed)}")

        click.echo("\n气动系数:")
        click.echo(f"  [Cx, Cy, Cz] : {fmt_vector(result.coeff_force)}")
        click.echo(f"  [Cl, Cm, Cn] : {fmt_vector(result.coeff_moment)}")
        click.echo("=" * 60)

        # 保存结果（若指定）
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            output_data = {
                "input": {"force": forces, "moment": moments},
                "result": {
                    "force_transformed": _make_serializable(
                        result.force_transformed
                    ),
                    "moment_transformed": _make_serializable(
                        result.moment_transformed
                    ),
                    "coeff_force": _make_serializable(result.coeff_force),
                    "coeff_moment": _make_serializable(result.coeff_moment),
                },
            }

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            click.echo(f"\n✓ 结果已保存: {output_file}")

    except Exception as e:
        click.echo(f"错误: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
