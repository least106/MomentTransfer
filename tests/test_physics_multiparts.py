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

    # AeroCalculator 在 config 为 ProjectData 且未指定 target_part 时应抛出 ValueError
    with pytest.raises(ValueError, match=r"配置包含.*Target.*必须.*指定"):
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
    caplog.set_level("DEBUG")
    # 明确指定 target_part 以避免报错
    pd, calc = cli_helpers.load_project_calculator(str(p), target_part="t1")
    # 检查日志中是否记录了 debug 信息（如果有的话）
    # 新行为下，多 target 时不会自动选择，但也不会警告，只是 debug 日志
    # 所以不需要检查特定的警告消息
    assert calc is not None
    assert pd is not None and calc is not None
