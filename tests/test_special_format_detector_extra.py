import os
import tempfile
from pathlib import Path

import pytest

from src import special_format_detector as sfd


def test_tokens_looks_like_header():
    assert sfd._tokens_looks_like_header(["alpha", "foo"]) is True
    assert sfd._tokens_looks_like_header(["nope"]) is False
    assert sfd._tokens_looks_like_header([]) is False


def test_is_metadata_summary_data():
    assert sfd.is_metadata_line("") is False
    assert sfd.is_metadata_line("Key: value") is True
    # 中文且短文本不视为元数据
    assert sfd.is_metadata_line("部件") is False
    # 长中文视为元数据
    long_cn = "这是一个很长的描述文本，用于测试元数据识别"
    assert sfd.is_metadata_line(long_cn) is True

    assert sfd.is_summary_line("CLa 0.1") is True
    assert sfd.is_summary_line("123 456") is False

    assert sfd.is_data_line("1.23 4.56") is True
    assert sfd.is_data_line("not a number") is False


def test_is_part_name_line_and_header_relation():
    # 当下一行是表头时，短文本应识别为 part 名
    assert sfd.is_part_name_line("Wing", next_line="Alpha CL CD") is True
    # 表头本身不应视为 part 名
    assert sfd.is_part_name_line("Alpha CL CD") is False
    # 数据行不视为 part 名
    assert sfd.is_part_name_line("1.0 2.0") is False
    # 长中文不视为 part 名
    long_cn = "这是一个超过二十个字符的中文描述，应该被视为说明文本而非部件名称"
    assert sfd.is_part_name_line(long_cn, next_line="Alpha CL CD") is False


def test__read_text_file_lines_fallback_and_max_lines(tmp_path):
    p = tmp_path / "binarystream.dat"
    # 写入一些对 utf-8 解码有问题的字节，触发降级分支
    with open(p, "wb") as fh:
        fh.write(b"\xff\xfe\n" + "部分文本\n".encode("utf-8"))

    lines = sfd._read_text_file_lines(p, max_lines=2)
    assert isinstance(lines, list)
    assert len(lines) <= 2

    # 不存在的文件应抛出 FileNotFoundError
    missing = tmp_path / "noexist.mtfmt"
    with pytest.raises(FileNotFoundError):
        sfd._read_text_file_lines(missing)


def test_looks_like_special_format_positive_and_negative(tmp_path):
    # 正例：包含表头关键词并带有非元数据的部件名行
    p = tmp_path / "test.mtfmt"
    p.write_text("Wing\nAlpha CL CD\n1.0 2.0\n")
    assert sfd.looks_like_special_format(p) is True

    # 带常见表格扩展名的文件应直接返回 False
    csv_p = tmp_path / "data.csv"
    csv_p.write_text("Alpha,CL,CD\n1,2,3\n")
    assert sfd.looks_like_special_format(csv_p) is False

    # 非存在文件或 I/O 错误时应返回 False（使用非支持后缀以触发读取）
    assert sfd.looks_like_special_format(tmp_path / "missing.xyz") is False
