import csv
from pathlib import Path

import pandas as pd

from batch import BatchConfig, process_single_file
from src.data_loader import load_data
from src.physics import AeroCalculator


def write_sample_csv(path: Path, rows=10):
    # 构造列: Fx,Fy,Fz,Mx,My,Mz 并在每 4 行插入一行非数值
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Fx", "Fy", "Fz", "Mx", "My", "Mz"])
        for i in range(rows):
            if i % 4 == 0:
                # 注入非数值
                writer.writerow(["x", "y", "z", "a", "b", "c"])
            else:
                writer.writerow([100 + i, 0, -50 + i, 0, 10 + i, 0])


def test_process_single_file_chunksize_drop(tmp_path):
    csv_path = tmp_path / "sample.csv"
    write_sample_csv(csv_path, rows=12)

    project = load_data("data/input.json")
    calc = AeroCalculator(project, target_part="TestModel")
    # Ensure calculator has cfg reference for coeff calculations
    calc.cfg = project

    cfg = BatchConfig()
    cfg.skip_rows = 0
    cfg.treat_non_numeric = "drop"

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    ok = process_single_file(csv_path, calc, cfg, out_dir)
    assert ok
    files = list(out_dir.glob("*.csv"))
    assert len(files) == 1
    df = pd.read_csv(files[0])
    # 原始数据共 12 行 + 表头，且每 4 行有 1 行非数值 -> 非数值 3 行，drop 后剩余 9 行
    assert len(df) == 9
