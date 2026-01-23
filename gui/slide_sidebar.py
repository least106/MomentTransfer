"""滑出式侧边栏组件，支持左右方向的隐藏/显示动画，带边缘悬浮切换按钮。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QPushButton, QSizePolicy, QVBoxLayout, QWidget

# 延迟导入 Qt 相关类型以避免部分环境下的循环导入警告
# pylint: disable=import-outside-toplevel




class SlideSidebar(QWidget):
    """浮动式侧边栏：内容 + 按钮一起动画，始终显示按钮。"""

    def __init__(
        self,
        content: QWidget,
        *,
        side: str = "left",
        expanded_width: int = 360,
        animation_duration: int = 200,
        button_text_collapsed: str = ">>",
        button_text_expanded: str = "<<",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        # 设置 objectName 以便 QSS 可以使用更高优先级的选择器定位该侧边栏实例
        try:
            self.setObjectName("SlideSidebar")
        except Exception:
            pass

        self._sidebar_width = 0
        self._side = side
        self._expanded_width = max(120, int(expanded_width))
        self._button_width = 24
        self._animation_duration = max(80, int(animation_duration))
        self._content = content
        self._button_text_collapsed = button_text_collapsed
        self._button_text_expanded = button_text_expanded

        # 创建内容容器
        self._container = QWidget(self)
        self._container.setObjectName("SidebarContainer")
        self._container.setCursor(Qt.ArrowCursor)
        self._container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container_lay = QVBoxLayout(self._container)
        container_lay.setContentsMargins(0, 0, 0, 0)
        container_lay.setSpacing(0)
        container_lay.addWidget(content)

        # 创建按钮
        self._toggle_btn = QPushButton(self)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.clicked.connect(self.toggle_panel)
        self._toggle_btn.setFixedSize(self._button_width, 80)
        self._toggle_btn.setText(button_text_collapsed)

        # 根据方向设置不同的 ObjectName（样式由 QSS 控制）
        if side == "left":
            self._toggle_btn.setObjectName("SidebarToggleLeft")
        else:
            self._toggle_btn.setObjectName("SidebarToggleRight")

        # ObjectName 在运行时变更时，Qt 不一定会自动重刷样式
        try:
            self._toggle_btn.style().unpolish(self._toggle_btn)
            self._toggle_btn.style().polish(self._toggle_btn)
        except Exception:
            pass

        # 样式优先交由全局 QSS 控制，避免内联样式在样式重刷时被覆盖或与主题冲突。

        # 主容器空布局（手动管理）
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # 属性动画
        self._anim = QPropertyAnimation(self, b"sidebarWidth", self)
        self._anim.setDuration(self._animation_duration)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._sidebar_width = self._button_width

        # 预先初始化按钮偏移和其他属性，确保 Property 可以正确绑定
        self._button_x_offset = 0  # 按钮偏移位置（用于动画）
        self._edge_detect_distance = 15  # 从屏幕边缘多少像素内触发显示
        self._hide_delay_ms = 2000  # 鼠标离开后2秒自动隐藏

        self._update_layout()

        # 按钮显示/隐藏动画（透明度）
        self._button_opacity_anim = QPropertyAnimation(
            self._toggle_btn, b"windowOpacity", self
        )
        self._button_opacity_anim.setDuration(150)
        self._button_opacity_anim.setEasingCurve(QEasingCurve.InOutQuad)

        # 按钮位置动画（从屏幕边缘滑出）
        self._button_pos_anim = QPropertyAnimation(self, b"buttonX", self)
        self._button_pos_anim.setDuration(150)
        self._button_pos_anim.setEasingCurve(QEasingCurve.InOutQuad)

        # 鼠标事件跟踪与延迟隐藏
        self._mouse_hide_timer = QTimer(self)
        self._mouse_hide_timer.setSingleShot(True)
        self._mouse_hide_timer.timeout.connect(self._hide_button_animated)

        # 初始状态：按钮隐藏
        self._toggle_btn.setWindowOpacity(0.0)

        # 启用鼠标追踪
        self.setMouseTracking(True)
        self._toggle_btn.setMouseTracking(True)

        # 为按钮添加进入/离开事件的自定义处理
        self._original_button_enter_event = None
        self._original_button_leave_event = None
        self._setup_button_events()

    def _get_button_x(self) -> int:
        """获取按钮的 X 偏移量（用于动画）。"""
        return self._button_x_offset

    def _set_button_x(self, value: int) -> None:
        """设置按钮的 X 偏移量（用于动画）。"""
        self._button_x_offset = value
        self._update_layout()

    buttonX = Property(int, _get_button_x, _set_button_x)

    def sizeHint(self) -> QSize:  # noqa: D401
        return QSize(self._button_width + self._expanded_width, 600)

    def _get_sidebar_width(self) -> int:
        return self._sidebar_width

    def _set_sidebar_width(self, value: int) -> None:
        self._sidebar_width = max(
            self._button_width, min(value, self._button_width + self._expanded_width)
        )
        self._update_layout()

    sidebarWidth = Property(int, _get_sidebar_width, _set_sidebar_width)

    def _reposition_in_parent(self) -> None:
        """确保右侧侧边栏在宽度变化时仍贴合父容器右边缘。"""
        parent = self.parentWidget()
        if parent is None:
            return

        w = parent.width()
        h = parent.height()
        if w <= 0 or h <= 0:
            return

        x = 0 if self._side == "left" else max(0, w - self._sidebar_width)
        # 这里用 setGeometry（而不是 move）确保高度始终填满父容器
        self.setGeometry(x, 0, self._sidebar_width, h)

    def reposition_in_parent(self) -> None:
        """对外暴露的重定位方法。

        用途：父容器 resize 时调用，确保侧边栏仍贴合左右边缘。
        """
        self._reposition_in_parent()

    def _update_layout(self) -> None:
        """更新布局：调整容器宽度、按钮位置、文本。"""
        try:
            # 容器宽度 = 总宽度 - 按钮宽度
            container_width = max(0, self._sidebar_width - self._button_width)

            # 设置容器大小
            self._container.setFixedWidth(container_width)
            self._container.setVisible(container_width > 0)

            # 容器鼠标穿透（收起时）
            is_collapsed = container_width <= 0
            self._container.setAttribute(Qt.WA_TransparentForMouseEvents, is_collapsed)

            # 更新按钮文本
            is_expanded = self._sidebar_width > self._button_width
            if self._side == "left":
                # 左侧：>> 表示隐藏（箭头指向左），<< 表示展开
                self._toggle_btn.setText(
                    self._button_text_expanded
                    if is_expanded
                    else self._button_text_collapsed
                )
            else:  # right
                # 右侧：<< 表示隐藏（箭头指向右），>> 表示展开
                self._toggle_btn.setText(
                    self._button_text_expanded
                    if is_expanded
                    else self._button_text_collapsed
                )

            # 设置总宽度
            self.setFixedWidth(self._sidebar_width)

            # 关键：右侧侧边栏展开/收起会改变宽度，需要同步重定位，否则会“向右溢出”看不见
            self._reposition_in_parent()

            # 手动定位子组件
            self._layout_children()
        except Exception:
            pass

    def _layout_children(self) -> None:
        """手动定位容器和按钮。"""
        try:
            h = self.height()
            if h <= 0:
                h = 600

            w = self.width()
            container_width = max(0, w - self._button_width)

            button_y = (h - 80) // 2

            # 根据方向定位，考虑按钮偏移（用于滑入/滑出动画）
            if self._side == "left":
                # 左侧：容器在左，按钮在容器右侧
                # 按钮初始在屏幕左边外，通过 _button_x_offset 从左滑入
                btn_x = (
                    container_width - self._button_x_offset
                    if self._button_x_offset >= 0
                    else container_width
                )
                self._container.setGeometry(0, 0, container_width, h)
                self._toggle_btn.setGeometry(btn_x, button_y, self._button_width, 80)
                try:
                    self._toggle_btn.raise_()
                    self._toggle_btn.setAttribute(Qt.WA_TranslucentBackground, True)
                    self._toggle_btn.setAutoFillBackground(False)
                except Exception:
                    pass
            else:  # right
                # 右侧：按钮在左，容器在按钮右侧
                # 按钮初始在屏幕右边外，通过 _button_x_offset 从右滑入
                btn_x = self._button_x_offset if self._button_x_offset <= 0 else 0
                self._toggle_btn.setGeometry(btn_x, button_y, self._button_width, 80)
                self._container.setGeometry(self._button_width, 0, container_width, h)
                try:
                    self._toggle_btn.raise_()
                    self._toggle_btn.setAttribute(Qt.WA_TranslucentBackground, True)
                    self._toggle_btn.setAutoFillBackground(False)
                except Exception:
                    pass
        except Exception:
            pass

    def resizeEvent(self, event) -> None:
        """重新布局子组件。"""
        super().resizeEvent(event)
        try:
            self._reposition_in_parent()
        except Exception:
            pass
        self._layout_children()

    def is_expanded(self) -> bool:
        return self._sidebar_width > self._button_width

    def show_panel(self) -> None:
        self._animate_to(self._button_width + self._expanded_width)

    def hide_panel(self) -> None:
        self._animate_to(self._button_width)

    def toggle_panel(self) -> None:
        if self.is_expanded():
            self.hide_panel()
        else:
            self.show_panel()

    def _animate_to(self, target: int) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._sidebar_width)
        self._anim.setEndValue(target)
        self.setVisible(True)
        self.raise_()
        self._anim.start()

    def set_expanded_width(self, width: int) -> None:
        self._expanded_width = max(120, int(width))
        if self.is_expanded():
            self.show_panel()

    def content_widget(self) -> QWidget:
        return self._content

    def side(self) -> str:
        return self._side

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """在组件上移动时检测鼠标位置。"""
        try:
            self._check_edge_proximity()
        except Exception:
            pass
        super().mouseMoveEvent(event)

    def _on_parent_mouse_move(self, event: QMouseEvent) -> None:
        """全局鼠标移动事件（通过连接到父窗口）。"""
        try:
            self._check_edge_proximity()
        except Exception:
            pass

    def _check_edge_proximity(self) -> None:
        """检查鼠标是否靠近屏幕边缘，决定是否显示按钮。"""
        try:
            from PySide6.QtGui import QCursor

            global_pos = QCursor.pos()
            # 获取主窗口或屏幕几何
            root = self.parent()
            while root and root.parent():
                root = root.parent()

            if not root:
                return

            screen = root.screen()
            if not screen:
                return

            screen_geometry = screen.geometry()

            # 检查鼠标是否靠近左边缘或右边缘
            is_near_left = (
                global_pos.x() <= screen_geometry.left() + self._edge_detect_distance
            )
            is_near_right = (
                global_pos.x() >= screen_geometry.right() - self._edge_detect_distance
            )

            # 判断是否应该显示按钮
            should_show = (self._side == "left" and is_near_left) or (
                self._side == "right" and is_near_right
            )

            if should_show:
                # 显示按钮
                self._show_button_animated()
                # 重置隐藏计时器
                self._mouse_hide_timer.stop()
                self._mouse_hide_timer.start(self._hide_delay_ms)
            elif self._toggle_btn.windowOpacity() > 0.5:
                # 鼠标离开边缘且不在按钮上方时，启动隐藏计时器
                if not self._is_mouse_on_button():
                    self._mouse_hide_timer.stop()
                    self._mouse_hide_timer.start(self._hide_delay_ms)
        except Exception:
            pass

    def _is_mouse_on_button(self) -> bool:
        """检查鼠标是否在按钮上方。"""
        try:
            from PySide6.QtGui import QCursor

            global_pos = QCursor.pos()
            btn_global = self._toggle_btn.mapToGlobal(QPoint(0, 0))
            btn_rect = self._toggle_btn.rect().translated(btn_global)
            return btn_rect.contains(global_pos)
        except Exception:
            return False

    def _show_button_animated(self) -> None:
        """显示按钮（带动画）。"""
        try:
            # 如果已经显示，不再重复
            if self._toggle_btn.windowOpacity() > 0.9:
                return

            # 停止之前的动画
            self._button_opacity_anim.stop()
            self._button_pos_anim.stop()

            # 透明度动画
            self._button_opacity_anim.setStartValue(self._toggle_btn.windowOpacity())
            self._button_opacity_anim.setEndValue(1.0)

            # 位置动画（从边缘滑入）
            self._button_pos_anim.setStartValue(self._button_x_offset)
            self._button_pos_anim.setEndValue(0)

            self._button_opacity_anim.start()
            self._button_pos_anim.start()
        except Exception:
            pass

    def _hide_button_animated(self) -> None:
        """隐藏按钮（带动画）。"""
        try:
            # 检查鼠标是否仍在边缘或按钮上方，如果是则不隐藏
            if self._is_mouse_on_button():
                self._mouse_hide_timer.start(self._hide_delay_ms)
                return

            # 停止之前的动画
            self._button_opacity_anim.stop()
            self._button_pos_anim.stop()

            # 透明度动画
            self._button_opacity_anim.setStartValue(self._toggle_btn.windowOpacity())
            self._button_opacity_anim.setEndValue(0.0)

            # 位置动画（滑出屏幕边缘）
            self._button_pos_anim.setStartValue(self._button_x_offset)
            target_offset = (
                -self._button_width if self._side == "left" else self._button_width
            )
            self._button_pos_anim.setEndValue(target_offset)

            self._button_opacity_anim.start()
            self._button_pos_anim.start()
        except Exception:
            pass

    def _setup_button_events(self) -> None:
        """为按钮设置进入/离开事件处理。"""
        try:
            # 使用继承来重写按钮的事件处理
            class CustomPushButton(QPushButton):
                def __init__(self, parent_sidebar):
                    # 不调用 super().__init__() 因为按钮已经存在，只是包装它
                    self.parent_sidebar = parent_sidebar

                def enterEvent(self, event):
                    """鼠标进入按钮时取消隐藏计时器。"""
                    if self.parent_sidebar._mouse_hide_timer.isActive():
                        self.parent_sidebar._mouse_hide_timer.stop()
                    return super().enterEvent(event)

                def leaveEvent(self, event):
                    """鼠标离开按钮时启动隐藏计时器。"""
                    self.parent_sidebar._mouse_hide_timer.start(
                        self.parent_sidebar._hide_delay_ms
                    )
                    return super().leaveEvent(event)

            # 保存原始事件处理
            self._original_button_enter_event = self._toggle_btn.enterEvent
            self._original_button_leave_event = self._toggle_btn.leaveEvent

            # 替换事件处理
            self._toggle_btn.enterEvent = self._on_button_enter
            self._toggle_btn.leaveEvent = self._on_button_leave
        except Exception:
            pass

    def _on_button_enter(self, event: QMouseEvent) -> None:
        """鼠标进入按钮时的事件处理。"""
        try:
            if self._mouse_hide_timer.isActive():
                self._mouse_hide_timer.stop()
        except Exception:
            pass

    def _on_button_leave(self, event: QMouseEvent) -> None:
        """鼠标离开按钮时的事件处理。"""
        try:
            self._mouse_hide_timer.start(self._hide_delay_ms)
        except Exception:
            pass
