import numpy as np
import pytest

from src.data_loader import CoordSystemDefinition, FrameConfiguration
from src.physics import AeroCalculator


def make_coord():
    return CoordSystemDefinition(
        origin=[0, 0, 0], x_axis=[1, 0, 0], y_axis=[0, 1, 0], z_axis=[0, 0, 1]
    )


def test_zero_q_produces_zero_coeffs_and_warns():
    coord = make_coord()
    # 使用 dataclass 直接构造（允许 q==0，因为 from_dict 也允许 q 为 0）
    frame = FrameConfiguration(
        part_name="P",
        coord_system=coord,
        moment_center=[0, 0, 0],
        c_ref=1.0,
        b_ref=1.0,
        q=0.0,
        s_ref=10.0,
    )

    calc = AeroCalculator(frame)

    with pytest.warns(UserWarning):
        res = calc.process_batch([10.0, 0.0, 0.0], [0.0, 0.0, 0.0])

    # 当 q==0 时，动压 * 面积 == 0，应返回系数为 0
    assert np.allclose(res["coeff_force"], 0.0)
    assert np.allclose(res["coeff_moment"], 0.0)


def test_zero_s_ref_produces_zero_coeffs_and_warns():
    coord = make_coord()
    # 直接构造 FrameConfiguration，允许 s_ref=0 测试边界（构造器并不禁止零）
    frame = FrameConfiguration(
        part_name="P",
        coord_system=coord,
        moment_center=[0, 0, 0],
        c_ref=1.0,
        b_ref=1.0,
        q=100.0,
        s_ref=0.0,
    )

    calc = AeroCalculator(frame)

    with pytest.warns(UserWarning):
        res = calc.process_batch([10.0, 0.0, 0.0], [0.0, 0.0, 0.0])

    assert np.allclose(res["coeff_force"], 0.0)
    assert np.allclose(res["coeff_moment"], 0.0)
