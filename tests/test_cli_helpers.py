import json
from pathlib import Path

import pytest

from src import cli_helpers


def test_load_format_from_file_valid(tmp_path):
    data = {
        "skip_rows": 1,
        "columns": {"alpha": None, "fx": 0, "fy": 1, "fz": 2, "mx": 3, "my": 4, "mz": 5},
        "passthrough": [6, 7],
        "chunksize": 10,
        "name_template": "{stem}_t.csv",
        "timestamp_format": "%Y%m%d",
        "overwrite": True,
        "treat_non_numeric": "zero",
        "sample_rows": 2,
    }
    p = tmp_path / "fmt.json"
    p.write_text(json.dumps(data), encoding='utf-8')

    cfg = cli_helpers.load_format_from_file(str(p))
    assert cfg.skip_rows == 1
    assert cfg.column_mappings['fx'] == 0
    assert cfg.passthrough_columns == [6, 7]


def test_mapping_file_priority_and_match(tmp_path):
    from src import cli_helpers

    global_cfg = cli_helpers.BatchConfig()
    # 文件与 sidecar
    f = tmp_path / "file_map.csv"
    f.write_text("1,2,3", encoding='utf-8')

    # sidecar 优先于 mapping
    side = tmp_path / "file_map.format.json"
    side.write_text(json.dumps({"columns": {"fx": 10}}), encoding='utf-8')

    mapping = [{"pattern": "*.csv", "format": {"columns": {"fx": 9}}}]
    m = tmp_path / "mapping.json"
    m.write_text(json.dumps(mapping), encoding='utf-8')

    cfg = cli_helpers.resolve_file_format(str(f), global_cfg, mapping_file=str(m))
    assert cfg.column_mappings['fx'] == 10


def test_mapping_over_dir_default(tmp_path):
    from src import cli_helpers

    global_cfg = cli_helpers.BatchConfig()
    d = tmp_path / "subdir"
    d.mkdir()
    f = d / "data.csv"
    f.write_text("a,b", encoding='utf-8')
    dir_def = d / "format.json"
    dir_def.write_text(json.dumps({"columns": {"fx": 5}}), encoding='utf-8')

    mapping = [{"pattern": "data.csv", "format": {"columns": {"fx": 7}}}]
    m = tmp_path / "mapping.json"
    m.write_text(json.dumps(mapping), encoding='utf-8')

    cfg = cli_helpers.resolve_file_format(str(f), global_cfg, mapping_file=str(m))
    assert cfg.column_mappings['fx'] == 7
    assert cfg.chunksize == 10


def test_load_format_from_file_empty(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text("", encoding='utf-8')
    with pytest.raises(ValueError):
        cli_helpers.load_format_from_file(str(p))


def test_load_format_from_file_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not a json", encoding='utf-8')
    with pytest.raises(ValueError):
        cli_helpers.load_format_from_file(str(p))


def test_get_user_file_format_interactive(monkeypatch):
    # 模拟用户输入序列：skip_rows, alpha(empty), fx..mz, passthrough
    inputs = iter([
        "0",  # skip_rows
        "",   # alpha
        "0",  # fx
        "1",  # fy
        "2",  # fz
        "3",  # mx
        "4",  # my
        "5",  # mz
        "6,7",# passthrough
    ])

    monkeypatch.setattr('builtins.input', lambda prompt='': next(inputs))

    cfg = cli_helpers.get_user_file_format()
    assert cfg.skip_rows == 0
    assert cfg.column_mappings['fx'] == 0
    assert cfg.column_mappings['mz'] == 5
    assert cfg.passthrough_columns == [6, 7]
