import json

from batch import run_batch_processing
from src.cli_helpers import BatchConfig


def test_batch_non_interactive_output_json(tmp_path):
    # 准备一个简单的 CSV 文件（包含表头）
    csv_file = tmp_path / "sample1.csv"
    csv_file.write_text(
        """Fx,Fy,Fz,Mx,My,Mz
1,2,3,0.1,0.2,0.3
4,5,6,0.4,0.5,0.6
""",
        encoding="utf-8",
    )

    cfg = BatchConfig()

    out_json = tmp_path / "result.json"

    # 调用批处理，非交互模式：提供 data_config
    run_batch_processing(
        config_path="data/input.json",
        input_path=str(tmp_path),
        data_config=cfg,
        strict=False,
        dry_run=False,
        show_progress=False,
        output_json=str(out_json),
        summary=True,
        target_part="TestModel",  # 明确指定 target part
    )

    assert out_json.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert "files" in payload
    assert payload["total"] == 1
    assert payload["success"] + payload["fail"] == payload["total"]
