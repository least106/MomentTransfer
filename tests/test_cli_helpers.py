import json

import pytest

from src import cli_helpers


def test_load_format_from_file_valid(tmp_path):
    data = {
        "skip_rows": 1,
        "columns": {
            "alpha": None,
            "fx": 0,
            "fy": 1,
            "fz": 2,
            "mx": 3,
            "my": 4,
            "mz": 5,
        },
        "passthrough": [6, 7],
        "chunksize": 10,
        "name_template": "{stem}_t.csv",
        "timestamp_format": "%Y%m%d",
        "overwrite": True,
        "treat_non_numeric": "zero",
        "sample_rows": 2,
    }
    p = tmp_path / "fmt.json"
    p.write_text(json.dumps(data), encoding="utf-8")

    cfg = cli_helpers.load_format_from_file(str(p))
    assert cfg.skip_rows == 1
    assert cfg.column_mappings["fx"] == 0
    assert cfg.passthrough_columns == [6, 7]
    assert cfg.chunksize == 10


def test_load_format_from_file_empty(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        cli_helpers.load_format_from_file(str(p))


def test_load_format_from_file_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not a json", encoding="utf-8")
    with pytest.raises(ValueError):
        cli_helpers.load_format_from_file(str(p))


def test_get_user_file_format_interactive(monkeypatch):
    # 模拟用户输入序列：skip_rows, alpha(empty), fx..mz, passthrough
    inputs = iter(
        [
            "0",  # skip_rows
            "",  # alpha
            "0",  # fx
            "1",  # fy
            "2",  # fz
            "3",  # mx
            "4",  # my
            "5",  # mz
            "6,7",  # passthrough
        ]
    )

    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    cfg = cli_helpers.get_user_file_format()
    assert cfg.skip_rows == 0
    assert cfg.column_mappings["fx"] == 0
    assert cfg.column_mappings["mz"] == 5
    assert cfg.passthrough_columns == [6, 7]
