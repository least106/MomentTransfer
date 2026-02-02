# 文件验证状态符号 - 开发者指南

本指南面向想要在代码中使用或引用文件验证状态符号的开发者。

## 导入符号常数

### 方式一：从 gui 包导入

```python
from gui import (
    STATUS_SYMBOL_READY,
    STATUS_SYMBOL_WARNING,
    STATUS_SYMBOL_UNVERIFIED,
    get_status_symbol_help,
    show_status_symbol_help,
)
```

### 方式二：从 managers 模块直接导入

```python
from gui.managers import (
    STATUS_SYMBOL_READY,
    STATUS_SYMBOL_WARNING,
    STATUS_SYMBOL_UNVERIFIED,
    get_status_symbol_help,
    show_status_symbol_help,
)
```

## 符号常数值

```python
STATUS_SYMBOL_READY = "✓"        # 文件已就绪，可以处理
STATUS_SYMBOL_WARNING = "⚠"      # 文件存在问题或配置不完整
STATUS_SYMBOL_UNVERIFIED = "❓"   # 文件状态无法验证
```

## 常见用法

### 1. 生成文件验证状态消息

```python
# 文件已就绪
status_message = f"{STATUS_SYMBOL_READY} 特殊格式(可处理)"

# 文件存在警告
status_message = f"{STATUS_SYMBOL_WARNING} 未映射: part1, part2"

# 文件无法验证
status_message = f"{STATUS_SYMBOL_UNVERIFIED} 未验证"
```

### 2. 显示符号帮助对话框

```python
from gui import show_status_symbol_help

# 在 Qt 窗口中显示帮助对话框
show_status_symbol_help(self)  # self 是 QWidget 实例

# 如果没有父窗口，可以传递 None（会使用 print 输出）
show_status_symbol_help(None)
```

### 3. 获取符号说明文本

```python
from gui import get_status_symbol_help

# 获取格式化的说明文本
help_text = get_status_symbol_help()
print(help_text)

# 输出示例：
# ✓ 对号：文件配置正常且已就绪
#   - 特殊格式：所有 parts 映射已完成
#   - 普通格式：Source/Target 已选择
# ⚠ 警告：文件配置不完整
#   - 缺少必要的部件映射或选择
#   - 选择的配置在项目中不存在
# ❓ 问号：文件状态无法验证
#   - 验证过程出错或数据加载失败
#   - 检查日志以了解具体原因
```

## 在状态检查中使用符号

### 文件验证方法示例

在 `gui/batch_manager.py` 中的现有实现：

```python
def _validate_special_format(self, file_path: Path) -> Optional[str]:
    """对特殊格式文件进行预检，返回状态文本或 None 表示非特殊格式。"""
    try:
        if not looks_like_special_format(file_path):
            status = None
        else:
            # ... 验证逻辑 ...
            if unmapped_parts:
                status = f"{STATUS_SYMBOL_WARNING} 未映射: {', '.join(unmapped_parts)}"
            else:
                status = f"{STATUS_SYMBOL_READY} 特殊格式(可处理)"
    except Exception:
        status = f"{STATUS_SYMBOL_UNVERIFIED} 未验证"
    return status
```

### 使用符号判断文件状态

```python
from gui import STATUS_SYMBOL_READY, STATUS_SYMBOL_WARNING, STATUS_SYMBOL_UNVERIFIED

def can_process_file(status_message: str) -> bool:
    """根据状态消息判断文件是否可以处理。"""
    return status_message.startswith(STATUS_SYMBOL_READY)

def is_file_ready(file_path, status_message):
    """检查特定文件的处理状态。"""
    if status_message.startswith(STATUS_SYMBOL_READY):
        return True  # 文件已就绪
    elif status_message.startswith(STATUS_SYMBOL_WARNING):
        # 记录警告，但继续处理
        logger.warning(f"{file_path}: {status_message}")
        return False
    else:  # STATUS_SYMBOL_UNVERIFIED
        logger.error(f"{file_path}: {status_message}")
        return False
```

## 符号验证逻辑

### 特殊格式文件验证流程

```
输入: 特殊格式文件路径
  ↓
检查文件是否看起来像特殊格式
  ↓ (是)
提取 part 名称
  ↓
检查 parts 映射配置
  ↓
是否所有 parts 都已正确映射？
  ├─ 是 → 返回 ✓ 特殊格式(可处理)
  ├─ 否 → 返回 ⚠ 缺失的具体信息
  └─ 异常 → 返回 ❓ 未验证
```

### 普通格式文件验证流程

```
输入: 普通格式文件路径
  ↓
是否已配置项目数据？
  ├─ 否 → 返回 ✓ 格式正常(待配置)
  ├─ 是 → 检查是否为该文件选择了 Source/Target
  │   ├─ 未选择 → 返回 ⚠ 未选择 Source/Target
  │   ├─ 选择的 Source/Target 不存在 → 返回 ⚠ Source/Target 缺失
  │   ├─ 都正确 → 返回 ✓ 可处理
  │   └─ 异常 → 返回 ❓ 未验证
```

## 测试符号功能

### 单元测试示例

```python
import pytest
from gui.managers import (
    STATUS_SYMBOL_READY,
    STATUS_SYMBOL_WARNING,
    STATUS_SYMBOL_UNVERIFIED,
)

def test_status_symbols_are_valid():
    """确保符号常数被正确定义。"""
    assert STATUS_SYMBOL_READY == "✓"
    assert STATUS_SYMBOL_WARNING == "⚠"
    assert STATUS_SYMBOL_UNVERIFIED == "❓"

def test_get_status_symbol_help():
    """测试获取符号帮助文本。"""
    from gui.managers import get_status_symbol_help
    
    help_text = get_status_symbol_help()
    assert STATUS_SYMBOL_READY in help_text
    assert STATUS_SYMBOL_WARNING in help_text
    assert STATUS_SYMBOL_UNVERIFIED in help_text
```

## 最佳实践

1. **始终使用符号常数**：不要硬编码符号（如 `"✓"` 或 `"⚠"`），使用 `STATUS_SYMBOL_*` 常数以保证一致性。

2. **提供详细的状态消息**：状态消息应包含符号和具体的问题描述：
   ```python
   # 好：提供具体信息
   f"{STATUS_SYMBOL_WARNING} 未映射: part1, part2"
   
   # 不好：只有符号
   STATUS_SYMBOL_WARNING
   ```

3. **记录验证失败原因**：当返回 `❓ 未验证` 时，应在日志中记录异常信息。

4. **在 UI 中添加提示**：为文件树项添加工具提示，展示完整的状态消息。

5. **定期测试验证逻辑**：确保验证逻辑在各种场景下都能正确工作。

## 相关文件

- 符号定义和辅助函数：`gui/managers.py`
- 文件验证实现：`gui/batch_manager.py`
  - `_validate_special_format()` - 特殊格式验证
  - `_determine_part_selection_status()` - 普通格式验证
  - `_evaluate_file_config_non_special()` - 非特殊格式评估
- 用户文档：`docs/FILE_VALIDATION_STATUS.md`
- 导出声明：`gui/__init__.py`

## 故障排除

### 符号不显示正确

1. 检查终端/编辑器是否支持 Unicode 字符
2. 确保使用的是 UTF-8 编码
3. 验证 Python 环境支持 Unicode（3.8+ 应该没有问题）

### 帮助对话框不显示

1. 检查是否正确导入 `show_status_symbol_help`
2. 确保传递了有效的 QWidget 实例作为 parent
3. 查看应用日志以获取错误信息

