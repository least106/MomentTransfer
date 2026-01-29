import textwrap

from src.plugin import PluginLoader, PluginRegistry


def test_load_plugin_from_file(tmp_path):
    # 创建一个最小可用的插件文件
    plugin_code = textwrap.dedent(
        """
from src.plugin import BasePlugin, PluginMetadata

class DummyPlugin(BasePlugin):
    @property
    def metadata(self):
        return PluginMetadata(
            name='dummy',
            version='0.1',
            author='test',
            description='',
            plugin_type='coord_system',
        )

def create_plugin():
    return DummyPlugin()
"""
    )

    p = tmp_path / "dummy_plugin.py"
    p.write_text(plugin_code, encoding="utf-8")

    registry = PluginRegistry()
    loader = PluginLoader(registry)

    plugin = loader.load_plugin_from_file(p)
    assert plugin is not None
    assert "dummy" in registry.list_plugins()
