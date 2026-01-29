from pathlib import Path

from src.plugin import PluginLoader, PluginRegistry


def write(p: Path, s: str):
    p.write_text(s, encoding="utf-8")


def test_dynamic_import_syntax_error(tmp_path):
    p = tmp_path / "bad_syntax.py"
    write(p, "def oops(:\n")
    loader = PluginLoader(PluginRegistry())
    mod = loader._dynamic_import_module(p)
    assert mod is None


def test_instantiate_no_create(tmp_path):
    p = tmp_path / "mod_no_create.py"
    write(p, "class C:\n    pass\n")
    loader = PluginLoader(PluginRegistry())
    mod = loader._dynamic_import_module(p)
    assert mod is not None
    plugin = loader._instantiate_and_register(mod, p)
    assert plugin is None


def test_instantiate_returns_non_plugin(tmp_path):
    p = tmp_path / "mod_returns_nonplugin.py"
    write(
        p,
        """
def create_plugin():
    return {'not':'a plugin'}
""",
    )
    loader = PluginLoader(PluginRegistry())
    mod = loader._dynamic_import_module(p)
    plugin = loader._instantiate_and_register(mod, p)
    assert plugin is None


def test_instantiate_create_raises(tmp_path):
    p = tmp_path / "mod_create_raises.py"
    write(
        p,
        """
def create_plugin():
    raise TypeError('fail')
""",
    )
    loader = PluginLoader(PluginRegistry())
    mod = loader._dynamic_import_module(p)
    plugin = loader._instantiate_and_register(mod, p)
    assert plugin is None


def test_instantiate_register_raises(tmp_path, monkeypatch):
    p = tmp_path / "mod_good.py"
    write(
        p,
        """
from src.plugin import BasePlugin, PluginMetadata

class Good(BasePlugin):
    @property
    def metadata(self):
        return PluginMetadata(
            name='g', version='1', author='', description='', plugin_type='output'
        )

def create_plugin():
    return Good()
""",
    )
    registry = PluginRegistry()
    loader = PluginLoader(registry)

    # 模拟 register 抛异常
    def bad_register(plugin):
        raise RuntimeError("boom")

    monkeypatch.setattr(registry, "register", bad_register)

    mod = loader._dynamic_import_module(p)
    plugin = loader._instantiate_and_register(mod, p)
    assert plugin is None
