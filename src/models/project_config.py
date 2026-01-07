"""
项目配置数据模型，替代原始字典操作。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from .part import Part


@dataclass
class ProjectConfig:
    """包含 Source/Target 部件集合。"""

    source_parts: Dict[str, Part] = field(default_factory=dict)
    target_parts: Dict[str, Part] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "Source": {
                "Parts": [p.to_dict() for p in self.source_parts.values()]
            },
            "Target": {
                "Parts": [p.to_dict() for p in self.target_parts.values()]
            },
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ProjectConfig":
        src_parts = {}
        tgt_parts = {}

        source = (data or {}).get("Source", {})
        for p in source.get("Parts", []) or []:
            part = Part.from_dict(p)
            src_parts[part.name] = part

        target = (data or {}).get("Target", {})
        for p in target.get("Parts", []) or []:
            part = Part.from_dict(p)
            tgt_parts[part.name] = part

        return cls(source_parts=src_parts, target_parts=tgt_parts)

    @classmethod
    def from_file(cls, path: Path) -> "ProjectConfig":
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return cls.from_dict(raw)

    def to_file(self, path: Path) -> None:
        path = Path(path)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)
