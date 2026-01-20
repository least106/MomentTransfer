import logging

from src.logging_config import configure_logging


def test_configure_logging_stream(capsys):
    log = configure_logging(None, False)
    assert log.level == logging.INFO
    assert log.propagate is False
    assert any(isinstance(h, logging.StreamHandler) for h in log.handlers)
    # 再次调用不会重复添加 handlers
    len(log.handlers)
    log2 = configure_logging(None, True)
    assert len(log2.handlers) == 1


def test_configure_logging_file(tmp_path):
    f = tmp_path / "log.txt"
    log = configure_logging(str(f), True)
    log.debug("debug-msg")
    log.info("info-msg")
    # 尝试刷新可能存在的 file handler
    for h in list(log.handlers):
        try:
            h.flush()
        except Exception:
            pass

    content = f.read_text(encoding="utf-8")
    assert "info-msg" in content or "debug-msg" in content
