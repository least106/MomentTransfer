import time


from src import performance as perf


def setup_function():
    # 确保每个测试用独立的监控器
    perf.reset_performance_monitor()


def test_get_and_reset_monitor_singleton():
    a = perf.get_performance_monitor()
    b = perf.get_performance_monitor()
    assert a is b
    perf.reset_performance_monitor()
    c = perf.get_performance_monitor()
    assert c is not a


def test_record_metric_and_get_stats():
    m = perf.get_performance_monitor()
    m.clear_metrics()
    m.record_metric("m1", 10.0)
    m.record_metric("m1", 30.0)
    stats = m.get_stats("m1")
    assert stats["count"] == 2
    assert (
        stats["duration_ms"]["min"]
        <= stats["duration_ms"]["avg"]
        <= stats["duration_ms"]["max"]
    )


def test_measure_context_and_decorator(caplog):
    m = perf.get_performance_monitor()
    m.clear_metrics()

    with m.measure("ctx_test"):
        # 短暂工作以产生可测时长
        time.sleep(0.001)

    @perf.measure_performance
    def fast_func(x):
        return x * 2

    assert fast_func(3) == 6

    stats = m.get_stats("ctx_test")
    assert stats and stats["count"] == 1


def test_get_system_stats_when_psutil_unavailable(monkeypatch):
    # 强制标记 psutil 不可用，函数不应抛异常并返回空字典
    monkeypatch.setattr(perf, "PSUTIL_AVAILABLE", False)
    m = perf.get_performance_monitor()
    stats = m.get_system_stats()
    assert isinstance(stats, dict)
