import time
import types

import pytest

from src import performance as perf


def test_singleton_and_reset():
    perf.reset_performance_monitor()
    a = perf.get_performance_monitor()
    b = perf.get_performance_monitor()
    assert a is b
    perf.reset_performance_monitor()
    c = perf.get_performance_monitor()
    assert c is not a


def test_measure_context_records_metrics():
    perf.reset_performance_monitor()
    monitor = perf.get_performance_monitor()
    # ensure empty
    monitor.clear_metrics()
    with monitor.measure("mymetric"):
        time.sleep(0.001)

    stats = monitor.get_stats("mymetric")
    assert stats and stats.get("count") >= 1


def test_measure_decorator_records_metric():
    perf.reset_performance_monitor()
    monitor = perf.get_performance_monitor()

    @perf.measure_performance
    def quick(x):
        return x + 1

    assert quick(2) == 3
    # the decorator records under module.func name
    name = f"{quick.__module__}.{quick.__name__}"
    metrics_list = monitor.metrics.get(name, [])
    assert len(metrics_list) >= 1


def test_measure_context_exception_sets_error():
    perf.reset_performance_monitor()
    monitor = perf.get_performance_monitor()
    with pytest.raises(RuntimeError):
        with monitor.measure("errmetric"):
            raise RuntimeError("boom")

    metrics_list = monitor.metrics.get("errmetric", [])
    assert len(metrics_list) >= 1 and metrics_list[0].error is not None


def test_get_system_stats_with_psutil_stub(monkeypatch):
    # stub psutil object on the module
    class DummyVM:
        percent = 12.3
        available = 1024 * 1024 * 10

    class DummyPsutil:
        @staticmethod
        def cpu_percent(interval=0.1):
            return 2.5

        @staticmethod
        def virtual_memory():
            return DummyVM()

    # force module to think psutil is available
    monkeypatch.setattr(perf, "PSUTIL_AVAILABLE", True)
    monkeypatch.setattr(perf, "psutil", DummyPsutil)

    monitor = perf.get_performance_monitor()
    stats = monitor.get_system_stats()
    assert "cpu_percent" in stats and "memory_percent" in stats
