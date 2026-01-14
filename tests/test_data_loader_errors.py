import pytest

from src.data_loader import FrameConfiguration, ProjectData


def test_projectdata_missing_sections():
    with pytest.raises(ValueError):
        ProjectData.from_dict({})


def test_frameconfiguration_missing_momentcenter():
    data = {
        "PartName": "P",
        "CoordSystem": {
            "Orig": [0, 0, 0],
            "X": [1, 0, 0],
            "Y": [0, 1, 0],
            "Z": [0, 0, 1],
        },
        # MomentCenter missing
        "Q": 1.0,
        "S": 1.0,
    }
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(data, frame_type="Test")


def test_frameconfiguration_invalid_numeric_values():
    data = {
        "PartName": "P",
        "CoordSystem": {
            "Orig": [0, 0, 0],
            "X": [1, 0, 0],
            "Y": [0, 1, 0],
            "Z": [0, 0, 1],
        },
        "MomentCenter": [0, 0, 0],
        "Q": -5,
        "S": 1.0,
    }
    with pytest.raises(ValueError):
        FrameConfiguration.from_dict(data, frame_type="Test")
