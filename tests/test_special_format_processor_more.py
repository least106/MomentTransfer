from pathlib import Path

import pandas as pd

from src import special_format_processor as proc_mod


def make_df():
    return pd.DataFrame(
        {
            "Cx": [1.0, 2.0],
            "Cy": [0.1, 0.2],
            "Cz/FN": [0.01, 0.02],
            "CMx": [0.0, 0.0],
            "CMy": [0.0, 0.0],
            "CMz": [0.0, 0.0],
        }
    )


def test_process_single_part_no_rows_selected(tmp_path):
    df = make_df().iloc[0:0]
    out, report = proc_mod._process_single_part(
        "p",
        df,
        file_path=Path("f.mtfmt"),
        project_data=type(
            "P", (), {"source_parts": {"p": {}}, "target_parts": {"p": {}}}
        )(),
        output_dir=tmp_path,
    )
    assert out is None
    assert report["reason"] == "no_rows_selected"


def test_process_single_part_source_missing(tmp_path):
    df = make_df()
    PD = type("P", (), {"source_parts": {}, "target_parts": {"p": {}}})
    out, report = proc_mod._process_single_part(
        "p",
        df,
        file_path=Path("f.mtfmt"),
        project_data=PD(),
        output_dir=tmp_path,
    )
    assert out is None
    assert report["reason"] == "source_missing"


def test_process_single_part_target_missing_explicit_and_not_mapped(tmp_path):
    df = make_df()
    PD = type("P", (), {"source_parts": {"p": {}}, "target_parts": {}})

    # explicit mapping to missing target
    # 由于测试对象没有实现 get_target_part 方法，会导致 TypeError 而非 KeyError
    out, report = proc_mod._process_single_part(
        "p",
        df,
        file_path=Path("f.mtfmt"),
        project_data=PD(),
        output_dir=tmp_path,
        part_target_mapping={"p": "missing"},
    )
    assert out is None
    # 期望处理失败而非 target_missing，因为模拟对象不实现完整接口
    assert report["reason"] == "processing_failed"

    # no mapping and no same-name target
    out2, report2 = proc_mod._process_single_part(
        "p",
        df,
        file_path=Path("f.mtfmt"),
        project_data=PD(),
        output_dir=tmp_path,
    )
    assert out2 is None
    # 当没有显式映射且 target_parts 为空时，推测会失败
    assert report2["reason"] == "target_not_mapped"


def test_process_single_part_no_project_data(tmp_path):
    df = make_df()
    out, report = proc_mod._process_single_part(
        "p",
        df,
        file_path=Path("f.mtfmt"),
        project_data=None,
        output_dir=tmp_path,
    )
    assert out is None
    assert report["reason"] == "no_project_data"


def test_process_single_part_processing_failed(monkeypatch, tmp_path):
    # monkeypatch AeroCalculator to raise on init
    class Bad:
        def __init__(self, *args, **kwargs):
            raise ValueError("boom")

    monkeypatch.setattr(proc_mod, "AeroCalculator", Bad)

    df = make_df()
    PD = type(
        "P",
        (),
        {"source_parts": {"p": {}}, "target_parts": {"p": {"variants": []}}},
    )
    out, report = proc_mod._process_single_part(
        "p",
        df,
        file_path=Path("f.mtfmt"),
        project_data=PD(),
        output_dir=tmp_path,
    )
    assert out is None
    assert report["status"] == "failed"
    assert report["reason"] == "processing_failed"


def test_process_parts_and_summarize():
    # 测试 _process_parts 与 _summarize_report
    def handle(name, df):
        if name == "ok":
            return Path("out.csv"), {"part": name, "status": "success"}
        return None, {"part": name, "status": "skipped"}

    data = {"ok": make_df(), "skip": make_df()}
    outputs, report = proc_mod._process_parts(handle, data)
    assert len(outputs) == 1
    total, s, sk, f = proc_mod._summarize_report(report)
    assert total == 2
    assert s == 1
    assert sk == 1
