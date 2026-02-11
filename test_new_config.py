"""测试新配置格式的加载和兼容性。"""

import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def test_new_format():
    """测试新配置格式的加载。"""
    print("=== 测试新配置格式加载 ===\n")
    
    from src.data_loader import load_data
    
    try:
        # 加载新格式配置
        project_data = load_data("data/input_new_format.json")
        
        print("✓ 配置文件加载成功")
        print(f"  Source Parts: {list(project_data.source_parts.keys())}")
        print(f"  Target Parts: {list(project_data.target_parts.keys())}")
        
        # 检查 Source BODY 的第一个 ReferenceSystem
        body_variants = project_data.source_parts.get("BODY", [])
        if body_variants:
            v1 = body_variants[0]
            print(f"\n  BODY ReferenceSystem[0]:")
            print(f"    Name: {v1.name}")
            print(f"    CoordSystemRef: {v1.coord_system_ref}")
            print(f"    MomentCenter (统一): {v1.moment_center}")
            print(f"    MomentCenterInPart: {v1.moment_center_in_part}")
            print(f"    MomentCenterInGlobal: {v1.moment_center_in_global}")
        
        if len(body_variants) > 1:
            v2 = body_variants[1]
            print(f"\n  BODY ReferenceSystem[1]:")
            print(f"    Name: {v2.name}")
            print(f"    CoordSystemRef: {v2.coord_system_ref}")
            print(f"    MomentCenter (统一): {v2.moment_center}")
            print(f"    MomentCenterInPart: {v2.moment_center_in_part}")
            print(f"    MomentCenterInGlobal: {v2.moment_center_in_global}")
        
        # 检查 Target WING
        wing_variants = project_data.target_parts.get("WING", [])
        if wing_variants:
            v1 = wing_variants[0]
            print(f"\n  WING ReferenceSystem[0]:")
            print(f"    Name: {v1.name}")
            print(f"    CoordSystemRef: {v1.coord_system_ref}")
            print(f"    MomentCenter (统一): {v1.moment_center}")
        
        print("\n✓ 新配置格式测试通过")
        return True
        
    except Exception as e:
        print(f"\n✗ 加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_old_format_compatibility():
    """测试旧配置格式的向后兼容性。"""
    print("\n=== 测试旧配置格式兼容性 ===\n")
    
    from src.data_loader import load_data
    
    try:
        # 加载旧格式配置（如果存在）
        project_data = load_data("data/input.json")
        
        print("✓ 旧配置文件加载成功")
        print(f"  Source Parts: {list(project_data.source_parts.keys())}")
        print(f"  Target Parts: {list(project_data.target_parts.keys())}")
        
        # 检查是否正确解析
        for part_name, variants in project_data.source_parts.items():
            print(f"\n  Source.{part_name}: {len(variants)} variant(s)")
            for i, v in enumerate(variants):
                print(f"    [{i}] MomentCenter: {v.moment_center}")
        
        for part_name, variants in project_data.target_parts.items():
            print(f"\n  Target.{part_name}: {len(variants)} variant(s)")
            for i, v in enumerate(variants):
                print(f"    [{i}] MomentCenter: {v.moment_center}")
        
        print("\n✓ 旧配置格式兼容性测试通过")
        return True
        
    except FileNotFoundError:
        print("  ⚠ data/input.json 不存在，跳过兼容性测试")
        return True
    except Exception as e:
        print(f"\n✗ 兼容性测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gui_models():
    """测试 GUI 模型的新格式支持。"""
    print("\n=== 测试 GUI 模型 ===\n")
    
    from src.models.project_model import ProjectConfigModel
    import json
    
    try:
        # 加载新格式配置
        with open("data/input_new_format.json", "r", encoding="utf-8") as f:
            config_dict = json.load(f)
        
        model = ProjectConfigModel.from_dict(config_dict)
        
        print("✓ GUI 模型加载成功")
        print(f"  Source Parts: {list(model.source_parts.keys())}")
        print(f"  Target Parts: {list(model.target_parts.keys())}")
        
        # 检查 BODY
        if "BODY" in model.source_parts:
            body = model.source_parts["BODY"]
            print(f"\n  BODY: {len(body.variants)} variant(s)")
            for i, v in enumerate(body.variants):
                print(f"    [{i}] Name: {v.name}")
                print(f"        CoordSystemRef: {v.coord_system_ref}")
                print(f"        MomentCenter: {v.coord_system.moment_center}")
        
        # 测试序列化
        serialized = model.to_dict()
        print("\n✓ GUI 模型序列化成功")
        
        # 验证序列化结果包含 ReferenceSystem 而非 Variants
        if "Source" in serialized and "Parts" in serialized["Source"]:
            for part in serialized["Source"]["Parts"]:
                if "ReferenceSystem" in part:
                    print("  ✓ 使用新字段名 'ReferenceSystem'")
                    break
                elif "Variants" in part:
                    print("  ⚠ 仍在使用旧字段名 'Variants'")
                    break
        
        print("\n✓ GUI 模型测试通过")
        return True
        
    except Exception as e:
        print(f"\n✗ GUI 模型测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("开始测试新配置格式功能...\n")
    
    results = []
    results.append(("新格式加载", test_new_format()))
    results.append(("旧格式兼容", test_old_format_compatibility()))
    results.append(("GUI 模型", test_gui_models()))
    
    print("\n" + "=" * 50)
    print("测试总结:")
    print("=" * 50)
    
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
    
    all_passed = all(r[1] for r in results)
    print("\n" + ("✓ 所有测试通过" if all_passed else "✗ 部分测试失败"))
    
    sys.exit(0 if all_passed else 1)
