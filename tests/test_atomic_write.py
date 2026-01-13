import csv
from pathlib import Path

import pandas as pd

from src.cli_helpers import load_project_calculator, load_format_from_file
from batch import process_single_file


def write_sample_csv(path: Path, rows=5):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for i in range(rows):
            writer.writerow([100 + i, 0, -50 + i, 0, 10 + i, 0])


def test_process_single_file_creates_complete_flag(tmp_path):
    csv_path = tmp_path / "in.csv"
    write_sample_csv(csv_path, rows=6)

    # load calculator from sample project config
    project_data, calculator = load_project_calculator("data/input.json")
    # 新版 AeroCalculator 不再自动保留 project 引用，测试中显式设置以兼容 process_batch
    calculator.cfg = project_data

    cfg = load_format_from_file("data/default.format.json")
    # ensure output goes to tmp_path
    ok = process_single_file(csv_path, calculator, cfg, tmp_path)
    assert ok

    out_files = list(tmp_path.glob("*_result_*.csv"))
    assert len(out_files) == 1

    out = out_files[0]
    # .complete flag exists
    complete = out.with_name(out.name + ".complete")
    partial = out.with_name(out.name + ".partial")
    assert complete.exists()
    assert not partial.exists()

    # file content contains expected number of rows
    df = pd.read_csv(out)
    assert len(df) == 6
