# CLI 与 GUI 批处理逻辑统一说明

**更新日期**: 2026年1月12日  
**状态**: 已统一核心逻辑

## 修改摘要

本次修改统一了命令行界面（CLI）和图形用户界面（GUI）的批处理逻辑，使两者在数据处理、计算器创建和行过滤方面保持一致。

## 主要变化

### 1. **每文件独立的 Calculator 支持** ✅

**之前**：CLI 使用全局唯一的 `calculator`，所有文件共用同一个 source/target part

**现在**：
- CLI 和 GUI 都支持为每个文件指定独立的 `source_part` 和 `target_part`
- 若未指定，则使用全局配置或自动推断（若唯一）
- 两者都在 `process_single_file()` 中创建文件级别的 `AeroCalculator`

**代码位置**：
- CLI: `batch.py` 第 550-582 行
- GUI: `gui/batch_thread.py` 第 304-345 行

### 2. **行级过滤支持** ✅

**之前**：只有 GUI 支持行选择，CLI 无此功能

**现在**：
- `process_single_file()` 新增 `selected_rows` 参数
- 若提供了行选择集合，则按索引过滤数据
- 当使用行选择时，表头自动检测被禁用（保持索引一致性）

**代码位置**：
- CLI: `batch.py` 第 633-640 行
- GUI: `gui/batch_thread.py` 第 225-235 行

### 3. **表头自动检测** ✅

**之前**：只有 GUI 支持

**现在**：
- CLI 也支持自动检测可能的表头行
- 若首行中 ≥60% 的映射列为非数值，则跳过该行
- 行选择时禁用（避免索引混乱）

**代码位置**：
- CLI: `batch.py` 第 641-667 行
- GUI: `gui/batch_thread.py` 第 237-265 行

### 4. **批处理函数签名扩展** ✅

```python
# 重命名：run_batch_processing_v2 → run_batch_processing
def process_single_file(file_path, calculator, config, output_dir, project_data=None,
                       source_part=None, target_part=None, selected_rows=None)
```

`run_batch_processing()` 支持以下参数：
```python
file_source_target_map: dict = None   # {str(file_path): {"source": str, "target": str}}
file_row_selection: dict = None       # {str(file_path): set([row_idx, ...])}
```

## 功能对比表

| 功能 | CLI | GUI |
|------|-----|-----|
| **每文件独立 calculator** | ✅ 新增 | ✅ 已有 |
| **文件级 source/target** | ✅ 新增 | ✅ 已有 |
| **行选择过滤** | ✅ 新增 | ✅ 已有 |
| **表头自动检测** | ✅ 新增 | ✅ 已有 |
| **特殊格式处理** | ✅ 已有 | ✅ 已有 |
| **列映射配置** | ✅ 已有 | ✅ 已有 |
| **非数值处理策略** | ✅ 已有 | ✅ 已有 |

## 使用场景

### CLI 中的应用

CLI 已完全参数化，示例用法：

```bash
# 基础批处理
python -m batch data/input.json ./data/examples

# 单帧计算（已参数化，无交互式提示）
python -m cli run -c data/input.json --force 100 0 -50 --moment 0 500 0
```

**关键变化**：
- 删除了所有 `input()` 调用
- 删除了 `prompt_vector()` 交互函数
- 删除了确认对话框和文件选择对话框
- 所有参数均在命令行明确指定

## 向后兼容性说明

⚠️ **此版本为清理旧兼容代码，删除了所有交互式提示和版本标记**
- 所有参数现在均为可选，默认值为 `None`
- 删除了 `run_batch_processing_v2()` 版本标记，统一使用 `run_batch_processing()`
- 若未指定文件级参数，使用全局 calculator（原有行为）
- CLI 现已完全参数化，不再有交互式输入提示

## 单元测试建议

建议补充以下测试用例：

1. **per-file calculator**
   - 测试同一批次中不同文件使用不同 source/target
   - 验证计算结果的独立性

2. **行过滤**
   - 测试部分行选择与全量行的结果差异
   - 验证索引与 GUI 预览一致

3. **表头检测**
   - 测试有表头与无表头的 CSV 识别准确性
   - 测试行选择时表头检测是否正确禁用

## 相关文件修改清单

- ✅ `batch.py` - 核心批处理函数修改
- ✅ `gui/batch_thread.py` - 已兼容（无需改动）
- ✅ `gui/batch_manager.py` - 已兼容（无需改动）
- ⚠️ `cli.py` - 可选扩展（暴露新参数）

## 后续改进方向

1. **CLI 参数扩展**：为 `batch.py` 的 `main()` 添加 `--file-mapping` 和 `--row-selection` 参数

2. **验证增强**：在 `process_single_file()` 中添加更详细的日志，便于调试多文件、多 part 场景

3. **并行支持**：确保并行处理（`workers > 1`）模式也能正确应用文件级参数

---

**测试建议**：在 CLI 中使用 `--non-interactive` 模式测试核心逻辑，确保与 GUI 行为一致。
