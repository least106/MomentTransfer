"""
测试 ConfigManager 对 Part 列表修改的状态追踪

验证问题修复：
- ConfigManager 现在监听 SignalBus 的 partAdded / partRemoved 信号
- 当 Source/Target Part 通过 PartManager 添加/删除时，配置被正确标记为已修改
- 运行批处理前会提示"配置已修改，是否保存"
"""

import pytest

# 如果缺少 PySide6 则跳过整个模块
pytest.importorskip("PySide6")


def test_config_manager_detects_part_addition(tmp_path):
    """测试 ConfigManager 检测到 Part 添加时标记为已修改"""
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication

    from gui.config_manager import ConfigManager
    from gui.signal_bus import SignalBus

    # 确保 QApplication 存在
    QApplication.instance() or QApplication([])

    # 创建 Mock GUI 实例
    gui_instance = Mock()
    gui_instance.signal_bus = SignalBus.instance()

    # 初始化 ConfigManager
    config_manager = ConfigManager(gui_instance)

    # 初始状态：配置未修改
    assert config_manager.is_config_modified() is False

    # 模拟 Part 添加信号
    gui_instance.signal_bus.partAdded.emit("Source", "新Part")

    # 配置应该被标记为已修改
    assert (
        config_manager.is_config_modified() is True
    ), "添加 Source Part 后，配置应被标记为已修改"


def test_config_manager_detects_part_removal(tmp_path):
    """测试 ConfigManager 检测到 Part 删除时标记为已修改"""
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication

    from gui.config_manager import ConfigManager
    from gui.signal_bus import SignalBus

    # 确保 QApplication 存在
    QApplication.instance() or QApplication([])

    # 创建 Mock GUI 实例
    gui_instance = Mock()
    gui_instance.signal_bus = SignalBus.instance()

    # 初始化 ConfigManager
    config_manager = ConfigManager(gui_instance)

    # 初始状态：配置未修改
    assert config_manager.is_config_modified() is False

    # 模拟 Part 删除信号
    gui_instance.signal_bus.partRemoved.emit("Target", "旧Part")

    # 配置应该被标记为已修改
    assert (
        config_manager.is_config_modified() is True
    ), "删除 Target Part 后，配置应被标记为已修改"


def test_config_manager_part_list_snapshot(tmp_path):
    """测试 ConfigManager 正确捕获 Part 列表快照"""
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication

    from gui.config_manager import ConfigManager
    from gui.signal_bus import SignalBus
    from src.data_loader import ProjectData
    from src.models import ProjectConfigModel

    # 确保 QApplication 存在
    QApplication.instance() or QApplication([])

    # 创建测试项目数据
    test_config = {
        "Source": {
            "Parts": [
                {
                    "PartName": "Body",
                    "Variants": [
                        {
                            "PartName": "Body",
                            "CoordSystem": {
                                "Orig": [0, 0, 0],
                                "X": [1, 0, 0],
                                "Y": [0, 1, 0],
                                "Z": [0, 0, 1],
                            },
                            "MomentCenter": [0, 0, 0],
                            "Q": 100.0,
                            "S": 10.0,
                        }
                    ],
                }
            ]
        },
        "Target": {
            "Parts": [
                {
                    "PartName": "Wind",
                    "Variants": [
                        {
                            "PartName": "Wind",
                            "CoordSystem": {
                                "Orig": [0, 0, 0],
                                "X": [1, 0, 0],
                                "Y": [0, 1, 0],
                                "Z": [0, 0, 1],
                            },
                            "MomentCenter": [0, 0, 0],
                            "Q": 100.0,
                            "S": 10.0,
                        }
                    ],
                }
            ]
        },
    }

    # 创建项目模型
    project_model = ProjectConfigModel.from_dict(test_config)
    project_data = ProjectData.from_dict(test_config)

    # 创建 Mock GUI 实例
    gui_instance = Mock()
    gui_instance.signal_bus = SignalBus.instance()
    gui_instance.current_config = project_data

    # 初始化 ConfigManager
    config_manager = ConfigManager(gui_instance)

    # 获取初始快照
    snapshot = config_manager.get_full_config_snapshot()

    assert snapshot is not None, "快照应该被生成"
    assert snapshot["source_part_names"] == ["Body"], "Source Part 名称列表应包含 Body"
    assert snapshot["target_part_names"] == ["Wind"], "Target Part 名称列表应包含 Wind"
    assert snapshot["payload"] is not None, "payload 应该存在"


def test_config_manager_detects_part_list_changes(tmp_path):
    """测试 ConfigManager 检测 Part 列表变化"""
    import copy
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication

    from gui.config_manager import ConfigManager
    from gui.signal_bus import SignalBus
    from src.models import ProjectConfigModel

    # 确保 QApplication 存在
    QApplication.instance() or QApplication([])

    # 创建测试项目数据
    test_config = {
        "Source": {
            "Parts": [
                {
                    "PartName": "Body",
                    "Variants": [
                        {
                            "PartName": "Body",
                            "CoordSystem": {
                                "Orig": [0, 0, 0],
                                "X": [1, 0, 0],
                                "Y": [0, 1, 0],
                                "Z": [0, 0, 1],
                            },
                            "MomentCenter": [0, 0, 0],
                            "Q": 100.0,
                            "S": 10.0,
                        }
                    ],
                }
            ]
        },
        "Target": {
            "Parts": [
                {
                    "PartName": "Wind",
                    "Variants": [
                        {
                            "PartName": "Wind",
                            "CoordSystem": {
                                "Orig": [0, 0, 0],
                                "X": [1, 0, 0],
                                "Y": [0, 1, 0],
                                "Z": [0, 0, 1],
                            },
                            "MomentCenter": [0, 0, 0],
                            "Q": 100.0,
                            "S": 10.0,
                        }
                    ],
                }
            ]
        },
    }

    # 创建项目模型
    project_model = ProjectConfigModel.from_dict(test_config)

    # 创建 Mock GUI 实例
    gui_instance = Mock()
    gui_instance.signal_bus = SignalBus.instance()
    gui_instance.current_config = project_model

    # 初始化 ConfigManager
    config_manager = ConfigManager(gui_instance)

    # 保存初始快照
    config_manager._loaded_snapshot = config_manager.get_full_config_snapshot()
    config_manager._config_modified = False

    # 验证初始状态
    assert not config_manager._part_list_changed_since_load(), "初始时 Part 列表未改变"

    # 模拟添加新 Part：向 source_parts 添加 "Wing"
    try:
        if hasattr(project_model, "source_parts"):
            project_model.source_parts["Wing"] = project_model.source_parts["Body"]
    except Exception as e:
        pytest.skip(f"项目模型不支持直接修改: {e}")

    # 检测变化
    has_changed = config_manager._part_list_changed_since_load()
    assert has_changed, "添加新 Part 后，应检测到 Part 列表变化"


def test_config_manager_emits_modification_signal(tmp_path):
    """测试 Part 修改时 ConfigManager 发出配置修改信号"""
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication

    from gui.config_manager import ConfigManager
    from gui.signal_bus import SignalBus

    # 确保 QApplication 存在
    QApplication.instance() or QApplication([])

    # 创建 Mock GUI 实例
    gui_instance = Mock()
    gui_instance.signal_bus = SignalBus.instance()

    # 初始化 ConfigManager
    config_manager = ConfigManager(gui_instance)

    # 监听 configModified 信号
    signal_emitted = []

    def on_modified(state):
        signal_emitted.append(state)

    gui_instance.signal_bus.configModified.connect(on_modified)

    # 模拟 Part 添加
    gui_instance.signal_bus.partAdded.emit("Source", "新Part")

    # 验证信号发出
    assert len(signal_emitted) > 0, "应该发出 configModified 信号"
    assert signal_emitted[-1] is True, "应该发出 modified=True 的信号"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
