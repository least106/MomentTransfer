"""
示例脚本: per_file_config_demo.py

用途：展示如何为每个 CSV 文件计算最终的 `BatchConfig`。

说明：
- 该脚本保留并演示了完整的侧车/目录/registry 查找逻辑，供教学与调试使用。
- 在生产路径中我们建议 **禁用** 侧车（请在 `src/cli_helpers.py::resolve_file_format` 中使用 `enable_sidecar=False`），
  并使用统一的 global config。

用法示例:
    python examples/per_file_config_demo.py /path/to/data_dir --registry registry.db

"""

import argparse
from copy import deepcopy
from pathlib import Path

from src.cli_helpers import (BatchConfig, _merge_batch_config,
                             load_format_from_file)
from src.format_registry import get_format_for_file


def resolve_file_format_demo(
    file_path: str,
    global_cfg: BatchConfig,
    *,
    registry_db: str = None,
    sidecar_suffixes=(".format.json", ".json"),
    dir_default_name="format.json",
) -> BatchConfig:
    """教学用：为单个文件解析最终 BatchConfig（包含侧车、目录、registry 查找）。"""
    p = Path(file_path)
    cfg = deepcopy(global_cfg)

    # 0) registry
    if registry_db:
        try:
            reg_fmt = get_format_for_file(registry_db, file_path)
            if reg_fmt:
                local = load_format_from_file(str(reg_fmt))
                _merge_batch_config(cfg, local)
                return cfg
        except Exception as e:
            print(f"Registry lookup failed: {e}")

    # 1) file-sidecar
    stem = p.stem
    parent = p.parent
    for suf in sidecar_suffixes:
        candidate = parent / f"{stem}{suf}"
        if candidate.exists():
            print(f"Using sidecar: {candidate}")
            local = load_format_from_file(str(candidate))
            _merge_batch_config(cfg, local)
            return cfg

    # 2) dir-default
    dir_candidate = parent / dir_default_name
    if dir_candidate.exists():
        print(f"Using dir default: {dir_candidate}")
        local = load_format_from_file(str(dir_candidate))
        _merge_batch_config(cfg, local)
        return cfg

    return cfg


def main():
    p = argparse.ArgumentParser()
    p.add_argument("data_dir", help="包含 CSV 的目录")
    p.add_argument("--registry", help="可选 registry 数据库路径 (.sqlite)")
    args = p.parse_args()

    base_cfg = BatchConfig()
    base_cfg.sample_rows = 5

    data_dir = Path(args.data_dir)
    for fp in sorted(data_dir.glob("*.csv")):
        print(f"Processing {fp.name}")
        cfg = resolve_file_format_demo(str(fp), base_cfg, registry_db=args.registry)
        print(f"  -> sample_rows: {cfg.sample_rows}\n")


if __name__ == "__main__":
    main()
