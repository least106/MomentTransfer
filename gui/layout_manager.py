"""
布局管理模块 - 处理窗口布局的响应和调整
"""
import logging
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget, QApplication

logger = logging.getLogger(__name__)


class LayoutManager:
    """布局管理器 - 管理 UI 布局的动态调整"""
    
    BUTTON_LAYOUT_THRESHOLD = 720
    
    def __init__(self, gui_instance):
        """初始化布局管理器"""
        self.gui = gui_instance
        self._current_threshold = self.BUTTON_LAYOUT_THRESHOLD
    
    def update_button_layout(self, threshold=None):
        """根据窗口宽度在网格中切换按钮位置
        
        参数 `threshold` 的单位为像素（px）。当窗口宽度大于或等于阈值时，
        按钮按一行两列排列；当宽度小于阈值时，按钮按两行单列排列（便于窄屏显示）。
        
        默认阈值 720px 由类常量 ``BUTTON_LAYOUT_THRESHOLD`` 提供，
        可根据实际布局和用户屏幕密度微调该值。
        """
        if threshold is None:
            threshold = self._current_threshold
        else:
            self._current_threshold = threshold
        
        if not hasattr(self.gui, 'btn_widget'):
            return
        
        try:
            w = self.gui.width()
        except Exception:
            w = threshold

        # 取出已有按钮实例
        btns = [
            getattr(self.gui, 'btn_config_format', None),
            getattr(self.gui, 'btn_batch', None),
            getattr(self.gui, 'btn_cancel', None)
        ]

        # 安全地移除旧布局但保留按钮 widget 本身，避免双重删除或内存泄漏
        # 我们不再替换已有的 layout 对象（self.gui.btn_grid），而是复用并清空它的内容
        extracted_widgets = []
        grid = getattr(self.gui, 'btn_grid', None)
        if grid is None:
            grid = QGridLayout()
            grid.setSpacing(8)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            self.gui.btn_grid = grid
        else:
            # 从现有 grid 中提取 widget（不删除 layout 本身）
            while grid.count():
                item = grid.takeAt(0)
                wdg = item.widget()
                if wdg:
                    try:
                        grid.removeWidget(wdg)
                    except Exception:
                        logger.debug("grid.removeWidget failed", exc_info=True)
                    extracted_widgets.append(wdg)
            # 重新确保列伸缩
            try:
                grid.setColumnStretch(0, 1)
                grid.setColumnStretch(1, 1)
            except Exception:
                logger.debug("grid.setColumnStretch failed", exc_info=True)

        if w >= threshold:
            # 宽窗口：一行两列
            # 如果我们刚才从旧布局提取了 widgets，优先使用它们以保持实例不变
            if extracted_widgets:
                if len(extracted_widgets) >= 1 and extracted_widgets[0]:
                    grid.addWidget(extracted_widgets[0], 0, 0)
                if len(extracted_widgets) >= 2 and extracted_widgets[1]:
                    grid.addWidget(extracted_widgets[1], 0, 1)
            else:
                if btns[0]:
                    grid.addWidget(btns[0], 0, 0)
                if btns[1]:
                    grid.addWidget(btns[1], 0, 1)
            self.gui._btn_orientation = 'horizontal'
        else:
            # 窄窗口：两行布局（第一列靠左）
            if extracted_widgets:
                if len(extracted_widgets) >= 1 and extracted_widgets[0]:
                    grid.addWidget(extracted_widgets[0], 0, 0)
                if len(extracted_widgets) >= 2 and extracted_widgets[1]:
                    grid.addWidget(extracted_widgets[1], 1, 0)
            else:
                if btns[0]:
                    grid.addWidget(btns[0], 0, 0)
                if btns[1]:
                    grid.addWidget(btns[1], 1, 0)
            self.gui._btn_orientation = 'vertical'

        # 将清理后的 grid 重新应用到 btn_widget（若尚未设置）
        if self.gui.btn_widget.layout() is not grid:
            try:
                self.gui.btn_widget.setLayout(grid)
            except Exception:
                logger.debug("btn_widget.setLayout failed", exc_info=True)
        
        # 确保按钮容器在布局更改后更新尺寸与几何，以免在窗口状态切换时被临时挤出视口
        try:
            self.gui.btn_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            # 尝试通过标准方式强制刷新布局：使布局失效并激活布局，更新几何信息
            cw = self.gui.centralWidget()
            if cw:
                layout = cw.layout()
                if layout:
                    layout.invalidate()
                    layout.activate()
                cw.updateGeometry()
                for child in cw.findChildren(QWidget):
                    child.updateGeometry()
            try:
                QApplication.processEvents()
            except Exception:
                logger.debug("QApplication.processEvents failed in update_button_layout", exc_info=True)
        except Exception:
            logger.debug("update_button_layout failed during size policy/layout refresh", exc_info=True)
    
    def on_resize_event(self, event):
        """窗口大小改变事件"""
        try:
            # 调用更新按钮布局
            self.update_button_layout()
            
            # 刷新所有布局
            self.refresh_layouts()
        
        except Exception as e:
            logger.debug(f"处理 resize 事件失败: {e}")
    
    def on_show_event(self, event):
        """窗口显示事件 - 初始化布局"""
        try:
            self.update_button_layout()
            self.refresh_layouts()
        
        except Exception as e:
            logger.debug(f"处理 show 事件失败: {e}")
    
    def refresh_layouts(self):
        """刷新所有布局 - 强制重新计算和绘制"""
        try:
            if hasattr(self.gui, 'layout'):
                layout = self.gui.layout()
                if layout:
                    layout.update()
                    layout.activate()
                    logger.debug("主布局已刷新")
            
            # 刷新各个面板的布局
            for attr_name in ['create_config_panel', 'create_operation_panel']:
                if hasattr(self.gui, attr_name):
                    try:
                        # 访问对应的 panel 对象并更新
                        panel_attr = attr_name.replace('create_', '')
                        if hasattr(self.gui, panel_attr):
                            panel = getattr(self.gui, panel_attr)
                            if hasattr(panel, 'layout'):
                                l = panel.layout()
                                if l:
                                    l.update()
                    except Exception:
                        pass
        
        except Exception as e:
            logger.debug(f"刷新布局失败: {e}")
