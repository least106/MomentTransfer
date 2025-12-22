"""
测试 geometry 模块的几何计算功能
"""
import pytest
import numpy as np
from src.geometry import (
    normalize, 
    construct_basis_matrix, 
    compute_rotation_matrix,
    compute_moment_arm_global,
    project_vector_to_frame
)


class TestNormalize:
    """测试向量归一化函数"""
    
    def test_normalize_standard_vector(self):
        """测试标准向量的归一化"""
        vec = np.array([3.0, 4.0, 0.0])
        normalized = normalize(vec)
        # 长度应为 1
        assert np.isclose(np.linalg.norm(normalized), 1.0)
        # 方向应保持不变
        assert np.allclose(normalized, [0.6, 0.8, 0.0])
    
    def test_normalize_unit_vector(self):
        """测试已经归一化的向量"""
        vec = np.array([1.0, 0.0, 0.0])
        normalized = normalize(vec)
        assert np.allclose(normalized, vec)
    
    def test_normalize_zero_vector_raises_error(self):
        """测试零向量应抛出异常"""
        vec = np.array([0.0, 0.0, 0.0])
        with pytest.raises(ValueError, match="无法归一化零向量"):
            normalize(vec)
    
    def test_normalize_near_zero_vector(self):
        """测试接近零的向量"""
        vec = np.array([1e-12, 1e-12, 1e-12])
        with pytest.raises(ValueError, match="无法归一化零向量"):
            normalize(vec)


class TestConstructBasisMatrix:
    """测试基向量矩阵构建"""
    
    def test_standard_basis(self):
        """测试标准正交基"""
        x = [1.0, 0.0, 0.0]
        y = [0.0, 1.0, 0.0]
        z = [0.0, 0.0, 1.0]
        
        basis = construct_basis_matrix(x, y, z)
        
        # 应该是单位矩阵
        expected = np.eye(3)
        assert np.allclose(basis, expected)
    
    def test_scaled_vectors(self):
        """测试缩放后的向量（应自动归一化）"""
        x = [2.0, 0.0, 0.0]
        y = [0.0, 3.0, 0.0]
        z = [0.0, 0.0, 5.0]
        
        basis = construct_basis_matrix(x, y, z)
        
        # 每行的模长应为 1
        for i in range(3):
            assert np.isclose(np.linalg.norm(basis[i]), 1.0)
    
    def test_zero_vector_raises_error(self):
        """测试零向量输入应抛出异常"""
        x = [0.0, 0.0, 0.0]  # 零向量
        y = [0.0, 1.0, 0.0]
        z = [0.0, 0.0, 1.0]
        
        with pytest.raises(ValueError, match="无法归一化零向量"):
            construct_basis_matrix(x, y, z)
    
    def test_non_orthogonal_warning(self):
        """测试非正交向量应发出警告"""
        x = [1.0, 0.0, 0.0]
        y = [0.5, 1.0, 0.0]  # 与 x 不正交
        z = [0.0, 0.0, 1.0]
        
        with pytest.warns(UserWarning, match="基向量可能不正交"):
            basis = construct_basis_matrix(x, y, z)
            assert basis.shape == (3, 3)


class TestComputeRotationMatrix:
    """测试旋转矩阵计算"""
    
    def test_identity_rotation(self):
        """测试相同坐标系的旋转（应为单位矩阵）"""
        basis = np.eye(3)
        R = compute_rotation_matrix(basis, basis)
        assert np.allclose(R, np.eye(3))
    
    def test_90_degree_rotation_z(self):
        """测试绕 Z 轴旋转 90 度"""
        source = np.eye(3)
        # 目标系统绕 Z 轴旋转 90 度
        target = np.array([
            [0.0, 1.0, 0.0],  # X' = Y
            [-1.0, 0.0, 0.0], # Y' = -X
            [0.0, 0.0, 1.0]   # Z' = Z
        ])
        
        R = compute_rotation_matrix(source, target)
        
        # 验证旋转效果：将源坐标系的 X 轴变换到目标系
        vec_source = np.array([1.0, 0.0, 0.0])
        vec_rotated = R @ vec_source
        
        # R = Target * Source^T
        # 对于 90 度旋转，X -> -Y (在目标系中)
        expected = np.array([0.0, -1.0, 0.0])
        assert np.allclose(vec_rotated, expected, atol=1e-10)
    
    def test_rotation_matrix_properties(self):
        """测试旋转矩阵的性质（正交矩阵）"""
        source = np.eye(3)
        target = np.array([
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 0.0]
        ])
        
        R = compute_rotation_matrix(source, target)
        
        # 旋转矩阵应满足 R^T * R = I
        assert np.allclose(R.T @ R, np.eye(3), atol=1e-10)
        
        # 行列式应为 ±1
        det = np.linalg.det(R)
        assert np.isclose(abs(det), 1.0)


class TestComputeMomentArmGlobal:
    """测试力臂计算"""
    
    def test_moment_arm_calculation(self):
        """测试力臂向量的计算"""
        source_origin = [1.0, 2.0, 3.0]
        target_center = [0.0, 0.0, 0.0]
        
        r = compute_moment_arm_global(source_origin, target_center)
        
        # r = source - target
        expected = np.array([1.0, 2.0, 3.0])
        assert np.allclose(r, expected)
    
    def test_zero_moment_arm(self):
        """测试力臂为零的情况"""
        point = [1.0, 1.0, 1.0]
        r = compute_moment_arm_global(point, point)
        assert np.allclose(r, [0.0, 0.0, 0.0])


class TestProjectVectorToFrame:
    """测试向量投影到坐标系"""
    
    def test_project_to_standard_frame(self):
        """测试投影到标准坐标系"""
        vec_global = np.array([1.0, 2.0, 3.0])
        frame_basis = np.eye(3)
        
        vec_frame = project_vector_to_frame(vec_global, frame_basis)
        
        # 在标准基下投影应不变
        assert np.allclose(vec_frame, vec_global)
    
    def test_project_to_rotated_frame(self):
        """测试投影到旋转坐标系"""
        vec_global = np.array([1.0, 0.0, 0.0])
        # 坐标系绕 Z 轴旋转 90 度
        frame_basis = np.array([
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0]
        ])
        
        vec_frame = project_vector_to_frame(vec_global, frame_basis)
        
        # 全局 X 方向在旋转系中应为负 Y 方向
        expected = np.array([0.0, -1.0, 0.0])
        assert np.allclose(vec_frame, expected, atol=1e-10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
