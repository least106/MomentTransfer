"""批处理管理模块 - 处理批处理相关功能"""

import fnmatch
import logging
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QWidget,
)

from src.format_registry import get_format_for_file

logger = logging.getLogger(__name__)


class BatchManager:
    """批处理管理器 - 管理批处理相关操作"""
    
    def __init__(self, gui_instance):
        """初始化批处理管理器"""
        self.gui = gui_instance
        self.batch_thread = None
    
    def browse_batch_input(self):
        """浏览并选择输入文件或目录，沿用 GUI 原有文件列表面板。"""
        try:
            dlg = QFileDialog(self.gui, '选择输入文件或目录')
            dlg.setOption(QFileDialog.DontUseNativeDialog, True)
            dlg.setFileMode(QFileDialog.ExistingFile)
            dlg.setNameFilter('Data Files (*.csv *.xlsx *.xls *.mtfmt *.mtdata *.txt *.dat);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls);;MomentTransfer (*.mtfmt *.mtdata)')

            # 允许切换目录模式
            from PySide6.QtWidgets import QCheckBox
            chk_dir = QCheckBox('选择目录（切换到目录选择模式）')
            chk_dir.setToolTip('勾选后可以直接选择文件夹；不勾选则选择单个数据文件。')
            try:
                layout = dlg.layout()
                layout.addWidget(chk_dir)
            except Exception:
                pass

            def on_toggle_dir(checked):
                if checked:
                    dlg.setFileMode(QFileDialog.Directory)
                    dlg.setOption(QFileDialog.ShowDirsOnly, True)
                else:
                    dlg.setFileMode(QFileDialog.ExistingFile)
                    dlg.setOption(QFileDialog.ShowDirsOnly, False)

            chk_dir.toggled.connect(on_toggle_dir)

            if dlg.exec() != QDialog.Accepted:
                return

            selected = dlg.selectedFiles()
            if not selected:
                return

            chosen_path = Path(selected[0])
            if hasattr(self.gui, 'inp_batch_input'):
                self.gui.inp_batch_input.setText(str(chosen_path))

            # 统一由 BatchManager 扫描并填充文件列表
            self._scan_and_populate_files(chosen_path)

        except Exception as e:
            logger.error(f"浏览输入失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'浏览失败: {e}')
    
    def _scan_and_populate_files(self, chosen_path: Path):
        """扫描所选路径并在文件列表区域生成复选框列表（默认全选）。"""
        try:
            p = Path(chosen_path)
            files = []

            if p.is_file():
                files = [p]
                try:
                    self.gui.output_dir = p.parent
                except Exception:
                    pass
            elif p.is_dir():
                # 支持分号分隔多模式：*.csv;*.xlsx
                pattern_text = "*.csv"
                try:
                    if hasattr(self.gui, 'inp_pattern') and self.gui.inp_pattern is not None:
                        pt = self.gui.inp_pattern.text().strip()
                        if pt:
                            pattern_text = pt
                except Exception:
                    pass

                patterns = [x.strip() for x in pattern_text.split(';') if x.strip()]
                if not patterns:
                    patterns = ["*.csv"]

                for file_path in p.rglob('*'):
                    if not file_path.is_file():
                        continue
                    if any(fnmatch.fnmatch(file_path.name, pat) for pat in patterns):
                        files.append(file_path)
                files = sorted(set(files))

                try:
                    self.gui.output_dir = p
                except Exception:
                    pass

            # UI 结构要求：create_operation_panel 中的 grp_file_list/file_list_layout_inner/file_scroll
            if not (hasattr(self.gui, 'grp_file_list') and hasattr(self.gui, 'file_list_layout_inner')):
                return

            # 清空旧的复选框及标签
            for i in reversed(range(self.gui.file_list_layout_inner.count())):
                item = self.gui.file_list_layout_inner.itemAt(i)
                if item is None:
                    continue
                w = item.widget()
                if w:
                    w.setParent(None)

            self.gui._file_check_items = []

            if not files:
                try:
                    self.gui.grp_file_list.setVisible(False)
                except Exception:
                    pass
                return

            # 创建复选框并显示格式来源标签
            for fp in files:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(8)

                cb = QCheckBox(fp.name)
                cb.setChecked(True)

                src_label = QLabel("")
                try:
                    src_label.setObjectName('fileSrcLabel')
                    src_label.setProperty('variant', 'muted')
                except Exception:
                    pass
                try:
                    src_label.setFont(QFont('Consolas', 8))
                except Exception:
                    pass

                try:
                    src, src_path = self._determine_format_source(fp)
                    disp, tip, color = self._format_label_from(src, src_path)
                    src_label.setText(disp)
                    src_label.setToolTip(tip or "")
                    try:
                        if color == '#dc3545':
                            src_label.setProperty('variant', 'error')
                        elif color == '#6c757d':
                            src_label.setProperty('variant', 'muted')
                        else:
                            src_label.setProperty('variant', 'normal')
                    except Exception:
                        pass
                except Exception:
                    src_label.setText('未知')
                    try:
                        src_label.setProperty('variant', 'error')
                    except Exception:
                        pass

                row_layout.addWidget(cb)
                row_layout.addStretch()
                try:
                    src_label.setFixedWidth(300)
                    src_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                except Exception:
                    pass
                row_layout.addWidget(src_label)

                self.gui.file_list_layout_inner.addWidget(row)
                self.gui._file_check_items.append((cb, fp, src_label))

            # 根据文件数量自适应高度
            try:
                row_count = len(files)
                row_height = 28
                padding = 36
                min_h = 80
                max_h = 420
                desired = min(max_h, max(min_h, row_count * row_height + padding))
                if hasattr(self.gui, 'file_scroll') and self.gui.file_scroll is not None:
                    self.gui.file_scroll.setFixedHeight(int(desired))
            except Exception:
                try:
                    if hasattr(self.gui, 'file_scroll') and self.gui.file_scroll is not None:
                        self.gui.file_scroll.setMinimumHeight(180)
                except Exception:
                    pass

            try:
                self.gui.grp_file_list.setVisible(True)
            except Exception:
                pass
            try:
                if hasattr(self.gui, 'file_scroll') and self.gui.file_scroll is not None:
                    self.gui.file_scroll.verticalScrollBar().setValue(0)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"扫描文件失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'扫描失败: {e}')

    def _on_pattern_changed(self):
        """当匹配模式改变时，基于当前输入路径重新扫描并刷新文件列表。"""
        try:
            path_text = self.gui.inp_batch_input.text().strip() if hasattr(self.gui, 'inp_batch_input') else ''
            if not path_text:
                return
            chosen = Path(path_text)
            if chosen.exists():
                self._scan_and_populate_files(chosen)
        except Exception:
            logger.debug("_on_pattern_changed 处理失败", exc_info=True)
    
    def run_batch_processing(self):
        """运行批处理（兼容 GUI 原有文件复选框面板与输出目录逻辑）。"""
        try:
            if not hasattr(self.gui, 'calculator') or self.gui.calculator is None:
                QMessageBox.warning(self.gui, '提示', '请先应用配置')
                return

            # 输入路径
            if not hasattr(self.gui, 'inp_batch_input'):
                QMessageBox.warning(self.gui, '提示', '缺少输入路径控件')
                return
            input_path = Path(self.gui.inp_batch_input.text().strip())
            if not input_path.exists():
                QMessageBox.warning(self.gui, '错误', '输入路径不存在')
                return

            files_to_process = []
            output_dir = getattr(self.gui, 'output_dir', None)

            if input_path.is_file():
                files_to_process = [input_path]
                if output_dir is None:
                    output_dir = input_path.parent
            elif input_path.is_dir():
                # 优先使用 GUI 的复选框列表
                if getattr(self.gui, '_file_check_items', None):
                    for item in self.gui._file_check_items:
                        try:
                            cb, fp = item[0], item[1]
                        except Exception:
                            continue
                        if cb.isChecked():
                            files_to_process.append(fp)
                    if output_dir is None:
                        output_dir = input_path
                else:
                    pattern = getattr(self.gui, 'inp_pattern', None)
                    pattern_text = pattern.text().strip() if pattern else '*.csv'
                    patterns = [x.strip() for x in pattern_text.split(';') if x.strip()]
                    if not patterns:
                        patterns = ['*.csv']
                    for file_path in input_path.rglob('*'):
                        if not file_path.is_file():
                            continue
                        if any(fnmatch.fnmatch(file_path.name, pat) for pat in patterns):
                            files_to_process.append(file_path)
                    if output_dir is None:
                        output_dir = input_path
                if not files_to_process:
                    QMessageBox.warning(self.gui, '提示', f"未找到匹配 '{getattr(self.gui, 'inp_pattern', None).text() if hasattr(self.gui, 'inp_pattern') else '*.csv'}' 的文件或未选择任何文件")
                    return
            else:
                QMessageBox.warning(self.gui, '错误', '输入路径无效')
                return

            # 输出目录
            if output_dir is None:
                output_dir = Path('data/output')
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # 数据格式
            data_config = getattr(self.gui, 'data_config', {'skip_rows': 0, 'columns': {}, 'passthrough': []})

            from gui.batch_thread import BatchProcessThread
            self.batch_thread = BatchProcessThread(
                self.gui.calculator,
                files_to_process,
                output_path,
                data_config,
                registry_db=getattr(self.gui, '_registry_db', None),
                project_data=getattr(self.gui, 'current_config', None),
                timestamp_format=getattr(self.gui, 'timestamp_format', "%Y%m%d_%H%M%S")
            )

            # 连接信号
            try:
                self.batch_thread.progress.connect(self.gui.progress_bar.setValue)
            except Exception:
                pass
            try:
                self.batch_thread.log_message.connect(
                    lambda msg: self.gui.txt_batch_log.append(f"[{self._now_str()}] {msg}")
                )
            except Exception:
                pass
            try:
                self.batch_thread.finished.connect(self.on_batch_finished)
            except Exception:
                pass
            try:
                self.batch_thread.error.connect(self.on_batch_error)
            except Exception:
                pass

            try:
                self.gui._set_controls_locked(True)
            except Exception:
                pass

            self.batch_thread.start()
            logger.info(f"开始批处理 {len(files_to_process)} 个文件")
        except Exception as e:
            logger.error(f"启动批处理失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'启动失败: {e}')

    def _now_str(self):
        from datetime import datetime
        return datetime.now().strftime('%H:%M:%S')
    
    def _on_batch_log(self, message: str):
        """批处理日志回调"""
        try:
            if hasattr(self.gui, 'txt_batch_log'):
                self.gui.txt_batch_log.append(message)
        except Exception:
            logger.debug(f"无法更新日志: {message}")
    
    def on_batch_finished(self, message: str):
        """批处理完成回调"""
        try:
            logger.info(f"批处理完成: {message}")
            if hasattr(self.gui, '_set_controls_locked'):
                self.gui._set_controls_locked(False)
            QMessageBox.information(self.gui, '完成', message)
        except Exception as e:
            logger.error(f"处理完成事件失败: {e}")
    
    def on_batch_error(self, error_msg: str):
        """批处理错误回调"""
        try:
            logger.error(f"批处理错误: {error_msg}")
            if hasattr(self.gui, '_set_controls_locked'):
                self.gui._set_controls_locked(False)
            QMessageBox.critical(self.gui, '错误', f'批处理出错: {error_msg}')
        except Exception as e:
            logger.error(f"处理错误事件失败: {e}")
    
    def _determine_format_source(self, fp: Path) -> Tuple[str, Optional[Path]]:
        """快速判断单个文件的格式来源，返回 (label, path_or_None)。

        label: 'registry' | 'sidecar' | 'dir' | 'global' | 'unknown'
        path_or_None: 指向具体的 format 文件（Path）或 None
        说明：当 per-file 覆盖未启用时（默认），直接返回 ('global', None)。
        """
        try:
            # 若 per-file 覆盖未显式启用，则统一视作全局（不检查 registry/sidecar）
            try:
                if hasattr(self.gui, 'experimental_settings'):
                    if not bool(self.gui.experimental_settings.get('enable_sidecar', False)):
                        return ('global', None)
                else:
                    if hasattr(self.gui, 'chk_enable_sidecar') and not self.gui.chk_enable_sidecar.isChecked():
                        return ('global', None)
            except Exception:
                pass

            # 1) registry 优先（若界面提供了 db 路径）
            if hasattr(self.gui, 'inp_registry_db'):
                dbp = self.gui.inp_registry_db.text().strip()
                if dbp:
                    try:
                        fmt = get_format_for_file(dbp, str(fp))
                        if fmt:
                            return ('registry', Path(fmt))
                    except Exception:
                        pass

            # 2) file-sidecar
            for suf in ('.format.json', '.json'):
                cand = fp.parent / f"{fp.stem}{suf}"
                if cand.exists():
                    return ('sidecar', cand)

            # 3) 目录级默认
            dir_cand = fp.parent / 'format.json'
            if dir_cand.exists():
                return ('dir', dir_cand)

            return ('global', None)
        except Exception:
            return ('unknown', None)

    def _format_label_from(self, src: str, src_path: Optional[Path]):
        """将源类型与路径格式化为显示文本、tooltip 与颜色。"""
        try:
            if src == 'registry':
                name = Path(src_path).name if src_path else ''
                return (f"registry ({name})" if name else 'registry', str(src_path) if src_path else '', '#1f77b4')
            if src == 'sidecar':
                name = Path(src_path).name if src_path else ''
                return (f"sidecar ({name})" if name else 'sidecar', str(src_path) if src_path else '', '#28a745')
            if src == 'dir':
                name = Path(src_path).name if src_path else ''
                return (f"dir ({name})" if name else 'dir', str(src_path) if src_path else '', '#ff8c00')
            if src == 'global':
                return ('global', '', '#6c757d')
            return ('unknown', '', '#dc3545')
        except Exception:
            logger.debug('_format_label_from encountered error', exc_info=True)
            return ('unknown', '', '#dc3545')

    def _refresh_format_labels(self):
        """遍历当前文件列表，重新解析并更新每个文件旁的来源标签及 tooltip。"""
        try:
            items = getattr(self.gui, '_file_check_items', None)
            if not items:
                return
            for tup in items:
                if len(tup) == 2:
                    continue
                cb, fp, lbl = tup
                try:
                    src, src_path = self._determine_format_source(fp)
                    disp, tip, color = self._format_label_from(src, src_path)
                    lbl.setText(disp)
                    lbl.setToolTip(tip or '')
                    try:
                        if color == '#dc3545':
                            lbl.setProperty('variant', 'error')
                        elif color == '#6c757d':
                            lbl.setProperty('variant', 'muted')
                        else:
                            lbl.setProperty('variant', 'normal')
                    except Exception:
                        pass
                except Exception:
                    logger.debug('Failed to set label text from format source', exc_info=True)
                    try:
                        lbl.setText('未知')
                        lbl.setToolTip('')
                        try:
                            lbl.setProperty('variant', 'error')
                        except Exception:
                            pass
                    except Exception:
                        pass
        except Exception:
            logger.debug('_refresh_format_labels failed', exc_info=True)

    # 对外提供与 gui.py 同名的委托入口（供 GUI 壳方法调用）
    def on_pattern_changed(self):
        return self._on_pattern_changed()

    def scan_and_populate_files(self, chosen_path: Path):
        return self._scan_and_populate_files(chosen_path)

    def refresh_format_labels(self):
        return self._refresh_format_labels()

