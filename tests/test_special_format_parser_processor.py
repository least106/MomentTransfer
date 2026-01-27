from pathlib import Path

import pandas as pd

from src import special_format_parser as parser_mod
from src import special_format_processor as proc_mod


def make_file(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.mtfmt"
    p.write_text(content, encoding="utf-8")
    return p


def test_get_part_names_and_parse(tmp_path):
    content = """
PartA
Alpha CL CD Cx Cy Cz/FN CMx CMy CMz
0.1 1 2 3 4 5 6 7 8

PartB
Alpha CL CD Cx Cy Cz/FN CMx CMy CMz
0.2 2 3 4 5 6 7 8 9
"""
    p = make_file(tmp_path, content)

    parts = parser_mod.get_part_names(p)
    assert "PartA" in parts and "PartB" in parts

    data = parser_mod.parse_special_format_file(p)
    assert "PartA" in data and isinstance(data["PartA"], pd.DataFrame)
    assert data["PartA"].shape[0] == 1
    # 核心列应被标准化存在
    assert any(c in data["PartA"].columns for c in ["Cx", "Cy", "Cz/FN"])


def test_process_single_part_missing_columns(tmp_path):
    # 创建缺少必需列的 df
    df = pd.DataFrame({"Alpha": [0.1], "CL": [1.0]})
    file_path = tmp_path / "f.mtfmt"
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    class PD:
        source_parts = {"P": {}}
        target_parts = {"P": {}}

    project_data = PD()

    out, report = proc_mod._process_single_part(
        "P",
        df,
        file_path=file_path,
        project_data=project_data,
        output_dir=output_dir,
    )

    assert out is None
    assert report["reason"] == "missing_columns"


def test_process_single_part_success(tmp_path, monkeypatch):
    # 构造含必需列的 df
    df = pd.DataFrame(
        {
            "Cx": [1.0, 2.0],
            "Cy": [0.5, 0.6],
            "Cz/FN": [0.1, 0.2],
            "CMx": [0.0, 0.0],
            "CMy": [0.0, 0.0],
            "CMz": [0.0, 0.0],
        }
    )
    file_path = tmp_path / "f.mtfmt"
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    # 模拟 ProjectData
    class PD:
        source_parts = {"part1": {}}
        target_parts = {"part1": {}}

    project_data = PD()

    # monkeypatch AeroCalculator 以返回确定形状的数据
    class FakeCalc:
        def __init__(self, project_data, source_part=None, target_part=None):
            pass

        def process_batch(self, forces, moments):
            n = forces.shape[0]
            import numpy as np

            return {
                "force_transformed": np.zeros((n, 3)),
                "moment_transformed": np.zeros((n, 3)),
                "coeff_force": np.zeros((n, 3)),
                "coeff_moment": np.zeros((n, 3)),
            }

    monkeypatch.setattr(proc_mod, "AeroCalculator", FakeCalc)

    out_path, report = proc_mod._process_single_part(
        "part1",
        df,
        file_path=file_path,
        project_data=project_data,
        output_dir=output_dir,
    )

    assert out_path is not None
    assert report["status"] == "success"
    # 输出文件确实存在
    assert (output_dir / Path(out_path).name).exists()
