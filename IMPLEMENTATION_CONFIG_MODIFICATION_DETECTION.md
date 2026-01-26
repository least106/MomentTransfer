# 配置修改检测实现文档

## 概述

本次实现在 MomentTransfer GUI 中添加了**配置修改检测**功能，用户在编辑坐标系配置后，若未保存就启动批处理，系统会自动检测并提示用户保存修改。

## 核心功能

### 1. 修改追踪（ConfigManager）

**文件**: `gui/config_manager.py`

#### 新增属性
- `_config_modified`: 布尔值，追踪配置是否被修改
  - 初值: `False`
  - 加载配置后: 重置为 `False`
  - 保存配置后: 重置为 `False`
  - 编辑坐标系时: 设置为 `True`

#### 修改的方法

**load_config()**
```python
# 在加载成功后重置修改标志
self._config_modified = False

# 连接坐标系面板的修改信号
self.gui.source_panel.valuesChanged.connect(
    lambda: self.set_config_modified(True)
)
self.gui.target_panel.valuesChanged.connect(
    lambda: self.set_config_modified(True)
)
```

**save_config()**
```python
# 在保存成功后重置修改标志
# 支持直接覆盖保存和另存为两种情况
self._config_modified = False
```

#### 新增方法

```python
def is_config_modified(self) -> bool:
    """返回配置是否被修改"""
    return self._config_modified

def set_config_modified(self, modified: bool):
    """设置配置修改状态"""
    self._config_modified = modified
```

### 2. 批处理前检测（MainWindow）

**文件**: `gui/main_window.py`

#### 修改的方法: `run_batch_processing()`

```python
def run_batch_processing(self):
    """运行批处理 - 在启动前检测配置修改"""
    try:
        # 检查配置是否被修改
        if self.config_manager and self.config_manager.is_config_modified():
            reply = QMessageBox.question(
                self,
                "配置已修改",
                "检测到配置已修改但未保存。\n\n是否要保存修改的配置后再进行批处理？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Cancel:
                return  # 取消批处理
            elif reply == QMessageBox.Save:
                self.config_manager.save_config()
                return  # 保存后返回，由用户再次启动批处理
            # 如果选择 Discard，继续处理
        
        self.batch_manager.run_batch_processing()
    except AttributeError:
        logger.warning("BatchManager 未初始化")
    except Exception as e:
        logger.error("运行批处理失败: %s", e)
```

#### 用户交互流程

1. **用户编辑配置** → `_config_modified` 被设置为 `True`
2. **用户点击"开始处理"** → 检测 `_config_modified == True`
3. **弹出对话框** 显示三个选项:
   - **Save（保存）**: 保存修改的配置，然后返回（用户需再次点击开始处理）
   - **Discard（不保存）**: 使用内存中已修改的配置继续批处理
   - **Cancel（取消）**: 取消批处理操作

### 3. 信号连接机制

**坐标系面板已有信号**: `valuesChanged`

在 `CoordinateSystemPanel` 中：
- Source Panel 和 Target Panel 继承自 `CoordinateSystemPanel`
- `valuesChanged` 信号在用户编辑任何输入框时发射
- ConfigManager 在加载配置后连接此信号

```python
# 在 load_config() 中
self.gui.source_panel.valuesChanged.connect(
    lambda: self.set_config_modified(True)
)
self.gui.target_panel.valuesChanged.connect(
    lambda: self.set_config_modified(True)
)
```

## 实现细节

### 信号流

```
用户编辑 Source/Target 坐标系
        ↓
CoordinateSystemPanel.valuesChanged 发射
        ↓
ConfigManager.set_config_modified(True) 执行
        ↓
_config_modified = True
        ↓
用户点击"开始处理"
        ↓
MainWindow.run_batch_processing() 检测修改状态
        ↓
弹出对话框询问是否保存
        ↓
根据用户选择执行相应操作
```

### 状态转换图

```
┌─────────────────┐
│  初始状态       │
│ modified = False│
└────────┬────────┘
         │
         │ 加载配置
         ↓
┌─────────────────┐
│  已加载状态     │  ← 连接坐标系面板信号
│ modified = False│
└────────┬────────┘
         │
         │ 编辑坐标系
         ↓
┌─────────────────┐
│  已修改状态     │
│ modified = True │
└─────┬───────┬───┘
      │       │
      │       └─→ 用户取消编辑（无法反向）
      │
      │ 保存配置
      ↓
┌─────────────────┐
│  已保存状态     │
│ modified = False│
└─────────────────┘
```

## 测试场景

### 场景 1: 正常保存流程
1. 加载配置文件
2. 编辑坐标系参数
3. 点击"保存"配置
4. 验证: `_config_modified` 重置为 `False`

### 场景 2: 批处理前检测 - 选择保存
1. 加载配置文件
2. 编辑坐标系参数
3. 点击"开始处理"
4. 弹出对话框
5. 选择"Save（保存）"
6. 验证: 配置已保存，对话框关闭

### 场景 3: 批处理前检测 - 选择不保存
1. 加载配置文件
2. 编辑坐标系参数
3. 点击"开始处理"
4. 弹出对话框
5. 选择"Discard（不保存）"
6. 验证: 使用修改后的配置继续批处理

### 场景 4: 批处理前检测 - 取消
1. 加载配置文件
2. 编辑坐标系参数
3. 点击"开始处理"
4. 弹出对话框
5. 选择"Cancel（取消）"
6. 验证: 批处理未启动

## 修改的文件列表

| 文件 | 修改类型 | 描述 |
|------|--------|------|
| `gui/config_manager.py` | 修改 | 添加 `_config_modified` 追踪、修改状态 getter/setter、信号连接 |
| `gui/main_window.py` | 修改 | 在 `run_batch_processing()` 中添加修改检测和对话框 |
| `gui/initialization_manager.py` | 修改（前期） | ProjectManager 初始化、菜单栏创建 |
| `gui/project_manager.py` | 新建（前期） | Project 文件管理类 |
| `gui/panels/batch_panel.py` | 修改（前期） | 添加保存 Project 按钮、Tab 重组 |
| `gui/panels/operation_panel.py` | 修改（前期） | 连接 saveProjectRequested 信号 |

## 向后兼容性

- 所有修改均**向后兼容**
- 现有的配置加载/保存流程不受影响
- 新增的修改检测是**可选的**增强功能
- 若 `config_manager` 为 `None`，批处理直接启动（无检测）

## 注意事项

1. **信号连接时机**: 
   - 必须在 `load_config()` 完成后再连接信号
   - 确保坐标系面板已初始化

2. **保存对话框行为**:
   - 选择"Save"后，配置已保存，用户需再次点击"开始处理"启动批处理
   - 选择"Discard"后，使用内存中的修改配置立即启动批处理
   - 选择"Cancel"后，批处理不启动

3. **异常处理**:
   - 若 `config_manager` 为 `None` 或未初始化，批处理直接启动
   - 若坐标系面板信号连接失败，修改检测不可用（但不中断流程）

## 可能的扩展

1. **修改指示器**: 在 UI 中显示配置是否已修改（如标题栏加 `*` 符号）
2. **自动保存**: 添加定时自动保存功能
3. **修改历史**: 记录配置修改的历史，支持撤销/重做
4. **配置对比**: 显示修改前后配置的差异
