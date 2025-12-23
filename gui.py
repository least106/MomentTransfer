import sys
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
import matplotlib
matplotlib.use('Qt5Agg')

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox, QFormLayout, QFileDialog,
    QTextEdit, QMessageBox, QTabWidget, QDoubleSpinBox, QComboBox,
    QTableWidget, QTableWidgetItem, QProgressBar, QCheckBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QThread, Signal

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# 导入项目模块
from src.data_loader import load_data, ProjectData
from src.physics import AeroCalculator
from src.geometry import euler_angles_to_basis


class Mpl3DCanvas(FigureCanvas):
    """3D坐标系可视化画布"""
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111, projection='3d')
        super().__init__(self.fig)
        self.setParent(parent)

    def plot_systems(self, origin, basis_matrix, moment_center):
        self.axes.clear()
        
        # 源坐标系（灰色虚线）
        self._draw_frame([0,0,0], np.eye(3), "Source", color=['gray']*3, alpha=0.3)
        
        # 目标坐标系（彩色实线）
        self._draw_frame(origin, basis_matrix, "Target", color=['r', 'g', 'b'], length=1.5)
        
        # 力矩中心（紫色点）
        self.axes.scatter(moment_center[0], moment_center[1], moment_center[2], 
                          c='m', marker='o', s=50, label='Moment Center')
        
        max_range = 3.0
        self.axes.set_xlim([-max_range, max_range])
        self.axes.set_ylim([-max_range, max_range])
        self.axes.set_zlim([-max_range, max_range])
        
        self.axes.set_xlabel('X')
        self.axes.set_ylabel('Y')
        self.axes.set_zlabel('Z')
        self.axes.legend()
        self.draw()

    def _draw_frame(self, o, basis, label_prefix, color, length=1.0, alpha=1.0):
        labels = ['X', 'Y', 'Z']
        for i in range(3):
            vec = basis[i] * length
            self.axes.quiver(o[0], o[1], o[2], 
                             vec[0], vec[1], vec[2], 
                             color=color[i], alpha=alpha, arrow_length_ratio=0.1)
            self.axes.text(o[0]+vec[0], o[1]+vec[1], o[2]+vec[2], 
                           f"{label_prefix}_{labels[i]}", color=color[i])


class BatchProcessThread(QThread):
    """批处理后台线程"""
    progress = Signal(int)
    finished = Signal(str)
    error = Signal(str)
    
    def __init__(self, calculator, input_file, output_file):
        super().__init__()
        self.calculator = calculator
        self.input_file = input_file
        self.output_file = output_file
    
    def run(self):
        try:
            # 读取文件
            if self.input_file.endswith('.csv'):
                df = pd.read_csv(self.input_file)
            else:
                df = pd.read_excel(self.input_file)
            
            # 列名识别
            required_cols = {
                'fx': ['fx', 'force_x', 'f_x'],
                'fy': ['fy', 'force_y', 'f_y'],
                'fz': ['fz', 'force_z', 'f_z'],
                'mx': ['mx', 'moment_x', 'm_x'],
                'my': ['my', 'moment_y', 'm_y'],
                'mz': ['mz', 'moment_z', 'm_z']
            }
            
            col_map = {}
            df_cols_lower = [c.lower() for c in df.columns]
            
            for key, candidates in required_cols.items():
                found = False
                for cand in candidates:
                    if cand in df_cols_lower:
                        real_col_name = df.columns[df_cols_lower.index(cand)]
                        col_map[key] = real_col_name
                        found = True
                        break
                if not found:
                    self.error.emit(f"找不到列: {key}")
                    return
            
            # 提取数据
            forces_in = df[[col_map['fx'], col_map['fy'], col_map['fz']]].values
            moments_in = df[[col_map['mx'], col_map['my'], col_map['mz']]].values
            

            self.progress.emit(0)
            
            # 批量计算
            results = self.calculator.process_batch(forces_in, moments_in)
            
            self.progress.emit(50)
            
            # 添加结果列
            suffix = "_new"
            df[f'Fx{suffix}'] = results['force_transformed'][:, 0]
            df[f'Fy{suffix}'] = results['force_transformed'][:, 1]
            df[f'Fz{suffix}'] = results['force_transformed'][:, 2]
            
            df[f'Mx{suffix}'] = results['moment_transformed'][:, 0]
            df[f'My{suffix}'] = results['moment_transformed'][:, 1]
            df[f'Mz{suffix}'] = results['moment_transformed'][:, 2]
            
            df['Cx'] = results['coeff_force'][:, 0]
            df['Cy'] = results['coeff_force'][:, 1]
            df['Cz'] = results['coeff_force'][:, 2]
            
            df['Cl'] = results['coeff_moment'][:, 0]
            df['Cm'] = results['coeff_moment'][:, 1]
            df['Cn'] = results['coeff_moment'][:, 2]
            
            self.progress.emit(75)
            
            # 保存文件
            out_ext = os.path.splitext(self.output_file)[1].lower()
            if out_ext == '.csv':
                df.to_csv(self.output_file, index=False)
            else:
                df.to_excel(self.output_file, index=False)
            
            self.progress.emit(100)
            self.finished.emit(f"成功处理 {total} 条数据")
            
        except Exception as e:
            self.error.emit(str(e))


class IntegratedAeroGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MomentTransfer - 集成气动载荷变换工具")
        self.resize(1400, 900)
        
        # 核心处理器
        self.calculator = None
        self.current_config = None
        
        self.init_ui()
        
    def init_ui(self):
        # 主Tab控件
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        
        # Tab 1: 配置创建
        tab_config = self.create_config_tab()
        tabs.addTab(tab_config, "1️⃣ 配置创建")
        
        # Tab 2: 单点测试
        tab_single = self.create_single_test_tab()
        tabs.addTab(tab_single, "2️⃣ 单点测试")
        
        # Tab 3: 批量处理
        tab_batch = self.create_batch_tab()
        tabs.addTab(tab_batch, "3️⃣ 批量处理")
        
        # 状态栏
        self.statusBar().showMessage("就绪")
    
    def create_config_tab(self):
        """Tab 1: 配置创建器"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        # 左侧控制面板
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_panel.setMaximumWidth(450)
        
        # 快速模板
        grp_template = QGroupBox("快速模板")
        form_temp = QFormLayout()
        self.combo_template = QComboBox()
        self.combo_template.addItems([
            "Generic (通用)", 
            "Right Wing (右机翼)", 
            "Left Wing (左机翼)", 
            "Vertical Tail (垂尾)", 
            "Horizontal Stabilizer (平尾)"
        ])
        self.combo_template.currentIndexChanged.connect(self.apply_template)
        
        self.inp_part_name = QLineEdit("TestModel")
        form_temp.addRow("选择组件:", self.combo_template)
        form_temp.addRow("部件名称:", self.inp_part_name)
        grp_template.setLayout(form_temp)
        
        # 姿态定义
        grp_angles = QGroupBox("姿态定义 (欧拉角)")
        form_angles = QFormLayout()
        
        self.spin_yaw = self._create_spin("偏航/后掠", 0)
        self.spin_pitch = self._create_spin("俯仰/安装", 0)
        self.spin_roll = self._create_spin("滚转/上反", 0)
        
        form_angles.addRow("Yaw (deg):", self.spin_yaw)
        form_angles.addRow("Pitch (deg):", self.spin_pitch)
        form_angles.addRow("Roll (deg):", self.spin_roll)
        grp_angles.setLayout(form_angles)
        
        # 几何参数
        grp_geom = QGroupBox("几何参数")
        form_geom = QFormLayout()
        
        self.spin_ox = self._create_spin("Origin X", 0, -100, 100)
        self.spin_oy = self._create_spin("Origin Y", 0, -100, 100)
        self.spin_oz = self._create_spin("Origin Z", 0, -100, 100)
        
        self.spin_mcx = self._create_spin("Moment Center X", 0.5, -100, 100)
        self.spin_mcy = self._create_spin("Moment Center Y", 0, -100, 100)
        self.spin_mcz = self._create_spin("Moment Center Z", 0, -100, 100)
        
        self.spin_sref = self._create_spin("S_ref", 10.0, 0.1, 1000)
        self.spin_bref = self._create_spin("B_ref", 1.0, 0.1, 100)
        self.spin_cref = self._create_spin("C_ref", 1.0, 0.1, 100)
        self.spin_q = self._create_spin("Q (动压)", 1000, 1, 100000)
        
        form_geom.addRow("Origin X:", self.spin_ox)
        form_geom.addRow("Origin Y:", self.spin_oy)
        form_geom.addRow("Origin Z:", self.spin_oz)
        form_geom.addRow("---", QLabel(""))
        form_geom.addRow("Moment Center X:", self.spin_mcx)
        form_geom.addRow("Moment Center Y:", self.spin_mcy)
        form_geom.addRow("Moment Center Z:", self.spin_mcz)
        form_geom.addRow("---", QLabel(""))
        form_geom.addRow("S_ref (m²):", self.spin_sref)
        form_geom.addRow("B_ref (m):", self.spin_bref)
        form_geom.addRow("C_ref (m):", self.spin_cref)
        form_geom.addRow("Q (Pa):", self.spin_q)
        
        grp_geom.setLayout(form_geom)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_save_config = QPushButton("保存配置文件")
        btn_save_config.clicked.connect(self.save_config)
        btn_load_config = QPushButton("加载已有配置")
        btn_load_config.clicked.connect(self.load_config)
        btn_apply_config = QPushButton("应用到当前会话")
        btn_apply_config.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold;")
        btn_apply_config.clicked.connect(self.apply_config_to_session)
        
        btn_layout.addWidget(btn_save_config)
        btn_layout.addWidget(btn_load_config)
        
        control_layout.addWidget(grp_template)
        control_layout.addWidget(grp_angles)
        control_layout.addWidget(grp_geom)
        control_layout.addStretch()
        control_layout.addLayout(btn_layout)
        control_layout.addWidget(btn_apply_config)
        
        # 右侧3D可视化
        self.canvas3d = Mpl3DCanvas(self, width=7, height=7, dpi=100)
        
        layout.addWidget(control_panel)
        layout.addWidget(self.canvas3d, stretch=1)
        
        # 初始化显示
        self.apply_template()
        
        return widget
    
    def create_single_test_tab(self):
        """Tab 2: 单点测试"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 配置状态
        status_group = QGroupBox("当前配置状态")
        status_layout = QHBoxLayout()
        self.lbl_status = QLabel("未加载配置 - 请先在Tab1创建或加载配置")
        self.lbl_status.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.lbl_status)
        status_layout.addStretch()
        status_group.setLayout(status_layout)
        
        # 输入区域
        input_group = QGroupBox("工况输入 (Source Frame)")
        input_layout = QFormLayout()
        
        self.inp_fx = QLineEdit("0.0")
        self.inp_fy = QLineEdit("0.0")
        self.inp_fz = QLineEdit("0.0")
        self.inp_mx = QLineEdit("0.0")
        self.inp_my = QLineEdit("0.0")
        self.inp_mz = QLineEdit("0.0")
        
        row_f = QHBoxLayout()
        row_f.addWidget(QLabel("Fx:"))
        row_f.addWidget(self.inp_fx)
        row_f.addWidget(QLabel("Fy:"))
        row_f.addWidget(self.inp_fy)
        row_f.addWidget(QLabel("Fz:"))
        row_f.addWidget(self.inp_fz)
        
        row_m = QHBoxLayout()
        row_m.addWidget(QLabel("Mx:"))
        row_m.addWidget(self.inp_mx)
        row_m.addWidget(QLabel("My:"))
        row_m.addWidget(self.inp_my)
        row_m.addWidget(QLabel("Mz:"))
        row_m.addWidget(self.inp_mz)
        
        input_layout.addRow("Force (N):", row_f)
        input_layout.addRow("Moment (N·m):", row_m)
        input_group.setLayout(input_layout)
        
        # 计算按钮
        btn_calc = QPushButton("执行计算")
        btn_calc.setMinimumHeight(50)
        btn_calc.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; font-size: 14px;")
        btn_calc.clicked.connect(self.run_single_test)
        
        # 结果显示
        result_group = QGroupBox("计算结果")
        result_layout = QVBoxLayout()
        self.txt_result = QTextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setFont(QFont("Consolas", 10))
        result_layout.addWidget(self.txt_result)
        result_group.setLayout(result_layout)
        
        layout.addWidget(status_group)
        layout.addWidget(input_group)
        layout.addWidget(btn_calc)
        layout.addWidget(result_group)
        
        return widget
    
    def create_batch_tab(self):
        """Tab 3: 批量处理"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 配置状态
        status_group = QGroupBox("当前配置状态")
        status_layout = QHBoxLayout()
        self.lbl_batch_status = QLabel("未加载配置")
        self.lbl_batch_status.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.lbl_batch_status)
        status_layout.addStretch()
        status_group.setLayout(status_layout)
        
        # 文件选择
        file_group = QGroupBox("文件选择")
        file_layout = QFormLayout()
        
        input_row = QHBoxLayout()
        self.inp_batch_input = QLineEdit()
        self.inp_batch_input.setPlaceholderText("选择输入的 CSV 或 Excel 文件...")
        btn_browse_input = QPushButton("浏览...")
        btn_browse_input.clicked.connect(self.browse_batch_input)
        input_row.addWidget(self.inp_batch_input)
        input_row.addWidget(btn_browse_input)
        
        output_row = QHBoxLayout()
        self.inp_batch_output = QLineEdit()
        self.inp_batch_output.setPlaceholderText("选择输出文件路径...")
        btn_browse_output = QPushButton("浏览...")
        btn_browse_output.clicked.connect(self.browse_batch_output)
        output_row.addWidget(self.inp_batch_output)
        output_row.addWidget(btn_browse_output)
        
        file_layout.addRow("输入文件:", input_row)
        file_layout.addRow("输出文件:", output_row)
        file_group.setLayout(file_layout)
        
        # 列名映射提示
        hint_group = QGroupBox("数据格式要求")
        hint_layout = QVBoxLayout()
        hint_text = QLabel(
            "输入文件必须包含以下列（不区分大小写）：\n"
            "• 力：Fx / Force_X / F_X\n"
            "• 力：Fy / Force_Y / F_Y\n"
            "• 力：Fz / Force_Z / F_Z\n"
            "• 力矩：Mx / Moment_X / M_X\n"
            "• 力矩：My / Moment_Y / M_Y\n"
            "• 力矩：Mz / Moment_Z / M_Z"
        )
        hint_text.setStyleSheet("color: #666; font-size: 11px;")
        hint_layout.addWidget(hint_text)
        hint_group.setLayout(hint_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        # 执行按钮
        btn_run_batch = QPushButton("开始批量处理")
        btn_run_batch.setMinimumHeight(50)
        btn_run_batch.setStyleSheet("background-color: #ff6b6b; color: white; font-weight: bold; font-size: 14px;")
        btn_run_batch.clicked.connect(self.run_batch_processing)
        
        # 日志显示
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()
        self.txt_batch_log = QTextEdit()
        self.txt_batch_log.setReadOnly(True)
        self.txt_batch_log.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.txt_batch_log)
        log_group.setLayout(log_layout)
        
        layout.addWidget(status_group)
        layout.addWidget(file_group)
        layout.addWidget(hint_group)
        layout.addWidget(self.progress_bar)
        layout.addWidget(btn_run_batch)
        layout.addWidget(log_group)
        
        return widget
    
    def _create_spin(self, tooltip, val, min_v=-180, max_v=180):
        spin = QDoubleSpinBox()
        spin.setRange(min_v, max_v)
        spin.setValue(val)
        spin.setSingleStep(1.0)
        spin.setToolTip(tooltip)
        spin.valueChanged.connect(self.update_visualization)
        return spin
    
    def apply_template(self):
        """应用快速模板"""
        idx = self.combo_template.currentIndex()
        # 仅在相关控件上屏蔽信号，避免影响整个窗口
        spins = [
            self.spin_yaw, self.spin_pitch, self.spin_roll,
            self.spin_ox, self.spin_oy, self.spin_oz,
            self.spin_mcx, self.spin_mcy, self.spin_mcz,
            self.spin_sref, self.spin_bref, self.spin_cref, self.spin_q
        ]

        for s in spins:
            try:
                s.blockSignals(True)
            except Exception:
                pass

        if idx == 1:  # Right Wing
            self.spin_yaw.setValue(30)
            self.spin_pitch.setValue(2)
            self.spin_roll.setValue(5)
        elif idx == 2:  # Left Wing
            self.spin_yaw.setValue(-30)
            self.spin_pitch.setValue(2)
            self.spin_roll.setValue(-5)
        elif idx == 3:  # Vertical Tail
            self.spin_yaw.setValue(0)
            self.spin_pitch.setValue(0)
            self.spin_roll.setValue(90)
        elif idx == 4:  # Horizontal Stabilizer
            self.spin_yaw.setValue(15)
            self.spin_pitch.setValue(-2)
            self.spin_roll.setValue(0)

        for s in spins:
            try:
                s.blockSignals(False)
            except Exception:
                pass

        self.update_visualization()
    
    def update_visualization(self):
        """更新3D可视化"""
        origin = [self.spin_ox.value(), self.spin_oy.value(), self.spin_oz.value()]
        mc = [self.spin_mcx.value(), self.spin_mcy.value(), self.spin_mcz.value()]
        
        basis = euler_angles_to_basis(
            self.spin_roll.value(),
            self.spin_pitch.value(),
            self.spin_yaw.value()
        )
        
        self.canvas3d.plot_systems(origin, basis, mc)
    
    def save_config(self):
        """保存配置到JSON文件"""
        basis = euler_angles_to_basis(
            self.spin_roll.value(),
            self.spin_pitch.value(),
            self.spin_yaw.value()
        )
        
        data = {
            "SourceCoordSystem": {
                "Orig": [0.0, 0.0, 0.0],
                "X": [1.0, 0.0, 0.0],
                "Y": [0.0, 1.0, 0.0],
                "Z": [0.0, 0.0, 1.0]
            },
            "Target": {
                "PartName": self.inp_part_name.text(),
                "TargetCoordSystem": {
                    "Orig": [self.spin_ox.value(), self.spin_oy.value(), self.spin_oz.value()],
                    "X": basis[0].tolist(),
                    "Y": basis[1].tolist(),
                    "Z": basis[2].tolist()
                },
                "TargetMomentCenter": [
                    self.spin_mcx.value(), self.spin_mcy.value(), self.spin_mcz.value()
                ],
                "Cref": self.spin_cref.value(),
                "Bref": self.spin_bref.value(),
                "Q": self.spin_q.value(),
                "S": self.spin_sref.value()
            }
        }
        
        fname, _ = QFileDialog.getSaveFileName(self, '保存配置', 'config.json', 'JSON Files (*.json)')
        if fname:
            try:
                with open(fname, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                QMessageBox.information(self, "成功", f"配置已保存到:\n{fname}")
                self.statusBar().showMessage(f"配置已保存: {fname}")
            except Exception as e:
                QMessageBox.critical(self, "错误", str(e))
    
    def load_config(self):
        """加载配置文件"""
        fname, _ = QFileDialog.getOpenFileName(self, '打开配置', '.', 'JSON Files (*.json)')
        if fname:
            try:
                with open(fname, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 解析并填充到界面
                target = data['Target']
                self.inp_part_name.setText(target['PartName'])
                
                orig = target['TargetCoordSystem']['Orig']
                self.spin_ox.setValue(orig[0])
                self.spin_oy.setValue(orig[1])
                self.spin_oz.setValue(orig[2])
                
                mc = target['TargetMomentCenter']
                self.spin_mcx.setValue(mc[0])
                self.spin_mcy.setValue(mc[1])
                self.spin_mcz.setValue(mc[2])
                
                self.spin_sref.setValue(target.get('S', 1.0))
                self.spin_bref.setValue(target.get('Bref', 1.0))
                self.spin_cref.setValue(target.get('Cref', 1.0))
                self.spin_q.setValue(target.get('Q', 1000.0))
                
                # 应用到会话
                self.current_config = load_data(fname)
                self.calculator = AeroCalculator(self.current_config)
                self._update_status_labels(target['PartName'])
                
                QMessageBox.information(self, "成功", "配置加载成功！")
                self.update_visualization()
                
            except Exception as e:
                QMessageBox.critical(self, "加载失败", str(e))
    
    def apply_config_to_session(self):
        """将当前配置应用到会话（不保存文件）"""
        try:
            basis = euler_angles_to_basis(
                self.spin_roll.value(),
                self.spin_pitch.value(),
                self.spin_yaw.value()
            )
            
            data = {
                "SourceCoordSystem": {
                    "Orig": [0.0, 0.0, 0.0],
                    "X": [1.0, 0.0, 0.0],
                    "Y": [0.0, 1.0, 0.0],
                    "Z": [0.0, 0.0, 1.0]
                },
                "Target": {
                    "PartName": self.inp_part_name.text(),
                    "TargetCoordSystem": {
                        "Orig": [self.spin_ox.value(), self.spin_oy.value(), self.spin_oz.value()],
                        "X": basis[0].tolist(),
                        "Y": basis[1].tolist(),
                        "Z": basis[2].tolist()
                    },
                    "TargetMomentCenter": [
                        self.spin_mcx.value(), self.spin_mcy.value(), self.spin_mcz.value()
                    ],
                    "Cref": self.spin_cref.value(),
                    "Bref": self.spin_bref.value(),
                    "Q": self.spin_q.value(),
                    "S": self.spin_sref.value()
                }
            }
            
            # 直接从字典创建配置对象

            self.current_config = ProjectData.from_dict(data)
            self.calculator = AeroCalculator(self.current_config)
            
            part_name = self.inp_part_name.text()
            self._update_status_labels(part_name)
            
            QMessageBox.information(self, "成功", "配置已应用到当前会话！\n可以进行单点测试和批量处理了。")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"配置应用失败:\n{str(e)}")
    
    def _update_status_labels(self, part_name):
        """更新所有Tab的状态标签"""
        status_text = f"已加载: {part_name}"
        self.lbl_status.setText(status_text)
        self.lbl_status.setStyleSheet("color: green; font-weight: bold;")
        self.lbl_batch_status.setText(status_text)
        self.lbl_batch_status.setStyleSheet("color: green; font-weight: bold;")
        self.statusBar().showMessage(f"配置已加载: {part_name}")
        
    def run_single_test(self):
        """运行单点测试"""
        if not self.calculator:
            QMessageBox.warning(self, "警告", "请先在Tab1创建或加载配置！")
            return
        
        try:
            f_raw = [float(self.inp_fx.text()), float(self.inp_fy.text()), float(self.inp_fz.text())]
            m_raw = [float(self.inp_mx.text()), float(self.inp_my.text()), float(self.inp_mz.text())]
            
            result = self.calculator.process_frame(f_raw, m_raw)
            
            report = (
                f"{'='*60}\n"
                f"计算报告 - {self.current_config.target_config.part_name}\n"
                f"{'='*60}\n\n"
                f"【输入】Source Frame:\n"
                f"  Force  (N)   : [{f_raw[0]:.4f}, {f_raw[1]:.4f}, {f_raw[2]:.4f}]\n"
                f"  Moment (N·m) : [{m_raw[0]:.4f}, {m_raw[1]:.4f}, {m_raw[2]:.4f}]\n\n"
                f"【输出】Target Frame:\n"
                f"  Force  (N)   : [{result.force_transformed[0]:.4f}, {result.force_transformed[1]:.4f}, {result.force_transformed[2]:.4f}]\n"
                f"  Moment (N·m) : [{result.moment_transformed[0]:.4f}, {result.moment_transformed[1]:.4f}, {result.moment_transformed[2]:.4f}]\n\n"
                f"【系数】Aerodynamic Coefficients:\n"
                f"  CF [Cx, Cy, Cz] : [{result.coeff_force[0]:.6f}, {result.coeff_force[1]:.6f}, {result.coeff_force[2]:.6f}]\n"
                f"  CM [Cl, Cm, Cn] : [{result.coeff_moment[0]:.6f}, {result.coeff_moment[1]:.6f}, {result.coeff_moment[2]:.6f}]\n"
                f"{'='*60}\n"
            )
            
            self.txt_result.setText(report)
            self.statusBar().showMessage("单点计算完成")
            
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字！")
        except Exception as e:
            QMessageBox.critical(self, "计算错误", str(e))

    def browse_batch_input(self):
        """选择批处理输入文件"""
        fname, _ = QFileDialog.getOpenFileName(
            self, '选择输入文件', '.', 
            'Data Files (*.csv *.xlsx *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls)'
        )
        if fname:
            self.inp_batch_input.setText(fname)
            # 自动生成输出文件名
            base, ext = os.path.splitext(fname)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            suggested_output = f"{base}_result_{timestamp}{ext}"
            self.inp_batch_output.setText(suggested_output)

    def browse_batch_output(self):
        """选择批处理输出文件"""
        fname, _ = QFileDialog.getSaveFileName(
            self, '保存结果文件', '', 
            'CSV Files (*.csv);;Excel Files (*.xlsx)'
        )
        if fname:
            self.inp_batch_output.setText(fname)

    def run_batch_processing(self):
        """运行批量处理"""
        if not self.calculator:
            QMessageBox.warning(self, "警告", "请先在Tab1创建或加载配置！")
            return
        
        input_file = self.inp_batch_input.text()
        output_file = self.inp_batch_output.text()
        
        if not input_file or not output_file:
            QMessageBox.warning(self, "警告", "请选择输入和输出文件！")
            return
        
        if not os.path.exists(input_file):
            QMessageBox.warning(self, "错误", f"输入文件不存在:\n{input_file}")
            return
        
        # 显示进度条
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.txt_batch_log.clear()
        self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 开始批量处理...")
        self.txt_batch_log.append(f"输入: {input_file}")
        self.txt_batch_log.append(f"输出: {output_file}\n")
        
        # 创建后台线程
        self.batch_thread = BatchProcessThread(self.calculator, input_file, output_file)
        self.batch_thread.progress.connect(self.progress_bar.setValue)
        self.batch_thread.finished.connect(self.on_batch_finished)
        self.batch_thread.error.connect(self.on_batch_error)
        self.batch_thread.start()

    def on_batch_finished(self, message):
        """批处理完成"""
        self.txt_batch_log.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✅ {message}")
        self.txt_batch_log.append(f"结果已保存到: {self.inp_batch_output.text()}")
        self.statusBar().showMessage("批量处理完成")
        QMessageBox.information(self, "完成", message)

    def on_batch_error(self, error_msg):
        """批处理出错"""
        self.txt_batch_log.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] ❌ 错误: {error_msg}")
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("批量处理失败")
        QMessageBox.critical(self, "错误", f"批处理失败:\n{error_msg}")

def main():
    app = QApplication(sys.argv)
    # 设置应用样式
    app.setStyle('Fusion')

    window = IntegratedAeroGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()