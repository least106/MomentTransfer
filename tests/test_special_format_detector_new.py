from pathlib import Path

import io
import os
import pytest

from src import special_format_detector as sfd


def test_read_text_file_lines_fallback(tmp_path):
    p = tmp_path / "weird.txt"
    # 写入对 utf-8 无效但 latin-1 可读的字节序列
    p.write_bytes(b"\xff\xfeABC\nAnother\n")
    lines = sfd._read_text_file_lines(p, max_lines=2)
    assert len(lines) == 2


def test_tokens_and_line_checks():
    assert sfd._tokens_looks_like_header(["alpha", "foo"]) is True
    assert sfd._tokens_looks_like_header([]) is False

    # metadata line
    assert sfd.is_metadata_line("Key: value") is True
    assert sfd.is_metadata_line("") is False
    # short Chinese single token not metadata
    assert sfd.is_metadata_line("描述") is False
    # longer Chinese considered metadata
    assert sfd.is_metadata_line("这是一个较长的中文描述行超过二十个字符啊") is True

    # summary lines
    assert sfd.is_summary_line("CLa something") is True
    assert sfd.is_summary_line("1.0 CLa") is False

    # data lines
    assert sfd.is_data_line("1.23 4 5") is True
    assert sfd.is_data_line("abc def") is False


def test_is_part_name_line_variants():
    header = "Alpha CL CD"
    assert sfd.is_part_name_line("Wing", next_line=header) is True

    # if line itself looks like header -> False
    assert sfd.is_part_name_line("Alpha CL") is False

    # long Chinese description with header next -> False
    long_ch = "这是一个非常长的中文描述文本超过二十个字符"
    assert sfd.is_part_name_line(long_ch, next_line=header) is False

    # short text without next line -> True
    assert sfd.is_part_name_line("ShortName") is True


def test_looks_like_special_format_basic(tmp_path):
    # csv suffix -> False
    p1 = tmp_path / "a.csv"
    p1.write_text("x")
    assert sfd.looks_like_special_format(p1) is False

    # supported ext -> True
    p2 = tmp_path / "b.mtfmt"
    p2.write_text("nothing")
    assert sfd.looks_like_special_format(p2) is True

    # text file containing header keywords and a non-metadata non-data line
    p3 = tmp_path / "c.txt"
    p3.write_text("Some description\nAlpha CL CD\n1.0 2.0 3.0\n")
    assert sfd.looks_like_special_format(p3) is True

    # non-existent file with unknown extension -> False (触发读取异常分支)
    assert sfd.looks_like_special_format(Path(tmp_path / "nope.unknown")) is False
