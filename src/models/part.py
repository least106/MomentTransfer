"""
部件与变体数据模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from .coordinate_system import CoordinateSystem


@dataclass
class Variant:
    """单个参考系配置（Reference System），含坐标系与参考参数。
    
    注意：在新配置格式中，此类对应 ReferenceSystem 数组中的元素。
    为保持兼容性，类名暂保留为 Variant，未来可重命名为 ReferenceSystemVariant。
    """

    part_name: str
    coord_system: CoordinateSystem
    name: str = ""  # 参考系名称（新增）
    coord_system_ref: str = None  # 坐标系引用（如 "Global"，新增）
    cref: float = 1.0
    bref: float = 1.0
    sref: float = 10.0
    q: float = 1000.0

    @property
    def moment_center(self):
        """返回该变体的力矩中心坐标（3 元向量）。"""
        return self.coord_system.moment_center

    def to_dict(self) -> Dict:
        """将 Variant 序列化为新的配置格式。"""
        result = {
            "Cref": float(self.cref),
            "Bref": float(self.bref),
            "S": float(self.sref),
            "Q": float(self.q),
        }
        # 添加名称（如果定义）
        if self.name:
            result["Name"] = self.name
        # 如果有坐标系引用，优先使用引用
        if self.coord_system_ref:
            result["CoordSystemRef"] = self.coord_system_ref
        else:
            # 否则导出完整坐标系定义
            result["CoordSystem"] = self.coord_system.to_dict()
        # 力矩中心由 CoordinateSystem.to_dict() 处理
        cs_dict = self.coord_system.to_dict()
        for key in ["MomentCenterInPartCoordSystem", "MomentCenterInGlobalCoordSystem", "MomentCenter"]:
            if key in cs_dict:
                result[key] = cs_dict[key]
        return result

    @classmethod
    def from_dict(cls, data: Dict, part_name: str = "", global_coord_systems: Dict[str, CoordinateSystem] = None) -> "Variant":
        """从字典创建 Variant（反序列化），支持新旧配置格式。
        
        Args:
            data: 配置字典
            part_name: 所属 Part 名称（用于向后兼容）
            global_coord_systems: 全局坐标系定义字典（用于解析引用）
        """
        if global_coord_systems is None:
            global_coord_systems = {}
        
        # 提取参考系名称
        name = data.get("Name", "")
        
        # 提取坐标系引用
        coord_system_ref = data.get("CoordSystemRef")
        
        # 解析坐标系：优先使用引用，否则从 CoordSystem 字段加载
        if coord_system_ref:
            if coord_system_ref not in global_coord_systems:
                raise ValueError(f"坐标系引用 '{coord_system_ref}' 未定义")
            cs = global_coord_systems[coord_system_ref]
        else:
            cs = CoordinateSystem.from_dict(data.get("CoordSystem") or {})
        
        # 处理力矩中心：新格式（双字段）或旧格式（单字段）
        mc_in_part = data.get("MomentCenterInPartCoordSystem")
        mc_in_global = data.get("MomentCenterInGlobalCoordSystem")
        mc_legacy = data.get("MomentCenter")
        
        # 向后兼容：旧格式的 MomentCenter
        if mc_legacy is not None and mc_in_part is None and mc_in_global is None:
            # 如果使用引用，视为全局坐标；否则视为 Part 坐标
            if coord_system_ref:
                mc_in_global = mc_legacy
            else:
                mc_in_part = mc_legacy
        
        # 验证：至少提供一个力矩中心
        if mc_in_part is None and mc_in_global is None:
            raise ValueError(f"参考系 '{name}' 必须提供至少一个力矩中心定义")
        
        # 导入坐标转换工具
        from ..moment_center_utils import (
            compute_missing_moment_center,
            validate_moment_center_consistency,
        )
        
        # 准备坐标系信息
        origin = cs.origin
        rotation_matrix = cs.to_matrix()
        
        # 转换为 numpy 数组
        if mc_in_part is not None:
            mc_in_part = np.array(mc_in_part, dtype=float)
        if mc_in_global is not None:
            mc_in_global = np.array(mc_in_global, dtype=float)
        
        # 如果两个都提供，验证一致性
        if mc_in_part is not None and mc_in_global is not None:
            is_consistent, error = validate_moment_center_consistency(
                mc_in_part, mc_in_global, origin, rotation_matrix, tolerance=1e-6
            )
            if not is_consistent:
                import warnings
                warnings.warn(
                    f"参考系 '{name}': MomentCenterInPartCoordSystem 和 "
                    f"MomentCenterInGlobalCoordSystem 不一致（误差: {error:.6e}），"
                    f"将使用 Part 坐标系定义"
                )
        
        # 如果只提供了一个，计算另一个
        if mc_in_part is None or mc_in_global is None:
            mc_in_part, mc_in_global = compute_missing_moment_center(
                mc_in_part, mc_in_global, origin, rotation_matrix
            )
        
        # 设置内部统一使用的 moment_center（全局坐标）
        cs.moment_center = mc_in_global
        cs._moment_center_in_part = mc_in_part
        cs._moment_center_in_global = mc_in_global

        # 支持多种字段名：S, Sref, S_ref
        sref = data.get("S") or data.get("Sref") or data.get("S_ref") or 10.0
        cref = data.get("Cref") or data.get("C_ref") or 1.0
        bref = data.get("Bref") or data.get("B_ref") or 1.0
        
        # 向后兼容：PartName 字段
        pname = data.get("PartName", part_name)

        return cls(
            part_name=pname,
            coord_system=cs,
            name=name,
            coord_system_ref=coord_system_ref,
            cref=float(cref),
            bref=float(bref),
            sref=float(sref),
            q=float(data.get("Q", 1000.0)),
        )


@dataclass
class Part:
    """部件，包含一个或多个变体。"""

    name: str
    variants: List[Variant] = field(default_factory=list)

    def add_variant(self, variant: Variant) -> None:
        """向 Part 中添加一个变体实例。"""
        self.variants.append(variant)

    def to_dict(self) -> Dict:
        """将 Part 序列化为字典，用于输出或持久化（新格式：ReferenceSystem）。"""
        return {
            "PartName": self.name,
            "ReferenceSystem": [v.to_dict() for v in self.variants] or [{}],
        }

    @classmethod
    def from_dict(cls, data: Dict, global_coord_systems: Dict[str, CoordinateSystem] = None) -> "Part":
        """从字典创建 Part 实例（反序列化），支持新旧格式。
        
        Args:
            data: 配置字典
            global_coord_systems: 全局坐标系定义字典（用于解析引用）
        """
        if global_coord_systems is None:
            global_coord_systems = {}
        
        name = data.get("PartName", "")
        # 支持新格式（ReferenceSystem）和旧格式（Variants）
        variants_data = data.get("ReferenceSystem") or data.get("Variants") or []
        variants = (
            [Variant.from_dict(v, part_name=name, global_coord_systems=global_coord_systems) for v in variants_data] 
            if variants_data else []
        )
        return cls(name=name, variants=variants)
