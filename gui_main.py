"""MomentTransfer GUI 应用入口"""

import logging

from gui.main_window import main as run_main

logging.basicConfig(level=logging.DEBUG)


def main():
    """启动 GUI 应用"""
    run_main()


if __name__ == "__main__":
    main()
