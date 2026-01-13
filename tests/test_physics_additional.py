import numpy as np
import pytest

from src.physics import AeroCalculator, AeroResult
from src.data_loader import FrameConfiguration, CoordSystemDefinition


def make_frame(q=2.0, s_ref=5.0, b_ref=2.0, c_ref=3.0):
    coord = CoordSystemDefinition(
        origin=[0, 0, 0], x_axis=[1, 0, 0], y_axis=[0, 1, 0], z_axis=[0, 0, 1]
    )
    return FrameConfiguration(
        part_name="P",
        coord_system=coord,
        moment_center=[0.0, 0.0, 0.0],
        c_ref=c_ref,
        b_ref=b_ref,
        q=q,
        s_ref=s_ref,
    )


def test_safe_divide_scalar_zero_warn():
    f = make_frame(q=1.0, s_ref=1.0)
    calc = AeroCalculator(f)

    with pytest.warns(UserWarning):
        out = calc._safe_divide(
            np.array([1.0, 2.0, 3.0]), 0.0, warn_msg="test"
        )

    assert np.all(out == 0.0)


def test_safe_divide_array_with_zero():
    f = make_frame()
    calc = AeroCalculator(f)

    numer = np.array([[2.0, 4.0, 6.0]])
    denom = np.array([2.0, 0.0, 3.0])

    with pytest.warns(UserWarning):
        res = calc._safe_divide(numer, denom)

    assert res.shape == numer.shape
    np.testing.assert_allclose(res, np.array([[1.0, 0.0, 2.0]]))


def test_process_frame_identity_transformation_and_coeffs():
    # 使用相同的 frame 作为 source/target -> 旋转矩阵为单位矩阵，力臂为零
    f = make_frame(q=2.0, s_ref=5.0, b_ref=2.0, c_ref=3.0)
    calc = AeroCalculator(f)

    force = [10.0, 0.0, 0.0]
    moment = [1.0, 2.0, 3.0]

    res: AeroResult = calc.process_frame(force, moment)

    # 1) 变换后力应该保持不变（单位旋转）
    assert np.allclose(res.force_transformed, force)

    # 2) 力系数 = F / (q * S)
    denom = f.q * f.s_ref
    expected_cf = np.array(force) / denom
    np.testing.assert_allclose(res.coeff_force, expected_cf)

    # 3) 力矩系数按轴分别除以 denom * [b, c, b]
    moment_length = np.array([f.b_ref, f.c_ref, f.b_ref], dtype=float)
    expected_cm = np.array(moment) / (denom * moment_length)
    np.testing.assert_allclose(res.coeff_moment, expected_cm)
