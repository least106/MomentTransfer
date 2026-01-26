# 特殊格式文件双层映射系统（V2）

## 概述

本文档描述特殊格式文件（.mtfmt/.mtdata）的双层映射系统实现，该系统允许用户手动选择每个内部部件对应的 source part 和 target part。

## 改动背景

### 原有限制

在之前的实现中，特殊格式文件的处理存在以下限制：

1. **单层映射**：只能指定内部部件名到 target part 的映射，source part 固定使用内部部件名本身
2. **缺少手动选择**：无法为内部部件手动指定不同的 source part
3. **布局不统一**：特殊格式文件与常规文件的 UI 布局不一致

### 新需求

1. **允许手动选择 source part**：用户可以为每个内部部件选择配置中的任意 source part
2. **智能自动推断**：系统自动推断合适的 source part，使用与 target part 相同的匹配逻辑
3. **统一布局**：文件列表中特殊格式和常规文件使用统一的 source/target 选择器布局

## 核心数据结构

### 映射结构

新的映射结构使用两层嵌套：

```python
{
    "internal_part_name": {
        "source": "配置中的Source Part名称",
        "target": "配置中的Target Part名称"
    }
}
```

**示例**：
```python
{
    "quanji": {
        "source": "Global",
        "target": "quanji"
    },
    "BODY": {
        "source": "Global",
        "target": "BODY"
    },
    "WIHG": {
        "source": "Global",
        "target": "WIHG"
    }
}
```

### 向后兼容

系统保持对旧格式的兼容，旧格式会在处理时自动转换：

**旧格式**：
```python
{
    "quanji": "quanji",
    "BODY": "BODY"
}
```

**转换逻辑**（在 `batch_thread.py` 中）：
```python
if isinstance(mapping_data, str):
    # 旧格式：只有target，source默认为内部部件名
    target_val = mapping_data.strip()
    if target_val:
        part_target_mapping[internal_part] = target_val
```

## 智能推断逻辑

### Source Part 推断

实现位置：`gui/batch_manager_files.py:_infer_source_part()`

**推断策略**（按优先级）：

1. **完全匹配**：内部部件名在 source_names 中存在同名项
2. **不区分大小写**：忽略大小写后匹配
3. **规范化匹配**：移除特殊字符（保留字母数字和中文）后匹配
4. **默认全局**：以上都不匹配时，选择 "Global"（如果存在）

**代码示例**：
```python
def _infer_source_part(manager, part_name: str, source_names: list) -> Optional[str]:
    """智能推测source part（内部部件名与配置中的source part对应关系）。"""
    result = None
    pn = (part_name or "").strip()
    if pn:
        sns = [str(x) for x in (source_names or []) if str(x).strip()]
        if sns:
            # 策略1：完全匹配
            if pn in sns:
                result = pn
            else:
                # 策略2：不区分大小写
                pn_lower = pn.lower()
                ci = [s for s in sns if s.lower() == pn_lower]
                if len(ci) == 1:
                    result = ci[0]
                else:
                    # 策略3：规范化匹配...
                    # 策略4：未找到则默认选择"Global"
                    if result is None and "Global" in sns:
                        result = "Global"
    return result
```

### Target Part 推断

实现位置：`gui/batch_manager_files.py:_infer_target_part()`

使用与 source part 相同的匹配策略，但不提供 "Global" 回退。

## UI 布局变更

### 特殊格式文件节点结构

```
📄 data.mtfmt [状态]
  ├─ quanji
  │   ├─ [source下拉] [target下拉]
  │   └─ 📊 数据预览表格
  ├─ BODY
  │   ├─ [source下拉] [target下拉]
  │   └─ 📊 数据预览表格
  └─ WIHG
      ├─ [source下拉] [target下拉]
      └─ 📊 数据预览表格
```

### 实现细节

**位置**：`gui/batch_manager_files.py:_create_special_part_node()`

1. 创建内部部件名节点
2. 创建选择器容器行（使用 QHBoxLayout）
3. 添加 source combo box（左侧）
4. 添加 target combo box（右侧）
5. 绑定变更事件以更新映射和状态

**代码片段**：
```python
# 创建容器widget来放置两个下拉框
selector_widget = QWidget()
selector_layout = QHBoxLayout(selector_widget)
selector_layout.setContentsMargins(0, 0, 0, 0)
selector_layout.setSpacing(4)

# Source部分选择器
source_combo = QComboBox()
source_combo.addItem("(选择source)", "")
for sn in source_names:
    source_combo.addItem(str(sn), str(sn))

# Target部分选择器
target_combo = QComboBox()
target_combo.addItem("(选择target)", "")
for tn in target_names:
    target_combo.addItem(str(tn), str(tn))

selector_layout.addWidget(source_combo, 1)
selector_layout.addWidget(target_combo, 1)
```

## 验证逻辑

### 文件状态验证

实现位置：`gui/batch_manager.py:_validate_file_config()`

**验证规则**：

1. **未映射**：内部部件缺少 source 或 target 映射
2. **Source 缺失**：选择的 source part 在配置中不存在
3. **Target 缺失**：选择的 target part 在配置中不存在
4. **可处理**：所有部件都有完整有效的 source/target 映射

**状态显示**：
- `✓ 特殊格式(可处理)` - 所有映射完整有效
- `⚠ 未映射: part1, part2` - 部分部件未配置映射
- `⚠ Source缺失: part1→source1` - source part 在配置中不存在
- `⚠ Target缺失: part2→target2` - target part 在配置中不存在

## 处理流程

### 批处理线程处理

**位置**：`gui/batch_thread.py:_process_special_format_branch()`

1. 获取文件的映射数据
2. 解析并拆分为 `part_source_mapping` 和 `part_target_mapping`
3. 处理向后兼容（旧格式自动转换）
4. 调用 `process_special_format_file()` 并传递两个映射

**代码片段**：
```python
part_source_mapping = {}
part_target_mapping = {}
if isinstance(part_mapping, dict):
    for internal_part, mapping_data in part_mapping.items():
        if isinstance(mapping_data, dict):
            source_val = mapping_data.get("source", "").strip()
            target_val = mapping_data.get("target", "").strip()
            if source_val:
                part_source_mapping[internal_part] = source_val
            if target_val:
                part_target_mapping[internal_part] = target_val
        elif isinstance(mapping_data, str):
            # 兼容旧格式
            target_val = mapping_data.strip()
            if target_val:
                part_target_mapping[internal_part] = target_val
```

### 核心处理器

**位置**：`src/special_format_processor.py:_process_single_part()`

新增参数 `part_source_mapping`，用于推断实际的 source part：

```python
def _process_single_part(
    part_name,
    df,
    *,
    file_path,
    project_data,
    output_dir,
    part_target_mapping=None,
    part_source_mapping=None,  # 新增
    part_row_selection=None,
    timestamp_format="%Y%m%d_%H%M%S",
    overwrite=False,
):
    # 推断source part：优先使用part_source_mapping，否则默认=part_name
    source_part = part_name
    try:
        if isinstance(part_source_mapping, dict) and part_source_mapping.get(part_name):
            source_part = part_source_mapping.get(part_name)
    except (TypeError, AttributeError):
        pass
    
    # ... 后续使用 source_part 创建 AeroCalculator
```

## 自动补全机制

### 触发时机

实现位置：`gui/batch_manager.py:_ensure_special_mapping_rows()`

自动补全在以下情况触发：
1. 加载配置文件后
2. 添加新的内部部件时
3. 刷新文件状态时

**注意**：只补全未设置的映射，不覆盖用户已手动设置的值。

### 补全逻辑

**位置**：`gui/batch_manager_files.py:_auto_fill_special_mappings()`

```python
def _auto_fill_special_mappings(
    manager, file_path: Path, part_names: list, 
    source_names: list, target_names: list, mapping: dict
) -> bool:
    """自动推断并填充内部部件->source->target映射。"""
    changed = False
    for part_name in part_names:
        # 初始化映射结构
        if part_name not in mapping:
            mapping[part_name] = {"source": "", "target": ""}
            changed = True
        
        # 步骤1：推断source part
        if not mapping[part_name].get("source"):
            inferred_source = _infer_source_part(manager, part_name, source_names)
            if inferred_source:
                mapping[part_name]["source"] = inferred_source
                changed = True
        
        # 步骤2：推断target part（基于已有或推断的source）
        if not mapping[part_name].get("target"):
            source_part = mapping[part_name].get("source", "").strip()
            if source_part:
                inferred_target = _infer_target_part(manager, source_part, target_names)
                if inferred_target:
                    mapping[part_name]["target"] = inferred_target
                    changed = True
    return changed
```

## 缓存管理

### Combo Box 缓存

新增两个缓存字典（在 `BatchManager.__init__` 中）：

```python
# 特殊格式：缓存source part选择器控件
# key: (file_path_str, internal_part_name)
self._special_part_source_combo = {}

# 特殊格式：缓存target part选择器控件
# key: (file_path_str, internal_part_name)
self._special_part_target_combo = {}
```

**用途**：便于在配置变更或刷新时更新下拉框的选项和选中状态。

## 测试验证

### 单元测试

创建临时测试文件 `test_new_mapping.py` 验证 `_infer_source_part()` 逻辑：

**测试用例**：
```python
test_cases = [
    ("quanji", ["Global", "quanji", "BODY"], "quanji"),      # 完全匹配
    ("QuAnJi", ["Global", "quanji", "BODY"], "quanji"),      # 不区分大小写
    ("BODY", ["Global", "quanji", "body"], "body"),          # 不区分大小写
    ("unknown", ["Global", "quanji", "BODY"], "Global"),     # 默认Global
    ("WIHG", ["Global"], "Global"),                          # 默认Global
    ("", ["Global", "quanji"], None),                        # 空名称
]
```

**测试结果**：✅ 所有测试用例通过

### 集成测试建议

1. **加载特殊格式文件**
   - 确认文件树正确显示内部部件节点
   - 验证 source/target 下拉框正确填充配置项

2. **自动推断测试**
   - 加载配置后验证 source/target 自动补全
   - 验证匹配策略的优先级（完全匹配 > 大小写不敏感 > 规范化 > Global）

3. **手动选择测试**
   - 手动更改 source/target 选择
   - 验证映射数据正确更新
   - 验证文件状态正确刷新

4. **批处理测试**
   - 执行批处理并检查输出文件
   - 验证每个部件使用正确的 source/target 配置
   - 验证输出文件命名和内容正确

5. **向后兼容测试**
   - 加载使用旧格式映射的项目
   - 验证自动转换正确工作
   - 验证处理结果与预期一致

## 修改的文件列表

### 核心修改

1. **gui/batch_manager.py**
   - 添加 `_special_part_source_combo` 和 `_special_part_target_combo` 缓存
   - 修改 `_validate_file_config()` 验证逻辑以检查双层映射
   - 更新 `_ensure_special_mapping_rows()` 传递 source_names 参数
   - 修改 `_auto_fill_special_mappings()` 签名以接受 source_names

2. **gui/batch_manager_files.py**
   - 新增 `_infer_source_part()` 函数实现智能推断
   - 重写 `_auto_fill_special_mappings()` 支持双层推断
   - 完全重构 `_create_special_part_node()` 创建双下拉框 UI

3. **gui/batch_thread.py**
   - 添加映射解析逻辑拆分 source/target
   - 实现向后兼容的旧格式转换
   - 传递 `part_source_mapping` 给处理器

4. **src/special_format_processor.py**
   - 添加 `part_source_mapping` 参数到所有相关函数
   - 更新 `ProcessOptions` dataclass 添加新字段
   - 修改 `_process_single_part()` 支持 source part 推断

## 未来改进方向

1. **批量操作**：支持一键为所有部件应用相同的 source/target 规则
2. **映射模板**：保存和加载常用的映射配置模板
3. **可视化**：图形化显示 internal_part -> source -> target 的映射关系
4. **验证增强**：提前检测循环依赖或冲突的映射配置
5. **性能优化**：对大量部件的文件优化 UI 渲染和映射计算

## 总结

本次改动实现了特殊格式文件的双层映射系统，主要优势：

✅ **灵活性**：用户可完全控制每个内部部件的 source 和 target 选择  
✅ **智能化**：自动推断逻辑减少手动配置工作量  
✅ **一致性**：UI 布局与常规文件保持统一  
✅ **兼容性**：完全向后兼容旧格式映射  
✅ **健壮性**：完善的验证逻辑确保配置正确性

---

**文档版本**：1.0  
**创建日期**：2025-01-28  
**作者**：least10  
**最后更新**：2025-01-28
