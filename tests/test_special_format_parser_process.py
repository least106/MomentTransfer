from pathlib import Path

import numpy as np

from src import special_format_parser as sfp


class SimpleProjectData:
    def __init__(self, sources=None, targets=None):
        self.source_parts = sources or {}
        self.target_parts = targets or {}


class FakeCalc:
    def __init__(self, project_data, source_part=None, target_part=None):
        self.project_data = project_data
        self.source_part = source_part
        self.target_part = target_part

    def process_batch(self, forces, moments):
        _n = forces.shape[0]
        ft = forces + 1.0
        mt = moments + 1.0
        cf = np.zeros_like(forces)
        cm = np.zeros_like(moments)
        return {
            "force_transformed": np.array(ft),
            "moment_transformed": np.array(mt),
            "coeff_force": np.array(cf),
            "coeff_moment": np.array(cm),
        }


class FakeCalcRaise(FakeCalc):
    def process_batch(self, forces, moments):
        raise RuntimeError("processing failed")


def make_sample_content(part_name="P"):
    hdr = "Cx Cy Cz/FN CMx CMy CMz"
    rows = ["0.1 0.2 0.3 1.0 2.0 3.0", "0.4 0.5 0.6 4.0 5.0 6.0"]
    return "\n".join([part_name, hdr] + rows)


def test_process_special_format_file_success(tmp_path: Path, monkeypatch):
    p = tmp_path / "in.mtfmt"
    p.write_text(make_sample_content("PARTX"), encoding="utf-8")

    outdir = tmp_path / "out"

    project_data = SimpleProjectData(
        sources={"PARTX": [1]}, targets={"PARTX": [1]}
    )

    # replace AeroCalculator with fake
    monkeypatch.setattr(sfp, "AeroCalculator", FakeCalc)

    outputs, report = sfp.process_special_format_file(
        p, project_data, outdir, return_report=True, overwrite=True
    )

    assert isinstance(outputs, list) and len(outputs) == 1
    assert any(r.get("status") == "success" for r in report)
    # file created
    assert outputs[0].exists()


def test_process_special_format_file_no_project_data(tmp_path: Path):
    p = tmp_path / "in2.mtfmt"
    p.write_text(make_sample_content("PARTY"), encoding="utf-8")
    outdir = tmp_path / "out2"

    outputs, report = sfp.process_special_format_file(
        p, None, outdir, return_report=True
    )
    assert outputs == []
    assert any(r.get("reason") == "no_project_data" for r in report)


def test_process_special_format_file_missing_columns(tmp_path: Path):
    # header lacks required columns
    content = "\n".join(["PARTZ", "Alpha CL CD", "1.0 2.0 3.0"])
    p = tmp_path / "in3.mtfmt"
    p.write_text(content, encoding="utf-8")
    outdir = tmp_path / "out3"

    project_data = SimpleProjectData(
        sources={"PARTZ": [1]}, targets={"PARTZ": [1]}
    )
    outputs, report = sfp.process_special_format_file(
        p, project_data, outdir, return_report=True
    )
    assert outputs == []
    assert any(r.get("reason") == "missing_columns" for r in report)


def test_process_special_format_file_processing_failure(
    tmp_path: Path, monkeypatch
):
    p = tmp_path / "in4.mtfmt"
    p.write_text(make_sample_content("FAILP"), encoding="utf-8")
    outdir = tmp_path / "out4"

    project_data = SimpleProjectData(
        sources={"FAILP": [1]}, targets={"FAILP": [1]}
    )
    monkeypatch.setattr(sfp, "AeroCalculator", FakeCalcRaise)

    outputs, report = sfp.process_special_format_file(
        p, project_data, outdir, return_report=True
    )
    assert outputs == []
    assert any(r.get("reason") == "processing_failed" for r in report)
