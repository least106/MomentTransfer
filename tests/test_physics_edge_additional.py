import numpy as np
import pytest

from src.data_loader import FrameConfiguration
from src.physics import AeroCalculator


def make_frame():
    cfg = {
        "PartName": "edge",
        "CoordSystem": {
            "Orig": [0, 0, 0],
            "X": [1, 0, 0],
            "Y": [0, 1, 0],
            "Z": [0, 0, 1],
        },
        "MomentCenter": [0, 0, 0],
        "Q": 1.0,
        "S": 1.0,
    }
    return FrameConfiguration.from_dict(cfg)


def test_process_batch_single_vector_broadcast():
    frame = make_frame()
    calc = AeroCalculator(frame)

    forces = [1.0, 2.0, 3.0]
    moments = [0.0, 0.0, 0.0]

    res = calc.process_batch(forces, moments)
    assert res["force_transformed"].shape == (1, 3)
    assert res["coeff_force"].shape == (1, 3)


def test_process_batch_shape_mismatch_raises():
    frame = make_frame()
    calc = AeroCalculator(frame)

    forces = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    moments = np.array([0.0, 0.0, 0.0])

    with pytest.raises(ValueError):
        calc.process_batch(forces, moments)


def test_safe_divide_column_masking():
    frame = make_frame()
    calc = AeroCalculator(frame)

    numerator = np.array([[10.0, 20.0, 30.0], [1.0, 2.0, 3.0]])
    denom = np.array([2.0, 0.0, 3.0])

    res = calc._safe_divide(numerator, denom)
    # 第二列对应分母为0，应被置为0
    assert np.allclose(res[:, 1], 0.0)
    # 其他列按正常除法
    assert np.allclose(res[:, 0], numerator[:, 0] / 2.0)
    assert np.allclose(res[:, 2], numerator[:, 2] / 3.0)
