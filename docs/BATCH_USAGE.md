**批处理使用说明**

- **文件**: 该批处理工具的实现位于 [batch.py](batch.py)。项目还提供通用 CLI 与配置加载器，见 [cli.py](cli.py) 与 [src/cli_helpers.py](src/cli_helpers.py)。

**简介**
- **用途**: 批量处理目录或单个数据文件，将源坐标系下的力/力矩转换到目标坐标系并计算无量纲气动系数。
- **支持模式**: 串行与并行（通过 `--workers` 指定进程数）、流式分块读取（`--chunksize`）。

**前置条件**
- 激活项目 Conda 环境（推荐）: `conda activate MomentTransfer`。
- 安装依赖（如尚未安装）:

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**快速开始（示例）**
- 单文件处理:

```powershell
python batch.py -c data/input.json -i tmp\file.csv --format-file data/sample.format.json
```

- 目录下所有 CSV（串行）:

```powershell
python batch.py -c data/input.json -i tmp\output -p "*.csv" --format-file data/sample.format.json
```

- 并行处理（4 个进程）:

```powershell
python batch.py -c data/input.json -i tmp\output -p "*.csv" --format-file data/sample.format.json --workers 4
```

- 干运行（仅显示将要处理哪些文件与输出路径）:

```powershell
python batch.py -c data/input.json -i tmp\output -p "*.csv" --format-file data/sample.format.json --dry-run
```

示例：启用 per-file 侧车并继续遇错文件

```powershell
python batch.py -c data/input.json -i tmp\output -p "*.csv" --enable-sidecar --continue-on-error --workers 4
```

**常用选项说明（摘选）**
- **-c, --config**: 必需，项目配置 JSON（例如 `data/input.json`），包含源/目标坐标系定义。
- **-i, --input**: 必需，输入文件或目录路径。
- **-p, --pattern**: 目录模式匹配（例如 `"*.csv"`）。
- **-f, --format-file**: 指定数据格式 JSON（包含 `skip_rows`, `columns`, `passthrough`），在非交互模式下通常必需。
 - **-f, --format-file**: 指定数据格式 JSON（包含 `skip_rows`, `columns`, `passthrough`），在非交互模式下通常必需。
 - **--enable-sidecar**: 启用 per-file 侧车查找（默认关闭），与 `--registry-db` 可配合使用从 registry 查找每个文件对应的格式。
 - **--registry-db**: 实验性选项，指定 registry 数据库文件路径，用于在 registry 中查找文件格式定义。
 - **--continue-on-error**: 在遇到单个文件处理错误时继续处理剩余文件（错误会被记录）。
- **--non-interactive**: 非交互模式（不弹出询问），通常需配合 `--format-file` 或 `--registry-db`。
- **--workers**: 并行进程数，默认为 1（串行）。
- **--chunksize**: 流式读取时的行块大小（节省内存）。
- **--overwrite**: 若输出已存在则覆盖（默认会自动改名避免冲突）。
- **--name-template**: 输出文件名模板，支持 `{stem}`（输入名）与 `{timestamp}` 占位符。
- **--treat-non-numeric**: 非数值处理策略：`zero`（置 0）、`nan`（保留 NaN）或 `drop`（丢弃整行）。
- **--dry-run**: 仅解析并显示将处理的文件与输出路径，不实际写文件。

**数据格式示例（format-file JSON）**

```json
{
  "skip_rows": 0,
  "columns": {"alpha": null, "fx": 0, "fy": 1, "fz": 2, "mx": 3, "my": 4, "mz": 5},
  "passthrough": [6,7]
}
```

- 含义: `skip_rows` 跳过表头行数；`columns` 指定列索引（从 0 开始）；`passthrough` 为要在输出中保留的源列索引列表。

**输出说明**
- 输出为 CSV，包含转换后的力/力矩列（`Fx_new,Fy_new,Fz_new,Mx_new,My_new,Mz_new`）以及气动系数列（`Cx,Cy,Cz,Cl,Cm,Cn`）。
- 默认输出文件名会在模板中包含时间戳以避免冲突，输出路径可由 `-i` 的父目录或命令行中指定的目录决定。

注意：当不传 `--format-file` 且未指定 `--enable-sidecar` 时，批处理会尝试根据文件扩展名与简单规则自动推断格式（对复杂或非标准文件建议显式提供 `--format-file` 或启用侧车）。

**常见问题与调试**
- 如果在非交互模式下运行失败，确认是否提供了 `--format-file` 或 `--registry-db`。
- 当遇到大量文件时建议使用 `--workers` 并配合 `--chunksize` 来降低内存峰值。
- 若输出文件名冲突，默认行为为自动生成带后缀的候选名；使用 `--overwrite` 可直接覆盖旧文件（谨慎）。

**参考文件**
- 批处理实现: [batch.py](batch.py)
- 通用交互 CLI: [cli.py](cli.py)
- 示例配置: [data/input.json](data/input.json), [data/sample.format.json](data/sample.format.json)

**示例工作流（一步步）**
1. 激活环境:

```powershell
conda activate MomentTransfer
```

2. 查看并编辑格式文件（若有特殊列顺序）: 编辑 data/sample.format.json。

3. 运行批处理（示例）:

```powershell
python batch.py -c data/input.json -i my_data_dir -p "*.csv" -f data/sample.format.json --workers 2 --chunksize 10000
```

如需进一步把示例写成脚本或在 CI 中调用，请告诉我你希望的运行方式（Windows PowerShell / Bash / CI），我可以提供可复制的脚本。
