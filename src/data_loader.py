import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

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
        
        for field in required_fields:
            if field not in data:
                raise ValueError(f"坐标系定义缺少必须字段: {field}")
        
        def validate_vector(vec, field_name):
            if not isinstance(vec, (list, tuple)):
                raise ValueError(f"字段 {field_name} 必须是列表或元组，当前类型: {type(vec).__name__}")
            if len(vec) != 3:
                raise ValueError(f"字段 {field_name} 必须包含 3 个元素，当前长度: {len(vec)}")
            try:
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
class FrameConfiguration:
    """
    通用坐标系配置类 (对等设计)
    Source 和 Target 都使用此结构
    """
    part_name: str                              # 组件名称
    coord_system: CoordSystemDefinition         # 坐标系定义
    moment_center: Optional[List[float]] = None # 力矩参考中心 (可选)
    c_ref: Optional[float] = None               # 参考弦长 (可选)
    b_ref: Optional[float] = None               # 参考展长 (可选)
    q: Optional[float] = None                   # 动压 (可选)
    s_ref: Optional[float] = None               # 参考面积 (可选)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], frame_type: str = "Frame"):
        """
        从字典创建配置对象
        :param data: 配置字典
        :param frame_type: 标识符 (用于错误提示)
        """
        # 验证必须字段
        if "PartName" not in data:
            raise ValueError(f"{frame_type} 定义缺少必须字段: PartName")
        
        # 坐标系定义的键名兼容
        coord_key = None
        for possible_key in ["CoordSystem", "TargetCoordSystem", "SourceCoordSystem"]:
            if possible_key in data:
                coord_key = possible_key
                break
        
        if coord_key is None:
            raise ValueError(f"{frame_type} 定义缺少坐标系字段 (CoordSystem)")
        
        # 力矩中心 (可选字段)
        moment_center = None
        for mc_key in ["MomentCenter", "TargetMomentCenter", "SourceMomentCenter"]:
            if mc_key in data:
                moment_center = data[mc_key]
                if not isinstance(moment_center, (list, tuple)) or len(moment_center) != 3:
                    raise ValueError(f"{mc_key} 必须是长度为 3 的列表")
                break
        
        # 获取数值参数 (都是可选的)
        c_ref = data.get("Cref")
        b_ref = data.get("Bref")
        q = data.get("Q")
        s_ref = data.get("S")
        
        # 如果提供了这些参数，进行验证
        def parse_positive_number(name: str, val, strictly_positive: bool = True):
            """
            尝试将 val 转为 float 并进行正数/非负校验。
            返回转换后的 float，失败时抛出 ValueError，错误消息为通用格式。
            """
            if val is None:
                return None
            try:
                f = float(val)
            except (ValueError, TypeError):
                raise ValueError(f"字段 {name} 的值必须是数值类型，当前值: {val} (type={type(val).__name__})")
            if strictly_positive:
                if f <= 0:
                    raise ValueError(f"字段 {name} 必须为正数 (>0)，当前值: {val}")
            else:
                if f < 0:
                    raise ValueError(f"字段 {name} 不能为负数，当前值: {val}")
            return f

        c_ref = parse_positive_number("Cref", c_ref, strictly_positive=True)
        b_ref = parse_positive_number("Bref", b_ref, strictly_positive=True)
        s_ref = parse_positive_number("S", s_ref, strictly_positive=True)
        q = parse_positive_number("Q", q, strictly_positive=False)
        
        return cls(
            part_name=data["PartName"],
            coord_system=CoordSystemDefinition.from_dict(data[coord_key]),
            moment_center=moment_center,
                c_ref=c_ref,
                b_ref=b_ref,
                q=q,
                s_ref=s_ref
        )


@dataclass
class TargetDefinition(FrameConfiguration):
    """
    Target 定义 (继承自 FrameConfiguration)
    为了向后兼容保留此类
    """
    pass


@dataclass
class ProjectData:
    """
    顶级数据类 - 对等的 Source 和 Target
    """
    source_config: FrameConfiguration  # Source 配置
    target_config: FrameConfiguration  # Target 配置

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """
        从字典创建项目数据
        兼容旧版格式和新版格式
        """
        # 解析 Source
        if "Source" in data:
            # 新格式: Source 是完整配置
            source_config = FrameConfiguration.from_dict(data["Source"], "Source")
        elif "SourceCoordSystem" in data:
            # 旧格式: 仅有坐标系定义
            source_config = FrameConfiguration(
                part_name="Global",
                coord_system=CoordSystemDefinition.from_dict(data["SourceCoordSystem"])
            )
        else:
            raise ValueError("配置文件缺少 Source 或 SourceCoordSystem 定义。有效的顶层字段为 'Source'（完整配置）或 'SourceCoordSystem'（仅坐标系定义，向后兼容）。")
        
        # 解析 Target
        if "Target" not in data:
            raise ValueError("配置文件缺少 Target 定义")
        
        target_config = FrameConfiguration.from_dict(data["Target"], "Target")
        
        # 验证 Target 必须有力矩中心和参考量
        if target_config.moment_center is None:
            raise ValueError("Target 必须定义 MomentCenter")
        if target_config.q is None:
            raise ValueError("Target 必须定义动压 Q")
        if target_config.s_ref is None:
            raise ValueError("Target 必须定义参考面积 S")
        if target_config.c_ref is None:
            target_config.c_ref = 1.0  # 默认值
        if target_config.b_ref is None:
            target_config.b_ref = 1.0  # 默认值
        
        return cls(
            source_config=source_config,
            target_config=target_config
        )

    @property
    def source_coord(self):
        """向后兼容属性"""
        return self.source_config.coord_system


def load_data(file_path: str) -> ProjectData:
    """
    读取 JSON 文件并转换为 Python 对象
    :param file_path: 配置文件路径
    :return: ProjectData 对象
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        return ProjectData.from_dict(raw_data)
        
    except FileNotFoundError:
        raise FileNotFoundError(f"错误: 找不到文件 {file_path}，请检查路径。")
    except json.JSONDecodeError:
        raise ValueError(f"错误: 文件 {file_path} 不是有效的 JSON 格式。")
    except KeyError as e:
        raise KeyError(f"错误: JSON 数据缺少关键字段 {e}，请检查输入文件结构。")


def try_load_project_data(file_path: str, *, strict: bool = True):
    """
    尝试加载并验证项目配置文件，返回结构化结果以便 CLI/GUI 决定回退策略。

    返回 (success: bool, project_data or None, info: dict or None)
    info 在失败时包含 'message' 与 'suggestion' 字段。
    如果 strict=True，则在遇到致命错误时也返回结构化信息（不抛出），调用方可选择抛出。
    """
    try:
        pd = load_data(file_path)
        return True, pd, None
    except FileNotFoundError as e:
        info = {
            'message': str(e),
            'suggestion': '检查路径或使用 creator.py 生成 data/input.json。'
        }
        return False, None, info
    except json.JSONDecodeError as e:
        info = {
            'message': f'配置文件不是有效的 JSON: {e}',
            'suggestion': '请使用 JSON 校验工具检查语法或修复格式错误。'
        }
        return False, None, info
    except (ValueError, KeyError) as e:
        # 语义/缺失字段类错误，提供修复建议
        msg = str(e)
        suggestion = '检查配置是否包含 Source/Target、Target.MomentCenter、Target.Q、Target.S 等必需字段，或使用 creator.py 生成兼容配置。'
        return False, None, {'message': msg, 'suggestion': suggestion}
    except Exception as e:
        # 未知错误：返回通用建议
        return False, None, {'message': str(e), 'suggestion': '查看完整异常并检查文件权限/编码。'}