"""
初始化管理器 - 负责主窗口的 UI 初始化与管理器设置
"""

# 延迟导入在初始化流程中较为常见，允许 import-outside-toplevel
# 同时临时允许行过长以减少噪音（后续将拆分长行）
# pylint: disable=import-outside-toplevel, line-too-long

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout

from gui.batch_history import BatchHistoryPanel, BatchHistoryStore
from gui.batch_manager import BatchManager
from gui.config_manager import ConfigManager
from gui.layout_manager import LayoutManager
from gui.log_manager import LoggingManager
from gui.part_manager import PartManager
# 侧边栏改为合并到底部栏，移除浮动 SlideSidebar 的使用

logger = logging.getLogger(__name__)

# 主题常量
LAYOUT_MARGIN = 12
LAYOUT_SPACING = 8


class InitializationManager:
    """管理主窗口的初始化流程"""

    def __init__(self, main_window):
        self.main_window = main_window
        self._is_initializing = True

    def setup_ui(self):
        """初始化 UI 组件"""
        try:
            # 创建菜单栏
            self._setup_menu_bar()
            
            central_widget = QWidget()
            self.main_window.setCentralWidget(central_widget)
            main_layout = QVBoxLayout(central_widget)
            main_layout.setContentsMargins(
                LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN
            )
            main_layout.setSpacing(LAYOUT_SPACING)

            # 创建配置/操作面板
            config_panel = self.main_window.create_config_panel()
            operation_panel = self.main_window.create_operation_panel()
            self.main_window.operation_panel = operation_panel
            self.main_window.config_panel = config_panel

            # 创建历史存储与面板
            history_store = BatchHistoryStore()
            history_panel = BatchHistoryPanel(history_store)
            self.main_window.history_store = history_store
            self.main_window.history_panel = history_panel

            # 主内容区域占满整个空间（不被侧边栏挤压）
            main_layout.addWidget(operation_panel)

            # 将原来的左右浮动侧边栏合并到一个底部栏（避免浮动按钮与动画）
            bottom_bar = QWidget()
            bottom_layout = QHBoxLayout(bottom_bar)
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(LAYOUT_SPACING)

            # 左右并排放置原先的配置与历史面板
            bottom_layout.addWidget(config_panel, 1)
            bottom_layout.addWidget(history_panel, 0)

            # 初始折叠（隐藏底部栏）
            bottom_bar.setVisible(False)

            # 简单包装以兼容旧的侧边栏 API（提供 toggle_panel/is_expanded）
            class BottomDock:
                def __init__(self, widget, bar: QWidget):
                    self._widget = widget
                    self._bar = bar

                def toggle_panel(self) -> None:
                    if self.is_expanded():
                        self.hide_panel()
                    else:
                        self.show_panel()

                def show_panel(self) -> None:
                    try:
                        self._widget.setVisible(True)
                        self._bar.setVisible(True)
                    except Exception:
                        pass

                def hide_panel(self) -> None:
                    try:
                        self._widget.setVisible(False)
                        # 如果所有子控件都不可见，则隐藏底部栏
                        any_visible = False
                        for i in range(self._bar.layout().count()):
                            w = self._bar.layout().itemAt(i).widget()
                            if w is not None and w.isVisible():
                                any_visible = True
                                break
                        if not any_visible:
                            self._bar.setVisible(False)
                    except Exception:
                        pass

                def is_expanded(self) -> bool:
                    try:
                        return self._widget.isVisible() and self._bar.isVisible()
                    except Exception:
                        return False

            # 兼容旧属性：指向包装对象
            config_sidebar = BottomDock(config_panel, bottom_bar)
            history_sidebar = BottomDock(history_panel, bottom_bar)

            self.main_window.config_sidebar = config_sidebar
            self.main_window.history_sidebar = history_sidebar
            self.main_window.operation_panel = operation_panel
            self.main_window.central_widget = central_widget

            # 将底部栏加入主布局（位于 operation_panel 之下）
            main_layout.addWidget(bottom_bar)

            # 连接 BatchPanel 的复选框信号以控制底部栏显示/隐藏
            try:
                operation_panel.batch_panel.bottomBarToggled.connect(
                    lambda visible: bottom_bar.setVisible(bool(visible))
                )
            except Exception:
                logger.debug("连接底部栏切换信号失败", exc_info=True)

            # 将状态信息显示为状态栏右侧的永久标签，避免默认消息框在左侧分散注意力
            try:
                from PySide6.QtWidgets import QLabel, QSizePolicy

                lbl = QLabel("步骤1：选择文件或目录")
                lbl.setObjectName("statusMessage")
                lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                # 添加为永久部件，位于状态栏右侧
                self.main_window.statusBar().addPermanentWidget(lbl, 1)
            except Exception:
                # 回退到默认行为
                try:
                    self.main_window.statusBar().showMessage("步骤1：选择文件或目录")
                except Exception:
                    pass

            logger.info("UI 组件初始化成功")
        except Exception as e:
            logger.error("UI 初始化失败: %s", e, exc_info=True)
            raise

    def setup_managers(self):
        """初始化所有管理器"""
        try:
            # 必须在创建面板之后初始化管理器
            config_panel = getattr(self.main_window, "config_panel", None)
            if not config_panel:
                raise RuntimeError("config_panel 未初始化")

            self.main_window.config_manager = ConfigManager(
                self.main_window, config_panel
            )
            self.main_window.part_manager = PartManager(self.main_window)
            self.main_window.batch_manager = BatchManager(self.main_window)
            self.main_window.layout_manager = LayoutManager(self.main_window)
            
            # 初始化 ProjectManager
            from gui.project_manager import ProjectManager
            self.main_window.project_manager = ProjectManager(self.main_window)
            
            # 将 ConfigPanel 替换到 Tab 的"参考系管理"位置
            try:
                if hasattr(self.main_window, "tab_main") and hasattr(self.main_window, "config_tab_placeholder"):
                    tab_main = self.main_window.tab_main
                    config_panel = self.main_window.config_panel
                    # 替换第0个Tab的内容
                    tab_main.removeTab(0)
                    tab_main.insertTab(0, config_panel, "参考系管理")
            except Exception:
                logger.debug("替换参考系管理Tab失败", exc_info=True)

            try:
                if hasattr(self.main_window, "history_store"):
                    self.main_window.batch_manager.attach_history(
                        self.main_window.history_store,
                        getattr(self.main_window, "history_panel", None),
                    )
            except Exception:
                logger.debug("绑定批处理历史失败", exc_info=True)

            logger.info("所有管理器初始化成功")
            # 绑定：当用户在输入框直接输入路径并完成编辑时，触发扫描和控件启用状态更新
            try:
                bp = getattr(self.main_window, "inp_batch_input", None)
                if bp is not None:

                    def _on_input_edit_finished():
                        try:
                            text = bp.text().strip()
                            if not text:
                                return
                            from pathlib import Path

                            p = Path(text)
                            if p.exists():
                                # 委托给 BatchManager 统一处理扫描与 UI 状态
                                try:
                                    self.main_window.batch_manager._scan_and_populate_files(
                                        p
                                    )
                                except Exception:
                                    logger.debug("扫描文件失败", exc_info=True)
                        except Exception:
                            pass

                    try:
                        bp.editingFinished.connect(_on_input_edit_finished)
                    except Exception:
                        # 有些 Qt 版本或组件可能不支持该信号，忽略绑定失败
                        pass
            except Exception:
                logger.debug("绑定 inp_batch_input 编辑完成信号失败", exc_info=True)
        except Exception as e:
            logger.error("管理器初始化失败: %s", e, exc_info=True)
            # 继续运行，即使管理器初始化失败

    def setup_logging(self):
        """设置日志系统"""
        try:
            logging_manager = LoggingManager(self.main_window)
            logging_manager.setup_gui_logging()
        except Exception as e:
            logger.debug("GUI logging setup failed (non-fatal): %s", e, exc_info=True)

    def bind_post_ui_signals(self):
        """绑定主窗口的后置 UI 信号与默认可视状态。"""
        try:
            bp = getattr(self.main_window, "batch_panel", None)
            if bp is not None:
                bp.switch_to_log_tab()
        except Exception:
            logger.debug("启动时切换默认页面到日志页失败", exc_info=True)

        try:
            pm = getattr(self.main_window, "part_manager", None)
            sp = getattr(self.main_window, "source_panel", None)
            tp = getattr(self.main_window, "target_panel", None)

            if sp is not None and pm is not None:
                sp.partSelected.connect(pm.on_source_part_changed)
            if tp is not None and pm is not None:
                tp.partSelected.connect(pm.on_target_part_changed)
        except Exception:
            logger.debug("连接 Part 选择器信号失败", exc_info=True)

        try:
            pm = getattr(self.main_window, "part_manager", None)
            if pm is not None:
                pm.on_source_part_changed()
        except Exception:
            logger.debug("初始 Part 状态更新失败", exc_info=True)

    def finalize_initialization(self):
        """完成初始化 - 在 showEvent 后调用"""

        def _finalize():
            self._is_initializing = False
            self.main_window._is_initializing = False
            logger.debug("初始化完成")

        # 延迟完成标志，避免 showEvent 期间的弹窗
        QTimer.singleShot(150, _finalize)


    def _setup_menu_bar(self):
        """创建菜单栏"""
        try:
            from PySide6.QtWidgets import QMenuBar
            
            menubar = self.main_window.menuBar()
            
            # 文件菜单
            file_menu = menubar.addMenu("文件(&F)")
            
            new_project_action = file_menu.addAction("新建 Project(&N)")
            new_project_action.setShortcut("Ctrl+N")
            new_project_action.triggered.connect(self.main_window._new_project)
            
            open_project_action = file_menu.addAction("打开 Project(&O)")
            open_project_action.setShortcut("Ctrl+O")
            open_project_action.triggered.connect(self.main_window._open_project)
            
            save_project_action = file_menu.addAction("保存 Project(&S)")
            save_project_action.setShortcut("Ctrl+Shift+S")
            save_project_action.triggered.connect(self.main_window._on_save_project)
            
            file_menu.addSeparator()
            
            exit_action = file_menu.addAction("退出(&Q)")
            exit_action.setShortcut("Alt+F4")
            exit_action.triggered.connect(self.main_window.close)
            
            # 工具菜单 - 添加操作按钮
            tools_menu = menubar.addMenu("工具(&T)")
            
            browse_action = tools_menu.addAction("浏览文件(&B)")
            browse_action.setToolTip("选择输入文件或目录")
            browse_action.triggered.connect(self.main_window.browse_batch_input)
            
            load_config_action = tools_menu.addAction("加载配置(&L)")
            load_config_action.setToolTip("加载配置文件（JSON），用于提供 Source/Target part 定义")
            load_config_action.triggered.connect(self.main_window.configure_data_format)
            
            tools_menu.addSeparator()
            
            start_action = tools_menu.addAction("开始处理(&S)")
            start_action.setShortcut("Ctrl+R")
            start_action.setToolTip("开始批量处理")
            start_action.triggered.connect(self.main_window.run_batch_processing)
            
            logger.info("菜单栏已创建")
        except Exception as e:
            logger.error("创建菜单栏失败: %s", e)

    def trigger_initial_layout_update(self):
        """触发初始布局更新"""
        try:
            # 合并为一次定时调用，减少启动时的多次视觉刷新
            def _do_initial_updates():
                try:
                    if (
                        hasattr(self.main_window, "layout_manager")
                        and self.main_window.layout_manager
                    ):
                        self.main_window.layout_manager.update_button_layout()
                except Exception:
                    pass
                try:
                    if (
                        hasattr(self.main_window, "layout_manager")
                        and self.main_window.layout_manager
                    ):
                        self.main_window.layout_manager.force_layout_refresh()
                except Exception:
                    pass

            QTimer.singleShot(120, _do_initial_updates)
        except Exception:
            logger.debug("Initial layout update scheduling failed", exc_info=True)
