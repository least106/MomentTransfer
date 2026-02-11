"""
坐标系数据模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

import numpy as np


def _vec3(vec: Iterable[float]) -> np.ndarray:
    """将输入转换为 shape (3,) 的浮点向量。"""
    arr = np.asarray(list(vec), dtype=float).reshape(-1)
    if arr.size != 3:
        raise ValueError("坐标向量必须包含3个分量")
    return arr


@dataclass
class CoordinateSystem:
    """描述坐标系基向量与力矩中心。"""

    origin: np.ndarray
    x_axis: np.ndarray
    y_axis: np.ndarray
    z_axis: np.ndarray
    moment_center: np.ndarray
    # 用于序列化：记录原始配置中的力矩中心定义
    _moment_center_in_part: np.ndarray = None
    _moment_center_in_global: np.ndarray = None

    def __post_init__(self) -> None:
        # 统一为 numpy 向量
        self.origin = _vec3(self.origin)
        self.x_axis = _vec3(self.x_axis)
        self.y_axis = _vec3(self.y_axis)
        self.z_axis = _vec3(self.z_axis)
        self.moment_center = _vec3(self.moment_center)
        # 转换私有字段为 numpy 向量
        if self._moment_center_in_part is not None:
            self._moment_center_in_part = _vec3(self._moment_center_in_part)
        if self._moment_center_in_global is not None:
            self._moment_center_in_global = _vec3(self._moment_center_in_global)

    def to_matrix(self) -> np.ndarray:
        """返回 3x3 旋转矩阵，列为 x/y/z 基向量。"""
        return np.column_stack([self.x_axis, self.y_axis, self.z_axis])

    def to_dict(self) -> Dict[str, list]:
        """序列化为新的 JSON 格式（包含双力矩中心）。"""
        result = {
            "Orig": self.origin.tolist(),
            "X": self.x_axis.tolist(),
            "Y": self.y_axis.tolist(),
            "Z": self.z_axis.tolist(),
        }
        # 优先导出原始定义的力矩中心
        if self._moment_center_in_part is not None:
            result["MomentCenterInPartCoordSystem"] = self._moment_center_in_part.tolist()
        if self._moment_center_in_global is not None:
            result["MomentCenterInGlobalCoordSystem"] = self._moment_center_in_global.tolist()
        # 如果都没有（向后兼容），导出统一的 moment_center
        if self._moment_center_in_part is None and self._moment_center_in_global is None:
            result["MomentCenter"] = self.moment_center.tolist()
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> "CoordinateSystem":
        """从字典构造，兼容键名：Orig/X/Y/Z/MomentCenter 或 TargetMomentCenter。"""
        if data is None:
            raise ValueError("坐标系数据不能为空")
        origin = data.get("Orig", [0.0, 0.0, 0.0])
        x_axis = data.get("X", [1.0, 0.0, 0.0])
        y_axis = data.get("Y", [0.0, 1.0, 0.0])
        z_axis = data.get("Z", [0.0, 0.0, 1.0])
        mc = (
            data.get("MomentCenter")
            or data.get("TargetMomentCenter")
            or [0.0, 0.0, 0.0]
        )
        return cls(
            origin=origin,
            x_axis=x_axis,
            y_axis=y_axis,
            z_axis=z_axis,
            moment_center=mc,
        )
