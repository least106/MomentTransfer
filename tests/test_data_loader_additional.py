from pathlib import Path

import pytest

from src.data_loader import (
    CoordSystemDefinition,
    FrameConfiguration,
    ProjectData,
    try_load_project_data,
)


def valid_coord():
    return {"Orig": [0, 0, 0], "X": [1, 0, 0], "Y": [0, 1, 0], "Z": [0, 0, 1]}


def valid_frame_dict():
    return {
        "PartName": "P",
        "CoordSystem": valid_coord(),
        "MomentCenter": [0.0, 0.0, 0.0],
        "Cref": 1.0,
        "Bref": 1.0,
        "Q": 100.0,
        "S": 10.0,
    }


def test_coordsystem_from_dict_missing_field_raises():
    data = {"Orig": [0, 0, 0], "X": [1, 0, 0], "Y": [0, 1, 0]}  # missing Z
    with pytest.raises(ValueError) as e:
        CoordSystemDefinition.from_dict(data)
    assert "缺少必须字段" in str(e.value)


def test_coordsystem_from_dict_invalid_vector_type():
    data = {"Orig": [0, 0, 0], "X": "notalist", "Y": [0, 1, 0], "Z": [0, 0, 1]}
    with pytest.raises(ValueError):
        CoordSystemDefinition.from_dict(data)


def test_frame_from_dict_missing_partname_raises():
    d = valid_frame_dict()
    d.pop("PartName")
    with pytest.raises(ValueError) as e:
        FrameConfiguration.from_dict(d, frame_type="Frame")
    assert "缺少必须字段: PartName" in str(e.value)


def test_frame_from_dict_missing_coord_raises():
    d = valid_frame_dict()
    d.pop("CoordSystem")
    with pytest.raises(ValueError) as e:
        FrameConfiguration.from_dict(d, frame_type="Frame")
    assert "缺少坐标系字段" in str(e.value) or "CoordSystem" in str(e.value)


def test_frame_from_dict_missing_moment_center_raises():
    d = valid_frame_dict()
    d.pop("MomentCenter")
    with pytest.raises(ValueError) as e:
        FrameConfiguration.from_dict(d, frame_type="Frame")
    assert "必须包含 MomentCenter" in str(e.value)


def test_frame_from_dict_missing_q_or_s_raises():
    d = valid_frame_dict()
    d.pop("Q")
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(d, frame_type="Frame")

    d2 = valid_frame_dict()
    d2.pop("S")
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(d2, frame_type="Frame")


def test_projectdata_parse_parts_section_requires_parts_list():
    data = {"Source": {}, "Target": {}}
    with pytest.raises(ValueError):
        ProjectData.from_dict(data)


def test_projectdata_variants_empty_raises():
    data = {
        "Source": {
            "Parts": [{"PartName": "S", "Variants": [valid_frame_dict()]}]
        },
        "Target": {"Parts": [{"PartName": "T", "Variants": []}]},
    }
    with pytest.raises(ValueError):
        ProjectData.from_dict(data)


def test_projectdata_success_and_accessors():
    frame = valid_frame_dict()
    data = {
        "Source": {"Parts": [{"PartName": "S", "Variants": [frame]}]},
        "Target": {"Parts": [{"PartName": "T", "Variants": [frame]}]},
    }
    pd = ProjectData.from_dict(data)
    # accessors
    assert pd.source_config.part_name == "P"
    assert pd.target_config.part_name == "P"
    assert pd.get_source_part("S").part_name == "P"
    assert pd.get_target_part("T").part_name == "P"


def test_load_data_and_try_load_project_data_file_errors(tmp_path: Path):
    missing = tmp_path / "nope.json"
    ok, pd, info = try_load_project_data(str(missing))
    assert ok is False
    assert pd is None
    assert info and "找不到文件" in info["message"]

    # invalid json
    bad = tmp_path / "bad.json"
    bad.write_text("{ not: valid json }")
    ok2, pd2, info2 = try_load_project_data(str(bad))
    assert ok2 is False
    assert pd2 is None
    assert info2 and "不是有效的 JSON" in info2["message"]


def test_try_load_project_data_strict_false_raises(tmp_path: Path):
    missing = tmp_path / "nope2.json"
    with pytest.raises(FileNotFoundError):
        try_load_project_data(str(missing), strict=False)
