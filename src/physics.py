import numpy as np
from dataclasses import dataclass
from typing import List, Tuple

# 引入我们刚才写好的模块
from src.data_loader import ProjectData
from src import geometry


# 定义计算结果结构体
@dataclass
class AeroResult:
    """存储最终的计算结果"""
    force_transformed: List[float]  # 变换后的力 [Fx, Fy, Fz] (N)
    moment_transformed: List[float]  # 变换后的力矩 [Mx, My, Mz] (N*m)
    coeff_force: List[float]  # 力系数 [Cx, Cy, Cz]
    coeff_moment: List[float]  # 力矩系数 [Cl, Cm, Cn]


# 核心物理计算类
class AeroCalculator:
    def __init__(self, config: ProjectData):
        self.cfg = config

        # 1. 预计算几何关系 (只需做一次)
        # 提取配置
        src = self.cfg.source_coord
        tgt = self.cfg.target_config.coord_system

        # 构建基向量矩阵 (3x3)
        self.basis_source = geometry.construct_basis_matrix(src.x_axis, src.y_axis, src.z_axis)
        self.basis_target = geometry.construct_basis_matrix(tgt.x_axis, tgt.y_axis, tgt.z_axis)

        # 计算旋转矩阵 R (Source -> Target)
        self.R_matrix = geometry.compute_rotation_matrix(self.basis_source, self.basis_target)

        # 计算力臂矢量 r (Global Frame) -> 对应笔记 delta M = r x F
        self.r_global = geometry.compute_moment_arm_global(
            source_origin=src.origin,
            target_moment_center=self.cfg.target_config.moment_center
        )

        # 将力臂投影到 Target Frame (为了做叉乘)
        self.r_target = geometry.project_vector_to_frame(self.r_global, self.basis_target)

    def process_frame(self, force_raw: List[float], moment_raw: List[float]) -> AeroResult:
        """
        处理单帧数据 (One Frame / One Data Point)
        输入: 原始力(F_src)和力矩(M_src)
        输出: 转换后的结果对象
        """
        # --- 步骤 A: 旋转 (Rotation) ---
        F_src = np.array(force_raw)
        M_src = np.array(moment_raw)

        # [核心公式] F_new = R * F_old
        F_rotated = np.dot(self.R_matrix, F_src)
        M_rotated = np.dot(self.R_matrix, M_src)

        # --- 步骤 B: 移轴 / 力矩转移 (Moment Transfer) ---
        # 对应笔记: delta_M = r x F
        # 注意: 这里的 r 和 F 都已经在 Target Frame 下了
        M_transfer = np.cross(self.r_target, F_rotated)

        # 总力矩 = 旋转后的原力矩 + 移轴产生的附加力矩
        M_final = M_rotated + M_transfer
        F_final = F_rotated

        # --- 步骤 C: 无量纲化 (Non-dimensionalization) ---
        # 对应笔记: Coeff = Value / (Q * S * Ref)

        q = self.cfg.target_config.q
        s = self.cfg.target_config.s_ref
        b = self.cfg.target_config.b_ref
        c = self.cfg.target_config.c_ref

        denom_force = q * s

        if denom_force == 0:
            # 防止除以零崩溃，返回全零
            return AeroResult(
                force_transformed=F_final.tolist(),
                moment_transformed=M_final.tolist(),
                coeff_force=[0.0, 0.0, 0.0],
                coeff_moment=[0.0, 0.0, 0.0]
            )

        # 计算力系数 [Cx, Cy, Cz]
        C_F = F_final / denom_force

        # 计算力矩系数 [Cl, Cm, Cn]
        # 航空惯例:
        #   Roll (Mx) -> 展长 b
        #   Pitch (My) -> 弦长 c
        #   Yaw (Mz) -> 展长 b
        C_M = np.zeros(3)
        C_M[0] = M_final[0] / (denom_force * b)
        C_M[1] = M_final[1] / (denom_force * c)
        C_M[2] = M_final[2] / (denom_force * b)

        return AeroResult(
            force_transformed=F_final.tolist(),
            moment_transformed=M_final.tolist(),
            coeff_force=C_F.tolist(),
            coeff_moment=C_M.tolist()
        )