import numpy as np
import pytest

from src import cache as cache_mod


def test_cachekey_array_to_tuple_rounding_and_none():
    arr = np.array([0.12345678901, 1.00000000004])
    tup = cache_mod.CacheKey.array_to_tuple(arr, precision_digits=5)
    assert isinstance(tup, tuple)
    # rounding to 5 decimals
    assert tup[0] == pytest.approx(round(arr[0], 5))
    assert tup[1] == pytest.approx(round(arr[1], 5))

    assert cache_mod.CacheKey.array_to_tuple(None) is None


def test_calculationcache_hits_misses_and_eviction():
    c = cache_mod.CalculationCache(max_entries=2)
    c.set(("k1",), 1)
    assert c.get(("k1",)) == 1
    assert c.hits == 1
    assert c.misses == 0

    # miss increments
    assert c.get(("no",)) is None
    assert c.misses == 1

    # eviction when exceeding max_entries
    c.set(("k2",), 2)
    c.set(("k3",), 3)
    assert len(c.cache) == 2
    assert ("k1",) not in c.cache

    # stats formatting
    stats = c.stats()
    assert "hits" in stats and "misses" in stats and "hit_rate" in stats

    # clear resets counts and entries
    c.clear()
    assert c.hits == 0 and c.misses == 0 and len(c.cache) == 0


def test_rotation_and_transformation_cache_operations():
    src_basis = np.eye(3)
    tgt_basis = np.eye(3) * 2
    rot = np.eye(3) * 5

    rcache = cache_mod.RotationMatrixCache(max_entries=10)
    assert rcache.get_rotation_matrix(src_basis, tgt_basis) is None
    rcache.set_rotation_matrix(src_basis, tgt_basis, rot)
    got = rcache.get_rotation_matrix(src_basis, tgt_basis)
    assert np.array_equal(got, rot)

    vec = np.array([1.0, 2.0, 3.0])
    tres = np.array([3.0, 2.0, 1.0])
    tcache = cache_mod.TransformationCache(max_entries=10)
    assert tcache.get_transformation(tgt_basis, vec) is None
    tcache.set_transformation(tgt_basis, vec, tres)
    got2 = tcache.get_transformation(tgt_basis, vec)
    assert np.array_equal(got2, tres)


def test_cache_manager_singleton_and_clear_all():
    mgr = cache_mod.CacheManager()
    # manager creates caches
    r1 = mgr.get_rotation_cache(max_entries=5)
    r2 = mgr.get_rotation_cache()
    assert r1 is r2

    t1 = mgr.get_transformation_cache(max_entries=5)
    t2 = mgr.get_transformation_cache()
    assert t1 is t2

    # populate and clear
    r1.set_rotation_matrix(np.eye(3), np.eye(3), np.eye(3))
    t1.set_transformation(np.eye(3), np.array([1, 2, 3]), np.array([1, 2, 3]))
    assert len(r1.cache) > 0 and len(t1.cache) > 0
    mgr.clear_all()
    assert len(r1.cache) == 0 and len(t1.cache) == 0


def test_module_level_helpers_and_clear_all_caches():
    # module-level singletons
    rc = cache_mod.get_rotation_cache(3)
    tc = cache_mod.get_transformation_cache(3)
    rc.set_rotation_matrix(np.eye(3), np.eye(3), np.eye(3))
    tc.set_transformation(np.eye(3), np.array([0, 0, 0]), np.array([0, 0, 0]))
    assert len(rc.cache) > 0 and len(tc.cache) > 0
    cache_mod.clear_all_caches()
    assert len(rc.cache) == 0 and len(tc.cache) == 0
