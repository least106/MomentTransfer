import numpy as np
import warnings

from src.data_loader import CoordSystemDefinition, FrameConfiguration
from src.physics import AeroCalculator


def _make_frame_obj():
    cs = CoordSystemDefinition(origin=[0, 0, 0], x_axis=[1, 0, 0], y_axis=[0, 1, 0], z_axis=[0, 0, 1])
    # 构造一个 q=0, s_ref=0 的 FrameConfiguration（用于测试零分母处理）
    fc = FrameConfiguration(part_name='P', coord_system=cs, moment_center=[0, 0, 0], c_ref=1.0, b_ref=1.0, q=0.0, s_ref=0.0)
    return fc


def test_aerocalc_zero_q_s_yields_zero_coeffs_and_warns():
    fc = _make_frame_obj()
    # 传入单个 FrameConfiguration（会被视为 source 和 target）
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        calc = AeroCalculator(fc)
        res = calc.process_frame([1.0, 0.0, 0.0], [0.0, 0.0, 0.0])

        # 系数应该被设为零（安全除法保护）
        assert all(abs(x) < 1e-12 for x in res.coeff_force)
        assert all(abs(x) < 1e-12 for x in res.coeff_moment)
        assert any('动压' in str(r.message) or '分母' in str(r.message) for r in w if hasattr(r, 'message') or hasattr(r, 'category')) or len(w) >= 1
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
