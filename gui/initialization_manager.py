"""
初始化管理器 - 负责主窗口的 UI 初始化与管理器设置
"""

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui.batch_history import BatchHistoryPanel, BatchHistoryStore
from gui.batch_manager import BatchManager
from gui.config_manager import ConfigManager
from gui.layout_manager import LayoutManager
from gui.log_manager import LoggingManager
from gui.part_manager import PartManager
from gui.slide_sidebar import SlideSidebar

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

            # 构建浮动覆盖层侧边栏（默认隐藏），直接作为 central_widget 的子组件
            # 重要：这些侧边栏是绝对定位的（不通过布局管理），所以需要手动设置几何位置
            config_sidebar = SlideSidebar(
                config_panel,
                side="left",
                # 配置面板需要同时容纳 Source/Target 两列，侧边栏过窄会导致横向滚动体验很怪。
                # 这里加宽左侧侧边栏，优先保证配置编辑器可读性。
                expanded_width=820,
                button_text_collapsed=">>",
                button_text_expanded="<<",
                parent=central_widget,
            )
            history_sidebar = SlideSidebar(
                history_panel,
                side="right",
                expanded_width=360,
                button_text_collapsed="<<",
                button_text_expanded=">>",
                parent=central_widget,
            )

            # 侧边栏为浮动覆盖层子组件：显示按钮、置顶层级
            config_sidebar.setVisible(True)
            history_sidebar.setVisible(True)
            config_sidebar.raise_()
            history_sidebar.raise_()

            self.main_window.config_sidebar = config_sidebar
            self.main_window.history_sidebar = history_sidebar
            self.main_window.operation_panel = operation_panel
            self.main_window.central_widget = central_widget

            # 动态调整侧边栏位置（贴合边缘，不受主内容影响）
            def resize_sidebars():
                try:
                    h = central_widget.height()
                    w = central_widget.width()

                    if h <= 0 or w <= 0:
                        return

                    # 统一由 SlideSidebar 自身根据 side 贴边定位
                    config_sidebar.reposition_in_parent()
                    history_sidebar.reposition_in_parent()

                    # 保持覆盖层在最上面
                    config_sidebar.raise_()
                    history_sidebar.raise_()
                except Exception as e:
                    logger.error("侧边栏定位失败: %s", e, exc_info=True)

            # 重写 central_widget 的 resizeEvent
            original_resize = central_widget.resizeEvent

            def new_resize_event(event):
                original_resize(event)
                resize_sidebars()

            central_widget.resizeEvent = new_resize_event

            # 初始调整一次
            QTimer.singleShot(0, resize_sidebars)

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
                                    # 兜底：仅更新匹配控件的启用状态
                                    try:
                                        if hasattr(self.main_window, "inp_pattern"):
                                            self.main_window.inp_pattern.setEnabled(
                                                not p.is_file()
                                            )
                                        if hasattr(
                                            self.main_window,
                                            "cmb_pattern_preset",
                                        ):
                                            self.main_window.cmb_pattern_preset.setEnabled(
                                                not p.is_file()
                                            )
                                    except Exception:
                                        pass
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
