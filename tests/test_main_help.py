import logging
from src import __main__ as main_mod


def test_print_help_logs_info(caplog):
    """确认 print_help() 会写入 INFO 级别的帮助信息"""
    caplog.set_level(logging.INFO)
    main_mod.print_help()
    # 至少有一条 INFO 日志包含关键字 MomentTransform
    logs = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert any("MomentTransform" in m for m in logs)
