import numpy as np
import warnings
import logging
from dataclasses import dataclass
from typing import List, Dict, Union, Optional

# 保持原有的 import
from src.data_loader import ProjectData, FrameConfiguration
from src import geometry
from src.cache import get_rotation_cache, get_transformation_cache
from src.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class AeroResult:
    # 保持原有的单点结果类不变，用于兼容 GUI 单点调试
    force_transformed: List[float]
    moment_transformed: List[float]
    coeff_force: List[float]
    coeff_moment: List[float]


class AeroCalculator:
    def __init__(
        self,
        config: Union[ProjectData, FrameConfiguration],
        *,
        source_part: Optional[str] = None,
        source_variant: int = 0,
        target_part: Optional[str] = None,
        target_variant: int = 0,
    ):
        """
        初始化 AeroCalculator。

        参数支持多种用法以保持向后兼容：
        - 传入一个 `ProjectData`：使用其第一个 source/target，或通过 `source_part`/`target_part` 指定特定 part/variant。
        - 传入 `FrameConfiguration`：被视为 target 配置（source 将使用 target 的坐标系作为回退，保持旧行为）。
        - 也可以直接传入两个 `FrameConfiguration`（通过在外部先获得）并分别创建计算器。
        """
        # 支持传入单个 FrameConfiguration（视为 target）或完整的 ProjectData
        if isinstance(config, ProjectData):
            project: ProjectData = config
            # 使用 ProjectData 时若未显式提供 target_part：
            # - 若仅包含单个 Target part，则自动选取该 part（便于测试与简单项目）；
            # - 若包含多个 Target part，则默认选取第一个并记录警告（保持向后兼容，同时鼓励在 CLI 中显式传入）。
            if target_part is None:
                if len(project.target_parts) == 1:
                    target_part = next(iter(project.target_parts.keys()))
                else:
                    import warnings
                    warnings.warn(
                        "ProjectData 包含多个 Target part，未显式指定 target_part，将使用第一个 Part。建议在 CLI/脚本中显式指定 --target-part/--target-variant。",
                        UserWarning,
                    )
                    target_part = next(iter(project.target_parts.keys()))
            # 选择 source frame（可选）
            if source_part is not None:
                source_frame = project.get_source_part(source_part, source_variant)
            else:
                source_frame = project.source_config

            # 选择 target frame（已确保不为 None）
            target_frame = project.get_target_part(target_part, target_variant)
        elif isinstance(config, FrameConfiguration):
            # 仅提供单个 FrameConfiguration：把它视为 target_frame，source 使用同一配置的坐标系（向后兼容）
            source_frame = config
            target_frame = config
        else:
            raise TypeError("AeroCalculator 的第一个参数必须是 ProjectData 或 FrameConfiguration")

        self.source_frame = source_frame
        self.target_frame = target_frame

        # --- 几何初始化（带缓存支持）---
        src = self.source_frame.coord_system
        tgt = self.target_frame.coord_system
        self.basis_source = geometry.construct_basis_matrix(src.x_axis, src.y_axis, src.z_axis)
        self.basis_target = geometry.construct_basis_matrix(tgt.x_axis, tgt.y_axis, tgt.z_axis)
        
        # 尝试从缓存获取旋转矩阵，如果缓存未命中则计算
        config = get_config()
        if config.cache.enabled and 'rotation' in config.cache.cache_types:
            rotation_cache = get_rotation_cache(config.cache.max_entries)
            self.R_matrix = rotation_cache.get_rotation_matrix(
                self.basis_source,
                self.basis_target,
                config.cache.precision_digits
            )
            if self.R_matrix is None:
                self.R_matrix = geometry.compute_rotation_matrix(self.basis_source, self.basis_target)
                rotation_cache.set_rotation_matrix(
                    self.basis_source,
                    self.basis_target,
                    self.R_matrix,
                    config.cache.precision_digits
                )
                logger.debug("旋转矩阵缓存未命中，已计算并缓存")
            else:
                logger.debug("旋转矩阵缓存命中")
        else:
            self.R_matrix = geometry.compute_rotation_matrix(self.basis_source, self.basis_target)

        # 计算力臂时优先使用 Source 的 MomentCenter（如果定义），否则退回到 Source 的 origin
        source_moment_ref = self.source_frame.moment_center if self.source_frame.moment_center is not None else src.origin
        self.r_global = geometry.compute_moment_arm_global(
            source_origin=source_moment_ref,
            target_moment_center=self.target_frame.moment_center,
        )
        
        # 尝试从缓存获取转换结果
        if config.cache.enabled and 'transformation' in config.cache.cache_types:
            transformation_cache = get_transformation_cache(config.cache.max_entries)
            self.r_target = transformation_cache.get_transformation(
                self.basis_target,
                self.r_global,
                config.cache.precision_digits
            )
            if self.r_target is None:
                self.r_target = geometry.project_vector_to_frame(self.r_global, self.basis_target)
                transformation_cache.set_transformation(
                    self.basis_target,
                    self.r_global,
                    self.r_target,
                    config.cache.precision_digits
                )
                logger.debug("力臂转换缓存未命中，已计算并缓存")
            else:
                logger.debug("力臂转换缓存命中")
        else:
            self.r_target = geometry.project_vector_to_frame(self.r_global, self.basis_target)

        # 构造时验证 target 必需字段
        if self.target_frame.moment_center is None:
            raise ValueError("目标 variant 必须包含 MomentCenter 字段（长度为3的列表）")
        if self.target_frame.q is None:
            raise ValueError("目标 variant 必须包含动压 Q（数值）")
        if self.target_frame.s_ref is None:
            raise ValueError("目标 variant 必须包含参考面积 S（数值）")

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

        # 4. 无量纲化（使用选定的 target_frame）
        q = getattr(self.target_frame, 'q', None)
        s = getattr(self.target_frame, 's_ref', None)
        b = getattr(self.target_frame, 'b_ref', None)
        c = getattr(self.target_frame, 'c_ref', None)
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