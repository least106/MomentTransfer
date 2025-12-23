import numpy as np
import warnings
from dataclasses import dataclass
from typing import List, Dict, Union

# 保持原有的 import
from src.data_loader import ProjectData
from src import geometry


@dataclass
class AeroResult:
    # 保持原有的单点结果类不变，用于兼容 GUI 单点调试
    force_transformed: List[float]
    moment_transformed: List[float]
    coeff_force: List[float]
    coeff_moment: List[float]


class AeroCalculator:
    def __init__(self, config: ProjectData):
        self.cfg = config

        # --- 几何初始化 (保持不变) ---
        src = self.cfg.source_coord
        tgt = self.cfg.target_config.coord_system
        self.basis_source = geometry.construct_basis_matrix(src.x_axis, src.y_axis, src.z_axis)
        self.basis_target = geometry.construct_basis_matrix(tgt.x_axis, tgt.y_axis, tgt.z_axis)
        self.R_matrix = geometry.compute_rotation_matrix(self.basis_source, self.basis_target)
        # 计算力臂时优先使用 Source 的 MomentCenter（如果定义），否则退回到 Source 的 origin
        source_moment_ref = self.cfg.source_config.moment_center if self.cfg.source_config.moment_center is not None else src.origin
        self.r_global = geometry.compute_moment_arm_global(
            source_origin=source_moment_ref,
            target_moment_center=self.cfg.target_config.moment_center
        )
        self.r_target = geometry.project_vector_to_frame(self.r_global, self.basis_target)

    def process_frame(self, force_raw: List[float], moment_raw: List[float]) -> AeroResult:
        """保持原有单点方法，用于 GUI 或简单测试"""
        # 调用下面的批量方法，但传入单行数据
        f_arr = np.array([force_raw])
        m_arr = np.array([moment_raw])
        results = self.process_batch(f_arr, m_arr)

        return AeroResult(
            force_transformed=results['force_transformed'][0].tolist(),
            moment_transformed=results['moment_transformed'][0].tolist(),
            coeff_force=results['coeff_force'][0].tolist(),
            coeff_moment=results['coeff_moment'][0].tolist()
        )

    def process_batch(self, forces: np.ndarray, moments: np.ndarray) -> Dict[str, np.ndarray]:
        """
        [新增] 高性能批处理方法
        输入:
            forces: (N, 3) Numpy Array
            moments: (N, 3) Numpy Array
        输出:
            Dictionary containing (N, 3) arrays
        """
        # 1. 批量旋转 (Matrix Multiplication)
        # 公式: F_new = (R @ F_old.T).T  或者更高效的 F_old @ R.T
        # R_matrix 是 (3,3), forces 是 (N,3)
        F_rotated = np.dot(forces, self.R_matrix.T)
        M_rotated = np.dot(moments, self.R_matrix.T)

        # 2. 批量移轴 (Moment Transfer)
        # delta_M = r x F
        # r_target 是 (3,), F_rotated 是 (N,3)。Numpy 会自动广播 r_target
        M_transfer = np.cross(self.r_target, F_rotated)

        # 3. 结果汇总
        F_final = F_rotated
        M_final = M_rotated + M_transfer

        # 4. 无量纲化
        q = self.cfg.target_config.q
        s = self.cfg.target_config.s_ref
        b = self.cfg.target_config.b_ref
        c = self.cfg.target_config.c_ref
        denom_force = q * s

        # 如果动压或面积为零，则无法计算任何系数
        if np.isclose(denom_force, 0.0):
            warnings.warn("动压(q) 或 参考面积 s_ref 为零，无法计算系数，已将力和力矩系数设为零。", UserWarning)
            C_F = np.zeros_like(F_final)
            C_M = np.zeros_like(M_final)
        else:
            C_F = F_final / denom_force

            # 创建并缓存不同轴参考长度系数向量（Roll->b, Pitch->c, Yaw->b）
            if not hasattr(self, "_moment_length_vector"):
                # 对可能的 None 值提供退路，避免创建包含 None 的数组
                b_val = float(b) if (b is not None) else 0.0
                c_val = float(c) if (c is not None) else 0.0
                self._moment_length_vector = np.array([b_val, c_val, b_val], dtype=float)

            # 根据当前的动压与参考长度计算力矩系数分母
            denom_moment = denom_force * self._moment_length_vector

            # 防止 denom_moment 中存在 0 导致除零，定位这些分量并对其单独处理
            zero_mask = np.isclose(denom_moment, 0.0)
            if np.any(zero_mask):
                warnings.warn(
                    "参考长度向量 (b_ref/c_ref) 中存在 0 或未定义值，相关轴向的力矩系数将被设为 0 以避免除以零。",
                    UserWarning
                )

            # 计算时使用安全分母（将为 0 的位置暂时设为 1 避免除零），随后将对应系数置为 0
            safe_denom = denom_moment.copy()
            safe_denom[zero_mask] = 1.0

            C_M = M_final / safe_denom

            if np.any(zero_mask):
                # zero_mask 是长度为3的布尔数组，按列屏蔽
                C_M[:, zero_mask] = 0.0

        return {
            "force_transformed": F_final,
            "moment_transformed": M_final,
            "coeff_force": C_F,
            "coeff_moment": C_M
        }