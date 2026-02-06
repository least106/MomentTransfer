"""文件加载进度指示器模块

提供大文件加载时的进度提示，避免 UI 冻结感知。
"""

import logging
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QProgressDialog, QWidget

# 导入集中配置
from gui.progress_config import FILE_LOADING_SIZE_THRESHOLD_MB

logger = logging.getLogger(__name__)

# 向后兼容的别名
DEFAULT_SIZE_THRESHOLD_MB = FILE_LOADING_SIZE_THRESHOLD_MB


class FileLoadWorker(QObject):
    """后台文件加载工作线程

    在独立线程中执行文件加载操作，避免阻塞主线程。
    """

    # 加载完成信号：(成功标志, 结果数据或错误信息)
    finished = Signal(bool, object)
    # 进度信号：(当前值, 最大值, 状态文本)
    progress = Signal(int, int, str)

    def __init__(self, file_path: Path, load_func: Callable, **kwargs):
        """初始化文件加载工作线程

        Args:
            file_path: 要加载的文件路径
            load_func: 实际的加载函数，签名为 func(file_path, **kwargs) -> Any
            **kwargs: 传递给加载函数的额外参数
        """
        super().__init__()
        self.file_path = file_path
        self.load_func = load_func
        self.kwargs = kwargs
        self._stop_requested = False

    def run(self):
        """执行文件加载"""
        try:
            # 发送开始加载进度
            self.progress.emit(0, 0, f"正在读取文件: {self.file_path.name}")

            # 执行实际加载
            result = self.load_func(self.file_path, **self.kwargs)

            # 检查是否被取消
            if self._stop_requested:
                self.finished.emit(False, "用户取消加载")
                return

            # 发送完成进度
            self.progress.emit(1, 1, "加载完成")
            self.finished.emit(True, result)

        except Exception as e:
            logger.error(f"加载文件失败: {self.file_path}", exc_info=True)
            self.finished.emit(False, str(e))

    def request_stop(self):
        """请求停止加载"""
        self._stop_requested = True


class FileLoadingProgressDialog:  # pylint: disable=R0903,R0913
    """文件加载进度对话框管理器

    管理进度对话框的显示、更新和关闭。
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        file_path: Path,
        load_func: Callable,
        on_success: Callable,
        on_failure: Optional[Callable] = None,
        dialog_title: str = "加载文件",
        custom_message: str = None,
        on_cancel: Optional[Callable] = None,
        **load_kwargs,
    ):
        """初始化进度对话框管理器

        Args:
            parent: 父窗口
            file_path: 要加载的文件路径
            load_func: 加载函数
            on_success: 加载成功的回调函数，签名为 func(result)
            on_failure: 加载失败的回调函数（可选），签名为 func(error_message)
            dialog_title: 对话框标题，例如 "预览文件" 或 "批处理加载"
            custom_message: 自定义消息文本，默认为 "正在加载文件: {文件名}..."
            on_cancel: 用户取消时的回调函数（可选）
            **load_kwargs: 传递给加载函数的参数
        """
        self.parent = parent
        self.file_path = file_path
        self.on_success = on_success
        self.on_failure = on_failure
        self.on_cancel = on_cancel

        # 如果 parent 不是 QWidget，设为 None（避免类型错误）
        safe_parent = parent
        if parent is not None and not isinstance(parent, QWidget):
            safe_parent = None

        # 构建消息文本
        if custom_message:
            message_text = custom_message
        else:
            message_text = f"正在加载文件: {file_path.name}..."

        # 创建进度对话框
        self.progress_dialog = QProgressDialog(
            message_text,
            "取消",
            0,
            0,  # 不确定进度（indeterminate）
            safe_parent,
        )
        self.progress_dialog.setWindowTitle(dialog_title)
        self.progress_dialog.setMinimumDuration(500)  # 0.5秒后显示
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)

        # 创建后台工作线程
        self.thread = QThread()
        self.worker = FileLoadWorker(file_path, load_func, **load_kwargs)
        self.worker.moveToThread(self.thread)

        # 连接信号
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.thread.quit)  # 完成后退出线程
        self.worker.progress.connect(self._on_progress)
        self.progress_dialog.canceled.connect(self._on_canceled)

    def start(self):
        """开始加载文件并显示进度"""
        self.progress_dialog.show()
        self.thread.start()

    def _on_progress(self, current: int, maximum: int, text: str):
        """更新进度"""
        try:
            self.progress_dialog.setLabelText(text)
            if maximum > 0:
                self.progress_dialog.setMaximum(maximum)
                self.progress_dialog.setValue(current)
        except RuntimeError:
            # 对话框可能已经被销毁
            logger.debug("更新进度时对话框已销毁", exc_info=True)

    def _on_finished(self, success: bool, result):
        """加载完成处理"""
        from gui.managers import report_user_error  # pylint: disable=C0415

        try:
            # 关闭进度对话框
            try:
                if self.progress_dialog:
                    self.progress_dialog.close()
            except RuntimeError:
                pass

            # 等待线程退出（非阻塞）
            if not self.thread.isFinished():
                self.thread.quit()
                self.thread.wait(100)  # 最多等待0.1秒

            # 调用回调
            if success:
                if self.on_success:
                    self.on_success(result)
            else:
                logger.warning(f"文件加载失败: {self.file_path.name} - {result}")
                if self.on_failure:
                    self.on_failure(result)
                else:
                    # 默认错误处理：显示错误对话框
                    from gui.managers import report_user_error

                    report_user_error(
                        self.parent,
                        "文件加载失败",
                        f"无法加载文件: {self.file_path.name}",
                        details=str(result),
                        is_warning=True,
                    )

        except Exception as e:
            logger.error("处理加载完成事件失败", exc_info=True)
            if self.on_failure:
                self.on_failure(str(e))

    def _on_canceled(self):
        """用户取消加载"""
        try:
            # 请求工作线程停止
            self.worker.request_stop()

            # 强制停止线程
            self.thread.quit()
            if not self.thread.wait(2000):  # 等待2秒
                logger.warning("工作线程未能及时停止，强制终止")
                self.thread.terminate()
                self.thread.wait()

            logger.info(f"用户取消加载文件: {self.file_path.name}")
            
            # 调用取消回调
            if self.on_cancel:
                try:
                    self.on_cancel()
                except Exception as e:
                    logger.warning(f"执行取消回调失败: {e}", exc_info=True)

        except Exception as e:
            logger.error("处理取消事件失败", exc_info=True)


def load_file_with_progress(
    parent: Optional[QWidget],
    file_path: Path,
    load_func: Callable,
    on_success: Callable,
    on_failure: Optional[Callable] = None,
    dialog_title: str = "加载文件",
    custom_message: str = None,
    on_cancel: Optional[Callable] = None,
    **load_kwargs,
) -> FileLoadingProgressDialog:
    """便捷函数：带进度指示器地加载文件

    Args:
        parent: 父窗口
        file_path: 文件路径
        load_func: 加载函数
        on_success: 成功回调
        on_failure: 失败回调（可选）
        dialog_title: 对话框标题（默认"加载文件"）
        custom_message: 自定义消息（可选）
        on_cancel: 取消回调（可选）
        **load_kwargs: 加载函数参数

    Returns:
        FileLoadingProgressDialog 实例（已启动）

    Example:
        ```python
        def on_loaded(df):
            print(f"加载了 {len(df)} 行数据")

        load_file_with_progress(
            self,
            Path("data.csv"),
            pd.read_csv,
            on_loaded,
            dialog_title="预览文件",
            skiprows=2
        )
        ```
    """
    dialog = FileLoadingProgressDialog(
        parent,
        file_path,
        load_func,
        on_success,
        on_failure,
        dialog_title=dialog_title,
        custom_message=custom_message,
        on_cancel=on_cancel,
        **load_kwargs,
    )
    dialog.start()
    return dialog
