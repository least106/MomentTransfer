"""JSON 输出插件：将 numpy 数据序列化为 JSON 文件。"""
import json
from pathlib import Path
from typing import Dict, Any, List

import numpy as np

from src.plugin import OutputPlugin, PluginMetadata


class JsonOutputPlugin(OutputPlugin):
    """把计算结果写为 JSON 文件的简单插件实现。"""

    def __init__(self, meta: PluginMetadata):
        self._meta = meta

    @property
    def metadata(self) -> PluginMetadata:
        return self._meta

    def get_supported_formats(self) -> List[str]:
        return ["json"]

    def write(self, data: Dict[str, Any], output_path: Path, **kwargs) -> None:
        serial = {}
        for k, v in data.items():
            if isinstance(v, np.ndarray):
                serial[k] = v.tolist()
            else:
                serial[k] = v

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(serial, fh, ensure_ascii=False, indent=2)


def create_plugin() -> JsonOutputPlugin:
    meta = PluginMetadata(
        name="json_output",
        version="0.1",
        author="example",
        description="将结果写为 JSON 的示例输出插件",
        plugin_type="output",
    )

    return JsonOutputPlugin(meta)
