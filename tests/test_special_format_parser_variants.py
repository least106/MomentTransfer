from pathlib import Path
import textwrap

from src import special_format_parser as sfp
from src.data_loader import (
    FrameConfiguration,
    CoordSystemDefinition,
    ProjectData,
)


def write_file(path: Path, content: str, encoding="utf-8"):
    path.write_text(content, encoding=encoding)


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


def test_header_variants_czfn_and_cmx(tmp_path):
    p = tmp_path / "variants.mtfmt"
    content = textwrap.dedent(
        """
    WingV
    Alpha CL CD Cm Cx Cy Cz_FN CMx CMy CMz
    0.0 0.1 0.2 0.0 1.0 2.0 3.0 0.0 0.1 0.2
    """
    )
    write_file(p, content)

    frame = make_frame_for_part("WingV")
    proj = ProjectData(
        source_parts={"WingV": [frame]}, target_parts={"WingV": [frame]}
    )

    outputs, report = sfp.process_special_format_file(
        p, proj, tmp_path, return_report=True
    )
    assert report and report[0]["status"] == "success"
    assert len(outputs) == 1


def test_lowercase_and_underscore_variants(tmp_path):
    p = tmp_path / "variants2.mtfmt"
    # 使用小写列名和下划线替代斜杆
    content = textwrap.dedent(
        """
    PartL
    alpha cl cd cm cx cy cz_fn cmx cmy cmz
    0.0 0.1 0.2 0.0 1.0 2.0 3.0 0.0 0.1 0.2
    """
    )
    write_file(p, content)

    frame = make_frame_for_part("PartL")
    proj = ProjectData(
        source_parts={"PartL": [frame]}, target_parts={"PartL": [frame]}
    )

    outputs, report = sfp.process_special_format_file(
        p, proj, tmp_path, return_report=True
    )
    assert report and report[0]["status"] == "success"
    assert len(outputs) == 1
