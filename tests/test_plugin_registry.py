import types
from pathlib import Path

from src import plugin as plugin_mod


class SimpleCoordPlugin(plugin_mod.CoordSystemPlugin):
    @property
    def metadata(self):
        return plugin_mod.PluginMetadata(
            name="simple_coord",
            version="0.0",
            author="test",
            description="",
            plugin_type="coord_system",
        )

    def get_coordinate_system(self, name: str):
        return {"origin": [0, 0, 0], "x_axis": [1, 0, 0], "y_axis": [0, 1, 0], "z_axis": [0, 0, 1]}

    def list_coordinate_systems(self):
        return ["default"]


def test_plugin_registry_register_and_unregister():
    reg = plugin_mod.PluginRegistry()
    p = SimpleCoordPlugin()
    reg.register(p)
    assert reg.get_plugin("simple_coord") is p
    assert "simple_coord" in reg.list_plugins("coord_system")
    reg.unregister("simple_coord")
    assert reg.get_plugin("simple_coord") is None


def test_instantiate_and_register_with_module(tmp_path):
    # 创建一个模拟模块并提供 create_plugin
    module = types.ModuleType("fake_module")

    class M(plugin_mod.CoordSystemPlugin):
        @property
        def metadata(self):
            return plugin_mod.PluginMetadata(
                name="mod_coord",
                version="0.1",
                author="t",
                description="",
                plugin_type="coord_system",
            )

        def get_coordinate_system(self, name: str):
            return {"origin": [0, 0, 0]}

        def list_coordinate_systems(self):
            return ["m"]

    def create_plugin():
        return M()

    module.create_plugin = create_plugin

    registry = plugin_mod.PluginRegistry()
    loader = plugin_mod.PluginLoader(registry)
    plugin = loader._instantiate_and_register(module, Path(str(tmp_path / "fake.py")))
    assert plugin is not None
    assert registry.get_plugin("mod_coord") is plugin
