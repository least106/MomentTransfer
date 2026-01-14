"""示例坐标系插件：基于字典的坐标系提供者。"""

from typing import Dict, List, Optional

from src.plugin import CoordSystemPlugin, PluginMetadata


class DictCoordSystemPlugin(CoordSystemPlugin):
    """通过传入的映射提供命名坐标系的简单实现。"""

    def __init__(
        self, mapping: Dict[str, Dict[str, List[float]]], meta: PluginMetadata
    ):
        self._mapping = mapping
        self._meta = meta

    @property
    def metadata(self) -> PluginMetadata:
        return self._meta

    def get_coordinate_system(self, name: str) -> Optional[Dict[str, List[float]]]:
        return self._mapping.get(name)

    def list_coordinate_systems(self) -> List[str]:
        return list(self._mapping.keys())


def create_plugin() -> DictCoordSystemPlugin:
    """工厂函数：创建一个包含示例坐标系的插件实例。"""
    mapping = {
        "example": {
            "origin": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
            "y_axis": [0.0, 1.0, 0.0],
            "z_axis": [0.0, 0.0, 1.0],
        }
    }

    meta = PluginMetadata(
        name="dict_coord_example",
        version="0.1",
        author="example",
        description="基于字典的示例坐标系插件",
        plugin_type="coord_system",
    )

    return DictCoordSystemPlugin(mapping, meta)


"""
示例坐标系插件 - 演示如何创建自定义坐标系定义插件

这个插件预定义了几个常见的坐标系供用户快速选择。
"""

from typing import Dict, List, Optional

from src.plugin import CoordSystemPlugin, PluginMetadata


class ExampleCoordSystemPlugin(CoordSystemPlugin):
    """示例坐标系插件"""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="example_coord_systems",
            version="1.0.0",
            author="MomentTransfer Team",
            description="提供示例和常见坐标系定义的插件",
            plugin_type="coord_system",
        )

    # 预定义的坐标系数据库
    _COORD_SYSTEMS = {
        "standard_body_frame": {
            "origin": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
            "y_axis": [0.0, 1.0, 0.0],
            "z_axis": [0.0, 0.0, 1.0],
        },
        "wind_frame": {
            "origin": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],  # 风向
            "y_axis": [0.0, 1.0, 0.0],  # 侧向
            "z_axis": [0.0, 0.0, -1.0],  # 竖直（反向）
        },
        "stability_frame": {
            "origin": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
            "y_axis": [0.0, 1.0, 0.0],
            "z_axis": [0.0, 0.0, 1.0],
        },
    }

    def get_coordinate_system(self, name: str) -> Optional[Dict]:
        """获取命名的坐标系"""
        return self._COORD_SYSTEMS.get(name)

    def list_coordinate_systems(self) -> List[str]:
        """列出所有可用的坐标系"""
        return list(self._COORD_SYSTEMS.keys())


# 工厂函数 - 插件加载器会调用此函数
def create_plugin() -> ExampleCoordSystemPlugin:
    """创建插件实例"""
    return ExampleCoordSystemPlugin()
