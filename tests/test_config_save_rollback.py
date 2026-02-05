"""配置保存失败后的状态回滚测试"""

import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_gui():
    """模拟 GUI 实例"""
    gui = Mock()
    gui.statusBar.return_value = Mock()
    gui.source_panel = Mock()
    gui.target_panel = Mock()
    
    gui.source_panel.to_variant_payload.return_value = {
        "PartName": "Global",
        "Datum": {"X": 0, "Y": 0, "Z": 0},
    }
    gui.target_panel.to_variant_payload.return_value = {
        "PartName": "Target",
        "Datum": {"X": 1, "Y": 1, "Z": 1},
    }
    
    gui.model_manager = Mock()
    gui.model_manager.project_model = None
    gui.ui_state_manager = Mock()
    gui.operation_performed = False
    
    return gui


@pytest.fixture
def config_manager(mock_gui):
    """创建 ConfigManager 实例"""
    from gui.config_manager import ConfigManager
    from gui.signal_bus import SignalBus
    
    signal_bus = SignalBus.instance()
    manager = ConfigManager(mock_gui, signal_bus)
    return manager


@pytest.fixture
def temp_config_file(tmp_path):
    """创建临时配置文件"""
    config_path = tmp_path / "test_config.json"
    config_data = {
        "Source": {"Parts": [{"PartName": "Old", "Variants": [{"PartName": "Old"}]}]},
        "Target": {"Parts": [{"PartName": "Old", "Variants": [{"PartName": "Old"}]}]},
    }
    config_path.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    return config_path


def test_save_success(config_manager, temp_config_file):
    """测试保存成功"""
    config_manager._last_loaded_config_path = temp_config_file
    config_manager._config_modified = True
    
    with patch("gui.config_manager.QMessageBox.information"):
        result = config_manager.save_config()
    
    assert result == True
    assert config_manager._config_modified == False
    
    saved_data = json.loads(temp_config_file.read_text(encoding="utf-8"))
    assert saved_data["Source"]["Parts"][0]["PartName"] == "Global"
    logger.info("✓ 保存成功")


def test_permission_error_keeps_modified_flag(config_manager, temp_config_file):
    """测试权限错误时保持 _config_modified = True"""
    config_manager._last_loaded_config_path = temp_config_file
    config_manager._config_modified = True
    
    with patch("tempfile.mkstemp", side_effect=PermissionError("权限不足")):
        with patch("gui.config_manager.QMessageBox.question", return_value=0):  # No
            result = config_manager.save_config()
    
    assert result == False
    assert config_manager._config_modified == True
    logger.info("✓ 权限错误时保持 _config_modified = True")


def test_model_rollback_on_error(config_manager, temp_config_file):
    """测试保存失败时模型回滚"""
    config_manager._last_loaded_config_path = temp_config_file
    config_manager._config_modified = True
    
    # 记录保存前模型状态
    initial_modified = config_manager._config_modified
    
    with patch("tempfile.mkstemp", side_effect=PermissionError("权限不足")):
        with patch("gui.config_manager.QMessageBox.question", return_value=0):
            result = config_manager.save_config()
    
    # 验证保存失败且状态保持
    assert result == False
    assert config_manager._config_modified == initial_modified  # 应该保持 True
    logger.info("✓ 保存失败时状态保持")


def test_user_cancel_keeps_modified_flag(config_manager):
    """测试用户取消时保持 _config_modified = True"""
    config_manager._config_modified = True
    
    with patch("gui.config_manager.QFileDialog.getSaveFileName", return_value=("", "")):
        result = config_manager.save_config()
    
    assert result == False
    assert config_manager._config_modified == True
    logger.info("✓ 用户取消时保持 _config_modified = True")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
