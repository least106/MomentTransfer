"""src.config 子包初始化。

为兼容性提供对顶层模块 `src/config.py` 中部分符号的延迟代理。

我们通过按文件路径加载顶层的 `config.py`，以避免与包导入路径产生循环依赖。
"""

import importlib.util
import sys
from pathlib import Path

# 定位顶层模块文件 src/config.py
_root_config_path = Path(__file__).resolve().parent.parent / "config.py"
spec = importlib.util.spec_from_file_location("src._config_mod", str(_root_config_path))
_root_mod = importlib.util.module_from_spec(spec)
# 将新模块挂到 sys.modules 以便其他导入可以复用
sys.modules["src._config_mod"] = _root_mod
spec.loader.exec_module(_root_mod)

# 转发常用符号
get_config = _root_mod.get_config
set_config = _root_mod.set_config
load_config_from_file = _root_mod.load_config_from_file
reset_config = _root_mod.reset_config

__all__ = [
	"get_config",
	"set_config",
	"load_config_from_file",
	"reset_config",
]
