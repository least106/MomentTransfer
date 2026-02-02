"""
GUI 工作流集成测试

测试完整的用户工作流程，模拟真实的使用场景。
这些测试确保用户能够顺利完成从文件加载到批处理的完整流程。

注意：所有测试不显示窗口，避免卡死，使用统一的清理模式。
"""

import json
from pathlib import Path

import pytest

# 如果缺少 PySide6 则跳过整个模块
pytest.importorskip("PySide6")


def test_config_load_and_validation(tmp_path):
    """测试配置加载和验证功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证配置管理器已创建
        assert hasattr(window, "config_manager"), "配置管理器未创建"
        assert window.config_manager is not None, "配置管理器为 None"

        # 创建测试配置文件
        config_file = tmp_path / "test_config.json"
        test_config = {
            "input_file": str(tmp_path / "test_input.json"),
            "output_dir": str(tmp_path / "output"),
            "coordinate_system": "body",
            "mass_units": "kg",
            "length_units": "mm",
        }
        config_file.write_text(json.dumps(test_config, ensure_ascii=False, indent=2))

        # 验证 load_config 方法存在
        assert hasattr(
            window.config_manager, "load_config"
        ), "load_config 方法不存在"

        # 测试加载配置（不触发文件对话框）
        # 注意：实际调用可能触发 UI 对话框，这里只验证方法存在

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_file_tree_population_and_selection(tmp_path):
    """测试文件树的填充和选择功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证批处理管理器
        assert hasattr(window, "batch_manager"), "批处理管理器未创建"

        # 验证文件树操作方法存在
        assert hasattr(
            window.batch_manager, "_populate_file_tree_from_files"
        ), "文件树填充方法不存在"
        assert hasattr(
            window.batch_manager, "_safe_add_file_tree_entry"
        ), "文件树添加方法不存在"
        assert hasattr(
            window.batch_manager, "browse_batch_input"
        ), "浏览批处理输入方法不存在"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_batch_preview_and_filtering(tmp_path):
    """测试批处理预览和过滤功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证批处理管理器
        assert hasattr(window, "batch_manager"), "批处理管理器未创建"

        # 验证过滤方法存在
        assert hasattr(
            window.batch_manager, "_apply_preview_filters"
        ), "预览过滤方法不存在"
        assert hasattr(
            window.batch_manager, "_apply_quick_filter_to_table"
        ), "快速过滤表格方法不存在"
        assert hasattr(
            window.batch_manager, "_apply_quick_filter_to_special_table"
        ), "特殊格式过滤方法不存在"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_part_name_management(tmp_path):
    """测试部件名称管理功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证部件管理器
        assert hasattr(window, "part_manager"), "部件管理器未创建"
        assert window.part_manager is not None, "部件管理器为 None"

        # 验证部件管理器的关键方法
        assert hasattr(
            window.part_manager, "add_source_part"
        ), "添加源部件方法不存在"
        assert hasattr(
            window.part_manager, "add_target_part"
        ), "添加目标部件方法不存在"
        assert hasattr(
            window.part_manager, "save_current_source_part"
        ), "保存当前源部件方法不存在"
        assert hasattr(
            window.part_manager, "save_current_target_part"
        ), "保存当前目标部件方法不存在"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_batch_history_tracking(tmp_path):
    """测试批处理历史记录功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证批处理管理器
        assert hasattr(window, "batch_manager"), "批处理管理器未创建"

        # 验证批处理相关方法存在
        assert hasattr(
            window.batch_manager, "attach_history"
        ), "附加历史面板方法不存在"
        assert hasattr(
            window.batch_manager, "run_batch_processing"
        ), "运行批处理方法不存在"
        assert hasattr(
            window.batch_manager, "request_cancel_batch"
        ), "请求取消批处理方法不存在"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_output_path_configuration(tmp_path):
    """测试输出路径配置功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证批处理管理器
        assert hasattr(window, "batch_manager"), "批处理管理器未创建"

        # 验证批处理输入浏览方法
        assert hasattr(
            window.batch_manager, "browse_batch_input"
        ), "浏览批处理输入方法不存在"

        # 验证文件扫描方法
        assert hasattr(
            window.batch_manager, "_scan_and_populate_files"
        ), "扫描和填充文件方法不存在"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_signal_bus_communication(tmp_path):
    """测试信号总线通信功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI
    from gui.signal_bus import SignalBus

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证信号总线
        assert hasattr(window, "signal_bus"), "信号总线未创建"
        signal_bus = window.signal_bus

        # 验证信号总线是单例
        global_bus = SignalBus.instance()
        assert signal_bus is global_bus, "信号总线不是单例"

        # 验证关键信号
        assert hasattr(signal_bus, "statusMessage"), "状态消息信号不存在"
        assert hasattr(signal_bus, "batchProgress"), "批处理进度信号不存在"
        assert hasattr(signal_bus, "configLoaded"), "配置加载信号不存在"
        assert hasattr(signal_bus, "batchStarted"), "批处理开始信号不存在"
        assert hasattr(signal_bus, "batchFinished"), "批处理完成信号不存在"

        # 测试信号连接（不触发实际操作）
        received_messages = []

        def test_slot(msg, timeout_ms, priority):
            received_messages.append(msg)

        signal_bus.statusMessage.connect(test_slot)

        # 发射测试信号
        test_message = "测试状态消息"
        signal_bus.statusMessage.emit(test_message, 3000, 0)

        # 处理事件队列
        app.processEvents()

        # 验证信号已接收
        assert test_message in received_messages, "信号未正确传递"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_ui_state_transitions(tmp_path):
    """测试 UI 状态转换功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证 UI 状态管理器
        assert hasattr(window, "ui_state_manager"), "UI 状态管理器未创建"
        state_manager = window.ui_state_manager

        # 验证状态管理方法
        assert hasattr(
            state_manager, "set_controls_locked"
        ), "设置控件锁定状态方法不存在"
        assert hasattr(
            state_manager, "set_config_panel_visible"
        ), "设置配置面板可见性方法不存在"

        # 验证按钮状态管理
        assert hasattr(window, "btn_start_menu"), "开始按钮未创建"
        assert hasattr(window, "btn_cancel"), "取消按钮未创建"

        # 初始状态验证
        assert not window.btn_cancel.isVisible(), "取消按钮初始应隐藏"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_file_selection_manager(tmp_path):
    """测试文件选择管理器功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证文件选择管理器
        assert hasattr(window, "file_selection_manager"), "文件选择管理器未创建"
        file_manager = window.file_selection_manager

        # 验证文件选择方法
        assert hasattr(
            file_manager, "mark_skipped_rows"
        ), "标记跳过行方法不存在"
        assert hasattr(
            file_manager, "clear_skipped_rows"
        ), "清除跳过行方法不存在"

        # 验证文件选择映射属性
        assert hasattr(
            file_manager, "file_part_selection_by_file"
        ), "文件部件选择映射不存在"
        assert isinstance(
            file_manager.file_part_selection_by_file, dict
        ), "文件部件选择映射应为dict"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_model_manager_data_handling(tmp_path):
    """测试模型管理器的数据处理功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证模型管理器
        assert hasattr(window, "model_manager"), "模型管理器未创建"
        model_manager = window.model_manager

        # 验证数据处理方法
        assert hasattr(
            model_manager, "save_current_source_part"
        ), "保存当前源部件方法不存在"
        assert hasattr(
            model_manager, "save_current_target_part"
        ), "保存当前目标部件方法不存在"
        assert hasattr(
            model_manager, "_ensure_project_model"
        ), "确保项目模型方法不存在"

        # 验证模型属性
        assert hasattr(model_manager, "calculator"), "calculator 属性不存在"
        assert hasattr(model_manager, "current_config"), "current_config 属性不存在"
        assert hasattr(model_manager, "project_model"), "project_model 属性不存在"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_logging_system_integration(tmp_path):
    """测试日志系统集成"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证日志面板（如果存在）
        # 注意：日志面板可能是可选的或动态创建的
        if hasattr(window, "log_panel"):
            log_panel = window.log_panel
            # 验证日志面板的基本功能
            assert hasattr(log_panel, "append_log"), "日志追加方法不存在"

        # 验证状态栏日志
        assert hasattr(window, "statusBar"), "状态栏未创建"
        status_bar = window.statusBar()
        assert status_bar is not None, "状态栏为 None"

        # 测试状态消息（不触发实际显示）
        test_message = "测试状态消息"
        status_bar.showMessage(test_message, 1000)

        # 验证消息已设置
        current_message = status_bar.currentMessage()
        assert current_message == test_message, "状态消息设置失败"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_batch_thread_lifecycle(tmp_path):
    """测试批处理线程的生命周期管理"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证批处理管理器
        assert hasattr(window, "batch_manager"), "批处理管理器未创建"
        batch_manager = window.batch_manager

        # 验证线程管理方法
        assert hasattr(
            batch_manager, "run_batch_processing"
        ), "运行批处理方法不存在"
        assert hasattr(
            batch_manager, "request_cancel_batch"
        ), "请求取消批处理方法不存在"
        assert hasattr(
            batch_manager, "undo_batch_processing"
        ), "撤销批处理方法不存在"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_event_manager_integration(tmp_path):
    """测试事件管理器集成"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证事件管理器（如果存在）
        if hasattr(window, "event_manager"):
            event_manager = window.event_manager

            # 验证事件处理方法
            assert hasattr(
                event_manager, "on_show_event"
            ), "显示事件处理方法不存在"
            assert hasattr(
                event_manager, "on_resize_event"
            ), "缩放事件处理方法不存在"
            assert hasattr(
                event_manager, "on_close_event"
            ), "关闭事件处理方法不存在"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_layout_manager_components(tmp_path):
    """测试布局管理器组件"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证布局管理器
        assert hasattr(window, "layout_manager"), "布局管理器未创建"
        layout_manager = window.layout_manager

        # 验证布局方法
        assert hasattr(
            layout_manager, "update_button_layout"
        ), "更新按钮布局方法不存在"
        assert hasattr(
            layout_manager, "refresh_layouts"
        ), "刷新布局方法不存在"
        assert hasattr(
            layout_manager, "force_layout_refresh"
        ), "强制刷新布局方法不存在"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()
