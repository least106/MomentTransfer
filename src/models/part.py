"""
部件与变体数据模型。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List
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
        return self.coord_system.moment_center

    def to_dict(self) -> Dict:
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
        cs = CoordinateSystem.from_dict(data.get("CoordSystem") or {})
        mc = data.get("MomentCenter")
        if mc is not None:
            from numpy import array
            cs.moment_center = array(mc, dtype=float)
        return cls(
            part_name=data.get("PartName", ""),
            coord_system=cs,
            cref=float(data.get("Cref", 1.0)),
            bref=float(data.get("Bref", 1.0)),
            sref=float(data.get("S", data.get("Sref", 10.0))),
            q=float(data.get("Q", 1000.0)),
        )


@dataclass
class Part:
    """部件，包含一个或多个变体。"""

    name: str
    variants: List[Variant] = field(default_factory=list)

    def add_variant(self, variant: Variant) -> None:
        self.variants.append(variant)

    def to_dict(self) -> Dict:
        return {
            "PartName": self.name,
            "Variants": [v.to_dict() for v in self.variants] or [{}],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Part":
        name = data.get("PartName", "")
        variants_data = data.get("Variants") or []
        variants = [Variant.from_dict(v) for v in variants_data] if variants_data else []
        return cls(name=name, variants=variants)
