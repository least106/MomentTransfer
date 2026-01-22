# 侧边栏按钮悬停可见性功能

## 功能概述

`gui/slide_sidebar.py` 中的 `SlideSidebar` 组件现在支持**智能按钮可见性**功能：

- **默认隐藏**：侧边栏切换按钮在应用启动时默认隐藏（透明度为 0）
- **边缘检测**：当鼠标靠近屏幕左/右边缘时（默认15像素内），相应的按钮自动显示
- **平滑动画**：按钮从屏幕边缘平滑滑出，伴随透明度渐进的淡入效果（150毫秒）
- **自动隐藏**：鼠标离开按钮后，经过2秒延迟自动隐藏
- **智能保持**：当鼠标在按钮上或靠近屏幕边缘时，隐藏计时器会被重置，保证用户交互不被中断

## 技术实现

### 核心变量

```python
self._button_x_offset = 0                # 按钮位置偏移（用于滑入/滑出动画）
self._edge_detect_distance = 15          # 边缘检测距离（像素）
self._hide_delay_ms = 2000               # 自动隐藏延迟（毫秒）
self._button_opacity_anim = ...          # 透明度动画对象
self._button_pos_anim = ...              # 位置动画对象
self._mouse_hide_timer = ...             # 隐藏计时器
```

### 关键方法

#### `_check_edge_proximity()`
检查鼠标是否靠近屏幕边缘，根据条件触发显示或隐藏动画。

```python
def _check_edge_proximity(self) -> None:
    """检查鼠标是否靠近屏幕边缘，决定是否显示按钮。"""
```

#### `_show_button_animated()`
执行按钮淡入和滑入动画。

```python
def _show_button_animated(self) -> None:
    """显示按钮（带动画）。"""
    # 1. 透明度动画：0 → 1.0
    # 2. 位置动画：_button_x_offset → 0（从边缘滑入）
```

#### `_hide_button_animated()`
执行按钮淡出和滑出动画。

```python
def _hide_button_animated(self) -> None:
    """隐藏按钮（带动画）。"""
    # 1. 透明度动画：当前值 → 0
    # 2. 位置动画：0 → 负偏移（滑出屏幕边缘）
```

#### `_is_mouse_on_button()`
检查鼠标当前位置是否在按钮上方。

```python
def _is_mouse_on_button(self) -> bool:
    """检查鼠标是否在按钮上方。"""
```

#### `_on_button_enter()` / `_on_button_leave()`
按钮的鼠标进入/离开事件处理。

```python
def _on_button_enter(self, event: QMouseEvent) -> None:
    """鼠标进入按钮时取消隐藏计时器。"""

def _on_button_leave(self, event: QMouseEvent) -> None:
    """鼠标离开按钮时启动隐藏计时器。"""
```

## 使用示例

```python
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
from gui.slide_sidebar import SlideSidebar

app = QApplication([])
main_window = QMainWindow()

# 创建侧边栏内容
left_content = QLabel("左侧内容")

# 创建侧边栏
left_sidebar = SlideSidebar(
    left_content,
    side="left",
    expanded_width=250,
    button_text_collapsed=">>",
    button_text_expanded="<<",
    parent=main_window.centralWidget(),
)

main_window.show()
app.exec()
```

## 配置参数

可通过修改构造函数中的以下参数来自定义行为：

```python
self._edge_detect_distance = 15     # 改为不同的像素值调整边缘检测范围
self._hide_delay_ms = 2000          # 改为不同的毫秒值调整自动隐藏延迟
```

## 动画配置

按钮动画的持续时间和缓动曲线可在构造函数中修改：

```python
self._button_opacity_anim.setDuration(150)  # 透明度动画时长（毫秒）
self._button_pos_anim.setDuration(150)      # 位置动画时长（毫秒）
self._button_opacity_anim.setEasingCurve(QEasingCurve.InOutQuad)  # 缓动曲线
```

## 事件流程图

```
用户移动鼠标
    ↓
检测是否靠近屏幕边缘（_check_edge_proximity）
    ↓
    ├─ 是 → 显示按钮动画 (_show_button_animated)
    │        ↓
    │   启动隐藏计时器（2秒）
    │
    └─ 否 → 启动隐藏计时器（除非鼠标在按钮上）

鼠标进入按钮
    ↓
取消隐藏计时器（_on_button_enter）

鼠标离开按钮
    ↓
启动隐藏计时器（_on_button_leave）

隐藏计时器超时
    ↓
执行隐藏动画 (_hide_button_animated)
    ↓
按钮淡出并滑出屏幕边缘
```

## 测试演示

运行 `test_sidebar_hover.py` 来查看完整的演示：

```bash
python test_sidebar_hover.py
```

此脚本创建一个展示窗口，显示左右两个侧边栏，可直观体验悬停按钮功能。

## 性能考虑

- 所有事件处理都被包装在 `try-except` 块中，确保异常不会中断应用
- 动画对象被重用而不是重复创建，提高效率
- 鼠标检测使用全局坐标，不依赖于窗口焦点状态
- 隐藏计时器使用 `QTimer` 而非手动延迟，符合 Qt 事件循环设计

## 兼容性

该功能与现有的侧边栏功能完全兼容：

- ✅ 展开/收起动画（`sidebarWidth` Property）
- ✅ 按钮点击事件 (`toggle_panel()`)
- ✅ 左右方向支持
- ✅ QSS 样式支持
- ✅ 所有屏幕尺寸和 DPI 设置

## 已知限制

1. 在多屏幕设置下，仅检测主屏幕的边缘。对于跨越多个屏幕的应用，可能需要扩展逻辑
2. 当窗口失去焦点时，鼠标事件可能不会被继续捕获（取决于操作系统和窗口管理器）
