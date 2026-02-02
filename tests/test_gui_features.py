"""
GUI 实际功能测试 - 扩展版

测试更多实际的用户操作场景，确保 GUI 能正确响应各种操作。
所有测试使用统一的清理模式，不显示窗口，避免卡死。
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")


def test_batch_input_path_selection():
    """测试批处理输入路径的选择和显示"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])
    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证批处理管理器和 GUI 存在
        assert hasattr(window, "batch_manager")
        batch_manager = window.batch_manager
        assert hasattr(batch_manager, "gui")

        # 验证输入路径显示控件存在
        gui = batch_manager.gui
        assert hasattr(gui, "inp_batch_input"), "输入路径控件未创建"

        # 测试路径文本可以设置
        test_path = "C:/test/path"
        gui.inp_batch_input.setText(test_path)
        app.processEvents()
        
        assert gui.inp_batch_input.text() == test_path, "路径设置失败"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_file_tree_operations():
    """测试文件树的基本操作"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])
    window = None
    try:
        window = IntegratedAeroGUI()

        batch_manager = window.batch_manager
        gui = batch_manager.gui

        # 验证文件树存在
        assert hasattr(gui, "file_tree"), "文件树未创建"

        # 测试文件树可以清空
        initial_count = gui.file_tree.topLevelItemCount()
        gui.file_tree.clear()
        app.processEvents()

        assert gui.file_tree.topLevelItemCount() == 0, "文件树清空失败"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_coordinate_system_selection():
    """测试坐标系选择功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])
    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证 operation_panel 存在
        assert hasattr(window, "operation_panel"), "operation_panel 未创建"
        
        # operation_panel 应该包含坐标系选择相关的控件
        # 这验证了面板的基本结构
        operation_panel = window.operation_panel
        assert operation_panel is not None, "operation_panel 为 None"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_status_message_update():
    """测试状态栏消息更新功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])
    window = None
    try:
        window = IntegratedAeroGUI()

        # 测试状态栏消息可以设置
        test_message = "测试状态消息"
        window.statusBar().showMessage(test_message)
        app.processEvents()

        # 验证消息已设置（通过不抛出异常）
        current_message = window.statusBar().currentMessage()
        assert current_message == test_message, "状态栏消息设置失败"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_window_title_setting():
    """测试窗口标题设置"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])
    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证窗口标题可以设置
        test_title = "测试窗口标题"
        window.setWindowTitle(test_title)
        app.processEvents()

        assert window.windowTitle() == test_title, "窗口标题设置失败"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_batch_mode_selection():
    """测试批处理模式选择（文件/目录）"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])
    window = None
    try:
        window = IntegratedAeroGUI()

        batch_manager = window.batch_manager
        gui = batch_manager.gui

        # 验证批处理模式控件存在
        if hasattr(gui, "radio_file_mode"):
            assert hasattr(gui, "radio_dir_mode"), "目录模式单选按钮未创建"

            # 测试模式切换
            gui.radio_file_mode.setChecked(True)
            app.processEvents()
            assert gui.radio_file_mode.isChecked(), "文件模式设置失败"

            gui.radio_dir_mode.setChecked(True)
            app.processEvents()
            assert gui.radio_dir_mode.isChecked(), "目录模式设置失败"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_progress_bar_access():
    """测试进度条访问和更新"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])
    window = None
    try:
        window = IntegratedAeroGUI()

        batch_manager = window.batch_manager
        gui = batch_manager.gui

        # 验证进度条存在
        assert hasattr(gui, "progress_bar"), "进度条未创建"

        # 测试进度条可以设置值
        gui.progress_bar.setRange(0, 100)
        gui.progress_bar.setValue(50)
        app.processEvents()

        assert gui.progress_bar.value() == 50, "进度条设置失败"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_signal_bus_singleton():
    """测试信号总线单例模式"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI
    from gui.signal_bus import SignalBus

    app = QApplication.instance() or QApplication([])
    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证信号总线是单例
        bus1 = SignalBus.instance()
        bus2 = SignalBus.instance()
        
        assert bus1 is bus2, "SignalBus 不是单例"

        # 验证窗口使用相同的信号总线
        if hasattr(window, "signal_bus"):
            window_bus = window.signal_bus
            assert window_bus is bus1, "窗口使用了不同的 SignalBus 实例"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_all_managers_initialized():
    """测试所有管理器都已初始化"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])
    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证所有关键管理器存在
        managers = [
            "batch_manager",
            "config_manager",
            "part_manager",
            "project_manager",
        ]

        for manager_name in managers:
            assert hasattr(window, manager_name), f"{manager_name} 未初始化"
            manager = getattr(window, manager_name)
            assert manager is not None, f"{manager_name} 为 None"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    # 允许直接运行此测试文件
    pytest.main([__file__, "-v"])
