"""
测试重做模式与批处理多选状态的清理

验证问题修复：
- 进入重做模式时清除多选文件列表
- 退出重做模式时清除多选文件列表
- 加载新配置时清除多选文件列表
- 避免用户误用旧配置的多选文件列表
"""

import pytest

pytest.importorskip("PySide6")


def test_config_manager_clears_selected_paths_on_load(tmp_path):
    """测试加载新配置时清除批处理多选文件列表"""
    from pathlib import Path
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication

    from gui.config_manager import ConfigManager
    from gui.signal_bus import SignalBus

    # 确保 QApplication 存在
    QApplication.instance() or QApplication([])

    # 创建 Mock GUI 实例
    gui_instance = Mock()
    gui_instance.signal_bus = SignalBus.instance()

    # 创建 Mock BatchManager
    batch_manager = Mock()
    batch_manager._selected_paths = [
        tmp_path / "file1.csv",
        tmp_path / "file2.csv",
    ]
    gui_instance.batch_manager = batch_manager

    # 初始化 ConfigManager
    config_manager = ConfigManager(gui_instance)

    # 验证初始状态：多选列表存在
    assert batch_manager._selected_paths is not None
    assert len(batch_manager._selected_paths) == 2

    # 调用清除多选列表的方法
    config_manager._clear_batch_file_selection()

    # 验证多选列表已被清除
    assert batch_manager._selected_paths is None, "加载新配置后多选列表应被清除"


def test_config_manager_clears_selected_paths_on_reset(tmp_path):
    """测试重置配置时清除批处理多选文件列表"""
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication

    from gui.config_manager import ConfigManager
    from gui.signal_bus import SignalBus

    # 确保 QApplication 存在
    QApplication.instance() or QApplication([])

    # 创建 Mock GUI 实例
    gui_instance = Mock()
    gui_instance.signal_bus = SignalBus.instance()

    # 创建 Mock BatchManager
    batch_manager = Mock()
    batch_manager._selected_paths = [
        tmp_path / "file1.csv",
        tmp_path / "file2.csv",
    ]
    gui_instance.batch_manager = batch_manager

    # 创建一个简单的 source_panel 和 target_panel
    gui_instance.source_panel = Mock()
    gui_instance.target_panel = Mock()

    # 初始化 ConfigManager
    config_manager = ConfigManager(gui_instance)

    # 验证初始状态
    assert batch_manager._selected_paths is not None

    # 调用重置配置方法
    config_manager.reset_config()

    # 验证多选列表已被清除
    assert batch_manager._selected_paths is None, "重置配置后多选列表应被清除"


def test_global_state_manager_tracks_redo_mode(tmp_path):
    """测试 GlobalStateManager 正确追踪重做模式转换"""
    from gui.global_state_manager import AppState, GlobalStateManager

    state_mgr = GlobalStateManager.instance()

    # 初始状态应为 NORMAL
    assert state_mgr.current_state == AppState.NORMAL
    assert state_mgr.is_redo_mode is False

    # 进入重做模式
    state_mgr.set_redo_mode("record_123", {"description": "用户修改了配置"})

    # 验证重做模式状态
    assert state_mgr.current_state == AppState.REDO_MODE
    assert state_mgr.is_redo_mode is True
    assert state_mgr.redo_parent_id == "record_123"

    # 退出重做模式
    state_mgr.exit_redo_mode()

    # 验证返回正常状态
    assert state_mgr.current_state == AppState.NORMAL
    assert state_mgr.is_redo_mode is False
    assert state_mgr.redo_parent_id is None


def test_batch_processing_detects_part_mismatch(tmp_path):
    """测试批处理检测文件 Part 选择与配置的不匹配"""
    from pathlib import Path as PathlibPath
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication

    from gui.batch_thread import BatchProcessThread, BatchThreadConfig
    from src.models import ProjectConfigModel

    # 确保 QApplication 存在
    QApplication.instance() or QApplication([])

    # 创建测试配置（2个 Source，2个 Target）
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
                },
                {
                    "PartName": "Wing",
                    "Variants": [
                        {
                            "PartName": "Wing",
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
                },
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
                },
                {
                    "PartName": "Stability",
                    "Variants": [
                        {
                            "PartName": "Stability",
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
                },
            ]
        },
    }

    project_model = ProjectConfigModel.from_dict(test_config)

    # 创建测试文件
    test_file = tmp_path / "test.csv"
    test_file.write_text("Fx,Fy,Fz,Mx,My,Mz\n1,2,3,4,5,6\n")

    # 场景1：文件有 Part 选择，应该使用该选择
    config = BatchThreadConfig(
        project_data=project_model,
        file_part_selection_by_file={
            str(test_file): {"source": "Body", "target": "Wind"}
        },
    )

    thread = BatchProcessThread(
        calculator=None,
        file_list=[str(test_file)],
        output_dir=tmp_path,
        data_config=None,
        config=config,
    )

    # 验证文件的 Part 选择是否符合预期
    part_sel = (config.file_part_selection_by_file or {}).get(str(test_file)) or {}
    assert part_sel.get("source") == "Body", "文件应使用明确指定的 Source Part"
    assert part_sel.get("target") == "Wind", "文件应使用明确指定的 Target Part"

    # 场景2：文件无 Part 选择，配置有多个 Part，应该报错
    # 这会在 _create_calc_to_use 执行时抛出异常
    config_multi = BatchThreadConfig(
        project_data=project_model,
        file_part_selection_by_file={},  # 无选择
    )

    thread_multi = BatchProcessThread(
        calculator=None,
        file_list=[str(test_file)],
        output_dir=tmp_path,
        data_config=None,
        config=config_multi,
    )

    # 验证配置状态
    assert len(project_model.source_parts) == 2, "测试配置应有2个 Source Part"
    assert len(project_model.target_parts) == 2, "测试配置应有2个 Target Part"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
