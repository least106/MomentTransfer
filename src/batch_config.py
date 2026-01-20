"""批处理相关配置与格式解析（从拆分的模块中提取）
"""

from copy import deepcopy


class BatchConfig:  # pylint: disable=R0902,R0903
    """批处理配置类（供 batch.py 使用，简化为固定表头语义）。"""

    def __init__(self):
        self.skip_rows = 0
        self.name_template = "{stem}_result_{timestamp}.csv"
        self.timestamp_format = "%Y%m%d_%H%M%S"
        self.overwrite = False
        self.treat_non_numeric = "zero"
        self.sample_rows = 5


def resolve_file_format(
    _file_path: str,
    global_cfg: BatchConfig,
) -> BatchConfig:
    """为单个数据文件返回全局配置的深拷贝（保留以前模块的行为）。

    参数：
        file_path: 数据文件路径（用于日志或未来的 sidecar 查找）
        global_cfg: 全局批处理配置

    返回值：
        global_cfg 的深拷贝
    """
    return deepcopy(global_cfg)
