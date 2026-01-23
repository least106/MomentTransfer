from src.config.batch_config import BatchConfig, resolve_file_format


def test_batch_config_defaults():
    cfg = BatchConfig()
    assert cfg.skip_rows == 0
    assert "timestamp" in cfg.name_template
    assert cfg.overwrite is False
    assert cfg.treat_non_numeric == "zero"
    assert cfg.sample_rows == 5


def test_resolve_file_format_returns_deepcopy():
    global_cfg = BatchConfig()
    global_cfg.skip_rows = 2

    res = resolve_file_format("some/path.dat", global_cfg)
    assert res is not global_cfg
    # 修改返回的对象不应影响原始 global_cfg
    res.skip_rows = 10
    assert global_cfg.skip_rows == 2
