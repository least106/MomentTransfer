"""
性能监控系统 - 实时监控应用性能指标

包括：
1. CPU 和内存使用率（如果 psutil 可用）
2. 执行时间统计
3. 缓存效率
4. I/O 性能指标
"""

import logging
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

# 尝试导入 psutil（可选）
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.debug("psutil 不可用，性能监控功能受限")


@dataclass
class PerformanceMetrics:  # pylint: disable=R0902
    """性能指标数据类"""

    metric_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    memory_before_mb: float = 0.0
    memory_after_mb: float = 0.0
    memory_delta_mb: float = 0.0
    cpu_percent: float = 0.0
    io_read_bytes: int = 0
    io_write_bytes: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "metric_name": self.metric_name,
            "duration_ms": self.duration_ms,
            "memory_delta_mb": self.memory_delta_mb,
            "cpu_percent": self.cpu_percent,
            "io_read_bytes": self.io_read_bytes,
            "io_write_bytes": self.io_write_bytes,
            "error": self.error,
        }


class PerformanceMonitor:
    """性能监控器 - 记录和分析应用性能"""

    def __init__(self):
        """初始化监控器"""
        self.metrics: Dict[str, list] = defaultdict(list)
        self.process = psutil.Process() if PSUTIL_AVAILABLE else None
        self.lock = threading.Lock()

    def start_measurement(self, metric_name: str) -> PerformanceMetrics:
        """开始测量"""
        memory_before_mb = 0.0
        if self.process:
            try:
                memory_before_mb = self.process.memory_info().rss / 1024 / 1024
            except (OSError, RuntimeError) as exc:
                # psutil 在某些环境下可能抛出系统/运行时错误，记录为调试信息并忽略
                logger.debug(
                    "无法读取进程内存信息，跳过memory_before: %s",
                    exc,
                    exc_info=True,
                )

        metrics = PerformanceMetrics(
            metric_name=metric_name,
            start_time=time.time(),
            memory_before_mb=memory_before_mb,
        )
        return metrics

    def end_measurement(self, metrics: PerformanceMetrics) -> PerformanceMetrics:
        """结束测量"""
        metrics.end_time = time.time()
        metrics.duration_ms = (metrics.end_time - metrics.start_time) * 1000

        if self.process:
            try:
                metrics.memory_after_mb = self.process.memory_info().rss / 1024 / 1024
                metrics.memory_delta_mb = (
                    metrics.memory_after_mb - metrics.memory_before_mb
                )
                metrics.cpu_percent = self.process.cpu_percent(interval=0.01)
            except (OSError, RuntimeError) as exc:
                logger.debug(
                    "读取进程性能信息失败，略过性能字段: %s",
                    exc,
                    exc_info=True,
                )

        with self.lock:
            self.metrics[metrics.metric_name].append(metrics)

        return metrics

    def record_metric(self, metric_name: str, duration_ms: float, **kwargs) -> None:
        """直接记录指标"""
        metrics = PerformanceMetrics(
            metric_name=metric_name,
            start_time=time.time(),
            end_time=time.time(),
            duration_ms=duration_ms,
            **kwargs,
        )
        with self.lock:
            self.metrics[metric_name].append(metrics)

    @contextmanager
    def measure(self, metric_name: str):
        """上下文管理器 - 测量代码块的执行时间"""
        metrics = self.start_measurement(metric_name)
        try:
            yield metrics
        except Exception as e:
            metrics.error = str(e)
            raise
        finally:
            self.end_measurement(metrics)

    def get_stats(self, metric_name: str) -> Dict:
        """获取指定指标的统计信息"""
        with self.lock:
            metrics_list = self.metrics.get(metric_name, [])

        if not metrics_list:
            return {}

        durations = [m.duration_ms for m in metrics_list if m.duration_ms > 0]
        memory_deltas = [m.memory_delta_mb for m in metrics_list]

        if not durations:
            return {}

        return {
            "count": len(metrics_list),
            "duration_ms": {
                "min": min(durations),
                "max": max(durations),
                "avg": sum(durations) / len(durations),
            },
            "memory_mb": {
                "min": min(memory_deltas),
                "max": max(memory_deltas),
                "avg": sum(memory_deltas) / len(memory_deltas),
            },
            "errors": sum(1 for m in metrics_list if m.error),
        }

    def get_all_stats(self) -> Dict:
        """获取所有指标的统计信息"""
        with self.lock:
            metric_names = list(self.metrics.keys())

        return {name: self.get_stats(name) for name in metric_names}

    def get_system_stats(self) -> Dict:
        """获取系统级统计信息"""
        stats = {}
        if PSUTIL_AVAILABLE:
            try:
                stats["cpu_percent"] = psutil.cpu_percent(interval=0.1)
                stats["memory_percent"] = psutil.virtual_memory().percent
                stats["memory_available_mb"] = (
                    psutil.virtual_memory().available / 1024 / 1024
                )
            except (OSError, RuntimeError) as exc:
                logger.debug("获取系统统计信息失败: %s", exc, exc_info=True)
        return stats

    def clear_metrics(self, metric_name: Optional[str] = None) -> None:
        """清空指标"""
        with self.lock:
            if metric_name:
                if metric_name in self.metrics:
                    del self.metrics[metric_name]
            else:
                self.metrics.clear()

    def log_summary(self) -> None:
        """记录性能摘要"""
        all_stats = self.get_all_stats()
        sys_stats = self.get_system_stats()

        logger.info("=== 性能监控摘要 ===")
        if sys_stats:
            logger.info(
                "系统 CPU: %s%%, 内存: %s%%",
                sys_stats.get("cpu_percent", "N/A"),
                sys_stats.get("memory_percent", "N/A"),
            )

        for metric_name, stats in all_stats.items():
            if stats:
                logger.info(
                    "%s: 计数=%s, 耗时=%.2fms (min: %.2fms, max: %.2fms), 内存Δ=%.2fMB",
                    metric_name,
                    stats["count"],
                    stats["duration_ms"]["avg"],
                    stats["duration_ms"]["min"],
                    stats["duration_ms"]["max"],
                    stats["memory_mb"]["avg"],
                )


def measure_performance(func: Callable) -> Callable:
    """装饰器 - 自动测量函数性能"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        monitor = get_performance_monitor()
        metric_name = f"{func.__module__}.{func.__name__}"

        with monitor.measure(metric_name):
            return func(*args, **kwargs)

    return wrapper


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器实例（使用函数属性作为单例容器，避免模块全局变量）。"""
    inst = getattr(get_performance_monitor, "_instance", None)
    if inst is None:
        inst = PerformanceMonitor()
        setattr(get_performance_monitor, "_instance", inst)
    return inst


def reset_performance_monitor() -> None:
    """重置监控器实例（删除函数属性）。"""
    if hasattr(get_performance_monitor, "_instance"):
        delattr(get_performance_monitor, "_instance")
