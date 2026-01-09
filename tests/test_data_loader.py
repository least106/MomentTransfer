"""
测试 data_loader 模块的功能，包括输入校验、边缘情况处理
"""

import pytest
import json
import tempfile
import os
from src.data_loader import (
    load_data,
    CoordSystemDefinition,
    TargetDefinition,
    ProjectData,
)


class TestCoordSystemDefinition:
    """测试坐标系定义的解析和校验"""

    def test_valid_coord_system(self):
        """测试合法的坐标系定义"""
        data = {
            "Orig": [0.0, 0.0, 0.0],
            "X": [1.0, 0.0, 0.0],
            "Y": [0.0, 1.0, 0.0],
            "Z": [0.0, 0.0, 1.0],
        }
        coord = CoordSystemDefinition.from_dict(data)
        assert coord.origin == [0.0, 0.0, 0.0]
        assert coord.x_axis == [1.0, 0.0, 0.0]

    def test_missing_field(self):
        """测试缺失必须字段"""
        data = {
            "Orig": [0.0, 0.0, 0.0],
            "X": [1.0, 0.0, 0.0],
            "Y": [0.0, 1.0, 0.0],
            # 缺少 Z
        }
        with pytest.raises(ValueError, match="缺少必须字段: Z"):
            CoordSystemDefinition.from_dict(data)

    def test_wrong_dimension(self):
        """测试向量维度错误"""
        data = {
            "Orig": [0.0, 0.0],  # 只有 2 个元素
            "X": [1.0, 0.0, 0.0],
            "Y": [0.0, 1.0, 0.0],
            "Z": [0.0, 0.0, 1.0],
        }
        with pytest.raises(ValueError, match="必须包含 3 个元素"):
            CoordSystemDefinition.from_dict(data)

    def test_non_numeric_values(self):
        """测试非数值类型"""
        data = {
            "Orig": [0.0, 0.0, 0.0],
            "X": ["a", "b", "c"],  # 字符串而非数值
            "Y": [0.0, 1.0, 0.0],
            "Z": [0.0, 0.0, 1.0],
        }
        with pytest.raises(ValueError, match="必须是数值类型"):
            CoordSystemDefinition.from_dict(data)


class TestTargetDefinition:
    """测试 Target 配置的解析和校验"""

    def test_valid_target(self):
        """测试合法的 Target 定义"""
        data = {
            "PartName": "TestPart",
            "TargetCoordSystem": {
                "Orig": [0, 0, 0],
                "X": [1, 0, 0],
                "Y": [0, 1, 0],
                "Z": [0, 0, 1],
            },
            "TargetMomentCenter": [0.5, 0.5, 0.5],
            "Cref": 1.0,
            "Bref": 2.0,
            "Q": 100.0,
            "S": 1.5,
        }
        target = TargetDefinition.from_dict(data)
        assert target.part_name == "TestPart"
        assert target.q == 100.0
        assert target.c_ref == 1.0

    def test_missing_part_name(self):
        """测试缺失 PartName"""
        data = {
            "TargetCoordSystem": {
                "Orig": [0, 0, 0],
                "X": [1, 0, 0],
                "Y": [0, 1, 0],
                "Z": [0, 0, 1],
            },
            "TargetMomentCenter": [0, 0, 0],
        }
        with pytest.raises(ValueError, match="缺少必须字段: PartName"):
            TargetDefinition.from_dict(data)

    def test_negative_reference_length(self):
        """测试参考长度为负数"""
        data = {
            "PartName": "TestPart",
            "TargetCoordSystem": {
                "Orig": [0, 0, 0],
                "X": [1, 0, 0],
                "Y": [0, 1, 0],
                "Z": [0, 0, 1],
            },
            "TargetMomentCenter": [0, 0, 0],
            "Cref": -1.0,  # 负数
        }
        with pytest.raises(ValueError, match="字段 Cref 必须为严格正数"):
            TargetDefinition.from_dict(data)

    def test_negative_dynamic_pressure(self):
        """测试动压为负数"""
        data = {
            "PartName": "TestPart",
            "TargetCoordSystem": {
                "Orig": [0, 0, 0],
                "X": [1, 0, 0],
                "Y": [0, 1, 0],
                "Z": [0, 0, 1],
            },
            "TargetMomentCenter": [0, 0, 0],
            "Q": -10.0,  # 负数
        }
        with pytest.raises(ValueError, match="字段 Q 必须为非负数"):
            TargetDefinition.from_dict(data)


class TestLoadData:
    """测试 load_data 函数的文件加载和异常处理"""

    def test_load_valid_json(self):
        """测试加载合法的 JSON 文件"""
        # 使用新版 ProjectData 的格式（包含 Source / Target 部分）
        # 使用新版 Parts/Variants 结构
        valid_data = {
            "Source": {
                "Parts": [
                    {
                        "PartName": "SrcPart",
                        "Variants": [
                            {
                                "CoordSystem": {
                                    "Orig": [0, 0, 0],
                                    "X": [1, 0, 0],
                                    "Y": [0, 1, 0],
                                    "Z": [0, 0, 1],
                                },
                                "MomentCenter": [0, 0, 0],
                                "Q": 100.0,
                                "S": 1.0,
                                "Cref": 1.0,
                                "Bref": 2.0,
                            }
                        ],
                    }
                ]
            },
            "Target": {
                "Parts": [
                    {
                        "PartName": "TestPart",
                        "Variants": [
                            {
                                "CoordSystem": {
                                    "Orig": [1, 1, 1],
                                    "X": [1, 0, 0],
                                    "Y": [0, 1, 0],
                                    "Z": [0, 0, 1],
                                },
                                "MomentCenter": [0, 0, 0],
                                "Q": 100.0,
                                "S": 1.0,
                                "Cref": 1.0,
                                "Bref": 2.0,
                            }
                        ],
                    }
                ]
            },
        }

        # 创建临时文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(valid_data, f)
            temp_path = f.name

        try:
            project = load_data(temp_path)
            assert isinstance(project, ProjectData)
            assert project.target_config.part_name == "TestPart"
        finally:
            os.unlink(temp_path)

    def test_file_not_found(self):
        """测试文件不存在"""
        with pytest.raises(FileNotFoundError, match="找不到文件"):
            load_data("nonexistent_file.json")

    def test_invalid_json(self):
        """测试非法 JSON 格式"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("{invalid json content")
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="不是有效的 JSON 格式"):
                load_data(temp_path)
        finally:
            os.unlink(temp_path)

    def test_missing_top_level_field(self):
        """测试缺失顶层字段"""
        incomplete_data = {
            "SourceCoordSystem": {
                "Orig": [0, 0, 0],
                "X": [1, 0, 0],
                "Y": [0, 1, 0],
                "Z": [0, 0, 1],
            }
            # 缺少 Target
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(incomplete_data, f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="配置文件缺少"):
                load_data(temp_path)
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
