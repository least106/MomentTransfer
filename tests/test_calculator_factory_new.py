import json
import types

import pytest

import src.calculator_factory as cf


def test_load_project_calculator_success(monkeypatch):
    # 模拟 ProjectData 与 AeroCalculator
    fake_pd = types.SimpleNamespace(target_parts={"T1": {}})

    def fake_load(path):
        return fake_pd

    class FakeCalc:
        def __init__(self, pd, **kwargs):
            self.pd = pd

    monkeypatch.setattr(cf, "load_data", fake_load)
    monkeypatch.setattr(cf, "AeroCalculator", FakeCalc)

    pd, calc = cf.load_project_calculator("some.json")
    assert pd is fake_pd
    assert isinstance(calc, FakeCalc)


def test_load_project_calculator_errors(monkeypatch):
    def raise_notfound(path):
        raise FileNotFoundError()

    monkeypatch.setattr(cf, "load_data", raise_notfound)
    with pytest.raises(ValueError):
        cf.load_project_calculator("missing.json")

    def raise_json(path):
        raise json.JSONDecodeError("err", "doc", 0)

    monkeypatch.setattr(cf, "load_data", raise_json)
    with pytest.raises(ValueError):
        cf.load_project_calculator("bad.json")


def test_attempt_load_project_data(monkeypatch):
    info = {"message": "no", "suggestion": "try"}
    # 返回失败且 strict=False
    monkeypatch.setattr(cf, "try_load_project_data", lambda p, strict=True: (False, None, info))
    res = cf.attempt_load_project_data("x", strict=False)
    assert isinstance(res, tuple) and res[0] is None and res[1] == info

    # strict=True 应抛出
    with pytest.raises(ValueError):
        cf.attempt_load_project_data("x", strict=True)
