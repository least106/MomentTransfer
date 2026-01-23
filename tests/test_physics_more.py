import numpy as np
import warnings
import pytest

from src.data_loader import CoordSystemDefinition, FrameConfiguration
from src.physics import AeroCalculator


def make_frame(q=1.0, s_ref=1.0, b_ref=1.0, c_ref=1.0):
    coord = CoordSystemDefinition(
        origin=[0, 0, 0], x_axis=[1, 0, 0], y_axis=[0, 1, 0], z_axis=[0, 0, 1]
    )
    return FrameConfiguration(
        part_name="T",
        coord_system=coord,
        moment_center=[0, 0, 0],
        c_ref=c_ref,
        b_ref=b_ref,
        q=q,
        s_ref=s_ref,
    )


def test_safe_divide_scalar_zero_warning():
    frame = make_frame(q=1.0, s_ref=1.0)
    calc = AeroCalculator(frame)

    num = np.array([1.0, 2.0, 3.0])
    with pytest.warns(UserWarning):
        res = calc._safe_divide(num, 0.0)
    assert np.all(res == 0.0)


def test_safe_divide_vector_with_zero_column():
    frame = make_frame()
    calc = AeroCalculator(frame)

    num = np.array([[2.0, 4.0, 6.0]])
    denom = np.array([2.0, 0.0, 3.0])
    with pytest.warns(UserWarning):
        res = calc._safe_divide(num, denom)
    # 第二列应被置为 0
    assert res.shape == (1, 3)
    assert res[0, 1] == 0.0


def test_rotate_and_transfer_moments_and_compute_coeffs():
    frame = make_frame(q=0.0, s_ref=1.0, b_ref=2.0, c_ref=3.0)
    calc = AeroCalculator(frame)

    # 覆盖 rotation_matrix 与 r_target 以简化断言
    calc.rotation_matrix = np.eye(3)
    calc.r_target = np.array([0.0, 0.0, 0.0])

    forces = np.array([[1.0, 0.0, 0.0]])
    moments = np.array([[0.0, 0.0, 0.0]])

    F_rot = calc._rotate_vectors(forces)
    assert np.allclose(F_rot, forces)

    M_transfer = calc._transfer_moments(F_rot)
    assert np.allclose(M_transfer, np.zeros_like(F_rot))

    # q == 0 将导致系数为 0 并发出警告
    with pytest.warns(UserWarning):
        C_F, C_M = calc._compute_coefficients(F_rot, M_transfer)
    assert np.all(C_F == 0)
    assert np.all(C_M == 0)


def test_process_batch_shape_checks():
    frame = make_frame()
    calc = AeroCalculator(frame)

    # 错误的形状应抛出 ValueError
    with pytest.raises(ValueError):
        calc.process_batch([1.0, 2.0], [[0, 0, 0]])

    with pytest.raises(ValueError):
        calc.process_batch([[1, 0, 0]], [[0, 0]])


def test_process_frame_returns_aeroresult():
    frame = make_frame()
    calc = AeroCalculator(frame)
    res = calc.process_frame([1.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    assert hasattr(res, "force_transformed")
    assert hasattr(res, "coeff_force")
