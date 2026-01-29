"""
批处理操作总面板，封装 BatchPanel 并连接主窗口回调。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from .batch_panel import BatchPanel

logger = logging.getLogger(__name__)


class OperationPanel(QWidget):
    """批处理操作面板，将 BatchPanel 与回调绑定并提供旧属性兼容。"""

    def __init__(
        self,
        *,
        parent: Optional[QWidget] = None,
        on_batch_start: Callable[[], None],
        on_browse: Callable[[], None],
        on_select_all: Callable[[], None],
        on_select_none: Callable[[], None],
        on_invert_selection: Callable[[], None],
        on_quick_select: Callable[[], None],
        on_save_project: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        app = QApplication.instance()
        try:
            if app:
                app.blockSignals(True)
        except Exception:
            logger.debug("OperationPanel blockSignals 失败", exc_info=True)

        try:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self.batch_panel = BatchPanel(self)
            layout.addWidget(self.batch_panel)

            # 连接信号到回调
            self.batch_panel.batchStartRequested.connect(on_batch_start)
            self.batch_panel.browseRequested.connect(on_browse)
            self.batch_panel.selectAllRequested.connect(on_select_all)
            self.batch_panel.selectNoneRequested.connect(on_select_none)
            self.batch_panel.invertSelectionRequested.connect(
                on_invert_selection
            )
            self.batch_panel.quickSelectRequested.connect(on_quick_select)
            if on_save_project:
                self.batch_panel.saveProjectRequested.connect(on_save_project)
        finally:
            try:
                if app:
                    app.blockSignals(False)
            except Exception:
                logger.debug(
                    "OperationPanel unblockSignals 失败", exc_info=True
                )

    def attach_legacy_aliases(self, gui_instance: QWidget) -> None:
        """将 BatchPanel 的子控件引用绑定到主窗口以保持兼容。"""
        bp = self.batch_panel
        # 核心控件映射
        gui_instance.batch_panel = bp
        gui_instance.grp_batch = bp
        gui_instance.file_form = bp.file_form
        gui_instance.inp_batch_input = bp.inp_batch_input
        # 按钮已移到菜单栏，设置为None保持兼容性
        gui_instance.btn_browse_input = None
        gui_instance.btn_load_config = None
        gui_instance.btn_batch_in_toolbar = None
        gui_instance.btn_batch = None
        gui_instance.btn_save_project = None
        # 匹配模式控件已移除，设置为None保持兼容性
        gui_instance.inp_pattern = None
        gui_instance.cmb_pattern_preset = None
        gui_instance._pattern_presets = []
        gui_instance.file_list_widget = bp.file_list_widget
        gui_instance.file_tree = bp.file_tree
        gui_instance._file_tree_items = bp._file_tree_items
        gui_instance.progress_bar = bp.progress_bar
        gui_instance.tab_main = bp.tab_main
        gui_instance.config_tab_placeholder = (
            bp.config_tab_placeholder
        )  # 参考系管理Tab占位符
        gui_instance.info_tab_widget = None
        gui_instance.txt_batch_log = bp.txt_batch_log
        # 配置数据格式功能已移除；保持属性为 None 以避免外部直接调用导致错误
        gui_instance.btn_config_format = None
        gui_instance.tab_logs_widget = bp.log_tab
        gui_instance.lbl_format_summary = getattr(
            bp, "lbl_format_summary", None
        )
        gui_instance.lbl_source_part_applied = None


__all__ = ["OperationPanel"]
