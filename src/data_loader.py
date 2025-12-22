import json
from dataclasses import dataclass
from typing import List, Dict, Any

# 定义数据结构 (Data Schema)
@dataclass
class CoordSystemDefinition:
    """定义坐标系的原点和基向量"""
    origin: List[float]  # 对应 JSON: Orig
    x_axis: List[float]  # 对应 JSON: X
    y_axis: List[float]  # 对应 JSON: Y
    z_axis: List[float]  # 对应 JSON: Z

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从字典创建对象的工厂方法

        TODO: 验证字段存在且为长度为 3 的数值列表；若缺失或类型不匹配，应抛出 ValueError 并给出明确错误信息。
        建议添加单元测试覆盖缺失字段、维度不对和非法类型的场景。
        """
        # TODO: 验证字段和维度（例如：len == 3 且元素为数值）
        return cls(
            origin=data["Orig"],
            x_axis=data["X"],
            y_axis=data["Y"],
            z_axis=data["Z"]
        )

@dataclass
class TargetDefinition:
    """定义目标状态（气流系/体轴系）及参考量"""
    part_name: str
    coord_system: CoordSystemDefinition
    moment_center: List[float]  # 目标矩心
    c_ref: float               # 参考弦长
    b_ref: float               # 参考展长
    q: float                   # 动压
    s_ref: float               # 参考面积

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        # TODO: 验证 Target 字段完整性（PartName, TargetCoordSystem, TargetMomentCenter）
        # 对数值字段（q, s_ref, c_ref, b_ref）添加合理性检查（例如非负）并抛出有意义的错误信息。
        return cls(
            part_name=data["PartName"],
            coord_system=CoordSystemDefinition.from_dict(data["TargetCoordSystem"]),
            moment_center=data["TargetMomentCenter"],
            c_ref=data.get("Cref", 1.0),
            b_ref=data.get("Bref", 1.0),
            q=data.get("Q", 0.0),
            s_ref=data.get("S", 1.0) # 对应 JSON 中的 S
        )

@dataclass
class ProjectData:
    """顶级数据类，包含整个配置文件"""
    source_coord: CoordSystemDefinition
    target_config: TargetDefinition

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        return cls(
            source_coord=CoordSystemDefinition.from_dict(data["SourceCoordSystem"]),
            target_config=TargetDefinition.from_dict(data["Target"])
        )

# 核心加载函数
def load_data(file_path: str) -> ProjectData:
    """
    读取 JSON 文件并转换为 Python 对象
    :param file_path: input.json 的路径
    :return: ProjectData 对象
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        # 将原始字典转换为结构化对象
        return ProjectData.from_dict(raw_data)
        
    except FileNotFoundError:
        raise FileNotFoundError(f"错误: 找不到文件 {file_path}，请检查路径。")
    except json.JSONDecodeError:
        raise ValueError(f"错误: 文件 {file_path} 不是有效的 JSON 格式。")
    except KeyError as e:
        raise KeyError(f"错误: JSON 数据缺少关键字段 {e}，请检查输入文件结构。")
