"""
可视化管理模块 - 处理 3D 可视化相关功能
"""
import logging
import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMessageBox
from gui.canvas import Mpl3DCanvas
from gui.ui_utils import get_numeric_value

logger = logging.getLogger(__name__)


class VisualizationManager:
    """可视化管理器 - 管理 3D 坐标系可视化"""
    
    def __init__(self, gui_instance):
        """初始化可视化管理器"""
        self.gui = gui_instance
    
    def toggle_visualization(self):
        """切换可视化窗口"""
        try:
            if hasattr(self.gui, 'visualization_window') and self.gui.visualization_window:
                if self.gui.visualization_window.isVisible():
                    self.gui.visualization_window.hide()
                else:
                    self.gui.visualization_window.show()
            else:
                self.show_visualization()
        except Exception as e:
            logger.error(f"切换可视化失败: {e}")
    
    def show_visualization(self):
        """显示 3D 可视化窗口"""
        try:
            # 读取当前配置
            source_orig = [
                get_numeric_value(self.gui.src_ox),
                get_numeric_value(self.gui.src_oy),
                get_numeric_value(self.gui.src_oz)
            ]
            source_basis = np.array([
                [get_numeric_value(self.gui.src_xx), get_numeric_value(self.gui.src_xy), get_numeric_value(self.gui.src_xz)],
                [get_numeric_value(self.gui.src_yx), get_numeric_value(self.gui.src_yy), get_numeric_value(self.gui.src_yz)],
                [get_numeric_value(self.gui.src_zx), get_numeric_value(self.gui.src_zy), get_numeric_value(self.gui.src_zz)]
            ])
            
            target_orig = [
                get_numeric_value(self.gui.tgt_ox),
                get_numeric_value(self.gui.tgt_oy),
                get_numeric_value(self.gui.tgt_oz)
            ]
            target_basis = np.array([
                [get_numeric_value(self.gui.tgt_xx), get_numeric_value(self.gui.tgt_xy), get_numeric_value(self.gui.tgt_xz)],
                [get_numeric_value(self.gui.tgt_yx), get_numeric_value(self.gui.tgt_yy), get_numeric_value(self.gui.tgt_yz)],
                [get_numeric_value(self.gui.tgt_zx), get_numeric_value(self.gui.tgt_zy), get_numeric_value(self.gui.tgt_zz)]
            ])
            
            moment_center = [
                get_numeric_value(self.gui.tgt_mcx),
                get_numeric_value(self.gui.tgt_mcy),
                get_numeric_value(self.gui.tgt_mcz)
            ]
            
            # 创建可视化窗口
            self.gui.visualization_window = QWidget()
            self.gui.visualization_window.setWindowTitle(f"3D坐标系可视化 - {self.gui.tgt_part_name.text()}")
            self.gui.visualization_window.resize(800, 600)
            
            layout = QVBoxLayout(self.gui.visualization_window)
            
            # 创建 3D 画布
            self.gui.canvas3d = Mpl3DCanvas(self.gui.visualization_window, width=8, height=6, dpi=100)
            self.gui.canvas3d.plot_systems(source_orig, source_basis, target_orig, target_basis, moment_center)
            
            # 添加说明
            info_label = QLabel(
                "灰色虚线: Source坐标系 | 彩色实线: Target坐标系 | 紫色点: 力矩中心\n"
                "提示: 可以使用鼠标拖动旋转视角"
            )
            try:
                info_label.setObjectName('infoLabel')
            except Exception:
                pass
            
            layout.addWidget(info_label)
            layout.addWidget(self.gui.canvas3d)
            
            self.gui.visualization_window.show()
        
        except ValueError as e:
            QMessageBox.warning(self.gui, "输入错误", f"请检查坐标系数值输入:\n{str(e)}")
        except Exception as e:
            logger.error(f"显示可视化失败: {e}")
            QMessageBox.critical(self.gui, "错误", f"无法显示可视化: {e}")
