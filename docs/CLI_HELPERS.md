# CLI Helpers 文档

本文件描述 `src/cli_helpers.py` 中提供的辅助函数与使用示例。

函数概览

- `configure_logging(log_file: str | None, verbose: bool) -> logging.Logger`
  - 配置并返回名为 `batch` 的 logger。

- `load_project_calculator(config_path: str)`
  - 加载几何/项目配置并返回 `(project_data, AeroCalculator)`。
  - 在加载失败时抛出 `ValueError`，便于 CLI 层友好处理错误。

- `BatchConfig` / `load_format_from_file(path: str) -> BatchConfig`
  - `BatchConfig` 为批处理工具使用的配置结构。
  - `load_format_from_file` 从 JSON 文件解析 `BatchConfig`，会对空文件或无效 JSON 抛出 `ValueError`。

- `get_user_file_format()`
  - 交互式请求用户输入数据文件格式（跳过行、列索引映射、保留列等）。

示例

非交互模式下从格式文件加载：

```python
from src.cli_helpers import load_format_from_file
cfg = load_format_from_file('data/format_example.json')
```

交互式模式：

```python
from src.cli_helpers import get_user_file_format
cfg = get_user_file_format()
```

测试

已为 `load_format_from_file` 与 `get_user_file_format` 增加单元测试，位于 `tests/test_cli_helpers.py`。
