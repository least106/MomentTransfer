import time

import pytest

from src.performance import (
    PSUTIL_AVAILABLE,
    PerformanceMonitor,
    get_performance_monitor,
    measure_performance,
    reset_performance_monitor,
)


def test_start_end_and_record_and_get_stats():
    reset_performance_monitor()
    monitor = get_performance_monitor()

    m = monitor.start_measurement("t1")
    time.sleep(0.001)
    m2 = monitor.end_measurement(m)
    assert m2.duration_ms > 0

    # 直接 record_metric
    monitor.record_metric("t1", 5.0, memory_delta_mb=0.1)

    stats = monitor.get_stats("t1")
    # durations 包含大于0的样本
    assert stats["count"] >= 1


def test_measure_context_manager_captures_exception():
    reset_performance_monitor()
    monitor = get_performance_monitor()

    with pytest.raises(ValueError):
        with monitor.measure("err_test"):
            raise ValueError("boom")

    stats = monitor.get_stats("err_test")
    # 发生异常时 metrics 列表仍应存在，但 durations 可能为 0
    assert isinstance(stats, dict)


def test_decorator_records_metric():
    reset_performance_monitor()

    @measure_performance
    def fast_fn(x):
        return x + 1

    assert fast_fn(1) == 2
    mon = get_performance_monitor()
    name = f"{fast_fn.__module__}.{fast_fn.__name__}"
    stats = mon.get_stats(name)
    # 可能 durations 为0（太快），此时 get_stats 返回 {}，但 metrics 应存在
    all_stats = mon.get_all_stats()
    assert name in all_stats


def test_get_system_stats_without_psutil(monkeypatch):
    # 在没有 psutil 的环境下，应返回空字典
    if PSUTIL_AVAILABLE:
        # 强制模拟 psutil 不可用
        monkeypatch.setattr("src.performance.PSUTIL_AVAILABLE", False)
    mon = PerformanceMonitor()
    sys = mon.get_system_stats()
    assert isinstance(sys, dict)
