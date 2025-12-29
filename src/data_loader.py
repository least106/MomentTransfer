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
        def parse_numeric_value(name: str, val, strictly_positive: bool = True):
            """
            尝试将 val 转为 float 并进行数值校验。

            - 当 `strictly_positive=True` 时，要求数值为严格正数 (>0)。
            - 当 `strictly_positive=False` 时，要求数值为非负 (>=0)。

            返回转换后的 float；当 val 为 None 时返回 None；校验失败时抛出 ValueError，错误消息为统一格式。
            """
            if val is None:
                return None
            try:
                f = float(val)
            except (ValueError, TypeError):
                raise ValueError(f"字段 {name} 的值必须是数值类型，当前值: {val} (type={type(val).__name__})")
            if strictly_positive:
                if f <= 0:
                    raise ValueError(f"字段 {name} 必须为严格正数 (>0)，当前值: {val}")
            else:
                if f < 0:
                    raise ValueError(f"字段 {name} 必须为非负数 (>=0)，当前值: {val}")
            return f

        c_ref = parse_numeric_value("Cref", c_ref, strictly_positive=True)
        b_ref = parse_numeric_value("Bref", b_ref, strictly_positive=True)
        s_ref = parse_numeric_value("S", s_ref, strictly_positive=True)
        q = parse_numeric_value("Q", q, strictly_positive=False)
        
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
    顶级数据类 - 支持多 Part / 多 Variant 的 Source/Target 表达
    - source_parts: Dict[part_name, List[FrameConfiguration]]
    - target_parts: Dict[part_name, List[FrameConfiguration]]

    为向后兼容，保留对单一 source_config/target_config 的访问器（返回第一个 part 的第一个 variant）。
    """
    source_parts: Dict[str, List[FrameConfiguration]]
    target_parts: Dict[str, List[FrameConfiguration]]

    @classmethod
    def _parse_parts_section(cls, section: Any, section_name: str) -> Dict[str, List[FrameConfiguration]]:
        """解析 Source/Target 部分，支持新格式（含 Parts 列表）和旧格式（单个对象）。"""
        parts: Dict[str, List[FrameConfiguration]] = {}

        # 新格式：包含 Parts 列表
        if isinstance(section, dict) and 'Parts' in section and isinstance(section['Parts'], list):
            for p in section['Parts']:
                if not isinstance(p, dict):
                    raise ValueError(f"{section_name}.Parts 中的元素必须为对象")
                part_name = p.get('PartName') or 'Unnamed'
                variants_raw = p.get('Variants')
                variants: List[FrameConfiguration] = []
                if variants_raw is None:
                    # 允许单个变体直接放在 part 对象中（向后兼容）
                    if any(k in p for k in ('CoordSystem', 'SourceCoordSystem', 'TargetCoordSystem')):
                        variants_raw = [p]
                    else:
                        variants_raw = []

                for v in variants_raw:
                    if not isinstance(v, dict):
                        raise ValueError(f"{section_name} Part {part_name} 的 variant 必须为对象")
                    # 确保每个 variant 有 PartName 字段以便 from_dict 验证；若无则注入 parent 名称
                    v_copy = dict(v)
                    if 'PartName' not in v_copy:
                        v_copy['PartName'] = part_name
                    variants.append(FrameConfiguration.from_dict(v_copy, frame_type=f"{section_name}.{part_name}"))

                parts[part_name] = variants

            return parts

        # 旧格式：直接给出单个对象（可能包含 CoordSystem 等字段）
        if isinstance(section, dict):
            # 如果该对象直接是一个完整的 FrameConfiguration（含 CoordSystem），则把它封装进默认 part 名称
            src_obj = dict(section)
            part_name = src_obj.get('PartName') or (section_name + '_Default')
            # 确保 PartName 存在以兼容 FrameConfiguration.from_dict
            if 'PartName' not in src_obj:
                src_obj['PartName'] = part_name
            parts[part_name] = [FrameConfiguration.from_dict(src_obj, frame_type=section_name)]
            return parts

        raise ValueError(f"{section_name} 部分结构不受支持：期望对象或包含 Parts 列表的对象。")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """
        从字典创建项目数据，兼容旧版格式与新格式（Parts 列表）。
        """
        if 'Source' not in data:
            raise ValueError("配置文件缺少 Source 定义")
        if 'Target' not in data:
            raise ValueError("配置文件缺少 Target 定义")

        source_parts = cls._parse_parts_section(data['Source'], 'Source')
        target_parts = cls._parse_parts_section(data['Target'], 'Target')

        # 对于 target，进行基础校验：每个 variant 应包含必需的数值字段（在 FrameConfiguration.from_dict 中已校验部分字段）
        # 对于兼容性，若某些可选字段未给出，FrameConfiguration.from_dict 已会返回 None 或默认值处理

        return cls(source_parts=source_parts, target_parts=target_parts)

    # 兼容性访问器：返回第一个 Part 的第一个 Variant，保持与旧 API 的语义
    @property
    def source_config(self) -> FrameConfiguration:
        # 取第一个 part 的第一个 variant
        first_part = next(iter(self.source_parts.values()), None)
        if not first_part:
            raise ValueError('source_parts 为空')
        return first_part[0]

    @property
    def target_config(self) -> FrameConfiguration:
        first_part = next(iter(self.target_parts.values()), None)
        if not first_part:
            raise ValueError('target_parts 为空')
        return first_part[0]

    @property
    def source_coord(self):
        """向后兼容属性，返回默认 source 的坐标系定义"""
        return self.source_config.coord_system

    # 便捷访问器
    def get_source_part(self, part_name: str, variant_index: int = 0) -> FrameConfiguration:
        parts = self.source_parts.get(part_name)
        if not parts:
            raise KeyError(f"找不到 Source part: {part_name}")
        try:
            return parts[variant_index]
        except IndexError:
            raise IndexError(f"Part {part_name} 没有索引 {variant_index} 的 variant")

    def get_target_part(self, part_name: str, variant_index: int = 0) -> FrameConfiguration:
        parts = self.target_parts.get(part_name)
        if not parts:
            raise KeyError(f"找不到 Target part: {part_name}")
        try:
            return parts[variant_index]
        except IndexError:
            raise IndexError(f"Part {part_name} 没有索引 {variant_index} 的 variant")


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
        if strict:
            return False, None, info
        raise
    except json.JSONDecodeError as e:
        info = {
            'message': f'配置文件不是有效的 JSON: {e}',
            'suggestion': '请使用 JSON 校验工具检查语法或修复格式错误。'
        }
        if strict:
            return False, None, info
        raise
    except (ValueError, KeyError) as e:
        # 语义/缺失字段类错误，提供修复建议
        msg = str(e)
        suggestion = '检查配置是否包含 Source/Target、Target.MomentCenter、Target.Q、Target.S 等必需字段，或使用 creator.py 生成兼容配置。'
        if strict:
            return False, None, {'message': msg, 'suggestion': suggestion}
        raise
    except Exception as e:
        # 未知错误：返回通用建议
        if strict:
            return False, None, {'message': str(e), 'suggestion': '查看完整异常并检查文件权限/编码。'}
        raise