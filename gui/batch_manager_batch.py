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

        # 优先使用保存的多选路径列表，否则从输入框读取
        selected_paths = getattr(manager, "_selected_paths", None)
        if selected_paths and len(selected_paths) > 0:
            input_paths = selected_paths
        else:
            if not hasattr(manager.gui, "inp_batch_input"):
                QMessageBox.warning(manager.gui, "提示", "缺少输入路径控件")
                return
            input_text = manager.gui.inp_batch_input.text().strip()
            if not input_text:
                QMessageBox.warning(manager.gui, "错误", "请选择输入路径")
                return
            # 从文本解析路径（移除可能的 "(+N 项)" 后缀）
            if "(+" in input_text and input_text.endswith("项)"):
                input_text = input_text.split("(")[0].strip()
            input_path = Path(input_text)
            if not input_path.exists():
                QMessageBox.warning(manager.gui, "错误", "输入路径不存在")
                return
            input_paths = [input_path]

        # 收集所有选中路径的文件
        all_files = []
        output_dir = None
        collect_fn = getattr(manager, "_collect_files_to_process", None)

        error_msg = None
        for input_path in input_paths:
            if not callable(collect_fn):
                error_msg = "无法收集待处理文件"
                break
            files, out_dir, err = collect_fn(input_path)
            if err:
                error_msg = err
                break
            if out_dir is not None and output_dir is None:
                output_dir = out_dir
            if files:
                all_files.extend(list(files))

        if error_msg:
            QMessageBox.warning(manager.gui, "提示", error_msg)
            return

        files_to_process = all_files
        if not files_to_process:
            QMessageBox.warning(manager.gui, "提示", "未找到可处理的文件")
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
            input_paths_str = ";".join(str(p) for p in input_paths)
            manager._current_batch_context = {
                "input_path": input_paths_str,
                "input_paths": [str(p) for p in input_paths],
                "files": [str(f) for f in files_to_process],
                "output_dir": str(output_path),
            }
        except Exception:
            logger.debug("设置当前批处理上下文失败（非致命）", exc_info=True)

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
        # 使用统一的错误报告函数
        from gui.managers import report_user_error

        report_user_error(
            manager.gui, "启动批处理失败", "无法启动批处理操作", details=str(e)
        )


def attach_batch_thread_signals(manager):
    """为当前的 `manager.batch_thread` 连接信号（安全地忽略错误）。"""
    try:
        if getattr(manager, "batch_thread", None) is None:
            return
        try:
            manager.batch_thread.progress.connect(manager.gui.progress_bar.setValue)
        except Exception:
            logger.debug("连接 progress 信号失败（非致命）", exc_info=True)

        # 连接详细进度信号以更新进度条格式文本
        try:

            def _on_progress_detail(pct, detail_msg):
                try:
                    # 设置进度条显示格式：百分比 + 详细信息
                    manager.gui.progress_bar.setFormat(f"{pct}% - {detail_msg}")
                except Exception:
                    logger.debug(
                        "更新进度条格式文本失败（非致命）",
                        exc_info=True,
                    )

            manager.batch_thread.progress_detail.connect(_on_progress_detail)
        except Exception:
            logger.debug("连接 progress_detail 信号失败（非致命）", exc_info=True)

        try:

            def _on_thread_log(msg):
                try:
                    manager.gui.txt_batch_log.append(f"[{_now_str(manager)}] {msg}")
                except Exception:
                    logger.debug(
                        "追加线程日志到 txt_batch_log 失败（非致命）",
                        exc_info=True,
                    )

            manager.batch_thread.log_message.connect(_on_thread_log)
        except Exception:
            logger.debug("连接 log_message 信号失败（非致命）", exc_info=True)

        try:
            manager.batch_thread.finished.connect(manager.on_batch_finished)
        except Exception:
            logger.debug("连接 finished 信号失败（非致命）", exc_info=True)
        try:
            manager.batch_thread.error.connect(manager.on_batch_error)
        except Exception:
            logger.debug("连接 error 信号失败（非致命）", exc_info=True)
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
            logger.debug("设置控件锁定失败（非致命）", exc_info=True)

        # 禁用所有开始按钮（支持新旧按钮名称）
        for btn_name in ("btn_batch", "btn_start_menu", "btn_batch_in_toolbar"):
            try:
                btn = getattr(manager.gui, btn_name, None)
                if btn is not None:
                    btn.setEnabled(False)
                    # 只对有 setText 方法的按钮设置文本
                    if hasattr(btn, "setText"):
                        try:
                            btn.setText("处理中...")
                        except Exception:
                            pass
            except Exception:
                logger.debug("无法禁用按钮 %s", btn_name, exc_info=True)

        # 显示进度条并初始化格式
        try:
            if hasattr(manager.gui, "progress_bar"):
                manager.gui.progress_bar.setVisible(True)
                manager.gui.progress_bar.setFormat("%p% - 准备中...")
        except Exception:
            logger.debug("显示进度条失败（非致命）", exc_info=True)

        # 显示取消按钮
        try:
            if hasattr(manager.gui, "btn_cancel"):
                manager.gui.btn_cancel.setVisible(True)
                manager.gui.btn_cancel.setEnabled(True)
        except Exception:
            logger.debug("显示取消按钮失败（非致命）", exc_info=True)

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
            logger.debug("恢复控件锁定失败（非致命）", exc_info=True)

        # 恢复所有开始按钮（支持新旧按钮名称）
        try:
            # 根据线程的停止请求判断是否为已取消状态
            try:
                bt = getattr(manager, "batch_thread", None)
                cancelled = False
                if bt is not None:
                    cancelled = bool(getattr(bt, "_stop_requested", False))
            except Exception:
                cancelled = False

            # 按钮文本和状态
            btn_text = "已取消" if cancelled else "开始处理"

            for btn_name in ("btn_batch", "btn_start_menu", "btn_batch_in_toolbar"):
                try:
                    btn = getattr(manager.gui, btn_name, None)
                    if btn is not None:
                        btn.setEnabled(True)
                        # 只对有 setText 方法的按钮设置文本
                        if hasattr(btn, "setText"):
                            try:
                                btn.setText(btn_text)
                            except Exception:
                                pass
                except Exception:
                    logger.debug("无法恢复按钮 %s", btn_name, exc_info=True)

            # 如果是已取消状态，显示状态消息并在两秒后恢复按钮文字
            if cancelled:
                try:
                    manager.gui.statusBar().showMessage("批处理已取消", 3000)
                except Exception:
                    pass

                try:
                    from PySide6.QtCore import QTimer

                    def _reset_btn_text():
                        for btn_name in ("btn_batch", "btn_start_menu", "btn_batch_in_toolbar"):
                            try:
                                btn = getattr(manager.gui, btn_name, None)
                                if btn is not None and hasattr(btn, "setText"):
                                    btn.setText("开始处理")
                            except Exception:
                                pass

                    try:
                        QTimer.singleShot(2000, _reset_btn_text)
                    except Exception:
                        _reset_btn_text()
                except Exception:
                    pass
        except Exception:
            logger.debug("无法恢复开始按钮", exc_info=True)

        # 重置进度条格式为默认百分比显示并隐藏
        try:
            if hasattr(manager.gui, "progress_bar"):
                manager.gui.progress_bar.setFormat("%p%")
                manager.gui.progress_bar.setVisible(False)  # 批处理完成后隐藏进度条
        except Exception:
            logger.debug("重置进度条格式失败（非致命）", exc_info=True)

        # 隐藏取消按钮
        try:
            if hasattr(manager.gui, "btn_cancel"):
                manager.gui.btn_cancel.setVisible(False)
                manager.gui.btn_cancel.setEnabled(False)
        except Exception:
            logger.debug("隐藏取消按钮失败（非致命）", exc_info=True)

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
        # 优先检查 manager 本身是否持有 batch_thread（BatchManager 情况），然后回退到 gui
        batch_thread = getattr(manager, "batch_thread", None)
        if batch_thread is None:
            batch_thread = getattr(getattr(manager, "gui", None), "batch_thread", None)
        if batch_thread is None:
            return

        # 记录日志到界面
        if hasattr(manager.gui, "txt_batch_log"):
            try:
                ts = datetime.now().strftime("%H:%M:%S")
                manager.gui.txt_batch_log.append(
                    f"[{ts}] 用户请求取消任务，正在停止..."
                )
            except Exception:
                logger.debug(
                    "追加取消日志到 txt_batch_log 失败（非致命）", exc_info=True
                )

        # 立即在 UI 上显示取消中状态
        try:
            if hasattr(manager.gui, "btn_batch"):
                try:
                    manager.gui.btn_batch.setText("取消中...")
                    manager.gui.btn_batch.setEnabled(False)
                except Exception:
                    logger.debug("设置批处理按钮为取消中失败（非致命）", exc_info=True)
        except Exception:
            pass

        try:
            if hasattr(manager.gui, "statusBar"):
                try:
                    manager.gui.statusBar().showMessage(
                        "取消请求已发送，正在停止...", 5000
                    )
                except Exception:
                    logger.debug("显示取消状态栏消息失败（非致命）", exc_info=True)
        except Exception:
            pass

        # 调用线程取消接口
        try:
            batch_thread.request_stop()
        except Exception:
            logger.debug(
                "batch_thread.request_stop 调用失败（可能已结束）",
                exc_info=True,
            )

        # 禁用取消按钮以避免重复请求
        if hasattr(manager.gui, "btn_cancel"):
            try:
                manager.gui.btn_cancel.setEnabled(False)
                manager.gui.btn_cancel.setVisible(False)  # 批处理结束后隐藏取消按钮
            except Exception:
                logger.debug("禁用取消按钮失败（非致命）", exc_info=True)

        # 启动超时监控：如果10秒后线程还未停止，显示强制终止选项
        try:
            from PySide6.QtCore import QTimer

            def check_cancel_timeout():
                try:
                    # 检查线程是否仍在运行
                    if batch_thread and batch_thread.isRunning():
                        from PySide6.QtWidgets import QMessageBox

                        reply = QMessageBox.warning(
                            manager.gui,
                            "取消超时",
                            "批处理任务取消超时（10秒），任务可能正在处理大文件或网络操作。\n\n"
                            "是否强制终止？（注意：强制终止可能导致数据不完整）",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No,
                        )
                        if reply == QMessageBox.Yes:
                            try:
                                batch_thread.terminate()
                                batch_thread.wait(2000)
                                if hasattr(manager.gui, "txt_batch_log"):
                                    ts = datetime.now().strftime("%H:%M:%S")
                                    manager.gui.txt_batch_log.append(
                                        f"[{ts}] 已强制终止批处理线程"
                                    )
                                # 恢复按钮状态
                                if hasattr(manager.gui, "btn_batch"):
                                    manager.gui.btn_batch.setText("开始批处理")
                                    manager.gui.btn_batch.setEnabled(True)
                                if hasattr(manager.gui, "btn_cancel"):
                                    manager.gui.btn_cancel.setEnabled(False)
                            except Exception as e:
                                logger.error(
                                    "强制终止批处理线程失败: %s", e, exc_info=True
                                )
                except Exception:
                    logger.debug("检查取消超时失败", exc_info=True)

            # 10秒后检查
            QTimer.singleShot(10000, check_cancel_timeout)
        except Exception:
            logger.debug("启动取消超时监控失败（非致命）", exc_info=True)

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
