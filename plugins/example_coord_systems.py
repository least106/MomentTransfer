"""
示例坐标系插件 - 演示如何创建自定义坐标系定义插件

这个插件预定义了几个常见的坐标系供用户快速选择。
"""

from typing import List, Optional, Dict
from src.plugin import CoordSystemPlugin, PluginMetadata


class ExampleCoordSystemPlugin(CoordSystemPlugin):
    """示例坐标系插件"""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name='example_coord_systems',
            version='1.0.0',
            author='MomentTransfer Team',
            description='提供示例和常见坐标系定义的插件',
            plugin_type='coord_system'
        )

    # 预定义的坐标系数据库
    _COORD_SYSTEMS = {
        'standard_body_frame': {
            'origin': [0.0, 0.0, 0.0],
            'x_axis': [1.0, 0.0, 0.0],
            'y_axis': [0.0, 1.0, 0.0],
            'z_axis': [0.0, 0.0, 1.0],
        },
        'wind_frame': {
            'origin': [0.0, 0.0, 0.0],
            'x_axis': [1.0, 0.0, 0.0],  # 风向
            'y_axis': [0.0, 1.0, 0.0],  # 侧向
            'z_axis': [0.0, 0.0, -1.0],  # 竖直（反向）
        },
        'stability_frame': {
            'origin': [0.0, 0.0, 0.0],
            'x_axis': [1.0, 0.0, 0.0],
            'y_axis': [0.0, 1.0, 0.0],
            'z_axis': [0.0, 0.0, 1.0],
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
