"""
项目强类型模型：替代裸字典，提供更安全的访问与序列化。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np


@dataclass
class CoordinateSystem:
    """坐标系模型（与 JSON 键兼容）。"""

    origin: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    x_axis: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0])
    y_axis: List[float] = field(default_factory=lambda: [0.0, 1.0, 0.0])
    z_axis: List[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    moment_center: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 用于序列化：记录原始配置中的力矩中心定义
    moment_center_in_part: List[float] = None
    moment_center_in_global: List[float] = None

    def to_matrix(self) -> np.ndarray:
        """转换为 3x3 变换矩阵（列为基向量）。"""
        return np.column_stack(
            [
                np.asarray(self.x_axis, dtype=float),
                np.asarray(self.y_axis, dtype=float),
                np.asarray(self.z_axis, dtype=float),
            ]
        )

    @classmethod
    def from_dict(cls, data: Dict) -> "CoordinateSystem":
        """从字典创建 CoordinateSystem（反序列化）。"""
        cs = cls(
            origin=list(data.get("Orig", [0.0, 0.0, 0.0])),
            x_axis=list(data.get("X", [1.0, 0.0, 0.0])),
            y_axis=list(data.get("Y", [0.0, 1.0, 0.0])),
            z_axis=list(data.get("Z", [0.0, 0.0, 1.0])),
        )
        
        # 支持双力矩中心定义
        mc_in_part = data.get("MomentCenterInPartCoordSystem")
        mc_in_global = data.get("MomentCenterInGlobalCoordSystem")
        mc_legacy = data.get("MomentCenter")
        
        # 向后兼容：旧格式的 MomentCenter
        if mc_legacy is not None:
            cs.moment_center = list(mc_legacy)
            # 如果没有新格式字段，假设为 Part 坐标系
            if mc_in_part is None and mc_in_global is None:
                cs.moment_center_in_part = list(mc_legacy)
        
        # 新格式：优先使用双字段
        if mc_in_part is not None:
            cs.moment_center_in_part = list(mc_in_part)
            if not cs.moment_center or cs.moment_center == [0.0, 0.0, 0.0]:
                # TODO: 应该计算为全局坐标，但这里暂时直接使用
                cs.moment_center = list(mc_in_part)
        
        if mc_in_global is not None:
            cs.moment_center_in_global = list(mc_in_global)
            # 全局坐标作为内部统一表达
            cs.moment_center = list(mc_in_global)
        
        return cs

    def to_dict(self) -> Dict:
        """序列化为字典（用于输出到 JSON）。"""
        result = {
            "Orig": list(self.origin),
            "X": list(self.x_axis),
            "Y": list(self.y_axis),
            "Z": list(self.z_axis),
        }
        # 优先导出原始定义的力矩中心
        if self.moment_center_in_part is not None:
            result["MomentCenterInPartCoordSystem"] = list(self.moment_center_in_part)
        if self.moment_center_in_global is not None:
            result["MomentCenterInGlobalCoordSystem"] = list(self.moment_center_in_global)
        # 如果都没有（向后兼容），导出统一的 moment_center
        if self.moment_center_in_part is None and self.moment_center_in_global is None:
            result["MomentCenter"] = list(self.moment_center)
        return result


@dataclass
class ReferenceValues:
    """参考值模型。"""

    cref: float = 1.0
    bref: float = 1.0
    sref: float = 10.0
    q: float = 1000.0

    @classmethod
    def from_dict(cls, data: Dict) -> "ReferenceValues":
        """从字典创建 ReferenceValues（反序列化）。"""
        return cls(
            cref=float(data.get("Cref", 1.0)),
            bref=float(data.get("Bref", 1.0)),
            sref=float(data.get("S", data.get("Sref", 10.0))),
            q=float(data.get("Q", 1000.0)),
        )

    def to_dict(self) -> Dict:
        """序列化 ReferenceValues 为字典。"""
        return {
            "Cref": float(self.cref),
            "Bref": float(self.bref),
            "S": float(self.sref),
            "Q": float(self.q),
        }


@dataclass
class PartVariant:
    """Part 变体模型。"""

    part_name: str
    coord_system: CoordinateSystem
    refs: ReferenceValues
    name: str = ""  # 参考系名称（新增）
    coord_system_ref: str = None  # 坐标系引用（如 "Global"，新增）

    @classmethod
    def from_dict(cls, data: Dict, global_coord_systems: Dict[str, CoordinateSystem] = None) -> "PartVariant":
        """从字典创建 PartVariant（反序列化）。
        
        Args:
            data: 配置字典
            global_coord_systems: 全局坐标系定义字典（用于解析引用）
        """
        if global_coord_systems is None:
            global_coord_systems = {}
        
        part_name = str(data.get("PartName", "Unnamed"))
        name = data.get("Name", "")
        coord_system_ref = data.get("CoordSystemRef")
        
        # 解析坐标系：优先使用引用
        if coord_system_ref:
            if coord_system_ref in global_coord_systems:
                # 创建深拷贝，避免多个 PartVariant 共享同一对象
                import copy
                cs = copy.deepcopy(global_coord_systems[coord_system_ref])
            else:
                import warnings
                warnings.warn(f"坐标系引用 '{coord_system_ref}' 未定义，使用默认坐标系")
                cs = CoordinateSystem.from_dict({})
        else:
            cs = CoordinateSystem.from_dict(data.get("CoordSystem", {}))
        
        # input.json 的 MomentCenter 位于 variant 顶层；这里要同步进坐标系模型
        mc = data.get("MomentCenter")
        mc_in_part = data.get("MomentCenterInPartCoordSystem")
        mc_in_global = data.get("MomentCenterInGlobalCoordSystem")
        
        if mc_in_part is not None:
            try:
                cs.moment_center_in_part = list(mc_in_part)
                cs.moment_center = list(mc_in_part)  # 暂时使用
            except (TypeError, ValueError):
                pass
        
        if mc_in_global is not None:
            try:
                cs.moment_center_in_global = list(mc_in_global)
                cs.moment_center = list(mc_in_global)  # 优先使用全局坐标
            except (TypeError, ValueError):
                pass
        
        # 向后兼容：旧格式的 MomentCenter
        if mc is not None and mc_in_part is None and mc_in_global is None:
            try:
                cs.moment_center = list(mc)
                # 如果使用引用，视为全局坐标
                if coord_system_ref:
                    cs.moment_center_in_global = list(mc)
                else:
                    cs.moment_center_in_part = list(mc)
            except (TypeError, ValueError):
                pass
        
        return cls(
            part_name=part_name,
            coord_system=cs,
            refs=ReferenceValues.from_dict(data),
            name=name,
            coord_system_ref=coord_system_ref,
        )

    def to_dict(self) -> Dict:
        """序列化 PartVariant 为字典，兼容旧版输入格式。"""
        result = {
            "PartName": self.part_name,
            **self.refs.to_dict(),
        }
        
        # 添加名称（如果定义）
        if self.name:
            result["Name"] = self.name
        
        # 如果有坐标系引用，优先使用引用
        if self.coord_system_ref:
            result["CoordSystemRef"] = self.coord_system_ref
        else:
            result["CoordSystem"] = self.coord_system.to_dict()
        
        # 力矩中心由 CoordinateSystem.to_dict() 处理
        cs_dict = self.coord_system.to_dict()
        for key in ["MomentCenterInPartCoordSystem", "MomentCenterInGlobalCoordSystem", "MomentCenter"]:
            if key in cs_dict:
                result[key] = cs_dict[key]
        
        return result


@dataclass
class Part:
    """Part 模型，包含变体列表。"""

    part_name: str
    variants: List[PartVariant] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict, global_coord_systems: Dict[str, CoordinateSystem] = None) -> "Part":
        """从字典创建 Part（反序列化）。
        
        Args:
            data: 配置字典
            global_coord_systems: 全局坐标系定义字典（用于解析引用）
        """
        if global_coord_systems is None:
            global_coord_systems = {}
        
        part_name = str(data.get("PartName", "Unnamed"))
        # 支持新格式（ReferenceSystem）和旧格式（Variants）
        variants_data = data.get("ReferenceSystem") or data.get("Variants") or [{}]
        variants: List[PartVariant] = []
        for v in variants_data:
            v_copy = dict(v or {})
            # 兼容 input.json：variant 内通常不含 PartName
            if not v_copy.get("PartName"):
                v_copy["PartName"] = part_name
            variants.append(PartVariant.from_dict(v_copy, global_coord_systems))
        return cls(part_name=part_name, variants=variants)

    def to_dict(self) -> Dict:
        """序列化 Part 为字典。"""
        return {
            "PartName": self.part_name,
            "ReferenceSystem": [v.to_dict() for v in self.variants],
        }


class ProjectConfigModel:
    """项目配置模型，替代裸字典。"""

    def __init__(self):
        self.source_parts: Dict[str, Part] = {}
        self.target_parts: Dict[str, Part] = {}

    @classmethod
    def from_dict(cls, data: Dict) -> "ProjectConfigModel":
        """从字典创建 ProjectConfigModel（反序列化）。"""
        model = cls()
        
        # 加载全局坐标系定义（新增）
        global_coord_systems: Dict[str, CoordinateSystem] = {}
        if "Global" in data and isinstance(data["Global"], dict):
            global_def = data["Global"]
            if "CoordSystem" in global_def:
                try:
                    global_coord_systems["Global"] = CoordinateSystem.from_dict(
                        global_def["CoordSystem"]
                    )
                except Exception as e:
                    import warnings
                    warnings.warn(f"加载全局坐标系失败: {e}")
        
        for p in (data.get("Source", {}) or {}).get("Parts", []) or []:
            part = Part.from_dict(p, global_coord_systems)
            model.source_parts[part.part_name] = part
        for p in (data.get("Target", {}) or {}).get("Parts", []) or []:
            part = Part.from_dict(p, global_coord_systems)
            model.target_parts[part.part_name] = part
        return model

    def to_dict(self) -> Dict:
        """将 ProjectConfigModel 序列化为字典以便输出或持久化。"""
        return {
            "Source": {"Parts": [p.to_dict() for p in self.source_parts.values()]},
            "Target": {"Parts": [p.to_dict() for p in self.target_parts.values()]},
        }
