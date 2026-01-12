from pathlib import Path
import textwrap
import pandas as pd
import numpy as np

import pytest

from src import special_format_parser as sfp
from src.data_loader import FrameConfiguration, CoordSystemDefinition, ProjectData


def write_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def make_frame_for_part(name="P", q=100.0, s=10.0):
    coord = CoordSystemDefinition(
        origin=[0, 0, 0], x_axis=[1, 0, 0], y_axis=[0, 1, 0], z_axis=[0, 0, 1]
    )
    return FrameConfiguration(
        part_name=name,
        coord_system=coord,
        moment_center=[0, 0, 0],
        c_ref=1.0,
        b_ref=1.0,
        q=q,
        s_ref=s,
    )


def test_is_line_helpers():
    assert sfp.is_metadata_line("")
    assert sfp.is_metadata_line("说明: 这是注释")
    assert sfp.is_data_line("1.0 2.0 3.0")
    assert not sfp.is_data_line("Alpha CL CD")
    assert sfp.is_summary_line("CLa 0.1")
    assert sfp.is_part_name_line("Wing1", "Alpha CL CD")


def test_get_part_names_and_parse(tmp_path):
    p = tmp_path / "sample.mtfmt"
    content = textwrap.dedent(
        """
    Project info: 测试文件

    WingA
    Alpha CL CD Cm Cx Cy Cz
    0.0 0.1 0.2 0.0 1.0 2.0 3.0
    1.0 0.2 0.3 0.0 1.1 2.1 3.1

    Fuselage
    Alpha CL CD Cm Cx Cy Cz
    0.0 0.05 0.06 0.0 0.5 0.6 0.7
    """
    )
    write_file(p, content)

    parts = sfp.get_part_names(p)
    assert "WingA" in parts
    assert "Fuselage" in parts

    data = sfp.parse_special_format_file(p)
    assert "WingA" in data and isinstance(data["WingA"], pd.DataFrame)
    assert data["WingA"].shape[0] == 2


def test_chinese_part_name_and_gbk_file(tmp_path):
    # 中文 part 名，UTF-8 编码
    p = tmp_path / "chinese.mtfmt"
    content = textwrap.dedent(
        """
    项目说明：测试中文 part 名

    翼面
    Alpha CL CD Cm Cx Cy Cz
    0.0 0.1 0.2 0.0 1.0 2.0 3.0
    """
    )
    write_file(p, content)

    parts = sfp.get_part_names(p)
    assert "翼面" in parts

    data = sfp.parse_special_format_file(p)
    assert "翼面" in data

    # 现在创建一个 GBK 编码的文件，内容类似
    p2 = tmp_path / "gbk.mtfmt"
    content2 = "机身\nAlpha CL CD Cm Cx Cy Cz\n0.0 0.1 0.2 0.0 1.0 2.0 3.0\n"
    # 写入 GBK 编码
    p2.write_bytes(content2.encode("gbk"))

    # 读取时应能回退并解析（不抛出异常）
    parts2 = sfp.get_part_names(p2)
    assert "机身" in parts2

    parsed2 = sfp.parse_special_format_file(p2)
    assert "机身" in parsed2


def test_process_special_format_file_success(tmp_path):
    p = tmp_path / "ok.mtfmt"
    content = textwrap.dedent(
        """
    WingX
    Alpha CL CD Cm Cx Cy Cz/FN CMx CMy CMz
    0.0 0.1 0.2 0.0 1.0 2.0 3.0 0.0 0.1 0.2
    1.0 0.2 0.3 0.0 1.1 2.1 3.1 0.0 0.2 0.3
    """
    )
    write_file(p, content)

    # 构造 ProjectData，包含目标 part
    frame = make_frame_for_part("WingX")
    proj = ProjectData(source_parts={"WingX": [frame]}, target_parts={"WingX": [frame]})

    out_dir = tmp_path / "out"
    outputs, report = sfp.process_special_format_file(
        p, proj, out_dir, return_report=True
    )
    assert len(outputs) == 1
    assert report and report[0]["status"] == "success"
    # 输出文件存在
    assert Path(outputs[0]).exists()


def test_process_special_format_file_skip_missing_target(tmp_path):
    p = tmp_path / "missing.mtfmt"
    content = textwrap.dedent(
        """
    MissingPart
    Alpha CL CD Cm Cx Cy Cz/FN CMx CMy CMz
    0.0 0.1 0.2 0.0 1.0 2.0 3.0 0.0 0.1 0.2
    """
    )
    write_file(p, content)

    # source 存在，但将其显式映射到不存在的 target，用于触发 target_missing
    frame = make_frame_for_part("MissingPart")
    proj = ProjectData(source_parts={"MissingPart": [frame]}, target_parts={"Other": [frame]})

    out_dir = tmp_path / "out2"
    outputs, report = sfp.process_special_format_file(
        p, proj, out_dir, return_report=True, part_target_mapping={"MissingPart": "NoSuchTarget"}
    )
    assert len(outputs) == 0
    assert (
        report
        and report[0]["status"] == "skipped"
        and report[0]["reason"] == "target_missing"
    )


def test_process_special_format_file_missing_columns_skips(tmp_path):
    p = tmp_path / "missingcols.mtfmt"
    content = textwrap.dedent(
        """
    PartA
    Alpha CL CD Cm Cx Cy
    0.0 0.1 0.2 0.0 1.0 2.0
    """
    )
    write_file(p, content)

    frame = make_frame_for_part("PartA")
    proj = ProjectData(source_parts={"PartA": [frame]}, target_parts={"PartA": [frame]})
    out_dir = tmp_path / "out3"
    outputs, report = sfp.process_special_format_file(
        p, proj, out_dir, return_report=True
    )
    assert len(outputs) == 0
    assert report and any(r.get("reason") == "missing_columns" for r in report)


from pathlib import Path

import pandas as pd
import pytest

from src import special_format_parser as sfp


def test_is_metadata_summary_and_data_line():
    assert sfp.is_metadata_line("")
    assert sfp.is_metadata_line("计算坐标系:X向后、Y向右")
    assert not sfp.is_metadata_line("BODY")

    assert sfp.is_summary_line("CLa Cdmin CmCL")
    assert not sfp.is_summary_line("1.0 2.0 3.0")

    assert sfp.is_data_line("0.00 1.23 4.56")
    assert not sfp.is_data_line("Alpha CL CD")


def test_is_part_name_line_with_next_header():
    line = "BODY"
    next_line = "Alpha CL CD Cm Cx Cy Cz"
    assert sfp.is_part_name_line(line, next_line)

    # single short line without header still qualifies
    assert sfp.is_part_name_line("WING")


def test_get_part_names_and_parse(tmp_path: Path):
    content = "\n".join(
        [
            "计算坐标系:X向后",
            "",
            "quanji",
            "Alpha CL CD Cm Cx Cy Cz",
            "-2.00 -0.10625 0.03809 0.00626 0.03059 -0.01136 0.01894",
            "0.00 0.00652 0.03443 -0.02196 0.02898 -0.01158 -0.00198",
            "CLa Cdmin CmCL",
            "",
            "BODY",
            "Alpha CL CD Cm Cx Cy Cz",
            "-2.00 -0.03869 0.02362 -0.00061 0.02961 -0.01279 0.00106",
        ]
    )

    p = tmp_path / "sample.mtfmt"
    p.write_text(content, encoding="utf-8")

    parts = sfp.get_part_names(p)
    assert "quanji" in parts and "BODY" in parts

    parsed = sfp.parse_special_format_file(p)
    assert "quanji" in parsed and "BODY" in parsed
    df_q = parsed["quanji"]
    assert isinstance(df_q, pd.DataFrame)
    # numeric conversion: ensure columns are numeric or at least convertible
    assert df_q.shape[0] == 2


def test_looks_like_special_format_by_extension(tmp_path: Path):
    p = tmp_path / "x.mtfmt"
    p.write_text("dummy", encoding="utf-8")
    assert sfp.looks_like_special_format(p)


def test_looks_like_special_format_skips_csv(tmp_path: Path):
    content = "\n".join(
        [
            "Alpha,CL,CD,Cm",
            "0,0.1,0.2,0.0",
            "1,0.2,0.3,0.0",
        ]
    )
    p = tmp_path / "plain.csv"
    p.write_text(content, encoding="utf-8")

    assert not sfp.looks_like_special_format(p)


def test_parse_skips_mismatched_rows_and_summary(tmp_path: Path):
    # header has 4 cols but a data row only has 3 -> should be skipped
    lines = [
        "PARTA",
        "Alpha CL CD Cm",
        "1.0 2.0 3.0 4.0",
        "2.0 3.0 4.0",  # mismatched
        "CLa Cdmin",
    ]
    p = tmp_path / "mismatch.mtfmt"
    p.write_text("\n".join(lines), encoding="utf-8")
    parsed = sfp.parse_special_format_file(p)
    assert "PARTA" in parsed
    assert parsed["PARTA"].shape[0] == 1
