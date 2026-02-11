"""
全局坐标系编辑面板 - 用于定义可被引用的全局坐标系
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class GlobalCoordSystemPanel(QGroupBox):
    """全局坐标系定义面板，用于定义可被其他 Part 引用的坐标系。"""

    valuesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__("全局坐标系定义 (Global CoordSystem)", parent)
        self._silent_update_count = 0
        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 说明文本
        info_label = QLabel(
            "定义全局坐标系，可在 Source/Target 参考系中通过 CoordSystemRef=\"Global\" 引用。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info_label)

        # 坐标系表格（仅4行：Orig + 3个基向量，不包含力矩中心）
        self.coord_table = QTableWidget(4, 3)
        self.coord_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.coord_table.setVerticalHeaderLabels(["Orig", "X轴", "Y轴", "Z轴"])

        # 设置默认值（标准世界坐标系）
        default_values = [
            [0.0, 0.0, 0.0],  # Orig
            [1.0, 0.0, 0.0],  # X轴
            [0.0, 1.0, 0.0],  # Y轴
            [0.0, 0.0, 1.0],  # Z轴
        ]

        for row in range(4):
            for col in range(3):
                item = QTableWidgetItem(str(default_values[row][col]))
                item.setTextAlignment(Qt.AlignCenter)
                self.coord_table.setItem(row, col, item)
            self.coord_table.setRowHeight(row, 26)

        # 设置表格尺寸
        self.coord_table.setMinimumHeight(140)
        self.coord_table.setMaximumHeight(160)
        self.coord_table.setMinimumWidth(250)

        # 列宽自适应
        h_header = self.coord_table.horizontalHeader()
        h_header.setSectionResizeMode(QHeaderView.Stretch)

        # 行标题列
        v_header = self.coord_table.verticalHeader()
        v_header.setMinimumWidth(60)

        # 连接值变化信号
        self.coord_table.itemChanged.connect(self._emit_values_changed)

        layout.addWidget(self.coord_table)

        # 快捷操作按钮
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        self.btn_reset = QPushButton("重置为标准坐标系")
        self.btn_reset.setToolTip("重置为世界坐标系：原点 (0,0,0)，XYZ 标准基向量")
        self.btn_reset.clicked.connect(self._reset_to_standard)
        btn_layout.addWidget(self.btn_reset)
        btn_layout.addStretch()

        layout.addWidget(btn_widget)

    def _emit_values_changed(self):
        """发射值变化信号"""
        try:
            if getattr(self, "_silent_update_count", 0) > 0:
                return
            self.valuesChanged.emit()
        except Exception:
            logger.debug("valuesChanged 发射失败", exc_info=True)

    def begin_silent_update(self):
        """开始静默更新"""
        try:
            self._silent_update_count = getattr(self, "_silent_update_count", 0) + 1
        except Exception:
            self._silent_update_count = 1

    def end_silent_update(self):
        """结束静默更新"""
        try:
            cnt = getattr(self, "_silent_update_count", 0) - 1
            self._silent_update_count = cnt if cnt > 0 else 0
        except Exception:
            self._silent_update_count = 0

    def _reset_to_standard(self):
        """重置为标准世界坐标系"""
        try:
            self.begin_silent_update()
            standard_values = [
                [0.0, 0.0, 0.0],  # Orig
                [1.0, 0.0, 0.0],  # X轴
                [0.0, 1.0, 0.0],  # Y轴
                [0.0, 0.0, 1.0],  # Z轴
            ]
            for row in range(4):
                for col in range(3):
                    item = self.coord_table.item(row, col)
                    if item:
                        item.setText(str(standard_values[row][col]))
        finally:
            self.end_silent_update()
            self._emit_values_changed()

    def to_dict(self) -> dict:
        """导出为配置字典"""
        try:
            result = {
                "Orig": [],
                "X": [],
                "Y": [],
                "Z": [],
            }
            keys = ["Orig", "X", "Y", "Z"]
            for row in range(4):
                for col in range(3):
                    item = self.coord_table.item(row, col)
                    try:
                        val = float(item.text()) if item else 0.0
                    except (ValueError, AttributeError):
                        val = 0.0
                    result[keys[row]].append(val)
            return result
        except Exception as e:
            logger.error(f"导出 Global 坐标系失败: {e}")
            return {
                "Orig": [0.0, 0.0, 0.0],
                "X": [1.0, 0.0, 0.0],
                "Y": [0.0, 1.0, 0.0],
                "Z": [0.0, 0.0, 1.0],
            }

    def from_dict(self, data: dict):
        """从配置字典加载"""
        try:
            self.begin_silent_update()
            keys = ["Orig", "X", "Y", "Z"]
            for row in range(4):
                vec = data.get(keys[row], [0.0, 0.0, 0.0])
                for col in range(3):
                    item = self.coord_table.item(row, col)
                    if item:
                        try:
                            val = float(vec[col]) if col < len(vec) else 0.0
                        except (ValueError, TypeError, IndexError):
                            val = 0.0
                        item.setText(str(val))
        finally:
            self.end_silent_update()
