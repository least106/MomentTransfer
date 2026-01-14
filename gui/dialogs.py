"""
对话框模块：包含实验性功能对话框
"""

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)


class ExperimentalDialog(QDialog):
    """实验性功能对话框（简化版，移除已废弃的 registry 功能）"""

    def __init__(self, parent=None, initial_settings: dict = None):
        super().__init__(parent)
        self.setWindowTitle("实验性功能")
        self.resize(500, 300)
        self.initial_settings = initial_settings or {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 实验性开关
        self.chk_show_visual = QCheckBox("启用 3D 可视化（实验）")
        layout.addWidget(self.chk_show_visual)
        
        layout.addWidget(QLabel("最近项目（只作展示）"))
        self.lst_recent = QListWidget()
        self.lst_recent.setMaximumHeight(80)
        layout.addWidget(self.lst_recent)

        # 按钮
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        self._load_initial()

    def _load_initial(self):
        s = self.initial_settings
        try:
            for rp in s.get("recent_projects", [])[:10]:
                self.lst_recent.addItem(rp)
        except Exception:
            pass

    def get_settings(self) -> dict:
        return {
            "recent_projects": [
                self.lst_recent.item(i).text() for i in range(self.lst_recent.count())
            ],
        }
