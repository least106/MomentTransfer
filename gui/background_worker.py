from __future__ import annotations

"""后台任务支持：保留原有 `BackgroundWorker` 用于 QThread 场景，
并提供一个全局 `ThreadPoolManager`（基于 concurrent.futures.ThreadPoolExecutor）
以便在需要时以统一的池化线程方式提交短时或 I/O 密集型任务。

设计原则：
- 保持现有 `BackgroundWorker` 接口兼容
- 提供线程池单例 `get_thread_pool()`，公开 `submit(func, *args, **kwargs)`
  并通过 Qt 信号在主线程安全地通知结果
"""

import concurrent.futures
import logging
import threading
import time
import traceback
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class BackgroundWorker(QObject):
    """兼容旧式 QThread 使用的 Worker（保留）。"""

    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args or ()
        self._kwargs = kwargs or {}

    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception:  # pylint: disable=broad-except
            tb = traceback.format_exc()
            self.error.emit(str(tb))


class CancellationToken:
    """轻量级取消令牌，任务应合作检查 `is_cancelled()`。"""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class ThreadPoolManager(QObject):
    """扩展的全局线程池管理器：

    特性：
    - 支持按 `key` 的去重（同一 key 的重复提交会复用已有任务）
    - 支持基于 `CancellationToken` 的协作式取消
    - 支持重试策略（指数退避）
    - 通过 Qt 信号在主线程回传多个关联 task_id 的结果/错误
    """

    task_finished = Signal(object, object)  # task_id, result
    task_error = Signal(object, str)  # task_id, traceback_str

    def __init__(self, max_workers: int = 4):
        super().__init__()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers
        )
        self._lock = threading.Lock()
        self._next_task_id = 1
        # key -> { 'future': Future, 'task_ids': [id,...], 'token': CancellationToken }
        self._in_flight: Dict[str, Dict] = {}
        # task_id -> key
        self._task_map: Dict[int, str] = {}

    def submit(self,
               func: Callable,
               *args,
               key: Optional[str] = None,
               retries: int = 0,
               initial_backoff: float = 0.5,
               backoff_factor: float = 2.0,
               max_backoff: float = 8.0,
               **kwargs) -> tuple[concurrent.futures.Future, int]:
        """提交任务。

        参数:
            key: 可选，做为去重键（例如文件路径）。
            retries: 失败重试次数（不包含首次尝试）。
            initial_backoff/backoff_factor/max_backoff: 指数退避参数。

        返回 (future, task_id)。如果使用 `key` 且已有进行中任务，会复用该任务的 future，
        但仍分配新的 `task_id`，并在完成时为每个 task_id 发信号。
        """

        with self._lock:
            task_id = self._next_task_id
            self._next_task_id += 1

            if key is not None and key in self._in_flight:
                # 去重：复用已有 future
                entry = self._in_flight[key]
                entry['task_ids'].append(task_id)
                self._task_map[task_id] = key
                return entry['future'], task_id

            # 新任务：创建取消令牌并提交
            token = CancellationToken()

            def _runner():
                attempt = 0
                backoff = initial_backoff
                last_exc = None
                # 在每次尝试前检查取消
                while True:
                    if token.is_cancelled():
                        raise RuntimeError('cancelled')
                    try:
                        return func(*args, **kwargs)
                    except Exception as exc:  # pylint: disable=broad-except
                        last_exc = exc
                        if attempt >= retries:
                            # 最后一次失败，抛出
                            raise
                        # 等待退避，期间可被取消
                        slept = 0.0
                        while slept < backoff:
                            if token.is_cancelled():
                                raise RuntimeError('cancelled')
                            to_sleep = min(0.1, backoff - slept)
                            time.sleep(to_sleep)
                            slept += to_sleep
                        attempt += 1
                        backoff = min(max_backoff, backoff * backoff_factor)

            future = self._executor.submit(_runner)

            # 注册 in-flight
            if key is None:
                key = f"_anon_{task_id}"

            self._in_flight[key] = {
                'future': future,
                'task_ids': [task_id],
                'token': token,
            }
            self._task_map[task_id] = key

            def _on_done(fut: concurrent.futures.Future):
                # 从 in_flight 取出所有关联 task_id 并触发信号
                try:
                    res = fut.result()
                except Exception:  # pylint: disable=broad-except
                    tb = traceback.format_exc()
                    with self._lock:
                        entry = self._in_flight.pop(key, None)
                    if entry is None:
                        return
                    for tid in entry['task_ids']:
                        try:
                            self.task_error.emit(tid, tb)
                        except Exception:
                            logger.debug("无法发出 task_error 信号", exc_info=True)
                    # 清理 task_map
                    with self._lock:
                        for tid in entry['task_ids']:
                            self._task_map.pop(tid, None)
                    return

                # success
                with self._lock:
                    entry = self._in_flight.pop(key, None)
                if entry is None:
                    return
                for tid in entry['task_ids']:
                    try:
                        self.task_finished.emit(tid, res)
                    except Exception:
                        logger.debug("无法发出 task_finished 信号", exc_info=True)
                # 清理 task_map
                with self._lock:
                    for tid in entry['task_ids']:
                        self._task_map.pop(tid, None)

            future.add_done_callback(_on_done)
            return future, task_id

    def cancel_task(self, task_id: int) -> bool:
        """取消指定 task_id。返回 True 表示成功标记为取消（不保证已停止）。"""
        with self._lock:
            key = self._task_map.get(task_id)
            if not key:
                return False
            entry = self._in_flight.get(key)
            if not entry:
                return False
            # 从 task_ids 中移除该 id；如果没有剩余 id，则取消底层任务
            try:
                entry['task_ids'].remove(task_id)
            except ValueError:
                pass
            self._task_map.pop(task_id, None)
            if not entry['task_ids']:
                # 没有关联的任务，协作取消
                try:
                    entry['token'].cancel()
                except Exception:
                    logger.debug("取消 token 失败", exc_info=True)
            return True

    def cancel_key(self, key: str) -> bool:
        """按 key 取消正在进行的任务。"""
        with self._lock:
            entry = self._in_flight.get(key)
            if not entry:
                return False
            try:
                entry['token'].cancel()
            except Exception:
                logger.debug("取消 token 失败", exc_info=True)
            # 清理映射
            for tid in entry['task_ids']:
                self._task_map.pop(tid, None)
            self._in_flight.pop(key, None)
            return True

    def shutdown(self, wait: bool = True) -> None:
        try:
            # 先取消所有
            with self._lock:
                keys = list(self._in_flight.keys())
            for k in keys:
                try:
                    self.cancel_key(k)
                except Exception:
                    logger.debug("取消 key 失败: %s", k, exc_info=True)
            self._executor.shutdown(wait=wait)
        except Exception:
            logger.exception("线程池关闭时出错")


_GLOBAL_POOL: Optional[ThreadPoolManager] = None


def get_thread_pool(max_workers: int = 4) -> ThreadPoolManager:
    """返回全局线程池管理器单例。"""
    global _GLOBAL_POOL
    if _GLOBAL_POOL is None:
        _GLOBAL_POOL = ThreadPoolManager(max_workers=max_workers)
    return _GLOBAL_POOL

