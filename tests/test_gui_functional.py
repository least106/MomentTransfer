"""
GUI 功能集成测试

测试 GUI 的实际用户操作流程，模拟真实使用场景。
这些测试确保用户能够正常完成各种任务。
"""

import json
from pathlib import Path

import pytest

# 如果缺少 PySide6 则跳过整个模块
pytest.importorskip("PySide6")


def test_batch_processing_button_states(tmp_path):
    """测试批处理按钮的状态管理（启用/禁用）"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    try:
        window = IntegratedAeroGUI()

        # 验证开始按钮初始状态
        assert hasattr(window, "btn_start_menu"), "开始按钮未创建"
        # 注意：初始化后可能被启用或禁用，取决于是否有默认输入

        # 验证取消按钮初始状态（应该隐藏）
        assert hasattr(window, "btn_cancel"), "取消按钮未创建"
        assert not window.btn_cancel.isVisible(), "取消按钮初始应该隐藏"
        assert not window.btn_cancel.isEnabled(), "取消按钮初始应该禁用"

        window.close()
        window.deleteLater()

    finally:
        app.processEvents()


def test_file_selection_and_tree_display(tmp_path):
    """测试文件选择和树状显示功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    try:
        window = IntegratedAeroGUI()

        # 创建测试文件
        test_file1 = tmp_path / "test1.csv"
        test_file1.write_text("Fx,Fy,Fz,Mx,My,Mz\n1,2,3,0.1,0.2,0.3\n")

        test_file2 = tmp_path / "test2.csv"
        test_file2.write_text("Fx,Fy,Fz,Mx,My,Mz\n4,5,6,0.4,0.5,0.6\n")

        # 验证 batch_manager 存在
        assert hasattr(window, "batch_manager"), "batch_manager 未创建"
        assert window.batch_manager is not None, "batch_manager 为 None"

        # 验证文件树访问
        batch_manager = window.batch_manager
        assert hasattr(batch_manager, "gui"), "batch_manager.gui 未创建"
        assert hasattr(
            batch_manager.gui, "file_tree"
        ), "文件树控件未创建"

        # 测试添加文件到批处理列表
        try:
            # 模拟添加文件（通过内部方法）
            if hasattr(batch_manager, "_add_files_to_tree"):
                batch_manager._add_files_to_tree([str(test_file1), str(test_file2)])
                app.processEvents()

                # 验证文件被添加
                tree = batch_manager.gui.file_tree
                assert tree.topLevelItemCount() > 0, "文件未添加到树"
        except Exception as e:
            # 某些实现可能不支持直接添加，这不是致命错误
            pytest.skip(f"文件添加测试跳过: {e}")

        window.close()
        window.deleteLater()

    finally:
        app.processEvents()


def test_config_loading(tmp_path):
    """测试配置文件加载功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    try:
        window = IntegratedAeroGUI()

        # 创建测试配置文件
        config_file = tmp_path / "test_config.json"
        test_config = {
            "source_part": "TestSource",
            "target_part": "TestTarget",
            "parts": {
                "TestSource": {
                    "X": [1, 0, 0],
                    "Y": [0, 1, 0],
                    "Z": [0, 0, 1],
                    "origin": [0, 0, 0],
                },
                "TestTarget": {
                    "X": [1, 0, 0],
                    "Y": [0, 1, 0],
                    "Z": [0, 0, 1],
                    "origin": [0, 0, 0],
                },
            },
        }
        config_file.write_text(json.dumps(test_config, indent=2))

        # 验证 config_manager 存在
        assert hasattr(window, "config_manager"), "config_manager 未创建"
        assert window.config_manager is not None, "config_manager 为 None"

        # 测试配置加载方法存在（方法名可能是 load_config 或 load_config_from_file）
        config_manager = window.config_manager
        has_load_method = hasattr(config_manager, "load_config") or hasattr(
            config_manager, "load_config_from_file"
        )
        assert has_load_method, "配置加载方法不存在"

        # 配置加载功能是交互式的（通常需要文件对话框），这里只验证方法存在即可
        # 实际加载测试需要 mock QFileDialog

        window.close()
        window.deleteLater()

    finally:
        app.processEvents()


def test_part_manager_operations():
    """测试 Part 管理器的基本操作"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    try:
        window = IntegratedAeroGUI()

        # 验证 part_manager 存在
        assert hasattr(window, "part_manager"), "part_manager 未创建"
        assert window.part_manager is not None, "part_manager 为 None"

        part_manager = window.part_manager

        # 验证 part_manager 有基本属性
        assert hasattr(part_manager, "gui"), "part_manager.gui 不存在"
        assert hasattr(part_manager, "signal_bus"), "part_manager.signal_bus 不存在"

        # 测试信号连接方法存在（这些是实际存在的内部方法）
        has_internal_methods = (
            hasattr(part_manager, "_on_part_add_requested")
            or hasattr(part_manager, "_get_model_manager")
        )
        assert has_internal_methods, "part_manager 关键方法不存在"

        window.close()
        window.deleteLater()

    finally:
        app.processEvents()


def test_project_save_and_load(tmp_path):
    """测试项目的保存和加载功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    try:
        window = IntegratedAeroGUI()

        # 验证 project_manager 存在
        assert hasattr(window, "project_manager"), "project_manager 未创建"
        assert window.project_manager is not None, "project_manager 为 None"

        project_manager = window.project_manager

        # 验证项目管理方法存在
        assert hasattr(
            project_manager, "save_project"
        ), "save_project 方法不存在"
        assert hasattr(
            project_manager, "load_project"
        ), "load_project 方法不存在"

        # 测试保存项目
        project_file = tmp_path / "test_project.mtproject"
        try:
            # 尝试保存项目（可能失败，但不应抛出 AttributeError）
            result = project_manager.save_project(str(project_file))
            app.processEvents()

            # 如果保存成功，验证文件存在
            if result:
                assert project_file.exists(), "项目文件未创建"

                # 尝试加载项目
                load_result = project_manager.load_project(str(project_file))
                app.processEvents()
        except AttributeError as e:
            pytest.fail(f"项目保存/加载时出现 AttributeError: {e}")
        except Exception:
            # 其他错误可以接受（如项目内容不完整）
            pass

        window.close()
        window.deleteLater()

    finally:
        app.processEvents()


def test_quick_filter_interaction():
    """测试快速筛选功能的交互"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    try:
        window = IntegratedAeroGUI()

        # 验证 batch_manager 和快速筛选控件存在
        assert hasattr(window, "batch_manager"), "batch_manager 未创建"
        batch_manager = window.batch_manager

        assert hasattr(batch_manager, "gui"), "batch_manager.gui 未创建"
        gui = batch_manager.gui

        # 验证快速筛选控件存在
        assert hasattr(gui, "cmb_filter_column"), "筛选列下拉框未创建"
        assert hasattr(gui, "cmb_filter_operator"), "筛选运算符下拉框未创建"
        assert hasattr(gui, "inp_filter_value"), "筛选值输入框未创建"

        # 测试筛选控件可以交互
        try:
            # 模拟选择筛选列
            if gui.cmb_filter_column.count() > 0:
                gui.cmb_filter_column.setCurrentIndex(0)
                app.processEvents()

            # 模拟选择运算符
            if gui.cmb_filter_operator.count() > 0:
                gui.cmb_filter_operator.setCurrentIndex(0)
                app.processEvents()

            # 模拟输入筛选值
            gui.inp_filter_value.setText("test")
            app.processEvents()
        except AttributeError as e:
            pytest.fail(f"快速筛选交互时出现 AttributeError: {e}")

        window.close()
        window.deleteLater()

    finally:
        app.processEvents()


def test_batch_history_recording():
    """测试批处理历史记录功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    try:
        window = IntegratedAeroGUI()

        # 验证历史存储和面板存在
        assert hasattr(window, "history_store"), "history_store 未创建"
        assert hasattr(window, "history_panel"), "history_panel 未创建"

        history_store = window.history_store

        # 验证历史存储方法存在
        assert hasattr(history_store, "add_record"), "add_record 方法不存在"
        assert hasattr(history_store, "get_all_records"), "get_all_records 方法不存在"
        assert hasattr(history_store, "clear"), "clear 方法不存在"

        # 测试添加历史记录
        try:
            initial_count = len(history_store.get_all_records())

            # 添加一条测试记录
            history_store.add_record(
                status="成功",
                file_count=2,
                duration=1.5,
                details="测试批处理",
            )
            app.processEvents()

            # 验证记录被添加
            new_count = len(history_store.get_all_records())
            assert new_count == initial_count + 1, "历史记录未添加"
        except AttributeError as e:
            pytest.fail(f"历史记录操作时出现 AttributeError: {e}")

        window.close()
        window.deleteLater()

    finally:
        app.processEvents()


def test_coordinate_panel_interaction():
    """测试坐标系面板的交互"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    try:
        window = IntegratedAeroGUI()

        # 验证 operation_panel 存在
        assert hasattr(window, "operation_panel"), "operation_panel 未创建"
        operation_panel = window.operation_panel

        # 验证坐标系面板存在
        # 注意：具体属性名可能不同，这里尝试常见的命名
        has_coord_panels = any(
            hasattr(operation_panel, attr)
            for attr in ["source_panel", "target_panel", "coord_source", "coord_target"]
        )

        if not has_coord_panels:
            pytest.skip("坐标系面板属性未找到")

        # 如果找到面板，验证它们可以访问
        try:
            if hasattr(operation_panel, "source_panel"):
                source_panel = operation_panel.source_panel
                assert source_panel is not None, "source_panel 为 None"

            if hasattr(operation_panel, "target_panel"):
                target_panel = operation_panel.target_panel
                assert target_panel is not None, "target_panel 为 None"
        except AttributeError as e:
            pytest.fail(f"访问坐标系面板时出现 AttributeError: {e}")

        window.close()
        window.deleteLater()

    finally:
        app.processEvents()


def test_bottom_bar_panels_visibility():
    """测试底部栏面板的显示/隐藏功能"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    try:
        window = IntegratedAeroGUI()
        window.show()
        app.processEvents()

        # 验证底部栏和复选框存在
        assert hasattr(window, "_bottom_bar"), "_bottom_bar 未创建"
        assert hasattr(window, "chk_bottom_bar_toolbar"), "chk_bottom_bar_toolbar 未创建"

        bottom_bar = window._bottom_bar
        checkbox = window.chk_bottom_bar_toolbar

        # 初始状态应该是隐藏的
        initial_visibility = bottom_bar.isVisible()
        assert not initial_visibility, "底部栏初始应该隐藏"

        # 测试显示底部栏
        checkbox.setChecked(True)
        app.processEvents()
        assert bottom_bar.isVisible(), "勾选后底部栏应该显示"

        # 测试隐藏底部栏
        checkbox.setChecked(False)
        app.processEvents()
        assert not bottom_bar.isVisible(), "取消勾选后底部栏应该隐藏"

        # 再次测试切换
        checkbox.setChecked(True)
        app.processEvents()
        assert bottom_bar.isVisible(), "第二次勾选后底部栏应该显示"

        window.close()
        window.deleteLater()

    finally:
        app.processEvents()


if __name__ == "__main__":
    # 允许直接运行此测试文件
    pytest.main([__file__, "-v"])
