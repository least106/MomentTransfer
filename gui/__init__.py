"""
MomentTransfer GUI 包
模块化 GUI 组件
"""

# 导出主要组件类
# Mpl3DCanvas 已改为延迟加载，在 visualization_manager 中按需导入
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
import importlib.util
from pathlib import Path

# 添加父目录到路径以便导入 gui.py
_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# 在这里我们不导入 IntegratedAeroGUI，因为 gui.py 会导入此包，可能造成循环导入
# 用户应该直接从 gui 模块导入：from gui import IntegratedAeroGUI

__all__ = [
    # UI 组件
    # 'Mpl3DCanvas' - 已改为延迟加载，不在此导出
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
    # 主窗口
    'IntegratedAeroGUI',
]

# 延迟导入 IntegratedAeroGUI 以避免循环导入
def __getattr__(name):
    """支持延迟导入 IntegratedAeroGUI"""
    if name == 'IntegratedAeroGUI':
        # 延迟导入以避免 gui.py 加载此包时的循环依赖
        import importlib
        gui_module = importlib.import_module('gui')  # 这会导致问题
        # 改为直接执行以避免递归
        import sys
        # 删除自己使得 re-import 使用 gui.py 而非包
        pkg_name = __name__
        if pkg_name in sys.modules and hasattr(sys.modules[pkg_name], '__path__'):
            # 尝试加载 gui.py 而不是包
            parent_dir = str(Path(__file__).parent.parent)
            gui_py_path = Path(parent_dir) / "gui.py"
            if gui_py_path.exists():
                spec = importlib.util.spec_from_file_location("_gui_module", str(gui_py_path))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod.IntegratedAeroGUI
        raise ImportError(f"Cannot import IntegratedAeroGUI")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


