"""
延迟任务调度器 - 集中管理 QTimer 延迟任务，避免重复/积压。

功能：
- 按 key 去重调度（replace=True 时覆盖旧任务）
- 统一管理延迟任务生命周期
- 提供 next-tick 调度接口
"""

import logging
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)


class DelayScheduler(QObject):
    """集中管理延迟任务的调度器（单例）。"""

    _instance = None

    def __init__(self):
        super().__init__()
        self._timers: Dict[str, QTimer] = {}

    @classmethod
    def instance(cls) -> "DelayScheduler":
        """获取单例实例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def schedule(
        self,
        key: str,
        delay_ms: int,
        callback: Callable[[], None],
        *,
        replace: bool = True,
    ) -> bool:
        """按 key 调度延迟任务。

        Args:
            key: 任务标识（用于去重与覆盖）
            delay_ms: 延迟毫秒数
            callback: 执行回调
            replace: 若已存在同 key 任务，是否覆盖

        Returns:
            是否成功调度
        """
        try:
            if not key or callback is None:
                return False
            if key in self._timers:
                if not replace:
                    return False
                try:
                    self._timers[key].stop()
                except Exception:
                    pass
                self._timers.pop(key, None)

            timer = QTimer(self)
            timer.setSingleShot(True)

            def _run():
                try:
                    self._timers.pop(key, None)
                except Exception:
                    pass
                try:
                    callback()
                except Exception:
                    logger.debug("延迟任务执行失败: %s", key, exc_info=True)

            timer.timeout.connect(_run)
            timer.start(int(delay_ms))
            self._timers[key] = timer
            return True
        except Exception:
            logger.debug("调度延迟任务失败: %s", key, exc_info=True)
            return False

    def schedule_next_tick(self, key: str, callback: Callable[[], None]) -> bool:
        """在事件循环下一次机会调度任务（delay=0）。"""
        return self.schedule(key, 0, callback, replace=True)

    def cancel(self, key: str) -> bool:
        """取消指定 key 的任务。"""
        try:
            timer = self._timers.pop(key, None)
            if timer is None:
                return False
            try:
                timer.stop()
            except Exception:
                pass
            return True
        except Exception:
            logger.debug("取消延迟任务失败: %s", key, exc_info=True)
            return False

    def cancel_all(self) -> None:
        """取消所有延迟任务。"""
        try:
            for key, timer in list(self._timers.items()):
                try:
                    timer.stop()
                except Exception:
                    pass
                self._timers.pop(key, None)
        except Exception:
            logger.debug("取消全部延迟任务失败", exc_info=True)
