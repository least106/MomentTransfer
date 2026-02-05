"""批处理工作流进度指示器

提供清晰的步骤指示和转换提示，帮助用户理解当前处于哪一步以及下一步该做什么。
"""

import logging
from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget, QHBoxLayout
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)

# 工作流步骤定义
WORKFLOW_STEPS = {
    "init": {
        "display": "🔧 初始化",
        "description": "系统准备就绪",
        "next_step": "step1",
        "instruction": "请加载配置文件（JSON），或在配置编辑器中新增/编辑 Part",
    },
    "step1": {
        "display": "📄 步骤1：加载配置",
        "description": "配置坐标系和参数",
        "next_step": "step2",
        "instruction": "请加载配置文件（JSON），或在配置编辑器中定义 Source/Target 坐标系",
    },
    "step2": {
        "display": "📂 步骤2：选择文件",
        "description": "选择待处理数据文件",
        "next_step": "step3",
        "instruction": "请选择输入数据文件或目录，并在文件列表中确认选择",
    },
    "step3": {
        "display": "⚙️ 步骤3：配置参数",
        "description": "配置处理参数和Part映射",
        "next_step": "ready",
        "instruction": "请配置Source/Target Part映射，检查文件状态（需显示✓），然后点击\"开始处理\"",
    },
}


class WorkflowProgressIndicator:
    """批处理工作流进度指示器

    显示当前步骤、步骤描述和下一步提示。
    """

    def __init__(self):
        """初始化进度指示器"""
        self._current_step = "init"
        self._widget: Optional[QWidget] = None
        self._label: Optional[QLabel] = None

    def create_widget(self) -> QWidget:
        """创建进度指示器小部件"""
        if self._widget is not None:
            return self._widget

        self._widget = QWidget()
        layout = QHBoxLayout(self._widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(8)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label.setStyleSheet(
            """
            QLabel {
                color: #333;
                font-weight: bold;
                font-size: 11px;
                padding: 3px 8px;
                border-radius: 3px;
                background-color: #f0f0f0;
            }
            """
        )

        layout.addWidget(self._label)
        layout.addStretch()

        self.update_step("init")
        return self._widget

    def update_step(self, step: str) -> None:
        """更新当前步骤并显示进度

        Args:
            step: 工作流步骤（"init", "step1", "step2", "step3"）
        """
        self._current_step = (step or "init").strip()

        if self._label is None:
            return

        step_info = WORKFLOW_STEPS.get(self._current_step, {})
        display = step_info.get("display", "未知步骤")
        description = step_info.get("description", "")
        instruction = step_info.get("instruction", "")

        # 构建完整的提示文本
        text_parts = [display]
        if description:
            text_parts.append(f"({description})")
        if instruction:
            text_parts.append(f" → {instruction}")

        full_text = " ".join(text_parts)

        self._label.setText(full_text)
        self._label.setToolTip(self._build_tooltip())

        # 根据步骤更新背景色
        self._update_style_by_step()

    def _update_style_by_step(self) -> None:
        """根据步骤更新样式"""
        if self._label is None:
            return

        # 定义步骤的颜色（从浅到深的进度感）
        colors = {
            "init": "#e3f2fd",  # 浅蓝
            "step1": "#fff3e0",  # 浅橙
            "step2": "#f3e5f5",  # 浅紫
            "step3": "#e8f5e9",  # 浅绿
        }

        bg_color = colors.get(self._current_step, "#f0f0f0")
        self._label.setStyleSheet(
            f"""
            QLabel {{
                color: #333;
                font-weight: bold;
                font-size: 11px;
                padding: 3px 8px;
                border-radius: 3px;
                background-color: {bg_color};
                border-left: 3px solid #1976d2;
            }}
            """
        )

    def _build_tooltip(self) -> str:
        """构建工作流提示文本"""
        step_info = WORKFLOW_STEPS.get(self._current_step, {})

        steps_summary = "批处理工作流程（4个步骤）:\n"
        steps_summary += "━" * 40 + "\n"

        for step_key, step_data in WORKFLOW_STEPS.items():
            is_current = step_key == self._current_step
            marker = "✓ " if is_current else "○ "
            color_marker = "→" if is_current else " "

            steps_summary += (
                f"{color_marker} {marker}{step_data['display']}\n"
                f"  {step_data['instruction']}\n\n"
            )

        return steps_summary.rstrip()

    def get_current_step(self) -> str:
        """获取当前步骤"""
        return self._current_step

    def get_next_step_instruction(self) -> str:
        """获取下一步的指令"""
        step_info = WORKFLOW_STEPS.get(self._current_step, {})
        next_step = step_info.get("next_step", "ready")
        next_info = WORKFLOW_STEPS.get(next_step, {})
        return next_info.get("instruction", "准备完成")

    def is_ready_to_process(self) -> bool:
        """检查是否已准备好开始处理"""
        return self._current_step == "step3"

    @staticmethod
    def get_step_display_name(step: str) -> str:
        """获取步骤的显示名称"""
        return WORKFLOW_STEPS.get(step, {}).get("display", step)

    @staticmethod
    def get_step_instruction(step: str) -> str:
        """获取步骤的操作指令"""
        return WORKFLOW_STEPS.get(step, {}).get("instruction", "")
