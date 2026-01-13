from pathlib import Path
import textwrap
import sys


# 确保在导入 src 包之前将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import plugin as pl


class SimpleCoordPlugin(pl.CoordSystemPlugin):
    def __init__(self, name="coord1"):
        self._meta = pl.PluginMetadata(
            name=name,
            version="0.1",
            author="me",
            description="d",
            plugin_type="coord_system",
        )
        self.shutdown_called = False

    @property
    def metadata(self):
        return self._meta

    def get_coordinate_system(self, name: str):
        if name == "test":
            return {
                "origin": [0, 0, 0],
                "x_axis": [1, 0, 0],
                "y_axis": [0, 1, 0],
                "z_axis": [0, 0, 1],
            }
        return None

    def list_coordinate_systems(self):
        return ["test"]

    def shutdown(self):
        self.shutdown_called = True


class SimpleOutputPlugin(pl.OutputPlugin):
    def __init__(self, name="out1"):
        self._meta = pl.PluginMetadata(
            name=name,
            version="0.1",
            author="me",
            description="d",
            plugin_type="output",
        )
        self.written = False

    @property
    def metadata(self):
        return self._meta

    def write(self, data, output_path: Path, **kwargs):
        Path(output_path).write_text("ok")
        self.written = True

    def get_supported_formats(self):
        return [".csv"]


def test_registry_register_and_query_and_unregister():
    reg = pl.PluginRegistry()
    p = SimpleCoordPlugin(name="coordA")
    reg.register(p)

    assert "coordA" in reg.list_plugins()
    assert reg.get_coord_system_plugin("coordA") is p

    # unregister
    reg.unregister("coordA")
    assert reg.get_plugin("coordA") is None


def test_register_overwrite_logs(monkeypatch):
    reg = pl.PluginRegistry()
    p1 = SimpleCoordPlugin(name="dup")
    p2 = SimpleCoordPlugin(name="dup")
    called = {}
    # monkeypatch logger.warning to capture call (accept any args/kwargs)
    monkeypatch.setattr(
        pl.logger,
        "warning",
        lambda *args, **kwargs: called.setdefault("w", args or kwargs),
    )
    reg.register(p1)
    reg.register(p2)
    assert "w" in called


def test_plugin_loader_loads_file(tmp_path: Path):
    registry = pl.PluginRegistry()
    loader = pl.PluginLoader(registry)

    # create a plugin file with create_plugin
    code = textwrap.dedent(
        """
    from src.plugin import BasePlugin, CoordSystemPlugin, PluginMetadata
    class MyP(CoordSystemPlugin):
        def __init__(self):
            self._meta = PluginMetadata(name='filep', version='1', author='a', description='d', plugin_type='coord_system')
        @property
        def metadata(self):
            return self._meta
        def get_coordinate_system(self, name):
            return None
        def list_coordinate_systems(self):
            return []
    def create_plugin():
        return MyP()
    """
    )

    f = tmp_path / "myplugin.py"
    f.write_text(code, encoding="utf-8")

    plugin = loader.load_plugin_from_file(f)
    assert plugin is not None
    assert registry.get_plugin("filep") is plugin


def test_plugin_loader_missing_file_returns_none(tmp_path: Path):
    registry = pl.PluginRegistry()
    loader = pl.PluginLoader(registry)
    res = loader.load_plugin_from_file(tmp_path / "noexist.py")
    assert res is None


def test_load_plugins_from_directory_skips_private_and_loads(tmp_path: Path):
    registry = pl.PluginRegistry()
    loader = pl.PluginLoader(registry)

    # create two files: _private.py and good.py
    (tmp_path / "_private.py").write_text("x=1")
    (tmp_path / "good.py").write_text(
        textwrap.dedent(
            """
    from src.plugin import BasePlugin, OutputPlugin, PluginMetadata, Path
    class G(OutputPlugin):
        def __init__(self):
            self._meta = PluginMetadata(name='goodp', version='1', author='a', description='d', plugin_type='output')
        @property
        def metadata(self):
            return self._meta
        def write(self, data, output_path: Path, **kwargs):
            pass
        def get_supported_formats(self):
            return ['.x']
    def create_plugin():
        return G()
    """
        )
    )

    plugins = loader.load_plugins_from_directory(tmp_path)
    # should load only good.py
    assert any(p.metadata.name == "goodp" for p in plugins)


def test_get_plugin_registry_singleton():
    a = pl.get_plugin_registry()
    b = pl.get_plugin_registry()
    assert a is b
