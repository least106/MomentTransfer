import warnings
import pytest

from src import geometry


def test_construct_basis_zero_vector_raises():
    x = [0.0, 0.0, 0.0]
    y = [0.0, 1.0, 0.0]
    z = [0.0, 0.0, 1.0]
    with pytest.raises(ValueError):
        geometry.construct_basis_matrix(x, y, z)


def test_construct_basis_non_orthogonal_warns_and_strict_raises():
    x = [1.0, 0.0, 0.0]
    # y 与 x 完全相同，非正交
    _y = [1.0, 0.0, 0.0]
    z = [0.0, 0.0, 1.0]

    # 使用稍微非正交但不退化的 y 向量以触发 warning 而不致奇异
    y2 = [0.99, 0.01, 0.0]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        basis = geometry.construct_basis_matrix(
            x, y2, z, strict=False, orthogonalize=False
        )
        assert basis.shape == (3, 3)
        assert any("基向量可能不正交" in str(wi.message) for wi in w)

    # 严格模式应抛出异常
    with pytest.raises(ValueError):
        geometry.construct_basis_matrix(
            x, y2, z, strict=True, orthogonalize=False
        )
