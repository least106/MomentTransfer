import json

import pytest

from src import calculator_factory as cf


class DummyProject:
    def __init__(self, targets=None):
        self.target_parts = targets or {}


class DummyCalc:
    def __init__(self, project_data, **kwargs):
        self.project_data = project_data
        self.kw = kwargs


class DummyExecutionContext:
    def __init__(self, project_data, calculator):
        self.project_data = project_data
        self.calculator = calculator


def test_load_project_calculator_success_auto_select(monkeypatch):
    dummy_proj = DummyProject(targets={"T1": {}})
    dummy_calc = DummyCalc(dummy_proj, target_part="T1")
    dummy_ctx = DummyExecutionContext(dummy_proj, dummy_calc)

    monkeypatch.setattr(
        cf, "create_execution_context", lambda *args, **kwargs: dummy_ctx
    )

    proj, calc = cf.load_project_calculator("somepath")
    assert proj is dummy_proj
    assert calc is dummy_calc


def test_load_project_calculator_file_not_found(monkeypatch):
    def raise_fn(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(cf, "create_execution_context", raise_fn)
    with pytest.raises(ValueError) as ei:
        cf.load_project_calculator("nope")
    assert "配置文件未找到" in str(ei.value)


def test_load_project_calculator_json_error(monkeypatch):
    def raise_fn(*args, **kwargs):
        raise json.JSONDecodeError("msg", "doc", 0)

    monkeypatch.setattr(cf, "create_execution_context", raise_fn)
    with pytest.raises(ValueError) as ei:
        cf.load_project_calculator("bad")
    assert "不是有效的 JSON" in str(ei.value)


def test_load_project_calculator_key_error(monkeypatch):
    def raise_fn(*args, **kwargs):
        raise KeyError("missing")

    monkeypatch.setattr(cf, "create_execution_context", raise_fn)
    with pytest.raises(ValueError) as ei:
        cf.load_project_calculator("bad")
    assert "缺少必要字段" in str(ei.value)


def test_attempt_load_project_data_strict_and_non_strict(monkeypatch):
    proj = DummyProject()
    monkeypatch.setattr(
        cf, "try_load_project_data", lambda p, strict=True: (True, proj, {})
    )
    got = cf.attempt_load_project_data("x", strict=True)
    assert got is proj

    monkeypatch.setattr(
        cf,
        "try_load_project_data",
        lambda p, strict=True: (
            False,
            None,
            {"message": "m", "suggestion": "s"},
        ),
    )
    with pytest.raises(ValueError):
        cf.attempt_load_project_data("x", strict=True)

    none, info = cf.attempt_load_project_data("x", strict=False)
    assert none is None and isinstance(info, dict)
