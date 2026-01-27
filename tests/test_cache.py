import numpy as np

from src.cache import (
    CacheKey,
    CacheManager,
    CalculationCache,
    RotationMatrixCache,
    TransformationCache,
    clear_all_caches,
    get_rotation_cache,
    get_transformation_cache,
)


def test_cache_key_array_to_tuple_rounding():
    arr = np.array([[1.000000001, 2.000000001], [3.0, 4.0]])
    t = CacheKey.array_to_tuple(arr, precision_digits=7)
    assert isinstance(t, tuple)
    # 精度化后应为可重复的元组
    t2 = CacheKey.array_to_tuple(arr + 1e-9, precision_digits=7)
    assert t == t2


def test_calculation_cache_get_set_and_eviction():
    c = CalculationCache(max_entries=2)
    k1 = (1,)
    k2 = (2,)
    k3 = (3,)

    assert c.get(k1) is None
    c.set(k1, "a")
    assert c.get(k1) == "a"
    c.set(k2, "b")
    # 添加第三个应触发淘汰（max_entries=2）
    c.set(k3, "c")
    # k1 为最旧项，应被弹出
    assert c.get(k1) is None
    assert c.get(k2) == "b"
    assert c.get(k3) == "c"


def test_rotation_and_transformation_cache_set_get():
    rm = RotationMatrixCache(max_entries=10)
    basis = np.eye(3)
    target = np.eye(3) * 2
    R = np.eye(3) * 0.5
    assert rm.get_rotation_matrix(basis, target) is None
    rm.set_rotation_matrix(basis, target, R)
    got = rm.get_rotation_matrix(basis, target)
    assert np.allclose(got, R)

    tc = TransformationCache(max_entries=10)
    v = np.array([1.0, 2.0, 3.0])
    res = np.array([0.1, 0.2, 0.3])
    assert tc.get_transformation(basis, v) is None
    tc.set_transformation(basis, v, res)
    got2 = tc.get_transformation(basis, v)
    assert np.allclose(got2, res)


def test_cache_manager_singleton_and_clear(monkeypatch):
    mgr = CacheManager()
    rc = mgr.get_rotation_cache(max_entries=5)
    tc = mgr.get_transformation_cache(max_entries=5)
    assert rc is mgr.get_rotation_cache()
    assert tc is mgr.get_transformation_cache()

    # 填入一些数据然后清空
    rc.set_rotation_matrix(np.eye(3), np.eye(3), np.eye(3))
    tc.set_transformation(np.eye(3), np.array([0, 0, 0]), np.array([0, 0, 0]))
    mgr.clear_all()
    assert rc.get_rotation_matrix(np.eye(3), np.eye(3)) is None
    assert tc.get_transformation(np.eye(3), np.array([0, 0, 0])) is None


def test_module_level_getters_and_clear_all():
    r = get_rotation_cache()
    t = get_transformation_cache()
    assert r is not None and t is not None
    clear_all_caches()
