"""滑出式侧边栏组件，支持左右方向的隐藏/显示动画，带边缘悬浮切换按钮。"""

from __future__ import annotations

import logging
import sys
import traceback
from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_logger = logging.getLogger(__name__)


def _safe_log(msg: str, exc_info: bool = True) -> None:
    """安全记录调试信息：首先尝试使用 logger，若记录器失败则降级到 stderr 打印。

    目的：避免在异常处理分支中再次调用可能抛出的 logger 调用而导致递归异常。
    """
    try:
        _logger.debug(msg, exc_info=exc_info)
    except Exception:
        try:
            traceback.print_exc()
            try:
                sys.stderr.write(msg + "\n")
            except Exception:
                # 最后兜底：不再尝试记录
                pass
        except Exception:
            # 完全静默兜底，避免递归
            pass


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
            _safe_log("设置 SlideSidebar objectName 失败（非致命）")

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
            _safe_log("刷新侧边栏切换按钮样式失败（非致命）")

        # 样式优先交由全局 QSS 控制，避免内联样式在样式重刷时被覆盖或与主题冲突。

        # 主容器空布局（手动管理）
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # 属性动画
        self._anim = QPropertyAnimation(self, b"sidebarWidth", self)
        self._anim.setDuration(self._animation_duration)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)

        # 动画并发计数：用于在动画期间禁用触发按钮，防止重复触发或竞态
        self._running_anim_count = 0

        # 连接动画完成回调以维护计数
        try:
            self._anim.finished.connect(lambda: self._on_animation_finished())
        except Exception:
            _safe_log("连接动画 finished 信号失败（非致命）")

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._sidebar_width = self._button_width

        # 预先初始化按钮偏移和其他属性，确保 Property 可以正确绑定
        self._button_x_offset = 0  # 按钮偏移位置（用于动画）
        self._edge_detect_distance = 15  # 从屏幕边缘多少像素内触发显示
        self._hide_delay_ms = 2000  # 鼠标离开后2秒自动隐藏
        # 上次是否处于应显示状态（用于节流调试日志）
        self._last_should_show = False

        self._update_layout()

        # 按钮显示/隐藏动画（透明度） — 使用 QGraphicsOpacityEffect，适用于子控件
        self._btn_opacity_effect = QGraphicsOpacityEffect(self._toggle_btn)
        self._toggle_btn.setGraphicsEffect(self._btn_opacity_effect)
        self._btn_opacity_effect.setOpacity(0.0)

        self._button_opacity_anim = QPropertyAnimation(self._btn_opacity_effect, b"opacity", self)
        self._button_opacity_anim.setDuration(150)
        self._button_opacity_anim.setEasingCurve(QEasingCurve.InOutQuad)
        try:
            self._button_opacity_anim.finished.connect(lambda: self._on_animation_finished())
        except Exception:
            _safe_log("连接按钮透明度动画 finished 信号失败（非致命）")

        # 按钮位置动画（从屏幕边缘滑出）
        self._button_pos_anim = QPropertyAnimation(self, b"buttonX", self)
        self._button_pos_anim.setDuration(150)
        self._button_pos_anim.setEasingCurve(QEasingCurve.InOutQuad)
        try:
            self._button_pos_anim.finished.connect(lambda: self._on_animation_finished())
        except Exception:
            _safe_log("连接按钮位置动画 finished 信号失败（非致命）")

        # 鼠标事件跟踪与延迟隐藏
        self._mouse_hide_timer = QTimer(self)
        self._mouse_hide_timer.setSingleShot(True)
        self._mouse_hide_timer.timeout.connect(self._hide_button_animated)

        # 初始状态：按钮隐藏（通过 opacity effect）

        # 将按钮初始位置设置到屏幕外，确保显示/隐藏动画有位移效果
        if self._side == "left":
            self._button_x_offset = -self._button_width
        else:
            self._button_x_offset = self._button_width
        self._update_layout()

        # 启用鼠标追踪
        self.setMouseTracking(True)
        self._toggle_btn.setMouseTracking(True)

        # 为按钮添加进入/离开事件的自定义处理
        self._original_button_enter_event = None
        self._original_button_leave_event = None
        self._setup_button_events()

        # 延迟安装父窗口的鼠标移动事件过滤器，确保在父窗口任意位置移动时可检测到边缘
        QTimer.singleShot(0, self._attach_parent_mouse_tracking)

        # 轮询定时器：在某些平台或布局下，事件过滤器可能无法覆盖所有鼠标移动，
        # 使用短间隔轮询全局鼠标位置作为补偿，保证边缘检测可靠性。
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(150)
        self._poll_timer.timeout.connect(self._check_edge_proximity)
        self._poll_timer.start()

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
            self._button_width,
            min(value, self._button_width + self._expanded_width),
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
                self._toggle_btn.setText(self._button_text_expanded if is_expanded else self._button_text_collapsed)
            else:  # right
                # 右侧：<< 表示隐藏（箭头指向右），>> 表示展开
                self._toggle_btn.setText(self._button_text_expanded if is_expanded else self._button_text_collapsed)

            # 设置总宽度
            self.setFixedWidth(self._sidebar_width)

            # 关键：右侧侧边栏展开/收起会改变宽度，需要同步重定位，否则会“向右溢出”看不见
            self._reposition_in_parent()

            # 手动定位子组件
            self._layout_children()
        except Exception:
            _safe_log("更新侧边栏布局失败（非致命）")

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
                btn_x = container_width - self._button_x_offset if self._button_x_offset >= 0 else container_width
                self._container.setGeometry(0, 0, container_width, h)
                self._toggle_btn.setGeometry(btn_x, button_y, self._button_width, 80)
                try:
                    self._toggle_btn.raise_()
                    self._toggle_btn.setAttribute(Qt.WA_TranslucentBackground, True)
                    self._toggle_btn.setAutoFillBackground(False)
                except Exception:
                    try:
                        _logger.debug("提升侧边栏按钮层级或设置属性失败（非致命）", exc_info=True)
                    except Exception:
                        _safe_log("提升侧边栏按钮层级或设置属性失败（非致命）")
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
                    try:
                        _logger.debug("提升侧边栏按钮层级或设置属性失败（非致命）", exc_info=True)
                    except Exception:
                        _safe_log("提升侧边栏按钮层级或设置属性失败（非致命）")
        except Exception:
            _safe_log("替换按钮事件处理失败（非致命）")

    def resizeEvent(self, event) -> None:
        """重新布局子组件。"""
        super().resizeEvent(event)
        try:
            self._reposition_in_parent()
        except Exception:
            _safe_log("重新定位父容器失败（非致命）")
        self._layout_children()

    def is_expanded(self) -> bool:
        return self._sidebar_width > self._button_width

    def show_panel(self) -> None:
        # 在展开时确保按钮可见且可交互
        # 即刻确保按钮可见（但在动画期间会被临时禁用）
        try:
            self._toggle_btn.setVisible(True)
        except Exception:
            try:
                _logger.debug("显示侧边栏按钮失败（非致命）", exc_info=True)
            except Exception:
                _safe_log("显示侧边栏按钮失败（非致命）")

        try:
            self._toggle_btn.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        except Exception:
            _safe_log("设置按钮鼠标穿透属性失败（非致命）")

        # 立即将按钮移到可见位置，避免快速点击时按钮仍在屏外
        self._button_x_offset = 0

        try:
            self._btn_opacity_effect.setOpacity(1.0)
        except Exception:
            _safe_log("设置按钮透明度失败（非致命）")

        self._update_layout()
        # 启动侧边栏展开动画（会在动画期间禁用切换按钮）
        self._animate_to(self._button_width + self._expanded_width)

    def hide_panel(self) -> None:
        self._animate_to(self._button_width)

    def toggle_panel(self) -> None:
        # 如果已有动画在运行，忽略重复触发以避免竞态
        try:
            if getattr(self, "_running_anim_count", 0) > 0:
                return
        except Exception:
            _safe_log("检查动画并发计数失败（非致命）")
        if self.is_expanded():
            self.hide_panel()
        else:
            self.show_panel()

    def _on_animation_started(self, count: int = 1) -> None:
        """在启动动画前调用：增加运行计数并临时禁用切换按钮以防止重复触发。"""
        try:
            self._running_anim_count = getattr(self, "_running_anim_count", 0) + int(count)
        except Exception:
            try:
                self._running_anim_count = 1
            except Exception:
                self._running_anim_count = 0
        try:
            # 禁用按钮交互并阻止鼠标穿透
            self._toggle_btn.setEnabled(False)
            self._toggle_btn.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        except Exception:
            _safe_log("在动画开始时禁用按钮失败（非致命）")

    def _on_animation_finished(self) -> None:
        """在动画完成时调用：减少计数并在所有动画完成后恢复按钮状态。"""
        try:
            prev = getattr(self, "_running_anim_count", 0)
            self._running_anim_count = max(0, prev - 1)
        except Exception:
            self._running_anim_count = 0

        # 仅在所有并发动画完成后恢复按钮
        try:
            if getattr(self, "_running_anim_count", 0) > 0:
                return
        except Exception:
            _safe_log("检查动画并发计数失败（非致命）")

        try:
            # 若按钮当前为可见或侧边栏展开，则启用交互；否则保持禁用以避免屏外点击
            visible = False
            try:
                visible = self._btn_opacity_effect.opacity() > 0.5
            except Exception:
                visible = True
            expanded = False
            try:
                expanded = self.is_expanded()
            except Exception:
                expanded = False

            if visible or expanded:
                try:
                    self._toggle_btn.setEnabled(True)
                    self._toggle_btn.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                except Exception:
                    _safe_log("恢复按钮交互失败（非致命）")

            else:
                try:
                    self._toggle_btn.setEnabled(False)
                    self._toggle_btn.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                except Exception:
                    _safe_log("禁用按钮交互失败（非致命）")
        except Exception:
            _safe_log("在动画完成后恢复按钮状态流程失败（非致命）")

    def _animate_to(self, target: int) -> None:
        # 启动侧边栏宽度动画：在开始前登记动画计数，结束时会自动回退
        try:
            # 增加一个动画计数
            self._on_animation_started(count=1)
        except Exception:
            _safe_log("标记动画开始失败（非致命）")
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
            _safe_log("mouseMoveEvent 检查边缘接近性失败（非致命）")
        super().mouseMoveEvent(event)

    def _on_parent_mouse_move(self, event: QMouseEvent) -> None:
        """全局鼠标移动事件（通过连接到父窗口）。"""
        try:
            self._check_edge_proximity()
        except Exception:
            try:
                _logger.debug("父窗口 mouse move 处理失败（非致命）", exc_info=True)
            except Exception:
                _logger.debug("父窗口 mouse move 处理失败（记录失败）", exc_info=True)

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

            # 优先检测顶层父窗口边缘（用户更常在窗口边缘触发），若未获取则退回到屏幕边缘检测
            parent_left = None
            parent_right = None
            try:
                parent_geom = root.frameGeometry()
                parent_left = parent_geom.left()
                parent_right = parent_geom.right()
                is_near_left = global_pos.x() <= parent_left + self._edge_detect_distance
                is_near_right = global_pos.x() >= parent_right - self._edge_detect_distance
            except Exception:
                is_near_left = global_pos.x() <= screen_geometry.left() + self._edge_detect_distance
                is_near_right = global_pos.x() >= screen_geometry.right() - self._edge_detect_distance

            # 判断是否应该显示按钮
            should_show = (self._side == "left" and is_near_left) or (self._side == "right" and is_near_right)

            if should_show:
                # 仅在显示状态发生变化时记录一次调试日志，避免刷屏
                if not self._last_should_show:
                    try:
                        _logger.debug(
                            "SlideSidebar: should_show=True mouse=(%s,%s) parent=(%s,%s) screen=(%s,%s)",
                            global_pos.x(),
                            global_pos.y(),
                            parent_left,
                            parent_right,
                            screen_geometry.left(),
                            screen_geometry.right(),
                        )
                    except Exception:
                        try:
                            _logger.debug("记录应显示日志失败（非致命）", exc_info=True)
                        except Exception:
                            _logger.debug("记录应显示日志失败（记录失败）", exc_info=True)
                    self._last_should_show = True

                self._show_button_animated()
                # 重置隐藏计时器
                self._mouse_hide_timer.stop()
                self._mouse_hide_timer.start(self._hide_delay_ms)
            elif self._btn_opacity_effect.opacity() > 0.5:
                # 鼠标离开边缘且不在按钮上方时，启动隐藏计时器
                if not self._is_mouse_on_button():
                    # 如果侧边栏已展开，则不自动隐藏按钮
                    if self.is_expanded():
                        self._last_should_show = True
                        return
                    # 仅在计时器未激活时启动，避免轮询不断重置计时器
                    if not self._mouse_hide_timer.isActive():
                        self._mouse_hide_timer.start(self._hide_delay_ms)
            else:
                # 当不应显示时，重置状态标记，便于下次变化时记录日志一次
                self._last_should_show = False
        except Exception:
            try:
                _logger.debug("检查边缘接近性失败（非致命）", exc_info=True)
            except Exception:
                _logger.debug("检查边缘接近性失败（记录失败）", exc_info=True)

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
            if self._btn_opacity_effect.opacity() > 0.9:
                return

            # 停止之前的动画
            self._button_opacity_anim.stop()
            self._button_pos_anim.stop()

            # 确保按钮可交互
            try:
                self._toggle_btn.setEnabled(True)
                self._toggle_btn.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            except Exception:
                try:
                    _logger.debug("设置按钮可交互失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("设置按钮可交互失败（记录失败）", exc_info=True)

            # 透明度与位置动画：将作为两个并发动画启动，登记为2个运行中动画
            try:
                self._on_animation_started(count=2)
            except Exception:
                try:
                    _logger.debug("登记并发动画计数失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("登记并发动画计数失败（记录失败）", exc_info=True)
            try:
                self._button_opacity_anim.setStartValue(self._btn_opacity_effect.opacity())
                self._button_opacity_anim.setEndValue(1.0)
            except Exception:
                try:
                    _logger.debug("设置按钮透明度动画起止值失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("设置按钮透明度动画起止值失败（记录失败）", exc_info=True)

            # 位置动画（从边缘滑入）
            try:
                self._button_pos_anim.setStartValue(self._button_x_offset)
                self._button_pos_anim.setEndValue(0)
            except Exception:
                try:
                    _logger.debug("设置按钮位置动画起止值失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("设置按钮位置动画起止值失败（记录失败）", exc_info=True)

            try:
                self._button_opacity_anim.start()
            except Exception:
                try:
                    _logger.debug("启动按钮透明度动画失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("启动按钮透明度动画失败（记录失败）", exc_info=True)
            try:
                self._button_pos_anim.start()
            except Exception:
                try:
                    _logger.debug("启动按钮位置动画失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("启动按钮位置动画失败（记录失败）", exc_info=True)
        except Exception:
            try:
                _logger.debug("显示按钮动画处理失败（非致命）", exc_info=True)
            except Exception:
                _logger.debug("显示按钮动画处理失败（记录失败）", exc_info=True)

    def _hide_button_animated(self) -> None:
        """隐藏按钮（带动画）。"""
        try:
            # 如果侧边栏已展开，则不要自动隐藏按钮
            if self.is_expanded():
                return

            # 检查鼠标是否仍在边缘或按钮上方，如果是则不隐藏
            if self._is_mouse_on_button():
                self._mouse_hide_timer.start(self._hide_delay_ms)
                return

            # 在隐藏时禁止按钮交互，避免透明但仍可点击
            try:
                self._toggle_btn.setEnabled(False)
                self._toggle_btn.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            except Exception:
                try:
                    _logger.debug("在隐藏时禁用按钮失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("在隐藏时禁用按钮失败（记录失败）", exc_info=True)

            # 停止之前的动画并启动隐藏的两个并发动画，登记为2个运行中动画
            try:
                self._button_opacity_anim.stop()
            except Exception:
                try:
                    _logger.debug("停止按钮透明度动画失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("停止按钮透明度动画失败（记录失败）", exc_info=True)
            try:
                self._button_pos_anim.stop()
            except Exception:
                try:
                    _logger.debug("停止按钮位置动画失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("停止按钮位置动画失败（记录失败）", exc_info=True)

            try:
                self._on_animation_started(count=2)
            except Exception:
                try:
                    _logger.debug("登记并发动画计数失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("登记并发动画计数失败（记录失败）", exc_info=True)

            # 透明度动画
            try:
                self._button_opacity_anim.setStartValue(self._btn_opacity_effect.opacity())
                self._button_opacity_anim.setEndValue(0.0)
            except Exception:
                try:
                    _logger.debug("设置按钮透明度动画起止值失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("设置按钮透明度动画起止值失败（记录失败）", exc_info=True)

            # 位置动画（滑出屏幕边缘）
            try:
                self._button_pos_anim.setStartValue(self._button_x_offset)
                target_offset = -self._button_width if self._side == "left" else self._button_width
                self._button_pos_anim.setEndValue(target_offset)
            except Exception:
                try:
                    _logger.debug("设置按钮位置动画起止值失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("设置按钮位置动画起止值失败（记录失败）", exc_info=True)

            try:
                self._button_opacity_anim.start()
            except Exception:
                try:
                    _logger.debug("启动按钮透明度动画失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("启动按钮透明度动画失败（记录失败）", exc_info=True)
            try:
                self._button_pos_anim.start()
            except Exception:
                try:
                    _logger.debug("启动按钮位置动画失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("启动按钮位置动画失败（记录失败）", exc_info=True)
        except Exception:
            try:
                _logger.debug("设置按钮自定义事件失败（非致命）", exc_info=True)
            except Exception:
                _logger.debug("设置按钮自定义事件失败（记录失败）", exc_info=True)

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
                    # 仅在侧边栏未展开时启动隐藏计时器
                    if not self.parent_sidebar.is_expanded():
                        self.parent_sidebar._mouse_hide_timer.start(self.parent_sidebar._hide_delay_ms)
                    return super().leaveEvent(event)

            # 保存原始事件处理
            self._original_button_enter_event = self._toggle_btn.enterEvent
            self._original_button_leave_event = self._toggle_btn.leaveEvent

            # 替换事件处理
            self._toggle_btn.enterEvent = self._on_button_enter
            self._toggle_btn.leaveEvent = self._on_button_leave
        except Exception:
            try:
                _logger.debug("安装父窗口鼠标跟踪失败（非致命）", exc_info=True)
            except Exception:
                _logger.debug("安装父窗口鼠标跟踪失败（记录失败）", exc_info=True)

    def _attach_parent_mouse_tracking(self) -> None:
        """为顶层父窗口安装事件过滤器以接收全局鼠标移动事件。"""
        try:
            root = self.parent()
            while root and root.parent():
                root = root.parent()

            if not root:
                return

            try:
                root.setMouseTracking(True)
            except Exception:
                try:
                    _logger.debug("为父窗口启用鼠标跟踪失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("为父窗口启用鼠标跟踪失败（记录失败）", exc_info=True)

            try:
                root.installEventFilter(self)
                _logger.debug("SlideSidebar: 已在父窗口安装事件过滤器: %s", root)
            except Exception:
                try:
                    _logger.debug("为父窗口安装事件过滤器失败（非致命）", exc_info=True)
                except Exception:
                    _logger.debug("为父窗口安装事件过滤器失败（记录失败）", exc_info=True)
        except Exception:
            try:
                _logger.debug("安装父窗口鼠标跟踪失败（非致命）", exc_info=True)
            except Exception:
                _logger.debug("安装父窗口鼠标跟踪失败（记录失败）", exc_info=True)

    def eventFilter(self, obj, event) -> bool:
        """捕获父窗口的鼠标移动事件并转发给内部处理逻辑。"""
        try:
            if event.type() == QEvent.MouseMove:
                # 将父窗口的鼠标移动事件转换为内部处理
                self._on_parent_mouse_move(event)
        except Exception:
            try:
                _logger.debug("事件过滤器处理异常（非致命）", exc_info=True)
            except Exception:
                _logger.debug("事件过滤器处理异常（记录失败）", exc_info=True)
        return super().eventFilter(obj, event)

    def _on_button_enter(self, event: QMouseEvent) -> None:
        """鼠标进入按钮时的事件处理。"""
        try:
            if self._mouse_hide_timer.isActive():
                self._mouse_hide_timer.stop()
        except Exception:
            try:
                _logger.debug("按钮进入事件处理异常（非致命）", exc_info=True)
            except Exception:
                _logger.debug("按钮进入事件处理异常（记录失败）", exc_info=True)

    def _on_button_leave(self, event: QMouseEvent) -> None:
        """鼠标离开按钮时的事件处理。"""
        try:
            # 仅在侧边栏未展开时启动隐藏计时器
            if not self.is_expanded():
                self._mouse_hide_timer.start(self._hide_delay_ms)
        except Exception:
            try:
                _logger.debug("按钮离开事件处理异常（非致命）", exc_info=True)
            except Exception:
                _logger.debug("按钮离开事件处理异常（记录失败）", exc_info=True)
