"""MomentTransfer 包的顶层导出。

此文件显式列出希望对外暴露的 API 名称，避免静态分析报未使用导入。
"""

from . import data_loader as _data_loader
from . import physics as _physics
from . import geometry as _geometry

# 将需要对外暴露的符号显式绑定到包顶层，避免未使用导入的静态检查警告
load_data = _data_loader.load_data
ProjectData = _data_loader.ProjectData
CoordSystemDefinition = _data_loader.CoordSystemDefinition
TargetDefinition = _data_loader.TargetDefinition

AeroCalculator = _physics.AeroCalculator
AeroResult = _physics.AeroResult

construct_basis_matrix = _geometry.construct_basis_matrix

__all__ = [
    "load_data",
    "ProjectData",
    "CoordSystemDefinition",
    "TargetDefinition",
    "AeroCalculator",
    "AeroResult",
    "construct_basis_matrix",
]

# 定义包的版本
__version__ = "1.0.0"
