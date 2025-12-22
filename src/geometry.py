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

    basis = np.array([vx, vy, vz])

    # 进一步检查基矩阵的线性相关性（行列式接近零表示基向量线性相关 -> 奇异矩阵）
    det = np.linalg.det(basis)
    if abs(det) < 1e-6:
        raise ValueError(f"基矩阵接近奇异（行列式={det:.3e}），基向量可能线性相关或退化。")

    return basis

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

def euler_angles_to_basis(roll_deg: float, pitch_deg: float, yaw_deg: float) -> np.ndarray:
    """
    将欧拉角转换为 3x3 基向量矩阵 (X, Y, Z 轴向量)。
    旋转顺序假设为: Yaw (Z) -> Pitch (Y) -> Roll (X) (航空常用顺序)
    
    :param roll_deg: 滚转角 (如上反角)
    :param pitch_deg: 俯仰角 (如安装角)
    :param yaw_deg: 偏航角 (如后掠角)
    :return: 3x3 矩阵，行0=X轴向量, 行1=Y轴向量, 行2=Z轴向量
    """
    r = np.radians(roll_deg)
    p = np.radians(pitch_deg)
    y = np.radians(yaw_deg)

    # 旋转矩阵构建
    # Rz (Yaw)
    Rz = np.array([
        [np.cos(y), -np.sin(y), 0],
        [np.sin(y),  np.cos(y), 0],
        [0,          0,         1]
    ])
    
    # Ry (Pitch)
    Ry = np.array([
        [np.cos(p),  0, np.sin(p)],
        [0,          1, 0],
        [-np.sin(p), 0, np.cos(p)]
    ])
    
    # Rx (Roll)
    Rx = np.array([
        [1, 0,          0],
        [0, np.cos(r), -np.sin(r)],
        [0, np.sin(r),  np.cos(r)]
    ])

    # 复合旋转 R = Rz * Ry * Rx
    # 注意：这里的基向量是列向量概念，或者是将全局坐标转到局部。
    # 我们需要的是：在全局坐标系下，局部坐标轴指向哪里。
    # 这等同于旋转矩阵的 列 (Columns)。
    R = Rz @ Ry @ Rx
    
    # R 的第一列是 X轴，第二列是 Y轴，第三列是 Z轴
    x_axis = R[:, 0]
    y_axis = R[:, 1]
    z_axis = R[:, 2]
    
    return np.array([x_axis, y_axis, z_axis])

