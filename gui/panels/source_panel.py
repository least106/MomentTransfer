"""
Source面板 - Source坐标系专用配置
"""

from .coordinate_panel import CoordinateSystemPanel


class SourcePanel(CoordinateSystemPanel):
    """Source坐标系配置面板"""
    
    def __init__(self, parent=None):
        super().__init__("Source Configuration", "src", parent)
        # Source特定的初始化（如有）
