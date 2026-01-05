"""
批处理管理模块 - 处理批处理相关功能
"""
import logging
from pathlib import Path
import sys
import os
import fnmatch

from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QDialog, QVBoxLayout, 
    QCheckBox, QPushButton, QLabel
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
            dlg.setNameFilter('Data Files (*.csv *.xlsx *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls)')

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

            # 调用 GUI 原有的扫描逻辑，保留复选框面板
            try:
                if hasattr(self.gui, '_scan_and_populate_files'):
                    self.gui._scan_and_populate_files(chosen_path)
                    return
            except Exception:
                logger.debug("调用 _scan_and_populate_files 失败，回退 BatchManager 扫描", exc_info=True)

            # 回退到 BatchManager 自己的扫描逻辑
            self.scan_and_populate_files(chosen_path)

        except Exception as e:
            logger.error(f"浏览输入失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'浏览失败: {e}')
    
    def scan_and_populate_files(self, chosen_path: Path):
        """扫描路径并生成文件列表"""
        try:
            chosen_path = Path(chosen_path)
            
            if chosen_path.is_file():
                # 单个文件
                files = [chosen_path]
            else:
                # 目录 - 递归扫描常见格式文件
                files = []
                for pattern in ['*.csv', '*.xlsx', '*.xls']:
                    files.extend(chosen_path.rglob(pattern))
                files = list(set(files))  # 去重
                files.sort()
            
            if not files:
                QMessageBox.warning(self.gui, '提示', '未找到任何支持的数据文件 (.csv, .xlsx)')
                return
            
            # 更新 GUI 中的文件列表
            if hasattr(self.gui, 'inp_batch_input'):
                self.gui.inp_batch_input.setText(str(chosen_path))
            
            # 清空并填充文件列表（假设有 scroll_files 滚动区域包含复选框）
            if hasattr(self.gui, 'scroll_files'):
                # 清空旧的复选框
                layout = self.gui.scroll_files.layout()
                if layout:
                    while layout.count():
                        item = layout.takeAt(0)
                        if item.widget():
                            item.widget().deleteLater()
                
                # 添加新的复选框（全选）
                from PySide6.QtWidgets import QCheckBox
                for fp in files:
                    chk = QCheckBox(fp.name)
                    chk.setChecked(True)
                    chk.file_path = fp
                    layout.addWidget(chk)
            
            logger.info(f"扫描找到 {len(files)} 个文件")
            QMessageBox.information(self.gui, '成功', f'找到 {len(files)} 个文件')
        
        except Exception as e:
            logger.error(f"扫描文件失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'扫描失败: {e}')
    
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
                    pattern_text = pattern.text() if pattern else '*.csv'
                    for file_path in input_path.rglob('*'):
                        if file_path.is_file() and fnmatch.fnmatch(file_path.name, pattern_text):
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
                registry_db=getattr(self.gui, '_registry_db', None)
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
    
    def determine_format_source(self, file_path: Path) -> str:
        """判断文件格式来源（全局/registry/sidecar）"""
        try:
            # 检查 registry
            if hasattr(self.gui, '_registry_db') and self.gui._registry_db:
                try:
                    result = get_format_for_file(str(file_path), self.gui._registry_db)
                    if result:
                        return 'registry'
                except Exception:
                    pass
            
            # 检查 sidecar
            sidecar_path = Path(str(file_path) + '.format.json')
            if sidecar_path.exists():
                return 'sidecar'
            
            # 默认全局
            return 'global'
        
        except Exception as e:
            logger.debug(f"判断格式来源失败: {e}")
            return 'global'
    
    def format_label_from(self, src: str, src_path=None) -> str:
        """生成格式标签"""
        labels = {
            'global': '（全局设置）',
            'registry': '（Registry）',
            'sidecar': f'（Sidecar: {src_path}）' if src_path else '（Sidecar）'
        }
        return labels.get(src, src)
    
    def refresh_format_labels(self):
        """刷新格式标签 - 更新 UI 中显示的格式来源标签"""
        try:
            if not hasattr(self.gui, 'scroll_files'):
                return
            
            layout = self.gui.scroll_files.layout()
            if not layout:
                return
            
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if hasattr(widget, 'file_path'):
                        src = self.determine_format_source(widget.file_path)
                        label = self.format_label_from(src, widget.file_path)
                        # 在复选框文本后添加来源标签
                        original_text = widget.file_path.name
                        widget.setText(f"{original_text} {label}")
        
        except Exception as e:
            logger.debug(f"刷新格式标签失败: {e}")
    
    def refresh_registry_list(self):
        """刷新 registry 列表"""
        try:
            # 这个方法会从 ExperimentalDialog 调用
            if hasattr(self.gui, '_refresh_registry_list'):
                self.gui._refresh_registry_list()
        except Exception as e:
            logger.debug(f"刷新 registry 列表失败: {e}")

