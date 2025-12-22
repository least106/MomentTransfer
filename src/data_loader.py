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
        """从字典创建对象的工厂方法，包含输入校验"""
        required_fields = ["Orig", "X", "Y", "Z"]
        
        # 验证必须字段存在
        for field in required_fields:
            if field not in data:
                raise ValueError(f"坐标系定义缺少必须字段: {field}")
        
        # 验证每个字段都是长度为 3 的数值列表
        def validate_vector(vec, field_name):
            if not isinstance(vec, (list, tuple)):
                raise ValueError(f"字段 {field_name} 必须是列表或元组，当前类型: {type(vec).__name__}")
            if len(vec) != 3:
                raise ValueError(f"字段 {field_name} 必须包含 3 个元素，当前长度: {len(vec)}")
            try:
                # 尝试转换为浮点数以验证是数值类型
                [float(x) for x in vec]
            except (ValueError, TypeError) as e:
                raise ValueError(f"字段 {field_name} 的元素必须是数值类型: {e}")
        
        validate_vector(data["Orig"], "Orig")
        validate_vector(data["X"], "X")
        validate_vector(data["Y"], "Y")
        validate_vector(data["Z"], "Z")
        
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
        """从字典创建 Target 对象，包含输入校验"""
        # 验证必须字段
        if "PartName" not in data:
            raise ValueError("Target 定义缺少必须字段: PartName")
        if "TargetCoordSystem" not in data:
            raise ValueError("Target 定义缺少必须字段: TargetCoordSystem")
        if "TargetMomentCenter" not in data:
            raise ValueError("Target 定义缺少必须字段: TargetMomentCenter")
        
        # 验证力矩中心是 3 维向量
        moment_center = data["TargetMomentCenter"]
        if not isinstance(moment_center, (list, tuple)) or len(moment_center) != 3:
            raise ValueError(f"TargetMomentCenter 必须是长度为 3 的列表，当前: {moment_center}")
        
        # 获取数值参数并验证非负
        c_ref = data.get("Cref", 1.0)
        b_ref = data.get("Bref", 1.0)
        q = data.get("Q", 0.0)
        s_ref = data.get("S", 1.0)
        
        # 验证参考长度和面积为正数
        if c_ref <= 0:
            raise ValueError(f"参考弦长 Cref 必须为正数，当前值: {c_ref}")
        if b_ref <= 0:
            raise ValueError(f"参考展长 Bref 必须为正数，当前值: {b_ref}")
        if s_ref <= 0:
            raise ValueError(f"参考面积 S 必须为正数，当前值: {s_ref}")
        if q < 0:
            raise ValueError(f"动压 Q 不能为负数，当前值: {q}")
        
        return cls(
            part_name=data["PartName"],
            coord_system=CoordSystemDefinition.from_dict(data["TargetCoordSystem"]),
            moment_center=data["TargetMomentCenter"],
            c_ref=c_ref,
            b_ref=b_ref,
            q=q,
            s_ref=s_ref
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
