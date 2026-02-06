"""
数据验证系统 - 增强输入验证安全性

包括：
1. 数据类型验证
2. 数值范围验证
3. CSV 安全检查
4. 文件路径验证
"""

import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    """数据验证错误"""


class DataValidator:
    """数据验证器 - 验证各类输入数据"""

    @staticmethod
    def validate_coordinate(
        coord: Any, name: str = "coordinate"
    ) -> Tuple[float, float, float]:
        """
        验证坐标（列表或数组）

        参数：
            coord: 3D 坐标
            name: 坐标名称（用于错误消息）

        返回：
            验证后的 (x, y, z) 元组
        """
        try:
            if isinstance(coord, (list, tuple)):
                if len(coord) != 3:
                    raise ValidationError(f"{name} 必须有 3 个元素，得到 {len(coord)}")
                coord_array = np.array(coord, dtype=float)
            elif isinstance(coord, np.ndarray):
                if coord.shape != (3,):
                    raise ValidationError(f"{name} 形状必须为 (3,)，得到 {coord.shape}")
                coord_array = coord.astype(float)
            else:
                raise ValidationError(f"{name} 必须是列表、元组或 numpy 数组")

            # 检查是否包含 NaN 或 Inf
            if np.any(np.isnan(coord_array)) or np.any(np.isinf(coord_array)):
                raise ValidationError(f"{name} 包含 NaN 或 Inf 值")

            return tuple(coord_array)

        except (TypeError, ValueError) as e:
            raise ValidationError(f"坐标验证失败: {e}") from e

    @staticmethod
    def validate_numeric_range(
        value: Any,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        name: str = "value",
    ) -> float:
        """
        验证数值范围

        参数：
            value: 待验证的数值
            min_val: 最小值（None 表示无下限）
            max_val: 最大值（None 表示无上限）
            name: 值名称（用于错误消息）

        返回：
            验证后的浮点数
        """
        try:
            float_val = float(value)

            if np.isnan(float_val) or np.isinf(float_val):
                raise ValidationError(f"{name} 包含 NaN 或 Inf 值")

            if min_val is not None and float_val < min_val:
                raise ValidationError(f"{name} = {float_val} < 最小值 {min_val}")

            if max_val is not None and float_val > max_val:
                raise ValidationError(f"{name} = {float_val} > 最大值 {max_val}")

            return float_val

        except (TypeError, ValueError) as e:
            raise ValidationError(f"数值验证失败: {e}") from e

    @staticmethod
    def validate_file_path(
        filepath: str, must_exist: bool = True, writable: bool = False
    ) -> Path:
        """
        验证文件路径安全性

        参数：
            filepath: 文件路径
            must_exist: 文件是否必须存在
            writable: 文件是否必须可写

        返回：
            验证后的 Path 对象
        """
        try:
            raw_path = Path(filepath)
            normalized_path = Path(str(filepath).replace("\\", "/"))

            # 检查路径遍历攻击（在 resolve 前检测，兼容不同分隔符）
            if ".." in raw_path.parts or ".." in normalized_path.parts:
                raise ValidationError(
                    f"路径包含 '..'，可能存在目录遍历攻击: {filepath}"
                )

            path = raw_path.resolve()

            if must_exist and not path.exists():
                raise ValidationError(f"文件不存在: {filepath}")

            if writable:
                # 检查目录是否可写
                parent_dir = path.parent if path.is_file() else path
                if not os.access(parent_dir, os.W_OK):
                    raise ValidationError(f"目录不可写: {parent_dir}")

            return path

        except OSError as e:
            raise ValidationError(f"路径验证失败: {e}") from e

    @staticmethod
    def validate_csv_safety(
        filepath: str, max_size_mb: float = 1024, max_rows: int = 1000000
    ) -> Path:
        """
        验证 CSV 文件安全性

        参数：
            filepath: CSV 文件路径
            max_size_mb: 最大文件大小（MB）
            max_rows: 最大行数

        返回：
            验证后的 Path 对象
        """
        try:
            path = DataValidator.validate_file_path(filepath, must_exist=True)

            # 检查文件大小
            file_size_mb = path.stat().st_size / 1024 / 1024
            if file_size_mb > max_size_mb:
                raise ValidationError(
                    f"CSV 文件过大: {file_size_mb:.2f} MB > {max_size_mb} MB"
                )

            # 检查行数（通过采样）
            try:
                df = pd.read_csv(path, nrows=100)
                if len(df) >= 100:
                    # 读取几行来估计总行数
                    with open(path, encoding="utf-8") as _f:
                        total_lines = sum(1 for _ in _f)
                    if total_lines > max_rows:
                        raise ValidationError(
                            f"CSV 文件行数过多: {total_lines} > {max_rows}"
                        )
            except pd.errors.ParserError as e:
                raise ValidationError(f"CSV 格式无效: {e}") from e

            return path

        except OSError as e:
            raise ValidationError(f"CSV 安全检查失败: {e}") from e

    @staticmethod
    def validate_data_frame(
        df: pd.DataFrame,
        required_columns: Optional[List[str]] = None,
        max_rows: int = 1000000,
    ) -> pd.DataFrame:
        """
        验证 DataFrame 的完整性和安全性

        参数：
            df: 待验证的 DataFrame
            required_columns: 必需的列名列表
            max_rows: 最大行数

        返回：
            验证后的 DataFrame
        """
        try:
            if not isinstance(df, pd.DataFrame):
                raise ValidationError("输入不是 DataFrame")

            if len(df) > max_rows:
                raise ValidationError(f"DataFrame 行数过多: {len(df)} > {max_rows}")

            if required_columns:
                missing_cols = set(required_columns) - set(df.columns)
                if missing_cols:
                    raise ValidationError(f"缺少必需的列: {missing_cols}")

            # 检查是否存在无效的列名（例如含有特殊字符的列名）
            for col in df.columns:
                if not isinstance(col, (str, int, float)):
                    raise ValidationError(f"无效的列名类型: {type(col)}")

            return df

        except (TypeError, ValueError) as e:
            raise ValidationError(f"DataFrame 验证失败: {e}") from e

    @staticmethod
    def validate_column_mapping(mapping: dict, available_columns: List[str]) -> dict:
        """
        验证列映射配置

        参数：
            mapping: 列映射字典 (列名 -> 索引)
            available_columns: 可用的列列表

        返回：
            验证后的映射字典
        """
        try:
            if not isinstance(mapping, dict):
                raise ValidationError("映射必须是字典")

            validated_mapping = {}
            for key, value in mapping.items():
                if not isinstance(key, str):
                    raise ValidationError(f"映射键必须是字符串，得到: {type(key)}")

                if isinstance(value, str):
                    # 列名映射
                    if value not in available_columns:
                        raise ValidationError(f"列不存在: {value}")
                    validated_mapping[key] = value
                elif isinstance(value, int):
                    # 列索引映射
                    if value < 0 or value >= len(available_columns):
                        raise ValidationError(f"列索引超出范围: {value}")
                    validated_mapping[key] = value
                else:
                    raise ValidationError(f"映射值类型无效: {type(value)}")

            return validated_mapping

        except (TypeError, ValueError, IndexError) as e:
            raise ValidationError(f"列映射验证失败: {e}") from e


# 快速验证函数
def validate_coordinates(
    coords: List[List[float]],
) -> List[Tuple[float, float, float]]:
    """验证多个坐标"""
    return [DataValidator.validate_coordinate(coord) for coord in coords]


def validate_numeric(
    value: Any, min_val: float = -1e10, max_val: float = 1e10
) -> float:
    """快速验证数值"""
    return DataValidator.validate_numeric_range(value, min_val, max_val)
