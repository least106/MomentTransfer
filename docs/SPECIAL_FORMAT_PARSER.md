## Special Format Parser — 使用说明（精简版）

目的：解析项目中自定义的批处理表格文件（常见扩展名 `.mtfmt`），把每个 part 的表格数据抽取为 Pandas DataFrame，供 `AeroCalculator` 计算力/力矩系数。

适用场景：当你需要把实验/仿真导出的多段表格（含元数据、part 名、表头与数据块）转为结构化数据并批量计算时使用。

主要行为要点

- 编码回退：优先尝试 `utf-8`，失败回退 `gbk`，最后 `latin-1`（实现：`_read_text_file_lines()`）。
- 行判定：解析器区分元数据、part 名、表头、数据行与汇总行；短中文行会优先识别为 `part` 名而非元数据。
- 表头识别：通过表头关键词（例如 `Alpha`, `CL`, `CD`, `Cm`, `Cx`, `Cy`, `Cz`）进行识别，支持大小写与常见变体。
- 列名规范：使用 `_normalize_column_mapping()` 把常见变体映射为标准列名（示例：`cz_fn`/`czfn`/`cz/fn` → `Cz/FN`，`cmx` → `CMx`）。

主要 API（概要）

- `parse_special_format_file(path: Path) -> Dict[str, pd.DataFrame]`
  - 读取并解析指定文件，返回 {part_name: DataFrame} 映射。DataFrame 列已做名称规范化并尽可能转换为数值类型。

- `process_special_format_file(path: Path, project_data, output_dir: Path) -> Dict`（概要）
  - 对每个被解析到的 part：校验是否在 `project_data` 的目标列表中，检查必要列，使用 `AeroCalculator` 计算，写出带时间戳的 CSV，并在返回的报告中记录每个 part 的 `status`（`success`/`skipped`/`failed`）及原因。

输入/输出要点

- 输入：文本文件（含元数据行、part 名行、表头行、若干数据行），列分隔通常由空格或制表符分隔。解析器会对连续空格做分割容错。
- 输出：按 part 生成 DataFrame；`process_special_format_file` 会输出 CSV 并返回包含每个 part 处理状态的报告字典。

简短示例

```python
from pathlib import Path
from src.special_format_parser import parse_special_format_file

parts = parse_special_format_file(Path('data/example.mtfmt'))
if 'Wing' in parts:
    df = parts['Wing']
    # df 已规范列名，可直接用于后续计算
```

常见问题与解决

- 未识别 part：确保 part 名为单独一行且下一行为表头；避免在 part 名行内混入注释性冒号（`:`）。
- 列名不匹配：在 `_normalize_column_mapping()` 中添加你的列名变体映射，或先预处理文件去除单位后缀（例如 `Cz/FN(%)` → `Cz/FN`）。
- 编码错误：若文件使用其他编码，请在 `_read_text_file_lines()` 中增加编码候选项。

扩展建议

- 若需识别更多表头变体，可把候选关键字做为子串匹配而非严格整词匹配；
- 若想记录更多元数据（例如试验条件），可在解析时把元数据块解析为字典并与对应 part 关联返回。

---
文档更新时间：2026-01-09
# Special Format Parser 使用说明

简洁说明 `src/special_format_parser.py` 的目的、主要行为与常见故障排查要点。

## 目的

解析自定义批处理数据文件（推荐扩展名 `.mtfmt`），将每个 part 的表格数据抽取为 Pandas DataFrame，供 `AeroCalculator` 使用。

## 主要要点

- 编码：优先 `utf-8`，失败回退 `gbk`、`latin-1`（实现：`_read_text_file_lines()`）。
- 行判定：区分元数据、part 名、表头、数据行与汇总行；支持短中文 part 名识别。
- 表头与列名：通过关键词识别表头；使用 `_normalize_column_mapping()` 将常见变体映射到标准列名（例如 `cz_fn` → `Cz/FN`，`cmx` → `CMx`）。
- 批处理：`process_special_format_file()` 为每个 part 做列名规范化、必要列检查、调用 `AeroCalculator` 并写出带时间戳的结果 CSV。每个 part 的状态会记录在返回的报告中。

## 快速使用示例

```python
from pathlib import Path
from src.special_format_parser import parse_special_format_file

parts = parse_special_format_file(Path('data/example.mtfmt'))
df = parts.get('Wing')  # 如果存在
```

## 常见故障排查

- 未识别 part：确保 part 名为单独一行且下一行是表头。
- 数据被跳过：确认数据行列数与表头一致且首列为数值。
- 列名未匹配：在 `_normalize_column_mapping()` 中添加新的变体规则或清理单位后缀。

---
更新日期：2026-01-09
