"""
UI 工具模块 - 提供通用的 UI 组件创建函数
"""

import logging

from PySide6.QtWidgets import (QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit,
                               QSizePolicy, QWidget)

logger = logging.getLogger(__name__)


def create_input(default_value: str) -> QLineEdit:
    """创建输入框

    参数：
        default_value: 默认值

    返回：
        QLineEdit 实例
    """
    inp = QLineEdit(default_value)
    # 提高最大宽度以适配高 DPI 和更长的文本输入，统一 Part Name 输入长度
    inp.setMaximumWidth(220)
    try:
        inp.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    except Exception:
        logger.debug("inp.setSizePolicy failed (non-fatal)", exc_info=True)
    return inp


def create_triple_spin(a: float = 0.0, b: float = 0.0, c: float = 0.0) -> tuple:
    """创建一行三个紧凑型 QDoubleSpinBox

    参数：
        a, b, c: 初始值 (X, Y, Z)

    返回：
        (spin_a, spin_b, spin_c) 元组
    """
    s1 = QDoubleSpinBox()
    s2 = QDoubleSpinBox()
    s3 = QDoubleSpinBox()
    for s in (s1, s2, s3):
        try:
            s.setRange(-1e6, 1e6)
            s.setDecimals(2)
            s.setSingleStep(0.1)
            s.setValue(0.0)
            s.setProperty("compact", "true")
            s.setMaximumWidth(96)
        except Exception:
            logger.debug("triple spin init failed", exc_info=True)
    s1.setValue(float(a))
    s2.setValue(float(b))
    s3.setValue(float(c))
    # ToolTip 提示
    try:
        s1.setToolTip("X 分量")
        s2.setToolTip("Y 分量")
        s3.setToolTip("Z 分量")
    except Exception:
        pass
    return s1, s2, s3


def get_numeric_value(widget) -> float:
    """从 QDoubleSpinBox 或 QLineEdit 返回 float 值的统一访问器

    参数：
        widget: QDoubleSpinBox 或 QLineEdit 实例

    返回：
        float 值

    抛出：
        ValueError: 无法解析数值时
    """
    try:
        if hasattr(widget, "value"):
            return float(widget.value())
        else:
            return float(widget.text())
    except Exception as e:
        # 若解析失败，抛出 ValueError 以便上层显示提示
        raise ValueError(f"无法解析数值输入: {e}")


def create_vector_row(inp1, inp2, inp3) -> QWidget:
    """创建向量输入行 [x, y, z]

    参数：
        inp1, inp2, inp3: 三个输入控件 (X, Y, Z)

    返回：
        包含向量输入的 QWidget
    """
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    lb1 = QLabel("[")
    lb_comma1 = QLabel(",")
    lb_comma2 = QLabel(",")
    lb2 = QLabel("]")
    for lb in (lb1, lb_comma1, lb_comma2, lb2):
        try:
            lb.setObjectName("smallLabel")
        except Exception:
            pass
    # 对传入的输入框标记为 compact 以便样式表进行收缩
    try:
        for w in (inp1, inp2, inp3):
            w.setProperty("compact", "true")
            try:
                w.setMaximumWidth(96)
            except Exception:
                pass
    except Exception:
        pass
    layout.addWidget(lb1)
    layout.addWidget(inp1)
    layout.addWidget(lb_comma1)
    layout.addWidget(inp2)
    layout.addWidget(lb_comma2)
    layout.addWidget(inp3)
    layout.addWidget(lb2)
    # 使用小间距替代 stretch，避免把右侧控件挤出可见区域
    layout.addSpacing(6)
    return row
