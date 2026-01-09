import concurrent.futures
import logging
from pathlib import Path

import pandas as pd


def _worker_write(args):
    # 在子进程内导入并执行写入（按 repo 模块路径导入）
    import batch as b
    from src.cli_helpers import load_project_calculator, BatchConfig

    project_path = args["project_path"]
    input_csv = Path(args["input_csv"])
    out_path = Path(args["out_path"])

    # 重建计算器与配置
    project_data, calculator = load_project_calculator(project_path)
    # 在子进程中也确保 calculator 包含 cfg（新版要求）
    calculator.cfg = project_data
    cfg = BatchConfig()
    cfg.column_mappings = {"fx": 0, "fy": 1, "fz": 2, "mx": 3, "my": 4, "mz": 5}
    cfg.passthrough_columns = []
    cfg.treat_non_numeric = "zero"

    # 读取整表作为一个 chunk 并追加写入同一目标文件
    df = pd.read_csv(input_csv, header=None)
    logger = logging.getLogger("test")
    processed, dropped, n_non, _ = b.process_df_chunk(
        df, 0, 1, 2, 3, 4, 5, calculator, cfg, out_path, False, logger
    )
    return processed


def test_concurrent_appends_to_same_file(tmp_path):
    """模拟多个进程并发向同一输出文件追加，最终检查行数一致性。"""
    project_config = Path("data/input.json")
    assert (
        project_config.exists()
    ), "需要 repository 中的 data/input.json 用于构造计算器"

    # 准备输入 CSV（每个 worker 写入相同的三行）
    input_csv = tmp_path / "in.csv"
    df_in = pd.DataFrame(
        [
            [1, 2, 3, 4, 5, 6],
            [7, 8, 9, 10, 11, 12],
            [13, 14, 15, 16, 17, 18],
        ]
    )
    df_in.to_csv(input_csv, index=False, header=False)

    # 输出文件（多个进程将并发写入此文件）
    out_file = tmp_path / "shared_out.csv"

    # 先写入 header（由主进程完成，模拟 first_chunk 已写入场景）
    import batch as b
    from src.cli_helpers import load_project_calculator, BatchConfig

    project_data, calculator = load_project_calculator(project_config)
    # 主进程也设置 cfg
    calculator.cfg = project_data
    cfg = BatchConfig()
    cfg.column_mappings = {"fx": 0, "fy": 1, "fz": 2, "mx": 3, "my": 4, "mz": 5}
    cfg.passthrough_columns = []
    cfg.treat_non_numeric = "zero"

    first_df = pd.read_csv(input_csv, header=None)
    logger = logging.getLogger("test")
    # 主进程写入 header（first_chunk=True）
    b.process_df_chunk(
        first_df, 0, 1, 2, 3, 4, 5, calculator, cfg, out_file, True, logger
    )

    # 并发提交多个写入任务（模拟 4 个并发进程）
    workers = 4
    args = {
        "project_path": str(project_config),
        "input_csv": str(input_csv),
        "out_path": str(out_file),
    }
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as exe:
        futures = [exe.submit(_worker_write, args) for _ in range(workers)]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    # 读取输出并验证行数（主进程先写入了 3 行，之后每个 worker 写入 3 行）
    out_df = pd.read_csv(out_file)
    assert len(out_df) == (workers + 1) * 3
    # 验证每个 worker 至少写入了数据行
    assert all(r == 3 for r in results)
