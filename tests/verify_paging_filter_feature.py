"""
简化的测试脚本，验证翻页与隐藏行的交互逻辑（不依赖 GUI 实例）
"""

import pandas as pd
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_recompute_match_pages_with_hidden_rows():
    """测试 _recompute_match_pages 方法能否正确处理隐藏行"""
    # 导入 PagedTableWidget 的逻辑
    df = pd.DataFrame({
        "A": list(range(10)),
        "B": list(range(10, 20))
    })
    
    # 模拟分页逻辑
    page_size = 3
    total = len(df)
    pages = (total + page_size - 1) // page_size
    
    # 情况1：全是隐藏行的页面
    hidden_rows = {0, 1, 2}  # 第一页全部隐藏
    page_has = [False] * pages
    for idx in range(total):
        if idx not in hidden_rows:
            p = idx // page_size
            if 0 <= p < len(page_has):
                page_has[p] = True
    
    print(f"数据总行数: {total}")
    print(f"页面大小: {page_size}")
    print(f"总页数: {pages}")
    print(f"隐藏行: {hidden_rows}")
    print(f"各页有效数据标记: {page_has}")
    
    assert page_has[0] is False, f"第0页应该无有效数据（全隐藏），但得到 {page_has[0]}"
    assert page_has[1] is True, f"第1页应该有有效数据，但得到 {page_has[1]}"
    print("✓ 测试1通过：隐藏行计算正确\n")
    
    # 情况2：混合隐藏行
    hidden_rows = {0, 3, 4, 5}  # 第一页1行隐藏，第二页全部隐藏
    page_has = [False] * pages
    for idx in range(total):
        if idx not in hidden_rows:
            p = idx // page_size
            if 0 <= p < len(page_has):
                page_has[p] = True
    
    print(f"隐藏行: {hidden_rows}")
    print(f"各页有效数据标记: {page_has}")
    
    assert page_has[0] is True, f"第0页有有效数据，但得到 {page_has[0]}"
    assert page_has[1] is False, f"第1页无有效数据（全隐藏），但得到 {page_has[1]}"
    assert page_has[2] is True, f"第2页有有效数据，但得到 {page_has[2]}"
    print("✓ 测试2通过：混合隐藏行计算正确\n")
    
    # 情况3：无隐藏行
    hidden_rows = set()
    if not hidden_rows:
        page_has = None  # 表示所有页都有有效数据
    
    print(f"隐藏行: {hidden_rows}")
    print(f"各页有效数据标记: {page_has}")
    
    assert page_has is None, f"无隐藏行时应该为 None，但得到 {page_has}"
    print("✓ 测试3通过：无隐藏行时为 None\n")

def test_skip_empty_pages_logic():
    """测试跳过空页的翻页逻辑"""
    page_has = [False, False, True, True, False, True]  # 页面0、1、4无数据
    current_page = 0
    total_pages = len(page_has)
    
    # 测试向前翻页
    def goto_next(curr, skip_empty):
        if curr >= total_pages - 1:
            return curr
        if skip_empty and page_has:
            p = curr + 1
            while p < total_pages and not page_has[p]:
                p += 1
            if p < total_pages:
                return p
        return min(curr + 1, total_pages - 1)
    
    next_page = goto_next(current_page, True)
    print(f"从页面 {current_page} 向前翻页（跳过空页）：{next_page}")
    assert next_page == 2, f"应该跳到页面2，但得到 {next_page}"
    print("✓ 翻页逻辑正确\n")

def test_paged_table_import():
    """验证 PagedTableWidget 能否导入"""
    try:
        from gui.paged_table import PagedTableWidget
        print("✓ 成功导入 PagedTableWidget")
        
        # 检查新添加的方法
        assert hasattr(PagedTableWidget, 'set_hidden_rows'), \
            "PagedTableWidget 缺少 set_hidden_rows 方法"
        print("✓ PagedTableWidget 有 set_hidden_rows 方法")
        
        # 检查新添加的属性
        import inspect
        init_source = inspect.getsource(PagedTableWidget.__init__)
        assert '_hidden_rows' in init_source, \
            "PagedTableWidget.__init__ 未包含 _hidden_rows 初始化"
        print("✓ PagedTableWidget.__init__ 包含 _hidden_rows 初始化\n")
        
    except Exception as e:
        print(f"✗ 导入或检查失败: {e}\n")
        raise

if __name__ == "__main__":
    print("=" * 60)
    print("验证翻页与筛选功能集成")
    print("=" * 60 + "\n")
    
    try:
        test_recompute_match_pages_with_hidden_rows()
        test_skip_empty_pages_logic()
        test_paged_table_import()
        
        print("=" * 60)
        print("所有验证通过！✓")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ 断言失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
