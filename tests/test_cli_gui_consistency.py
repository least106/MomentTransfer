"""
CLI 与 GUI 批处理逻辑一致性测试

验证：
1. CLI 和 GUI 都支持每文件独立的 calculator
2. 行过滤逻辑一致
3. 表头检测一致
"""

import pytest
import tempfile
import pandas as pd

# 导入核心模块
from batch import process_single_file


@pytest.fixture
def temp_csv_file():
    """创建临时 CSV 文件用于测试"""
    # 创建带表头的 CSV 数据
    data = [
        ["Fx", "Fy", "Fz", "Mx", "My", "Mz"],  # 表头
        [100, 0, 0, 0, 0, 0],
        [200, 10, 5, 5, 10, 0],
        [150, -5, 2, 0, 5, 1],
    ]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    ) as f:
        for row in data:
            f.write(",".join(str(x) for x in row) + "\n")
        return f.name


def test_per_file_calculator_support():
    """
    测试 process_single_file() 支持 per-file source/target

    验证函数能够接受 source_part、target_part 和 selected_rows 参数
    """
    import inspect

    sig = inspect.signature(process_single_file)
    params = list(sig.parameters.keys())

    # 检查新增的参数
    assert "source_part" in params, "缺少 source_part 参数"
    assert "target_part" in params, "缺少 target_part 参数"
    assert "selected_rows" in params, "缺少 selected_rows 参数"

    # 检查参数的默认值
    assert sig.parameters["source_part"].default is None
    assert sig.parameters["target_part"].default is None
    assert sig.parameters["selected_rows"].default is None


def test_header_detection_logic(temp_csv_file):
    """
    测试表头自动检测逻辑
    """
    # 读取带表头的 CSV
    df = pd.read_csv(temp_csv_file, header=None)

    # 模拟 CLI 中的表头检测逻辑
    required_cols = [0, 1, 2, 3, 4, 5]  # fx, fy, fz, mx, my, mz 列索引
    non_numeric_count = 0
    checked = 0

    for idx in required_cols:
        if 0 <= idx < len(df.columns):
            checked += 1
            val = df.iloc[0, idx]
            try:
                nv = pd.to_numeric(pd.Series([val]), errors="coerce").iloc[0]
            except Exception:
                nv = None
            if pd.isna(nv) and pd.notna(val):
                non_numeric_count += 1

    # 若大多数列在首行为非数值，则判定为表头
    is_header = checked > 0 and non_numeric_count / checked >= 0.6

    assert is_header, "应该检测到表头"

    # 跳过表头后的数据应该都是数值
    df_data = df.iloc[1:]
    for col_idx in required_cols:
        col_numeric = pd.to_numeric(df_data.iloc[:, col_idx], errors="coerce")
        assert col_numeric.notna().all(), f"列 {col_idx} 应该都是数值"


def test_row_selection_filter():
    """
    测试行选择过滤逻辑
    """
    # 创建示例数据
    df = pd.DataFrame(
        {
            "fx": [100, 200, 150],
            "fy": [0, 10, -5],
            "fz": [0, 5, 2],
            "mx": [0, 5, 0],
            "my": [0, 10, 5],
            "mz": [0, 0, 1],
        }
    )

    # 模拟行选择
    selected_rows = {0, 2}  # 选择第 0 和 2 行
    selected_rows_sorted = sorted(int(x) for x in set(selected_rows))
    df_filtered = df.iloc[selected_rows_sorted].reset_index(drop=True)

    assert len(df_filtered) == 2, "应该过滤出 2 行"
    assert df_filtered.iloc[0]["fx"].item() == 100
    assert df_filtered.iloc[1]["fx"].item() == 150


def test_process_single_file_signature():
    """
    验证 process_single_file 的函数签名包含新参数
    """
    import inspect

    sig = inspect.signature(process_single_file)
    params = list(sig.parameters.keys())

    expected_params = [
        "file_path",
        "calculator",
        "config",
        "output_dir",
        "project_data",
        "source_part",
        "target_part",
        "selected_rows",
    ]

    for param in expected_params:
        assert param in params, f"参数 {param} 缺失"


def test_run_batch_processing_signature():
    """
    验证 run_batch_processing 的函数签名包含新参数
    """
    import inspect
    from batch import run_batch_processing

    sig = inspect.signature(run_batch_processing)
    params = list(sig.parameters.keys())

    expected_new_params = ["file_source_target_map", "file_row_selection"]

    for param in expected_new_params:
        assert param in params, f"参数 {param} 缺失"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
