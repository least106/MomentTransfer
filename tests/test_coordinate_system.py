"""
坐标系模型单元测试 - 验证 CoordinateSystem 与 ReferenceValues 的基本功能
"""

import numpy as np
import pytest

from src.models.project_model import (
    CoordinateSystem,
    Part,
    PartVariant,
    ProjectConfigModel,
    ReferenceValues,
)


class TestCoordinateSystem:
    """CoordinateSystem 单元测试"""

    def test_coordinate_system_default(self):
        """测试默认坐标系创建"""
        cs = CoordinateSystem()
        assert cs.origin == [0.0, 0.0, 0.0]
        assert cs.x_axis == [1.0, 0.0, 0.0]
        assert cs.y_axis == [0.0, 1.0, 0.0]
        assert cs.z_axis == [0.0, 0.0, 1.0]
        assert cs.moment_center == [0.0, 0.0, 0.0]

    def test_coordinate_system_custom(self):
        """测试自定义坐标系"""
        cs = CoordinateSystem(
            origin=[1.0, 2.0, 3.0],
            x_axis=[1.0, 0.0, 0.0],
            y_axis=[0.0, 1.0, 0.0],
            z_axis=[0.0, 0.0, 1.0],
            moment_center=[0.5, 0.5, 0.5],
        )
        assert cs.origin == [1.0, 2.0, 3.0]
        assert cs.moment_center == [0.5, 0.5, 0.5]

    def test_coordinate_system_to_matrix(self):
        """测试转换为矩阵"""
        cs = CoordinateSystem(
            origin=[0.0, 0.0, 0.0],
            x_axis=[1.0, 0.0, 0.0],
            y_axis=[0.0, 1.0, 0.0],
            z_axis=[0.0, 0.0, 1.0],
        )
        matrix = cs.to_matrix()
        expected = np.eye(3)
        assert np.allclose(matrix, expected), f"预期 {expected}，实际 {matrix}"

    def test_coordinate_system_to_dict(self):
        """测试序列化为字典"""
        cs = CoordinateSystem(
            origin=[1.0, 0.0, 0.0],
            x_axis=[1.0, 0.0, 0.0],
            moment_center=[0.5, 0.5, 0.5],
        )
        data = cs.to_dict()
        assert data["Orig"] == [1.0, 0.0, 0.0]
        assert data["X"] == [1.0, 0.0, 0.0]
        assert data["MomentCenter"] == [0.5, 0.5, 0.5]

    def test_coordinate_system_from_dict(self):
        """测试从字典反序列化"""
        data = {
            "Orig": [1.0, 2.0, 3.0],
            "X": [1.0, 0.0, 0.0],
            "Y": [0.0, 1.0, 0.0],
            "Z": [0.0, 0.0, 1.0],
            "MomentCenter": [0.5, 0.5, 0.5],
        }
        cs = CoordinateSystem.from_dict(data)
        assert cs.origin == [1.0, 2.0, 3.0]
        assert cs.x_axis == [1.0, 0.0, 0.0]
        assert cs.moment_center == [0.5, 0.5, 0.5]

    def test_coordinate_system_roundtrip(self):
        """测试序列化/反序列化循环一致性"""
        original = CoordinateSystem(
            origin=[1.5, 2.5, 3.5],
            x_axis=[1.0, 0.1, 0.0],
            y_axis=[0.0, 1.0, 0.2],
            z_axis=[0.0, 0.0, 1.0],
            moment_center=[0.7, 0.8, 0.9],
        )
        data = original.to_dict()
        restored = CoordinateSystem.from_dict(data)
        assert restored.origin == original.origin
        assert restored.x_axis == original.x_axis
        assert restored.moment_center == original.moment_center


class TestReferenceValues:
    """ReferenceValues 单元测试"""

    def test_reference_values_default(self):
        """测试默认参考值"""
        refs = ReferenceValues()
        assert refs.cref == 1.0
        assert refs.bref == 1.0
        assert refs.sref == 10.0
        assert refs.q == 1000.0

    def test_reference_values_custom(self):
        """测试自定义参考值"""
        refs = ReferenceValues(cref=2.0, bref=3.0, sref=20.0, q=2000.0)
        assert refs.cref == 2.0
        assert refs.bref == 3.0
        assert refs.sref == 20.0
        assert refs.q == 2000.0

    def test_reference_values_to_dict(self):
        """测试参考值序列化"""
        refs = ReferenceValues(cref=2.0, bref=3.0, sref=20.0, q=2000.0)
        data = refs.to_dict()
        assert data["Cref"] == 2.0
        assert data["Bref"] == 3.0
        assert data["S"] == 20.0
        assert data["Q"] == 2000.0

    def test_reference_values_from_dict(self):
        """测试参考值反序列化（支持多种字段名）"""
        # 支持 'S' 或 'Sref'
        data1 = {"Cref": 2.0, "Bref": 3.0, "S": 20.0, "Q": 2000.0}
        refs1 = ReferenceValues.from_dict(data1)
        assert refs1.sref == 20.0

        # 支持 'Sref' 别名
        data2 = {"Cref": 2.0, "Bref": 3.0, "Sref": 25.0, "Q": 2000.0}
        refs2 = ReferenceValues.from_dict(data2)
        assert refs2.sref == 25.0


class TestPartVariant:
    """PartVariant 单元测试"""

    def test_part_variant_creation(self):
        """测试 PartVariant 创建"""
        cs = CoordinateSystem()
        refs = ReferenceValues()
        variant = PartVariant(part_name="TestPart", coord_system=cs, refs=refs)
        assert variant.part_name == "TestPart"
        assert variant.coord_system is not None
        assert variant.refs is not None

    def test_part_variant_to_dict(self):
        """测试 PartVariant 序列化"""
        cs = CoordinateSystem(origin=[1.0, 0.0, 0.0])
        refs = ReferenceValues(cref=2.0)
        variant = PartVariant(part_name="Part1", coord_system=cs, refs=refs)
        data = variant.to_dict()
        assert data["PartName"] == "Part1"
        assert data["CoordSystem"]["Orig"] == [1.0, 0.0, 0.0]
        assert data["Cref"] == 2.0

    def test_part_variant_from_dict(self):
        """测试 PartVariant 反序列化"""
        data = {
            "PartName": "Part1",
            "CoordSystem": {
                "Orig": [1.0, 0.0, 0.0],
                "X": [1.0, 0.0, 0.0],
                "Y": [0.0, 1.0, 0.0],
                "Z": [0.0, 0.0, 1.0],
            },
            "Cref": 2.0,
            "Bref": 3.0,
            "S": 20.0,
            "Q": 2000.0,
        }
        variant = PartVariant.from_dict(data)
        assert variant.part_name == "Part1"
        assert variant.coord_system.origin == [1.0, 0.0, 0.0]
        assert variant.refs.cref == 2.0


class TestPart:
    """Part 单元测试"""

    def test_part_creation(self):
        """测试 Part 创建"""
        cs = CoordinateSystem()
        refs = ReferenceValues()
        variant = PartVariant(part_name="Part1", coord_system=cs, refs=refs)
        part = Part(part_name="Part1", variants=[variant])
        assert part.part_name == "Part1"
        assert len(part.variants) == 1

    def test_part_to_dict(self):
        """测试 Part 序列化"""
        cs = CoordinateSystem()
        refs = ReferenceValues()
        variant = PartVariant(part_name="Part1", coord_system=cs, refs=refs)
        part = Part(part_name="Part1", variants=[variant])
        data = part.to_dict()
        assert data["PartName"] == "Part1"
        assert len(data["Variants"]) == 1


class TestProjectConfigModel:
    """ProjectConfigModel 单元测试"""

    def test_project_config_model_creation(self):
        """测试项目配置模型创建"""
        model = ProjectConfigModel()
        assert len(model.source_parts) == 0
        assert len(model.target_parts) == 0

    def test_project_config_model_add_part(self):
        """测试向项目中添加 Part"""
        model = ProjectConfigModel()
        cs = CoordinateSystem()
        refs = ReferenceValues()
        variant = PartVariant(part_name="Global", coord_system=cs, refs=refs)
        part = Part(part_name="Global", variants=[variant])
        model.source_parts["Global"] = part
        assert len(model.source_parts) == 1
        assert "Global" in model.source_parts

    def test_project_config_model_to_dict(self):
        """测试项目配置序列化"""
        model = ProjectConfigModel()
        cs = CoordinateSystem()
        refs = ReferenceValues()
        variant = PartVariant(part_name="Global", coord_system=cs, refs=refs)
        part = Part(part_name="Global", variants=[variant])
        model.source_parts["Global"] = part
        data = model.to_dict()
        assert "Source" in data
        assert len(data["Source"]["Parts"]) == 1

    def test_project_config_model_from_dict(self):
        """测试项目配置反序列化"""
        data = {
            "Source": {
                "Parts": [
                    {
                        "PartName": "Global",
                        "CoordSystem": {
                            "Orig": [0.0, 0.0, 0.0],
                            "X": [1.0, 0.0, 0.0],
                            "Y": [0.0, 1.0, 0.0],
                            "Z": [0.0, 0.0, 1.0],
                        },
                        "Cref": 1.0,
                        "Bref": 1.0,
                        "S": 10.0,
                        "Q": 1000.0,
                    }
                ]
            },
            "Target": {"Parts": []},
        }
        model = ProjectConfigModel.from_dict(data)
        assert "Global" in model.source_parts
        assert len(model.target_parts) == 0

    def test_project_config_model_roundtrip(self):
        """测试项目配置序列化/反序列化循环一致性"""
        # 创建原始模型
        original = ProjectConfigModel()
        cs = CoordinateSystem(origin=[1.0, 2.0, 3.0])
        refs = ReferenceValues(cref=2.0)
        variant = PartVariant(part_name="Part1", coord_system=cs, refs=refs)
        part = Part(part_name="Part1", variants=[variant])
        original.source_parts["Part1"] = part

        # 序列化
        data = original.to_dict()

        # 反序列化
        restored = ProjectConfigModel.from_dict(data)

        # 验证一致性
        assert "Part1" in restored.source_parts
        assert restored.source_parts["Part1"].variants[0].coord_system.origin == [
            1.0,
            2.0,
            3.0,
        ]
        assert restored.source_parts["Part1"].variants[0].refs.cref == 2.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
