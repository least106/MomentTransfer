"""批处理线程相关的迁移模块。

本模块提供一组函数，封装 `BatchManager` 中与批处理线程、GUI 状态准备与撤销相关的逻辑，
以便将 `gui/batch_manager.py` 逐步拆分为更小的子模块。
"""

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from gui.batch_thread import BatchProcessThread

logger = logging.getLogger(__name__)


def run_batch_processing(manager):
    """运行批处理（由 `BatchManager` 委托）。"""
    try:
        project_data = getattr(manager.gui, "current_config", None)
        if project_data is None:
            QMessageBox.warning(manager.gui, "提示", "请先加载配置（JSON）")
            return

        if not hasattr(manager.gui, "inp_batch_input"):
            QMessageBox.warning(manager.gui, "提示", "缺少输入路径控件")
            return
        input_path = Path(manager.gui.inp_batch_input.text().strip())
        if not input_path.exists():
            QMessageBox.warning(manager.gui, "错误", "输入路径不存在")
            return

        collect_fn = getattr(manager, "_collect_files_to_process", None)
        if callable(collect_fn):
            files_to_process, output_dir, error_msg = collect_fn(input_path)
        else:
            files_to_process, output_dir, error_msg = ([], None, "无法收集待处理文件")
        if error_msg:
            QMessageBox.warning(manager.gui, "提示", error_msg)
            return

        if output_dir is None:
            output_dir = Path("data/output")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        existing_files = set(str(f) for f in output_path.glob("*") if f.is_file())
        # pylint: disable=protected-access
        manager.gui._batch_output_dir = output_path
        manager.gui._batch_existing_files = existing_files
        # pylint: enable=protected-access

        try:
            manager._current_batch_context = {
                "input_path": str(input_path),
                "files": [str(f) for f in files_to_process],
                "output_dir": str(output_path),
            }
        except Exception:
            pass

        data_config = None

        manager.batch_thread = create_batch_thread(
            manager, files_to_process, output_path, data_config, project_data
        )

        attach_batch_thread_signals(manager)
        prepare_gui_for_batch(manager)

        if manager.batch_thread is not None:
            manager.batch_thread.start()
            logger.info(f"开始批处理 {len(files_to_process)} 个文件")
    except Exception as e:
        logger.error(f"启动批处理失败: {e}")
        try:
            QMessageBox.critical(manager.gui, "错误", f"启动失败: {e}")
        except Exception:
            pass


def attach_batch_thread_signals(manager):
    """为当前的 `manager.batch_thread` 连接信号（安全地忽略错误）。"""
    try:
        if getattr(manager, "batch_thread", None) is None:
            return
        try:
            manager.batch_thread.progress.connect(manager.gui.progress_bar.setValue)
        except Exception:
            pass

        try:

            def _on_thread_log(msg):
                try:
                    manager.gui.txt_batch_log.append(f"[{_now_str(manager)}] {msg}")
                except Exception:
                    pass

            manager.batch_thread.log_message.connect(_on_thread_log)
        except Exception:
            pass

        try:
            manager.batch_thread.finished.connect(manager.on_batch_finished)
        except Exception:
            pass
        try:
            manager.batch_thread.error.connect(manager.on_batch_error)
        except Exception:
            pass
    except Exception:
        logger.debug("连接 batch_thread 信号失败", exc_info=True)


def _now_str(manager):
    return datetime.now().strftime("%H:%M:%S")


def prepare_gui_for_batch(manager):
    """更新 GUI 状态以进入批处理模式（锁定控件等）。"""
    try:
        try:
            if hasattr(manager.gui, "_set_controls_locked"):
                # pylint: disable=protected-access
                manager.gui._set_controls_locked(True)
                # pylint: enable=protected-access
        except Exception:
            pass

        try:
            if hasattr(manager.gui, "btn_batch"):
                manager.gui.btn_batch.setEnabled(False)
                manager.gui.btn_batch.setText("处理中...")
        except Exception:
            logger.debug("无法禁用批处理按钮", exc_info=True)

        # 不再在开始处理时自动切换到日志标签，保持用户当前视图不变
    except Exception:
        logger.debug("准备 GUI 进入批处理失败", exc_info=True)


def create_batch_thread(
    manager,
    files_to_process,
    output_path: Path,
    data_config,
    project_data,
):
    """构造并返回配置好的 `BatchProcessThread` 实例（安全容错）。"""
    try:
        calc = getattr(manager.gui, "calculator", None)
        ts_fmt = getattr(manager.gui, "timestamp_format", "%Y%m%d_%H%M%S")
        sp_map = getattr(manager.gui, "special_part_mapping_by_file", {})
        sp_sel = getattr(manager.gui, "special_part_row_selection_by_file", {})
        fp_sel = getattr(manager.gui, "file_part_selection_by_file", {})
        tbl_sel = getattr(manager.gui, "table_row_selection_by_file", {})

        return BatchProcessThread(
            calc,
            files_to_process,
            output_path,
            data_config,
            project_data=project_data,
            timestamp_format=ts_fmt,
            special_part_mapping_by_file=sp_map,
            special_row_selection_by_file=sp_sel,
            file_part_selection_by_file=fp_sel,
            table_row_selection_by_file=tbl_sel,
        )
    except Exception:
        logger.debug("创建 BatchProcessThread 失败", exc_info=True)
        return None


def restore_gui_after_batch(manager, *, enable_undo: bool = False):
    """在批处理结束或出错后恢复 GUI 状态（解锁控件、恢复按钮状态）。"""
    try:
        try:
            if hasattr(manager.gui, "_set_controls_locked"):
                # pylint: disable=protected-access
                manager.gui._set_controls_locked(False)
                # pylint: enable=protected-access
        except Exception:
            pass

        try:
            if hasattr(manager.gui, "btn_batch"):
                manager.gui.btn_batch.setEnabled(True)
                manager.gui.btn_batch.setText("开始处理")
        except Exception:
            logger.debug("无法启用批处理按钮", exc_info=True)

        if enable_undo:
            try:
                if hasattr(manager.gui, "btn_undo"):
                    manager.gui.btn_undo.setEnabled(True)
                    manager.gui.btn_undo.setVisible(True)
            except Exception:
                logger.debug("无法启用撤销按钮", exc_info=True)
    except Exception:
        logger.debug("恢复 GUI 状态失败", exc_info=True)


def request_cancel_batch(manager):
    """请求取消正在运行的批处理任务（由 main_window 或 BatchManager 调用）。"""
    try:
        batch_thread = getattr(manager.gui, "batch_thread", None)
        if batch_thread is not None:
            if hasattr(manager.gui, "txt_batch_log"):
                try:
                    ts = datetime.now().strftime("%H:%M:%S")
                    manager.gui.txt_batch_log.append(
                        f"[{ts}] 用户请求取消任务，正在停止..."
                    )
                except Exception:
                    pass
            try:
                batch_thread.request_stop()
            except Exception:
                logger.debug(
                    "batch_thread.request_stop 调用失败（可能已结束）", exc_info=True
                )

            if hasattr(manager.gui, "btn_cancel"):
                try:
                    manager.gui.btn_cancel.setEnabled(False)
                except Exception:
                    pass
    except Exception:
        logger.debug("request_cancel_batch 失败", exc_info=True)


def undo_batch_processing(manager):
    """撤销最近一次批处理操作（由 `BatchManager` 委托）。"""
    try:
        output_dir = getattr(manager.gui, "_batch_output_dir", None)
        existing_files = getattr(manager.gui, "_batch_existing_files", set())

        if not output_dir or not isinstance(existing_files, set):
            QMessageBox.warning(
                manager.gui,
                "提示",
                "没有可撤销的批处理记录。请先运行批处理。",
            )
            return

        reply = QMessageBox.question(
            manager.gui,
            "确认撤销",
            f"确定要撤销最近一次批处理？\n将删除 {output_dir} 中的新生成文件（保留源数据）。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            deleted_count = delete_new_output_files(manager, output_dir, existing_files)
            QMessageBox.information(
                manager.gui, "撤销完成", f"已删除 {deleted_count} 个输出文件"
            )

            # pylint: disable=protected-access
            manager.gui._batch_output_dir = None
            manager.gui._batch_existing_files = set()
            # pylint: enable=protected-access

            try:
                rid = getattr(manager, "_last_history_record_id", None)
                if rid and getattr(manager, "history_store", None):
                    manager.history_store.mark_status(rid, "undone")
                    if getattr(manager, "history_panel", None):
                        manager.history_panel.refresh()
            except Exception:
                logger.debug("更新历史记录状态失败", exc_info=True)

            try:
                if hasattr(manager.gui, "btn_undo"):
                    manager.gui.btn_undo.setEnabled(False)
                    manager.gui.btn_undo.setVisible(False)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"撤销批处理失败: {e}", exc_info=True)
            try:
                QMessageBox.critical(manager.gui, "错误", f"撤销失败: {e}")
            except Exception:
                pass
    except Exception as e:
        logger.error(f"undo_batch_processing 失败: {e}", exc_info=True)


def delete_new_output_files(manager, output_dir, existing_files):
    """删除 `output_dir` 中不在 `existing_files` 中的新文件，返回删除计数。"""
    deleted_count = 0
    try:
        if output_dir and Path(output_dir).exists():
            output_path = Path(output_dir)
            existing_iter = existing_files or set()
            existing_files_resolved = set()
            for p in existing_iter:
                try:
                    existing_files_resolved.add(str(Path(p).resolve()))
                except Exception:
                    continue
            for file in output_path.iterdir():
                try:
                    file_path_str = str(file.resolve())
                except Exception:
                    continue
                if file.is_file() and file_path_str not in existing_files_resolved:
                    try:
                        file.unlink()
                        deleted_count += 1
                        logger.info(f"已删除: {file}")
                    except Exception as e:
                        logger.warning(f"无法删除 {file}: {e}")
    except Exception:
        logger.debug("删除输出文件时发生错误", exc_info=True)
        raise
    return deleted_count
