"""命令行帮助入口，用于在直接运行包时显示简要使用说明。"""

import logging


def print_help():
    """打印简要的使用帮助信息到日志（默认 INFO）。"""
    help_text = """
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
    """
    logger = logging.getLogger(__name__)
    logger.info("\n%s", help_text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print_help()
