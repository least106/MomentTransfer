"""
初始化管理器 - 负责主窗口的 UI 初始化与管理器设置
"""

import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PySide6.QtCore import Qt, QTimer

from gui.config_manager import ConfigManager
from gui.part_manager import PartManager
from gui.batch_manager import BatchManager
from gui.visualization_manager import VisualizationManager
from gui.layout_manager import LayoutManager
from gui.log_manager import LoggingManager

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

            # 创建配置面板
            config_panel = self.main_window.create_config_panel()

            # 创建操作面板（使用 main_window 的方法）
            operation_panel = self.main_window.create_operation_panel()
            self.main_window.operation_panel = operation_panel

            # 存储引用以便管理器访问
            self.main_window.config_panel = config_panel

            # 创建主分割器
            splitter = QSplitter(Qt.Vertical)
            splitter.addWidget(config_panel)
            splitter.addWidget(operation_panel)

            # 记录 splitter，便于后续按流程动态显示/隐藏配置面板
            self.main_window.main_splitter = splitter

            # 初始化阶段：默认隐藏配置编辑器，避免页面初始化可选项过多导致注意力分散。
            # 在用户选中数据文件后再显示配置编辑器。
            try:
                config_panel.setVisible(False)
                splitter.setSizes([0, 1])
            except Exception:
                logger.debug(
                    "splitter initial hide failed (non-fatal)", exc_info=True
                )

            main_layout.addWidget(splitter)
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
                    self.main_window.statusBar().showMessage(
                        "步骤1：选择文件或目录"
                    )
                except Exception:
                    pass

            logger.info("UI 组件初始化成功")
        except Exception as e:
            logger.error(f"UI 初始化失败: {e}", exc_info=True)
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
            self.main_window.visualization_manager = VisualizationManager(
                self.main_window
            )
            self.main_window.layout_manager = LayoutManager(self.main_window)

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
                                        if hasattr(
                                            self.main_window, "inp_pattern"
                                        ):
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
                logger.debug(
                    "绑定 inp_batch_input 编辑完成信号失败", exc_info=True
                )
        except Exception as e:
            logger.error(f"管理器初始化失败: {e}", exc_info=True)
            # 继续运行，即使管理器初始化失败

    def setup_logging(self):
        """设置日志系统"""
        try:
            logging_manager = LoggingManager(self.main_window)
            logging_manager.setup_gui_logging()
        except Exception as e:
            logger.debug(
                f"GUI logging setup failed (non-fatal): {e}", exc_info=True
            )

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
                    self.main_window.update_button_layout()
                except Exception:
                    pass
                try:
                    self.main_window._force_layout_refresh()
                except Exception:
                    pass

            QTimer.singleShot(120, _do_initial_updates)
        except Exception:
            logger.debug(
                "Initial layout update scheduling failed", exc_info=True
            )
