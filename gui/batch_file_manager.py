"""批处理文件管理模块

负责批处理文件选择、扫描、列表管理等文件相关操作。
"""

import logging
from pathlib import Path
from typing import List

from PySide6.QtWidgets import QCheckBox, QDialog, QFileDialog, QHBoxLayout

logger = logging.getLogger(__name__)


class BatchFileManager:
    """批处理文件管理器

    负责：
    - 文件/目录浏览选择
    - 文件扫描和列表填充
    - 文件列表 UI 更新
    """

    def __init__(self):
        """初始化文件管理器"""
        self.selected_paths: List[Path] = []

    def browse_batch_input(self, manager_instance):
        """浏览并选择输入文件或目录

        支持一次选择多个文件/目录，会自动扫描并添加所有选择的内容。

        Args:
            manager_instance: BatchManager 实例
        """
        try:
            # 创建非原生对话框，支持文件和目录选择
            dlg = QFileDialog(manager_instance.gui, "选择输入文件或目录")
            dlg.setOption(QFileDialog.DontUseNativeDialog, True)

            # 默认为文件模式
            dlg.setFileMode(QFileDialog.ExistingFiles)

            parts = [
                "所有文件 (*)",
                "所有支持的数据文件 (*.csv *.xlsx *.xls *.mtfmt *.mtdata *.txt *.dat)",
                "Data Files (*.csv *.xlsx *.xls *.mtfmt *.mtdata *.txt *.dat)",
                "CSV Files (*.csv)",
                "Excel Files (*.xlsx *.xls)",
                "MomentConversion (*.mtfmt *.mtdata)",
            ]
            dlg.setNameFilter(";;".join(parts))

            # 添加"选择目录"复选框，允许用户动态切换模式
            mode_box = QCheckBox("选择目录模式")
            mode_box.setChecked(False)

            # 定义模式切换函数
            def toggle_mode(checked):
                if checked:
                    # 切换到目录选择模式
                    dlg.setFileMode(QFileDialog.Directory)
                    dlg.setOption(QFileDialog.ShowDirsOnly, True)
                else:
                    # 切换回文件选择模式
                    dlg.setFileMode(QFileDialog.ExistingFiles)
                    dlg.setOption(QFileDialog.ShowDirsOnly, False)

            # 连接复选框信号
            mode_box.stateChanged.connect(toggle_mode)

            # 获取对话框的主布局，并在底部添加复选框
            main_layout = dlg.layout()
            if main_layout is not None:
                # 创建一个水平布局来放置复选框
                checkbox_layout = QHBoxLayout()
                checkbox_layout.addStretch()  # 左边留空
                checkbox_layout.addWidget(mode_box)
                checkbox_layout.addStretch()  # 右边留空

                # QGridLayout 需要指定行列位置
                # 添加到最后一行的第 0 列，跨越所有列
                row = main_layout.rowCount()
                main_layout.addLayout(checkbox_layout, row, 0, 1, main_layout.columnCount())

            # 用户取消了对话框
            if dlg.exec() != QDialog.Accepted:
                return

            # 获取选择的文件/目录
            selected = dlg.selectedFiles()
            chosen_paths = [Path(p) for p in selected]
            if not chosen_paths:
                return
            first_path = chosen_paths[0]

            if hasattr(manager_instance.gui, "inp_batch_input"):
                # 显示所有选择的路径，便于用户确认处理范围
                if len(chosen_paths) > 1:
                    display_text = "; ".join(str(p) for p in chosen_paths)
                else:
                    display_text = str(first_path)
                manager_instance.gui.inp_batch_input.setText(display_text)
                try:
                    manager_instance.gui.inp_batch_input.setToolTip(display_text)
                except Exception:
                    pass

            # 保存实际选择的路径列表
            self.selected_paths = chosen_paths
            manager_instance._selected_paths = chosen_paths

            # 统一扫描所有选择的文件或目录
            # 对第一个路径进行完整扫描（清空旧数据）
            try:
                manager_instance._scan_and_populate_files(first_path)
            except Exception as e:
                logger.debug("扫描第一个路径失败: %s", e, exc_info=True)

            # 对其他选择的路径进行增量扫描（追加数据）
            for additional_path in chosen_paths[1:]:
                try:
                    manager_instance._scan_and_populate_files(additional_path, clear=False)
                except Exception as e:
                    logger.debug("扫描追加路径 %s 失败: %s", additional_path, e, exc_info=True)

            # 输入路径后自动切换到文件列表页
            self._switch_to_file_list_tab(manager_instance)

        except Exception:
            logger.exception("浏览文件/目录失败")

    def _switch_to_file_list_tab(self, manager_instance):
        """切换到文件列表 Tab"""
        try:
            if hasattr(manager_instance.gui, "tab_main"):
                try:
                    tab = manager_instance.gui.tab_main
                    # 尝试通过文件列表控件查找正确的 Tab 索引
                    idx = -1
                    try:
                        idx = tab.indexOf(getattr(manager_instance.gui, "file_list_widget", None))
                    except Exception:
                        idx = -1

                    if idx is None or idx == -1:
                        # 兜底到第一个可用 Tab
                        idx = 0
                    tab.setCurrentIndex(idx)
                except Exception:
                    # 最后兜底方案：直接切换到第0个Tab
                    try:
                        manager_instance.gui.tab_main.setCurrentIndex(0)
                    except Exception:
                        try:
                            manager_instance.gui.tab_batch.setCurrentIndex(0)
                        except Exception:
                            pass
        except Exception:
            logger.debug("切换到文件列表 Tab 失败", exc_info=True)

    def prepare_file_list_ui(self, manager_instance):
        """准备文件列表界面（设置 workflow step 与状态栏）

        Args:
            manager_instance: BatchManager 实例
        """
        try:
            bp = getattr(manager_instance.gui, "batch_panel", None)
            if bp is not None and hasattr(bp, "set_workflow_step"):
                try:
                    bp.set_workflow_step("step2")
                except (IndexError, KeyError, TypeError, ValueError) as e:
                    logger.debug("处理筛选回退行时出错: %s", e, exc_info=True)
                except Exception:
                    logger.debug("处理筛选回退行时发生未知错误", exc_info=True)
        except Exception:
            try:
                from gui.managers import _report_ui_exception

                _report_ui_exception(manager_instance.gui, "创建浏览对话失败")
            except Exception:
                # 保持向后兼容：若无法展示提示则记录调试信息
                logger.debug("创建浏览对话失败", exc_info=True)
            return None

        try:
            # 使用 SignalBus 统一状态消息显示步骤2
            try:
                from gui.signal_bus import SignalBus

                bus = SignalBus.instance()
                # 使用永久显示（timeout=0）和高优先级，确保步骤提示明显
                bus.statusMessage.emit("📂 步骤2：在文件列表选择数据文件", 0, 2)
            except Exception:
                logger.debug("更新步骤2提示失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("设置永久状态标签文本外层异常（非致命）", exc_info=True)
