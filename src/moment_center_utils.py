"""力矩中心坐标转换与验证工具。

用于在 Part 坐标系和全局坐标系之间转换力矩中心坐标，
并验证两种定义的一致性。
"""

from typing import Tuple
import numpy as np


def transform_point_to_global(
    point_in_part: np.ndarray,
    coord_system_origin: np.ndarray,
    coord_system_matrix: np.ndarray,
) -> np.ndarray:
    """将 Part 坐标系中的点转换到全局坐标系。
    
    Args:
        point_in_part: Part 坐标系中的点坐标 [x, y, z]
        coord_system_origin: Part 坐标系原点在全局坐标系中的位置
        coord_system_matrix: 3x3 旋转矩阵（列向量为 Part 坐标系的基向量）
    
    Returns:
        全局坐标系中的点坐标
    """
    # 全局坐标 = 原点 + 旋转矩阵 @ Part坐标
    return coord_system_origin + coord_system_matrix @ point_in_part


def transform_point_to_part(
    point_in_global: np.ndarray,
    coord_system_origin: np.ndarray,
    coord_system_matrix: np.ndarray,
) -> np.ndarray:
    """将全局坐标系中的点转换到 Part 坐标系。
    
    Args:
        point_in_global: 全局坐标系中的点坐标 [x, y, z]
        coord_system_origin: Part 坐标系原点在全局坐标系中的位置
        coord_system_matrix: 3x3 旋转矩阵（列向量为 Part 坐标系的基向量）
    
    Returns:
        Part 坐标系中的点坐标
    """
    # Part坐标 = 旋转矩阵^T @ (全局坐标 - 原点)
    return coord_system_matrix.T @ (point_in_global - coord_system_origin)


def validate_moment_center_consistency(
    mc_in_part: np.ndarray,
    mc_in_global: np.ndarray,
    coord_system_origin: np.ndarray,
    coord_system_matrix: np.ndarray,
    tolerance: float = 1e-6,
) -> Tuple[bool, float]:
    """验证两种力矩中心定义的一致性。
    
    Args:
        mc_in_part: MomentCenterInPartCoordSystem
        mc_in_global: MomentCenterInGlobalCoordSystem
        coord_system_origin: Part 坐标系原点在全局坐标系中的位置
        coord_system_matrix: 3x3 旋转矩阵
        tolerance: 允许的误差范围（默认 1e-6）
    
    Returns:
        (is_consistent, error_norm): 是否一致，以及误差的范数
    """
    # 将 Part 坐标转换为全局坐标
    mc_global_from_part = transform_point_to_global(
        mc_in_part, coord_system_origin, coord_system_matrix
    )
    
    # 计算差异
    diff = mc_global_from_part - mc_in_global
    error_norm = np.linalg.norm(diff)
    
    is_consistent = error_norm < tolerance
    
    return is_consistent, error_norm


def compute_missing_moment_center(
    mc_in_part: np.ndarray = None,
    mc_in_global: np.ndarray = None,
    coord_system_origin: np.ndarray = None,
    coord_system_matrix: np.ndarray = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """根据提供的一个力矩中心计算另一个。
    
    Args:
        mc_in_part: MomentCenterInPartCoordSystem（可选）
        mc_in_global: MomentCenterInGlobalCoordSystem（可选）
        coord_system_origin: Part 坐标系原点
        coord_system_matrix: 3x3 旋转矩阵
    
    Returns:
        (mc_in_part, mc_in_global): 两个力矩中心坐标（都已计算）
    
    Raises:
        ValueError: 如果两个都未提供，或缺少坐标系信息
    """
    if mc_in_part is None and mc_in_global is None:
        raise ValueError("必须提供至少一个力矩中心定义")
    
    if coord_system_origin is None or coord_system_matrix is None:
        raise ValueError("必须提供坐标系原点和旋转矩阵")
    
    if mc_in_part is not None and mc_in_global is None:
        # 从 Part 坐标计算全局坐标
        mc_in_global = transform_point_to_global(
            mc_in_part, coord_system_origin, coord_system_matrix
        )
    elif mc_in_global is not None and mc_in_part is None:
        # 从全局坐标计算 Part 坐标
        mc_in_part = transform_point_to_part(
            mc_in_global, coord_system_origin, coord_system_matrix
        )
    # 如果两个都提供了，直接返回（验证由调用者负责）
    
    return mc_in_part, mc_in_global
