"""
MomentTransfer GUI 包
模块化 GUI 组件
"""

# 导出主要组件类
from gui.canvas import Mpl3DCanvas
from gui.dialogs import ColumnMappingDialog, ExperimentalDialog
from gui.batch_thread import BatchProcessThread

# 导出管理器类
from gui.ui_utils import create_input, create_triple_spin, get_numeric_value, create_vector_row
from gui.config_manager import ConfigManager
from gui.part_manager import PartManager
from gui.batch_manager import BatchManager
from gui.visualization_manager import VisualizationManager
from gui.layout_manager import LayoutManager

# 主窗口类在此导入（避免循环导入）
import sys
from pathlib import Path

# 添加父目录到路径以便导入 gui.py
_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# 在这里我们不导入 IntegratedAeroGUI，因为 gui.py 会导入此包，可能造成循环导入
# 用户应该直接从 gui 模块导入：from gui import IntegratedAeroGUI

__all__ = [
    # UI 组件
    'Mpl3DCanvas',
    'ColumnMappingDialog',
    'ExperimentalDialog',
    'BatchProcessThread',
    # UI 工具函数
    'create_input',
    'create_triple_spin',
    'get_numeric_value',
    'create_vector_row',
    # 管理器
    'ConfigManager',
    'PartManager',
    'BatchManager',
    'VisualizationManager',
    'LayoutManager',
]


