import numpy as np

from src import geometry


def test_project_vector_identity_basis():
    # 身份基：投影应保持不变
    basis = np.eye(3)
    v = np.array([1.0, 2.0, -3.0])
    proj = geometry.project_vector_to_frame(v, basis)
    assert np.allclose(proj, v)


def test_basis_reconstruction_roundtrip():
    # 使用欧拉角生成基，投影再重构应回到原始全局向量
    basis = geometry.euler_angles_to_basis(
        roll_deg=10, pitch_deg=20, yaw_deg=30
    )
    v_global = np.array([0.5, -1.2, 2.0])
    # 在目标坐标系下的分量
    v_coords = geometry.project_vector_to_frame(v_global, basis)
    # 从分量重构回全局：v_global_recon = basis.T @ v_coords
    v_recon = basis.T.dot(v_coords)
    assert np.allclose(v_recon, v_global)


def test_compute_rotation_matrix_consistency():
    # 验证 compute_rotation_matrix 与基投影的一致性
    A = np.eye(3)
    B = geometry.euler_angles_to_basis(0, 0, 90)  # 绕 Z 轴 90 度

    # 任意在 A 坐标系下的分量
    a_coords = np.array([1.0, 0.0, 0.0])
    # 通过旋转矩阵将 A->B
    R = geometry.compute_rotation_matrix(A, B)
    b_via_R = R.dot(a_coords)

    # 另一种方法：先把 a_coords 转为全局 (A 是单位基, 全局即 a_coords)，再投影到 B
    v_global = a_coords
    b_via_proj = geometry.project_vector_to_frame(v_global, B)

    assert np.allclose(b_via_R, b_via_proj)
