"""
缓存系统 - 使用 LRU 缓存避免重复计算

用于缓存：
1. 旋转矩阵计算（高计算成本）
2. 坐标系转换（重复使用相同配置）
3. 力臂计算结果
"""

import logging
from functools import lru_cache
from typing import Tuple, Optional
import numpy as np
from collections import OrderedDict

logger = logging.getLogger(__name__)


class CacheKey:
    """缓存键生成器 - 用于将 numpy 数组转换为可哈希的键"""

    @staticmethod
    def array_to_tuple(arr: np.ndarray, precision_digits: int = 10) -> Tuple:
        """将 numpy 数组转换为元组（用于哈希）"""
        if arr is None:
            return None
        # 四舍五入到指定精度以处理浮点数精度问题
        rounded = np.around(arr, decimals=precision_digits)
        return tuple(rounded.flatten().tolist())

    @staticmethod
    def basis_matrix_key(basis: np.ndarray, precision_digits: int = 10) -> Tuple:
        """为基向量矩阵生成缓存键"""
        return CacheKey.array_to_tuple(basis, precision_digits)

    @staticmethod
    def vector_key(vector: np.ndarray, precision_digits: int = 10) -> Tuple:
        """为向量生成缓存键"""
        return CacheKey.array_to_tuple(vector, precision_digits)


class CalculationCache:
    """通用计算缓存类 - 基于 LRU 缓存"""

    def __init__(self, max_entries: int = 1000):
        """
        初始化缓存
        
        参数：
            max_entries: 最大缓存条目数
        """
        self.max_entries = max_entries
        self.cache: OrderedDict = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: Tuple) -> Optional[object]:
        """获取缓存值"""
        if key in self.cache:
            # 移到末尾（LRU）
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    def set(self, key: Tuple, value: object) -> None:
        """设置缓存值"""
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            self.cache[key] = value
            # 超过限制时删除最旧的条目
            if len(self.cache) > self.max_entries:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
            else:
                self.cache[key] = value

    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def stats(self) -> dict:
        """获取缓存统计信息"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            'hits': self.hits,
            'misses': self.misses,
            'total': total,
            'hit_rate': f'{hit_rate:.1f}%',
            'entries': len(self.cache),
            'max_entries': self.max_entries,
        }


class RotationMatrixCache(CalculationCache):
    """旋转矩阵专用缓存"""

    def get_rotation_matrix(
        self,
        basis_source: np.ndarray,
        basis_target: np.ndarray,
        precision_digits: int = 10,
    ) -> Optional[np.ndarray]:
        """获取缓存的旋转矩阵"""
        key = (
            CacheKey.basis_matrix_key(basis_source, precision_digits),
            CacheKey.basis_matrix_key(basis_target, precision_digits),
        )
        return self.get(key)

    def set_rotation_matrix(
        self,
        basis_source: np.ndarray,
        basis_target: np.ndarray,
        rotation_matrix: np.ndarray,
        precision_digits: int = 10,
    ) -> None:
        """设置旋转矩阵缓存"""
        key = (
            CacheKey.basis_matrix_key(basis_source, precision_digits),
            CacheKey.basis_matrix_key(basis_target, precision_digits),
        )
        self.set(key, rotation_matrix)


class TransformationCache(CalculationCache):
    """坐标系转换结果缓存"""

    def get_transformation(
        self,
        basis_target: np.ndarray,
        vector: np.ndarray,
        precision_digits: int = 10,
    ) -> Optional[np.ndarray]:
        """获取缓存的转换结果"""
        key = (
            CacheKey.basis_matrix_key(basis_target, precision_digits),
            CacheKey.vector_key(vector, precision_digits),
        )
        return self.get(key)

    def set_transformation(
        self,
        basis_target: np.ndarray,
        vector: np.ndarray,
        result: np.ndarray,
        precision_digits: int = 10,
    ) -> None:
        """设置转换结果缓存"""
        key = (
            CacheKey.basis_matrix_key(basis_target, precision_digits),
            CacheKey.vector_key(vector, precision_digits),
        )
        self.set(key, result)


# 全局缓存实例
_rotation_cache: Optional[RotationMatrixCache] = None
_transformation_cache: Optional[TransformationCache] = None


def get_rotation_cache(max_entries: int = 1000) -> RotationMatrixCache:
    """获取全局旋转矩阵缓存实例"""
    global _rotation_cache
    if _rotation_cache is None:
        _rotation_cache = RotationMatrixCache(max_entries)
    return _rotation_cache


def get_transformation_cache(max_entries: int = 1000) -> TransformationCache:
    """获取全局坐标转换缓存实例"""
    global _transformation_cache
    if _transformation_cache is None:
        _transformation_cache = TransformationCache(max_entries)
    return _transformation_cache


def clear_all_caches() -> None:
    """清空所有缓存"""
    global _rotation_cache, _transformation_cache
    if _rotation_cache:
        _rotation_cache.clear()
    if _transformation_cache:
        _transformation_cache.clear()
    logger.info("所有缓存已清空")
