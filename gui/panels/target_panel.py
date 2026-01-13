"""
Target面板 - Target坐标系专用配置
"""

from .coordinate_panel import CoordinateSystemPanel


class TargetPanel(CoordinateSystemPanel):
    """Target坐标系配置面板"""

    def __init__(self, parent=None):
        super().__init__("Target Configuration", "tgt", parent)
        # Target特定的初始化（如有）
