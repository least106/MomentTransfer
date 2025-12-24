import sys

import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import fnmatch
import matplotlib

matplotlib.use('Qt5Agg')

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox, QFormLayout, QFileDialog,
    QTextEdit, QMessageBox, QProgressBar, QSplitter, QCheckBox, QSpinBox,
    QDialog, QDialogButtonBox, QDoubleSpinBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QThread, Signal
from src.physics import AeroCalculator
from src.data_loader import ProjectData


class Mpl3DCanvas(FigureCanvas):
    """3D坐标系可视化画布"""

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111, projection='3d')
        super().__init__(self.fig)
        self.setParent(parent)

    def plot_systems(self, source_orig, source_basis, target_orig, target_basis, moment_center):
        self.axes.clear()

        # 源坐标系（灰色虚线）
        self._draw_frame(source_orig, source_basis, "Source", color=['gray'] * 3, alpha=0.3, linestyle='--')

        # 目标坐标系（彩色实线）
        self._draw_frame(target_orig, target_basis, "Target", color=['r', 'g', 'b'], length=1.5)

        # 力矩中心（紫色点）
        self.axes.scatter(moment_center[0], moment_center[1], moment_center[2],
                          c='m', marker='o', s=80, label='Moment Center', edgecolors='black', linewidths=1)

        # 自动调整显示范围
        all_points = np.array([source_orig, target_orig, moment_center])
        max_range = max(np.ptp(all_points[:, 0]), np.ptp(all_points[:, 1]), np.ptp(all_points[:, 2])) * 0.6
        max_range = max(max_range, 2.0)

        center = np.mean(all_points, axis=0)
        self.axes.set_xlim([center[0] - max_range, center[0] + max_range])
        self.axes.set_ylim([center[1] - max_range, center[1] + max_range])
        self.axes.set_zlim([center[2] - max_range, center[2] + max_range])

        self.axes.set_xlabel('X', fontsize=10, fontweight='bold')
        self.axes.set_ylabel('Y', fontsize=10, fontweight='bold')
        self.axes.set_zlabel('Z', fontsize=10, fontweight='bold')
        self.axes.legend(loc='upper right', fontsize=9)
        self.axes.set_title('Coordinate Systems Visualization', fontsize=11, fontweight='bold')
        self.draw()

    def _draw_frame(self, o, basis, label_prefix, color, length=1.0, alpha=1.0, linestyle='-'):
        labels = ['X', 'Y', 'Z']
        for i in range(3):
            vec = basis[i] * length
            self.axes.quiver(o[0], o[1], o[2],
                             vec[0], vec[1], vec[2],
                             color=color[i], alpha=alpha, arrow_length_ratio=0.15,
                             linewidth=2 if linestyle == '-' else 1,
                             linestyle=linestyle)
            self.axes.text(o[0] + vec[0] * 1.1, o[1] + vec[1] * 1.1, o[2] + vec[2] * 1.1,
                                # 检查预条件
                                if not self.calculator:
                                    QMessageBox.warning(self, "警告", '请先点击"应用配置"按钮!')
                                    return

                                if not self.data_config:
                                    # 使用默认配置代替弹窗询问
                                    self.data_config = {
                                        'skip_rows': 0,
                                        'columns': {'alpha': None, 'fx': 0, 'fy': 1, 'fz': 2, 'mx': 3, 'my': 4, 'mz': 5},
                                        'passthrough': []
                                    }

                                # 根据当前输入路径和模式扫描（如果尚未扫描，先进行扫描并展示）
                                scanned = self.scan_input_path()
                                if not scanned:
                                    QMessageBox.warning(self, "警告", "未找到要处理的文件，请检查输入路径和匹配模式")
                                    return

                                # 收集被选中的文件
                                files_to_process = []
                                for cb, path in getattr(self, 'file_checkboxes', []):
                                    if cb.isChecked():
                                        files_to_process.append(path)

                                if not files_to_process:
                                    QMessageBox.warning(self, "警告", "未选中任何要处理的文件")
                                    return

                                # 输出目录默认取第一个文件的父目录（与之前行为一致）
                                output_dir = files_to_process[0].parent

                                # 开始处理（不额外弹窗）
                                self.progress_bar.setVisible(True)
                                self.progress_bar.setValue(0)
                                self.txt_batch_log.clear()
                                self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 开始批量处理...")
                                self.txt_batch_log.append(f"共 {len(files_to_process)} 个文件")

                                self.batch_thread = BatchProcessThread(
                                    self.calculator, files_to_process, output_dir, self.data_config
                                )
                                self.batch_thread.progress.connect(self.progress_bar.setValue)
                                self.batch_thread.log_message.connect(
                                    lambda msg: self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"))
                                self.batch_thread.finished.connect(self.on_batch_finished)
                                self.batch_thread.error.connect(self.on_batch_error)
                                self.batch_thread.start()
        layout.addWidget(grp_columns)
        layout.addWidget(grp_pass)
        layout.addWidget(btn_box)
    
    def get_config(self):
        """获取配置"""
        passthrough = []
        if self.txt_passthrough.text().strip():
            try:
                passthrough = [int(x.strip()) for x in self.txt_passthrough.text().split(',')]
            except ValueError:
                QMessageBox.warning(
                    self,
                    "无效的列索引",
                    "透传列索引解析失败，请使用逗号分隔的整数，例如：0, 3, 5。\n"
                    "当前输入将被忽略。"
                )
                passthrough = []
        
        return {
            'skip_rows': self.spin_skip_rows.value(),
            'columns': {
                'alpha': self.col_alpha.value() if self.col_alpha.value() >= 0 else None,
                'fx': self.col_fx.value(),
                'fy': self.col_fy.value(),
                'fz': self.col_fz.value(),
                'mx': self.col_mx.value(),
                'my': self.col_my.value(),
                'mz': self.col_mz.value()
            },
            'passthrough': passthrough
        }


class BatchProcessThread(QThread):
    """批处理后台线程"""
    progress = Signal(int)
    log_message = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, calculator, file_list, output_dir, data_config):
        super().__init__()
        self.calculator = calculator
        self.file_list = file_list
        self.output_dir = Path(output_dir)
        self.data_config = data_config

    def process_file(self, file_path):
        """处理单个文件"""
        # 读取数据
        if str(file_path).endswith('.csv'):
            df = pd.read_csv(file_path, header=None, skiprows=self.data_config['skip_rows'])
        else:
            df = pd.read_excel(file_path, header=None, skiprows=self.data_config['skip_rows'])
        
        cols = self.data_config['columns']

        # 提取力和力矩（逐列转换为数值以防原始 CSV 为字符串）
        def _col_to_numeric(df, col_idx, name):
            if col_idx is None:
                raise ValueError(f"缺失必需的列映射: {name}")
            if not (0 <= col_idx < len(df.columns)):
                raise IndexError(f"列索引越界: {name} -> {col_idx}")
            ser = pd.to_numeric(df.iloc[:, col_idx], errors='coerce')
            if ser.isna().any():
                try:
                    self.log_message.emit(f"列 {name} 存在无法解析为数值的项，已将其设为 NaN。")
                except Exception:
                    pass
            return ser.values.astype(float)

        try:
            fx = _col_to_numeric(df, cols['fx'], 'Fx')
            fy = _col_to_numeric(df, cols['fy'], 'Fy')
            fz = _col_to_numeric(df, cols['fz'], 'Fz')

            mx = _col_to_numeric(df, cols['mx'], 'Mx')
            my = _col_to_numeric(df, cols['my'], 'My')
            mz = _col_to_numeric(df, cols['mz'], 'Mz')

            forces = np.vstack([fx, fy, fz]).T
            moments = np.vstack([mx, my, mz]).T
        except Exception as e:
            try:
                self.log_message.emit(f"数据列提取或转换失败: {e}")
            except Exception:
                pass
            raise
        
        # 计算
        results = self.calculator.process_batch(forces, moments)
        
        # 构建输出
        output_df = pd.DataFrame()
        
        # 保留列 - 校验索引类型与范围，避免负数或越界导致异常
        for col_idx in self.data_config.get('passthrough', []):
            try:
                idx = int(col_idx)
            except Exception:
                # 记录无效的索引并跳过
                try:
                    self.log_message.emit(f"透传列索引无效（非整数）：{col_idx}")
                except Exception:
                    pass
                continue

            if 0 <= idx < len(df.columns):
                output_df[f'Col_{idx}'] = df.iloc[:, idx]
            else:
                try:
                    self.log_message.emit(f"透传列索引越界: {idx}")
                except Exception:
                    pass
        
        # 迎角
        if cols['alpha'] is not None and cols['alpha'] < len(df.columns):
            output_df['Alpha'] = df.iloc[:, cols['alpha']]
        
        # 结果
        output_df['Fx_new'] = results['force_transformed'][:, 0]
        output_df['Fy_new'] = results['force_transformed'][:, 1]
        output_df['Fz_new'] = results['force_transformed'][:, 2]
        output_df['Mx_new'] = results['moment_transformed'][:, 0]
        output_df['My_new'] = results['moment_transformed'][:, 1]
        output_df['Mz_new'] = results['moment_transformed'][:, 2]
        output_df['Cx'] = results['coeff_force'][:, 0]
        output_df['Cy'] = results['coeff_force'][:, 1]
        output_df['Cz'] = results['coeff_force'][:, 2]
        output_df['Cl'] = results['coeff_moment'][:, 0]
        output_df['Cm'] = results['coeff_moment'][:, 1]
        output_df['Cn'] = results['coeff_moment'][:, 2]
        
        # 保存
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f"{file_path.stem}_result_{timestamp}.csv"
        output_df.to_csv(output_file, index=False)
        
        return output_file

    def run(self):
        try:
            total = len(self.file_list)
            success = 0
            
            for i, file_path in enumerate(self.file_list):
                self.log_message.emit(f"处理 [{i+1}/{total}]: {file_path.name}")
                
                try:
                    output_file = self.process_file(file_path)
                    self.log_message.emit(f"  ✓ 完成: {output_file.name}")
                    success += 1
                except Exception as e:
                    self.log_message.emit(f"  ✗ 失败: {str(e)}")
                
                self.progress.emit(int((i + 1) / total * 100))
            
            self.finished.emit(f"成功处理 {success}/{total} 个文件")
            
        except Exception as e:
            self.error.emit(str(e))


class IntegratedAeroGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MomentTransfer v2.0 - 气动载荷坐标变换工具")
        self.resize(1400, 850)

        self.calculator = None
        self.current_config = None
        self.data_config = None
        self.canvas3d = None
        self.visualization_window = None

        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.create_config_panel())
        splitter.addWidget(self.create_operation_panel())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)

        main_layout.addWidget(splitter)
        self.statusBar().showMessage("就绪 - 请加载或创建配置")

    def create_config_panel(self):
        """创建左侧配置编辑面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        # 标题与可视化按钮
        header_layout = QHBoxLayout()
        title = QLabel("配置编辑器")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")

        btn_visualize = QPushButton("3D可视化")
        btn_visualize.setMaximumWidth(120)
        btn_visualize.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold;")
        btn_visualize.setToolTip("打开3D坐标系可视化窗口")
        btn_visualize.clicked.connect(self.toggle_visualization)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(btn_visualize)

        layout.addLayout(header_layout)

        # === Source 坐标系（可折叠） ===
        self.chk_show_source = QCheckBox("显示 Source 坐标系设置")
        self.chk_show_source.setStyleSheet("font-weight: bold; color: #0078d7;")
        self.chk_show_source.stateChanged.connect(self.toggle_source_visibility)
        layout.addWidget(self.chk_show_source)

        self.grp_source = QGroupBox("Source Coordinate System")
        self.grp_source.setStyleSheet("QGroupBox { font-weight: bold; }")
        form_source = QFormLayout()

        self.src_ox = self._create_input("0.0")
        self.src_oy = self._create_input("0.0")
        self.src_oz = self._create_input("0.0")

        # Source Part Name（与 Target 对等）
        self.src_part_name = self._create_input("Global")

        self.src_xx = self._create_input("1.0")
        self.src_xy = self._create_input("0.0")
        self.src_xz = self._create_input("0.0")

        self.src_yx = self._create_input("0.0")
        self.src_yy = self._create_input("1.0")
        self.src_yz = self._create_input("0.0")

        self.src_zx = self._create_input("0.0")
        self.src_zy = self._create_input("0.0")
        self.src_zz = self._create_input("1.0")

        # Source 力矩中心
        self.src_mcx = self._create_input("0.0")
        self.src_mcy = self._create_input("0.0")
        self.src_mcz = self._create_input("0.0")

        form_source.addRow("Part Name:", self.src_part_name)
        form_source.addRow("Orig:", self._create_vector_row(self.src_ox, self.src_oy, self.src_oz))
        form_source.addRow("X:", self._create_vector_row(self.src_xx, self.src_xy, self.src_xz))
        form_source.addRow("Y:", self._create_vector_row(self.src_yx, self.src_yy, self.src_yz))
        form_source.addRow("Z:", self._create_vector_row(self.src_zx, self.src_zy, self.src_zz))

        # Source 参考量（与 Target 对等）
        self.src_cref = self._create_input("1.0")
        self.src_bref = self._create_input("1.0")
        self.src_sref = self._create_input("10.0")
        self.src_q = self._create_input("1000.0")

        form_source.addRow("Moment Center:", self._create_vector_row(self.src_mcx, self.src_mcy, self.src_mcz))
        form_source.addRow("C_ref (m):", self.src_cref)
        form_source.addRow("B_ref (m):", self.src_bref)
        form_source.addRow("S_ref (m²):", self.src_sref)
        form_source.addRow("Q (Pa):", self.src_q)

        self.grp_source.setLayout(form_source)
        self.grp_source.setVisible(False)
        layout.addWidget(self.grp_source)

        # === Target 配置 ===
        grp_target = QGroupBox("Target Configuration")
        grp_target.setStyleSheet("QGroupBox { font-weight: bold; }")
        form_target = QFormLayout()

        # Part Name
        self.tgt_part_name = QLineEdit("TestModel")
        form_target.addRow("Part Name:", self.tgt_part_name)

        # Target 坐标系
        self.tgt_ox = self._create_input("0.0")
        self.tgt_oy = self._create_input("0.0")
        self.tgt_oz = self._create_input("0.0")

        self.tgt_xx = self._create_input("1.0")
        self.tgt_xy = self._create_input("0.0")
        self.tgt_xz = self._create_input("0.0")

        self.tgt_yx = self._create_input("0.0")
        self.tgt_yy = self._create_input("1.0")
        self.tgt_yz = self._create_input("0.0")

        self.tgt_zx = self._create_input("0.0")
        self.tgt_zy = self._create_input("0.0")
        self.tgt_zz = self._create_input("1.0")

        form_target.addRow("Orig:", self._create_vector_row(self.tgt_ox, self.tgt_oy, self.tgt_oz))
        form_target.addRow("X:", self._create_vector_row(self.tgt_xx, self.tgt_xy, self.tgt_xz))
        form_target.addRow("Y:", self._create_vector_row(self.tgt_yx, self.tgt_yy, self.tgt_yz))
        form_target.addRow("Z:", self._create_vector_row(self.tgt_zx, self.tgt_zy, self.tgt_zz))

        # Moment Center
        self.tgt_mcx = self._create_input("0.5")
        self.tgt_mcy = self._create_input("0.0")
        self.tgt_mcz = self._create_input("0.0")
        form_target.addRow("Moment Center:", self._create_vector_row(self.tgt_mcx, self.tgt_mcy, self.tgt_mcz))

        # Target 参考量（与 Source 对等）
        self.tgt_cref = self._create_input("1.0")
        self.tgt_bref = self._create_input("1.0")
        self.tgt_sref = self._create_input("10.0")
        self.tgt_q = self._create_input("1000.0")

        form_target.addRow("C_ref (m):", self.tgt_cref)
        form_target.addRow("B_ref (m):", self.tgt_bref)
        form_target.addRow("S_ref (m²):", self.tgt_sref)
        form_target.addRow("Q (Pa):", self.tgt_q)
        grp_target.setLayout(form_target)

        # === 配置操作按钮 ===
        btn_layout = QHBoxLayout()

        btn_load = QPushButton("加载配置")
        btn_load.clicked.connect(self.load_config)

        btn_save = QPushButton("保存配置")
        btn_save.clicked.connect(self.save_config)

        btn_apply = QPushButton("应用配置")
        btn_apply.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold;")
        btn_apply.clicked.connect(self.apply_config)

        btn_layout.addWidget(btn_load)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_apply)

        # 添加到主布局
        layout.addWidget(grp_target)
        # layout.addWidget(grp_global)  # 删除未定义的grp_global，避免报错
        layout.addLayout(btn_layout)
        layout.addStretch()

        return panel

    def create_operation_panel(self):
        """创建右侧操作面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(15)

        # === 配置状态显示 ===
        status_group = QGroupBox("当前配置状态")
        status_layout = QHBoxLayout()
        self.lbl_status = QLabel("未加载配置")
        self.lbl_status.setStyleSheet("color: red; font-weight: bold; font-size: 13px;")
        status_layout.addWidget(self.lbl_status)
        status_layout.addStretch()
        status_group.setLayout(status_layout)

        # === 批量处理区 ===
        grp_batch = QGroupBox("批量处理 (Batch Processing)")
        grp_batch.setStyleSheet("QGroupBox { font-weight: bold; }")
        layout_batch = QVBoxLayout()

        # 文件选择
        file_form = QFormLayout()

        input_row = QHBoxLayout()
        self.inp_batch_input = QLineEdit()
        self.inp_batch_input.setPlaceholderText("选择文件或目录...")

        # 提供两个明确的按钮，避免弹窗询问文件/目录类型
        btn_browse_file = QPushButton("选择文件")
        btn_browse_file.setMaximumWidth(100)
        btn_browse_file.clicked.connect(self.browse_batch_file)

        btn_browse_dir = QPushButton("选择目录")
        btn_browse_dir.setMaximumWidth(100)
        btn_browse_dir.clicked.connect(self.browse_batch_dir)

        input_row.addWidget(self.inp_batch_input)
        input_row.addWidget(btn_browse_file)
        input_row.addWidget(btn_browse_dir)

        # 文件匹配模式
        pattern_row = QHBoxLayout()
        self.inp_pattern = QLineEdit("*.csv")
        self.inp_pattern.setToolTip("文件名匹配模式，如 *.csv, data_*.xlsx")
        pattern_row.addWidget(QLabel("匹配模式:"))
        pattern_row.addWidget(self.inp_pattern)

        file_form.addRow("输入路径:", input_row)
        file_form.addRow("", pattern_row)

        # 文件列表（可滚动，多文件复选框）
        self.grp_file_list = QGroupBox("文件列表")
        file_list_layout = QVBoxLayout()
        self.file_list_container = QWidget()
        self.file_list_vbox = QVBoxLayout(self.file_list_container)
        self.file_list_vbox.setContentsMargins(2, 2, 2, 2)
        self.file_list_vbox.addStretch()

        self.scr_file_list = QScrollArea()
        self.scr_file_list.setWidgetResizable(True)
        self.scr_file_list.setWidget(self.file_list_container)
        file_list_layout.addWidget(self.scr_file_list)
        self.grp_file_list.setLayout(file_list_layout)

        # 数据格式配置按钮
        btn_config_format = QPushButton("⚙ 配置数据格式")
        btn_config_format.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        btn_config_format.setToolTip("设置跳过行数、列映射等")
        btn_config_format.clicked.connect(self.configure_data_format)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        # 执行按钮
        btn_batch = QPushButton("开始批量处理")
        btn_batch.setMinimumHeight(40)
        btn_batch.setStyleSheet("background-color: #ff6b6b; color: white; font-weight: bold;")
        btn_batch.clicked.connect(self.run_batch_processing)

        # 日志
        self.txt_batch_log = QTextEdit()
        self.txt_batch_log.setReadOnly(True)
        self.txt_batch_log.setFont(QFont("Consolas", 9))
        self.txt_batch_log.setMaximumHeight(300)

        layout_batch.addLayout(file_form)
        layout_batch.addWidget(self.grp_file_list)
        layout_batch.addWidget(btn_config_format)
        layout_batch.addWidget(self.progress_bar)
        layout_batch.addWidget(btn_batch)
        layout_batch.addWidget(QLabel("处理日志:"))
        layout_batch.addWidget(self.txt_batch_log)

        grp_batch.setLayout(layout_batch)

        layout.addWidget(status_group)
        layout.addWidget(grp_batch)
        layout.addStretch()

        return panel

    def _create_input(self, default_value):
        """创建输入框"""
        inp = QLineEdit(default_value)
        inp.setMaximumWidth(80)
        return inp

    def _create_vector_row(self, inp1, inp2, inp3):
        """创建向量输入行 [x, y, z]"""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        layout.addWidget(QLabel("["))
        layout.addWidget(inp1)
        layout.addWidget(QLabel(","))
        layout.addWidget(inp2)
        layout.addWidget(QLabel(","))
        layout.addWidget(inp3)
        layout.addWidget(QLabel("]"))
        layout.addStretch()

        return row

    def toggle_source_visibility(self, state):
        """切换 Source 坐标系的显示/隐藏"""
        self.grp_source.setVisible(state == Qt.Checked)

    def toggle_visualization(self):
        """切换3D可视化窗口"""
        if self.visualization_window is None or not self.visualization_window.isVisible():
            self.show_visualization()
        else:
            self.visualization_window.close()
            self.visualization_window = None

    def show_visualization(self):
        """显示3D可视化窗口"""
        try:
            # 读取当前配置
            source_orig = [float(self.src_ox.text()), float(self.src_oy.text()), float(self.src_oz.text())]
            source_basis = np.array([
                [float(self.src_xx.text()), float(self.src_xy.text()), float(self.src_xz.text())],
                [float(self.src_yx.text()), float(self.src_yy.text()), float(self.src_yz.text())],
                [float(self.src_zx.text()), float(self.src_zy.text()), float(self.src_zz.text())]
            ])

            target_orig = [float(self.tgt_ox.text()), float(self.tgt_oy.text()), float(self.tgt_oz.text())]
            target_basis = np.array([
                [float(self.tgt_xx.text()), float(self.tgt_xy.text()), float(self.tgt_xz.text())],
                [float(self.tgt_yx.text()), float(self.tgt_yy.text()), float(self.tgt_yz.text())],
                [float(self.tgt_zx.text()), float(self.tgt_zy.text()), float(self.tgt_zz.text())]
            ])

            moment_center = [float(self.tgt_mcx.text()), float(self.tgt_mcy.text()), float(self.tgt_mcz.text())]

            # 创建可视化窗口
            self.visualization_window = QWidget()
            self.visualization_window.setWindowTitle(f"3D坐标系可视化 - {self.tgt_part_name.text()}")
            self.visualization_window.resize(800, 600)

            layout = QVBoxLayout(self.visualization_window)

            # 创建3D画布
            self.canvas3d = Mpl3DCanvas(self.visualization_window, width=8, height=6, dpi=100)
            self.canvas3d.plot_systems(source_orig, source_basis, target_orig, target_basis, moment_center)

            # 添加说明文本
            info_label = QLabel(
                "灰色虚线: Source坐标系 | 彩色实线: Target坐标系 | 紫色点: 力矩中心\n"
                "提示: 可以使用鼠标拖动旋转视角"
            )
            info_label.setStyleSheet("background-color: #f0f0f0; padding: 8px; border-radius: 4px; font-size: 10px;")

            layout.addWidget(info_label)
            layout.addWidget(self.canvas3d)

            self.visualization_window.show()

        except ValueError as e:
            QMessageBox.warning(self, "输入错误", f"请检查坐标系数值输入:\n{str(e)}")

    def load_config(self):
        """加载配置文件"""
        fname, _ = QFileDialog.getOpenFileName(self, '打开配置', '.', 'JSON Files (*.json)')
        if not fname:
            return

        try:
            with open(fname, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 填充 Source（兼容旧/新格式）
            src_section = data.get('Source')
            if src_section and 'CoordSystem' in src_section:
                src = src_section['CoordSystem']
                part_name = src_section.get('PartName', 'Global')
            else:
                # 兼容旧版仅包含 SourceCoordSystem 的情况
                src = data.get('SourceCoordSystem')
                part_name = 'Global'

            if src:
                if hasattr(self, 'src_part_name'):
                    self.src_part_name.setText(str(part_name))

                self.src_ox.setText(str(src['Orig'][0]))
                self.src_oy.setText(str(src['Orig'][1]))
                self.src_oz.setText(str(src['Orig'][2]))

                self.src_xx.setText(str(src['X'][0]))
                self.src_xy.setText(str(src['X'][1]))
                self.src_xz.setText(str(src['X'][2]))

                self.src_yx.setText(str(src['Y'][0]))
                self.src_yy.setText(str(src['Y'][1]))
                self.src_yz.setText(str(src['Y'][2]))

                self.src_zx.setText(str(src['Z'][0]))
                self.src_zy.setText(str(src['Z'][1]))
                self.src_zz.setText(str(src['Z'][2]))
                # Source 的力矩中心与参考量（若存在），稳健解析并容错
                mc_src = None
                if src_section and isinstance(src_section, dict):
                    try:
                        mc_src = src_section.get('SourceMomentCenter') or src_section.get('MomentCenter')
                    except (IndexError, TypeError, ValueError):
                        mc_src = None

                if mc_src and hasattr(self, 'src_mcx'):
                    try:
                        self.src_mcx.setText(str(mc_src[0]))
                        self.src_mcy.setText(str(mc_src[1]))
                        self.src_mcz.setText(str(mc_src[2]))
                    except Exception:
                        # 格式异常则跳过，不中断加载流程
                        pass

                if hasattr(self, 'src_cref') and src_section and isinstance(src_section, dict):
                    # 使用 get 并提供默认值以防缺失
                    self.src_cref.setText(str(src_section.get('Cref', 1.0)))
                    self.src_bref.setText(str(src_section.get('Bref', 1.0)))
                    self.src_sref.setText(str(src_section.get('S', 10.0)))
                    self.src_q.setText(str(src_section.get('Q', 1000.0)))

            # 填充 Target
            tgt = data['Target']
            self.tgt_part_name.setText(tgt['PartName'])

            tgt_coord = tgt.get('TargetCoordSystem') or tgt.get('CoordSystem')
            self.tgt_ox.setText(str(tgt_coord['Orig'][0]))
            self.tgt_oy.setText(str(tgt_coord['Orig'][1]))
            self.tgt_oz.setText(str(tgt_coord['Orig'][2]))

            self.tgt_xx.setText(str(tgt_coord['X'][0]))
            self.tgt_xy.setText(str(tgt_coord['X'][1]))
            self.tgt_xz.setText(str(tgt_coord['X'][2]))

            self.tgt_yx.setText(str(tgt_coord['Y'][0]))
            self.tgt_yy.setText(str(tgt_coord['Y'][1]))
            self.tgt_yz.setText(str(tgt_coord['Y'][2]))

            self.tgt_zx.setText(str(tgt_coord['Z'][0]))
            self.tgt_zy.setText(str(tgt_coord['Z'][1]))
            self.tgt_zz.setText(str(tgt_coord['Z'][2]))

            mc = tgt.get('TargetMomentCenter') or tgt.get('MomentCenter')
            self.tgt_mcx.setText(str(mc[0]))
            self.tgt_mcy.setText(str(mc[1]))
            self.tgt_mcz.setText(str(mc[2]))

            # Target 的参考量
            if hasattr(self, 'tgt_cref'):
                self.tgt_cref.setText(str(tgt.get('Cref', 1.0)))
                self.tgt_bref.setText(str(tgt.get('Bref', 1.0)))
                self.tgt_sref.setText(str(tgt.get('S', 10.0)))
                self.tgt_q.setText(str(tgt.get('Q', 1000.0)))

            QMessageBox.information(self, "成功", f"配置已加载:\n{fname}")
            self.statusBar().showMessage(f"已加载: {fname}")

            # 自动应用
            self.apply_config()

        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法加载配置文件:\n{str(e)}")

    def save_config(self):
        """保存配置到JSON"""
        try:
            # 保存为对等的 Source / Target 配置，便于在 GUI 中保持一致性
            data = {
                "Source": {
                    "PartName": self.src_part_name.text() if hasattr(self, 'src_part_name') else "Global",
                    "CoordSystem": {
                        "Orig": [float(self.src_ox.text()), float(self.src_oy.text()), float(self.src_oz.text())],
                        "X": [float(self.src_xx.text()), float(self.src_xy.text()), float(self.src_xz.text())],
                        "Y": [float(self.src_yx.text()), float(self.src_yy.text()), float(self.src_yz.text())],
                        "Z": [float(self.src_zx.text()), float(self.src_zy.text()), float(self.src_zz.text())]
                    },
                    "SourceMomentCenter": [float(self.src_mcx.text()), float(self.src_mcy.text()), float(self.src_mcz.text())],
                    "Cref": float(self.src_cref.text()) if hasattr(self, 'src_cref') else 1.0,
                    "Bref": float(self.src_bref.text()) if hasattr(self, 'src_bref') else 1.0,
                    "Q": float(self.src_q.text()) if hasattr(self, 'src_q') else 1000.0,
                    "S": float(self.src_sref.text()) if hasattr(self, 'src_sref') else 10.0
                },
                "Target": {
                    "PartName": self.tgt_part_name.text(),
                    "CoordSystem": {
                        "Orig": [float(self.tgt_ox.text()), float(self.tgt_oy.text()), float(self.tgt_oz.text())],
                        "X": [float(self.tgt_xx.text()), float(self.tgt_xy.text()), float(self.tgt_xz.text())],
                        "Y": [float(self.tgt_yx.text()), float(self.tgt_yy.text()), float(self.tgt_yz.text())],
                        "Z": [float(self.tgt_zx.text()), float(self.tgt_zy.text()), float(self.tgt_zz.text())]
                    },
                    "TargetMomentCenter": [float(self.tgt_mcx.text()), float(self.tgt_mcy.text()), float(self.tgt_mcz.text())],
                    "Cref": float(self.tgt_cref.text()) if hasattr(self, 'tgt_cref') else 1.0,
                    "Bref": float(self.tgt_bref.text()) if hasattr(self, 'tgt_bref') else 1.0,
                    "Q": float(self.tgt_q.text()) if hasattr(self, 'tgt_q') else 1000.0,
                    "S": float(self.tgt_sref.text()) if hasattr(self, 'tgt_sref') else 10.0
                }
            }

            fname, _ = QFileDialog.getSaveFileName(self, '保存配置', 'config.json', 'JSON Files (*.json)')
            if fname:
                with open(fname, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                QMessageBox.information(self, "成功", f"配置已保存:\n{fname}")
                self.statusBar().showMessage(f"已保存: {fname}")

        except ValueError as e:
            QMessageBox.warning(self, "输入错误", f"请检查数值输入是否正确:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def apply_config(self):
        """应用当前配置到计算器"""
        try:
            # 使用对等结构构建配置，方便 ProjectData.from_dict 解析
            data = {
                "Source": {
                    "PartName": self.src_part_name.text() if hasattr(self, 'src_part_name') else "Global",
                    "CoordSystem": {
                        "Orig": [float(self.src_ox.text()), float(self.src_oy.text()), float(self.src_oz.text())],
                        "X": [float(self.src_xx.text()), float(self.src_xy.text()), float(self.src_xz.text())],
                        "Y": [float(self.src_yx.text()), float(self.src_yy.text()), float(self.src_yz.text())],
                        "Z": [float(self.src_zx.text()), float(self.src_zy.text()), float(self.src_zz.text())]
                    }
                    ,
                    "SourceMomentCenter": [float(self.src_mcx.text()), float(self.src_mcy.text()), float(self.src_mcz.text())],
                    "Cref": float(self.src_cref.text()) if hasattr(self, 'src_cref') else 1.0,
                    "Bref": float(self.src_bref.text()) if hasattr(self, 'src_bref') else 1.0,
                    "Q": float(self.src_q.text()) if hasattr(self, 'src_q') else 1000.0,
                    "S": float(self.src_sref.text()) if hasattr(self, 'src_sref') else 10.0
                },
                "Target": {
                    "PartName": self.tgt_part_name.text(),
                    "CoordSystem": {
                        "Orig": [float(self.tgt_ox.text()), float(self.tgt_oy.text()), float(self.tgt_oz.text())],
                        "X": [float(self.tgt_xx.text()), float(self.tgt_xy.text()), float(self.tgt_xz.text())],
                        "Y": [float(self.tgt_yx.text()), float(self.tgt_yy.text()), float(self.tgt_yz.text())],
                        "Z": [float(self.tgt_zx.text()), float(self.tgt_zy.text()), float(self.tgt_zz.text())]
                    },
                    "TargetMomentCenter": [float(self.tgt_mcx.text()), float(self.tgt_mcy.text()), float(self.tgt_mcz.text())],
                    "Cref": float(self.tgt_cref.text()) if hasattr(self, 'tgt_cref') else 1.0,
                    "Bref": float(self.tgt_bref.text()) if hasattr(self, 'tgt_bref') else 1.0,
                    "Q": float(self.tgt_q.text()) if hasattr(self, 'tgt_q') else 1000.0,
                    "S": float(self.tgt_sref.text()) if hasattr(self, 'tgt_sref') else 10.0
                }
            }

            self.current_config = ProjectData.from_dict(data)
            self.calculator = AeroCalculator(self.current_config)

            part_name = self.tgt_part_name.text()
            self.lbl_status.setText(f"已加载配置: {part_name}")
            self.lbl_status.setStyleSheet("color: green; font-weight: bold; font-size: 13px;")
            self.statusBar().showMessage(f"配置已应用: {part_name}")

            QMessageBox.information(self, "成功", f"配置已应用!\n组件: {part_name}\n现在可以进行计算了。")

        except ValueError as e:
            QMessageBox.warning(self, "输入错误", f"请检查数值输入:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "应用失败", f"配置应用失败:\n{str(e)}")

    def configure_data_format(self):
        """配置数据格式"""
        dialog = ColumnMappingDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.data_config = dialog.get_config()
            QMessageBox.information(self, "成功", 
                f"数据格式配置已保存:\n"
                f"- 跳过 {self.data_config['skip_rows']} 行\n"
                f"- Fx 列: {self.data_config['columns']['fx']}\n"
                f"- 保留列: {self.data_config['passthrough']}")

    def browse_batch_input(self):
        """选择输入文件或目录"""
        # 保留兼容方法，但改为由两个明确按钮触发：browse_batch_file / browse_batch_dir
        pass

    def browse_batch_file(self):
        fname, _ = QFileDialog.getOpenFileName(
            self, '选择输入文件', '.',
            'Data Files (*.csv *.xlsx *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls)'
        )
        if fname:
            self.inp_batch_input.setText(fname)
            # 扫描并显示（若是单文件就只显示该文件）
            self.scan_input_path()

    def browse_batch_dir(self):
        dirname = QFileDialog.getExistingDirectory(self, '选择输入目录')
        if dirname:
            self.inp_batch_input.setText(dirname)
            # 扫描并显示目录下匹配的文件
            self.scan_input_path()

    def run_batch_processing(self):
        """运行批处理"""
        if not self.calculator:
            QMessageBox.warning(self, "警告", '请先点击"应用配置"按钮!')
            return

        if not self.data_config:
            reply = QMessageBox.question(
                self, "未配置数据格式", 
                '尚未配置数据格式，是否使用默认配置?\n\n'
                '默认: 跳过0行, Fx-Fz=列0-2, Mx-Mz=列3-5',
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.data_config = {
                    'skip_rows': 0,
                    'columns': {'alpha': None, 'fx': 0, 'fy': 1, 'fz': 2, 'mx': 3, 'my': 4, 'mz': 5},
                    'passthrough': []
                }
            else:
                return

        input_path = Path(self.inp_batch_input.text())
        if not input_path.exists():
            QMessageBox.warning(self, "错误", "输入路径不存在")
            return

        # 确定文件列表
        files_to_process = []
        if input_path.is_file():
            files_to_process = [input_path]
            output_dir = input_path.parent
        elif input_path.is_dir():
            pattern = self.inp_pattern.text()
            for file_path in input_path.rglob('*'):
                if file_path.is_file() and fnmatch.fnmatch(file_path.name, pattern):
                    files_to_process.append(file_path)
            output_dir = input_path
            
            if not files_to_process:
                QMessageBox.warning(self, "警告", f"未找到匹配 '{pattern}' 的文件")
                return
        else:
            QMessageBox.warning(self, "错误", "无效的输入路径")
            return

        # 确认处理：先展示找到的文件列表，用户确认后再执行
        file_list_text = "\n".join([str(p) for p in files_to_process])
        confirm_dlg = QMessageBox(self)
        confirm_dlg.setWindowTitle("确认处理")
        confirm_dlg.setText(f"准备处理 {len(files_to_process)} 个文件\n输出目录: {output_dir}\n\n确认开始?")
        # 将完整文件列表放在可展开的详细文本中，便于查看长列表
        confirm_dlg.setDetailedText(file_list_text)
        confirm_dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        reply = confirm_dlg.exec()

        if reply != QMessageBox.Yes:
            self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 已取消：用户未确认文件列表。")
            return

        # 开始处理
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.txt_batch_log.clear()
        self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 开始批量处理...")
        self.txt_batch_log.append(f"共 {len(files_to_process)} 个文件")

        self.batch_thread = BatchProcessThread(
            self.calculator, files_to_process, output_dir, self.data_config
        )
        self.batch_thread.progress.connect(self.progress_bar.setValue)
        self.batch_thread.log_message.connect(
            lambda msg: self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"))
        self.batch_thread.finished.connect(self.on_batch_finished)
        self.batch_thread.error.connect(self.on_batch_error)
        self.batch_thread.start()

    def on_batch_finished(self, message):
        """批处理完成"""
        self.txt_batch_log.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✓ {message}")
        self.statusBar().showMessage("批量处理完成")
        QMessageBox.information(self, "完成", message)

    def on_batch_error(self, error_msg):
        """批处理出错"""
        self.txt_batch_log.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✗ 错误: {error_msg}")
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("批量处理失败")
        QMessageBox.critical(self, "错误", f"批处理失败:\n{error_msg}")

    def scan_input_path(self):
        """扫描 `self.inp_batch_input` 指定的路径，填充文件列表滚动区，返回是否找到文件"""
        input_path = Path(self.inp_batch_input.text())
        if not input_path.exists():
            return False

        files_to_process = []
        if input_path.is_file():
            files_to_process = [input_path]
        elif input_path.is_dir():
            pattern = self.inp_pattern.text() if hasattr(self, 'inp_pattern') else '*.csv'
            for file_path in input_path.rglob('*'):
                if file_path.is_file() and fnmatch.fnmatch(file_path.name, pattern):
                    files_to_process.append(file_path)
        else:
            return False

        # 填充滚动区
        # 清理旧内容
        for i in reversed(range(self.file_list_vbox.count())):
            item = self.file_list_vbox.itemAt(i)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        self.file_checkboxes = []
        for p in files_to_process:
            cb = QCheckBox(p.name)
            cb.setChecked(True)
            self.file_list_vbox.addWidget(cb)
            self.file_checkboxes.append((cb, p))

        self.file_list_vbox.addStretch()
        return len(files_to_process) > 0


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = IntegratedAeroGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()