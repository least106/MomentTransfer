"""应用入口：委托 gui.main_window.main，保持向后兼容。"""
from gui.main_window import main as run_main


def main():
    """启动 GUI 应用，直接复用 gui.main_window.main。"""
    run_main()


if __name__ == "__main__":
    main()
