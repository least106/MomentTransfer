import numpy as np
import pytest

from src.data_loader import CoordSystemDefinition, FrameConfiguration
from src.physics import AeroCalculator


def make_frame(q=1.0, s=1.0, b=1.0, c=1.0, moment_center=None):
    coord = CoordSystemDefinition.from_dict(
        {
            "Orig": [0, 0, 0],
            "X": [1, 0, 0],
            "Y": [0, 1, 0],
            "Z": [0, 0, 1],
        }
    )
    if moment_center is None:
        moment_center = [0.0, 0.0, 0.0]
    return FrameConfiguration(
        part_name="P",
        coord_system=coord,
        moment_center=moment_center,
        c_ref=c,
        b_ref=b,
        q=q,
        s_ref=s,
    )


def test_safe_divide_scalar_zero_warns():
    cfg = make_frame()
    calc = AeroCalculator(cfg)

    num = np.array([1.0, 2.0, 3.0])
    with pytest.warns(UserWarning):
        out = calc._safe_divide(num, 0.0)

    assert np.allclose(out, np.zeros_like(num))


def test_safe_divide_array_masking():
    cfg = make_frame()
    calc = AeroCalculator(cfg)

    num = np.array([[2.0, 4.0, 6.0]])
    denom = np.array([1.0, 0.0, 2.0])
    with pytest.warns(UserWarning):
        out = calc._safe_divide(num, denom)

    # 第二列应被屏蔽为0
    assert out.shape == (1, 3)
    assert out[0, 1] == 0.0
    # 其他列应正常除法
    assert out[0, 0] == pytest.approx(2.0)
    assert out[0, 2] == pytest.approx(3.0)


def test_validate_and_fix_rotation_and_r_target():
    cfg = make_frame()
    calc = AeroCalculator(cfg)

    # 故意置为非法 rotation_matrix 并修复
    calc.rotation_matrix = np.array([1.0, 2.0, 3.0])
    calc._validate_and_fix_R()
    assert isinstance(calc.rotation_matrix, np.ndarray)
    assert calc.rotation_matrix.shape == (3, 3)

    # 故意置为包含 NaN 的 r_target
    calc.r_target = np.array([np.nan, np.nan, np.nan])
    calc._validate_and_fix_r_target()
    assert isinstance(calc.r_target, np.ndarray)
    assert calc.r_target.shape == (3,)


def test_process_batch_shape_mismatch_raises():
    cfg = make_frame()
    calc = AeroCalculator(cfg)

    forces = np.array([[1.0, 0.0, 0.0]])
    moments = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    with pytest.raises(ValueError):
        calc.process_batch(forces, moments)


def test_process_frame_with_zero_q_returns_zero_coeffs():
    # q 为 0 时，系数应全部为 0，并发出警告
    cfg = make_frame(q=0.0, s=1.0)
    calc = AeroCalculator(cfg)

    with pytest.warns(UserWarning):
        res = calc.process_frame([1.0, 0.0, 0.0], [0.0, 0.0, 0.0])

    assert res.coeff_force == [0.0, 0.0, 0.0]
    assert res.coeff_moment == [0.0, 0.0, 0.0]
