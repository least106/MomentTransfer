"""
配置系统、缓存系统和插件系统的单元测试
"""

import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pytest

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cache import (CacheKey, CalculationCache, RotationMatrixCache,
                       TransformationCache)
from src.config import SystemConfig, get_config, reset_config
from src.plugin import (CoordSystemPlugin, PluginMetadata, PluginRegistry,
                        get_plugin_registry)


class TestConfigSystem:
    """配置系统测试"""

    def test_default_config_creation(self):
        """测试默认配置创建"""
        config = SystemConfig()
        assert config.cache.enabled is True
        assert config.batch.chunk_size == 10000
        assert config.physics.check_nan is True

    def test_config_to_dict(self):
        """测试配置转字典"""
        config = SystemConfig()
        config_dict = config.to_dict()
        assert "cache" in config_dict
        assert "batch" in config_dict
        assert "physics" in config_dict

    def test_config_to_json(self):
        """测试配置转 JSON"""
        config = SystemConfig()
        json_str = config.to_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert "cache" in parsed

    def test_config_from_dict(self):
        """测试从字典创建配置"""
        config_dict = {
            "cache": {"enabled": False, "max_entries": 500},
            "batch": {"chunk_size": 5000},
            "physics": {},
            "plugin": {},
            "debug_mode": True,
        }
        config = SystemConfig.from_dict(config_dict)
        assert config.cache.enabled is False
        assert config.cache.max_entries == 500
        assert config.batch.chunk_size == 5000
        assert config.debug_mode is True

    def test_config_file_save_and_load(self):
        """测试配置文件保存和加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            # 创建并保存配置
            config = SystemConfig()
            config.cache.max_entries = 2000
            config.save_to_json_file(str(config_path))

            # 加载配置
            loaded_config = SystemConfig.from_json_file(str(config_path))
            assert loaded_config.cache.max_entries == 2000

    def test_global_config(self):
        """测试全局配置"""
        reset_config()
        config1 = get_config()
        config1.cache.max_entries = 5000

        config2 = get_config()
        assert config2.cache.max_entries == 5000


class TestCacheSystem:
    """缓存系统测试"""

    def test_calculation_cache_basic(self):
        """测试基本缓存操作"""
        cache = CalculationCache(max_entries=10)

        # 测试缓存未命中
        result = cache.get(("key1",))
        assert result is None

        # 缓存值
        cache.set(("key1",), np.array([1, 2, 3]))
        result = cache.get(("key1",))
        np.testing.assert_array_equal(result, np.array([1, 2, 3]))

    def test_cache_lru_eviction(self):
        """测试 LRU 缓存驱逐"""
        cache = CalculationCache(max_entries=3)

        # 添加 4 个条目（超过限制）
        for i in range(4):
            cache.set((f"key{i}",), f"value{i}")

        # 最旧的条目应该被驱逐
        assert cache.get(("key0",)) is None
        assert cache.get(("key3",)) is not None

    def test_cache_stats(self):
        """测试缓存统计"""
        cache = CalculationCache(max_entries=10)
        cache.set(("key1",), "value1")

        cache.get(("key1",))  # 缓存命中
        cache.get(("key2",))  # 缓存未命中

        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["entries"] == 1

    def test_rotation_matrix_cache(self):
        """测试旋转矩阵缓存"""
        cache = RotationMatrixCache(max_entries=10)

        basis_source = np.eye(3)
        basis_target = np.eye(3)
        rotation_matrix = np.eye(3)

        # 缓存旋转矩阵
        cache.set_rotation_matrix(basis_source, basis_target, rotation_matrix)

        # 获取缓存
        result = cache.get_rotation_matrix(basis_source, basis_target)
        assert result is not None
        np.testing.assert_array_equal(result, rotation_matrix)

    def test_transformation_cache(self):
        """测试坐标转换缓存"""
        cache = TransformationCache(max_entries=10)

        basis_target = np.eye(3)
        vector = np.array([1.0, 2.0, 3.0])
        result_vec = np.array([1.0, 2.0, 3.0])

        # 缓存转换
        cache.set_transformation(basis_target, vector, result_vec)

        # 获取缓存
        result = cache.get_transformation(basis_target, vector)
        assert result is not None
        np.testing.assert_array_equal(result, result_vec)

    def test_cache_key_generation(self):
        """测试缓存键生成"""
        arr = np.array([1.23456789, 2.34567890, 3.45678901])
        key = CacheKey.array_to_tuple(arr, precision_digits=5)

        # 精度舍入后应该相同
        arr_rounded = np.around(arr, decimals=5)
        key_expected = tuple(arr_rounded.flatten().tolist())
        assert key == key_expected


class TestPluginSystem:
    """插件系统测试"""

    def test_plugin_registry_creation(self):
        """测试插件注册表创建"""
        registry = PluginRegistry()
        assert len(registry.list_plugins()) == 0

    def test_plugin_registration(self):
        """测试插件注册"""
        registry = PluginRegistry()

        # 创建测试插件
        class TestCoordPlugin(CoordSystemPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="test_plugin",
                    version="1.0.0",
                    author="Test",
                    description="Test plugin",
                    plugin_type="coord_system",
                )

            def get_coordinate_system(self, name: str) -> Optional[Dict]:
                return None

            def list_coordinate_systems(self) -> List[str]:
                return []

        plugin = TestCoordPlugin()
        registry.register(plugin)

        assert len(registry.list_plugins()) == 1
        assert registry.get_plugin("test_plugin") is not None
        assert registry.get_coord_system_plugin("test_plugin") is not None

    def test_plugin_unregistration(self):
        """测试插件注销"""
        registry = PluginRegistry()

        class TestPlugin(CoordSystemPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="test",
                    version="1.0",
                    author="Test",
                    description="Test",
                    plugin_type="coord_system",
                )

            def get_coordinate_system(self, name: str):
                return None

            def list_coordinate_systems(self) -> List[str]:
                return []

        plugin = TestPlugin()
        registry.register(plugin)
        registry.unregister("test")

        assert registry.get_plugin("test") is None

    def test_global_plugin_registry(self):
        """测试全局插件注册表"""
        registry = get_plugin_registry()
        assert isinstance(registry, PluginRegistry)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
