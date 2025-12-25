import json

import pytest

from src import cli_helpers


def test_mapping_applies(tmp_path):
    # 全局 cfg（默认无映射）
    global_cfg = cli_helpers.BatchConfig()

    # 建立目标文件
    f = tmp_path / "data_a.csv"
    f.write_text("1,2,3\n4,5,6", encoding='utf-8')

    # mapping 文件：所有 csv 使用 fx 列为 1
    mapping = [
        {"pattern": "*.csv", "format": {"columns": {"fx": 1}}}
    ]
    m = tmp_path / "mapping.json"
    m.write_text(json.dumps(mapping), encoding='utf-8')

    cfg = cli_helpers.resolve_file_format(str(f), global_cfg, mapping_file=str(m))
    assert cfg.column_mappings['fx'] == 7
    global_cfg = cli_helpers.BatchConfig()
    # 文件与 sidecar
    f = tmp_path / "fileX.csv"
    f.write_text("a,b,c", encoding='utf-8')
    side = tmp_path / "fileX.format.json"
    side.write_text(json.dumps({"columns": {"fx": 2}}), encoding='utf-8')

    # mapping 与 sidecar 冲突：mapping 指定 fx=9，但 sidecar 应优先
    mapping = [{"pattern": "*.csv", "format": {"columns": {"fx": 9}}}]
    m = tmp_path / "mapping.json"
    m.write_text(json.dumps(mapping), encoding='utf-8')

    cfg = cli_helpers.resolve_file_format(str(f), global_cfg, mapping_file=str(m))
    assert cfg.column_mappings['fx'] == 2


def test_mapping_over_dir_default(tmp_path):
    global_cfg = cli_helpers.BatchConfig()
    # 目录默认
    d = tmp_path / "sub"
    d.mkdir()
    f = d / "data.csv"
    f.write_text("1,2", encoding='utf-8')
    dir_def = d / "format.json"
    dir_def.write_text(json.dumps({"columns": {"fx": 5}}), encoding='utf-8')

    # mapping 指定 fx=7，应覆盖目录默认
    mapping = [{"pattern": "data.csv", "format": {"columns": {"fx": 7}}}]
    m = tmp_path / "mapping.json"
    m.write_text(json.dumps(mapping), encoding='utf-8')

    cfg = cli_helpers.resolve_file_format(str(f), global_cfg, mapping_file=str(m))
    assert cfg.column_mappings['fx'] == 7
```
