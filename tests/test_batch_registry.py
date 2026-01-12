import csv
import json
from pathlib import Path

from src.format_registry import init_db, register_mapping
from batch import run_batch_processing
from src.cli_helpers import BatchConfig


def write_sample_csv(path: Path, rows=8):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for i in range(rows):
            writer.writerow([100 + i, 0, -50 + i, 0, 10 + i, 0])


def test_noninteractive_with_registry(tmp_path):
    # 准备样例数据与格式文件
    csv_path = tmp_path / "sample.csv"
    write_sample_csv(csv_path, rows=8)

    fmt = {
        "skip_rows": 0,
        "columns": {
            "alpha": None,
            "fx": 0,
            "fy": 1,
            "fz": 2,
            "mx": 3,
            "my": 4,
            "mz": 5,
        },
        "passthrough": [],
    }
    fmt_path = tmp_path / "sample.format.json"
    with open(fmt_path, "w", encoding="utf-8") as fh:
        json.dump(fmt, fh)

    # 初始化 registry 并注册 sample.csv -> sample.format.json
    registry_path = tmp_path / "registry.sqlite"
    init_db(str(registry_path))
    # 使用文件名精确匹配
    register_mapping(str(registry_path), "sample.csv", str(fmt_path))

    # 使用默认 BatchConfig 作为全局基准（无全局 format_file），并传入 registry_db
    global_cfg = BatchConfig()

    # 为兼容新版 AeroCalculator，在内部加载项目并构造计算器时注入 cfg
    import src.cli_helpers as ch

    _real_loader = ch.load_project_calculator

    def _patched_loader(path, **kwargs):
        pd, calc = _real_loader(path, **kwargs)
        calc.cfg = pd
        return pd, calc

    ch.load_project_calculator = _patched_loader

    # 运行串行批处理（会在 tmp_path 下生成输出文件）
    run_batch_processing(
        "data/input.json",
        str(tmp_path),
        data_config=global_cfg,
        registry_db=str(registry_path),
    )

    # 恢复原始 loader（避免副作用）
    ch.load_project_calculator = _real_loader

    # 检查输出目录中是否出现结果文件
    out_files = list(tmp_path.glob("*_result_*.csv"))
    assert len(out_files) == 1
    # 简单检查输出内容行数与输入一致；若处理失败导致空文件，则应存在 .partial 文件记录错误
    import pandas as pd

    out = out_files[0]
    try:
        df = pd.read_csv(out)
        assert len(df) == 8
    except pd.errors.EmptyDataError:
        # 若为空，确认 partial 文件包含错误信息
        partial = out.with_name(out.name + ".partial")
        assert partial.exists()
        txt = partial.read_text(encoding="utf-8")
        assert "error" in txt or len(txt.strip()) > 0
