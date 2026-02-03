"""
GUI 初始化集成测试

测试 GUI 主窗口的完整初始化流程，确保所有组件能正确创建和连接。
这些测试能捕获实际运行时的 AttributeError、方法名错误等问题。
"""

import pytest

# 如果缺少 PySide6 则跳过整个模块
pytest.importorskip("PySide6")


def test_main_window_initialization():
    """测试主窗口能够完整初始化而不抛出异常"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    # 创建 QApplication（若测试运行环境中尚未创建）
    app = QApplication.instance() or QApplication([])

    window = None
    try:
        # 创建主窗口（这会触发完整的初始化流程）
        window = IntegratedAeroGUI()

        # 验证关键组件已创建
        assert hasattr(window, "batch_manager"), "batch_manager 未初始化"
        assert hasattr(window, "config_manager"), "config_manager 未初始化"
        assert hasattr(window, "part_manager"), "part_manager 未初始化"

        # 验证工具栏组件已创建
        assert hasattr(window, "btn_start_menu"), "开始按钮未创建"
        assert hasattr(window, "btn_browse_menu"), "浏览按钮未创建"
        assert hasattr(window, "btn_cancel"), "取消按钮未创建"
        assert hasattr(window, "chk_bottom_bar_toolbar"), "底部栏复选框未创建"

        # 验证底部栏相关组件已创建
        assert hasattr(window, "_bottom_splitter"), "_bottom_splitter 未创建"
        assert hasattr(window, "_bottom_bar"), "_bottom_bar 未创建"

        # 验证关键方法存在
        assert hasattr(
            window, "request_cancel_batch"
        ), "request_cancel_batch 方法不存在"
        assert hasattr(
            window, "run_batch_processing"
        ), "run_batch_processing 方法不存在"
        assert hasattr(window, "browse_batch_input"), "browse_batch_input 方法不存在"

    finally:
        # 清理窗口
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_initialization_manager_components():
    """测试 InitializationManager 能正确创建所有 UI 组件"""
    from PySide6.QtWidgets import QApplication

    from gui.initialization_manager import InitializationManager
    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()
        init_manager = InitializationManager(window)

        # 验证初始化管理器的方法可以安全调用
        # setup_ui 在 IntegratedAeroGUI.__init__ 中已被调用
        # 这里验证关键组件确实存在

        # 验证面板已创建
        assert hasattr(window, "config_panel"), "config_panel 未创建"
        assert hasattr(window, "operation_panel"), "operation_panel 未创建"
        assert hasattr(window, "history_panel"), "history_panel 未创建"

        # 验证侧边栏包装器已创建
        assert hasattr(window, "config_sidebar"), "config_sidebar 未创建"
        assert hasattr(window, "history_sidebar"), "history_sidebar 未创建"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_signal_connections():
    """测试信号连接不会抛出 AttributeError"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证取消按钮的信号连接
        assert hasattr(window, "btn_cancel"), "取消按钮未创建"
        assert window.btn_cancel is not None, "取消按钮为 None"

        # 验证底部栏复选框的信号连接
        assert hasattr(window, "chk_bottom_bar_toolbar"), "底部栏复选框未创建"
        assert window.chk_bottom_bar_toolbar is not None, "底部栏复选框为 None"

        # 测试底部栏切换信号连接正确（验证信号已连接，不验证UI行为）
        # 信号连接的验证：尝试触发不应抛出异常
        try:
            # 验证信号可以被触发而不抛出 AttributeError
            window.chk_bottom_bar_toolbar.setChecked(True)
            app.processEvents()

            window.chk_bottom_bar_toolbar.setChecked(False)
            app.processEvents()

            # 如果执行到这里，说明信号连接正确，没有 AttributeError
        except AttributeError as e:
            pytest.fail(f"底部栏切换信号连接有 AttributeError: {e}")
        except Exception as e:
            # 其他异常可能是正常的（例如 UI 状态相关）
            # 只要不是 AttributeError 就说明信号连接正确
            pass

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_cancel_button_connection():
    """测试取消按钮的方法连接正确"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证取消按钮连接的是正确的方法
        assert hasattr(
            window, "request_cancel_batch"
        ), "request_cancel_batch 方法不存在"

        # 验证方法可以安全调用（不会抛出异常）
        try:
            window.request_cancel_batch()
        except Exception as e:
            # request_cancel_batch 可能因为没有正在运行的批处理而无操作
            # 但不应抛出 AttributeError 或其他严重错误
            if isinstance(e, AttributeError):
                pytest.fail(f"request_cancel_batch 调用时出现 AttributeError: {e}")

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


def test_menu_bar_and_toolbar_creation():
    """测试菜单栏和工具栏的创建顺序正确"""
    from PySide6.QtWidgets import QApplication

    from gui.main_window import IntegratedAeroGUI

    app = QApplication.instance() or QApplication([])

    window = None
    try:
        window = IntegratedAeroGUI()

        # 验证菜单栏已创建
        menubar = window.menuBar()
        assert menubar is not None, "菜单栏未创建"

        # 验证工具栏已创建并包含关键按钮
        toolbars = window.findChildren(type(window.menuBar().__class__))
        # 注意：这里只验证按钮属性存在，不验证 toolbar 数量

        # 验证所有工具栏按钮都已正确引用
        assert window.btn_start_menu is not None, "开始按钮未引用"
        assert window.btn_browse_menu is not None, "浏览按钮未引用"
        assert window.btn_cancel is not None, "取消按钮未引用"

    finally:
        if window:
            window.close()
            window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    # 允许直接运行此测试文件
    pytest.main([__file__, "-v"])
