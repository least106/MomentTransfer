import json

import pytest

from src import cli_helpers
from src.data_loader import ProjectData
from src.physics import AeroCalculator


def _make_frame_dict(name="P", origin=(0, 0, 0)):
    return {
        "PartName": name,
        "CoordSystem": {
            "Orig": list(origin),
            "X": [1, 0, 0],
            "Y": [0, 1, 0],
            "Z": [0, 0, 1],
        },
        "MomentCenter": [0, 0, 0],
        "Q": 1.0,
        "S": 1.0,
    }


def test_aerocalc_warns_on_multiple_target_parts():
    # 构造包含两个 target part 的 ProjectData 字典
    data = {
        "Source": {
            "Parts": [{"PartName": "src", "Variants": [{**_make_frame_dict("src")}]}]
        },
        "Target": {
            "Parts": [
                {"PartName": "t1", "Variants": [{**_make_frame_dict("t1")}]},
                {"PartName": "t2", "Variants": [{**_make_frame_dict("t2")}]},
            ]
        },
    }

    pd = ProjectData.from_dict(data)

    # AeroCalculator 在 config 为 ProjectData 且未指定 target_part 时应发出 UserWarning
    with pytest.warns(UserWarning):
        AeroCalculator(pd)


def test_load_project_calculator_logs_warning_for_multiple_targets(tmp_path, caplog):
    # 将上面相同的数据写入临时文件并调用 load_project_calculator，检查日志
    data = {
        "Source": {
            "Parts": [{"PartName": "src", "Variants": [{**_make_frame_dict("src")}]}]
        },
        "Target": {
            "Parts": [
                {"PartName": "t1", "Variants": [{**_make_frame_dict("t1")}]},
                {"PartName": "t2", "Variants": [{**_make_frame_dict("t2")}]},
            ]
        },
    }
    p = tmp_path / "proj.json"
    p.write_text(json.dumps(data), encoding="utf-8")

    caplog.clear()
    caplog.set_level("WARNING")
    pd, calc = cli_helpers.load_project_calculator(str(p))
    # 检查日志中是否包含提示未指定 target_part 的警告
    assert any(
        "未指定 --target-part" in rec.getMessage()
        or "自动选择第一个 Part" in rec.getMessage()
        for rec in caplog.records
    )
    assert pd is not None and calc is not None
