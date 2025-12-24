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

    def _safe_divide(self, numerator: np.ndarray, denominator, warn_msg: str = None) -> np.ndarray:
        """安全除法，处理标量或按轴数组的分母。

        - numerator: (N, M) 或 (M,) 的数组
        - denominator: 标量或 1D 数组（长度为 M）
        当分母接近零时：发出警告并将对应结果置为 0，避免除以零或 NaN。
        """
        denom_arr = np.array(denominator, dtype=float)

        # 标量分母情况
        if denom_arr.ndim == 0:
            if np.isclose(denom_arr, 0.0):
                if warn_msg is None:
                    warnings.warn("分母为零，已将结果设为 0。", UserWarning)
                else:
                    warnings.warn(warn_msg, UserWarning)
                return np.zeros_like(numerator)
            return numerator / denom_arr

        # 数组分母情况（按轴分母，例如 moment_length_vector）
        zero_mask = np.isclose(denom_arr, 0.0)
        if np.any(zero_mask):
            if warn_msg is None:
                warnings.warn(
                    "分母向量中存在零或未定义值，相关轴的结果将被设为 0。",
                    UserWarning,
                )
            else:
                warnings.warn(warn_msg, UserWarning)

        safe_denom = np.where(zero_mask, 1.0, denom_arr)
        result = numerator / safe_denom

        # 如果 numerator 是 (N, M) 而 denom_arr 是 (M,), 则按列屏蔽
        try:
            if result.ndim == 2 and denom_arr.ndim == 1:
                result[:, zero_mask] = 0.0
            elif result.ndim == 1 and denom_arr.ndim == 1:
                result[zero_mask] = 0.0
        except Exception:
            # 若形状不匹配，回退为原始结果
            pass

        return result

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
        # 使用统一的安全除法处理标量/按轴分母的各种场景
        C_F = self._safe_divide(
            F_final,
            denom_force,
            warn_msg="动压(q) 或 参考面积 s_ref 为零，无法计算力系数，已将力系数设为 0。",
        )

        # 为不同轴创建参考长度系数向量（Roll->b, Pitch->c, Yaw->b）
        b_val = float(b) if (b is not None) else 0.0
        c_val = float(c) if (c is not None) else 0.0
        moment_length_vector = np.array([b_val, c_val, b_val], dtype=float)

        denom_moment = denom_force * moment_length_vector

        C_M = self._safe_divide(
            M_final,
            denom_moment,
            warn_msg="动压(q) 或 参考长度 b_ref/c_ref 为零，相关轴的力矩系数已设为0。",
        )

        return {
            "force_transformed": F_final,
            "moment_transformed": M_final,
            "coeff_force": C_F,
            "coeff_moment": C_M
        }