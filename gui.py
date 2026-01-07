"""
兼容入口脚本：请使用 gui_main.py。

本文件保留为兼容启动，运行时将委托到 gui_main.py。
为避免包名冲突（gui/ 目录与 gui.py 同名导致导入混乱），
主窗口实现已迁移到 gui_main.py。
"""
import sys

try:
    import gui_main
except Exception:
    print("ERROR: 请改用: python gui_main.py")
    raise

if __name__ == "__main__":
    gui_main.main()
