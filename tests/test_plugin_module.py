import sys
from pathlib import Path

import pytest

from src import plugin as plugin_mod


class DummyCoordPlugin(plugin_mod.CoordSystemPlugin):
    @property
    def metadata(self):
        return plugin_mod.PluginMetadata(
            name="dummy",
            version="0.1",
            author="test",
            description="d",
            plugin_type="coord_system",
        )

    def get_coordinate_system(self, name: str):
        return {"origin": [0, 0, 0], "x_axis": [1, 0, 0], "y_axis": [0, 1, 0], "z_axis": [0,0,1]}

    def list_coordinate_systems(self):
        return ["dummy"]


def test_registry_register_and_unregister():
    reg = plugin_mod.PluginRegistry()
    p = DummyCoordPlugin()
    reg.register(p)
    assert "dummy" in reg.list_plugins()
    assert reg.get_coord_system_plugin("dummy") is p
    reg.unregister("dummy")
    assert reg.get_plugin("dummy") is None


def write_plugin_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")
    return path


def test_loader_load_valid_plugin(tmp_path):
    # valid plugin file with create_plugin returning a CoordSystemPlugin
    code = '''
from src.plugin import CoordSystemPlugin, PluginMetadata
class P(CoordSystemPlugin):
    @property
    def metadata(self):
        return PluginMetadata(name='tmpplug', version='1', author='x', description='d', plugin_type='coord_system')
    def get_coordinate_system(self, name):
        return {'origin':[0,0,0], 'x_axis':[1,0,0], 'y_axis':[0,1,0], 'z_axis':[0,0,1]}
    def list_coordinate_systems(self):
        return ['tmpplug']
def create_plugin():
    return P()
'''
    f = write_plugin_file(tmp_path / "good_plugin.py", code)
    reg = plugin_mod.PluginRegistry()
    loader = plugin_mod.PluginLoader(reg)
    plugin = loader.load_plugin_from_file(f)
    assert plugin is not None
    assert reg.get_plugin('tmpplug') is plugin


def test_loader_missing_create_factory(tmp_path):
    code = "# no factory here\nX = 1\n"
    f = write_plugin_file(tmp_path / "nofactory.py", code)
    reg = plugin_mod.PluginRegistry()
    loader = plugin_mod.PluginLoader(reg)
    assert loader.load_plugin_from_file(f) is None


def test_loader_create_returns_non_base(tmp_path):
    code = "def create_plugin():\n    return 123\n"
    f = write_plugin_file(tmp_path / "badreturn.py", code)
    reg = plugin_mod.PluginRegistry()
    loader = plugin_mod.PluginLoader(reg)
    assert loader.load_plugin_from_file(f) is None


def test_loader_create_raises(tmp_path):
    code = "def create_plugin():\n    raise ValueError('boom')\n"
    f = write_plugin_file(tmp_path / "raise.py", code)
    reg = plugin_mod.PluginRegistry()
    loader = plugin_mod.PluginLoader(reg)
    assert loader.load_plugin_from_file(f) is None


def test_plugin_manager_get_and_clear():
    mgr = plugin_mod.PluginManager()
    reg = mgr.get_registry()
    assert isinstance(reg, plugin_mod.PluginRegistry)
    # register dummy
    reg.register(DummyCoordPlugin())
    assert 'dummy' in reg.list_plugins()
    mgr.clear()
    # after clear, asking for registry returns a new instance
    newreg = mgr.get_registry()
    assert newreg is not reg
