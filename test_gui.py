# -*- coding: utf-8 -*-
"""测试GUI启动并捕获错误"""
import sys
import traceback

try:
    # 导入主模块
    import gui
    print("GUI模块导入成功")
    
    # 调用main函数
    gui.main()
except Exception as e:
    print(f"错误类型: {type(e).__name__}")
    print(f"错误信息: {str(e)}")
    print("\n完整堆栈:")
    traceback.print_exc()
    sys.exit(1)
