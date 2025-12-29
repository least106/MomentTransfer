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

---

⚠️ 注意：生产默认行为现在**不启用** per-file 侧车（file-sidecar / directory per-file format / registry lookup）。
- `resolve_file_format` 新增参数 `enable_sidecar: bool = False`，默认返回传入的 `global_cfg` 的拷贝而不做本地查找。

- 新增命令行选项 `--enable-sidecar`（默认关闭）以显式启用 per-file 覆盖；`--registry-db` 仍保留但作为实验性隐藏选项，仅在需要时与 `--enable-sidecar` 一起使用。
- 如果你想为每个 CSV 启用侧车或 registry 覆盖（仅作为示例或调试），请参考示例脚本：`examples/per_file_config_demo.py`，其中包含完整的查找逻辑和说明。
