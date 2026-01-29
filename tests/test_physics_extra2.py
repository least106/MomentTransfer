import numpy as np
import pytest

from src.data_loader import CoordSystemDefinition, FrameConfiguration
from src.physics import AeroCalculator


def make_coord():
    return CoordSystemDefinition.from_dict(
        {"Orig": [0, 0, 0], "X": [1, 0, 0], "Y": [0, 1, 0], "Z": [0, 0, 1]}
    )


def make_frame(name="P", q=1.0, s_ref=1.0, b_ref=1.0, c_ref=1.0):
    coord = make_coord()
    return FrameConfiguration(
        part_name=name,
        coord_system=coord,
        moment_center=[0.0, 0.0, 0.0],
        c_ref=c_ref,
        b_ref=b_ref,
        q=q,
        s_ref=s_ref,
    )


def test_safe_divide_scalar_zero_and_vector_zero():
    f = make_frame()
    calc = AeroCalculator(f)

    num = np.array([1.0, 2.0, 3.0])
    with pytest.warns(UserWarning):
        out = calc._safe_divide(num, 0)
    assert np.all(out == 0)

    denom = np.array([1.0, 0.0, 2.0])
    num2 = np.array([[2.0, 4.0, 6.0]])
    with pytest.warns(UserWarning):
        out2 = calc._safe_divide(num2, denom)
    # second column should be zero due to denom zero
    assert out2.shape == (1, 3)
    assert out2[0, 1] == 0.0


def test_process_frame_and_batch_shapes_and_values():
    f = make_frame(q=2.0, s_ref=3.0)
    calc = AeroCalculator(f)

    res = calc.process_frame([1.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    assert hasattr(res, "force_transformed")
    assert len(res.force_transformed) == 3
    assert isinstance(res.coeff_force, list) and len(res.coeff_force) == 3

    batch = calc.process_batch(
        np.array([[1.0, 0.0, 0.0]]), np.array([[0.0, 0.0, 0.0]])
    )
    assert batch["force_transformed"].shape == (1, 3)
    assert batch["coeff_force"].shape == (1, 3)


def test_process_batch_shape_mismatch_raises():
    f = make_frame()
    calc = AeroCalculator(f)
    with pytest.raises(ValueError):
        calc.process_batch(
            np.array([1.0, 2.0, 3.0]), np.array([[1.0, 2.0, 3.0], [4, 5, 6]])
        )


def test_compute_coefficients_warns_when_q_or_s_zero():
    # q*s_ref == 0 should warn and produce zeros
    f = make_frame(q=0.0, s_ref=1.0)
    calc = AeroCalculator(f)
    F = np.array([[1.0, 0.0, 0.0]])
    M = np.array([[0.0, 0.0, 0.0]])
    with pytest.warns(UserWarning):
        C_F, C_M = calc._compute_coefficients(F, M)
    assert np.all(C_F == 0) or np.allclose(C_F, 0)
