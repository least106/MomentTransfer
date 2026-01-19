"""物理计算模块：提供 `AeroCalculator` 用于坐标系之间的力/力矩变换与无量纲化。

公共 API:
- `AeroCalculator(config, source_part=None, target_part=None, ...)`
    - `process_batch(forces, moments)`：批量计算，输入/输出均为 (N,3) 数组。
    - `process_frame(force, moment)`：单点计算接口，返回 `AeroResult`。

示例:
    >>> from src.data_loader import FrameConfiguration
    >>> from src.physics import AeroCalculator
    >>> cfg = FrameConfiguration.from_dict({...})
    >>> calc = AeroCalculator(cfg)
    >>> res = calc.process_batch([[1,0,0]], [[0,0,0]])
    >>> res['force_transformed'].shape
    (1, 3)
"""

import logging
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import numpy as np

from src import geometry
from src.cache import get_rotation_cache, get_transformation_cache
from src.config import get_config
from src.data_loader import FrameConfiguration, ProjectData

logger = logging.getLogger(__name__)
# 该模块包含物理学惯例命名（如 R, F_rotated 等），接受非 snake_case 命名风格
# pylint: disable=invalid-name,too-many-arguments


@dataclass
class AeroResult:
    """单点计算结果容器。"""

    force_transformed: List[float]
    moment_transformed: List[float]
    coeff_force: List[float]
    coeff_moment: List[float]


@dataclass
class AeroInitOptions:
    """可选的初始化参数集合，用于简化 `AeroCalculator` 的构造调用。

    使用时可一次性传入多个可选项，调用者仍可通过关键字参数覆盖其中的值。
    """

    source_part: Optional[str] = None
    source_variant: int = 0
    target_part: Optional[str] = None
    target_variant: int = 0
    cache_provider: Optional[Any] = None
    cache_cfg: Optional[Any] = None


class AeroCalculator:
    """核心的 Aero 计算器：在不同坐标系间变换力/力矩并计算无量纲系数。

    设计目标：
    - 支持批量计算（`process_batch`）以提高性能。
    - 支持单点计算（`process_frame`）以支持交互式和简单场景。
    - 将缓存、旋转、移轴与无量纲化逻辑拆分为小方法，便于测试与维护。
    """

    def __init__(
        self,
        config: Union[ProjectData, FrameConfiguration],
        *,
        # 保持向后兼容的关键字参数，同时支持通过 `init_options` 批量传入
        source_part: Optional[str] = None,
        source_variant: int = 0,
        target_part: Optional[str] = None,
        target_variant: int = 0,
        cache_provider: Optional[Any] = None,
        cache_cfg: Optional[Any] = None,
        init_options: Optional[Any] = None,
    ):
        """
        初始化 AeroCalculator。

        参数用法：
        - 传入 `ProjectData`：使用其 source/target，或通过 `source_part`/`target_part` 指定特定 part/variant。
        - 传入 `FrameConfiguration`：同时用作 source 和 target 坐标系。
        """
        # 支持传入 FrameConfiguration 或完整的 ProjectData
        if isinstance(config, ProjectData):
            project: ProjectData = config
            # target_part 参数指定将 source 数据转换到哪个 target 坐标系
            # - 配置仅有 1 个 target：可不指定，自动选择该 target
            # - 配置有多个 target：必须明确指定（特殊文件/普通文件都需要）
            #   * 特殊文件：每个 source part 块会指定对应的 target
            #   * 普通文件：用户在 GUI/CLI 中为整个文件选择 target
            if target_part is None:
                if len(project.target_parts) == 1:
                    target_part = next(iter(project.target_parts.keys()))
                elif len(project.target_parts) > 1:
                    raise ValueError(
                        f"配置包含 {len(project.target_parts)} 个 Target 坐标系，"
                        f"必须通过 target_part 参数明确指定目标坐标系。"
                        f"可用: {list(project.target_parts.keys())}"
                    )
                else:
                    raise ValueError("配置不包含任何 Target 坐标系定义")
            # 若调用方通过 init_options 传入了选项，则优先使用其中的值（兼容旧参数行为）
            if init_options is not None:
                try:
                    source_part = (
                        getattr(init_options, "source_part")
                        if getattr(init_options, "source_part", None)
                        is not None
                        else source_part
                    )
                    source_variant = (
                        getattr(init_options, "source_variant", source_variant)
                    )
                    target_part = (
                        getattr(init_options, "target_part")
                        if getattr(init_options, "target_part", None)
                        is not None
                        else target_part
                    )
                    target_variant = getattr(init_options, "target_variant", target_variant)
                    cache_provider = getattr(init_options, "cache_provider", cache_provider)
                    cache_cfg = getattr(init_options, "cache_cfg", cache_cfg)
                except Exception:
                    # 不应阻塞初始化，继续使用已解析的关键字参数
                    logger.debug("init_options 解析失败，使用显式参数或默认值", exc_info=True)

            # 选择 source frame（可选）
            if source_part is not None:
                source_frame = project.get_source_part(source_part, source_variant)
            else:
                source_frame = project.source_config

            # 选择 target frame（已确保不为 None）
            target_frame = project.get_target_part(target_part, target_variant)
        elif isinstance(config, FrameConfiguration):
            # 仅提供单个 FrameConfiguration：source 和 target 使用同一配置
            source_frame = config
            target_frame = config
        else:
            raise TypeError(
                "AeroCalculator 的第一个参数必须是 ProjectData 或 FrameConfiguration"
            )

        self.source_frame = source_frame
        self.target_frame = target_frame

        # --- 几何初始化（带缓存支持）---
        src = self.source_frame.coord_system
        tgt = self.target_frame.coord_system
        self.basis_source = geometry.construct_basis_matrix(
            src.x_axis, src.y_axis, src.z_axis
        )
        self.basis_target = geometry.construct_basis_matrix(
            tgt.x_axis, tgt.y_axis, tgt.z_axis
        )

        # 支持依赖注入的缓存提供者（便于测试与替换）
        self._cache_provider = cache_provider

        # 从参数优先获取 cache_cfg，否则从全局配置读取（向后兼容）
        if cache_cfg is None:
            cfg = get_config()
            cache_cfg = getattr(cfg, "cache", None) if cfg else None

        # 从私有方法初始化旋转矩阵（含缓存回退逻辑）
        self.rotation_matrix = self._init_rotation_matrix(cache_cfg)

        # 计算力臂时优先使用 Source 的 MomentCenter（如果定义），否则退回到 Source 的 origin
        source_moment_ref = (
            self.source_frame.moment_center
            if self.source_frame.moment_center is not None
            else src.origin
        )
        self.r_global = geometry.compute_moment_arm_global(
            source_origin=source_moment_ref,
            target_moment_center=self.target_frame.moment_center,
        )

        # 从私有方法初始化 r_target（含缓存回退逻辑）
        self.r_target = self._init_r_target(cache_cfg)

        # 额外校验：确保 R_matrix 与 r_target 具有期望的形状和值；若缓存返回异常形状或 NaN，则回退为直接计算
        # 额外校验：确保 R_matrix 与 r_target 具有期望的形状和值；若缓存返回异常形状或 NaN，则回退为直接计算
        self._validate_and_fix_R()
        self._validate_and_fix_r_target()

        # 构造时验证 target 必需字段
        if self.target_frame.moment_center is None:
            raise ValueError("目标 variant 必须包含 MomentCenter 字段（长度为3的列表）")
        if self.target_frame.q is None:
            raise ValueError("目标 variant 必须包含动压 Q（数值）")
        if self.target_frame.s_ref is None:
            raise ValueError("目标 variant 必须包含参考面积 S（数值）")

    def _safe_divide(
        self, numerator: np.ndarray, denominator, warn_msg: str = None
    ) -> np.ndarray:
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
        except (ValueError, IndexError) as exc:
            # 若形状不匹配，回退为原始结果
            logger.debug(
                "_safe_divide: 形状不匹配，无法按列屏蔽 zero_mask: %s",
                exc,
                exc_info=True,
            )

        return result

    def _init_rotation_matrix(self, cache_cfg):
        """
        初始化旋转矩阵，尝试使用缓存并在异常或未命中时回退为直接计算。
        """
        try:
            if (
                cache_cfg
                and getattr(cache_cfg, "enabled", False)
                and "rotation" in getattr(cache_cfg, "cache_types", [])
            ):
                if self._cache_provider is not None:
                    rotation_cache = self._cache_provider.get_rotation_cache(
                        getattr(cache_cfg, "max_entries", None)
                    )
                else:
                    rotation_cache = get_rotation_cache(
                        getattr(cache_cfg, "max_entries", None)
                    )
                try:
                    rotation_matrix = rotation_cache.get_rotation_matrix(
                        self.basis_source,
                        self.basis_target,
                        getattr(cache_cfg, "precision_digits", None),
                    )
                except (KeyError, RuntimeError, AttributeError, TypeError) as exc:
                    logger.debug("旋转矩阵缓存调用失败，回退到直接计算: %s", exc, exc_info=True)
                    rotation_matrix = None

                if rotation_matrix is None:
                    rotation_matrix = geometry.compute_rotation_matrix(
                        self.basis_source, self.basis_target
                    )
                    try:
                        rotation_cache.set_rotation_matrix(
                            self.basis_source,
                            self.basis_target,
                            rotation_matrix,
                            getattr(cache_cfg, "precision_digits", None),
                        )
                        logger.debug("旋转矩阵缓存未命中，已计算并缓存")
                    except (RuntimeError, AttributeError, TypeError) as exc:
                        logger.debug("旋转矩阵缓存写入失败，已忽略: %s", exc, exc_info=True)
                else:
                    logger.debug("旋转矩阵缓存命中")
            else:
                rotation_matrix = geometry.compute_rotation_matrix(
                    self.basis_source, self.basis_target
                )
        except (AttributeError, TypeError) as exc:
            logger.debug("获取缓存配置失败或异常，直接计算旋转矩阵: %s", exc, exc_info=True)
            rotation_matrix = geometry.compute_rotation_matrix(
                self.basis_source, self.basis_target
            )

        return rotation_matrix

    def _init_r_target(self, cache_cfg):
        """
        初始化 r_target，尝试使用缓存并在异常或未命中时回退为直接计算。
        """
        try:
            if (
                cache_cfg
                and getattr(cache_cfg, "enabled", False)
                and "transformation" in getattr(cache_cfg, "cache_types", [])
            ):
                if self._cache_provider is not None:
                    transformation_cache = self._cache_provider.get_transformation_cache(
                        getattr(cache_cfg, "max_entries", None)
                    )
                else:
                    transformation_cache = get_transformation_cache(
                        getattr(cache_cfg, "max_entries", None)
                    )
                try:
                    r_t = transformation_cache.get_transformation(
                        self.basis_target,
                        self.r_global,
                        getattr(cache_cfg, "precision_digits", None),
                    )
                except (KeyError, RuntimeError, AttributeError, TypeError) as exc:
                    logger.debug("力臂转换缓存调用失败，回退到直接计算: %s", exc, exc_info=True)
                    r_t = None

                if r_t is None:
                    r_t = geometry.project_vector_to_frame(
                        self.r_global, self.basis_target
                    )
                    try:
                        transformation_cache.set_transformation(
                            self.basis_target,
                            self.r_global,
                            r_t,
                            getattr(cache_cfg, "precision_digits", None),
                        )
                        logger.debug("力臂转换缓存未命中，已计算并缓存")
                    except (RuntimeError, AttributeError, TypeError) as exc:
                        logger.debug("力臂转换写入失败，已忽略: %s", exc, exc_info=True)
                else:
                    logger.debug("力臂转换缓存命中")
            else:
                r_t = geometry.project_vector_to_frame(self.r_global, self.basis_target)
        except (AttributeError, TypeError) as exc:
            logger.debug(
                "获取/使用力臂转换缓存时发生异常，直接计算 r_target: %s",
                exc,
                exc_info=True,
            )
            r_t = geometry.project_vector_to_frame(self.r_global, self.basis_target)

        return r_t

    def _validate_and_fix_R(self):
        """验证并在必要时重新计算 `rotation_matrix`。"""
        try:
            if (
                not isinstance(self.rotation_matrix, np.ndarray)
                or self.rotation_matrix.shape != (3, 3)
                or np.isnan(self.rotation_matrix).any()
            ):
                logger.debug("检测到无效的 rotation_matrix，重新计算")
                self.rotation_matrix = geometry.compute_rotation_matrix(
                    self.basis_source, self.basis_target
                )
        except (TypeError, ValueError, AttributeError) as exc:
            logger.debug(
                "校验 rotation_matrix 时发生异常，重新计算旋转矩阵: %s",
                exc,
                exc_info=True,
            )
            self.rotation_matrix = geometry.compute_rotation_matrix(
                self.basis_source, self.basis_target
            )

    def _validate_and_fix_r_target(self):
        """验证并在必要时重新计算 `r_target`。"""
        try:
            r_arr = np.asarray(self.r_target, dtype=float)
            if r_arr.shape != (3,) or np.isnan(r_arr).any():
                logger.debug("检测到无效的 r_target，重新计算")
                self.r_target = geometry.project_vector_to_frame(
                    self.r_global, self.basis_target
                )
            else:
                self.r_target = r_arr
        except (TypeError, ValueError, AttributeError) as exc:
            logger.debug("校验 r_target 时发生异常，重新计算 r_target: %s", exc, exc_info=True)
            self.r_target = geometry.project_vector_to_frame(
                self.r_global, self.basis_target
            )

    def _rotate_vectors(self, vectors: np.ndarray) -> np.ndarray:
        """批量旋转向量到目标坐标系。

        参数:
            vectors: (N,3) 或 (3,) 的数组或可转为 numpy 数组的对象。

        返回值:
            旋转后的数组，形状与输入相同。

        示例:
            >>> calc._rotate_vectors([[1,0,0]])
            array([[1., 0., 0.]])  # 对单位坐标系无变化
        """
        try:
            return np.dot(np.asarray(vectors, dtype=float), self.rotation_matrix.T)
        except (TypeError, ValueError) as exc:
            logger.debug("旋转向量时发生异常，尝试逐行计算: %s", exc, exc_info=True)
            vecs = np.asarray(vectors, dtype=float)
            out = np.zeros_like(vecs)
            for i, v in enumerate(vecs):
                out[i] = np.dot(self.rotation_matrix, v)
            return out

    def _transfer_moments(self, F_rotated: np.ndarray) -> np.ndarray:
        """计算移轴产生的附加力矩: r_target x F_rotated（支持批量）。

        返回与 `F_rotated` 相同形状的数组，表示由力臂 `r_target` 与力的叉乘产生的附加力矩。

        示例:
            >>> calc.r_target = np.array([0,0,0])
            >>> calc._transfer_moments([[1,0,0]])
            array([[0.,0.,0.]])
        """
        try:
            return np.cross(self.r_target, np.asarray(F_rotated, dtype=float))
        except (TypeError, ValueError) as exc:
            logger.debug("计算移轴力矩时异常，回退为逐行计算: %s", exc, exc_info=True)
            fr = np.asarray(F_rotated, dtype=float)
            out = np.zeros_like(fr)
            for i, f in enumerate(fr):
                out[i] = np.cross(self.r_target, f)
            return out

    def _compute_coefficients(self, F_final: np.ndarray, M_final: np.ndarray) -> tuple:
        """
        计算力与力矩的无量纲系数，封装无量纲化逻辑以便测试与复用。

        返回: (C_F, C_M)
        """
        q = getattr(self.target_frame, "q", None)
        s = getattr(self.target_frame, "s_ref", None)
        b = getattr(self.target_frame, "b_ref", None)
        c = getattr(self.target_frame, "c_ref", None)

        denom_force = q * s
        C_F = self._safe_divide(
            F_final,
            denom_force,
            warn_msg="动压(q) 或 参考面积 s_ref 为零，无法计算力系数，已将力系数设为 0。",
        )

        b_val = float(b) if (b is not None) else 0.0
        c_val = float(c) if (c is not None) else 0.0
        moment_length_vector = np.array([b_val, c_val, b_val], dtype=float)

        denom_moment = denom_force * moment_length_vector

        C_M = self._safe_divide(
            M_final,
            denom_moment,
            warn_msg=(
                "动压(q) 或 参考长度 b_ref/c_ref 为零，相关轴的力矩系数已设为0。"
            ),
        )

        # 返回力和力矩的无量纲系数 (C_F, C_M)。
        # 说明：当 `q * s_ref == 0` 或参考长度为 0 时，使用 `_safe_divide` 会将对应结果设为 0 并发出警告。

        return C_F, C_M

    def process_frame(
        self, force_raw: List[float], moment_raw: List[float]
    ) -> AeroResult:
        """保持原有单点方法，用于 GUI 或简单测试"""
        # 调用下面的批量方法，但传入单行数据
        f_arr = np.array([force_raw])
        m_arr = np.array([moment_raw])
        results = self.process_batch(f_arr, m_arr)

        return AeroResult(
            force_transformed=results["force_transformed"][0].tolist(),
            moment_transformed=results["moment_transformed"][0].tolist(),
            coeff_force=results["coeff_force"][0].tolist(),
            coeff_moment=results["coeff_moment"][0].tolist(),
        )

    def process_batch(
        self, forces: np.ndarray, moments: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        [新增] 高性能批处理方法
        输入:
            forces: (N, 3) Numpy Array
            moments: (N, 3) Numpy Array
        输出:
            Dictionary containing (N, 3) arrays
        """
        # 输入校验并强制为 numpy 数组
        forces = np.asarray(forces, dtype=float)
        moments = np.asarray(moments, dtype=float)

        # 强制形状为 (N,3)
        if forces.ndim == 1:
            if forces.size == 3:
                forces = forces.reshape(1, 3)
            else:
                raise ValueError("forces 必须为形状 (N,3) 或长度为3 的向量")
        if moments.ndim == 1:
            if moments.size == 3:
                moments = moments.reshape(1, 3)
            else:
                raise ValueError("moments 必须为形状 (N,3) 或长度为3 的向量")

        if forces.shape != moments.shape:
            raise ValueError("forces 与 moments 必须具有相同形状")

        # 1. 批量旋转与移轴（提取为独立私有方法以便测试与复用）
        F_rotated = self._rotate_vectors(forces)
        M_rotated = self._rotate_vectors(moments)
        M_transfer = self._transfer_moments(F_rotated)

        # 3. 结果汇总
        F_final = F_rotated
        M_final = M_rotated + M_transfer

        # 4. 无量纲化（使用选定的 target_frame）
        C_F, C_M = self._compute_coefficients(F_final, M_final)

        return {
            "force_transformed": F_final,
            "moment_transformed": M_final,
            "coeff_force": C_F,
            "coeff_moment": C_M,
        }
