import sys
import os
import json
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QGroupBox, QFormLayout, QFileDialog, QTextEdit, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

# 导入我们之前写的模块
# 注意：确保你在项目根目录下运行，或者调整PYTHONPATH
try:
    from src.data_loader import load_data, ProjectData
    from src.physics import AeroCalculator
except ImportError:
    # 简单的fallback，防止直接运行此文件时找不到包
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    # TODO: 避免在运行时修改 sys.path，建议保持包结构或使用 package 运行方式（`python -m src.gui_main`）。
    # TODO: 在 CI/测试环境中确保导入路径一致，减少运行时导入差异导致的问题。
    from src.data_loader import load_data, ProjectData
    from src.physics import AeroCalculator

class AeroTransformWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("力矩变换坐标系工具 (Aero Moment Transform)")
        self.resize(1000, 700)
        
        # 核心处理器实例
        self.processor: AeroCalculator = None
        self.current_config: ProjectData = None

        # --- 主界面布局 ---
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # === 左侧面板：控制与输入 ===
        left_panel = QVBoxLayout()
        main_layout.addLayout(left_panel, stretch=1)

        # 1. 配置文件加载区
        config_group = QGroupBox("1. 配置文件 (Configuration)")
        config_layout = QVBoxLayout()
        
        self.path_label = QLabel("未选择文件")
        self.path_label.setStyleSheet("color: gray; font-style: italic;")
        
        btn_load = QPushButton("加载 input.json")
        btn_load.clicked.connect(self.load_json_file)
        
        config_layout.addWidget(btn_load)
        config_layout.addWidget(self.path_label)
        config_group.setLayout(config_layout)
        left_panel.addWidget(config_group)

        # 2. 参数显示/修改区 (简化版，只读显示关键参数)
        info_group = QGroupBox("2. 当前参数 (Read-Only)")
        info_layout = QFormLayout()
        self.lbl_part = QLabel("-")
        self.lbl_q = QLabel("-")
        self.lbl_moment_center = QLabel("-")
        
        info_layout.addRow("部件名称:", self.lbl_part)
        info_layout.addRow("动压 (Q):", self.lbl_q)
        info_layout.addRow("目标矩心:", self.lbl_moment_center)
        info_group.setLayout(info_layout)
        left_panel.addWidget(info_group)

        # 3. 原始数据输入区
        input_group = QGroupBox("3. 输入原始数据 (Source Frame)")
        input_layout = QFormLayout()
        
        # 原始力 F
        self.input_fx = QLineEdit("100.0")
        self.input_fy = QLineEdit("0.0")
        self.input_fz = QLineEdit("500.0")
        
        # 原始力矩 M
        self.input_mx = QLineEdit("0.0")
        self.input_my = QLineEdit("20.0")
        self.input_mz = QLineEdit("0.0")
        
        input_layout.addRow("Fx (N):", self.input_fx)
        input_layout.addRow("Fy (N):", self.input_fy)
        input_layout.addRow("Fz (N):", self.input_fz)
        input_layout.addRow("---", QLabel("---"))
        input_layout.addRow("Mx (N·m):", self.input_mx)
        input_layout.addRow("My (N·m):", self.input_my)
        input_layout.addRow("Mz (N·m):", self.input_mz)
        
        input_group.setLayout(input_layout)
        left_panel.addWidget(input_group)

        # 4. 计算按钮
        self.btn_calc = QPushButton("执行计算 (Calculate)")
        self.btn_calc.setFixedHeight(50)
        self.btn_calc.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold; font-size: 14px;")
        self.btn_calc.clicked.connect(self.run_calculation)
        self.btn_calc.setEnabled(False) # 加载配置前禁用
        left_panel.addWidget(self.btn_calc)
        
        left_panel.addStretch() # 弹簧，把上面内容顶上去

        # === 右侧面板：结果展示 ===
        right_panel = QVBoxLayout()
        main_layout.addLayout(right_panel, stretch=2) # 右侧宽一点

        result_group = QGroupBox("4. 计算结果 (Results)")
        result_layout = QVBoxLayout()
        
        self.result_display = QTextEdit()
        self.result_display.setReadOnly(True)
        self.result_display.setFont(QFont("Consolas", 11)) # 等宽字体方便对齐
        self.result_display.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")
        
        result_layout.addWidget(self.result_display)
        result_group.setLayout(result_layout)
        right_panel.addWidget(result_group)

    def load_json_file(self):
        """选择并加载 JSON 文件"""
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 input.json", os.getcwd(), "JSON Files (*.json)")
        if not file_path:
            return

        try:
            self.path_label.setText(os.path.basename(file_path))
            # 1. 调用我们写的 data_loader
            self.current_config = load_data(file_path)
            
            # 2. 初始化物理引擎
            self.processor = AeroCalculator(self.current_config)
            
            # 3. 更新界面显示
            tgt = self.current_config.target_config
            self.lbl_part.setText(tgt.part_name)
            self.lbl_q.setText(str(tgt.q))
            self.lbl_moment_center.setText(str(tgt.moment_center))
            
            # 4. 启用计算按钮
            self.btn_calc.setEnabled(True)
            self.status_log(f"✅ 成功加载配置: {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "加载错误", f"无法解析配置文件:\n{str(e)}")
            self.btn_calc.setEnabled(False)

    def run_calculation(self):
        """获取输入 -> 调用物理引擎 -> 显示结果"""
        if not self.processor:
            return

        try:
            # 1. 获取用户输入的原始数据
            f_raw = [float(self.input_fx.text()), float(self.input_fy.text()), float(self.input_fz.text())]
            m_raw = [float(self.input_mx.text()), float(self.input_my.text()), float(self.input_mz.text())]
            
            # 2. 调用 physics 模块进行核心计算
            # 这一步就是我们之前费劲写的核心逻辑在发挥作用
            # TODO: 注意：`AeroCalculator` 当前实现提供 `process_frame()` 并返回 `AeroResult` dataclass，
            # 而这里调用 `process_single_point()` 并期望得到 dict。需要统一 GUI 与 core 的 API（添加适配器或修改调用方），
            # 并为此添加单元/集成测试以保证端到端行为一致。
            result = self.processor.process_single_point(f_raw, m_raw)
            
            # 3. 格式化输出
            self.display_results(f_raw, m_raw, result)
            
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字 (Fx, Fy 等)")
        except Exception as e:
            QMessageBox.critical(self, "计算错误", str(e))

    def display_results(self, f_raw, m_raw, result):
        """美化输出结果到文本框"""
        f_new = result['Force_TargetFrame']
        m_new = result['Moment_TargetFrame']
        c = result['Coefficients']
        
        text = "========================================\n"
        text += f"   计算报告 (Part: {self.current_config.target_config.part_name})\n"
        text += "========================================\n\n"
        
        text += "[1] 原始输入 (Source Frame):\n"
        text += f"    Force : [{f_raw[0]:.2f}, {f_raw[1]:.2f}, {f_raw[2]:.2f}] N\n"
        text += f"    Moment: [{m_raw[0]:.2f}, {m_raw[1]:.2f}, {m_raw[2]:.2f}] N·m\n\n"
        
        text += "[2] 变换后结果 (Target Frame):\n"
        text += f"    Force : [{f_new[0]:.2f}, {f_new[1]:.2f}, {f_new[2]:.2f}] N\n"
        text += f"    Moment: [{m_new[0]:.2f}, {m_new[1]:.2f}, {m_new[2]:.2f}] N·m\n"
        text += "    (包含坐标旋转 + 移轴效应)\n\n"
        
        text += "[3] 无量纲气动系数 (Coefficients):\n"
        text += "    -----------------------------\n"
        text += f"    Cx: {c['Cx']:.6f}   Cl: {c['Cl']:.6f}\n"
        text += f"    Cy: {c['Cy']:.6f}   Cm: {c['Cm']:.6f}\n"
        text += f"    Cz: {c['Cz']:.6f}   Cn: {c['Cn']:.6f}\n"
        text += "    -----------------------------\n"
        
        self.result_display.setText(text)

    def status_log(self, msg):
        self.result_display.append(f"[{msg}]")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 设置全局字体，让界面好看点
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    window = AeroTransformWindow()
    window.show()
    sys.exit(app.exec())