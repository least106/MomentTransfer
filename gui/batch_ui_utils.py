"""批处理 UI 工具模块

提供批处理相关的 UI 辅助功能，如控件样式管理、状态更新等。
"""

import logging

logger = logging.getLogger(__name__)


def set_control_enabled_with_style(widget, enabled: bool):
    """设置控件启用状态并在单文件模式下通过文字颜色灰显提示（安全包装）

    Args:
        widget: Qt 控件对象
        enabled: 是否启用控件
    """
    try:
        if widget is None:
            return

        # 优先使用 setEnabled 保持控件行为一致且让 Qt 按主题处理禁用样式
        try:
            widget.setEnabled(enabled)
            return
        except Exception:
            # 个别自定义控件可能不支持 setEnabled，继续尝试更温和的视觉提示
            logger.debug("控件不支持 setEnabled，尝试使用调色板/样式回退", exc_info=True)

        # 回退：尝试使用 QPalette 根据状态设置文字颜色，优先保证对暗色/亮色主题友好
        try:
            from PySide6.QtGui import QPalette

            pal = widget.palette()
            if not enabled:
                # 使用 Disabled 状态下的文本颜色
                try:
                    disabled_color = pal.color(QPalette.Disabled, QPalette.Text)
                except Exception:
                    disabled_color = pal.color(QPalette.Text)
                try:
                    pal.setColor(QPalette.Active, QPalette.Text, disabled_color)
                    pal.setColor(QPalette.Inactive, QPalette.Text, disabled_color)
                except Exception:
                    try:
                        pal.setColor(QPalette.Text, disabled_color)
                    except Exception:
                        logger.debug("设置 QPalette 文本颜色失败（非致命）", exc_info=True)
            else:
                # 恢复为 Active 状态的文本颜色
                try:
                    active_color = pal.color(QPalette.Active, QPalette.Text)
                    pal.setColor(QPalette.Active, QPalette.Text, active_color)
                    pal.setColor(QPalette.Inactive, QPalette.Text, active_color)
                except Exception:
                    logger.debug("恢复 Active 状态颜色失败（非致命）", exc_info=True)
            try:
                widget.setPalette(pal)
                widget.update()
                return
            except Exception:
                logger.debug("使用 QPalette 设置控件颜色失败，尝试样式表回退", exc_info=True)
        except Exception:
            logger.debug("构建 QPalette 回退路径失败", exc_info=True)

        # 最后回退：尝试从控件的调色板获取一个主题中性颜色作为折中
        try:
            from PySide6.QtGui import QPalette

            pal = widget.palette()
            try:
                c = pal.color(QPalette.Disabled, QPalette.Text)
            except Exception:
                c = pal.color(QPalette.Text)
            try:
                neutral_gray = f"color: {c.name()};"
            except Exception:
                neutral_gray = "color: gray;"
        except Exception:
            neutral_gray = "color: gray;"

        try:
            widget.setStyleSheet("" if enabled else neutral_gray)
        except Exception:
            logger.debug("使用 setStyleSheet 回退失败", exc_info=True)

    except Exception:
        logger.debug("设置控件启用/样式失败", exc_info=True)
