import sys
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QGroupBox, QFormLayout, QFileDialog, QTextEdit, QMessageBox)
from PySide6.QtGui import QFont, QIcon

# 标准导入
from src import load_data, AeroCalculator, ProjectData


class AeroTransformWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AeroTransform - 工程气动载荷变换工具")
        self.resize(1000, 750)

        # 核心处理器
        self.processor: AeroCalculator = None
        self.current_config: ProjectData = None

        # 初始化 UI
        self.init_ui()

        # 尝试自动加载默认配置
        default_config = os.path.join(os.path.dirname(__file__), 'data', 'input.json')
        if os.path.exists(default_config):
            self.load_config_file(default_config)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # --- 顶部：配置加载 ---
        config_group = QGroupBox("项目配置 (Geometry Configuration)")
        config_layout = QHBoxLayout()

        self.lbl_config_status = QLabel("未加载配置")
        self.lbl_config_status.setStyleSheet("color: red; font-weight: bold;")

        btn_load = QPushButton("加载配置文件 (JSON)")
        btn_load.clicked.connect(self.open_file_dialog)

        config_layout.addWidget(QLabel("当前状态:"))
        config_layout.addWidget(self.lbl_config_status)
        config_layout.addStretch()
        config_layout.addWidget(btn_load)
        config_group.setLayout(config_layout)

        # --- 中部：输入区域 ---
        input_group = QGroupBox("工况输入 (Source Frame)")
        input_layout = QFormLayout()

        self.inp_fx = QLineEdit("0.0")
        self.inp_fy = QLineEdit("0.0")
        self.inp_fz = QLineEdit("0.0")
        self.inp_mx = QLineEdit("0.0")
        self.inp_my = QLineEdit("0.0")
        self.inp_mz = QLineEdit("0.0")

        # 一行放三个输入框
        row_force = QHBoxLayout()
        row_force.addWidget(QLabel("Fx:"))
        row_force.addWidget(self.inp_fx)
        row_force.addWidget(QLabel("Fy:"))
        row_force.addWidget(self.inp_fy)
        row_force.addWidget(QLabel("Fz:"))
        row_force.addWidget(self.inp_fz)

        row_moment = QHBoxLayout()
        row_moment.addWidget(QLabel("Mx:"))
        row_moment.addWidget(self.inp_mx)
        row_moment.addWidget(QLabel("My:"))
        row_moment.addWidget(self.inp_my)
        row_moment.addWidget(QLabel("Mz:"))
        row_moment.addWidget(self.inp_mz)

        input_layout.addRow("Force (N):", row_force)
        input_layout.addRow("Moment (N*m):", row_moment)
        input_group.setLayout(input_layout)

        # --- 按钮 ---
        btn_calc = QPushButton("执行计算 (Calculate)")
        btn_calc.setMinimumHeight(40)
        btn_calc.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold;")
        btn_calc.clicked.connect(self.run_calculation)

        # --- 底部：结果展示 ---
        result_group = QGroupBox("计算结果报告")
        result_layout = QVBoxLayout()
        self.txt_result = QTextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setFont(QFont("Consolas", 10))  # 等宽字体便于对齐
        result_layout.addWidget(self.txt_result)
        result_group.setLayout(result_layout)

        # 添加到主布局
        layout.addWidget(config_group)
        layout.addWidget(input_group)
        layout.addWidget(btn_calc)
        layout.addWidget(result_group)

    def open_file_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, '打开配置文件', '.', 'JSON Files (*.json)')
        if fname:
            self.load_config_file(fname)

    def load_config_file(self, path):
        try:
            self.current_config = load_data(path)
            self.processor = AeroCalculator(self.current_config)

            part = self.current_config.target_config.part_name
            self.lbl_config_status.setText(f"已加载: {part} ({os.path.basename(path)})")
            self.lbl_config_status.setStyleSheet("color: green; font-weight: bold;")
            self.statusBar().showMessage(f"配置加载成功: {path}")
        except Exception as e:
            QMessageBox.critical(self, "加载失败", str(e))
            self.lbl_config_status.setText("配置错误")
            self.lbl_config_status.setStyleSheet("color: red;")

    def run_calculation(self):
        if not self.processor:
            QMessageBox.warning(self, "警告", "请先加载配置文件！")
            return

        try:
            # 获取输入
            f_raw = [float(self.inp_fx.text()), float(self.inp_fy.text()), float(self.inp_fz.text())]
            m_raw = [float(self.inp_mx.text()), float(self.inp_my.text()), float(self.inp_mz.text())]

            # 计算
            res = self.processor.process_frame(f_raw, m_raw)

            # 生成报告
            report = self.generate_report(f_raw, m_raw, res)
            self.txt_result.setText(report)

        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字！")
        except Exception as e:
            QMessageBox.critical(self, "计算错误", str(e))

    def generate_report(self, f_in, m_in, res):
        return (
            f"--- Computation Report ---\n"
            f"Source Input:\n"
            f"  Force : {f_in}\n"
            f"  Moment: {m_in}\n\n"
            f"Target Output ({self.current_config.target_config.part_name}):\n"
            f"  Force : {[round(x, 4) for x in res.force_transformed]}\n"
            f"  Moment: {[round(x, 4) for x in res.moment_transformed]}\n\n"
            f"Coefficients:\n"
            f"  CF: {[round(x, 6) for x in res.coeff_force]}\n"
            f"  CM: {[round(x, 6) for x in res.coeff_moment]}\n"
        )


def main():
    app = QApplication(sys.argv)
    window = AeroTransformWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()