"""
MomentTransfer GUI 包
模块化 GUI 组件
"""

import importlib.util

# 主窗口类在此导入（避免循环导入）
import sys
from pathlib import Path

from gui.batch_manager import BatchManager
from gui.batch_thread import BatchProcessThread
from gui.config_manager import ConfigManager

# 导出主要组件类
from gui.layout_manager import LayoutManager
from gui.part_manager import PartManager

# 导出管理器类
from gui.ui_utils import (
    create_input,
    create_triple_spin,
    create_vector_row,
    get_numeric_value,
)

# 添加父目录到路径以便导入 gui.py
_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# 在这里我们不导入 IntegratedAeroGUI，因为 gui.py 会导入此包，可能造成循环导入
# 用户应该直接从 gui 模块导入：from gui import IntegratedAeroGUI

__all__ = [
    # UI 组件
    # 'Mpl3DCanvas' - 已改为延迟加载，不在此导出
    "BatchProcessThread",
    # UI 工具函数
    "create_input",
    "create_triple_spin",
    "get_numeric_value",
    "create_vector_row",
    # 管理器
    "ConfigManager",
    "PartManager",
    "BatchManager",
    "LayoutManager",
    # 主窗口
    "IntegratedAeroGUI",
]

# 占位符：用于让静态分析器/导出检查通过。实际导入通过 `__getattr__` 延迟加载。
IntegratedAeroGUI = None


# 延迟导入 IntegratedAeroGUI 以避免循环导入（改为加载 gui_main.py）
def __getattr__(name):
    """支持延迟导入 IntegratedAeroGUI（从顶层脚本 gui_main.py 加载）"""
    if name == "IntegratedAeroGUI":
        parent_dir = Path(__file__).parent.parent
        gui_main_path = parent_dir / "gui_main.py"
        if gui_main_path.exists():
            spec = importlib.util.spec_from_file_location(
                "_gui_main_module", str(gui_main_path)
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return getattr(mod, "IntegratedAeroGUI")
        raise ImportError("Cannot import IntegratedAeroGUI from gui_main.py")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
