import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from src import special_format_parser as parser


def test_normalize_column_mapping_variants():
    cols = ["cx", " Cz/FN ", "CmX", "alpha", "unknown_col"]
    mapping = parser._normalize_column_mapping(cols)
    assert mapping[cols[0]] == "Cx"
    assert mapping[cols[1]] == "Cz/FN"
    assert mapping[cols[2]] == "CMx"
    assert mapping[cols[3]] == "Alpha"
    assert mapping[cols[4]] == "unknown_col"


def test_extract_parts_and_finalize_creates_dataframe():
    lines = [
        "PartA",
        "Alpha CL CD",
        "1 2 3",
        "4 5 6",
        "",
        "PartB",
        "Alpha CL CD",
        "7 8 9",
        "Summary: end",
    ]

    extracted = parser._extract_parts_from_lines(lines, Path("dummy"))
    assert "PartA" in extracted
    hdr, rows = extracted["PartA"]
    assert hdr == ["Alpha", "CL", "CD"]
    assert rows == [["1", "2", "3"], ["4", "5", "6"]]

    result = {}
    parser._finalize_part("PartA", hdr, rows, result)
    assert "PartA" in result
    df = result["PartA"]
    assert isinstance(df, pd.DataFrame)
    assert df.shape[0] == 2
    # 值应被转换为数值类型
    assert pd.api.types.is_numeric_dtype(df["Alpha"])
    assert df["Alpha"].tolist() == [1.0, 4.0]


def test_parse_and_get_part_names_monkeypatched_read():
    # 使用 monkey-patched _read_text_file_lines 来避免文件 I/O
    lines = [
        "Header metadata: 测试",
        "PartX",
        "Alpha CL CD",
        "0.1 0.2 0.3",
        "PartY",
        "Alpha CL CD",
        "1 2 3",
    ]

    orig = parser._read_text_file_lines
    try:
        parser._read_text_file_lines = lambda fp: lines
        parts = parser.get_part_names(Path("ignored"))
        assert "PartX" in parts and "PartY" in parts

        parsed = parser.parse_special_format_file(Path("ignored"))
        assert "PartX" in parsed and "PartY" in parsed
        assert parsed["PartX"].shape[0] == 1
    finally:
        parser._read_text_file_lines = orig


def test_process_special_format_file_delegates(monkeypatch):
    # 创建一个假的模块并注入到 sys.modules，以便延迟导入时被发现
    fake_mod = types.SimpleNamespace(
        process_special_format_file=lambda *a, **k: {"ok": True}
    )
    sys.modules["src.special_format_processor"] = fake_mod

    try:
        ret = parser.process_special_format_file(
            Path("p"), project_data=None, output_dir=Path(".")
        )
        assert ret == {"ok": True}
    finally:
        del sys.modules["src.special_format_processor"]


from pathlib import Path

import pandas as pd
import pytest

from src import special_format_parser as sfp


def test_normalize_column_mapping_variants():
    cols = [" Cx ", "cz_fn", "CMx", "alpha", "unknown"]
    mapping = sfp._normalize_column_mapping(cols)
    assert mapping[" Cx "] == "Cx"
    assert mapping["cz_fn"] == "Cz/FN"
    assert mapping["CMx"] == "CMx"
    assert mapping["alpha"] == "Alpha"
    assert mapping["unknown"] == "unknown"


def test_parse_special_format_file_basic_and_mismatch(monkeypatch, tmp_path):
    # prepare lines: one part with header and two data lines, one malformed
    lines = [
        "PartA\n",
        "Alpha CL CD\n",
        "1 2 3\n",
        "4 5\n",  # mismatched columns, should be skipped
        "\n",
        "PartB\n",
        "Alpha CL CD\n",
        "7 8 9\n",
    ]

    monkeypatch.setattr(sfp, "_read_text_file_lines", lambda p: lines)
    result = sfp.parse_special_format_file(Path("dummy"))
    assert "PartA" in result and "PartB" in result
    assert isinstance(result["PartA"], pd.DataFrame)
    assert result["PartA"].shape[0] == 1  # second line skipped
    assert result["PartB"].shape[0] == 1


def test_get_part_names_ignores_metadata(monkeypatch):
    lines = [
        "# some metadata: author\n",
        "PartX\n",
        "Alpha CL CD\n",
        "1 2 3\n",
        "Long descriptive text that is not a part name but has Chinese 描述内容\n",
        "PartY\n",
        "Alpha CL CD\n",
        "5 6 7\n",
    ]
    monkeypatch.setattr(sfp, "_read_text_file_lines", lambda p: lines)
    parts = sfp.get_part_names(Path("dummy2"))
    assert parts == ["PartX", "PartY"]


def test_finalize_part_coerce_numeric(monkeypatch):
    result = {}
    header = ["Alpha", "CL"]
    data = [["1", "bad"], ["2", "3"]]
    sfp._finalize_part("P", header, data, result)
    df = result.get("P")
    assert df is not None
    # CL column: first row coerced to NaN
    assert pd.isna(df.loc[0, "CL"]) or isinstance(df.loc[0, "CL"], float)
