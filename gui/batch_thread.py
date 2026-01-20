"""
批处理线程模块
"""

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from PySide6.QtCore import QThread, Signal

from src.special_format_parser import (
    looks_like_special_format,
    process_special_format_file,
)

logger = logging.getLogger(__name__)


class BatchProcessThread(QThread):
    """在后台线程中执行批量处理"""

    progress = Signal(int)
    log_message = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        calculator,
        file_list,
        output_dir,
        data_config,
        project_data=None,
        timestamp_format: str = "%Y%m%d_%H%M%S",
        special_part_mapping_by_file: dict = None,
        special_row_selection_by_file: dict = None,
        file_part_selection_by_file: dict = None,
        table_row_selection_by_file: dict = None,
    ):
        super().__init__()
        self.calculator = calculator
        self.file_list = file_list
        self.output_dir = Path(output_dir)
        self.data_config = data_config
        self._stop_requested = False
        self.project_data = project_data
        self.timestamp_format = timestamp_format
        # {str(file_path): {source_part: target_part}}
        self.special_part_mapping_by_file = special_part_mapping_by_file or {}
        # {str(file_path): {source_part: set(row_indices)}}
        self.special_row_selection_by_file = special_row_selection_by_file or {}
        # {str(file_path): {"source": str, "target": str}}
        self.file_part_selection_by_file = file_part_selection_by_file or {}
        # {str(file_path): set([row_index, ...])}
        self.table_row_selection_by_file = table_row_selection_by_file or {}

        # 全局批处理格式默认值（已不再提供 GUI 入口配置）；但保留作为 per-file 解析的 base。
        try:
            from src.cli_helpers import BatchConfig

            base = BatchConfig()
            # 兼容旧：若传入 dict，则用其覆盖 base
            if isinstance(data_config, dict):
                try:
                    base.skip_rows = int(data_config.get("skip_rows", base.skip_rows))
                except Exception:
                    pass
                if "overwrite" in data_config:
                    try:
                        base.overwrite = bool(data_config.get("overwrite"))
                    except Exception:
                        pass
            self._global_batch_cfg = base
        except Exception:
            self._global_batch_cfg = None

    def _resolve_cfg_for_file(self, file_path: Path):
        """为单个文件返回全局批处理配置。"""
        from src.cli_helpers import BatchConfig, resolve_file_format

        base = (
            self._global_batch_cfg
            if self._global_batch_cfg is not None
            else BatchConfig()
        )
        return resolve_file_format(str(file_path), base)

    def process_file(self, file_path):
        """处理单个文件并返回输出路径"""
        if self._stop_requested:
            raise RuntimeError("处理已被请求停止")
        # 特殊格式分支：解析多 part 并按 target part 输出
        if self.project_data is not None and looks_like_special_format(file_path):
            overwrite_flag = False
            try:
                if isinstance(self.data_config, dict):
                    overwrite_flag = bool(self.data_config.get("overwrite", False))
                else:
                    overwrite_flag = bool(getattr(self.data_config, "overwrite", False))
            except Exception:
                overwrite_flag = False

            part_mapping = None
            try:
                part_mapping = self.special_part_mapping_by_file.get(
                    str(Path(file_path))
                )
            except Exception:
                part_mapping = None

            row_selection = None
            try:
                row_selection = self.special_row_selection_by_file.get(
                    str(Path(file_path))
                )
            except Exception:
                row_selection = None

            outputs, report = process_special_format_file(
            # 在调用可能耗时的特殊格式解析前检查停止请求
            if self._stop_requested:
                raise RuntimeError("处理已被请求停止")

            outputs, report = process_special_format_file(
                Path(file_path),
                self.project_data,
                self.output_dir,
                part_target_mapping=part_mapping,
                part_row_selection=row_selection,
                timestamp_format=self.timestamp_format,
                overwrite=overwrite_flag,
                return_report=True,
            )

            # 将详细报告转换为 GUI 日志消息，按 part 显示成功/跳过/失败原因
            try:
                for r in report:
                    status = r.get("status")
                    part = r.get("part")
                    if status == "success":
                        msg = f"part '{part}' 处理成功，输出: {r.get('out_path', '')}"
                        try:
                            self.log_message.emit(msg)
                        except Exception:
                            logger.debug("无法发送 part 成功消息", exc_info=True)
                    elif status == "skipped":
                        reason = r.get("reason")
                        msg = f"part '{part}' 被跳过: {reason} - {r.get('message','') }"
                        try:
                            self.log_message.emit(msg)
                        except Exception:
                            logger.debug("无法发送 part 跳过消息", exc_info=True)
                    else:
                        msg = f"part '{part}' 处理失败: {r.get('reason')} - {r.get('message','') }"
                        try:
                            self.log_message.emit(msg)
                        except Exception:
                            logger.debug("无法发送 part 失败消息", exc_info=True)
            except Exception:
                logger.debug("处理 special format report 时发生错误", exc_info=True)

            # 如果特殊格式解析既没有产出 outputs 也没有 report（即解析器判定为特殊但未提取到任何 part），
            # 则回退为普通 CSV/Excel 处理（避免把空结果当作成功）。
            if not outputs and not report:
                try:
                    logger.debug(
                        "special_format 解析未提取到任何 part，回退到常规 CSV/Excel 处理: %s",
                        file_path,
                    )
                    try:
                        self.log_message.emit(
                            f"特殊格式解析未提取到 part，回退为常规表格处理: {file_path.name}"
                        )
                    except Exception:
                        logger.debug("无法发送回退日志消息", exc_info=True)
                except Exception:
                    pass
                # 不返回，此时继续到后面的常规分支处理
            else:
                return outputs

        try:
            if self._stop_requested:
                raise RuntimeError("处理已被请求停止")

            cfg_to_use = self._resolve_cfg_for_file(Path(file_path))
        except Exception as e:
            try:
                self.log_message.emit(
                    f"为文件 {Path(file_path).name} 解析 per-file 格式失败: {e}"
                )
            except Exception:
                logger.debug("无法发送 per-file 格式失败日志", exc_info=True)
            raise

        if file_path.suffix.lower() == ".csv":
            # 按列名读取 CSV（要求有表头）
            try:
                df = pd.read_csv(file_path, skiprows=int(getattr(cfg_to_use, "skip_rows", 0)))
                logger.debug("CSV 读取完成: %s 行, %s 列", df.shape[0], df.shape[1])
                try:
                    self.log_message.emit(
                        f"已读取文件 {file_path.name}: {df.shape[0]} 行, {df.shape[1]} 列"
                    )
                except Exception:
                    logger.debug("无法通过 signal 发送 df.shape", exc_info=True)
            except Exception as e:
                try:
                    self.log_message.emit(f"CSV 读取失败: {file_path.name} -> {e}")
                except Exception:
                    pass
                raise
        else:
            # Excel 文件也按列名读取
            try:
                df = pd.read_excel(file_path, skiprows=int(getattr(cfg_to_use, "skip_rows", 0)))
            except Exception as e:
                try:
                    self.log_message.emit(f"Excel 读取失败: {file_path.name} -> {e}")
                except Exception:
                    pass
                raise

        # 读取后检查是否需要停止
        if self._stop_requested:
            raise RuntimeError("处理已被请求停止")

        # 若用户在文件列表选择了“处理哪些数据行”，则按选择过滤。
        # 注意：此时不再执行“自动表头检测/丢弃首行”，以保证索引与 GUI 预览一致。
        try:
            fp_str = str(Path(file_path))
            sel = (self.table_row_selection_by_file or {}).get(fp_str)
            if sel is not None:
                sel_sorted = sorted(int(x) for x in set(sel))
                df = df.iloc[sel_sorted].reset_index(drop=True)
        except Exception as e:
            try:
                self.log_message.emit(
                    f"按行选择过滤失败: {Path(file_path).name} -> {e}"
                )
            except Exception:
                pass
            raise

        col_map = {str(c).strip().lower(): c for c in df.columns}

        has_dimensional = all(
            k in col_map for k in ["fx", "fy", "fz", "mx", "my", "mz"]
        )
        coeff_normal_key = "cz" if "cz" in col_map else "fn" if "fn" in col_map else None
        has_coeff = coeff_normal_key is not None and all(
            k in col_map for k in ["cx", "cy", "cmx", "cmy", "cmz"]
        )

        if not has_dimensional and not has_coeff:
            raise ValueError(
                "缺少必要列，需包含 Fx/Fy/Fz/Mx/My/Mz 或 Cx/Cy/Cz(CM)/CMx/CMy/CMz"
            )

        try:
            if has_dimensional:
                forces_df = df[
                    [
                        col_map["fx"],
                        col_map["fy"],
                        col_map["fz"],
                    ]
                ].apply(pd.to_numeric, errors="coerce")
                moments_df = df[
                    [
                        col_map["mx"],
                        col_map["my"],
                        col_map["mz"],
                    ]
                ].apply(pd.to_numeric, errors="coerce")
            else:
                coeff_force_df = df[
                    [
                        col_map["cx"],
                        col_map["cy"],
                        col_map[coeff_normal_key],
                    ]
                ].apply(pd.to_numeric, errors="coerce")
                coeff_moment_df = df[
                    [
                        col_map["cmx"],
                        col_map["cmy"],
                        col_map["cmz"],
                    ]
                ].apply(pd.to_numeric, errors="coerce")

                q = self.calculator.target_frame.q
                s_ref = self.calculator.target_frame.s_ref
                c_ref = self.calculator.target_frame.c_ref
                b_ref = self.calculator.target_frame.b_ref

                forces_df = coeff_force_df * (q * s_ref)
                moments_df = pd.DataFrame(
                    {
                        "mx": coeff_moment_df.iloc[:, 0] * (q * s_ref * b_ref),
                        "my": coeff_moment_df.iloc[:, 1] * (q * s_ref * c_ref),
                        "mz": coeff_moment_df.iloc[:, 2] * (q * s_ref * b_ref),
                    }
                )
        except Exception as e:
            try:
                self.log_message.emit(f"数据列提取或转换失败: {e}")
            except Exception:
                logger.debug("无法通过 signal 发送失败消息: %s", e, exc_info=True)
            raise

        alpha_col_name = col_map.get("alpha")

        calc_to_use = self.calculator
        # 新语义：若提供了 project_data，则按“每文件选择的 source/target”创建计算器
        if self.project_data is not None:
            try:
                from src.physics import AeroCalculator

                fp_str = str(Path(file_path))
                sel = (self.file_part_selection_by_file or {}).get(fp_str) or {}
                source_sel = (sel.get("source") or "").strip()
                target_sel = (sel.get("target") or "").strip()

                # 允许唯一 part 自动推断
                try:
                    source_names = list(
                        (getattr(self.project_data, "source_parts", {}) or {}).keys()
                    )
                except Exception:
                    source_names = []
                try:
                    target_names = list(
                        (getattr(self.project_data, "target_parts", {}) or {}).keys()
                    )
                except Exception:
                    target_names = []

                if not source_sel and len(source_names) == 1:
                    source_sel = str(source_names[0])
                if not target_sel and len(target_names) == 1:
                    target_sel = str(target_names[0])

                if not source_sel or not target_sel:
                    raise ValueError(
                        f"文件未选择 Source/Target: {Path(file_path).name}"
                    )

                calc_to_use = AeroCalculator(
                    self.project_data,
                    source_part=source_sel,
                    target_part=target_sel,
                )
            except Exception as e:
                try:
                    self.log_message.emit(
                        f"为文件 {Path(file_path).name} 创建 per-file 计算器失败: {e}"
                    )
                except Exception:
                    logger.debug("无法发送 per-file 计算器失败日志", exc_info=True)
                raise

        if calc_to_use is None:
            raise ValueError("缺少计算器：请先加载配置并为文件选择 Source/Target")

        # 将输入转换为有量纲力和力矩
        if has_dimensional:
            forces_dimensional = forces_df.to_numpy(dtype=float)
            moments_dimensional = moments_df.to_numpy(dtype=float)
        else:
            try:
                q = calc_to_use.target_frame.q
                s_ref = calc_to_use.target_frame.s_ref
                c_ref = calc_to_use.target_frame.c_ref
                b_ref = calc_to_use.target_frame.b_ref
            except Exception as e:
                raise ValueError(f"无法从计算器获取参考值: {e}")

            forces_dimensional = forces_df.to_numpy(dtype=float)  # F = C * q * S
            moments_dimensional = moments_df.to_numpy(dtype=float)

        # 在调用可能耗时的批量计算前检查停止请求
        if self._stop_requested:
            raise RuntimeError("处理已被请求停止")

        results = calc_to_use.process_batch(forces_dimensional, moments_dimensional)
        output_df = pd.DataFrame()

        # 如果原始数据有 Alpha 列，保留它
        if alpha_col_name and alpha_col_name in df.columns:
            output_df["Alpha"] = df[alpha_col_name]

        # 输出变换后的有量纲力和力矩
        output_df["Fx_new"] = results["force_transformed"][:, 0]
        output_df["Fy_new"] = results["force_transformed"][:, 1]
        output_df["Fz_new"] = results["force_transformed"][:, 2]
        output_df["Mx_new"] = results["moment_transformed"][:, 0]
        output_df["My_new"] = results["moment_transformed"][:, 1]
        output_df["Mz_new"] = results["moment_transformed"][:, 2]
        
        # 输出变换后的无量纲系数
        output_df["Cx"] = results["coeff_force"][:, 0]
        output_df["Cy"] = results["coeff_force"][:, 1]
        output_df["Cz"] = results["coeff_force"][:, 2]
        output_df["Cl"] = results["coeff_moment"][:, 0]
        output_df["Cm"] = results["coeff_moment"][:, 1]
        output_df["Cn"] = results["coeff_moment"][:, 2]

        # 生成更高分辨率且具唯一性的文件名，减少同名冲突
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        unique = uuid.uuid4().hex[:8]
        output_file = self.output_dir / f"{file_path.stem}_result_{timestamp}_{unique}.csv"

        # 确保输出目录存在
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception:
            pass

        # 使用临时文件写入并通过原子替换完成最终写入（跨进程/线程更安全）
        tmp_name = f".{output_file.name}.{uuid.uuid4().hex}.tmp"
        tmp_path = output_file.parent / tmp_name
        try:
            # 若系统临时文件生成失败，直接 fallback 到常规写入
            output_df.to_csv(tmp_path, index=False)
            os.replace(tmp_path, output_file)
        except Exception:
            # 清理临时文件（若存在）并降级为直接写入
            try:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            output_df.to_csv(output_file, index=False)

        return output_file

    def request_stop(self):
        """请求停止后台线程的处理"""
        self._stop_requested = True
        # 如果外部提供了可取消的计算器接口，尝试调用它以尽快中断正在进行的计算
        try:
            calc = getattr(self, "calculator", None)
            if calc is not None:
                # 常见取消方法名：cancel, request_stop, stop, shutdown
                for name in ("cancel", "request_stop", "stop", "shutdown"):
                    fn = getattr(calc, name, None)
                    if callable(fn):
                        try:
                            fn()
                        except Exception:
                            logger.debug("调用计算器取消接口 %s 失败", name, exc_info=True)
        except Exception:
            logger.debug("请求停止时尝试取消计算器失败", exc_info=True)

    def run(self):
        try:
            total = len(self.file_list)
            success = 0
            elapsed_list = []

            for i, file_path in enumerate(self.file_list):
                if self._stop_requested:
                    try:
                        self.log_message.emit("用户取消：正在停止批处理")
                    except Exception:
                        logger.debug("Cannot emit cancel log message", exc_info=True)
                    break

                file_start = datetime.now()
                try:
                    self.log_message.emit(f"处理 [{i+1}/{total}]: {file_path.name}")
                except Exception:
                    logger.debug("无法发出开始处理消息: %s", file_path, exc_info=True)

                try:
                    output_file = self.process_file(file_path)
                    file_elapsed = (datetime.now() - file_start).total_seconds()
                    elapsed_list.append(file_elapsed)
                    avg = sum(elapsed_list) / len(elapsed_list)
                    remaining = total - (i + 1)
                    eta = int(avg * remaining)

                    # 兼容特殊格式返回多个输出文件的情况
                    success_flag = False
                    if isinstance(output_file, list):
                        if len(output_file) > 0:
                            out_names = ", ".join([p.name for p in output_file])
                            success_msg = (
                                f"生成 {len(output_file)} 个 part 输出: {out_names}"
                            )
                            success_flag = True
                        else:
                            success_msg = "未生成任何 part 输出"
                    else:
                        out_names = getattr(output_file, "name", None)
                        if out_names:
                            success_msg = out_names
                            success_flag = True
                        else:
                            success_msg = "未生成输出文件"

                    try:
                        if success_flag:
                            self.log_message.emit(
                                f"  ✓ 完成: {success_msg} (耗时: {file_elapsed:.2f}s)"
                            )
                        else:
                            self.log_message.emit(
                                f"  ✗ 处理结果：{success_msg} (耗时: {file_elapsed:.2f}s)"
                            )
                    except Exception:
                        logger.debug(
                            "Cannot emit success/failure message for %s",
                            file_path,
                            exc_info=True,
                        )

                    try:
                        self.log_message.emit(
                            f"已完成 {i+1}/{total}，平均每文件耗时 {avg:.2f}s，预计剩余 {eta}s"
                        )
                    except Exception:
                        logger.debug("无法发出 ETA 消息", exc_info=True)

                    if success_flag:
                        success += 1

                except (ValueError, IndexError, OSError) as e:
                    file_elapsed = (datetime.now() - file_start).total_seconds()
                    elapsed_list.append(file_elapsed)
                    logger.debug(
                        "File processing failed for %s: %s",
                        file_path,
                        e,
                        exc_info=True,
                    )
                    try:
                        self.log_message.emit(
                            f"  ✗ 失败: {e} (耗时: {file_elapsed:.2f}s)"
                        )
                    except Exception:
                        logger.debug(
                            "Cannot emit failure message for %s: %s",
                            file_path,
                            e,
                            exc_info=True,
                        )

                except Exception:
                    file_elapsed = (datetime.now() - file_start).total_seconds()
                    elapsed_list.append(file_elapsed)
                    logger.exception("Unexpected error processing file %s", file_path)
                    try:
                        self.log_message.emit(
                            f"  ✗ 未知错误 (耗时: {file_elapsed:.2f}s)"
                        )
                    except Exception:
                        logger.debug(
                            "Cannot emit unknown error message for %s",
                            file_path,
                            exc_info=True,
                        )

                try:
                    pct = int((i + 1) / total * 100)
                    self.progress.emit(pct)
                except Exception:
                    logger.debug(
                        "Unable to emit progress value for %s",
                        file_path,
                        exc_info=True,
                    )

            total_elapsed = sum(elapsed_list)
            try:
                # 只有在实际处理了文件时才报告成功
                if success > 0:
                    msg = (
                        f"成功处理 {success}/{total} 个文件，耗时 {total_elapsed:.2f}s"
                    )
                elif total == 0:
                    msg = "没有文件需要处理"
                else:
                    msg = f"未成功处理任何文件 (0/{total})，耗时 {total_elapsed:.2f}s"

                if self._stop_requested:
                    msg = f"已取消：已处理 {success}/{total} 个文件，耗时 {total_elapsed:.2f}s"

                self.finished.emit(msg)
            except Exception:
                logger.debug("Cannot emit finished signal", exc_info=True)

        except Exception as e:
            logger.exception("BatchProcessThread.run 出现未处理异常")
            try:
                self.error.emit(str(e))
            except Exception:
                logger.debug("Cannot emit error signal", exc_info=True)
        finally:
            # 最终清理：若线程被请求停止但未发送 finished 信号，尝试发送一个通用消息
            try:
                if self._stop_requested:
                    try:
                        self.log_message.emit("批处理线程已停止（请求中止）")
                    except Exception:
                        logger.debug("无法发出停止日志消息", exc_info=True)
            except Exception:
                pass
