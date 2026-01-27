import json

import pytest

from src import calculator_factory as cf
from src.data_loader import CoordSystemDefinition, FrameConfiguration, ProjectData
from src.physics import AeroCalculator


def make_project(single_target=True):
    coord = CoordSystemDefinition(
        origin=[0, 0, 0], x_axis=[1, 0, 0], y_axis=[0, 1, 0], z_axis=[0, 0, 1]
    )
    frame = FrameConfiguration(
        part_name="P",
        coord_system=coord,
        moment_center=[0, 0, 0],
        c_ref=1.0,
        b_ref=1.0,
        q=1.0,
        s_ref=1.0,
    )
    source_parts = {"src": [frame]}
    if single_target:
        target_parts = {"tgt": [frame]}
    else:
        target_parts = {"t1": [frame], "t2": [frame]}
    return ProjectData(source_parts=source_parts, target_parts=target_parts)


def test_load_project_calculator_success(monkeypatch, tmp_path):
    proj = make_project(single_target=True)

    def fake_load(path):
        return proj

    monkeypatch.setattr(cf, "load_data", fake_load)

    pd, calc = cf.load_project_calculator(str(tmp_path / "dummy.json"))
    assert pd is proj
    assert isinstance(calc, AeroCalculator)


def test_load_project_calculator_file_not_found(monkeypatch):
    def raise_fn(path):
        raise FileNotFoundError()

    monkeypatch.setattr(cf, "load_data", raise_fn)
    with pytest.raises(ValueError) as exc:
        cf.load_project_calculator("missing.json")
    assert "配置文件未找到" in str(exc.value)


def test_load_project_calculator_bad_json(monkeypatch):
    def raise_fn(path):
        raise json.JSONDecodeError("err", "doc", 0)

    monkeypatch.setattr(cf, "load_data", raise_fn)
    with pytest.raises(ValueError) as exc:
        cf.load_project_calculator("bad.json")
    assert "不是有效的 JSON" in str(exc.value)


def test_load_project_calculator_missing_key(monkeypatch):
    def raise_fn(path):
        raise KeyError("SomeKey")

    monkeypatch.setattr(cf, "load_data", raise_fn)
    with pytest.raises(ValueError) as exc:
        cf.load_project_calculator("bad.json")
    assert "缺少必要字段" in str(exc.value)
