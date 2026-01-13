import json

from src.cli_helpers import BatchConfig
from batch import run_batch_processing


def test_batch_non_interactive_output_json(tmp_path):
    # 准备一个简单的 CSV 文件（无表头）
    csv_file = tmp_path / "sample1.csv"
    # 6 列：fx,fy,fz,mx,my,mz
    csv_file.write_text(
        """1,2,3,0.1,0.2,0.3
4,5,6,0.4,0.5,0.6
"""
    )

    # 配置 BatchConfig，映射前六列
    cfg = BatchConfig()
    cfg.column_mappings.update({"fx": 0, "fy": 1, "fz": 2, "mx": 3, "my": 4, "mz": 5})
    cfg.passthrough_columns = []

    out_json = tmp_path / "result.json"

    # 调用批处理，非交互模式：提供 data_config 与 registry_db（可为空文件路径）
    registry_db = tmp_path / "reg.db"
    run_batch_processing(
        config_path="data/input.json",
        input_path=str(tmp_path),
        data_config=cfg,
        registry_db=str(registry_db),
        strict=False,
        dry_run=False,
        show_progress=False,
        output_json=str(out_json),
        summary=True,
    )

    assert out_json.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert "files" in payload
    assert payload["total"] == 1
    assert payload["success"] + payload["fail"] == payload["total"]
