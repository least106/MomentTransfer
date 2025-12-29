import csv
from pathlib import Path
import json

import pandas as pd

from src.data_loader import load_data
from src.physics import AeroCalculator
from batch import process_single_file, BatchConfig


def write_sample_csv(path: Path, rows=10):
    # 构造列: fx,fy,fz,mx,my,mz (索引 0..5)
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        for i in range(rows):
            if i % 4 == 0:
                # 注入非数值
                writer.writerow(['x', 'y', 'z', 'a', 'b', 'c'])
            else:
                writer.writerow([100+i, 0, -50+i, 0, 10+i, 0])


def test_process_single_file_chunksize_drop(tmp_path):
    csv_path = tmp_path / 'sample.csv'
    write_sample_csv(csv_path, rows=12)

    project = load_data('data/input.json')
    calc = AeroCalculator(project)
    # Ensure calculator has cfg reference for coeff calculations
    calc.cfg = project

    cfg = BatchConfig()
    cfg.skip_rows = 0
    # 对应写入的列顺序: fx,fy,fz,mx,my,mz -> 索引 0..5
    cfg.column_mappings = {'alpha': None, 'fx': 0, 'fy': 1, 'fz': 2, 'mx': 3, 'my': 4, 'mz': 5}
    cfg.passthrough_columns = []
    cfg.chunksize = 5
    cfg.treat_non_numeric = 'drop'

    out_dir = tmp_path / 'out'
    out_dir.mkdir()

    ok = process_single_file(csv_path, calc, cfg, out_dir)
    assert ok
    files = list(out_dir.glob('*.csv'))
    assert len(files) == 1
    df = pd.read_csv(files[0])
    # 原始12行中每4行有1个非数值 -> 非数值行为 3 -> drop 后应剩余 9 行
    assert len(df) == 9
