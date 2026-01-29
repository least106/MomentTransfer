"""MomentTransfer GUI 应用入口

改动：为处理用户在终端按 Ctrl+C 导致的 KeyboardInterrupt，添加 SIGINT 处理
以便优雅退出 Qt 应用并避免在控制台打印未捕获的回溯。
"""

import logging
import signal
import sys
from PySide6 import QtWidgets

from gui.main_window import main as run_main

logging.basicConfig(level=logging.DEBUG)


def main():
    """启动 GUI 应用，安装 SIGINT 处理并优雅退出"""

    # 让 Ctrl+C 触发 Qt 的退出流程（在主线程中有效）
    try:
        signal.signal(signal.SIGINT, lambda *_: QtWidgets.QApplication.quit())
    except Exception:
        logging.getLogger(__name__).debug("无法安装 SIGINT 处理器（非致命）", exc_info=True)

    try:
        run_main()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("收到 KeyboardInterrupt，正在退出")
        try:
            QtWidgets.QApplication.quit()
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()
