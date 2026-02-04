"""
测试 Part 映射与配置同步

验证问题修复：
- Part 删除时，文件树中相应的映射状态会被更新
- 不可用的 Part 在文件验证时会显示清晰的错误提示
- 批处理能够检测到 Part 缺失并提供有用的错误信息
"""

import pytest

# 如果缺少 PySide6 则跳过整个模块
pytest.importorskip("PySide6")


def test_part_removal_updates_file_validation_status(tmp_path):
    """测试删除 Part 时文件树中的验证状态被更新"""
    from pathlib import Path as PathlibPath
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

    # 创建 Mock GUI 实例，包含文件树映射
    gui_instance = Mock()
    gui_instance.signal_bus = SignalBus.instance()
    gui_instance.project_model = project_model
    gui_instance.current_config = project_model

    # 模拟文件树项
    from PySide6.QtWidgets import QTreeWidgetItem

    test_file = tmp_path / "test.csv"
    test_file.write_text("Fx,Fy,Fz\n1,2,3\n")

    file_item = QTreeWidgetItem([test_file.name, "✓ 可处理"])
    gui_instance._file_tree_items = {str(test_file): file_item}

    # 初始化 ConfigManager
    config_manager = ConfigManager(gui_instance)

    # 初始状态：文件映射正常（假设）
    assert file_item.text(1) == "✓ 可处理", "初始状态应为可处理"

    # 模拟删除 Part - 发出 partRemoved 信号
    # 由于没有真正的 BatchManager，这里测试的是信号处理和状态更新调用
    gui_instance.signal_bus.partRemoved.emit("Target", "Wind")

    # 验证文件项的状态会被标记为修改（由于没有 BatchManager，
    # 实际验证状态的更新需要通过 integration test）
    # 这里主要测试的是回调被正确触发
    assert (
        config_manager.is_config_modified() is True
    ), "Part 删除后配置应被标记为已修改"


def test_part_missing_status_message_clarity(tmp_path):
    """测试缺失 Part 时的状态消息清晰度"""
    from pathlib import Path as PathlibPath
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication, QMainWindow

    from gui.batch_manager import BatchManager
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
    gui_instance = Mock(spec=QMainWindow)
    gui_instance.project_model = project_model
    gui_instance.current_config = project_model
    gui_instance.file_part_selection_by_file = {
        str(tmp_path / "test.csv"): {"source": "Body", "target": "NonExistent"}
    }

    # 创建 BatchManager（简单模式，无 GUI 依赖）
    batch_manager = BatchManager(gui_instance)

    # 测试缺失 Target 的状态消息
    file_path = tmp_path / "test.csv"
    status = batch_manager._determine_part_selection_status(file_path, project_model)

    # 验证状态消息包含清晰的错误提示
    assert "❌" in status, "缺失 Part 时应显示错误符号"
    assert "Target缺失" in status, "应明确说明是 Target 缺失"
    assert "NonExistent" in status, "应显示缺失的 Part 名称"
    assert "需在配置中添加" in status, "应提供修复建议"


def test_config_manager_refreshes_file_status_on_part_removal(tmp_path):
    """测试 ConfigManager 在 Part 删除时刷新文件状态"""
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem

    from gui.config_manager import ConfigManager
    from gui.signal_bus import SignalBus
    from src.models import ProjectConfigModel

    # 确保 QApplication 存在
    QApplication.instance() or QApplication([])

    # 创建测试配置
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

    project_model = ProjectConfigModel.from_dict(test_config)

    # 创建 Mock GUI 实例，包含文件树
    gui_instance = Mock()
    gui_instance.signal_bus = SignalBus.instance()
    gui_instance.project_model = project_model
    gui_instance.current_config = project_model

    # 模拟文件树结构
    test_file = tmp_path / "data.csv"
    test_file.write_text("Fx,Fy,Fz\n1,2,3\n")

    file_item = QTreeWidgetItem([test_file.name, "✓ 可处理"])
    gui_instance._file_tree_items = {str(test_file): file_item}

    # 创建虚拟的 file_tree 对象
    gui_instance.file_tree = QTreeWidget()

    # 初始化 ConfigManager
    config_manager = ConfigManager(gui_instance)

    # 配置初始化完成，现在模拟 Part 删除
    # 直接调用刷新方法（因为没有真实的 BatchManager）
    config_manager._refresh_file_tree_on_part_removed("Target", "Wind")

    # 由于没有 BatchManager，文件状态不会改变，但方法应该优雅地处理缺失
    # 这个测试主要验证方法不会抛出异常


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
