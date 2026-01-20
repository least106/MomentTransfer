"""MomentTransfer GUI 应用入口"""

from gui.main_window import main as run_main
import logging
logging.basicConfig(level=logging.DEBUG)

def main():
    """启动 GUI 应用"""
    run_main()


if __name__ == "__main__":
    main()
