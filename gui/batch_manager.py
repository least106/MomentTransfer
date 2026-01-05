"""
批处理管理模块 - 处理批处理相关功能
"""
import logging
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox
from src.format_registry import get_format_for_file

logger = logging.getLogger(__name__)


class BatchManager:
    """批处理管理器 - 管理批处理相关操作"""
    
    def __init__(self, gui_instance):
        """初始化批处理管理器"""
        self.gui = gui_instance
        self.batch_thread = None
    
    def browse_batch_input(self):
        """浏览和选择批处理输入文件或目录"""
        try:
            # 提供 QFileDialog 用于选择文件或目录
            path = QFileDialog.getExistingDirectory(
                self.gui, 
                '选择输入目录（或直接选择文件）',
                '.'
            )
            if not path:
                return
            
            # 扫描并填充文件列表
            self.scan_and_populate_files(Path(path))
        
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
        """运行批处理"""
        try:
            if not hasattr(self.gui, 'calculator') or self.gui.calculator is None:
                QMessageBox.warning(self.gui, '提示', '请先应用配置')
                return
            
            # 获取输出目录
            if hasattr(self.gui, 'inp_batch_output'):
                output_dir = self.gui.inp_batch_output.text() or 'data/output'
            else:
                output_dir = 'data/output'
            
            # 创建输出目录
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # 收集选中的文件
            files_to_process = []
            if hasattr(self.gui, 'scroll_files'):
                layout = self.gui.scroll_files.layout()
                if layout:
                    for i in range(layout.count()):
                        item = layout.itemAt(i)
                        if item and item.widget():
                            widget = item.widget()
                            if hasattr(widget, 'isChecked') and widget.isChecked():
                                if hasattr(widget, 'file_path'):
                                    files_to_process.append(widget.file_path)
            
            if not files_to_process:
                QMessageBox.warning(self.gui, '提示', '请选择至少一个文件')
                return
            
            # 获取数据格式配置
            if hasattr(self.gui, 'data_config'):
                data_config = self.gui.data_config
            else:
                data_config = {'skip_rows': 0, 'columns': {}, 'passthrough': []}
            
            # 启动后台线程
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
                self.batch_thread.progress.connect(self.gui.progressBar.setValue)
            except Exception:
                pass
            
            try:
                self.batch_thread.log_message.connect(self._on_batch_log)
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
            
            # 禁用相关控件
            try:
                self.gui._set_controls_locked(True)
            except Exception:
                pass
            
            # 启动线程
            self.batch_thread.start()
            logger.info(f"开始批处理 {len(files_to_process)} 个文件")
        
        except Exception as e:
            logger.error(f"启动批处理失败: {e}")
            QMessageBox.critical(self.gui, '错误', f'启动失败: {e}')
    
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

