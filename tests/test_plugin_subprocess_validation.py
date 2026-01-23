from pathlib import Path

from src.plugin import PluginLoader, PluginRegistry


def write(p: Path, s: str):
    p.write_text(s, encoding="utf-8")


def test_validate_plugin_file_success(tmp_path):
    p = tmp_path / "good_plugin.py"
    write(
        p,
        """
from src.plugin import BasePlugin, PluginMetadata

class Good(BasePlugin):
    @property
    def metadata(self):
        return PluginMetadata(name='good', version='1.0', author='x', description='', plugin_type='output')

def create_plugin():
    return Good()
""",
    )

    loader = PluginLoader(PluginRegistry())
    proc = loader._validate_plugin_file_subprocess(p, timeout=5)
    assert proc is not None
    assert getattr(proc, "returncode", None) == 0
    assert "good" in (proc.stdout or "")


def test_validate_plugin_file_no_factory(tmp_path):
    p = tmp_path / "no_factory.py"
    write(p, "# no create_plugin here\nVAR = 1\n")

    loader = PluginLoader(PluginRegistry())
    proc = loader._validate_plugin_file_subprocess(p, timeout=3)
    assert proc is not None
    assert getattr(proc, "returncode", None) == 4
    assert (proc.stdout or "").strip().startswith("NO_FACTORY")


def test_validate_plugin_file_factory_raises(tmp_path):
    p = tmp_path / "bad_factory.py"
    write(
        p,
        """
def create_plugin():
    raise RuntimeError('boom')
""",
    )

    loader = PluginLoader(PluginRegistry())
    proc = loader._validate_plugin_file_subprocess(p, timeout=3)
    assert proc is not None
    # factory 抛异常时子进程应以非零退出，validator 捕获并打印 traceback
    assert getattr(proc, "returncode", None) != 0
    assert (proc.stderr or "") != ""


def test_validate_plugin_file_timeout(tmp_path):
    p = tmp_path / "slow.py"
    write(
        p,
        """
import time
def create_plugin():
    time.sleep(2)
    return None
""",
    )

    loader = PluginLoader(PluginRegistry())
    # 使用很短的超时以触发 TimeoutExpired 分支
    proc = loader._validate_plugin_file_subprocess(p, timeout=0.1)
    assert proc is None
