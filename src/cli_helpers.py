"""CLI 共享帮助与验证函数

包含日志配置与几何配置加载的公共逻辑，供 `cli.py` 和 `batch.py` 复用。
"""
import logging
import json
from src.data_loader import load_data
from src.physics import AeroCalculator
from pathlib import Path
from datetime import datetime
import numpy as np


class BatchConfig:
    """批处理配置类（供 batch.py 使用，抽取以便复用）。"""
    def __init__(self):
        self.skip_rows = 0
        self.column_mappings = {
            'alpha': None,
            'fx': None,
            'fy': None,
            'fz': None,
            'mx': None,
            'my': None,
            'mz': None,
        }
        self.passthrough_columns = []
        self.chunksize = None
        self.name_template = "{stem}_result_{timestamp}.csv"
        self.timestamp_format = "%Y%m%d_%H%M%S"
        self.overwrite = False
        self.treat_non_numeric = 'zero'
        self.sample_rows = 5


def load_format_from_file(path: str) -> BatchConfig:
    """从 JSON 文件加载 BatchConfig（保留原有行为并提高错误说明）。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"格式文件未找到: {path}")
    with open(p, 'r', encoding='utf-8') as fh:
        text = fh.read()
    if not text or not text.strip():
        raise ValueError(f"格式文件为空或仅包含空白: {path}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"格式文件不是有效的 JSON: {path} -> {e}") from e

    cfg = BatchConfig()
    cfg.skip_rows = int(data.get('skip_rows', 0))
    cols = data.get('columns', {})
    for k in cfg.column_mappings.keys():
        if k in cols:
            v = cols[k]
            cfg.column_mappings[k] = int(v) if v is not None else None
    cfg.passthrough_columns = [int(x) for x in data.get('passthrough', [])]
    if 'chunksize' in data:
        try:
            cfg.chunksize = int(data.get('chunksize'))
        except Exception:
            cfg.chunksize = None
    if 'name_template' in data:
        cfg.name_template = str(data.get('name_template'))
    if 'timestamp_format' in data:
        cfg.timestamp_format = str(data.get('timestamp_format'))
    if 'overwrite' in data:
        cfg.overwrite = bool(data.get('overwrite'))
    if 'treat_non_numeric' in data:
        cfg.treat_non_numeric = str(data.get('treat_non_numeric'))
    if 'sample_rows' in data:
        try:
            cfg.sample_rows = int(data.get('sample_rows'))
        except (TypeError, ValueError):
            cfg.sample_rows = 5
    return cfg


def configure_logging(log_file: str | None, verbose: bool) -> logging.Logger:
    """配置并返回名为 `batch` 的 logger。"""
    log_level = logging.DEBUG if verbose else logging.INFO
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s: %(message)s', handlers=handlers)
    return logging.getLogger('batch')


def load_project_calculator(config_path: str):
    """加载几何/项目配置并返回 (project_data, AeroCalculator)

    若加载失败会抛出 ValueError，消息对用户更友好。
    """
    try:
        project_data = load_data(config_path)
        calculator = AeroCalculator(project_data)
        return project_data, calculator
    except FileNotFoundError as e:
        raise ValueError(f"配置文件未找到: {config_path}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件不是有效的 JSON: {config_path} -> {e}") from e
    except KeyError as e:
        raise ValueError(f"配置文件缺少必要字段: {e}") from e
