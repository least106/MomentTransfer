import numpy as np
from typing import List

# 基础向量工具
def to_numpy_vec(vec: List[float]) -> np.ndarray:
    """辅助函数：将列表转换为 Numpy 数组"""
    return np.array(vec, dtype=float)

def normalize(vec: np.ndarray) -> np.ndarray:
    """
    归一化向量 (Normalization)。
    确保坐标轴向量长度为 1，防止旋转矩阵缩放变形。
    
    Raises:
        ValueError: 当输入向量为零向量时抛出异常
    """
    norm = np.linalg.norm(vec)
    if norm < 1e-10:  # 使用小阈值避免数值精度问题
        raise ValueError(f"无法归一化零向量或接近零的向量: {vec}，模长: {norm}")
    return vec / norm

# 矩阵构建与旋转逻辑
def construct_basis_matrix(x: List[float], y: List[float], z: List[float]) -> np.ndarray:
    """
    构建基向量矩阵 (3x3)。
    输入：三个轴的方向向量
    输出：Numpy矩阵，每一行是一个基向量
    
    Raises:
        ValueError: 当输入向量为零或基向量不正交时抛出异常
    """
    vx = normalize(to_numpy_vec(x))
    vy = normalize(to_numpy_vec(y))
    vz = normalize(to_numpy_vec(z))
    
    # 检查基向量的正交性（可选但推荐）
    # 正交向量的点积应接近 0
    xy_dot = abs(np.dot(vx, vy))
    yz_dot = abs(np.dot(vy, vz))
    zx_dot = abs(np.dot(vz, vx))
    
    orthogonality_threshold = 0.1  # 允许一定误差
    if xy_dot > orthogonality_threshold or yz_dot > orthogonality_threshold or zx_dot > orthogonality_threshold:
        import warnings
        warnings.warn(
            f"基向量可能不正交：X·Y={xy_dot:.4f}, Y·Z={yz_dot:.4f}, Z·X={zx_dot:.4f}。"
            f"这可能导致坐标变换不准确。",
            UserWarning
        )
    
    return np.array([vx, vy, vz])

def compute_rotation_matrix(source_basis: np.ndarray, target_basis: np.ndarray) -> np.ndarray:
    """
    计算从源坐标系到目标坐标系的旋转矩阵 R。
    
    数学原理 (Linear Algebra):
    V_target = R · V_source
    推导公式: R = Target_Basis · Source_Basis.T
    """
    # 矩阵乘法：目标基向量矩阵 x 源基向量矩阵的转置
    return np.dot(target_basis, source_basis.T)

# 空间位置与投影逻辑 
def compute_moment_arm_global(source_origin: List[float], target_moment_center: List[float]) -> np.ndarray:
    """
    计算力臂矢量 r (在全局/绝对坐标系下)。
    
    对应笔记: "力矩转移"示意图
    数学公式: r = Source_Origin - Target_Center
    物理意义: 从“目标矩心(新)”指向“力的作用点(旧)”的矢量。
    """
    p_src = to_numpy_vec(source_origin)
    p_tgt = to_numpy_vec(target_moment_center)
    return p_src - p_tgt

def project_vector_to_frame(vec_global: np.ndarray, frame_basis: np.ndarray) -> np.ndarray:
    """
    将全局坐标系下的向量投影到特定坐标系（如目标坐标系）。
    
    用途:
    我们需要计算 r x F，但 r 是在全局坐标系算出来的，F 是在目标坐标系下的。
    必须先把 r 投影到目标坐标系 (Target Frame)，才能进行叉乘。
    """
    return np.dot(frame_basis, vec_global)