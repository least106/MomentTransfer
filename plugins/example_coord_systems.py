"""示例坐标系插件：提供若干预定义的坐标系供示例和测试使用。

此文件保留单一实现，避免重复定义 `create_plugin` 导致的 E0102 错误。
"""

from typing import Dict, List, Optional

from src.plugin import CoordSystemPlugin, PluginMetadata


class ExampleCoordSystemPlugin(CoordSystemPlugin):
    """示例坐标系插件，提供若干常用坐标系定义。"""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="example_coord_systems",
            version="1.0.0",
            author="MomentTransfer Team",
            description="提供示例和常见坐标系定义的插件",
            plugin_type="coord_system",
        )

    _COORD_SYSTEMS: Dict[str, Dict[str, List[float]]] = {
        "standard_body_frame": {
            "origin": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
            "y_axis": [0.0, 1.0, 0.0],
            "z_axis": [0.0, 0.0, 1.0],
        },
        "wind_frame": {
            "origin": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
            "y_axis": [0.0, 1.0, 0.0],
            "z_axis": [0.0, 0.0, -1.0],
        },
        "stability_frame": {
            "origin": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
            "y_axis": [0.0, 1.0, 0.0],
            "z_axis": [0.0, 0.0, 1.0],
        },
    }

    def get_coordinate_system(self, name: str) -> Optional[Dict[str, List[float]]]:
        return self._COORD_SYSTEMS.get(name)

    def list_coordinate_systems(self) -> List[str]:
        return list(self._COORD_SYSTEMS.keys())


def create_plugin() -> ExampleCoordSystemPlugin:
    """创建并返回插件实例。"""
    return ExampleCoordSystemPlugin()
