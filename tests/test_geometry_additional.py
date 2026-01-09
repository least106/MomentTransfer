import numpy as np
import warnings
import pytest

from src.geometry import (
    normalize,
    construct_basis_matrix,
    compute_rotation_matrix,
    compute_moment_arm_global,
    project_vector_to_frame,
    euler_angles_to_basis,
    ZERO_VECTOR_THRESHOLD,
)


def test_normalize_zero_raises():
    with pytest.raises(ValueError):
        normalize(np.array([0.0, 0.0, 0.0]))


def test_construct_basis_non_orthogonal_warn_and_strict():
    x = [1.0, 0.0, 0.0]
    # y 与 x 有轻微非正交分量
    y = [0.02, 1.0, 0.0]
    z = [0.0, 0.0, 1.0]

    # 非 strict 模式下应当发出警告而不是抛出
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        basis = construct_basis_matrix(
            x, y, z, orthogonality_threshold=0.01, strict=False, orthogonalize=False
        )
        assert len(w) >= 1
        assert basis.shape == (3, 3)

    # strict=True 时应抛出 ValueError
    with pytest.raises(ValueError):
        construct_basis_matrix(
            x, y, z, orthogonality_threshold=0.01, strict=True, orthogonalize=False
        )


def test_construct_basis_orthogonalize_success():
    # 使用 orthogonalize=True 可以修正轻微不正交
    x = [1.0, 0.0, 0.0]
    y = [0.02, 1.0, 0.0]
    z = [0.0, 0.0, 1.0]

    basis = construct_basis_matrix(
        x, y, z, orthogonality_threshold=0.01, orthogonalize=True
    )
    # 检查正交性：任意两行点积接近 0
    assert abs(np.dot(basis[0], basis[1])) < 1e-6
    assert abs(np.dot(basis[1], basis[2])) < 1e-6
    assert abs(np.dot(basis[2], basis[0])) < 1e-6


def test_compute_rotation_matrix_identity_and_mapping():
    # identity source/target -> R 应为单位矩阵
    src = np.eye(3)
    tgt = np.eye(3)
    R = compute_rotation_matrix(src, tgt)
    assert np.allclose(R, np.eye(3))

    # 更一般情形：R @ src == tgt
    angle = 90.0
    tgt_basis = euler_angles_to_basis(0.0, 0.0, angle)
    src_basis = euler_angles_to_basis(0.0, 0.0, 0.0)
    R2 = compute_rotation_matrix(src_basis, tgt_basis)
    assert np.allclose(R2.dot(src_basis), tgt_basis)


def test_euler_angles_to_basis_yaw_90():
    b = euler_angles_to_basis(0.0, 0.0, 90.0)
    # 对应第一列 (X轴) 应指向全局 Y，第二列 (Y轴) 指向 -X
    assert np.allclose(b[0], np.array([0.0, 1.0, 0.0]))
    assert np.allclose(b[1], np.array([-1.0, 0.0, 0.0]))
    assert np.allclose(b[2], np.array([0.0, 0.0, 1.0]))


def test_compute_moment_arm_and_projection():
    src = [1.0, 2.0, 3.0]
    tgt = [0.0, 1.0, 3.0]
    r = compute_moment_arm_global(src, tgt)
    assert np.allclose(r, np.array([1.0, 1.0, 0.0]))

    # 投影到单位基矩阵应保持不变
    frame = np.eye(3)
    proj = project_vector_to_frame(r, frame)
    assert np.allclose(proj, r)
