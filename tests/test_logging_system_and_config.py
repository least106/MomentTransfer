import json
import logging

import pytest

from src.logging_config import configure_logging
from src.logging_system import LoggerFactory, log_operation_context


def _parse_json_lines(s: str):
    lines = [ln for ln in s.splitlines() if ln.strip()]
    parsed = []
    for ln in lines:
        try:
            parsed.append(json.loads(ln))
        except Exception:
            # 忽略非 JSON 行
            continue
    return parsed


def test_structured_formatter_and_logger_factory_json(capsys):
    LoggerFactory.reset()
    LoggerFactory.configure(log_level="INFO", json_output=True)
    logger = LoggerFactory.get_logger("testlogger")

    logger.info("hello %s", "world")

    out = capsys.readouterr().out
    parsed = _parse_json_lines(out)
    assert parsed, "没有输出 JSON 日志"
    entry = parsed[-1]
    for key in (
        "timestamp",
        "level",
        "logger",
        "module",
        "function",
        "line",
        "message",
    ):
        assert key in entry
    assert entry["level"] == "INFO"


def test_log_context_and_operation_context(capsys):
    LoggerFactory.reset()
    LoggerFactory.configure(log_level="INFO", json_output=True)

    with log_operation_context("op1", "ctx1", user="u") as logger:
        logger.info("doing")

    out = capsys.readouterr().out
    parsed = _parse_json_lines(out)
    # 至少两条日志：开始与完成
    assert len(parsed) >= 2
    # 确认 context 字段出现在日志中
    assert any("context" in e and e["context"]["context_id"] == "ctx1" for e in parsed)


def test_log_operation_context_exception_path(capsys):
    LoggerFactory.reset()
    LoggerFactory.configure(log_level="INFO", json_output=True)

    with pytest.raises(RuntimeError):
        with log_operation_context("opX", "ctxX"):
            raise RuntimeError("err")

    out = capsys.readouterr().out
    parsed = _parse_json_lines(out)
    # 应包含 ERROR 级别的日志条目
    assert any(e.get("level") == "ERROR" for e in parsed)


def test_logger_factory_idempotent_and_reset():
    LoggerFactory.reset()
    LoggerFactory.configure(log_level="INFO", json_output=False)
    # 再次调用不会重复初始化
    LoggerFactory.configure(log_level="DEBUG", json_output=False)
    # 仍可获取 logger
    l1 = LoggerFactory.get_logger("a")
    l2 = LoggerFactory.get_logger("a")
    assert l1 is l2
    LoggerFactory.reset()


def test_configure_logging_handles_handlers_and_file(tmp_path):
    # 无文件时返回 batch logger
    batch = configure_logging(None, verbose=False)
    assert batch.name == "batch"
    assert batch.propagate is False
    assert any(isinstance(h, logging.StreamHandler) for h in batch.handlers)

    # 加文件处理器
    fn = tmp_path / "log.txt"
    batch2 = configure_logging(str(fn), verbose=True)
    assert any(h.__class__.__name__ == "FileHandler" for h in batch2.handlers)


def test_configure_logging_closes_existing_handlers_gracefully(monkeypatch):
    # 给 batch logger 添加入会在 close 时抛异常的 handler，确认 configure_logging 不抛
    batch = logging.getLogger("batch")

    class BadHandler(logging.StreamHandler):
        def close(self):
            raise OSError("close fail")

    bad = BadHandler()
    batch.addHandler(bad)

    # 应不抛出异常
    configure_logging(None, verbose=False)
