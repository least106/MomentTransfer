"""数据加载与解析模块。

负责从 JSON 配置文件加载项目数据并将其转换为内部数据结构（`ProjectData`、
`FrameConfiguration`、`CoordSystemDefinition` 等）。

包含输入校验与向后兼容的适配逻辑。
"""

# 为了先消除行过长的 lint 噪音，暂时在文件级允许 `line-too-long`，后续可逐行重构。
# pylint: disable=line-too-long

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


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
                raise ValueError(
                    f"字段 {field_name} 必须是列表或元组，当前类型: {type(vec).__name__}"
                )
            if len(vec) != 3:
                raise ValueError(
                    f"字段 {field_name} 必须包含 3 个元素，当前长度: {len(vec)}"
                )
            try:
                [float(x) for x in vec]
            except (ValueError, TypeError) as e:
                raise ValueError(f"字段 {field_name} 的元素必须是数值类型: {e}") from e

        validate_vector(data["Orig"], "Orig")
        validate_vector(data["X"], "X")
        validate_vector(data["Y"], "Y")
        validate_vector(data["Z"], "Z")

        return cls(
            origin=data["Orig"],
            x_axis=data["X"],
            y_axis=data["Y"],
            z_axis=data["Z"],
        )


@dataclass
class FrameConfiguration:
    """
    通用坐标系配置类 (对等设计)
    Source 和 Target 都使用此结构
    """

    part_name: str  # 组件名称
    coord_system: CoordSystemDefinition  # 坐标系定义
    name: Optional[str] = None  # 参考系名称（新增）
    coord_system_ref: Optional[str] = None  # 坐标系引用（新增）
    moment_center: Optional[List[float]] = None  # 力矩参考中心 (可选)
    moment_center_in_part: Optional[List[float]] = None  # 力矩中心(部件坐标系，新增)
    moment_center_in_global: Optional[List[float]] = None  # 力矩中心(全局坐标系，新增)
    c_ref: Optional[float] = None  # 参考弦长 (可选)
    b_ref: Optional[float] = None  # 参考展长 (可选)
    q: Optional[float] = None  # 动压 (可选)
    s_ref: Optional[float] = None  # 参考面积 (可选)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], frame_type: str = "Frame", global_coord_systems: Dict[str, CoordSystemDefinition] = None):
        """
        从字典创建配置对象，支持新旧配置格式
        :param data: 配置字典
        :param frame_type: 标识符 (用于错误提示)
        :param global_coord_systems: 全局坐标系定义字典（用于解析引用）
        """
        if global_coord_systems is None:
            global_coord_systems = {}
        
        # 验证必须字段
        if "PartName" not in data:
            raise ValueError(f"{frame_type} 定义缺少必须字段: PartName")

        # 提取参考系名称（新增）
        name = data.get("Name", "")
        
        # 提取坐标系引用（新增）
        coord_system_ref = data.get("CoordSystemRef")
        
        # 解析坐标系：优先使用引用，否则从 CoordSystem 字段加载
        coord_system = None
        if coord_system_ref:
            if coord_system_ref not in global_coord_systems:
                raise ValueError(f"坐标系引用 '{coord_system_ref}' 未定义")
            # 创建深拷贝，避免多个 FrameConfiguration 共享同一对象
            import copy
            coord_system = copy.deepcopy(global_coord_systems[coord_system_ref])
        else:
            # 坐标系定义的键名兼容
            coord_key = None
            for possible_key in [
                "CoordSystem",
                "TargetCoordSystem",
                "SourceCoordSystem",
            ]:
                if possible_key in data:
                    coord_key = possible_key
                    break

            if coord_key is None:
                raise ValueError(f"{frame_type} 定义缺少坐标系字段 (CoordSystem)")
            
            coord_system = CoordSystemDefinition.from_dict(data[coord_key])

        # 处理力矩中心：支持新格式（双字段）和旧格式（单字段）
        mc_in_part = None
        mc_in_global = None
        moment_center = None
        
        # 新格式：双力矩中心
        if "MomentCenterInPartCoordSystem" in data:
            mc_in_part = data["MomentCenterInPartCoordSystem"]
            if not isinstance(mc_in_part, (list, tuple)) or len(mc_in_part) != 3:
                raise ValueError(f"MomentCenterInPartCoordSystem 必须是长度为 3 的列表")
        
        if "MomentCenterInGlobalCoordSystem" in data:
            mc_in_global = data["MomentCenterInGlobalCoordSystem"]
            if not isinstance(mc_in_global, (list, tuple)) or len(mc_in_global) != 3:
                raise ValueError(f"MomentCenterInGlobalCoordSystem 必须是长度为 3 的列表")
        
        # 旧格式：单一 MomentCenter
        if mc_in_part is None and mc_in_global is None:
            for mc_key in [
                "MomentCenter",
                "TargetMomentCenter",
                "SourceMomentCenter",
            ]:
                if mc_key in data:
                    moment_center = data[mc_key]
                    if not isinstance(moment_center, (list, tuple)) or len(moment_center) != 3:
                        raise ValueError(f"{mc_key} 必须是长度为 3 的列表")
                    # 向后兼容：如果使用引用，视为全局坐标；否则视为 Part 坐标
                    if coord_system_ref:
                        mc_in_global = moment_center
                    else:
                        mc_in_part = moment_center
                    break
        
        # 如果提供了双力矩中心，计算统一的 moment_center（全局坐标）
        # 并进行一致性验证
        if mc_in_part is not None or mc_in_global is not None:
            from src.moment_center_utils import (
                compute_missing_moment_center,
                validate_moment_center_consistency,
            )
            import numpy as np
            
            origin = np.array(coord_system.origin, dtype=float)
            x_vec = np.array(coord_system.x_axis, dtype=float)
            y_vec = np.array(coord_system.y_axis, dtype=float)
            z_vec = np.array(coord_system.z_axis, dtype=float)
            rotation_matrix = np.column_stack([x_vec, y_vec, z_vec])
            
            mc_part_arr = np.array(mc_in_part, dtype=float) if mc_in_part else None
            mc_global_arr = np.array(mc_in_global, dtype=float) if mc_in_global else None
            
            # 如果两个都提供，验证一致性
            if mc_part_arr is not None and mc_global_arr is not None:
                is_consistent, error = validate_moment_center_consistency(
                    mc_part_arr, mc_global_arr, origin, rotation_matrix, tolerance=1e-6
                )
                if not is_consistent:
                    import warnings
                    warnings.warn(
                        f"{frame_type} '{name}': 力矩中心定义不一致（误差: {error:.6e}），"
                        f"将使用 Part 坐标系定义"
                    )
            
            # 计算缺失的力矩中心
            if mc_part_arr is None or mc_global_arr is None:
                mc_part_arr, mc_global_arr = compute_missing_moment_center(
                    mc_part_arr, mc_global_arr, origin, rotation_matrix
                )
            
            # 统一使用全局坐标
            moment_center = mc_global_arr.tolist()
            if mc_in_part is None:
                mc_in_part = mc_part_arr.tolist()
            if mc_in_global is None:
                mc_in_global = mc_global_arr.tolist()

        # 获取数值参数 (都是可选的) - 支持多种字段名以保证兼容性
        c_ref = data.get("Cref") or data.get("C_ref")
        b_ref = data.get("Bref") or data.get("B_ref")
        q = data.get("Q")
        # S/S_ref/Sref 都支持
        s_ref = data.get("S") or data.get("Sref") or data.get("S_ref")

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
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"字段 {name} 的值必须是数值类型，当前值: {val} (type={type(val).__name__})"
                ) from exc
            if strictly_positive:
                if f <= 0:
                    raise ValueError(f"字段 {name} 必须为严格正数 (>0)，当前值: {val}")
            else:
                if f < 0:
                    raise ValueError(f"字段 {name} 必须为非负数 (>=0)，当前值: {val}")
            return f

        c_ref = (
            parse_numeric_value("Cref", c_ref, strictly_positive=True)
            if c_ref is not None
            else None
        )
        b_ref = (
            parse_numeric_value("Bref", b_ref, strictly_positive=True)
            if b_ref is not None
            else None
        )
        s_ref = parse_numeric_value("S", s_ref, strictly_positive=True)
        q = parse_numeric_value("Q", q, strictly_positive=False)

        # 强制要求 Q 与 S
        if q is None:
            raise ValueError(f"{frame_type} 定义必须包含动压 Q（数值）")
        if s_ref is None:
            raise ValueError(f"{frame_type} 定义必须包含参考面积 S（数值）")

        # 若 Cref 或 Bref 缺失，使用默认值 1.0 并不报错（但建议在配置中显式提供）
        if c_ref is None:
            c_ref = 1.0
        if b_ref is None:
            b_ref = 1.0

        return cls(
            part_name=data["PartName"],
            coord_system=coord_system,
            name=name,
            coord_system_ref=coord_system_ref,
            moment_center=moment_center,
            moment_center_in_part=mc_in_part,
            moment_center_in_global=mc_in_global,
            c_ref=c_ref,
            b_ref=b_ref,
            q=q,
            s_ref=s_ref,
        )


@dataclass
class TargetDefinition(FrameConfiguration):
    """
    Target 定义 (继承自 FrameConfiguration)
    为了向后兼容保留此类
    """


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
    def _parse_parts_section(
        cls, section: Any, section_name: str, global_coord_systems: Dict[str, CoordSystemDefinition] = None
    ) -> Dict[str, List[FrameConfiguration]]:
        """解析 Source/Target 部分，支持新格式（含 Parts 列表）和旧格式（单个对象）。"""
        if global_coord_systems is None:
            global_coord_systems = {}
        
        parts: Dict[str, List[FrameConfiguration]] = {}
        # 新格式：必须包含 Parts 列表（严格模式：不再支持旧的直接对象格式）
        if not (
            isinstance(section, dict)
            and "Parts" in section
            and isinstance(section["Parts"], list)
        ):
            raise ValueError(
                (
                    f"{section_name} 必须为对象且包含 'Parts' 列表。示例: "
                    "{'Parts':[{'PartName':'Name','Variants':[{'...'}]}]}"
                )
            )

        if isinstance(section["Parts"], list):
            for p in section["Parts"]:
                if not isinstance(p, dict):
                    raise ValueError(f"{section_name}.Parts 中的元素必须为对象")
                part_name = p.get("PartName") or "Unnamed"
                # 支持新格式（ReferenceSystem）和旧格式（Variants）
                variants_raw = p.get("ReferenceSystem") or p.get("Variants")
                variants: List[FrameConfiguration] = []
                if (
                    variants_raw is None
                    or not isinstance(variants_raw, list)
                    or len(variants_raw) == 0
                ):
                    raise ValueError(
                        f"{section_name} Part '{part_name}' 必须包含非空的 'ReferenceSystem' 或 'Variants' 列表"
                    )

                for v in variants_raw:
                    if not isinstance(v, dict):
                        raise ValueError(
                            f"{section_name} Part {part_name} 的 variant 必须为对象"
                        )
                    # 确保每个 variant 有 PartName 字段以便 from_dict 验证；若无则注入 parent 名称
                    v_copy = dict(v)
                    if "PartName" not in v_copy:
                        v_copy["PartName"] = part_name
                    # FrameConfiguration.from_dict 已会对 CoordSystem 和必需字段进行校验
                    variants.append(
                        FrameConfiguration.from_dict(
                            v_copy, 
                            frame_type=f"{section_name}.{part_name}",
                            global_coord_systems=global_coord_systems
                        )
                    )

                parts[part_name] = variants

            return parts

        # 解析完成后返回
        return parts

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """
        从字典创建项目数据，兼容旧版格式与新格式（Parts 列表 + ReferenceSystem + 坐标系引用）。
        """
        if "Source" not in data:
            raise ValueError("配置文件缺少 Source 定义")
        if "Target" not in data:
            raise ValueError("配置文件缺少 Target 定义")

        # 加载全局坐标系定义（新增）
        global_coord_systems: Dict[str, CoordSystemDefinition] = {}
        if "Global" in data and isinstance(data["Global"], dict):
            global_def = data["Global"]
            if "CoordSystem" in global_def:
                try:
                    global_coord_systems["Global"] = CoordSystemDefinition.from_dict(
                        global_def["CoordSystem"]
                    )
                except Exception as e:
                    import warnings
                    warnings.warn(f"加载全局坐标系失败: {e}")

        source_parts = cls._parse_parts_section(data["Source"], "Source", global_coord_systems)
        target_parts = cls._parse_parts_section(data["Target"], "Target", global_coord_systems)

        # 对 target_parts 做额外的严格校验，确保每个 variant 包含必需字段并给出清晰错误提示
        for part_name, variants in target_parts.items():
            if not variants:
                raise ValueError(f"Target 部件 '{part_name}' 必须包含至少一个 Variant")
            for idx, var in enumerate(variants):
                if (
                    var.moment_center is None
                    or not isinstance(var.moment_center, (list, tuple))
                    or len(var.moment_center) != 3
                ):
                    raise ValueError(
                        f"Target Part '{part_name}' Variant[{idx}] 缺少有效的 MomentCenter（长度为3的列表）"
                    )
                if var.q is None:
                    raise ValueError(
                        f"Target Part '{part_name}' Variant[{idx}] 缺少动压 Q（数值）"
                    )
                if var.s_ref is None:
                    raise ValueError(
                        f"Target Part '{part_name}' Variant[{idx}] 缺少参考面积 S（数值）"
                    )

        return cls(source_parts=source_parts, target_parts=target_parts)

    # 兼容性访问器：返回第一个 Part 的第一个 Variant，保持与旧 API 的语义
    @property
    def source_config(self) -> FrameConfiguration:
        """返回向后兼容的默认 source 配置（第一个 Part 的第一个 Variant）。"""
        first_part = next(iter(self.source_parts.values()), None)
        if not first_part:
            raise ValueError("source_parts 为空")
        return first_part[0]

    @property
    def target_config(self) -> FrameConfiguration:
        """返回向后兼容的默认 target 配置（第一个 Part 的第一个 Variant）。"""
        first_part = next(iter(self.target_parts.values()), None)
        if not first_part:
            raise ValueError("target_parts 为空")
        return first_part[0]

    @property
    def source_coord(self):
        """向后兼容属性，返回默认 source 的坐标系定义"""
        return self.source_config.coord_system

    # 便捷访问器
    def get_source_part(
        self, part_name: str, variant_index: int = 0
    ) -> FrameConfiguration:
        """按名称和变体索引返回 source 部件的 `FrameConfiguration`。"""
        parts = self.source_parts.get(part_name)
        if not parts:
            raise KeyError(f"找不到 Source part: {part_name}")
        try:
            return parts[variant_index]
        except IndexError as exc:
            raise IndexError(
                f"Part {part_name} 没有索引 {variant_index} 的 variant"
            ) from exc

    def get_target_part(
        self, part_name: str, variant_index: int = 0
    ) -> FrameConfiguration:
        """按名称和变体索引返回 target 部件的 `FrameConfiguration`。"""
        parts = self.target_parts.get(part_name)
        if not parts:
            raise KeyError(f"找不到 Target part: {part_name}")
        try:
            return parts[variant_index]
        except IndexError as exc:
            raise IndexError(
                f"Part {part_name} 没有索引 {variant_index} 的 variant"
            ) from exc


def load_data(file_path: str) -> ProjectData:
    """
    读取 JSON 文件并转换为 Python 对象
    :param file_path: 配置文件路径
    :return: ProjectData 对象
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        return ProjectData.from_dict(raw_data)

    except FileNotFoundError as exc:
        raise FileNotFoundError(f"错误: 找不到文件 {file_path}，请检查路径。") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"错误: 文件 {file_path} 不是有效的 JSON 格式。") from exc
    except KeyError as e:
        raise KeyError(f"错误: JSON 数据缺少关键字段 {e}，请检查输入文件结构。") from e


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
            "message": str(e),
            "suggestion": "检查路径或使用 creator.py 生成 data/input.json。",
        }
        if strict:
            return False, None, info
        raise
    except json.JSONDecodeError as e:
        info = {
            "message": f"配置文件不是有效的 JSON: {e}",
            "suggestion": "请使用 JSON 校验工具检查语法或修复格式错误。",
        }
        if strict:
            return False, None, info
        raise
    except (ValueError, KeyError) as e:
        # 语义/缺失字段类错误，提供修复建议
        msg = str(e)
        suggestion = (
            "检查配置是否包含 Source/Target、Target.MomentCenter、"
            "Target.Q、Target.S 等必需字段，或使用 creator.py 生成兼容配置。"
        )
        if strict:
            return False, None, {"message": msg, "suggestion": suggestion}
        raise
    except Exception as e:
        # 未知错误：返回通用建议
        if strict:
            return (
                False,
                None,
                {
                    "message": str(e),
                    "suggestion": "查看完整异常并检查文件权限/编码。",
                },
            )
        raise
