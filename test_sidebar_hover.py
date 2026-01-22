#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
悬停按钮可见性功能的演示脚本

此脚本演示了新的 SlideSidebar 功能：
- 默认隐藏侧边栏按钮
- 鼠标靠近屏幕边缘时显示按钮
- 按钮从屏幕边缘平滑滑出
- 鼠标离开时自动隐藏

用法：python test_sidebar_hover.py
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

from gui.slide_sidebar import SlideSidebar


def main():
    """创建一个演示窗口来展示悬停按钮功能。"""
    app = QApplication([])

    # 创建主窗口
    main_window = QMainWindow()
    main_window.setWindowTitle("侧边栏悬停按钮演示")
    main_window.setGeometry(100, 100, 900, 600)

    # 创建中央窗口
    central = QWidget()
    main_window.setCentralWidget(central)
    central_layout = QVBoxLayout(central)
    central_layout.setContentsMargins(0, 0, 0, 0)

    # 创建左侧内容
    left_content = QWidget()
    left_layout = QVBoxLayout(left_content)
    left_label = QLabel("左侧边栏\n\n将鼠标移动到左边缘\n会看到切换按钮从边缘滑出")
    left_label.setAlignment(Qt.AlignCenter)
    left_layout.addWidget(left_label)

    # 创建右侧内容
    right_content = QWidget()
    right_layout = QVBoxLayout(right_content)
    right_label = QLabel("右侧边栏\n\n将鼠标移动到右边缘\n会看到切换按钮从边缘滑出")
    right_label.setAlignment(Qt.AlignCenter)
    right_layout.addWidget(right_label)

    # 创建左侧栏
    left_sidebar = SlideSidebar(
        left_content,
        side="left",
        expanded_width=250,
        button_text_collapsed=">>",
        button_text_expanded="<<",
        parent=central,
    )

    # 创建右侧栏
    right_sidebar = SlideSidebar(
        right_content,
        side="right",
        expanded_width=250,
        button_text_collapsed="<<",
        button_text_expanded=">>",
        parent=central,
    )

    # 创建中央显示区域
    main_content = QWidget()
    main_layout = QVBoxLayout(main_content)
    info_label = QLabel(
        "侧边栏悬停按钮功能演示\n\n"
        "功能说明：\n"
        "1. 按钮默认隐藏\n"
        "2. 鼠标靠近屏幕左/右边缘 (15像素内) 时显示\n"
        "3. 按钮从屏幕边缘平滑滑出 (150ms动画)\n"
        "4. 鼠标离开边缘2秒后自动隐藏\n\n"
        "提示：尝试：\n"
        "- 将鼠标移到屏幕左边缘\n"
        "- 将鼠标移到屏幕右边缘\n"
        "- 单击按钮展开/收起侧栏\n"
        "- 鼠标在按钮上时，隐藏计时器会重置"
    )
    info_label.setAlignment(Qt.AlignCenter)
    main_layout.addWidget(info_label)
    main_content.setStyleSheet("background-color: #f0f0f0;")

    # 布局管理
    central_layout.addWidget(main_content, 1)

    # 手动调整侧边栏位置（因为还没有集成到主布局中）
    def reposition_sidebars():
        """重新定位侧边栏。"""
        w = central.width()
        h = central.height()
        left_sidebar.setGeometry(0, 0, left_sidebar.width(), h)
        right_sidebar.setGeometry(
            w - right_sidebar.width(), 0, right_sidebar.width(), h
        )

    # 在窗口调整大小时重新定位
    def on_resize(event):
        reposition_sidebars()
        return super(QWidget, central).resizeEvent(event)

    central.resizeEvent = on_resize

    # 初始化布局
    QTimer.singleShot(100, reposition_sidebars)

    # 显示窗口
    main_window.show()

    # 运行应用
    return app.exec()


if __name__ == "__main__":
    exit(main())
