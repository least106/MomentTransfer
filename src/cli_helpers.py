"""CLI 共享帮助与验证函数

包含日志配置与几何配置加载的公共逻辑，供 `cli.py` 和 `batch.py` 复用。
"""
import logging
import json
from src.data_loader import load_data
from src.physics import AeroCalculator
from pathlib import Path
from datetime import datetime



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

    return _batchconfig_from_dict(data)


def _batchconfig_from_dict(data: dict) -> BatchConfig:
    """从字典创建 BatchConfig，供文件/映射加载复用。"""
    cfg = BatchConfig()
    cfg.skip_rows = int(data.get('skip_rows', 0))
    cols = data.get('columns', {}) or {}
    for k in cfg.column_mappings.keys():
        if k in cols:
            v = cols[k]
            cfg.column_mappings[k] = int(v) if v is not None else None
    cfg.passthrough_columns = [int(x) for x in (data.get('passthrough', []) or [])]
    if 'chunksize' in data:
        try:
            cfg.chunksize = int(data.get('chunksize'))
        except (TypeError, ValueError):
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


def load_mapping_file(path: str) -> list:
    """加载 mapping 文件，返回按顺序的映射列表: [{"pattern": str, "config": BatchConfig}, ...]

    映射文件期望一个 JSON 列表，每项包含 `pattern` 字段和 `format` 字典，
    例如: [{"pattern": "*_A.csv", "format": { ... }}, ...]
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"mapping 文件未找到: {path}")
    with open(p, 'r', encoding='utf-8') as fh:
        txt = fh.read()
    if not txt or not txt.strip():
        raise ValueError(f"mapping 文件为空: {path}")
    try:
        data = json.loads(txt)
    except json.JSONDecodeError as e:
        raise ValueError(f"mapping 文件不是有效的 JSON: {path} -> {e}") from e
    if not isinstance(data, list):
        raise ValueError("mapping 文件必须是一个列表，每项包含 'pattern' 和 'format' 字段")
    mappings = []
    for item in data:
        if not isinstance(item, dict) or 'pattern' not in item or 'format' not in item:
            raise ValueError("mapping 文件每项应为对象且包含 'pattern' 和 'format' 字段")
        pat = str(item['pattern'])
        fmt = item['format']
        cfg = _batchconfig_from_dict(fmt)
        mappings.append({'pattern': pat, 'config': cfg})
    return mappings


def get_user_file_format() -> BatchConfig:
    """交互式获取用户数据格式配置，供命令行交互使用。

    虽然这是交互函数，但放在此处可将所有与数据格式相关的逻辑集中。
    """
    print("\n=== 数据格式配置 ===")
    config = BatchConfig()

    # 跳过行数
    skip_input = input("需要跳过的表头行数 (默认0): ").strip()
    if skip_input:
        try:
            config.skip_rows = int(skip_input)
        except ValueError:
            print("[警告] 无效输入，使用默认值0")

    print("\n请指定数据列位置 (从0开始计数，留空表示该列不存在):")

    # 可选的迎角列
    alpha_col = input("  迎角 Alpha 列号: ").strip()
    if alpha_col:
        try:
            config.column_mappings['alpha'] = int(alpha_col)
        except ValueError:
            pass

    # 必需的力和力矩列
    required_mappings = {
        'fx': '轴向力 Fx',
        'fy': '侧向力 Fy', 
        'fz': '法向力 Fz',
        'mx': '滚转力矩 Mx',
        'my': '俯仰力矩 My',
        'mz': '偏航力矩 Mz'
    }

    for key, label in required_mappings.items():
        while True:
            col_input = input(f"  {label} 列号 (必需): ").strip()
            if col_input:
                try:
                    config.column_mappings[key] = int(col_input)
                    break
                except ValueError:
                    print("    [错误] 请输入有效的列号")
            else:
                print("    [错误] 此列为必需项")

    # 需要保留的列
    print("\n需要原样输出的其他列 (用逗号分隔列号，如: 0,1,2):")
    passthrough = input("  列号: ").strip()
    if passthrough:
        try:
            config.passthrough_columns = [int(x.strip()) for x in passthrough.split(',')]
        except ValueError:
            print("[警告] 格式错误，将不保留额外列")

    return config


def resolve_file_format(file_path: str, global_cfg: BatchConfig, *,
                        sidecar_suffixes=('.format.json', '.json'),
                        dir_default_name='format.json',
                        mapping_file: str | None = None) -> BatchConfig:
    """为单个数据文件解析并返回最终的 BatchConfig。

    优先级：file-sidecar（同名） -> 目录级默认（dir_default_name） -> global_cfg（传入的全局配置）。

    返回的是一个 `BatchConfig` 的深拷贝，基于 `global_cfg` ，并由本地配置覆盖相应字段。
    """
    from copy import deepcopy
    from pathlib import Path

    p = Path(file_path)
    # 开始于全局配置的拷贝
    cfg = deepcopy(global_cfg)

    # 1) 检查 file-sidecar
    stem = p.stem
    parent = p.parent
    for suf in sidecar_suffixes:
        candidate = parent / f"{stem}{suf}"
        if candidate.exists():
            local = load_format_from_file(str(candidate))
            # 覆盖 cfg
            _merge_batch_config(cfg, local)
            return cfg

    # 1.5) 若提供 mapping_file，则按映射优先级匹配（mapping 的优先级低于 file-sidecar，但高于 dir-default）
    if mapping_file:
        try:
            mappings = load_mapping_file(mapping_file)
        except Exception:
            mappings = []
        # 尝试按顺序匹配，优先第一项匹配
        import fnmatch
        for m in mappings:
            pat = m.get('pattern')
            # 匹配文件名或相对路径
            if fnmatch.fnmatch(p.name, pat) or fnmatch.fnmatch(str(p), pat):
                _merge_batch_config(cfg, m['config'])
                return cfg

    # 2) 检查目录级默认
    dir_candidate = parent / dir_default_name
    if dir_candidate.exists():
        local = load_format_from_file(str(dir_candidate))
        _merge_batch_config(cfg, local)
        return cfg

    # 3) 否则返回全局（已拷贝）
    return cfg


def _merge_batch_config(dst: BatchConfig, src: BatchConfig) -> None:
    """把 src 的非空/非默认字段合并到 dst（就地修改 dst）。"""
    # 简单策略：直接覆盖字段（列映射中以非 None 值覆盖）
    dst.skip_rows = int(src.skip_rows)
    for k, v in src.column_mappings.items():
        if v is not None:
            dst.column_mappings[k] = int(v)
    if src.passthrough_columns:
        dst.passthrough_columns = list(src.passthrough_columns)
    dst.chunksize = src.chunksize
    dst.name_template = src.name_template
    dst.timestamp_format = src.timestamp_format
    dst.overwrite = bool(src.overwrite)
    dst.treat_non_numeric = src.treat_non_numeric
    dst.sample_rows = int(src.sample_rows)


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
