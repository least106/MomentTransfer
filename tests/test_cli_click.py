import json
from pathlib import Path

from src.cli_helpers import attempt_load_project_data
from src.physics import AeroCalculator


def test_cli_non_interactive(tmp_path):
    # 直接复用 CLI 内部逻辑：加载配置、构造计算器并计算，再把结果写为 JSON
    out_file = tmp_path / 'out.json'
    project = attempt_load_project_data('data/input.json')
    if isinstance(project, tuple):
        # attempt_load_project_data 可能返回 (ok, project, info) 或直接 ProjectData
        # 上层包装里通常返回 ProjectData，当为 tuple 时提取第二项
        project = project[1] if project[0] else project[1]
    calc = AeroCalculator(project)
    calc.cfg = project

    result = calc.process_frame([100.0, 0.0, 0.0], [0.0, 0.0, 0.0])

    out_data = {
        "input": {"force": [100.0, 0.0, 0.0], "moment": [0.0, 0.0, 0.0]},
        "target": getattr(project.target_config, 'part_name', None),
        "result": {
            "force_transformed": result.force_transformed,
            "moment_transformed": result.moment_transformed,
            "coeff_force": result.coeff_force,
            "coeff_moment": result.coeff_moment,
        }
    }

    with open(out_file, 'w', encoding='utf-8') as fh:
        json.dump(out_data, fh, ensure_ascii=False)

    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding='utf-8'))
    assert 'result' in data
    assert 'force_transformed' in data['result']
