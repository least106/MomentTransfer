# 通过在此处导入，外部脚本可以直接使用：
# from src import load_data, AeroCalculator
# 而不需要：from src.data_loader import load_data

from .data_loader import load_data, ProjectData, CoordSystemDefinition, TargetDefinition
from .physics import AeroCalculator, AeroResult
from .geometry import construct_basis_matrix  # 如果需要暴露几何工具

# 定义包的版本
__version__ = '1.0.0'