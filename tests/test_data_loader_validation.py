import pytest

from src.data_loader import FrameConfiguration


def base_coord():
    return {"Orig": [0, 0, 0], "X": [1, 0, 0], "Y": [0, 1, 0], "Z": [0, 0, 1]}


def make_frame_dict(**overrides):
    d = {
        "PartName": "p",
        "CoordSystem": base_coord(),
        "MomentCenter": [0, 0, 0],
        "Q": 1.0,
        "S": 1.0,
    }
    d.update(overrides)
    return d


def test_missing_partname_raises():
    d = make_frame_dict()
    d.pop("PartName")
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(d)


def test_missing_coordsys_raises():
    d = make_frame_dict()
    d.pop("CoordSystem")
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(d)


def test_invalid_moment_center_length():
    d = make_frame_dict(MomentCenter=[0, 0])
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(d)


def test_missing_q_raises():
    d = make_frame_dict()
    d.pop("Q")
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(d)


def test_missing_s_raises():
    d = make_frame_dict()
    d.pop("S")
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(d)


def test_non_numeric_q_raises():
    d = make_frame_dict(Q="not-a-number")
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(d)


def test_negative_cref_raises():
    d = make_frame_dict(Cref=-1.0)
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(d)
