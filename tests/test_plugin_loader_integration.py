from pathlib import Path

from src import plugin as plugin_mod


def write_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def test_load_plugin_from_file_success(tmp_path):
    registry = plugin_mod.PluginRegistry()
    loader = plugin_mod.PluginLoader(registry)

    good = tmp_path / "good_plugin.py"
    good.write_text(
        """
from src.plugin import CoordSystemPlugin, PluginMetadata

class GoodPlugin(CoordSystemPlugin):
    @property
    def metadata(self):
        return PluginMetadata(name='good', version='1', author='t', description='', plugin_type='coord_system')

    def get_coordinate_system(self, name: str):
        return {'origin':[0,0,0], 'x_axis':[1,0,0], 'y_axis':[0,1,0], 'z_axis':[0,0,1]}

    def list_coordinate_systems(self):
        return ['default']

def create_plugin():
    return GoodPlugin()
""",
        encoding="utf-8",
    )

    plugin = loader.load_plugin_from_file(good)
    assert plugin is not None
    assert registry.get_plugin("good") is plugin


def test_load_plugin_from_file_failure_cases(tmp_path):
    registry = plugin_mod.PluginRegistry()
    loader = plugin_mod.PluginLoader(registry)

    # no factory
    no_factory = tmp_path / "no_factory.py"
    no_factory.write_text("# empty plugin file\n", encoding="utf-8")
    assert loader.load_plugin_from_file(no_factory) is None

    # factory raises
    bad = tmp_path / "bad_plugin.py"
    bad.write_text(
        """
def create_plugin():
    raise RuntimeError('boom')
""",
        encoding="utf-8",
    )
    assert loader.load_plugin_from_file(bad) is None


def test_load_plugins_from_directory(tmp_path):
    registry = plugin_mod.PluginRegistry()
    loader = plugin_mod.PluginLoader(registry)

    # create two valid plugins
    p1 = tmp_path / "p1.py"
    p1.write_text(
        """
from src.plugin import CoordSystemPlugin, PluginMetadata
class P1(CoordSystemPlugin):
    @property
    def metadata(self):
        return PluginMetadata(name='p1', version='0', author='t', description='', plugin_type='coord_system')
    def get_coordinate_system(self, name: str):
        return {'origin':[0,0,0]}
    def list_coordinate_systems(self):
        return ['a']
def create_plugin():
    return P1()
""",
        encoding="utf-8",
    )

    p2 = tmp_path / "p2.py"
    p2.write_text(
        """
from src.plugin import CoordSystemPlugin, PluginMetadata
class P2(CoordSystemPlugin):
    @property
    def metadata(self):
        return PluginMetadata(name='p2', version='0', author='t', description='', plugin_type='coord_system')
    def get_coordinate_system(self, name: str):
        return {'origin':[0,0,0]}
    def list_coordinate_systems(self):
        return ['b']
def create_plugin():
    return P2()
""",
        encoding="utf-8",
    )

    plugins = loader.load_plugins_from_directory(tmp_path)
    names = [p.metadata.name for p in plugins]
    assert "p1" in names and "p2" in names
