# -*- coding: utf-8 -*-
"""
文件缓存模块
用于减少重复读取文件，提高性能并避免Win7下可能的I/O冲突
"""
import hashlib
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


class FileCache:
    """
    文件缓存管理器
    提供文件内容和元数据的缓存功能
    """

    def __init__(self, max_file_size_mb: float = 10):
        """
        初始化文件缓存

        Args:
            max_file_size_mb: 缓存文件的最大大小（MB），超过此大小的文件不缓存
        """
        self.max_file_size = max_file_size_mb * 1024 * 1024  # 转换为字节
        self._content_cache: Dict[str, str] = {}  # 文件内容缓存
        self._metadata_cache: Dict[str, Dict[str, Any]] = {}  # 元数据缓存
        self._lock = threading.Lock()

    def _get_file_key(self, file_path: Path) -> str:
        """
        生成文件的缓存键（基于路径和修改时间）

        Args:
            file_path: 文件路径

        Returns:
            缓存键字符串
        """
        try:
            stat = file_path.stat()
            # 使用路径+修改时间+文件大小作为键
            key_str = f"{file_path}_{stat.st_mtime}_{stat.st_size}"
            return hashlib.md5(key_str.encode()).hexdigest()
        except Exception:
            # 如果无法获取文件状态，使用路径作为键
            return hashlib.md5(str(file_path).encode()).hexdigest()

    def get_file_content(
        self, file_path: Path, encoding: str = "utf-8-sig"
    ) -> Optional[str]:
        """
        获取文件内容（优先从缓存）

        Args:
            file_path: 文件路径
            encoding: 文件编码

        Returns:
            文件内容字符串，失败返回None
        """
        if not file_path.exists():
            return None

        # 检查文件大小是否超过限制
        try:
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                # 超过大小限制，直接读取不缓存
                with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                    return f.read()
        except Exception:
            return None

        # 生成缓存键
        cache_key = self._get_file_key(file_path)

        # 检查缓存
        with self._lock:
            if cache_key in self._content_cache:
                return self._content_cache[cache_key]

        # 读取文件
        try:
            with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                content = f.read()

            # 存入缓存
            with self._lock:
                self._content_cache[cache_key] = content

            return content
        except Exception:
            return None

    def get_file_header(
        self, file_path: Path, num_lines: int = 10, encoding: str = "utf-8-sig"
    ) -> Optional[List[str]]:
        """
        获取文件头部若干行（用于格式检测）

        Args:
            file_path: 文件路径
            num_lines: 读取的行数
            encoding: 文件编码

        Returns:
            文件头部行列表，失败返回None
        """
        if not file_path.exists():
            return None

        # 生成缓存键（包含行数）
        cache_key = f"{self._get_file_key(file_path)}_header_{num_lines}"

        # 检查元数据缓存
        with self._lock:
            if cache_key in self._metadata_cache:
                return self._metadata_cache[cache_key].get("header")

        # 读取文件头部
        try:
            with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                lines = [next(f) for _ in range(num_lines) if f]

            # 存入缓存
            with self._lock:
                self._metadata_cache[cache_key] = {"header": lines}

            return lines
        except Exception:
            return None

    def set_metadata(self, file_path: Path, key: str, value: Any) -> None:
        """
        设置文件的元数据（如格式检测结果）

        Args:
            file_path: 文件路径
            key: 元数据键名
            value: 元数据值
        """
        cache_key = self._get_file_key(file_path)

        with self._lock:
            if cache_key not in self._metadata_cache:
                self._metadata_cache[cache_key] = {}
            self._metadata_cache[cache_key][key] = value

    def get_metadata(self, file_path: Path, key: str) -> Optional[Any]:
        """
        获取文件的元数据

        Args:
            file_path: 文件路径
            key: 元数据键名

        Returns:
            元数据值，不存在返回None
        """
        cache_key = self._get_file_key(file_path)

        with self._lock:
            if cache_key in self._metadata_cache:
                return self._metadata_cache[cache_key].get(key)

        return None

    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self._content_cache.clear()
            self._metadata_cache.clear()

    def clear_file(self, file_path: Path) -> None:
        """
        清除指定文件的缓存

        Args:
            file_path: 文件路径
        """
        cache_key = self._get_file_key(file_path)

        with self._lock:
            self._content_cache.pop(cache_key, None)
            # 清除所有相关的元数据缓存
            keys_to_remove = [
                k for k in self._metadata_cache.keys() if k.startswith(cache_key)
            ]
            for k in keys_to_remove:
                self._metadata_cache.pop(k, None)

    def get_cache_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息

        Returns:
            包含缓存统计的字典
        """
        with self._lock:
            return {
                "content_cached": len(self._content_cache),
                "metadata_cached": len(self._metadata_cache),
            }


# 全局缓存实例
_global_cache = None


def get_file_cache() -> FileCache:
    """获取全局文件缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = FileCache()
    return _global_cache


@lru_cache(maxsize=128)
def get_file_hash(file_path: str) -> Optional[str]:
    """
    计算文件的MD5哈希值（带LRU缓存）

    Args:
        file_path: 文件路径字符串

    Returns:
        MD5哈希值，失败返回None
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return None

        md5_hash = hashlib.md5()
        with open(path, "rb") as f:
            # 分块读取以处理大文件
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)

        return md5_hash.hexdigest()
    except Exception:
        return None
