"""
插件系统 - 支持自定义坐标系定义和扩展功能

插件接口：
1. CoordSystemPlugin: 自定义坐标系定义
2. TransformationPlugin: 自定义坐标转换算法
3. OutputPlugin: 自定义输出格式
"""

import importlib.util
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PluginMetadata:
    """插件元数据"""

    name: str  # 插件名称
    version: str  # 版本
    author: str  # 作者
    description: str  # 描述
    plugin_type: str  # 插件类型：'coord_system', 'transformation', 'output'


class BasePlugin(ABC):
    """所有插件的基类"""

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """返回插件元数据"""
        raise NotImplementedError()

    def initialize(self, _config: Dict[str, Any]) -> None:
        """
        初始化插件（可选）

        参数：
            config: 插件特定的配置字典
        """
        return None

    def shutdown(self) -> None:
        """关闭插件时的清理工作（可选）"""
        return None


class CoordSystemPlugin(BasePlugin):
    """坐标系定义插件"""

    @abstractmethod
    def get_coordinate_system(self, name: str) -> Optional[Dict[str, List[float]]]:
        """
        获取命名的坐标系定义

        返回格式：
        {
            'origin': [x, y, z],
            'x_axis': [x, y, z],
            'y_axis': [x, y, z],
            'z_axis': [x, y, z]
        }
        """
        raise NotImplementedError()

    @abstractmethod
    def list_coordinate_systems(self) -> List[str]:
        """列出所有可用的坐标系"""
        raise NotImplementedError()


class TransformationPlugin(BasePlugin):
    """自定义坐标转换算法插件"""

    @abstractmethod
    def transform(
        self,
        forces: np.ndarray,
        moments: np.ndarray,
        rotation_matrix: np.ndarray,
        moment_arm: np.ndarray,
    ) -> Dict[str, np.ndarray]:
        """
        执行自定义坐标转换

        参数：
            forces: (N, 3) 力数组
            moments: (N, 3) 力矩数组
            rotation_matrix: (3, 3) 旋转矩阵
            moment_arm: (3,) 力臂向量

        返回：
            包含转换后的力、力矩和系数的字典
        """
        raise NotImplementedError()


class OutputPlugin(BasePlugin):
    """自定义输出格式插件"""

    @abstractmethod
    def write(self, data: Dict[str, np.ndarray], output_path: Path, **kwargs) -> None:
        """
        以自定义格式写入数据

        参数：
            data: 计算结果数据
            output_path: 输出文件路径
            kwargs: 其他选项
        """
        raise NotImplementedError()

    @abstractmethod
    def get_supported_formats(self) -> List[str]:
        """获取支持的文件格式"""
        raise NotImplementedError()


class PluginRegistry:
    """插件注册表 - 管理所有已加载的插件"""

    def __init__(self):
        """初始化插件注册表"""
        self.plugins: Dict[str, BasePlugin] = {}
        self.coord_system_plugins: Dict[str, CoordSystemPlugin] = {}
        self.transformation_plugins: Dict[str, TransformationPlugin] = {}
        self.output_plugins: Dict[str, OutputPlugin] = {}

    def register(self, plugin: BasePlugin) -> None:
        """注册插件"""
        metadata = plugin.metadata
        name = metadata.name
        if name in self.plugins:
            logger.warning("插件 %s 已存在，将被覆盖", name)

        self.plugins[name] = plugin

        # 按类型分类注册
        if isinstance(plugin, CoordSystemPlugin):
            self.coord_system_plugins[name] = plugin
            logger.info("已注册坐标系插件: %s v%s", name, metadata.version)
        elif isinstance(plugin, TransformationPlugin):
            self.transformation_plugins[name] = plugin
            logger.info("已注册转换插件: %s v%s", name, metadata.version)
        elif isinstance(plugin, OutputPlugin):
            self.output_plugins[name] = plugin
            logger.info("已注册输出插件: %s v%s", name, metadata.version)

    def unregister(self, name: str) -> None:
        """注销插件"""
        if name in self.plugins:
            plugin = self.plugins[name]
            plugin.shutdown()
            del self.plugins[name]

            if isinstance(plugin, CoordSystemPlugin):
                del self.coord_system_plugins[name]
            elif isinstance(plugin, TransformationPlugin):
                del self.transformation_plugins[name]
            elif isinstance(plugin, OutputPlugin):
                del self.output_plugins[name]

            logger.info("已注销插件: %s", name)

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """获取指定的插件"""
        return self.plugins.get(name)

    def get_coord_system_plugin(self, name: str) -> Optional[CoordSystemPlugin]:
        """获取坐标系插件"""
        return self.coord_system_plugins.get(name)

    def get_transformation_plugin(self, name: str) -> Optional[TransformationPlugin]:
        """获取转换插件"""
        return self.transformation_plugins.get(name)

    def get_output_plugin(self, name: str) -> Optional[OutputPlugin]:
        """获取输出插件"""
        return self.output_plugins.get(name)

    def list_plugins(self, plugin_type: Optional[str] = None) -> List[str]:
        """列出所有插件"""
        if plugin_type == "coord_system":
            return list(self.coord_system_plugins.keys())
        if plugin_type == "transformation":
            return list(self.transformation_plugins.keys())
        if plugin_type == "output":
            return list(self.output_plugins.keys())

        return list(self.plugins.keys())


class PluginLoader:
    """插件加载器 - 从文件系统加载插件"""

    def __init__(self, registry: PluginRegistry):
        """初始化插件加载器"""
        self.registry = registry

    def load_plugin_from_file(self, filepath: Path) -> Optional[BasePlugin]:
        """
        从 Python 文件加载插件

        约定：插件文件应包含一个继承自 BasePlugin 的类，
        且该类应有 `create_plugin()` 工厂函数。
        """
        filepath = Path(filepath)
        if not filepath.exists():
            logger.error("插件文件不存在: %s", filepath)
            return None

        try:
            # 动态加载模块
            spec = importlib.util.spec_from_file_location(filepath.stem, filepath)
            if spec is None or spec.loader is None:
                logger.error("无法加载模块: %s", filepath)
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 查找 create_plugin 工厂函数
            if hasattr(module, "create_plugin"):
                plugin = module.create_plugin()
                self.registry.register(plugin)
                logger.info("成功加载插件: %s", filepath)
                return plugin

            logger.error("插件 %s 不包含 create_plugin() 函数", filepath)
            return None

        except (OSError, ImportError, AttributeError, SyntaxError) as exc:
            # 捕获常见的加载/语法错误并记录
            logger.error("加载插件 %s 失败: %s", filepath, exc, exc_info=True)
            return None
        except Exception as exc:  # pylint: disable=broad-except
            # 插件代码可能在导入时抛出任意异常；记录并继续
            logger.error("加载插件 %s 失败: %s", filepath, exc, exc_info=True)
            return None

    def load_plugins_from_directory(self, directory: Path) -> List[BasePlugin]:
        """从目录加载所有插件"""
        directory = Path(directory)
        if not directory.exists():
            logger.warning("插件目录不存在: %s", directory)
            return []

        plugins = []
        for plugin_file in directory.glob("*.py"):
            if plugin_file.name.startswith("_"):
                continue  # 跳过私有文件

            plugin = self.load_plugin_from_file(plugin_file)
            if plugin:
                plugins.append(plugin)

        logger.info("从 %s 加载了 %d 个插件", directory, len(plugins))
        return plugins


# 使用 PluginManager 单例管理插件注册表，避免模块级 global


class PluginManager:
    """管理全局 `PluginRegistry` 实例的管理器。"""

    def __init__(self) -> None:
        self._registry: Optional[PluginRegistry] = None

    def get_registry(self) -> PluginRegistry:
        """返回或创建 `PluginRegistry` 单例实例。"""
        if self._registry is None:
            self._registry = PluginRegistry()
        return self._registry

    def clear(self) -> None:
        """清空已创建的 `PluginRegistry`（若存在）。"""
        if self._registry is not None:
            # 注销并清理所有插件
            for name in list(self._registry.list_plugins()):
                try:
                    self._registry.unregister(name)
                except Exception:  # pylint: disable=broad-except
                    # 忽略注销时的插件错误
                    pass
            self._registry = None


_PLUGIN_MANAGER = PluginManager()


def get_plugin_registry() -> PluginRegistry:
    """获取全局插件注册表（代理到 `_PLUGIN_MANAGER`）。"""
    return _PLUGIN_MANAGER.get_registry()


def load_plugins_from_config(config_dirs: List[str]) -> None:
    """
    根据配置目录加载所有插件

    参数：
        config_dirs: 插件目录列表
    """
    registry = get_plugin_registry()
    loader = PluginLoader(registry)

    for directory in config_dirs:
        loader.load_plugins_from_directory(Path(directory))
