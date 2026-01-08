"""
兼容性管理器 - 处理旧代码的向后兼容性
"""
import logging

logger = logging.getLogger(__name__)


class CompatibilityManager:
    """管理旧代码兼容性，提供属性别名和信号连接"""
    
    def __init__(self, main_window):
        self.main_window = main_window
    
    def setup_legacy_aliases(self):
        """设置旧属性别名以保持向后兼容"""
        try:
            # Source 面板控件引用
            self.main_window.grp_source = self.main_window.source_panel
            self.main_window.src_part_name = self.main_window.source_panel.part_name_input
            self.main_window.cmb_source_parts = self.main_window.source_panel.part_selector
            self.main_window.src_coord_table = self.main_window.source_panel.coord_table
            self.main_window.btn_add_source_part = self.main_window.source_panel.btn_add_part
            self.main_window.btn_remove_source_part = self.main_window.source_panel.btn_remove_part
            
            # Target 面板控件引用
            self.main_window.tgt_part_name = self.main_window.target_panel.part_name_input
            self.main_window.cmb_target_parts = self.main_window.target_panel.part_selector
            self.main_window.tgt_coord_table = self.main_window.target_panel.coord_table
            self.main_window.btn_add_target_part = self.main_window.target_panel.btn_add_part
            self.main_window.btn_remove_target_part = self.main_window.target_panel.btn_remove_part
            
            # Config 面板按钮引用
            self.main_window.btn_load = self.main_window.config_panel.btn_load
            self.main_window.btn_save = self.main_window.config_panel.btn_save
            self.main_window.btn_apply = self.main_window.config_panel.btn_apply
            
            # 初始化当前 Part 名称
            self.main_window._current_source_part_name = "Global"
            self.main_window._current_target_part_name = "TestModel"
            
            logger.debug("兼容性别名设置完成")
        except Exception as e:
            logger.error(f"设置兼容性别名失败: {e}", exc_info=True)
    
    def handle_legacy_signals(self):
        """处理旧信号连接"""
        try:
            # Part 选择信号（通过 wrapper 连接到旧方法）
            self.main_window.source_panel.partSelected.connect(
                self.main_window._on_source_part_changed_wrapper
            )
            self.main_window.target_panel.partSelected.connect(
                self.main_window._on_target_part_changed_wrapper
            )
            
            logger.debug("兼容性信号连接完成")
        except Exception as e:
            logger.error(f"连接兼容性信号失败: {e}", exc_info=True)
