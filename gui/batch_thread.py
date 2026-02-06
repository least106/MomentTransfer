"""
批处理线程模块

Part 选择优先级规则（关键）：
====================================
对于普通格式文件（CSV/Excel），批处理采用以下优先级选择 Source/Target Part：

1. 优先级1（最高）：文件树中的 Part 选择（file_part_selection_by_file）
   - 用户在 GUI 文件树中为该文件的"选择 Source Part"和"选择 Target Part"下拉框选择
   - 若该文件有此选择，则**必须使用**此选择，不可被其他配置覆盖
   - 代表用户对该文件的**明确意图**

2. 优先级2（中）：配置编辑器的全局 Part 选择（src_partname / tgt_partname）
   - ConfigPanel 中当前激活的 Source/Target Part
   - **仅当**该文件未在树中设置明确选择时，才使用此作为后备
   - 不推荐依赖此方式（已过时的设计）

3. 优先级3（最低）：自动唯一推断
   - 若配置中 Source/Target Part 只有1个，自动使用该Part
   - 若有多个则必须明确指定

对于特殊格式文件（.mtfmt/.mtdata），规则类似，但优先级为：
1. special_part_mapping_by_file（文件树中的 Part 映射）
2. 自动推断

违反此优先级的代码将被视为 bug 并修复！
"""

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QThread, Signal

from src.special_format_detector import looks_like_special_format
from src.special_format_parser import process_special_format_file

logger = logging.getLogger(__name__)


@dataclass
class ProcessInputs:
    """封装传入 _compute_and_write_output 的相关输入以减少参数个数。"""

    forces_df: pd.DataFrame
    moments_df: pd.DataFrame
    has_dimensional: bool
    original_df: pd.DataFrame
    alpha_col_name: str
    file_path: Path


@dataclass
class BatchThreadConfig:
    project_data: object = None
    timestamp_format: str = "%Y%m%d_%H%M%S"
    special_part_mapping_by_file: dict = None
    special_row_selection_by_file: dict = None
    file_part_selection_by_file: dict = None
    table_row_selection_by_file: dict = None


class BatchProcessThread(QThread):
    """在后台线程中执行批量处理"""

    progress = Signal(int)
    progress_detail = Signal(int, str)  # (百分比, 详细信息文本)
    log_message = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        calculator,
        file_list,
        output_dir,
        data_config,
        config: BatchThreadConfig = None,
        project_data=None,
        timestamp_format: str = "%Y%m%d_%H%M%S",
        special_part_mapping_by_file: dict = None,
        special_row_selection_by_file: dict = None,
        file_part_selection_by_file: dict = None,
        table_row_selection_by_file: dict = None,
    ):  # pylint: disable=too-many-arguments
        super().__init__()
        self.calculator = calculator
        self.file_list = file_list
        self.output_dir = Path(output_dir)
        self.data_config = data_config
        self._stop_requested = False
        # 配置对象优先；为兼容旧调用，合并提供的参数
        if config is None:
            config = BatchThreadConfig(
                project_data=project_data,
                timestamp_format=timestamp_format,
                special_part_mapping_by_file=special_part_mapping_by_file or {},
                special_row_selection_by_file=special_row_selection_by_file or {},
                file_part_selection_by_file=file_part_selection_by_file or {},
                table_row_selection_by_file=table_row_selection_by_file or {},
            )

        self.config = config

        # 全局批处理格式默认值（已不再提供 GUI 入口配置）；但保留作为 per-file 解析的 base。
        try:
            # 延迟导入以避免循环依赖
            # pylint: disable=import-outside-toplevel
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
        # 内部 helper 已提升为实例方法。
        # 包括: _emit_log/_emit_progress/_emit_finished
        # 以及 _handle_special_report 和 _atomic_write

    def _resolve_cfg_for_file(self, file_path: Path):
        """为单个文件返回全局批处理配置。"""
        # 延迟导入以避免循环依赖
        # pylint: disable=import-outside-toplevel
        from src.cli_helpers import BatchConfig, resolve_file_format

        base = (
            self._global_batch_cfg
            if self._global_batch_cfg is not None
            else BatchConfig()
        )
        return resolve_file_format(str(file_path), base)

    def _emit_log(self, msg: str) -> None:
        """安全发送日志 signal（捕获异常避免重复 try/except 代码）。"""
        try:
            # 在某些测试场景下，signals 可能被替换为简单可调用对象
            emit = getattr(self.log_message, "emit", None)
            if callable(emit):
                emit(msg)
            else:
                # 兼容直接把 log_message 设为可调用对象
                if callable(self.log_message):
                    self.log_message(msg)
        except Exception:
            logger.debug("无法发送日志消息: %s", msg, exc_info=True)

    def _emit_progress(self, pct: int) -> None:
        """安全发送进度 signal。"""
        try:
            emit = getattr(self.progress, "emit", None)
            if callable(emit):
                emit(pct)
            else:
                if callable(self.progress):
                    self.progress(pct)
        except Exception:
            logger.debug("无法发送进度消息: %s", pct, exc_info=True)

    def _emit_progress_detail(self, pct: int, detail_msg: str) -> None:
        """安全发送详细进度 signal。"""
        try:
            emit = getattr(self.progress_detail, "emit", None)
            if callable(emit):
                emit(pct, detail_msg)
            else:
                if callable(self.progress_detail):
                    self.progress_detail(pct, detail_msg)
        except Exception:
            logger.debug("无法发送详细进度消息: %s", detail_msg, exc_info=True)

    def _emit_finished(self, msg: str) -> None:
        """安全发送 finished signal。"""
        try:
            emit = getattr(self.finished, "emit", None)
            if callable(emit):
                emit(msg)
            else:
                if callable(self.finished):
                    self.finished(msg)
        except Exception:
            logger.debug("无法发送 finished 消息: %s", msg, exc_info=True)

    def _handle_special_report(self, report) -> None:
        """将特殊格式解析报告转换为日志消息并发送（集中处理）。"""
        try:
            for r in report:
                status = r.get("status")
                part = r.get("part")
                if status == "success":
                    msg = (
                        "part '"
                        + str(part)
                        + "' 处理成功，输出: "
                        + str(r.get("out_path", ""))
                    )
                elif status == "skipped":
                    reason = r.get("reason")
                    msg = (
                        "part '"
                        + str(part)
                        + "' 被跳过: "
                        + str(reason)
                        + " - "
                        + str(r.get("message", ""))
                    )
                else:
                    msg = (
                        "part '"
                        + str(part)
                        + "' 处理失败: "
                        + str(r.get("reason"))
                        + " - "
                        + str(r.get("message", ""))
                    )
                self._emit_log(msg)
        except Exception:
            logger.debug("处理 special format report 时发生错误", exc_info=True)

    def _atomic_write(self, output_df: pd.DataFrame, output_file: Path) -> None:
        """原子写入 DataFrame 到 csv：先写临时文件，再 replace。"""
        tmp_name = f".{output_file.name}.{uuid.uuid4().hex}.tmp"
        tmp_path = output_file.parent / tmp_name
        try:
            output_df.to_csv(tmp_path, index=False)
            os.replace(tmp_path, output_file)
        except Exception:
            try:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            output_df.to_csv(output_file, index=False)

    def _process_special_format_branch(self, file_path: Path):
        """处理特殊格式文件的分支逻辑，成功返回 outputs 列表或其他 truthy 值，否则返回 None。"""
        if self.config.project_data is None or not looks_like_special_format(file_path):
            return None

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
            part_mapping = (self.config.special_part_mapping_by_file or {}).get(
                str(Path(file_path))
            )
        except Exception:
            part_mapping = None

        # 解析part_mapping，从新的格式{"internal_part": {"source": "...", "target": "..."}}
        # 提取出part_source_mapping和part_target_mapping
        part_source_mapping = {}
        part_target_mapping = {}
        if isinstance(part_mapping, dict):
            for internal_part, mapping_data in part_mapping.items():
                if isinstance(mapping_data, dict):
                    source_val = mapping_data.get("source", "").strip()
                    target_val = mapping_data.get("target", "").strip()
                    if source_val:
                        part_source_mapping[internal_part] = source_val
                    if target_val:
                        part_target_mapping[internal_part] = target_val
                elif isinstance(mapping_data, str):
                    # 兼容旧格式：internal_part -> target_part
                    target_val = mapping_data.strip()
                    if target_val:
                        part_target_mapping[internal_part] = target_val

        row_selection = None
        try:
            row_selection = (self.config.special_row_selection_by_file or {}).get(
                str(Path(file_path))
            )
        except Exception:
            row_selection = None

        # 在调用可能耗时的特殊格式解析前检查停止请求
        if self._stop_requested:
            raise RuntimeError("处理已被请求停止")

        outputs, report = process_special_format_file(
            Path(file_path),
            self.config.project_data,
            self.output_dir,
            part_target_mapping=part_target_mapping,
            part_source_mapping=part_source_mapping,
            part_row_selection=row_selection,
            timestamp_format=self.config.timestamp_format,
            overwrite=overwrite_flag,
            return_report=True,
        )

        # 将详细报告转换为 GUI 日志消息，按 part 显示成功/跳过/失败原因
        self._handle_special_report(report)

        # 如果特殊格式解析既没有产出 outputs 也没有 report，回退为常规处理
        if not outputs and not report:
            logger.debug(
                "special_format 解析未提取到任何 part，回退到常规 CSV/Excel 处理: %s",
                file_path,
            )
            msg = "特殊格式解析未提取到 part，回退为常规表格处理: " f"{file_path.name}"
            self._emit_log(msg)
            return None

        return outputs

    def process_file(self, file_path):
        """处理单个文件并返回输出路径"""
        if self._stop_requested:
            raise RuntimeError("处理已被请求停止")
        # 特殊格式分支：解析多 part 并按 target part 输出
        out = self._process_special_format_branch(file_path)
        if out is not None:
            return out

        try:
            if self._stop_requested:
                raise RuntimeError("处理已被请求停止")

            cfg_to_use = self._resolve_cfg_for_file(Path(file_path))
        except Exception as e:
            msg = f"为文件 {Path(file_path).name} 解析 per-file 格式失败: {e}"
            self._emit_log(msg)
            raise

        # 读取输入为 DataFrame（CSV/Excel）
        df = self._read_input_dataframe(file_path, cfg_to_use)

        # 读取后检查是否需要停止
        if self._stop_requested:
            raise RuntimeError("处理已被请求停止")
        # 应用用户在 GUI 中按文件选择的行过滤（若有）
        df = self._apply_table_row_selection(file_path, df)

        # 提取列、构造 inputs 并创建 per-file 计算器（如果需要）
        inputs, calc_to_use = self._prepare_inputs_and_calc(file_path, df)

        # 执行计算并写出，返回输出文件路径
        output = self._compute_and_write_output(calc_to_use, inputs)
        return output

    def _prepare_inputs_and_calc(self, file_path, df: pd.DataFrame):
        """为给定文件和 DataFrame 构建 ProcessInputs 并返回 (inputs, calc_to_use)。"""
        (
            _col_map,
            has_dimensional,
            has_coeff,
            forces_df,
            moments_df,
            alpha_col_name,
        ) = self._extract_columns_and_dfs(df, file_path)

        calc_to_use = self._create_calc_to_use(file_path)

        file_path_obj = Path(file_path)
        inputs = ProcessInputs(
            forces_df=forces_df,
            moments_df=moments_df,
            has_dimensional=has_dimensional,
            original_df=df,
            alpha_col_name=alpha_col_name,
            file_path=file_path_obj,
        )
        return inputs, calc_to_use

    def _extract_columns_and_dfs(self, df: pd.DataFrame, file_path: Path):
        """从输入 DataFrame 提取列映射并构造 force/moment DataFrame。

        返回: (col_map, has_dimensional, has_coeff, forces_df, moments_df, alpha_col_name)
        """
        try:
            (
                col_map,
                has_dimensional,
                coeff_normal_key,
                has_coeff,
            ) = self._build_col_map(df)

            if not has_dimensional and not has_coeff:
                raise ValueError(
                    "缺少必要列，需包含 Fx/Fy/Fz/Mx/My/Mz 或 "
                    "Cx/Cy/Cz(CM)/CMx/CMy/CMz"
                )

            if has_dimensional:
                forces_df = df[[col_map["fx"], col_map["fy"], col_map["fz"]]].apply(
                    pd.to_numeric, errors="coerce"
                )
                moments_df = df[[col_map["mx"], col_map["my"], col_map["mz"]]].apply(
                    pd.to_numeric, errors="coerce"
                )
            else:
                # 保持为无量纲系数，后续在计算器上下文中转换为有量纲
                forces_df = df[
                    [col_map["cx"], col_map["cy"], col_map[coeff_normal_key]]
                ].apply(pd.to_numeric, errors="coerce")
                moments_df = df[[col_map["cmx"], col_map["cmy"], col_map["cmz"]]].apply(
                    pd.to_numeric, errors="coerce"
                )

            alpha_col_name = col_map.get("alpha")
            return (
                col_map,
                has_dimensional,
                has_coeff,
                forces_df,
                moments_df,
                alpha_col_name,
            )

        except Exception as e:
            try:
                self._emit_log(f"数据列提取或转换失败: {e}")
            except Exception:
                logger.debug("无法通过 signal 发送失败消息: %s", e, exc_info=True)
            raise

    def _build_col_map(self, df: pd.DataFrame):
        """构建列小写映射并判断是否为有量纲或系数格式。"""
        col_map = {str(c).strip().lower(): c for c in df.columns}

        has_dimensional = all(
            k in col_map for k in ["fx", "fy", "fz", "mx", "my", "mz"]
        )
        coeff_normal_key = (
            "cz" if "cz" in col_map else "fn" if "fn" in col_map else None
        )
        has_coeff = coeff_normal_key is not None and all(
            k in col_map for k in ["cx", "cy", "cmx", "cmy", "cmz"]
        )

        return col_map, has_dimensional, coeff_normal_key, has_coeff

    def _create_calc_to_use(self, file_path: Path):
        """为单个文件创建或选择计算器（支持 project_data 的 per-file 选择）。

        Part 选择优先级（遵循模块文档）：
        1. 优先级1：文件树中的 Part 选择（file_part_selection_by_file）
           - 用户在 GUI 文件树中明确为该文件设置的 Source/Target Part
           - 此为**最优先**的选择，代表用户的明确意图
        2. 优先级2：配置中的唯一 Part 推断
           - 若配置中只有1个 Source/Target Part，自动使用
           - 这种情况下无需用户手工选择
        3. 优先级3：其他情况则报错，要求用户明确指定
           - 配置中有多个 Part 但用户未在树中选择：不允许运行
        """
        calc_to_use = self.calculator
        if self.config.project_data is None:
            return calc_to_use

        try:
            # 延迟导入以避免循环依赖
            # pylint: disable=import-outside-toplevel
            from src.physics import AeroCalculator

            fp_str = str(Path(file_path))
            # 优先级1：获取文件树中用户明确设置的 Part 选择
            sel = (self.config.file_part_selection_by_file or {}).get(fp_str) or {}
            source_sel = (sel.get("source") or "").strip()
            target_sel = (sel.get("target") or "").strip()

            # 尝试唯一推断
            try:
                source_names = list(
                    (getattr(self.config.project_data, "source_parts", {}) or {}).keys()
                )
            except Exception:
                source_names = []
            try:
                target_names = list(
                    (getattr(self.config.project_data, "target_parts", {}) or {}).keys()
                )
            except Exception:
                target_names = []

            # 优先级2：如果树中无明确选择，尝试唯一推断
            if not source_sel and len(source_names) == 1:
                source_sel = str(source_names[0])
                logger.debug(
                    "文件 %s 无树中选择，使用唯一推断的 Source Part: %s",
                    Path(file_path).name,
                    source_sel,
                )
            if not target_sel and len(target_names) == 1:
                target_sel = str(target_names[0])
                logger.debug(
                    "文件 %s 无树中选择，使用唯一推断的 Target Part: %s",
                    Path(file_path).name,
                    target_sel,
                )

            # 优先级3：无法推断则报错
            if not source_sel or not target_sel:
                raise ValueError(
                    f"文件 {Path(file_path).name} 未选择 Source/Target Part。"
                    f"请在文件树中明确指定，或确保配置中仅有1个 Source/Target Part"
                    f"（当前 {len(source_names)} 个 Source，{len(target_names)} 个 Target）"
                )

            return AeroCalculator(
                self.config.project_data,
                source_part=source_sel,
                target_part=target_sel,
            )
        except Exception as e:
            try:
                msg = f"为文件 {Path(file_path).name} 创建 per-file 计算器失败: {e}"
                self._emit_log(msg)
            except Exception:
                logger.debug("无法发送 per-file 计算器失败日志", exc_info=True)
            raise

    def _prepare_dimensional_arrays(
        self,
        calc_to_use,
        forces_df: pd.DataFrame,
        moments_df: pd.DataFrame,
        has_dimensional: bool,
    ):
        """将输入的 DataFrame 转为有量纲的 numpy 数组（forces_dimensional, moments_dimensional）。"""
        if has_dimensional:
            return (
                forces_df.to_numpy(dtype=float),
                moments_df.to_numpy(dtype=float),
            )

        try:
            q = calc_to_use.target_frame.q
            s_ref = calc_to_use.target_frame.s_ref
            c_ref = calc_to_use.target_frame.c_ref
            b_ref = calc_to_use.target_frame.b_ref
        except Exception as e:
            raise ValueError(f"无法从计算器获取参考值: {e}") from e

        forces_dimensional = forces_df.to_numpy(dtype=float) * (q * s_ref)
        cm = moments_df.to_numpy(dtype=float)
        moments_dimensional = pd.DataFrame(
            {
                "mx": cm[:, 0] * (q * s_ref * b_ref),
                "my": cm[:, 1] * (q * s_ref * c_ref),
                "mz": cm[:, 2] * (q * s_ref * b_ref),
            }
        ).to_numpy(dtype=float)

        return forces_dimensional, moments_dimensional

    def _build_output_dataframe(
        self, results, original_df: pd.DataFrame, alpha_col_name: str
    ) -> pd.DataFrame:
        """根据计算结果构建输出的 DataFrame（含 Alpha、力/力矩和系数列）。"""
        out = pd.DataFrame()
        if alpha_col_name and alpha_col_name in original_df.columns:
            out["Alpha"] = original_df[alpha_col_name]

        out["Fx_new"] = results["force_transformed"][:, 0]
        out["Fy_new"] = results["force_transformed"][:, 1]
        out["Fz_new"] = results["force_transformed"][:, 2]
        out["Mx_new"] = results["moment_transformed"][:, 0]
        out["My_new"] = results["moment_transformed"][:, 1]
        out["Mz_new"] = results["moment_transformed"][:, 2]

        out["Cx"] = results["coeff_force"][:, 0]
        out["Cy"] = results["coeff_force"][:, 1]
        out["Cz"] = results["coeff_force"][:, 2]
        out["Cl"] = results["coeff_moment"][:, 0]
        out["Cm"] = results["coeff_moment"][:, 1]
        out["Cn"] = results["coeff_moment"][:, 2]

        return out

    def _format_output_summary(self, output_file):
        """根据 process_file 的返回值（Path 或 list）生成 (success_flag, success_msg)。"""
        if isinstance(output_file, list):
            if len(output_file) > 0:
                out_names = ", ".join([p.name for p in output_file])
                return (
                    True,
                    f"生成 {len(output_file)} 个 part 输出: {out_names}",
                )
            return False, "未生成任何 part 输出"

        out_names = getattr(output_file, "name", None)
        if out_names:
            return True, out_names
        return False, "未生成输出文件"

    def _apply_table_row_selection(
        self, file_path: Path, df: pd.DataFrame
    ) -> pd.DataFrame:
        """如果用户为文件指定了行选择，则按选择过滤并返回新的 DataFrame。"""
        try:
            fp_str = str(Path(file_path))
            sel = (self.config.table_row_selection_by_file or {}).get(fp_str)
            if sel is not None:
                sel_sorted = sorted(int(x) for x in set(sel))
                return df.iloc[sel_sorted].reset_index(drop=True)
            return df
        except Exception as e:
            try:
                self.log_message.emit(
                    f"按行选择过滤失败: {Path(file_path).name} -> {e}"
                )
            except Exception:
                pass
            raise

    def _compute_and_write_output(self, calc_to_use, inputs: ProcessInputs) -> Path:
        """将输入转为有量纲数组，调用计算器批量计算并把结果写出为 CSV（原子写入）。"""
        forces_dimensional, moments_dimensional = self._prepare_dimensional_arrays(
            calc_to_use,
            inputs.forces_df,
            inputs.moments_df,
            inputs.has_dimensional,
        )

        # 在调用可能耗时的批量计算前检查停止请求
        if self._stop_requested:
            raise RuntimeError("处理已被请求停止")

        results = calc_to_use.process_batch(forces_dimensional, moments_dimensional)

        output_df = self._build_output_dataframe(
            results, inputs.original_df, inputs.alpha_col_name
        )

        # 生成更高分辨率且具唯一性的文件名，减少同名冲突
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        unique = uuid.uuid4().hex[:8]
        filename = f"{inputs.file_path.stem}_result_{timestamp}_{unique}.csv"
        output_file = self.output_dir / filename

        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception:
            pass

        # 原子写入
        self._atomic_write(output_df, output_file)

        return output_file

    def _process_single_file(self, i: int, file_path: Path, total: int):
        """处理单个文件并返回 (success_flag, output_file, file_elapsed, success_msg)。"""
        file_start = datetime.now()
        try:
            try:
                self.log_message.emit(f"处理 [{i+1}/{total}]: {file_path.name}")
            except Exception:
                logger.debug("无法发出开始处理消息: %s", file_path, exc_info=True)

            output_file = self.process_file(file_path)
            file_elapsed = (datetime.now() - file_start).total_seconds()

            # 兼容特殊格式返回多个输出文件的情况，并生成 summary
            success_flag, success_msg = self._format_output_summary(output_file)
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

            return success_flag, output_file, file_elapsed, success_msg

        except (ValueError, IndexError, OSError) as e:
            file_elapsed = (datetime.now() - file_start).total_seconds()
            try:
                self.log_message.emit(f"  ✗ 失败: {e} (耗时: {file_elapsed:.2f}s)")
            except Exception:
                logger.debug(
                    "Cannot emit failure message for %s: %s",
                    file_path,
                    e,
                    exc_info=True,
                )
            return False, None, file_elapsed, str(e)

        except Exception:
            file_elapsed = (datetime.now() - file_start).total_seconds()
            logger.exception("Unexpected error processing file %s", file_path)
            try:
                self.log_message.emit(f"  ✗ 未知错误 (耗时: {file_elapsed:.2f}s)")
            except Exception:
                logger.debug(
                    "Cannot emit unknown error message for %s",
                    file_path,
                    exc_info=True,
                )
            return False, None, file_elapsed, "未知错误"

    def _read_input_dataframe(self, file_path: Path, cfg_to_use):
        """读取输入文件为 DataFrame（CSV 或 Excel），并发送日志。"""
        from gui.progress_config import BATCH_LARGE_FILE_ROW_THRESHOLD
        
        try:
            if file_path.suffix.lower() == ".csv":
                df = pd.read_csv(
                    file_path,
                    skiprows=int(getattr(cfg_to_use, "skip_rows", 0)),
                )
                logger.debug("CSV 读取完成: %s 行, %s 列", df.shape[0], df.shape[1])
                row_count = df.shape[0]
                self._emit_log(
                    f"已读取文件 {file_path.name}: {row_count} 行, {df.shape[1]} 列"
                )
                # 大文件提示：根据配置的阈值显示详细信息
                if row_count > BATCH_LARGE_FILE_ROW_THRESHOLD:
                    self._emit_log(
                        f"  文件较大（{row_count} 行），处理可能需要较长时间..."
                    )
            else:
                df = pd.read_excel(
                    file_path,
                    skiprows=int(getattr(cfg_to_use, "skip_rows", 0)),
                )
                row_count = df.shape[0]
                self._emit_log(
                    f"已读取文件 {file_path.name}: {row_count} 行, {df.shape[1]} 列"
                )
                if row_count > BATCH_LARGE_FILE_ROW_THRESHOLD:
                    self._emit_log(
                        f"  文件较大（{row_count} 行），处理可能需要较长时间..."
                    )
            return df
        except Exception as e:
            self._emit_log(f"读取文件失败: {file_path.name} -> {e}")
            raise

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
                            logger.debug(
                                "调用计算器取消接口 %s 失败",
                                name,
                                exc_info=True,
                            )
        except Exception:
            logger.debug("请求停止时尝试取消计算器失败", exc_info=True)

    def _emit_eta(self, completed: int, total: int, elapsed_list: list) -> None:
        """计算并发送 ETA/平均耗时消息。"""
        if not elapsed_list:
            return
        avg = sum(elapsed_list) / len(elapsed_list)
        remaining = total - completed
        eta = int(avg * remaining)
        try:
            self.log_message.emit(
                f"已完成 {completed}/{total}，平均每文件耗时 {avg:.2f}s，预计剩余 {eta}s"
            )
        except Exception:
            logger.debug("无法发出 ETA 消息", exc_info=True)

    def _build_progress_detail(
        self,
        completed: int,
        total: int,
        elapsed_list: list,
        current_file_name: str = None,
    ) -> str:
        """构建详细的进度信息文本。

        Args:
            completed: 已完成的文件数
            total: 总文件数
            elapsed_list: 各文件耗时列表

        Returns:
            详细进度信息字符串，例如："15/100 文件 | 平均 2.5s/文件 | 预计剩余 3分25秒"
        """
        if not elapsed_list:
            if current_file_name:
                return f"{completed}/{total} 文件 | 当前: {current_file_name}"
            return f"{completed}/{total} 文件"

        avg = sum(elapsed_list) / len(elapsed_list)
        remaining = total - completed
        eta_seconds = int(avg * remaining)

        # 格式化预计剩余时间
        if eta_seconds < 60:
            eta_str = f"{eta_seconds}秒"
        elif eta_seconds < 3600:
            minutes = eta_seconds // 60
            seconds = eta_seconds % 60
            eta_str = f"{minutes}分{seconds}秒"
        else:
            hours = eta_seconds // 3600
            minutes = (eta_seconds % 3600) // 60
            eta_str = f"{hours}小时{minutes}分"

        file_info = f" | 当前: {current_file_name}" if current_file_name else ""
        return (
            f"{completed}/{total} 文件{file_info} | "
            f"平均 {avg:.1f}s/文件 | "
            f"预计剩余 {eta_str}"
        )

    def _finalize_run(self, success: int, total: int, elapsed_list: list) -> None:
        """发送运行完成的汇总消息（成功/取消/无文件等）。"""
        total_elapsed = sum(elapsed_list)
        if success > 0:
            msg = f"成功处理 {success}/{total} 个文件，耗时 {total_elapsed:.2f}s"
        elif total == 0:
            msg = "没有文件需要处理"
        else:
            msg = f"未成功处理任何文件 (0/{total})，耗时 {total_elapsed:.2f}s"

        if self._stop_requested:
            msg = f"已取消：已处理 {success}/{total} 个文件，耗时 {total_elapsed:.2f}s"

        try:
            self.finished.emit(msg)
        except Exception:
            logger.debug("Cannot emit finished signal", exc_info=True)

    def _run_main_loop(self):
        """主循环：遍历文件列表，调用单文件处理并更新进度。返回 (success_count, elapsed_list)。"""
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
                pct_start = int((i / total) * 100) if total else 0
                start_msg = f"正在处理 {i+1}/{total}: {file_path.name}"
                self._emit_progress_detail(pct_start, start_msg)
            except Exception:
                logger.debug("无法发送开始处理进度信息", exc_info=True)

            try:
                res = self._process_single_file(i, file_path, total)
                success_flag, output_file, file_elapsed, success_msg = res
                elapsed_list.append(file_elapsed)
                try:
                    self._emit_eta(i + 1, total, elapsed_list)
                except Exception:
                    logger.debug("无法发出 ETA 消息", exc_info=True)

                if success_flag:
                    success += 1
            except Exception:
                # 保护性捕获：理论上 _process_single_file 会自行处理异常
                file_elapsed = (datetime.now() - file_start).total_seconds()
                elapsed_list.append(file_elapsed)
                logger.exception("Unexpected error processing file %s", file_path)
                try:
                    self.log_message.emit(f"  ✗ 未知错误 (耗时: {file_elapsed:.2f}s)")
                except Exception:
                    logger.debug(
                        "Cannot emit unknown error message for %s",
                        file_path,
                        exc_info=True,
                    )

            try:
                pct = int((i + 1) / total * 100)
                self.progress.emit(pct)

                # 发送详细进度信息
                try:
                    detail_msg = self._build_progress_detail(
                        i + 1,
                        total,
                        elapsed_list,
                        current_file_name=file_path.name,
                    )
                    self._emit_progress_detail(pct, detail_msg)
                except Exception:
                    logger.debug("无法发送详细进度信息", exc_info=True)
            except Exception:
                logger.debug(
                    "Unable to emit progress value for %s",
                    file_path,
                    exc_info=True,
                )

        return success, elapsed_list

    def run(self):
        try:
            success, elapsed_list = self._run_main_loop()
            try:
                self._finalize_run(success, len(self.file_list), elapsed_list)
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
