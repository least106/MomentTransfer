import numpy as np
import pytest

from src.data_loader import FrameConfiguration
from src.physics import AeroCalculator


def make_simple_frame(part_name="P", q=100.0, s=10.0, b=2.0, c=1.0):
    coord = {"Orig": [0, 0, 0], "X": [1, 0, 0], "Y": [0, 1, 0], "Z": [0, 0, 1]}
    data = {
        "PartName": part_name,
        "CoordSystem": coord,
        "MomentCenter": [0, 0, 0],
        "Cref": c,
        "Bref": b,
        "Q": q,
        "S": s,
    }
    return FrameConfiguration.from_dict(data)


def test_process_batch_accepts_length3_vectors():
    fc = make_simple_frame()
    calc = AeroCalculator(fc)

    forces = [100.0, 0.0, 0.0]
    moments = [0.0, 0.0, 0.0]

    res = calc.process_batch(forces, moments)
    # 结果应为 (1,3) 的数组
    assert res["force_transformed"].shape == (1, 3)
    # 力系数 = F / (q * S) = 100 / (100*10) = 0.1
    assert np.allclose(res["coeff_force"][0, 0], 100.0 / (fc.q * fc.s_ref))


def test_process_batch_shape_mismatch_raises():
    fc = make_simple_frame()
    calc = AeroCalculator(fc)

    forces = np.zeros((2, 3))
    moments = np.zeros((1, 3))

    with pytest.raises(ValueError):
        calc.process_batch(forces, moments)


def test_process_batch_wrong_length_vector_raises():
    fc = make_simple_frame()
    calc = AeroCalculator(fc)

    forces = [1.0, 2.0]  # 错误长度
    moments = [0.0, 0.0]

    with pytest.raises(ValueError):
        calc.process_batch(forces, moments)


def test_safe_divide_scalar_zero_warns():
    fc = make_simple_frame()
    calc = AeroCalculator(fc)

    num = np.array([1.0, 2.0, 3.0])
    with pytest.warns(UserWarning):
        out = calc._safe_divide(num, 0.0)
    assert np.allclose(out, np.zeros_like(num))


def test_safe_divide_vector_zero_masking():
    fc = make_simple_frame()
    calc = AeroCalculator(fc)

    num = np.ones((2, 3)) * 2.0
    denom = np.array([1.0, 0.0, 2.0])

    with pytest.warns(UserWarning):
        out = calc._safe_divide(num, denom)

    # 中间列（index=1）应被置为 0
    assert np.allclose(out[:, 1], 0.0)
    # 其他列按 safe 除法计算
    assert np.allclose(out[:, 0], 2.0 / 1.0)


def test_cache_exceptions_do_not_raise(monkeypatch):
    # 模拟 get_config 返回启用缓存，但缓存接口抛异常的场景
    import src.physics as physics_mod

    class BadCache:
        def get_rotation_matrix(self, *a, **k):
            raise RuntimeError("cache get failed")

        def set_rotation_matrix(self, *a, **k):
            raise RuntimeError("cache set failed")

        def get_transformation(self, *a, **k):
            raise RuntimeError("cache get failed")

        def set_transformation(self, *a, **k):
            raise RuntimeError("cache set failed")

    def fake_get_config():
        class C:
            pass

        c = C()
        c.cache = C()
        c.cache.enabled = True
        c.cache.cache_types = ["rotation", "transformation"]
        c.cache.max_entries = 10
        c.cache.precision_digits = 3
        return c

    monkeypatch.setattr(physics_mod, "get_config", fake_get_config)
    monkeypatch.setattr(
        physics_mod, "get_rotation_cache", lambda *_: BadCache()
    )
    monkeypatch.setattr(
        physics_mod, "get_transformation_cache", lambda *_: BadCache()
    )

    # 应该不会抛出异常（内部回退为直接计算）
    fc = make_simple_frame()
    calc = AeroCalculator(fc)
    res = calc.process_batch([1, 0, 0], [0, 0, 0])
    assert res["force_transformed"].shape == (1, 3)


def test_cache_malformed_shape_fallback(monkeypatch):
    import src.physics as physics_mod

    class BadCacheMalformed:
        # 返回错误形状
        def get_rotation_matrix(self, *a, **k):
            return np.array([1.0, 0.0, 0.0])

        def set_rotation_matrix(self, *a, **k):
            return None

        def get_transformation(self, *a, **k):
            return np.array([[1.0, 0.0]])

        def set_transformation(self, *a, **k):
            return None

    def fake_get_config():
        class C:
            pass

        c = C()
        c.cache = C()
        c.cache.enabled = True
        c.cache.cache_types = ["rotation", "transformation"]
        c.cache.max_entries = 10
        c.cache.precision_digits = 3
        return c

    monkeypatch.setattr(physics_mod, "get_config", fake_get_config)
    monkeypatch.setattr(
        physics_mod, "get_rotation_cache", lambda *_: BadCacheMalformed()
    )
    monkeypatch.setattr(
        physics_mod, "get_transformation_cache", lambda *_: BadCacheMalformed()
    )

    fc = make_simple_frame()
    calc = AeroCalculator(fc)
    res = calc.process_batch([1, 0, 0], [0, 0, 0])
    # 确认回退后仍返回正确形状且没有异常
    assert res["force_transformed"].shape == (1, 3)
