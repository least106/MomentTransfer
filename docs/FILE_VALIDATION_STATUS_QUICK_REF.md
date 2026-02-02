# 文件验证状态符号 - 快速参考

在 MomentTransfer 中，文件树显示的状态符号帮助您快速了解每个文件的处理准备情况。

## 符号一览表

| 符号 | 含义 | 状态 | 操作 |
|------|------|------|------|
| ✓ | 已就绪 | 配置正确，可处理 | 无需操作 |
| ⚠ | 警告 | 配置不完整或有问题 | 查看详情，补充配置 |
| ❓ | 未验证 | 验证失败或异常 | 检查日志找出原因 |

## 常见状态信息

### 对号 (✓) - 文件已就绪

```
✓ 特殊格式(可处理)     → 特殊格式已完整配置
✓ 特殊格式(待配置)     → 文件有效，但项目还未配置
✓ 可处理                → 普通格式，Source/Target 已选
✓ 格式正常(待配置)     → 文件有效，项目还未配置
```

### 警告 (⚠) - 需要处理

```
⚠ 未映射: part1       → 这些 parts 还没有配置映射
⚠ Source缺失: src1    → 选择的 Source 不在项目中
⚠ Target缺失: tgt1    → 选择的 Target 不在项目中
⚠ 未选择 Source/Target → 还没有选择数据源和目标
```

### 问号 (❓) - 需要调查

```
❓ 未验证              → 系统无法验证文件状态
```

## 快速处理指南

### 当看到 ⚠ 时

1. **读一下状态信息** - 了解具体什么配置有问题
2. **编辑项目配置** - 添加缺失的 parts 或 Source/Target
3. **重新扫描文件** - 刷新验证状态

### 当看到 ❓ 时

1. **打开应用日志**
2. **查找对应文件的错误信息**
3. **根据错误提示调整配置或检查文件**

## 在代码中使用

```python
from gui import (
    STATUS_SYMBOL_READY,        # "✓"
    STATUS_SYMBOL_WARNING,      # "⚠"
    STATUS_SYMBOL_UNVERIFIED,   # "❓"
    get_status_symbol_help,
    show_status_symbol_help,
)

# 显示帮助对话框
show_status_symbol_help(window)

# 生成状态消息
status = f"{STATUS_SYMBOL_READY} 可处理"
```

## 更多信息

- **详细说明**：[FILE_VALIDATION_STATUS.md](FILE_VALIDATION_STATUS.md)
- **开发指南**：[FILE_VALIDATION_STATUS_DEV.md](FILE_VALIDATION_STATUS_DEV.md)

