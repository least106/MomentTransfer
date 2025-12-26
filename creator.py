import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Qt5Agg') # 兼容 PySide6

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QDoubleSpinBox, QPushButton, 
                               QGroupBox, QFormLayout, QComboBox, QFileDialog, QMessageBox)
from PySide6.QtCore import Qt

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# 引入刚才添加的几何算法
from src.geometry import euler_angles_to_basis

class Mpl3DCanvas(FigureCanvas):
    """嵌入 Qt 的 Matplotlib 3D 画布"""
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111, projection='3d')
        super(Mpl3DCanvas, self).__init__(self.fig)
        self.setParent(parent)

    def plot_systems(self, origin, basis_matrix, moment_center):
        self.axes.clear()
        
        # 1. 绘制源坐标系 (Global / Source) - 灰色虚线
        self._draw_frame([0,0,0], np.eye(3), "Source", color=['gray']*3, alpha=0.3)

        # 2. 绘制目标坐标系 (Target) - 彩色实线
        self._draw_frame(origin, basis_matrix, "Target", color=['r', 'g', 'b'], length=1.5)

        # 3. 绘制力矩参考点 (Moment Center) - 紫色点
        self.axes.scatter(moment_center[0], moment_center[1], moment_center[2], 
                          c='m', marker='o', s=50, label='Moment Center')

        # 设置显示范围 (自动缩放)
        max_range = 3.0
        self.axes.set_xlim([-max_range, max_range])
        self.axes.set_ylim([-max_range, max_range])
        self.axes.set_zlim([-max_range, max_range])
        
        self.axes.set_xlabel('X')
        self.axes.set_ylabel('Y')
        self.axes.set_zlabel('Z')
        self.axes.legend()
        self.draw()

    def _draw_frame(self, origin, basis, label_prefix, color, length=1.0, alpha=1.0):
        # Basis[0]=X, Basis[1]=Y, Basis[2]=Z
        labels = ['X', 'Y', 'Z']
        for i in range(3):
            vec = basis[i] * length
            self.axes.quiver(origin[0], origin[1], origin[2],
                             vec[0], vec[1], vec[2],
                             color=color[i], alpha=alpha, arrow_length_ratio=0.1)
            # 在箭头末端加标签
            self.axes.text(origin[0] + vec[0], origin[1] + vec[1], origin[2] + vec[2],
                           f"{label_prefix}_{labels[i]}", color=color[i])

class ConfigCreator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AeroConfig Creator - 坐标系模板生成器")
        self.resize(1100, 700)
        
        self.init_ui()
        self.apply_template() # 初始化默认值

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # --- 左侧：控制面板 ---
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_panel.setMaximumWidth(400)

        # 1. 模板选择
        grp_temp = QGroupBox("1. 快速模板 (Part Template)")
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
        form_temp.addRow("选择组件:", self.combo_template)
        grp_temp.setLayout(form_temp)

        # 2. 角度控制 (人类可读)
        grp_angles = QGroupBox("2. 姿态定义 (Euler Angles)")
        form_angles = QFormLayout()
        
        self.spin_yaw = self._create_spin("Yaw/Sweep (偏航/后掠)", 0)
        self.spin_pitch = self._create_spin("Pitch/Incidence (俯仰/安装)", 0)
        self.spin_roll = self._create_spin("Roll/Dihedral (滚转/上反)", 0)
        
        form_angles.addRow("Yaw (deg):", self.spin_yaw)
        form_angles.addRow("Pitch (deg):", self.spin_pitch)
        form_angles.addRow("Roll (deg):", self.spin_roll)
        grp_angles.setLayout(form_angles)

        # 3. 位置与参考量
        grp_pos = QGroupBox("3. 几何参数 (Position & Ref)")
        form_pos = QFormLayout()
        
        # 坐标原点
        self.spin_ox = self._create_spin("Origin X", 0, -100, 100)
        self.spin_oy = self._create_spin("Origin Y", 0, -100, 100)
        self.spin_oz = self._create_spin("Origin Z", 0, -100, 100)
        
        # 力矩中心
        self.spin_mcx = self._create_spin("Moment Center X", 0.5, -100, 100)
        self.spin_mcy = self._create_spin("Moment Center Y", 0, -100, 100)
        self.spin_mcz = self._create_spin("Moment Center Z", 0, -100, 100)

        # 参考量
        self.spin_cref = self._create_spin("C_ref", 1.0, 0.1, 100)
        self.spin_bref = self._create_spin("B_ref", 1.0, 0.1, 100)
        self.spin_sref = self._create_spin("S_ref", 10.0, 0.1, 1000)
        self.spin_q = self._create_spin("Q (Dynamic Pressure)", 1000, 1, 100000)

        form_pos.addRow("Origin X:", self.spin_ox)
        form_pos.addRow("Origin Y:", self.spin_oy)
        form_pos.addRow("Origin Z:", self.spin_oz)
        form_pos.addRow("---", QLabel(""))
        form_pos.addRow("MomentCenter X:", self.spin_mcx)
        form_pos.addRow("MomentCenter Y:", self.spin_mcy)
        form_pos.addRow("MomentCenter Z:", self.spin_mcz)
        form_pos.addRow("---", QLabel(""))
        form_pos.addRow("S_ref:", self.spin_sref)
        form_pos.addRow("B_ref:", self.spin_bref)
        form_pos.addRow("C_ref:", self.spin_cref)
        form_pos.addRow("Q (Pa):", self.spin_q)
        
        grp_pos.setLayout(form_pos)

        # 4. 生成按钮
        btn_save = QPushButton("生成配置文件 (Save JSON)")
        btn_save.setMinimumHeight(50)
        btn_save.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold; font-size: 14px;")
        btn_save.clicked.connect(self.save_json)

        control_layout.addWidget(grp_temp)
        control_layout.addWidget(grp_angles)
        control_layout.addWidget(grp_pos)
        control_layout.addStretch()
        control_layout.addWidget(btn_save)

        # --- 右侧：3D 可视化 ---
        self.canvas3d = Mpl3DCanvas(self, width=6, height=6, dpi=100)
        
        layout.addWidget(control_panel)
        layout.addWidget(self.canvas3d, stretch=1)

    def _create_spin(self, tooltip, initial_value, minimum_value=-180, maximum_value=180):
        spin = QDoubleSpinBox()
        spin.setRange(minimum_value, maximum_value)
        spin.setValue(initial_value)
        spin.setSingleStep(1.0)
        spin.setToolTip(tooltip)
        spin.valueChanged.connect(self.update_visualization)
        return spin

    def apply_template(self):
        """根据下拉框选择，预设一些经验值"""
        idx = self.combo_template.currentIndex()
        # 仅暂停会触发 redraw 的旋转控件信号，避免全窗口屏蔽
        self.spin_yaw.blockSignals(True)
        self.spin_pitch.blockSignals(True)
        self.spin_roll.blockSignals(True)

        if idx == 0:  # Generic
            pass
        elif idx == 1:  # Right Wing
            self.spin_yaw.setValue(30)   # 后掠
            self.spin_pitch.setValue(2)  # 安装角
            self.spin_roll.setValue(5)   # 上反
        elif idx == 2:  # Left Wing
            self.spin_yaw.setValue(-30)
            self.spin_pitch.setValue(2)
            self.spin_roll.setValue(-5)
        elif idx == 3:  # Vertical Tail
            self.spin_yaw.setValue(0)
            self.spin_pitch.setValue(0)
            self.spin_roll.setValue(90)  # 竖起来
        elif idx == 4:  # Horizontal Stabilizer
            self.spin_yaw.setValue(15)
            self.spin_pitch.setValue(-2)
            self.spin_roll.setValue(0)

        # 解除仅针对上面控件的信号屏蔽
        self.spin_yaw.blockSignals(False)
        self.spin_pitch.blockSignals(False)
        self.spin_roll.blockSignals(False)

        # 手动触发一次可视化刷新
        self.update_visualization()

    def update_visualization(self):
        """核心逻辑：读取控件 -> 计算向量 -> 刷新3D图"""
        # 1. 获取位置
        origin = [self.spin_ox.value(), self.spin_oy.value(), self.spin_oz.value()]
        mc = [self.spin_mcx.value(), self.spin_mcy.value(), self.spin_mcz.value()]
        
        # 2. 计算方向矩阵 (Euler -> Basis Vectors)
        basis = self._get_current_basis_matrix()

        # 3. 绘图
        self.canvas3d.plot_systems(origin, basis, mc)

    def save_json(self):
        data = self.build_config_dict()

        # 3. 保存文件
        fname, _ = QFileDialog.getSaveFileName(self, '保存配置', 'custom_part.json', 'JSON Files (*.json)')
        if fname:
            try:
                with open(fname, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                QMessageBox.information(self, "成功", f"配置文件已生成：\n{fname}")
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "错误",
                    f"保存配置文件失败：\n{fname}\n\n详细信息：{e}"
                )

    def build_config_dict(self) -> dict:
        """构建符合项目 `input.json` 结构的字典并返回。

        抽取为独立方法以避免与其他位置重复定义结构。
        """
        basis = self._get_current_basis_matrix()

        data = {
            "Source": {
                "PartName": "Global",
                "CoordSystem": {
                    "Orig": [0.0, 0.0, 0.0],
                    "X": [1.0, 0.0, 0.0],
                    "Y": [0.0, 1.0, 0.0],
                    "Z": [0.0, 0.0, 1.0]
                },
                "MomentCenter": [0.0, 0.0, 0.0],
                "Cref": 1.0,
                "Bref": 1.0,
                "Q": 1000.0,
                "S": 10.0
            },
            "Target": {
                "PartName": self.combo_template.currentText(),
                "CoordSystem": {
                    "Orig": [self.spin_ox.value(), self.spin_oy.value(), self.spin_oz.value()],
                    "X": basis[0].tolist(),
                    "Y": basis[1].tolist(),
                    "Z": basis[2].tolist()
                },
                "MomentCenter": [
                    self.spin_mcx.value(), self.spin_mcy.value(), self.spin_mcz.value()
                ],
                "Cref": self.spin_cref.value(),
                "Bref": self.spin_bref.value(),
                "Q": self.spin_q.value(),
                "S": self.spin_sref.value()
            }
        }

        return data

    def _get_current_basis_matrix(self):
        """Helper: 从当前 UI 的欧拉角控件计算并返回基向量矩阵。

        抽取为单独方法以避免在多处重复调用 `euler_angles_to_basis`，
        并确保两个位置使用一致的参数顺序。
        """
        # note: euler_angles_to_basis(roll, pitch, yaw)
        roll = self.spin_roll.value()
        pitch = self.spin_pitch.value()
        yaw = self.spin_yaw.value()
        return euler_angles_to_basis(roll, pitch, yaw)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ConfigCreator()
    window.show()
    sys.exit(app.exec())