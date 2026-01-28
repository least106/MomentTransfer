from __future__ import annotations

from PySide6.QtCore import QObject, Signal
import traceback


class BackgroundWorker(QObject):
    """通用后台 Worker：在 QThread 中运行一个可调用，并通过信号返回结果/错误/进度。

    用法：在主线程中创建 BackgroundWorker(callable, args, kwargs)，将其移动到 QThread，启动线程。
    """

    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args or ()
        self._kwargs = kwargs or {}

    def run(self):
        try:
            # func 可能会调用进度回调（通过传入 progress 参数），但我们不强制要求
            result = self._func(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as e:  # pylint: disable=broad-except
            tb = traceback.format_exc()
            self.error.emit(str(tb))
