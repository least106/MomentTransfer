"""对话框辅助模块 - 提供标准化的对话框创建和配置功能"""

import logging
from typing import Optional

from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


def create_confirmation_dialog(
    parent,
    title: str,
    message: str,
    details: Optional[str] = None,
    default_button: str = "cancel",
) -> QMessageBox:
    """
    创建确认对话框

    参数：
        parent: 父窗口
        title: 对话框标题
        message: 对话框消息
        details: 详细信息
        default_button: 默认按钮（"ok" 或 "cancel"）

    返回：
        配置好的 QMessageBox
    """
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Warning)
    msg.setWindowTitle(title)
    msg.setText(message)

    if details:
        msg.setDetailedText(details)

    # 添加按钮
    btn_ok = msg.addButton("确定", QMessageBox.AcceptRole)
    btn_cancel = msg.addButton("取消", QMessageBox.RejectRole)

    # 设置默认按钮
    if default_button == "ok":
        msg.setDefaultButton(btn_ok)
    else:
        msg.setDefaultButton(btn_cancel)

    # 设置 Esc 按钮
    msg.setEscapeButton(btn_cancel)

    return msg


def show_warning_dialog(
    parent, title: str, message: str, details: Optional[str] = None
) -> bool:
    """
    显示警告对话框

    参数：
        parent: 父窗口
        title: 对话框标题
        message: 对话框消息
        details: 详细信息

    返回：
        用户是否点击了确定
    """
    try:
        msg = create_confirmation_dialog(parent, title, message, details)
        result = msg.exec()
        return result == QMessageBox.AcceptRole
    except Exception:
        logger.debug("显示警告对话框失败", exc_info=True)
        return False


def show_info_dialog(parent, title: str, message: str, details: Optional[str] = None):
    """
    显示信息对话框

    参数：
        parent: 父窗口
        title: 对话框标题
        message: 对话框消息
        details: 详细信息
    """
    try:
        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle(title)
        msg.setText(message)

        if details:
            msg.setDetailedText(details)

        msg.exec()
    except Exception:
        logger.debug("显示信息对话框失败", exc_info=True)


def show_error_dialog(parent, title: str, message: str, details: Optional[str] = None):
    """
    显示错误对话框

    参数：
        parent: 父窗口
        title: 对话框标题
        message: 对话框消息
        details: 详细信息
    """
    try:
        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle(title)
        msg.setText(message)

        if details:
            msg.setDetailedText(details)

        msg.exec()
    except Exception:
        logger.debug("显示错误对话框失败", exc_info=True)


def create_save_changes_dialog(
    parent, title: str = "保存更改？", message: Optional[str] = None
) -> QMessageBox:
    """
    创建保存更改对话框（带保存、不保存、取消三个按钮）

    参数：
        parent: 父窗口
        title: 对话框标题
        message: 对话框消息

    返回：
        配置好的 QMessageBox
    """
    if message is None:
        message = "是否保存对当前配置的更改？"

    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Warning)
    msg.setWindowTitle(title)
    msg.setText(message)

    # 添加按钮
    msg.addButton("保存", QMessageBox.AcceptRole)
    msg.addButton("不保存", QMessageBox.DestructiveRole)
    btn_cancel = msg.addButton("取消", QMessageBox.RejectRole)

    # 设置默认按钮（降低误操作风险）
    msg.setDefaultButton(btn_cancel)
    msg.setEscapeButton(btn_cancel)

    return msg


def show_save_changes_dialog(
    parent, title: str = "保存更改？", message: Optional[str] = None
) -> Optional[str]:
    """
    显示保存更改对话框

    参数：
        parent: 父窗口
        title: 对话框标题
        message: 对话框消息

    返回：
        "save", "discard", "cancel" 或 None（出错时）
    """
    try:
        msg = create_save_changes_dialog(parent, title, message)
        msg.exec()

        # 获取点击的按钮
        clicked_button = msg.clickedButton()
        button_text = clicked_button.text() if clicked_button else ""

        if "保存" in button_text:
            return "save"
        if "不保存" in button_text:
            return "discard"
        return "cancel"

    except Exception:
        logger.debug("显示保存更改对话框失败", exc_info=True)
        return None


def configure_message_box_safe(msg: QMessageBox) -> bool:
    """
    安全配置消息框（防止误操作）

    参数：
        msg: 消息框

    返回：
        是否配置成功
    """
    try:
        # 防止误触 Enter
        cancel_buttons = msg.buttons()
        if cancel_buttons:
            for btn in cancel_buttons:
                if btn.text() in ["取消", "Cancel"]:
                    msg.setDefaultButton(btn)
                    msg.setEscapeButton(btn)
                    break
        return True
    except Exception:
        logger.debug("配置消息框失败", exc_info=True)
        return False
