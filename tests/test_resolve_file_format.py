import json

from src.cli_helpers import BatchConfig, resolve_file_format


def test_resolve_file_format_default_skips_sidecar(tmp_path):
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("a,b,c\n1,2,3\n")

    sidecar = tmp_path / "sample.format.json"
    sidecar.write_text(json.dumps({"sample_rows": 10}))

    base = BatchConfig()
    base.sample_rows = 5

    cfg = resolve_file_format(str(csv_file), base)
    assert cfg.sample_rows == 5


def test_resolve_file_format_enable_sidecar_applies(tmp_path):
    csv_file = tmp_path / "sample2.csv"
    csv_file.write_text("a,b,c\n1,2,3\n")

    sidecar = tmp_path / "sample2.format.json"
    sidecar.write_text(json.dumps({"sample_rows": 20}))

    base = BatchConfig()
    base.sample_rows = 5

    cfg = resolve_file_format(str(csv_file), base, enable_sidecar=True)
    assert cfg.sample_rows == 20
