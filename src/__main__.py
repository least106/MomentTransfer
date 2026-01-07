# src/__main__.py
import sys
import os

def print_help():
    print("""
================================================
               MomentTransform
================================================

这是一个 Python 包，包含气动载荷坐标变换的核心算法。
请使用项目根目录下的入口脚本进行操作：

1. 批量处理 (推荐):
   python batch.py -c data/input.json -i data/loads.csv -o result.csv

2. 单点调试 (CLI):
   python cli.py

3. 图形界面 (GUI):
   python gui_main.py

------------------------------------------------
    """)

if __name__ == "__main__":
   print_help()