import numpy as np

from src.data_loader import FrameConfiguration
from src.physics import AeroCalculator


def make_simple_frame():
    cfg = {
        "PartName": "test",
        "CoordSystem": {"Orig": [0, 0, 0], "X": [1, 0, 0], "Y": [0, 1, 0], "Z": [0, 0, 1]},
        "MomentCenter": [0, 0, 0],
        "Q": 1.0,
        "S": 1.0,
        "Cref": 1.0,
        "Bref": 1.0,
    }
    return FrameConfiguration.from_dict(cfg)


def test_coeff_equals_force_when_unit_refs():
    """当参考值均为 1 且坐标系为单位矩阵时，力系数应等于变换后的力。"""
    frame = make_simple_frame()
    calc = AeroCalculator(frame)

    forces = np.array([[1.0, 2.0, 3.0]])
    moments = np.array([[0.0, 0.0, 0.0]])

    res = calc.process_batch(forces, moments)

    assert res["force_transformed"].shape == (1, 3)
    assert res["coeff_force"].shape == (1, 3)
    assert np.allclose(res["coeff_force"], res["force_transformed"])  # 因为 q*s == 1


def test_transfer_moments_zero_r():
    frame = make_simple_frame()
    calc = AeroCalculator(frame)
    calc.r_target = np.array([0.0, 0.0, 0.0])

    F_rot = np.array([[1.0, 0.0, 0.0]])
    mt = calc._transfer_moments(F_rot)

    assert mt.shape == (1, 3)
    assert np.allclose(mt, np.zeros((1, 3)))
