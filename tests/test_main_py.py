import logging

from src import __main__ as main_mod


def test_print_help_logs_info(caplog):
    caplog.set_level(logging.INFO)
    main_mod.print_help()
    # 确认日志中包含包名和关键描述
    assert any("MomentTransform" in rec.getMessage() for rec in caplog.records)


def test_module_exec_does_not_raise(monkeypatch):
    # 在作为脚本执行分支不会在测试中自动触发；直接调用 print_help 覆盖行为即可
    main_mod.print_help()
