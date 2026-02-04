"""
初始化管理器 - 负责主窗口的 UI 初始化与管理器设置
"""

# 延迟导入在初始化流程中较为常见，允许 import-outside-toplevel
# 同时临时允许行过长以减少噪音（后续将拆分长行）
# pylint: disable=import-outside-toplevel, line-too-long

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QVBoxLayout, QWidget

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

try:
    from gui.managers import _report_ui_exception
except Exception:
    _report_ui_exception = None


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

    def _set_splitter_bottom_ratio(self, splitter: QSplitter, bottom_ratio: float) -> None:
        """按比例设置 splitter 的上下部尺寸（bottom_ratio 为 0.0-1.0）。

        为了避免在布局尚未完成时设置不合理的像素值，本函数会尝试即时计算并设置；
        若可用高度为 0，则使用 `QTimer.singleShot(0, ...)` 在事件循环下一次机会重试。
        """
        try:
            # 限制比例范围
            try:
                r = float(bottom_ratio)
            except Exception:
                r = 0.0
            r = max(0.0, min(1.0, r))

            def _apply():
                try:
                    total_h = splitter.size().height()
                    # 回退：尝试从父窗口或主窗口获取高度
                    if not total_h or total_h <= 0:
                        try:
                            total_h = splitter.parentWidget().height() or 0
                        except Exception:
                            total_h = 0
                    if not total_h or total_h <= 0:
                        try:
                            total_h = self.main_window.height() or 0
                        except Exception:
                            total_h = 0

                    # 若仍无法获取可靠高度，则使用相对权重设置以交由 Qt 布局管理
                    if not total_h or total_h <= 0:
                        # 使用 setStretchFactor 提供更稳健的行为
                        try:
                            splitter.setStretchFactor(0, 1)
                            splitter.setStretchFactor(1, 0 if r <= 0.0 else 1)
                        except Exception:
                            pass
                        return

                    bottom_h = int(total_h * r)
                    top_h = max(0, total_h - bottom_h)
                    try:
                        splitter.setSizes([top_h, bottom_h])
                    except Exception:
                        # 回退为权重设置
                        try:
                            splitter.setStretchFactor(0, 1)
                            splitter.setStretchFactor(1, 0 if r <= 0.0 else 1)
                        except Exception:
                            pass
                except Exception:
                    # 在应用尺寸时若出现问题，不要抛出异常
                    logger.debug("_apply splitter sizes failed", exc_info=True)

            # 若当前可见尺寸为 0，则在事件循环下一次机会重试
            cur_h = splitter.size().height()
            if not cur_h or cur_h <= 0:
                try:
                    QTimer.singleShot(0, _apply)
                except Exception:
                    _apply()
            else:
                _apply()
        except Exception:
            logger.debug("_set_splitter_bottom_ratio failed", exc_info=True)

    def setup_ui(self):
        """初始化 UI 组件"""
        # setup_ui invoked
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
            main_layout.setContentsMargins(LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN)
            main_layout.setSpacing(LAYOUT_SPACING)

            # 创建状态横幅（默认隐藏）
            try:
                from gui.state_banner import StateBanner

                state_banner = StateBanner()
                state_banner.exitRequested.connect(self._on_banner_exit_requested)
                # 连接带状态类型的信号
                state_banner.exitStateRequested.connect(self._on_banner_exit_state_requested)
                state_banner.setVisible(False)  # 默认隐藏
                self.main_window.state_banner = state_banner
                # 若工具栏已创建，则优先放入工具栏；否则回退到主布局
                toolbar = getattr(self.main_window, "main_toolbar", None)
                if toolbar is not None:
                    try:
                        state_banner.apply_toolbar_mode()
                    except Exception:
                        logger.debug("应用状态横幅工具栏模式失败（非致命）", exc_info=True)
                    try:
                        # 将状态横幅插入到弹性间隔之前，使其显示在左侧按钮右边
                        spacer_action = getattr(self.main_window, "_toolbar_spacer_action", None)
                        if spacer_action is not None:
                            banner_action = toolbar.insertWidget(spacer_action, state_banner)
                        else:
                            banner_action = toolbar.addWidget(state_banner)
                        # 保存 action 引用，便于通过 action 控制可见性
                        self.main_window._state_banner_action = banner_action
                        # 设置状态横幅的 action 引用
                        state_banner.set_toolbar_action(banner_action)
                        # 初始隐藏 action
                        banner_action.setVisible(False)
                        logger.debug("状态横幅已添加到工具栏")
                    except Exception:
                        logger.debug("状态横幅添加到工具栏失败，回退到主布局", exc_info=True)
                        main_layout.addWidget(state_banner)
                else:
                    main_layout.addWidget(state_banner)
                    logger.debug("状态横幅已添加到主布局")
            except Exception as e:
                logger.debug("创建状态横幅失败（非致命）: %s", e, exc_info=True)
                self.main_window.state_banner = None

            # 创建配置/操作面板
            config_panel = self.main_window.create_config_panel()
            part_mapping_panel = self.main_window.create_part_mapping_panel()
            operation_panel = self.main_window.create_operation_panel()
            # 通过集中注册接口统一管理面板，避免在多处重复赋值
            try:
                if hasattr(self.main_window, "register_panel"):
                    self.main_window.register_panel("config_panel", config_panel)
                    self.main_window.register_panel("part_mapping_panel", part_mapping_panel)
                    self.main_window.register_panel("operation_panel", operation_panel)
                else:
                    self.main_window.config_panel = config_panel
                    self.main_window.part_mapping_panel = part_mapping_panel
                    self.main_window.operation_panel = operation_panel
            except Exception:
                # 兼容回退：尽量设置属性并记录失败
                try:
                    self.main_window.config_panel = config_panel
                except Exception:
                    logger.debug("注册 config_panel 失败（非致命）", exc_info=True)
                try:
                    self.main_window.part_mapping_panel = part_mapping_panel
                except Exception:
                    logger.debug("注册 part_mapping_panel 失败（非致命）", exc_info=True)
                try:
                    self.main_window.operation_panel = operation_panel
                except Exception:
                    logger.debug("注册 operation_panel 失败（非致命）", exc_info=True)

            # 创建历史存储与面板
            history_store = BatchHistoryStore()
            history_panel = BatchHistoryPanel(history_store)
            self.main_window.history_store = history_store
            self.main_window.history_panel = history_panel

            # 使用垂直分割 (QSplitter) 将主内容与可伸缩的底部栏分隔，允许用户上下拖拽调整高度
            splitter = QSplitter(Qt.Vertical)
            # 保存 splitter 引用供后续信号连接使用
            self.main_window._bottom_splitter = splitter

            # 主内容区域放入分割上方
            # 防御性检查：确保 operation_panel 是 QWidget 实例（某些回归会返回 bool/None）
            try:
                if not isinstance(operation_panel, QWidget):
                    logger.error(
                        "operation_panel 不是 QWidget，类型=%r，使用占位 QWidget 回退",
                        type(operation_panel),
                    )
                    operation_panel = QWidget()
            except Exception:
                # 若 isinstance 检查失败，创建回退 QWidget
                operation_panel = QWidget()

            splitter.addWidget(operation_panel)

            # 将原来的左右浮动侧边栏合并到一个底部栏（避免浮动按钮与动画）
            bottom_bar = QWidget()
            # 保存 bottom_bar 引用供后续信号连接使用
            self.main_window._bottom_bar = bottom_bar
            bottom_layout = QHBoxLayout(bottom_bar)
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(LAYOUT_SPACING)

            # 底部栏仅放置批处理历史面板，避免配置面板重复插入导致父级重置
            bottom_layout.addWidget(history_panel, 1)

            # 初始折叠（隐藏底部栏） — 使用比例设置分割器大小以提高跨分辨率/字体的稳健性
            bottom_bar.setVisible(False)
            splitter.addWidget(bottom_bar)
            try:
                # 使用 0.0 的底部占比以折叠底部栏（在布局完成后会应用）
                self._set_splitter_bottom_ratio(splitter, 0.0)
            except Exception:
                logger.debug("设置分割器初始大小失败（可忽略）", exc_info=True)

            # 使用模块级的 BottomDock 类作为兼容包装（在文件底部定义）

            # 兼容旧属性：指向包装对象
            config_sidebar = BottomDock(config_panel, bottom_bar)
            history_sidebar = BottomDock(history_panel, bottom_bar)

            self.main_window.config_sidebar = config_sidebar
            self.main_window.history_sidebar = history_sidebar
            try:
                if hasattr(self.main_window, "register_panel"):
                    self.main_window.register_panel("operation_panel", operation_panel)
                else:
                    self.main_window.operation_panel = operation_panel
            except Exception:
                try:
                    self.main_window.operation_panel = operation_panel
                except Exception:
                    logger.debug("注册 operation_panel 回退失败（非致命）", exc_info=True)
            self.main_window.central_widget = central_widget

            # 将分割器加入主布局（包含 operation_panel 与 bottom_bar）
            main_layout.addWidget(splitter)

            # 连接底部栏切换信号（必须在 splitter 和 bottom_bar 创建后）
            try:
                self._connect_bottom_bar_signals()
            except Exception:
                logger.debug("连接底部栏信号失败（非致命）", exc_info=True)

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
            # toolbar.addWidget(state_banner)  # 移除状态横幅从工具栏

    def setup_managers(self):
        """初始化所有管理器"""
        try:
            # 必须在创建面板之后初始化管理器
            config_panel = getattr(self.main_window, "config_panel", None)
            if not config_panel:
                raise RuntimeError("config_panel 未初始化")

            self.main_window.config_manager = ConfigManager(self.main_window, config_panel)
            self.main_window.part_manager = PartManager(self.main_window)
            self.main_window.batch_manager = BatchManager(self.main_window)
            self.main_window.layout_manager = LayoutManager(self.main_window)

            # 初始化全局状态管理器并连接到 batch_manager
            try:
                from gui.global_state_manager import GlobalStateManager

                state_manager = GlobalStateManager.instance()
                batch_manager = self.main_window.batch_manager

                # 连接状态改变信号到 batch_manager 的回调
                if hasattr(batch_manager, "_on_redo_mode_changed"):
                    state_manager.redoModeChanged.connect(batch_manager._on_redo_mode_changed)
                    logger.info("已连接全局状态管理器到 batch_manager")
                else:
                    logger.warning("batch_manager 缺少 _on_redo_mode_changed 方法")
            except Exception as e:
                logger.debug("初始化全局状态管理器失败: %s", e, exc_info=True)

            # 初始化 ProjectManager
            from gui.project_manager import ProjectManager

            self.main_window.project_manager = ProjectManager(self.main_window)

            # 将 ConfigPanel 替换到 Tab 的"参考系管理"位置
            try:
                if hasattr(self.main_window, "tab_main") and hasattr(self.main_window, "config_tab_placeholder"):
                    tab_main = self.main_window.tab_main
                    config_panel = self.main_window.config_panel
                    part_mapping_panel = getattr(self.main_window, "part_mapping_panel", None)
                    # 替换第0个Tab的内容（在配置编辑器右侧加入映射面板）
                    container = QWidget()
                    container_layout = QHBoxLayout(container)
                    container_layout.setContentsMargins(0, 0, 0, 0)
                    container_layout.setSpacing(10)
                    container_layout.addWidget(config_panel, 3)
                    if part_mapping_panel is not None:
                        container_layout.addWidget(part_mapping_panel, 2)
                    tab_main.removeTab(0)
                    tab_main.insertTab(0, container, "参考系管理")
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
            # 尝试绑定 BatchManager 的 UI 相关信号（若 UI 尚未就绪则重试）
            try:

                def _bind_once() -> bool:
                    try:
                        bm = getattr(self.main_window, "batch_manager", None)
                        if bm is None:
                            return False
                        made = False
                        try:
                            if hasattr(bm, "_connect_ui_signals"):
                                res = bm._connect_ui_signals()
                                made = made or bool(res)
                        except Exception:
                            logger.debug(
                                "在 bind_once 中连接 UI 信号失败（非致命）",
                                exc_info=True,
                            )
                        try:
                            if hasattr(bm, "_connect_quick_filter"):
                                res = bm._connect_quick_filter()
                                made = made or bool(res)
                        except Exception:
                            logger.debug(
                                "在 bind_once 中连接快速筛选失败（非致命）",
                                exc_info=True,
                            )
                        try:
                            if hasattr(bm, "_connect_signal_bus_events"):
                                res = bm._connect_signal_bus_events()
                                made = made or bool(res)
                        except Exception:
                            logger.debug(
                                "在 bind_once 中连接 signal bus 失败（非致命）",
                                exc_info=True,
                            )
                        return bool(made)
                    except Exception:
                        logger.debug("批处理 UI 绑定单次尝试内部异常", exc_info=True)
                        return False

                def _attempt_bind(attempt_index: int = 0) -> None:
                    try:
                        if _bind_once():
                            logger.info("批处理 UI 绑定成功")
                            return
                        # 重试上限与指数回退延迟
                        delays = [0, 50, 150, 300, 600, 800]
                        if attempt_index >= len(delays) - 1:
                            logger.debug("批处理 UI 绑定尝试达到上限，停止重试")
                            return
                        delay = delays[min(attempt_index + 1, len(delays) - 1)]
                        try:
                            QTimer.singleShot(delay, lambda: _attempt_bind(attempt_index + 1))
                        except Exception:
                            logger.debug("调度批处理 UI 绑定重试失败（非致命）", exc_info=True)
                    except Exception:
                        logger.debug("批处理 UI 绑定尝试内部异常", exc_info=True)

                try:
                    _attempt_bind(0)
                except Exception:
                    logger.debug("启动批处理 UI 绑定重试序列失败（非致命）", exc_info=True)
            except Exception:
                logger.debug("调度批处理 UI 绑定流程失败（非致命）", exc_info=True)
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
                            logger.debug(
                                "处理 inp_batch_input 编辑完成回调失败（非致命）",
                                exc_info=True,
                            )

                    try:
                        bp.editingFinished.connect(_on_input_edit_finished)
                    except Exception:
                        # 有些 Qt 版本或组件可能不支持该信号，记录并忽略绑定失败
                        logger.debug(
                            "绑定 inp_batch_input.editingFinished 失败（兼容性问题）",
                            exc_info=True,
                        )
            except Exception:
                logger.debug("绑定 inp_batch_input 编辑完成信号失败", exc_info=True)
        except Exception as e:
            logger.error("管理器初始化失败: %s", e, exc_info=True)
            # 向用户提供轻量提示（避免静默失败）
            try:
                if _report_ui_exception:
                    _report_ui_exception(self.main_window, "管理器初始化失败（请查看日志以获取详细信息）")
            except Exception:
                logger.debug("报告初始化管理器失败时出错", exc_info=True)
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
                            self.main_window,
                            "mark_config_loaded",
                            lambda: None,
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
        # 使用事件驱动的重试策略替代固定短延迟：在 managers 与关键组件就绪后再解除初始化保护。
        # 这样可以避免在慢机或 I/O 慢时过早解除初始化或反之长时间保持锁定。

        # 判断是否可以完成初始化的条件：主窗口上的关键管理器存在
        def _is_ready():
            try:
                mw = self.main_window
                required = (
                    getattr(mw, "config_manager", None),
                    getattr(mw, "part_manager", None),
                    getattr(mw, "batch_manager", None),
                    getattr(mw, "layout_manager", None),
                )
                # 若至少一个 manager 缺失，则认为尚未就绪
                return all(x is not None for x in required)
            except Exception:
                return False

        start_time = None

        def _attempt_finalize():
            nonlocal start_time
            try:
                from time import monotonic

                if start_time is None:
                    start_time = monotonic()
                # 如果满足就绪条件或超过最大等待时间（5s），都执行 finalize
                elapsed = monotonic() - start_time
                max_wait = 5.0
                if _is_ready() or elapsed >= max_wait:
                    try:
                        self._is_initializing = False
                        self.main_window._is_initializing = False
                        try:
                            self._hide_initializing_overlay()
                        except Exception:
                            logger.debug("隐藏初始化遮罩失败（非致命）", exc_info=True)
                        # 初始化完成后启用 `新建`/`打开` 按钮，但让保存按钮继续由 UIStateManager 控制
                        try:
                            setattr(
                                self.main_window,
                                "_project_buttons_temporarily_disabled",
                                False,
                            )
                            for btn_name in ("btn_new_project", "btn_open_project"):
                                btn = getattr(self.main_window, btn_name, None)
                                if btn is not None:
                                    try:
                                        btn.setEnabled(True)
                                    except Exception:
                                        logger.debug("启用按钮 %s 失败", btn_name, exc_info=True)
                            # 刷新控件状态，让 managers 中的逻辑决定保存按钮是否可用（基于 is_operation_performed()）
                            try:
                                if hasattr(self.main_window, "_refresh_controls_state"):
                                    self.main_window._refresh_controls_state()
                            except Exception:
                                logger.debug("刷新控件状态失败", exc_info=True)
                            # 创建配置修改警告标签
                            try:
                                self._create_config_warning_label()
                            except Exception:
                                logger.debug("创建配置警告标签失败（非致命）", exc_info=True)
                                logger.debug("刷新控件状态失败（非致命）", exc_info=True)
                        except Exception:
                            logger.debug("初始化完成后启用 project 按钮失败", exc_info=True)
                        logger.debug("初始化完成 (elapsed=%.3fs)", elapsed)
                        return
                    except Exception:
                        logger.debug("执行 finalize 操作时失败（非致命）", exc_info=True)

                # 否则：还未就绪，使用指数回退的定时再次尝试（上限 800ms）
                # initial 0ms -> 50ms -> 150ms -> 300ms -> 600ms -> 800ms ...
                # 使用 elapsed 决定下次延迟
                if elapsed < 0.05:
                    delay = 0
                elif elapsed < 0.2:
                    delay = 50
                elif elapsed < 0.6:
                    delay = 150
                elif elapsed < 1.2:
                    delay = 300
                elif elapsed < 2.5:
                    delay = 600
                else:
                    delay = 800

                try:
                    QTimer.singleShot(delay, _attempt_finalize)
                except Exception:
                    # 若调度失败，记录并在 150ms 后尽力完成以避免永久阻塞
                    logger.debug("调度后续 finalize 尝试失败，使用后备单次延迟", exc_info=True)
                    try:
                        QTimer.singleShot(150, _attempt_finalize)
                    except Exception:
                        # 最终兜底：立即尝试
                        _attempt_finalize()
            except Exception:
                logger.debug("finalize_initialization 内部调度失败", exc_info=True)

        # 立即尝试一次（非阻塞）
        try:
            _attempt_finalize()
        except Exception:
            logger.debug(
                "启动 finalize_initialization 过程失败，退回到固定延迟解除初始化",
                exc_info=True,
            )
            try:
                QTimer.singleShot(150, lambda: setattr(self.main_window, "_is_initializing", False))
                QTimer.singleShot(150, lambda: setattr(self, "_is_initializing", False))
            except Exception:
                # 如果也失败，则立即解除以避免界面永久被锁定
                try:
                    self.main_window._is_initializing = False
                    self._is_initializing = False
                except Exception:
                    pass

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
            spacer_action = toolbar.addWidget(spacer)
            # 保存弹性间隔动作作为状态横幅插入锚点
            self.main_window._toolbar_spacer_action = spacer_action

            # 右侧：主要操作按钮（将复选框放在浏览按钮左侧）
            # 右侧：展开批处理记录复选框（放在浏览按钮左侧）
            chk_bottom_bar = QCheckBox("展开批处理记录")
            chk_bottom_bar.setToolTip("在底部显示批处理历史记录")
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
            btn_load_config.setToolTip("加载配置文件（JSON），用于提供 Source/Target part 定义")

            # 绑定到一个安全的回调：若 ConfigManager 已初始化则委托给它，否则弹出文件选择或提示
            def _on_load_config_clicked():
                try:
                    cm = getattr(self.main_window, "config_manager", None)
                    if cm and hasattr(cm, "load_config"):
                        try:
                            cm.load_config()
                            return
                        except Exception:
                            logger.debug(
                                "ConfigManager.load_config 调用失败，回退处理",
                                exc_info=True,
                            )

                    # 回退：由用户选择配置文件并尝试通过 ConfigManager 或直接提示
                    from PySide6.QtWidgets import QFileDialog, QMessageBox

                    fp, _ = QFileDialog.getOpenFileName(
                        self.main_window,
                        "加载配置文件",
                        "",
                        "JSON Files (*.json);;All Files (*)",
                    )
                    if not fp:
                        return

                    if cm and hasattr(cm, "load_config_from_file"):
                        try:
                            cm.load_config_from_file(fp)
                        except Exception as e:
                            try:
                                QMessageBox.critical(self.main_window, "错误", f"加载配置失败: {e}")
                            except Exception:
                                logger.debug("显示加载失败对话失败", exc_info=True)
                    else:
                        try:
                            QMessageBox.information(
                                self.main_window,
                                "加载配置",
                                "配置加载将在管理器初始化后生效。",
                            )
                        except Exception:
                            logger.debug("显示加载提示失败", exc_info=True)
                except Exception:
                    try:
                        from gui.managers import _report_ui_exception

                        _report_ui_exception(self.main_window, "加载配置回调处理失败")
                    except Exception:
                        logger.debug("加载配置回调处理失败", exc_info=True)

            btn_load_config.clicked.connect(_on_load_config_clicked)
            toolbar.addWidget(btn_load_config)

            btn_start = QPushButton("开始处理")
            btn_start.setMaximumWidth(80)
            # 初始化期间默认禁用开始按钮，避免在管理器未就绪时触发批处理
            btn_start.setEnabled(False)
            btn_start.setToolTip("正在初始化，功能暂不可用 — 稍后将自动启用或刷新")
            btn_start.clicked.connect(self.main_window.run_batch_processing)
            toolbar.addWidget(btn_start)

            # 添加取消按钮（初始隐藏，仅在批处理期间显示）
            btn_cancel = QPushButton("取消")
            btn_cancel.setMaximumWidth(60)
            btn_cancel.setToolTip("取消当前批处理")
            btn_cancel.setVisible(False)  # 初始隐藏
            btn_cancel.setEnabled(False)
            btn_cancel.clicked.connect(self.main_window.request_cancel_batch)
            toolbar.addWidget(btn_cancel)

            # 状态横幅将插入到右侧按钮之前（通过锚点动作定位）

            # 保存复选框引用到主窗口 (复选框已在浏览按钮左侧创建)
            self.main_window.chk_bottom_bar_toolbar = chk_bottom_bar

            # 将工具栏添加到主窗口顶部
            self.main_window.addToolBar(Qt.TopToolBarArea, toolbar)

            # 保存工具栏引用，便于后续插入状态横幅
            self.main_window.main_toolbar = toolbar

            # 保存按钮引用以供后续使用
            self.main_window.btn_new_project = btn_new_project
            self.main_window.btn_open_project = btn_open_project
            self.main_window.btn_save_project_toolbar = btn_save_project
            # 标记为临时禁用 project 按钮，供 UIStateManager 等处判断
            try:
                # 不再永久将 project 按钮标记为临时禁用。
                # 保留属性但默认为 False，避免导致按钮长期不可用。
                self.main_window._project_buttons_temporarily_disabled = False
            except Exception:
                pass
            self.main_window.btn_browse_menu = btn_browse
            self.main_window.btn_load_config_menu = btn_load_config
            self.main_window.btn_start_menu = btn_start
            self.main_window.btn_cancel = btn_cancel

            logger.info("工具栏已创建")
        except Exception as e:
            logger.error("创建工具栏失败: %s", e)

    def _connect_bottom_bar_signals(self):
        """连接底部栏切换信号（在 splitter 和 bottom_bar 创建后调用）"""
        try:
            splitter = self.main_window._bottom_splitter
            bottom_bar = self.main_window._bottom_bar

            # 切换时同时调整 splitter 尺寸以折叠/展开底部栏
            def _toggle_bottom_bar(visible: bool) -> None:
                try:
                    bottom_bar.setVisible(bool(visible))
                    if bool(visible):
                        # 展开到合理默认高度
                        try:
                            # 使用约 20% 的底部高度作为默认展开比例
                            self._set_splitter_bottom_ratio(splitter, 0.2)
                        except Exception:
                            logger.debug(
                                "展开底部栏时调整分割器大小失败（非致命）",
                                exc_info=True,
                            )
                    else:
                        try:
                            self._set_splitter_bottom_ratio(splitter, 0.0)
                        except Exception:
                            logger.debug(
                                "折叠底部栏时调整分割器大小失败（非致命）",
                                exc_info=True,
                            )
                except Exception:
                    logger.debug("切换底部栏时发生异常（非致命）", exc_info=True)

            self.main_window.chk_bottom_bar_toolbar.toggled.connect(_toggle_bottom_bar)
        except Exception:
            logger.debug("连接底部栏切换信号失败", exc_info=True)

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
                logger.debug(
                    "设置初始化遮罩几何信息失败（非致命）: %s",
                    e,
                    exc_info=True,
                )
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
                                    logger.debug(
                                        "强制刷新布局失败（非致命）",
                                        exc_info=True,
                                    )
                        except Exception:
                            logger.debug("更新初始布局失败（非致命）", exc_info=True)
                except Exception:
                    logger.debug("调度初始布局更新时发生错误", exc_info=True)

            QTimer.singleShot(120, _do_initial_updates)
        except Exception:
            logger.debug("Initial layout update scheduling failed", exc_info=True)

    def _create_config_warning_label(self):
        """创建配置修改警告标签并连接信号"""
        try:
            from PySide6.QtWidgets import QLabel

            # 创建警告标签
            warning_label = QLabel("⚠️ 配置已修改未保存")
            warning_label.setStyleSheet(
                """
                QLabel {
                    color: #ff6b35;
                    background-color: rgba(255, 107, 53, 0.1);
                    border: 1px solid #ff6b35;
                    border-radius: 3px;
                    padding: 4px 8px;
                    font-weight: bold;
                }
            """
            )
            warning_label.setVisible(False)
            self.main_window.config_warning_label = warning_label

            # 查找批处理按钮所在布局并添加警告标签
            try:
                batch_panel = getattr(self.main_window, "batch_panel", None)
                if batch_panel:
                    # 尝试将警告标签添加到批处理面板顶部
                    layout = batch_panel.layout()
                    if layout:
                        # 在第一个位置插入警告标签
                        layout.insertWidget(0, warning_label)
                else:
                    # 回退：添加到状态栏
                    statusbar = getattr(self.main_window, "statusBar", lambda: None)()
                    if statusbar:
                        statusbar.addPermanentWidget(warning_label)
            except Exception:
                logger.debug("添加配置警告标签到布局失败", exc_info=True)

            # 连接配置修改信号
            def _on_config_modified(modified: bool):
                try:
                    warning_label.setVisible(modified)
                except Exception:
                    logger.debug("更新配置警告标签可见性失败", exc_info=True)

            try:
                from gui.signal_bus import SignalBus

                signal_bus = SignalBus.instance()
                signal_bus.configModified.connect(_on_config_modified)
            except Exception:
                logger.debug("连接配置修改信号失败", exc_info=True)

        except Exception:
            logger.debug("创建配置警告标签失败（完整）", exc_info=True)

    def _on_banner_exit_requested(self):
        """用户点击横幅退出按钮（兼容旧信号）"""
        # 尝试获取状态类型并调用新方法
        try:
            banner = getattr(self.main_window, "state_banner", None)
            if banner:
                from gui.state_banner import BannerStateType

                state_type = getattr(banner, "_current_state_type", BannerStateType.NONE)
                self._on_banner_exit_state_requested(state_type)
                return
        except Exception:
            pass
        # 回退：假设是重做模式
        try:
            from gui.state_banner import BannerStateType

            self._on_banner_exit_state_requested(BannerStateType.REDO_MODE)
        except Exception:
            logger.debug("处理横幅退出请求失败", exc_info=True)

    def _on_banner_exit_state_requested(self, state_type):
        """用户点击横幅退出按钮，根据状态类型执行相应清理"""
        try:
            from gui.state_banner import BannerStateType

            if state_type == BannerStateType.REDO_MODE:
                # 退出重做模式
                try:
                    from gui.global_state_manager import GlobalStateManager

                    state_manager = GlobalStateManager.instance()
                    if state_manager and state_manager.is_redo_mode:
                        state_manager.exit_redo_mode()
                        logger.info("已通过全局状态管理器退出重做模式")
                except Exception:
                    logger.debug("通过全局状态管理器退出重做模式失败", exc_info=True)

                # 清除本地重做状态
                try:
                    if hasattr(self.main_window, "batch_manager") and self.main_window.batch_manager:
                        self.main_window.batch_manager._redo_mode_parent_id = None
                except Exception:
                    pass

                logger.info("用户退出重做模式")

            elif state_type == BannerStateType.PROJECT_LOADED:
                # 退出项目模式：清除当前项目文件关联
                try:
                    if hasattr(self.main_window, "project_manager") and self.main_window.project_manager:
                        pm = self.main_window.project_manager
                        pm.current_project_file = None
                        pm.last_saved_state = None
                        logger.info("已清除当前项目文件关联")
                except Exception:
                    logger.debug("清除项目文件关联失败", exc_info=True)

                logger.info("用户退出项目模式")
            else:
                logger.info("用户退出状态横幅（类型: %s）", state_type)

        except Exception:
            logger.debug("处理横幅退出请求失败", exc_info=True)
