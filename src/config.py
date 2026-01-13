"""
配置管理系统 - 集中管理所有系统参数、阈值和默认值

支持多种配置源的优先级：
1. 命令行参数（最高优先级）
2. 环境变量
3. 配置文件 (.env, .ini, .json)
4. 系统默认值（最低优先级）
"""

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DataTreatmentStrategy(Enum):
    """非数值数据处理策略"""

    DROP = "drop"  # 丢弃非数值行
    NAN = "nan"  # 保留为 NaN
    ZERO = "zero"  # 替换为 0


@dataclass
class CacheConfig:
    """缓存系统配置"""

    # 缓存启用标志
    enabled: bool = True
    # 最大缓存条目数（LRU 缓存）
    max_entries: int = 1000
    # 缓存的计算结果类型：'rotation', 'transformation', 'all'
    cache_types: List[str] = field(
        default_factory=lambda: ["rotation", "transformation"]
    )
    # 缓存键生成时是否考虑精度（用于浮点数）
    precision_digits: int = 10


@dataclass
class BatchProcessConfig:
    """批处理配置"""

    # 数据块大小（行数）
    chunk_size: int = 10000
    # 非数值处理策略
    treat_non_numeric: str = DataTreatmentStrategy.DROP.value
    # 记录非数值示例的行数
    sample_rows: int = 5
    # 输出文件名模板
    name_template: str = "{stem}_result_{timestamp}.csv"
    # 时间戳格式
    timestamp_format: str = "%Y%m%d_%H%M%S"
    # 最大重试次数
    max_retries: int = 3
    # 文件锁超时（秒）
    file_lock_timeout: float = 5.0
    # 是否启用并行处理
    enable_parallel: bool = True
    # 并行工作进程数（0 = CPU 核心数）
    num_workers: int = 0


@dataclass
class PhysicsConfig:
    """物理计算配置"""

    # 旋转矩阵计算精度阈值
    rotation_precision_threshold: float = 1e-10
    # 力臂计算精度阈值
    moment_arm_threshold: float = 1e-12
    # 无量纲化时的安全除法阈值
    safe_divide_threshold: float = 1e-15
    # 是否在计算中检查NaN
    check_nan: bool = True


@dataclass
class PluginConfig:
    """插件系统配置"""

    # 插件目录
    plugin_dirs: List[str] = field(
        default_factory=lambda: ["./plugins", "./custom_plugins"]
    )
    # 自动加载插件
    auto_load: bool = True
    # 启用的插件列表（空列表表示加载所有）
    enabled_plugins: List[str] = field(default_factory=list)
    # 禁用的插件列表
    disabled_plugins: List[str] = field(default_factory=list)


@dataclass
class SystemConfig:
    """系统配置 - 集中管理所有系统参数"""

    # 子配置
    cache: CacheConfig = field(default_factory=CacheConfig)
    batch: BatchProcessConfig = field(default_factory=BatchProcessConfig)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    plugin: PluginConfig = field(default_factory=PluginConfig)

    # 通用设置
    debug_mode: bool = False
    log_level: str = "INFO"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "SystemConfig":
        """从字典创建配置"""
        cache_fields = {f.name for f in fields(CacheConfig)}
        cache_config = CacheConfig(
            **{
                k: v
                for k, v in config_dict.get("cache", {}).items()
                if k in cache_fields
            }
        )
        batch_config = BatchProcessConfig(
            **{
                k: v
                for k, v in config_dict.get("batch", {}).items()
                if k in {f.name for f in fields(BatchProcessConfig)}
            }
        )
        physics_config = PhysicsConfig(
            **{
                k: v
                for k, v in config_dict.get("physics", {}).items()
                if k in {f.name for f in fields(PhysicsConfig)}
            }
        )
        plugin_config = PluginConfig(
            **{
                k: v
                for k, v in config_dict.get("plugin", {}).items()
                if k in {f.name for f in fields(PluginConfig)}
            }
        )

        return cls(
            cache=cache_config,
            batch=batch_config,
            physics=physics_config,
            plugin=plugin_config,
            debug_mode=config_dict.get("debug_mode", False),
            log_level=config_dict.get("log_level", "INFO"),
        )

    @classmethod
    def from_json_file(cls, filepath: str) -> "SystemConfig":
        """从 JSON 配置文件加载"""
        path = Path(filepath)
        if not path.exists():
            logger.warning("配置文件不存在: %s，使用默认配置", filepath)
            return cls()

        try:
            with open(path, "r", encoding="utf-8") as f:
                config_dict = json.load(f)
            logger.info("从 %s 加载配置成功", filepath)
            return cls.from_dict(config_dict)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("加载配置文件失败: %s，使用默认配置", exc)
            return cls()

    def save_to_json_file(self, filepath: str) -> None:
        """保存配置到 JSON 文件"""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.to_json())
            logger.info("配置已保存到 %s", filepath)
        except OSError as exc:
            logger.error("保存配置失败: %s", exc)


# 使用 ConfigManager 单例管理配置，避免模块级 global


class ConfigManager:
    """管理 `SystemConfig` 单例的管理器。"""

    def __init__(self) -> None:
        self._config: Optional[SystemConfig] = None

    def get_config(self) -> SystemConfig:
        """返回当前配置实例（不存在则创建默认配置）。"""
        if self._config is None:
            self._config = SystemConfig()
        return self._config

    def set_config(self, config: SystemConfig) -> None:
        """设置配置实例。"""
        self._config = config

    def load_config_from_file(self, filepath: str) -> SystemConfig:
        """从文件加载配置并设置为当前配置。"""
        config = SystemConfig.from_json_file(filepath)
        self.set_config(config)
        return config

    def reset_config(self) -> None:
        """重置为默认配置实例。"""
        self._config = SystemConfig()


_CONFIG_MANAGER = ConfigManager()


def get_config() -> SystemConfig:
    """获取全局配置实例（代理到 `_CONFIG_MANAGER`）。"""
    return _CONFIG_MANAGER.get_config()


def set_config(config: SystemConfig) -> None:
    """设置全局配置实例（代理到 `_CONFIG_MANAGER`）。"""
    _CONFIG_MANAGER.set_config(config)


def load_config_from_file(filepath: str) -> SystemConfig:
    """加载配置文件并设置为全局配置（代理到 `_CONFIG_MANAGER`）。"""
    return _CONFIG_MANAGER.load_config_from_file(filepath)


def reset_config() -> None:
    """重置为默认配置（代理到 `_CONFIG_MANAGER`）。"""
    _CONFIG_MANAGER.reset_config()
