# -*- coding: utf-8 -*-
"""
文件缓存模块
用于减少重复读取文件，提高性能并避免Win7下可能的I/O冲突
"""
import hashlib
import threading
from functools import lru_cache
from itertools import islice
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
        # 每个 cache_key 的细粒度锁，避免多个线程同时读取并缓存同一文件
        self._key_locks: Dict[str, threading.Lock] = {}

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
        except OSError:
            # 如果无法获取文件状态（权限/不存在等），使用路径作为键
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

        # 生成缓存键并先行检查缓存（快速路径）
        cache_key = self._get_file_key(file_path)
        with self._lock:
            cached = self._content_cache.get(cache_key)
            if cached is not None:
                return cached

            # 获取或创建细粒度锁，保证只有一个线程去读取并写入缓存
            key_lock = self._key_locks.get(cache_key)
            if key_lock is None:
                key_lock = threading.Lock()
                self._key_locks[cache_key] = key_lock

        # 在 key_lock 下执行实际 I/O（双重检查以防竞争）
        with key_lock:
            with self._lock:
                cached = self._content_cache.get(cache_key)
                if cached is not None:
                    return cached

            # 检查文件大小以决定是否缓存
            try:
                file_size = file_path.stat().st_size
            except OSError:
                return None

            # 超大文件：直接读取并不缓存
            if file_size > self.max_file_size:
                try:
                    with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                        return f.read()
                except (OSError, UnicodeDecodeError):
                    return None

            # 普通文件：读取并缓存
            try:
                with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                    content = f.read()

                with self._lock:
                    self._content_cache[cache_key] = content

                return content
            except (OSError, UnicodeDecodeError):
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

        # 读取文件头部（短文件也返回已有行，不把 StopIteration 视为错误）
        try:
            with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                lines = list(islice(f, num_lines))

            # 存入缓存
            with self._lock:
                self._metadata_cache[cache_key] = {"header": lines}

            return lines
        except (OSError, UnicodeDecodeError):
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
            self._key_locks.clear()

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
                k for k in list(self._metadata_cache) if k.startswith(cache_key)
            ]
            for k in keys_to_remove:
                self._metadata_cache.pop(k, None)
            # 清除对应的细粒度锁（如存在）
            self._key_locks.pop(cache_key, None)

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


# 使用管理器单例，避免模块级 global
class FileCacheManager:
    """管理 `FileCache` 实例的单例管理器。"""

    def __init__(self) -> None:
        self._file_cache: Optional[FileCache] = None

    def get_file_cache(self) -> FileCache:
        """返回或创建 `FileCache` 单例实例。"""
        if self._file_cache is None:
            self._file_cache = FileCache()
        return self._file_cache

    def clear(self) -> None:
        """清空已创建的 `FileCache` 缓存（如果存在）。"""
        if self._file_cache is not None:
            self._file_cache.clear()


_FILE_CACHE_MANAGER = FileCacheManager()


def get_file_cache() -> FileCache:
    """获取文件缓存实例（代理到 `_FILE_CACHE_MANAGER`）。"""
    return _FILE_CACHE_MANAGER.get_file_cache()


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
    except OSError:
        return None
