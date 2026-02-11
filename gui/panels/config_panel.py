"""
参考系管理面板 - 汇总 Global/Source/Target 坐标系配置与加载/保存按钮。
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .global_coord_panel import GlobalCoordSystemPanel
from .source_panel import SourcePanel
from .target_panel import TargetPanel

logger = logging.getLogger(__name__)


class ConfigPanel(QWidget):
    """配置编辑器面板，封装 Source/Target 面板与配置按钮。"""

    loadRequested = Signal()
    saveRequested = Signal()
    # 已移除：applyRequested 信号与“应用配置”按钮，
    # 因为配置现在直接保存为 ProjectConfigModel 并在需要时由批处理按文件创建计算器。

    def __init__(self, parent=None):
        super().__init__(parent)
        # 不设置固定的最小宽度，让侧边栏容器决定大小
        self.setMinimumWidth(100)
        # 移除最大高度限制，允许滚动
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        title = QLabel("配置编辑器")
        try:
            title.setObjectName("panelTitle")
        except Exception:
            pass
        header_layout.addWidget(title)

        # 未保存提示：轻量徽标，避免挤压坐标系管理页面
        try:
            self.lbl_unsaved = QLabel("未保存")
            self.lbl_unsaved.setObjectName("unsavedNotice")
            self.lbl_unsaved.setStyleSheet(
                "background-color: #fff3cd; color: #856404; padding:2px 6px; "
                "border-radius:8px; font-size:11px;"
            )
            self.lbl_unsaved.setVisible(False)
            self.lbl_unsaved.setToolTip("配置已被修改，请记得保存（可在配置编辑器中编辑 Part）")
            self.lbl_unsaved.setSizePolicy(
                self.lbl_unsaved.sizePolicy().horizontalPolicy(),
                self.lbl_unsaved.sizePolicy().verticalPolicy(),
            )
            header_layout.addWidget(self.lbl_unsaved)
        except Exception:
            self.lbl_unsaved = None

        header_layout.addStretch()
        main_layout.addWidget(header)

        # 面板组件：Global + Source + Target
        self.global_panel = GlobalCoordSystemPanel(self)
        self.source_panel = SourcePanel(self)
        self.target_panel = TargetPanel(self)

        # 防止在侧边栏宽度较小时被强行压缩导致控件挤压/错位。
        # 外层 QScrollArea 会自动提供水平滚动条。
        self.global_panel.setMinimumWidth(360)
        self.source_panel.setMinimumWidth(360)
        self.target_panel.setMinimumWidth(360)

        # 配置操作按钮
        btn_widget = QWidget(self)
        btn_widget.setFixedHeight(50)
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setSpacing(8)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        # “加载配置”入口已统一移动到文件列表右上角：避免用户在配置编辑器内重复入口。
        # 为保持向后兼容，这里保留 loadRequested 信号，但不再展示加载按钮。
        self.btn_load = None

        self.btn_save = QPushButton("保存配置", btn_widget)
        self.btn_save.setFixedHeight(40)
        try:
            self.btn_save.setObjectName("primaryButton")
            self.btn_save.setToolTip("将当前配置保存到磁盘 (Ctrl+S)")
            self.btn_save.setShortcut("Ctrl+S")
        except Exception:
            pass
        self.btn_save.clicked.connect(self.saveRequested.emit)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addStretch()

        # 创建滚动区域容纳横向布局的面板
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 滚动内容容器
        scroll_content = QWidget()
        coord_layout = QHBoxLayout(scroll_content)
        coord_layout.setSpacing(4)
        coord_layout.setContentsMargins(0, 0, 0, 0)
        coord_layout.addWidget(self.global_panel)
        coord_layout.addWidget(self.source_panel)
        coord_layout.addWidget(self.target_panel)
        coord_layout.setStretch(0, 1)
        coord_layout.setStretch(1, 1)
        coord_layout.setStretch(2, 1)

        scroll_area.setWidget(scroll_content)

        main_layout.addWidget(scroll_area)
        main_layout.addWidget(btn_widget)

        # 绑定面板变更以显示未保存提示并设置 ConfigManager 标志
        try:

            def _on_panel_changed():
                try:
                    win = self.window()
                    # 当前面板数据
                    try:
                        cur_src = self.source_panel.to_variant_payload()
                    except Exception:
                        cur_src = None
                    try:
                        cur_tgt = self.target_panel.to_variant_payload()
                    except Exception:
                        cur_tgt = None

                    # 若有 ConfigManager，尝试与加载时的快照比较，决定是否标记为已修改
                    marked = False
                    if (
                        win is not None
                        and hasattr(win, "config_manager")
                        and win.config_manager is not None
                    ):
                        try:
                            # 优先使用 ConfigManager 在加载时保存的基线快照（若存在），
                            # 否则回退到即时生成的快照。这样可以避免加载后面板与
                            # 管理器内部模型之间的微小差异导致误判。
                            snap = None
                            try:
                                snap = getattr(
                                    win.config_manager, "_loaded_snapshot", None
                                )
                            except Exception:
                                snap = None
                            if snap is None:
                                snap = win.config_manager.get_simple_payload_snapshot()
                        except Exception:
                            snap = None

                        # 规范化为保存时使用的结构进行比较
                        def _make_simple(src, tgt):
                            s_part = (
                                {
                                    "PartName": (src or {}).get("PartName", "Global"),
                                    "Variants": [src],
                                }
                                if src
                                else {"PartName": "Global", "Variants": []}
                            )
                            t_part = (
                                {
                                    "PartName": (tgt or {}).get("PartName", "Target"),
                                    "Variants": [tgt],
                                }
                                if tgt
                                else {"PartName": "Target", "Variants": []}
                            )
                            return {
                                "Source": {"Parts": [s_part]},
                                "Target": {"Parts": [t_part]},
                            }

                        cur_simple = _make_simple(cur_src, cur_tgt)
                        try:
                            if snap is None:
                                # 无加载快照，任何用户操作视为修改
                                marked = True
                            else:
                                # 若与快照一致，则视为未修改，否则为已修改
                                marked = cur_simple != snap
                        except Exception:
                            marked = True

                        try:
                            win.config_manager.set_config_modified(bool(marked))
                        except Exception:
                            pass

                    # UI 层：显示/隐藏未保存提示并启用保存按钮（通过 mark_user_modified）
                    if getattr(self, "lbl_unsaved", None) is not None:
                        try:
                            self.lbl_unsaved.setVisible(bool(marked))
                        except Exception:
                            pass

                    try:
                        # 仅当为用户修改（marked True）时标记为已操作，以启用保存按钮
                        if win is not None and hasattr(win, "mark_user_modified"):
                            if marked:
                                win.mark_user_modified()
                            else:
                                # 清除用户修改标记并刷新状态（优先通过 UIStateManager）
                                try:
                                    if hasattr(win, "ui_state_manager") and getattr(
                                        win, "ui_state_manager"
                                    ):
                                        try:
                                            win.ui_state_manager.clear_user_modified()
                                        except Exception:
                                            pass
                                    else:
                                        win.operation_performed = False
                                        try:
                                            win._refresh_controls_state()
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                    except Exception:
                        pass
                except Exception:
                    logger.debug("处理面板修改回调失败", exc_info=True)

            try:
                self.global_panel.valuesChanged.connect(_on_panel_changed)
            except Exception:
                pass
            try:
                self.source_panel.valuesChanged.connect(_on_panel_changed)
            except Exception:
                pass
            try:
                self.target_panel.valuesChanged.connect(_on_panel_changed)
            except Exception:
                pass
            # 也监听 Part 名称变更（用户直接修改 Part 名应被视为配置修改）
            try:
                self.source_panel.partNameChanged.connect(_on_panel_changed)
            except Exception:
                pass
            try:
                self.target_panel.partNameChanged.connect(_on_panel_changed)
            except Exception:
                pass
        except Exception:
            logger.debug("连接 panel valuesChanged/partNameChanged 失败", exc_info=True)

        # 监听保存完成信号以隐藏未保存提示
        try:
            from gui.signal_bus import SignalBus

            sb = getattr(self.window(), "signal_bus", None) or SignalBus.instance()
            try:
                sb.configSaved.connect(lambda _p=None: self._on_config_saved())
            except Exception:
                pass
        except Exception:
            logger.debug("连接 configSaved 信号失败（非致命）", exc_info=True)

    def _on_config_saved(self) -> None:
        try:
            if getattr(self, "lbl_unsaved", None) is not None:
                self.lbl_unsaved.setVisible(False)
        except Exception:
            pass
