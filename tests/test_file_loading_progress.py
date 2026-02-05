"""测试文件加载进度指示器功能

验证大文件加载时显示进度指示器，避免 UI 冻结感知。
"""

import logging
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

from gui.file_loading_progress import (
    FileLoadWorker,
    FileLoadingProgressDialog,
    load_file_with_progress,
)

logger = logging.getLogger(__name__)


class TestFileLoadWorker:
    """测试 FileLoadWorker 类"""

    def test_worker_initialization(self):
        """测试工作线程初始化"""
        file_path = Path("test.csv")
        load_func = Mock()

        worker = FileLoadWorker(file_path, load_func, max_rows=100)

        assert worker.file_path == file_path
        assert worker.load_func == load_func
        assert worker.kwargs == {"max_rows": 100}
        assert not worker._stop_requested

    def test_worker_run_success(self, qtbot):
        """测试工作线程成功加载"""
        file_path = Path("test.csv")
        mock_df = pd.DataFrame({"A": [1, 2, 3]})
        load_func = Mock(return_value=mock_df)

        worker = FileLoadWorker(file_path, load_func)

        # 监听信号
        with qtbot.waitSignal(worker.finished, timeout=1000) as blocker:
            worker.run()

        # 验证信号参数
        success, result = blocker.args
        assert success is True
        assert result.equals(mock_df)
        load_func.assert_called_once_with(file_path)

    def test_worker_run_failure(self, qtbot):
        """测试工作线程加载失败"""
        file_path = Path("test.csv")
        load_func = Mock(side_effect=ValueError("测试错误"))

        worker = FileLoadWorker(file_path, load_func)

        # 监听信号
        with qtbot.waitSignal(worker.finished, timeout=1000) as blocker:
            worker.run()

        # 验证信号参数
        success, error_msg = blocker.args
        assert success is False
        assert "测试错误" in error_msg

    def test_worker_request_stop(self, qtbot):
        """测试请求停止工作线程"""

        def slow_load_func(file_path):
            """模拟慢速加载"""
            time.sleep(0.1)
            return pd.DataFrame()

        file_path = Path("test.csv")
        worker = FileLoadWorker(file_path, slow_load_func)

        # 请求停止
        worker.request_stop()

        # 运行后应该检测到停止请求
        with qtbot.waitSignal(worker.finished, timeout=1000) as blocker:
            worker.run()

        success, result = blocker.args
        assert success is False
        assert "用户取消" in result

    def test_worker_progress_signal(self, qtbot):
        """测试工作线程发送进度信号"""
        file_path = Path("test.csv")
        load_func = Mock(return_value=pd.DataFrame())

        worker = FileLoadWorker(file_path, load_func)

        # 监听进度信号
        progress_received = []

        def on_progress(current, maximum, text):
            progress_received.append((current, maximum, text))

        worker.progress.connect(on_progress)

        # 运行并等待完成
        with qtbot.waitSignal(worker.finished, timeout=1000):
            worker.run()

        # 验证进度信号至少发送了两次（开始和结束）
        assert len(progress_received) >= 2
        assert "正在读取文件" in progress_received[0][2]
        assert "加载完成" in progress_received[-1][2]


class TestFileLoadingProgressDialog:
    """测试 FileLoadingProgressDialog 类"""

    def test_dialog_initialization(self, qtbot):
        """测试进度对话框初始化"""
        file_path = Path("test.csv")
        load_func = Mock()
        on_success = Mock()

        dialog = FileLoadingProgressDialog(
            None, file_path, load_func, on_success, max_rows=100
        )

        assert dialog.file_path == file_path
        assert dialog.on_success == on_success
        assert dialog.progress_dialog is not None
        assert dialog.thread is not None
        assert dialog.worker is not None

    def test_dialog_success_callback(self, qtbot):
        """测试加载成功后调用回调"""
        file_path = Path("test.csv")
        mock_df = pd.DataFrame({"A": [1, 2, 3]})
        load_func = Mock(return_value=mock_df)
        on_success = Mock()

        dialog = FileLoadingProgressDialog(
            None, file_path, load_func, on_success
        )

        # 使用 qtbot 等待信号
        with qtbot.waitSignal(dialog.worker.finished, timeout=2000):
            dialog.start()

        # 处理所有挂起的事件
        QCoreApplication.processEvents()

        # 验证回调被调用
        on_success.assert_called_once()
        args = on_success.call_args[0]
        assert args[0].equals(mock_df)

    def test_dialog_failure_callback(self, qtbot):
        """测试加载失败后调用回调"""
        file_path = Path("test.csv")
        load_func = Mock(side_effect=ValueError("测试错误"))
        on_success = Mock()
        on_failure = Mock()

        dialog = FileLoadingProgressDialog(
            None, file_path, load_func, on_success, on_failure
        )

        # 使用 qtbot 等待信号
        with qtbot.waitSignal(dialog.worker.finished, timeout=2000):
            dialog.start()

        # 处理所有挂起的事件
        QCoreApplication.processEvents()

        # 验证失败回调被调用
        on_failure.assert_called_once()
        error_msg = on_failure.call_args[0][0]
        assert "测试错误" in error_msg

    def test_dialog_cancel(self, qtbot):
        """测试用户取消加载"""

        def slow_load_func(file_path):
            """模拟慢速加载"""
            time.sleep(1)
            return pd.DataFrame()

        file_path = Path("test.csv")
        on_success = Mock()

        dialog = FileLoadingProgressDialog(
            None, file_path, slow_load_func, on_success
        )
        dialog.start()

        # 模拟用户取消
        dialog._on_canceled()

        # 等待线程停止
        assert dialog.thread.wait(3000), "线程未能及时停止"

        # 成功回调不应该被调用
        on_success.assert_not_called()


class TestLoadFileWithProgress:
    """测试便捷函数 load_file_with_progress"""

    def test_load_file_with_progress_success(self, qtbot):
        """测试便捷函数成功加载"""
        file_path = Path("test.csv")
        mock_df = pd.DataFrame({"A": [1, 2, 3]})
        load_func = Mock(return_value=mock_df)
        on_success = Mock()

        dialog = load_file_with_progress(
            None, file_path, load_func, on_success
        )

        # 验证返回的是 FileLoadingProgressDialog 实例
        assert isinstance(dialog, FileLoadingProgressDialog)

        # 等待加载完成
        with qtbot.waitSignal(dialog.worker.finished, timeout=2000):
            pass  # 已经在 load_file_with_progress 中启动了
        QCoreApplication.processEvents()

        # 验证回调被调用
        on_success.assert_called_once()

    def test_load_file_with_kwargs(self, qtbot):
        """测试传递额外参数给加载函数"""
        file_path = Path("test.csv")
        mock_df = pd.DataFrame({"A": [1, 2, 3]})
        load_func = Mock(return_value=mock_df)
        on_success = Mock()

        dialog = load_file_with_progress(
            None,
            file_path,
            load_func,
            on_success,
            max_rows=100,
            skiprows=2,
        )

        # 等待加载完成
        with qtbot.waitSignal(dialog.worker.finished, timeout=2000):
            pass
        QCoreApplication.processEvents()

        # 验证加载函数被调用时传入了正确的参数
        load_func.assert_called_once_with(
            file_path, max_rows=100, skiprows=2
        )


class TestIntegrationWithBatchState:
    """集成测试：与 BatchStateManager 配合使用"""

    def test_batch_state_async_loading(self, qtbot, tmp_path):
        """测试 BatchStateManager.get_table_df_preview_async"""
        from gui.batch_state import BatchStateManager

        # 创建测试 CSV 文件
        csv_path = tmp_path / "test_large.csv"
        df = pd.DataFrame({"A": list(range(1000)), "B": list(range(1000))})
        df.to_csv(csv_path, index=False)

        # 创建状态管理器
        state_manager = BatchStateManager()

        # 模拟 GUI 实例
        gui_instance = Mock()

        # 测试异步加载
        loaded_df = None

        def on_loaded(df):
            nonlocal loaded_df
            loaded_df = df

        dialog = state_manager.get_table_df_preview_async(
            csv_path, gui_instance, on_loaded, max_rows=100
        )

        # 等待加载完成
        with qtbot.waitSignal(dialog.worker.finished, timeout=3000):
            pass
        QCoreApplication.processEvents()

        # 验证数据被正确加载
        assert loaded_df is not None
        assert len(loaded_df) == 100

    def test_batch_state_cached_loading(self, qtbot, tmp_path):
        """测试缓存命中时直接返回"""
        from gui.batch_state import BatchStateManager

        # 创建测试 CSV 文件
        csv_path = tmp_path / "test.csv"
        df = pd.DataFrame({"A": [1, 2, 3]})
        df.to_csv(csv_path, index=False)

        # 创建状态管理器
        state_manager = BatchStateManager()
        gui_instance = Mock()

        # 第一次加载（同步）
        df1 = state_manager.get_table_df_preview(csv_path, gui_instance, max_rows=100)
        assert df1 is not None

        # 第二次加载（异步）应该直接使用缓存
        loaded_df = None

        def on_loaded(df):
            nonlocal loaded_df
            loaded_df = df

        dialog = state_manager.get_table_df_preview_async(
            csv_path, gui_instance, on_loaded, max_rows=100
        )

        # 缓存命中时不会创建对话框
        assert dialog is None

        # 回调应该立即被调用
        assert loaded_df is not None
        assert len(loaded_df) == len(df1)


class TestRealWorldScenarios:
    """真实场景测试"""

    def test_large_csv_loading(self, qtbot, tmp_path):
        """测试加载大型 CSV 文件"""
        # 创建一个较大的 CSV 文件（约 1MB）
        csv_path = tmp_path / "large.csv"
        df = pd.DataFrame({
            "col1": list(range(10000)),
            "col2": list(range(10000)),
            "col3": list(range(10000)),
        })
        df.to_csv(csv_path, index=False)

        # 测试加载
        loaded_df = None

        def on_loaded(df):
            nonlocal loaded_df
            loaded_df = df

        from src.utils import read_table_preview

        dialog = load_file_with_progress(
            None,
            csv_path,
            read_table_preview,
            on_loaded,
            max_rows=200,
        )

        # 等待加载完成
        with qtbot.waitSignal(dialog.worker.finished, timeout=5000):
            pass
        QCoreApplication.processEvents()

        # 验证数据正确
        assert loaded_df is not None
        assert len(loaded_df) == 200

    def test_excel_loading_with_progress(self, qtbot, tmp_path):
        """测试加载 Excel 文件时显示进度"""
        # 创建测试 Excel 文件
        excel_path = tmp_path / "test.xlsx"
        df = pd.DataFrame({"A": list(range(100)), "B": list(range(100))})
        df.to_excel(excel_path, index=False)

        # 测试加载
        loaded_df = None
        progress_updates = []

        def on_loaded(df):
            nonlocal loaded_df
            loaded_df = df

        from src.utils import read_table_preview

        dialog = load_file_with_progress(
            None,
            excel_path,
            read_table_preview,
            on_loaded,
            max_rows=50,
        )

        # 监听进度信号
        def on_progress(current, maximum, text):
            progress_updates.append(text)

        dialog.worker.progress.connect(on_progress)

        # 等待加载完成
        with qtbot.waitSignal(dialog.worker.finished, timeout=5000):
            pass
        QCoreApplication.processEvents()

        # 验证
        assert loaded_df is not None
        assert len(loaded_df) == 50
        assert len(progress_updates) >= 2  # 至少有开始和结束两条进度

    def test_file_not_found_error_handling(self, qtbot):
        """测试文件不存在时的错误处理"""
        file_path = Path("nonexistent.csv")
        on_success = Mock()
        on_failure = Mock()

        from src.utils import read_table_preview

        dialog = load_file_with_progress(
            None,
            file_path,
            read_table_preview,
            on_success,
            on_failure,
        )

        # 等待完成
        with qtbot.waitSignal(dialog.worker.finished, timeout=2000):
            pass
        QCoreApplication.processEvents()

        # read_table_preview 返回 None 而不是抛出异常
        # 所以成功回调会被调用，但参数是 None
        on_success.assert_called_once()
        result = on_success.call_args[0][0]
        assert result is None  # 文件不存在时返回 None
