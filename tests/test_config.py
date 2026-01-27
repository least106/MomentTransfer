import json
from pathlib import Path

import pytest

from src.config import (
    SystemConfig,
    get_config,
    load_config_from_file,
    reset_config,
    set_config,
)


def test_systemconfig_from_dict_and_json_roundtrip():
    cfg_dict = {
        "cache": {"enabled": False, "max_entries": 5},
        "batch": {"chunk_size": 50},
        "physics": {"safe_divide_threshold": 1e-6},
        "plugin": {"auto_load": False},
        "debug_mode": True,
        "log_level": "DEBUG",
    }

    cfg = SystemConfig.from_dict(cfg_dict)
    assert cfg.cache.enabled is False
    assert cfg.cache.max_entries == 5
    assert cfg.batch.chunk_size == 50
    assert cfg.physics.safe_divide_threshold == 1e-6
    assert cfg.plugin.auto_load is False
    assert cfg.debug_mode is True

    json_str = cfg.to_json()
    parsed = json.loads(json_str)
    assert parsed.get("debug_mode") is True
    assert parsed.get("cache", {}).get("max_entries") == 5


def test_from_json_file_missing_and_invalid(tmp_path):
    missing = tmp_path / "noexist.json"
    # missing file should return default SystemConfig
    cfg = SystemConfig.from_json_file(str(missing))
    assert isinstance(cfg, SystemConfig)
    assert cfg.debug_mode is False

    # invalid json should return default and not raise
    bad = tmp_path / "bad.json"
    bad.write_text("not a json", encoding="utf-8")
    cfg2 = SystemConfig.from_json_file(str(bad))
    assert isinstance(cfg2, SystemConfig)


def test_save_and_load_file_and_manager(tmp_path):
    p = tmp_path / "confdir" / "cfg.json"
    cfg = SystemConfig()
    cfg.debug_mode = True
    cfg.log_level = "DEBUG"

    # save should create parent dirs and write file
    cfg.save_to_json_file(str(p))
    assert p.exists()

    # load via module-level helper should set global config
    loaded = load_config_from_file(str(p))
    assert loaded.debug_mode is True
    assert get_config().log_level == "DEBUG"

    # set_config and reset_config
    new_cfg = SystemConfig()
    new_cfg.debug_mode = False
    set_config(new_cfg)
    assert get_config().debug_mode is False

    reset_config()
    assert get_config().debug_mode is False
