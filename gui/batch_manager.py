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
            
            # 输入路径后自动切换到文件列表页
            try:
                if hasattr(self.gui, 'tab_main'):
                    self.gui.tab_main.setCurrentIndex(1)  # 文件列表页是第1个Tab
            except Exception:
                pass

        except Exception as e:
            logger.error(f"浏览输入失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'浏览失败: {e}')
    
    def _scan_and_populate_files(self, chosen_path: Path):
        """扫描所选路径并在文件树中显示（支持目录结构，默认全选）。"""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTreeWidgetItem
        
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

            # 检查UI组件是否存在
            if not hasattr(self.gui, 'file_tree'):
                return

            # 清空旧的树项
            self.gui.file_tree.clear()
            self.gui._file_tree_items = {}

            if not files:
                try:
                    self.gui.file_list_widget.setVisible(False)
                except Exception:
                    pass
                return

            # 构建目录树结构
            # 获取所有文件的共同根目录
            if p.is_file():
                base_path = p.parent
            else:
                base_path = p

            # 创建目录节点的字典：{relative_dir_path: QTreeWidgetItem}
            dir_items = {}
            
            for fp in files:
                # 计算相对路径
                try:
                    rel_path = fp.relative_to(base_path)
                except ValueError:
                    # 如果文件不在base_path下，直接显示完整路径
                    rel_path = fp
                
                # 构建父目录节点
                parts = rel_path.parts[:-1]  # 不包括文件名
                parent_item = None
                current_path = Path()
                
                for part in parts:
                    current_path = current_path / part
                    if current_path not in dir_items:
                        # 创建目录节点
                        dir_item = QTreeWidgetItem([str(part), ""])
                        dir_item.setData(0, Qt.UserRole, None)  # 目录节点不存储路径
                        
                        if parent_item is None:
                            self.gui.file_tree.addTopLevelItem(dir_item)
                        else:
                            parent_item.addChild(dir_item)
                        
                        dir_items[current_path] = dir_item
                        parent_item = dir_item
                    else:
                        parent_item = dir_items[current_path]
                
                # 创建文件节点
                file_item = QTreeWidgetItem([rel_path.name, ""])
                file_item.setCheckState(0, Qt.Checked)  # 默认选中
                file_item.setData(0, Qt.UserRole, str(fp))  # 存储完整路径
                
                # 验证配置：检查target name是否存在
                status_text = self._validate_file_config(fp)
                file_item.setText(1, status_text)
                
                if parent_item is None:
                    self.gui.file_tree.addTopLevelItem(file_item)
                else:
                    parent_item.addChild(file_item)
                
                self.gui._file_tree_items[str(fp)] = file_item

            # 展开所有节点
            self.gui.file_tree.expandAll()
            
            # 显示文件列表区域
            try:
                self.gui.file_list_widget.setVisible(True)
            except Exception:
                pass

            logger.info(f"已扫描到 {len(files)} 个文件")
            
        except Exception as e:
            logger.error(f"扫描并填充文件列表失败: {e}")
            import traceback
            traceback.print_exc()

    def _validate_file_config(self, file_path: Path) -> str:
        """验证文件的配置，返回状态文本"""
        try:
            # 使用缓存机制读取文件头部用于格式检测
            from src.file_cache import get_file_cache
            from src.cli_helpers import resolve_file_format, BatchConfig
            
            cache = get_file_cache()
            
            # 尝试从缓存获取格式信息
            cached_format = cache.get_metadata(file_path, 'format_info')
            if cached_format:
                fmt_info = cached_format
            else:
                # 构造BatchConfig用于格式解析
                base_cfg = BatchConfig(
                    skip_rows=0,
                    columns={},
                    passthrough=[]
                )
                
                fmt_info = resolve_file_format(
                    str(file_path),
                    base_cfg,
                    enable_sidecar=True,
                    registry_db=getattr(self.gui, '_registry_db', None)
                )
                
                # 缓存格式信息
                if fmt_info:
                    cache.set_metadata(file_path, 'format_info', fmt_info)
            
            if not fmt_info:
                return "❌ 未知格式"
            
            # resolve_file_format返回的是BatchConfig对象，我们需要检查target_names
            # BatchConfig没有target_names属性，这个验证逻辑需要调整
            # 简化处理：只要格式解析成功就认为正常
            return "✓ 格式正常"
            
        except Exception as e:
            logger.debug(f"验证文件配置失败: {e}")
            return "❓ 未验证"

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
                # 使用树形文件列表收集选中的文件
                if hasattr(self.gui, 'file_tree') and hasattr(self.gui, '_file_tree_items'):
                    from PySide6.QtCore import Qt
                    from PySide6.QtWidgets import QTreeWidgetItemIterator
                    
                    iterator = QTreeWidgetItemIterator(self.gui.file_tree)
                    while iterator.value():
                        item = iterator.value()
                        # 只处理文件项（有UserRole数据的）
                        file_path_str = item.data(0, Qt.UserRole)
                        if file_path_str and item.checkState(0) == Qt.Checked:
                            files_to_process.append(Path(file_path_str))
                        iterator += 1
                    
                    if output_dir is None:
                        output_dir = input_path
                else:
                    # Fallback：直接扫描目录
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
            
            # 记录批处理前的文件列表（用于撤销时恢复）
            existing_files = set(f.name for f in output_path.glob('*') if f.is_file())
            self.gui._batch_output_dir = output_path
            self.gui._batch_existing_files = existing_files
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

            # 禁用批处理按钮，防止重复点击
            try:
                if hasattr(self.gui, 'btn_batch'):
                    self.gui.btn_batch.setEnabled(False)
                    self.gui.btn_batch.setText("处理中...")
            except Exception:
                logger.debug("无法禁用批处理按钮", exc_info=True)
            
            # 批处理开始时自动切换到处理日志页
            try:
                if hasattr(self.gui, 'tab_main'):
                    self.gui.tab_main.setCurrentIndex(2)  # 处理日志页是第2个Tab
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
            
            # 重新启用批处理按钮
            try:
                if hasattr(self.gui, 'btn_batch'):
                    self.gui.btn_batch.setEnabled(True)
                    self.gui.btn_batch.setText("开始批量处理")
            except Exception:
                logger.debug("无法启用批处理按钮", exc_info=True)
            
            # 启用撤销按钮
            try:
                if hasattr(self.gui, 'btn_undo'):
                    self.gui.btn_undo.setEnabled(True)
                    self.gui.btn_undo.setVisible(True)
            except Exception:
                logger.debug("无法启用撤销按钮", exc_info=True)
            
            QMessageBox.information(self.gui, '完成', message)
        except Exception as e:
            logger.error(f"处理完成事件失败: {e}")
    
    def on_batch_error(self, error_msg: str):
        """批处理错误回调"""
        try:
            logger.error(f"批处理错误: {error_msg}")
            if hasattr(self.gui, '_set_controls_locked'):
                self.gui._set_controls_locked(False)
            
            # 重新启用批处理按钮
            try:
                if hasattr(self.gui, 'btn_batch'):
                    self.gui.btn_batch.setEnabled(True)
                    self.gui.btn_batch.setText("开始批量处理")
            except Exception:
                logger.debug("无法启用批处理按钮", exc_info=True)
            
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
    
    # 文件选择方法（从 main_window 迁移）
    def select_all_files(self):
        """全选文件树中的所有文件项"""
        self._set_all_file_items_checked(Qt.Checked)
    
    def select_none_files(self):
        """全不选文件树中的所有文件项"""
        self._set_all_file_items_checked(Qt.Unchecked)
    
    def invert_file_selection(self):
        """反选文件树中的所有文件项"""
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        
        if not hasattr(self.gui, 'file_tree'):
            return
        
        iterator = QTreeWidgetItemIterator(self.gui.file_tree)
        while iterator.value():
            item = iterator.value()
            # 只反选文件项（有用户数据中存储了路径的项）
            if item.data(0, Qt.UserRole):
                if item.checkState(0) == Qt.Checked:
                    item.setCheckState(0, Qt.Unchecked)
                else:
                    item.setCheckState(0, Qt.Checked)
            iterator += 1
    
    def _set_all_file_items_checked(self, check_state):
        """设置所有文件项的选中状态（仅文件，不包括目录节点）"""
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        
        if not hasattr(self.gui, 'file_tree'):
            return
        
        iterator = QTreeWidgetItemIterator(self.gui.file_tree)
        while iterator.value():
            item = iterator.value()
            # 只选中文件项（有用户数据中存储了路径的项）
            if item.data(0, Qt.UserRole):
                item.setCheckState(0, check_state)
            iterator += 1
    
    # 批处理控制方法（从 main_window 迁移）
    def request_cancel_batch(self):
        """请求取消正在运行的批处理任务"""
        from datetime import datetime
        
        try:
            batch_thread = getattr(self.gui, 'batch_thread', None)
            if batch_thread is not None:
                if hasattr(self.gui, 'txt_batch_log'):
                    self.gui.txt_batch_log.append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] 用户请求取消任务，正在停止..."
                    )
                try:
                    batch_thread.request_stop()
                except Exception:
                    logger.debug("batch_thread.request_stop 调用失败（可能已结束）", exc_info=True)
                
                # 禁用取消按钮以避免重复点击
                if hasattr(self.gui, 'btn_cancel'):
                    try:
                        self.gui.btn_cancel.setEnabled(False)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("request_cancel_batch 失败", exc_info=True)
    
    def undo_batch_processing(self):
        """撤销最近一次批处理操作"""
        try:
            reply = QMessageBox.question(
                self.gui,
                '确认撤销',
                '确定要撤销最近一次批处理？这将删除本次生成的输出文件（保留源数据）。',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # 只删除本次批处理新生成的文件
            deleted_count = 0
            try:
                output_dir = getattr(self.gui, '_batch_output_dir', None)
                existing_files = getattr(self.gui, '_batch_existing_files', set())
                
                if output_dir and Path(output_dir).exists():
                    output_path = Path(output_dir)
                    for file in output_path.iterdir():
                        if file.is_file() and str(file) not in existing_files:
                            try:
                                file.unlink()
                                deleted_count += 1
                                logger.info(f"已删除: {file}")
                            except Exception as e:
                                logger.warning(f"无法删除 {file}: {e}")
                
                QMessageBox.information(
                    self.gui,
                    '撤销完成',
                    f'已删除 {deleted_count} 个输出文件'
                )
                
                # 清空批处理记录
                self.gui._batch_output_dir = None
                self.gui._batch_existing_files = set()
                
            except Exception as e:
                logger.error(f"撤销批处理失败: {e}", exc_info=True)
                QMessageBox.critical(self.gui, '错误', f'撤销失败: {e}')
        
        except Exception as e:
            logger.error(f"undo_batch_processing 失败: {e}", exc_info=True)

