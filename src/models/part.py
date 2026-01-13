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
    """单个变体，含坐标系与参考参数。"""

    part_name: str
    coord_system: CoordinateSystem
    cref: float = 1.0
    bref: float = 1.0
    sref: float = 10.0
    q: float = 1000.0

    @property
    def moment_center(self):
        """返回该变体的力矩中心坐标（3 元向量）。"""
        return self.coord_system.moment_center

    def to_dict(self) -> Dict:
        """将 Variant 序列化为与 `input.json` 兼容的字典结构。"""
        return {
            "PartName": self.part_name,
            "CoordSystem": self.coord_system.to_dict(),
            "MomentCenter": self.coord_system.moment_center.tolist(),
            "Cref": float(self.cref),
            "Bref": float(self.bref),
            "S": float(self.sref),
            "Q": float(self.q),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Variant":
        """从字典创建 Variant（反序列化）。"""
        cs = CoordinateSystem.from_dict(data.get("CoordSystem") or {})
        mc = data.get("MomentCenter")
        if mc is not None:
            cs.moment_center = np.array(mc, dtype=float)

        # 支持多种字段名：S, Sref, S_ref
        sref = data.get("S") or data.get("Sref") or data.get("S_ref") or 10.0
        cref = data.get("Cref") or data.get("C_ref") or 1.0
        bref = data.get("Bref") or data.get("B_ref") or 1.0

        return cls(
            part_name=data.get("PartName", ""),
            coord_system=cs,
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
        """将 Part 序列化为字典，用于输出或持久化。"""
        return {
            "PartName": self.name,
            "Variants": [v.to_dict() for v in self.variants] or [{}],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Part":
        """从字典创建 Part 实例（反序列化）。"""
        name = data.get("PartName", "")
        variants_data = data.get("Variants") or []
        variants = (
            [Variant.from_dict(v) for v in variants_data] if variants_data else []
        )
        return cls(name=name, variants=variants)
