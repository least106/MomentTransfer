"""
初始化管理器 - 负责主窗口的 UI 初始化与管理器设置
"""
import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PySide6.QtCore import Qt, QTimer

from gui.panels import ConfigPanel, OperationPanel
from gui.config_manager import ConfigManager
from gui.part_manager import PartManager
from gui.batch_manager import BatchManager
from gui.visualization_manager import VisualizationManager
from gui.layout_manager import LayoutManager
from gui.log_manager import LoggingManager

logger = logging.getLogger(__name__)

# 主题常量
LAYOUT_MARGIN = 12
LAYOUT_SPACING = 8


class InitializationManager:
    """管理主窗口的初始化流程"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self._is_initializing = True
    
    def setup_ui(self):
        """初始化 UI 组件"""
        try:
            central_widget = QWidget()
            self.main_window.setCentralWidget(central_widget)
            main_layout = QVBoxLayout(central_widget)
            main_layout.setContentsMargins(LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN)
            main_layout.setSpacing(LAYOUT_SPACING)
            
            # 创建配置面板
            config_panel = self.main_window.create_config_panel()
            
            # 创建操作面板（使用 main_window 的方法）
            operation_panel = self.main_window.create_operation_panel()
            self.main_window.operation_panel = operation_panel
            
            # 存储引用以便管理器访问
            self.main_window.config_panel = config_panel
            
            # 创建主分割器
            splitter = QSplitter(Qt.Vertical)
            splitter.addWidget(config_panel)
            splitter.addWidget(operation_panel)
            
            try:
                splitter.setSizes([380, 420])
            except Exception:
                logger.debug("splitter.setSizes failed (non-fatal)", exc_info=True)
            
            main_layout.addWidget(splitter)
            self.main_window.statusBar().showMessage("就绪 - 请加载或创建配置")
            
            logger.info("UI 组件初始化成功")
        except Exception as e:
            logger.error(f"UI 初始化失败: {e}", exc_info=True)
            raise
    
    def setup_managers(self):
        """初始化所有管理器"""
        try:
            # 必须在创建面板之后初始化管理器
            config_panel = getattr(self.main_window, 'config_panel', None)
            if not config_panel:
                raise RuntimeError("config_panel 未初始化")
            
            self.main_window.config_manager = ConfigManager(self.main_window, config_panel)
            self.main_window.part_manager = PartManager(self.main_window)
            self.main_window.batch_manager = BatchManager(self.main_window)
            self.main_window.visualization_manager = VisualizationManager(self.main_window)
            self.main_window.layout_manager = LayoutManager(self.main_window)
            
            logger.info("所有管理器初始化成功")
        except Exception as e:
            logger.error(f"管理器初始化失败: {e}", exc_info=True)
            # 继续运行，即使管理器初始化失败
    
    def setup_logging(self):
        """设置日志系统"""
        try:
            logging_manager = LoggingManager(self.main_window)
            logging_manager.setup_gui_logging()
        except Exception as e:
            logger.debug(f"GUI logging setup failed (non-fatal): {e}", exc_info=True)
    
    def finalize_initialization(self):
        """完成初始化 - 在 showEvent 后调用"""
        def _finalize():
            self._is_initializing = False
            self.main_window._is_initializing = False
            logger.debug("初始化完成")
        
        # 延迟完成标志，避免 showEvent 期间的弹窗
        QTimer.singleShot(150, _finalize)
    
    def trigger_initial_layout_update(self):
        """触发初始布局更新"""
        try:
            QTimer.singleShot(50, self.main_window.update_button_layout)
            QTimer.singleShot(120, self.main_window._force_layout_refresh)
        except Exception:
            logger.debug("Initial layout update scheduling failed", exc_info=True)
