"""
初始化管理器 - 负责主窗口的 UI 初始化与管理器设置
"""

# 延迟导入在初始化流程中较为常见，允许 import-outside-toplevel
# 同时临时允许行过长以减少噪音（后续将拆分长行）
# pylint: disable=import-outside-toplevel, line-too-long

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QSplitter

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


class BottomDock:
    """底部栏兼容包装：提供 `toggle_panel`/`show_panel`/`hide_panel`/`is_expanded`。

    将此类放在模块级便于单元测试和复用（而不是在 `setup_ui` 中定义局部类）。
    """

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
            logger.debug("显示底部面板失败（非致命）", exc_info=True)

    def hide_panel(self) -> None:
        try:
            self._widget.setVisible(False)
            # 如果所有子控件都不可见，则隐藏底部栏
            any_visible = False
            try:
                layout = self._bar.layout()
                if layout is not None:
                    for i in range(layout.count()):
                        w = layout.itemAt(i).widget()
                        if w is not None and w.isVisible():
                            any_visible = True
                            break
            except Exception:
                # 若查询子控件失败，则保守地不隐藏 bar
                logger.debug("检查底部栏子控件可见性失败（非致命）", exc_info=True)
                any_visible = True
            if not any_visible:
                self._bar.setVisible(False)
        except Exception:
            logger.debug("隐藏底部面板失败（非致命）", exc_info=True)

    def is_expanded(self) -> bool:
        try:
            return self._widget.isVisible() and self._bar.isVisible()
        except Exception:
            return False


class InitializationManager:
    """管理主窗口的初始化流程"""

    def __init__(self, main_window):
        self.main_window = main_window
        self._is_initializing = True
        self._init_overlay = None

    def setup_ui(self):
        """初始化 UI 组件"""
        try:
            # 在开始初始化时显示一个遮罩，提示用户程序正在初始化
            try:
                self._show_initializing_overlay()
            except Exception:
                logger.debug("显示初始化遮罩失败（非致命）", exc_info=True)

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

            # 使用垂直分割 (QSplitter) 将主内容与可伸缩的底部栏分隔，允许用户上下拖拽调整高度
            splitter = QSplitter(Qt.Vertical)

            # 主内容区域放入分割上方
            splitter.addWidget(operation_panel)

            # 将原来的左右浮动侧边栏合并到一个底部栏（避免浮动按钮与动画）
            bottom_bar = QWidget()
            bottom_layout = QHBoxLayout(bottom_bar)
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(LAYOUT_SPACING)

            # 左右并排放置原先的配置与历史面板
            bottom_layout.addWidget(config_panel, 1)
            bottom_layout.addWidget(history_panel, 0)

            # 初始折叠（隐藏底部栏） — 同时将分割器下部高度设为 0
            bottom_bar.setVisible(False)
            splitter.addWidget(bottom_bar)
            try:
                splitter.setSizes([1000, 0])
            except Exception:
                logger.debug("设置分割器初始大小失败（可忽略）", exc_info=True)

            # 使用模块级的 BottomDock 类作为兼容包装（在文件底部定义）

            # 兼容旧属性：指向包装对象
            config_sidebar = BottomDock(config_panel, bottom_bar)
            history_sidebar = BottomDock(history_panel, bottom_bar)

            self.main_window.config_sidebar = config_sidebar
            self.main_window.history_sidebar = history_sidebar
            self.main_window.operation_panel = operation_panel
            self.main_window.central_widget = central_widget

            # 将分割器加入主布局（包含 operation_panel 与 bottom_bar）
            main_layout.addWidget(splitter)

            # 连接工具栏中的复选框信号以控制底部栏显示/隐藏
            try:
                # 切换时同时调整 splitter 尺寸以折叠/展开底部栏
                def _toggle_bottom_bar(visible: bool) -> None:
                    try:
                        bottom_bar.setVisible(bool(visible))
                        if bool(visible):
                            # 展开到合理默认高度
                            try:
                                splitter.setSizes([800, 200])
                            except Exception:
                                logger.debug("展开底部栏时调整分割器大小失败（非致命）", exc_info=True)
                        else:
                            try:
                                splitter.setSizes([1000, 0])
                            except Exception:
                                logger.debug("折叠底部栏时调整分割器大小失败（非致命）", exc_info=True)
                    except Exception:
                        logger.debug("切换底部栏时发生异常（非致命）", exc_info=True)

                self.main_window.chk_bottom_bar_toolbar.toggled.connect(_toggle_bottom_bar)
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
                    logger.debug("回退到状态栏消息显示失败（非致命）", exc_info=True)

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
                if hasattr(self.main_window, "tab_main") and hasattr(
                        self.main_window, "config_tab_placeholder"
                ):
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
                                # 委托给 BatchManager 的对外方法（非阻塞）统一处理扫描与 UI 状态
                                try:
                                    # 使用非下划线方法以便 BatchManager 可选择在后台执行
                                    self.main_window.batch_manager.scan_and_populate_files(p)
                                except Exception:
                                    logger.debug("扫描文件失败", exc_info=True)
                        except Exception:
                            logger.debug("处理 inp_batch_input 编辑完成回调失败（非致命）", exc_info=True)

                    try:
                        bp.editingFinished.connect(_on_input_edit_finished)
                    except Exception:
                        # 有些 Qt 版本或组件可能不支持该信号，记录并忽略绑定失败
                        logger.debug("绑定 inp_batch_input.editingFinished 失败（兼容性问题）", exc_info=True)
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

        # 连接配置加载信号以更新主窗口控件状态
        try:
            sb = getattr(self.main_window, "signal_bus", None)
            if sb is not None:
                try:
                    sb.configLoaded.connect(
                        lambda _model=None: getattr(
                            self.main_window, "mark_config_loaded", lambda: None
                        )()
                    )
                except Exception:
                    logger.debug("连接 configLoaded 信号失败", exc_info=True)
        except Exception:
            logger.debug("绑定 configLoaded 失败", exc_info=True)

        # 初始刷新一次控件状态（确保开始/保存/选项卡按需禁用）
        try:
            if hasattr(self.main_window, "_refresh_controls_state"):
                try:
                    self.main_window._refresh_controls_state()
                except Exception:
                    logger.debug("刷新控件状态失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("调度刷新控件状态失败（非致命）", exc_info=True)

    def finalize_initialization(self):
        """完成初始化 - 在 showEvent 后调用"""

        def _finalize():
            self._is_initializing = False
            self.main_window._is_initializing = False
            try:
                self._hide_initializing_overlay()
            except Exception:
                logger.debug("隐藏初始化遮罩失败（非致命）", exc_info=True)
            logger.debug("初始化完成")

        # 延迟完成标志，避免 showEvent 期间的弹窗
        QTimer.singleShot(150, _finalize)

    def _setup_menu_bar(self):
        """创建工具栏（伪菜单栏）"""
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import (
                QCheckBox,
                QPushButton,
                QSizePolicy,
                QToolBar,
                QWidget,
            )

            # 隐藏传统菜单栏
            self.main_window.menuBar().setVisible(False)

            # 创建工具栏作为伪菜单栏
            toolbar = QToolBar("主工具栏")
            toolbar.setObjectName("MainToolBar")
            toolbar.setMovable(False)
            toolbar.setFloatable(False)

            # 左侧：文件操作按钮
            btn_new_project = QPushButton("新建Project")
            btn_new_project.setMaximumWidth(90)
            btn_new_project.setToolTip("新建 Project（Ctrl+N）")
            btn_new_project.clicked.connect(self.main_window._new_project)
            # 临时将 Project 相关按钮禁用，避免用户在此阶段误操作
            try:
                btn_new_project.setEnabled(False)
            except Exception:
                pass
            toolbar.addWidget(btn_new_project)

            btn_open_project = QPushButton("打开Project")
            btn_open_project.setMaximumWidth(90)
            btn_open_project.setToolTip("打开 Project（Ctrl+O）")
            btn_open_project.clicked.connect(self.main_window._open_project)
            try:
                btn_open_project.setEnabled(False)
            except Exception:
                pass
            toolbar.addWidget(btn_open_project)

            btn_save_project = QPushButton("保存Project")
            btn_save_project.setMaximumWidth(90)
            btn_save_project.setToolTip("保存 Project（Ctrl+Shift+S）")
            btn_save_project.clicked.connect(self.main_window._on_save_project)
            try:
                btn_save_project.setEnabled(False)
            except Exception:
                pass
            toolbar.addWidget(btn_save_project)

            toolbar.addSeparator()

            # 添加弹性间隔，使右侧按钮靠右
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            toolbar.addWidget(spacer)

            # 右侧：主要操作按钮（将复选框放在浏览按钮左侧）
            # 右侧：展开批处理记录复选框（放在浏览按钮左侧）
            chk_bottom_bar = QCheckBox("展开批处理记录")
            chk_bottom_bar.setToolTip("在底部显示批处理历史记录与配置编辑器")
            chk_bottom_bar.setChecked(False)

            # 将复选框添加到工具栏并添加右侧的操作按钮
            toolbar.addWidget(chk_bottom_bar)

            btn_browse = QPushButton("浏览文件")
            btn_browse.setMaximumWidth(80)
            btn_browse.setToolTip("选择输入文件或目录")
            btn_browse.clicked.connect(self.main_window.browse_batch_input)
            toolbar.addWidget(btn_browse)

            btn_load_config = QPushButton("加载配置")
            btn_load_config.setMaximumWidth(80)
            btn_load_config.setToolTip(
                "加载配置文件（JSON），用于提供 Source/Target part 定义"
            )
            # 绑定到主窗口的 load_config，以恢复旧的加载配置行为
            btn_load_config.clicked.connect(self.main_window.load_config)
            toolbar.addWidget(btn_load_config)

            btn_start = QPushButton("开始处理")
            btn_start.setMaximumWidth(80)
            # 初始化期间默认禁用开始按钮，避免在管理器未就绪时触发批处理
            btn_start.setEnabled(False)
            btn_start.setToolTip("正在初始化，功能暂不可用 — 稍后将自动启用或刷新")
            btn_start.clicked.connect(self.main_window.run_batch_processing)
            toolbar.addWidget(btn_start)

            # 保存复选框引用到主窗口 (复选框已在浏览按钮左侧创建)
            self.main_window.chk_bottom_bar_toolbar = chk_bottom_bar

            # 将工具栏添加到主窗口顶部
            self.main_window.addToolBar(Qt.TopToolBarArea, toolbar)

            # 保存按钮引用以供后续使用
            self.main_window.btn_new_project = btn_new_project
            self.main_window.btn_open_project = btn_open_project
            self.main_window.btn_save_project_toolbar = btn_save_project
            # 标记为临时禁用 project 按钮，供 UIStateManager 等处判断
            try:
                self.main_window._project_buttons_temporarily_disabled = True
            except Exception:
                pass
            self.main_window.btn_browse_menu = btn_browse
            self.main_window.btn_load_config_menu = btn_load_config
            self.main_window.btn_start_menu = btn_start

            logger.info("工具栏已创建")
        except Exception as e:
            logger.error("创建工具栏失败: %s", e)

    def _show_initializing_overlay(self):
        """在主窗口上显示半透明遮罩，提示正在初始化。"""
        try:
            from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout

            if self._init_overlay is not None:
                return
            w = QWidget(self.main_window)
            w.setObjectName("initOverlay")
            w.setAttribute(Qt.WA_StyledBackground, True)
            w.setStyleSheet("background: rgba(0,0,0,0.45);")
            layout = QVBoxLayout(w)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(10)
            lbl = QLabel("正在初始化，请稍候...", w)
            lbl.setStyleSheet("color: white; font-size: 14pt;")
            lbl.setAlignment(Qt.AlignCenter)
            pb = QProgressBar(w)
            pb.setRange(0, 0)  # 不确定进度（忙碌态）
            layout.addStretch(1)
            layout.addWidget(lbl)
            layout.addWidget(pb)
            layout.addStretch(2)
            # 覆盖整个主窗口区域
            try:
                geom = self.main_window.rect()
                w.setGeometry(geom)
            except Exception as e:
                logger.debug("设置初始化遮罩几何信息失败（非致命）: %s", e, exc_info=True)
            w.setVisible(True)
            w.raise_()
            self._init_overlay = w
        except Exception:
            logger.debug("构建初始化遮罩失败（非致命）", exc_info=True)

    def _hide_initializing_overlay(self):
        """隐藏并删除初始化遮罩。"""
        try:
            if self._init_overlay is None:
                return
            try:
                self._init_overlay.setVisible(False)
                self._init_overlay.setParent(None)
            except Exception:
                logger.debug("移除初始化遮罩失败（非致命）", exc_info=True)
            self._init_overlay = None
        except Exception:
            logger.debug("隐藏初始化遮罩失败（非致命）", exc_info=True)
        

    def trigger_initial_layout_update(self):
        """触发初始布局更新"""
        try:
            # 合并为一次定时调用，减少启动时的多次视觉刷新
            def _do_initial_updates():
                try:
                    lm = getattr(self.main_window, "layout_manager", None)
                    if lm:
                        try:
                            # 仅在确实需要调整按钮布局时才执行更新与强制刷新，避免重复昂贵操作
                            if getattr(lm, "needs_button_layout_update", lambda: False)():
                                lm.update_button_layout()
                                try:
                                    lm.force_layout_refresh()
                                except Exception:
                                    logger.debug("强制刷新布局失败（非致命）", exc_info=True)
                        except Exception:
                            logger.debug("更新初始布局失败（非致命）", exc_info=True)
                except Exception:
                    logger.debug("调度初始布局更新时发生错误", exc_info=True)

            QTimer.singleShot(120, _do_initial_updates)
        except Exception:
            logger.debug("Initial layout update scheduling failed", exc_info=True)
