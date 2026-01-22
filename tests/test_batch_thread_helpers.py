import os
from pathlib import Path
import pandas as pd

from gui.batch_thread import BatchProcessThread


class DummySignal:
    def __init__(self):
        self.messages = []

    def emit(self, v):
        self.messages.append(v)


def test_atomic_write_and_cleanup(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3]})
    out = tmp_path / "out.csv"

    thread = BatchProcessThread(None, [], tmp_path, {})
    # ensure the output dir exists
    tmp_path.mkdir(parents=True, exist_ok=True)

    thread._atomic_write(df, out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "a" in content


def test_handle_special_report_emits_logs(tmp_path):
    thread = BatchProcessThread(None, [], tmp_path, {})
    ds = DummySignal()
    thread.log_message = ds

    report = [
        {"status": "success", "part": "P1", "out_path": "f1.csv"},
        {"status": "skipped", "part": "P2", "reason": "no target", "message": ""},
        {"status": "error", "part": "P3", "reason": "fail", "message": "bad"},
    ]

    thread._handle_special_report(report)
    # three messages should be emitted
    assert len(ds.messages) == 3
    assert "part 'P1' 处理成功" in ds.messages[0]
    assert "被跳过" in ds.messages[1]
    assert "处理失败" in ds.messages[2]
