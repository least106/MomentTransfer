import numpy as np

from src.data_loader import FrameConfiguration
from src.physics import AeroCalculator


def make_cfg(q=1.0, s=1.0, cref=0.1, bref=0.3):
    cfg = {
        "PartName": "boundary_example",
        "CoordSystem": {
            "Orig": [0, 0, 0],
            "X": [1, 0, 0],
            "Y": [0, 1, 0],
            "Z": [0, 0, 1],
        },
        "MomentCenter": [0.0, 0.0, 0.0],
        "Q": q,
        "S": s,
        "Cref": cref,
        "Bref": bref,
    }
    return FrameConfiguration.from_dict(cfg)


def test_zero_q_returns_zero_coefficients():
    """当动压 q=0 时，应返回零的无量纲系数（防止除零）"""
    frame = make_cfg(q=0.0, s=1.0)
    calc = AeroCalculator(frame)
    force = [100.0, 0.0, 0.0]
    moment = [0.0, 0.0, 0.0]
    res = calc.process_frame(force, moment)
    # coeff_force 和 coeff_moment 都应为零向量
    assert np.allclose(res.coeff_force, [0.0, 0.0, 0.0])
    assert np.allclose(res.coeff_moment, [0.0, 0.0, 0.0])


def test_identity_rotation_preserves_vectors():
    """单位坐标系下，变换前后的力和力矩在数值上应相等（忽略浮点误差）"""
    frame = make_cfg(q=100.0, s=1.0)
    calc = AeroCalculator(frame)
    force = [12.34, -5.6, 7.8]
    moment = [1.0, 2.0, 3.0]
    res = calc.process_frame(force, moment)
    # 在单位坐标系（源=目标）下，变换后的力矩应与输入一致（或非常接近）
    assert np.allclose(res.force_transformed, np.array(force), atol=1e-6)
    assert np.allclose(res.moment_transformed, np.array(moment), atol=1e-6)
