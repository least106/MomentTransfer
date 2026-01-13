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
        return cls(
            origin=list(data.get("Orig", [0.0, 0.0, 0.0])),
            x_axis=list(data.get("X", [1.0, 0.0, 0.0])),
            y_axis=list(data.get("Y", [0.0, 1.0, 0.0])),
            z_axis=list(data.get("Z", [0.0, 0.0, 1.0])),
            moment_center=list(data.get("MomentCenter", [0.0, 0.0, 0.0])),
        )

    def to_dict(self) -> Dict:
        return {
            "Orig": list(self.origin),
            "X": list(self.x_axis),
            "Y": list(self.y_axis),
            "Z": list(self.z_axis),
            "MomentCenter": list(self.moment_center),
        }


@dataclass
class ReferenceValues:
    """参考值模型。"""

    cref: float = 1.0
    bref: float = 1.0
    sref: float = 10.0
    q: float = 1000.0

    @classmethod
    def from_dict(cls, data: Dict) -> "ReferenceValues":
        return cls(
            cref=float(data.get("Cref", 1.0)),
            bref=float(data.get("Bref", 1.0)),
            sref=float(data.get("S", data.get("Sref", 10.0))),
            q=float(data.get("Q", 1000.0)),
        )

    def to_dict(self) -> Dict:
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

    @classmethod
    def from_dict(cls, data: Dict) -> "PartVariant":
        part_name = str(data.get("PartName", "Unnamed"))
        cs = CoordinateSystem.from_dict(data.get("CoordSystem", {}))
        # input.json 的 MomentCenter 位于 variant 顶层；这里要同步进坐标系模型
        mc = data.get("MomentCenter")
        if mc is not None:
            try:
                cs.moment_center = list(mc)
            except Exception:
                pass
        return cls(
            part_name=part_name,
            coord_system=cs,
            refs=ReferenceValues.from_dict(data),
        )

    def to_dict(self) -> Dict:
        return {
            "PartName": self.part_name,
            "CoordSystem": self.coord_system.to_dict(),
            # 保持兼容：在 variant 顶层也输出 MomentCenter，供旧的 data_loader 校验使用
            "MomentCenter": list(self.coord_system.moment_center),
            **self.refs.to_dict(),
        }


@dataclass
class Part:
    """Part 模型，包含变体列表。"""

    part_name: str
    variants: List[PartVariant] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> "Part":
        part_name = str(data.get("PartName", "Unnamed"))
        variants: List[PartVariant] = []
        for v in data.get("Variants") or [{}]:
            v_copy = dict(v or {})
            # 兼容 input.json：variant 内通常不含 PartName
            if not v_copy.get("PartName"):
                v_copy["PartName"] = part_name
            variants.append(PartVariant.from_dict(v_copy))
        return cls(part_name=part_name, variants=variants)

    def to_dict(self) -> Dict:
        return {
            "PartName": self.part_name,
            "Variants": [v.to_dict() for v in self.variants],
        }


class ProjectConfigModel:
    """项目配置模型，替代裸字典。"""

    def __init__(self):
        self.source_parts: Dict[str, Part] = {}
        self.target_parts: Dict[str, Part] = {}

    @classmethod
    def from_dict(cls, data: Dict) -> "ProjectConfigModel":
        model = cls()
        for p in (data.get("Source", {}) or {}).get("Parts", []) or []:
            part = Part.from_dict(p)
            model.source_parts[part.part_name] = part
        for p in (data.get("Target", {}) or {}).get("Parts", []) or []:
            part = Part.from_dict(p)
            model.target_parts[part.part_name] = part
        return model

    def to_dict(self) -> Dict:
        return {
            "Source": {
                "Parts": [p.to_dict() for p in self.source_parts.values()]
            },
            "Target": {
                "Parts": [p.to_dict() for p in self.target_parts.values()]
            },
        }
