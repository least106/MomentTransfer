import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from src.cli_helpers import load_project_calculator
from gui import BatchProcessThread


def test_gui_background_thread_processing(tmp_path, qtbot=None):
    # 创建 QApplication（若测试运行环境中尚未创建）
    _app = QApplication.instance() or QApplication([])

    # 使用项目自带的配置加载计算器
    project_data, calculator = load_project_calculator("data/input.json")
    # 确保 calculator 包含 cfg 引用以兼容新版实现
    calculator.cfg = project_data

    # 创建一个简单 CSV
    csv_file = tmp_path / "g_sample.csv"
    csv_file.write_text("1,2,3,0.1,0.2,0.3\n4,5,6,0.4,0.5,0.6\n")

    data_config = {
        "skip_rows": 0,
        "columns": {"fx": 0, "fy": 1, "fz": 2, "mx": 3, "my": 4, "mz": 5},
        "passthrough": [],
    }

    thread = BatchProcessThread(
        calculator, [csv_file], tmp_path, data_config, registry_db=None
    )
    thread.start()
    # 等待线程结束（最长 5 秒）
    finished = thread.wait(5000)
    assert finished, "后台线程未在超时内完成"

    # 检查输出文件（模式 *_result_*.csv）
    found = list(tmp_path.glob("*_result_*.csv"))
    assert len(found) >= 1
