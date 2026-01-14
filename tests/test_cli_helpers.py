from src import cli_helpers


def test_batch_config_defaults():
    cfg = cli_helpers.BatchConfig()
    assert cfg.skip_rows == 0
    assert cfg.name_template == "{stem}_result_{timestamp}.csv"
    assert cfg.timestamp_format == "%Y%m%d_%H%M%S"
    assert cfg.overwrite is False
    assert cfg.treat_non_numeric == "zero"
    assert cfg.sample_rows == 5


def test_resolve_file_format_returns_copy():
    cfg = cli_helpers.BatchConfig()
    cfg.skip_rows = 2
    copied = cli_helpers.resolve_file_format("/tmp/foo.csv", cfg)
    assert copied is not cfg
    assert copied.skip_rows == cfg.skip_rows
