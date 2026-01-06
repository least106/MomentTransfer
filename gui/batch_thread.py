"""
批处理线程模块
"""
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from src.special_format_parser import looks_like_special_format, process_special_format_file

logger = logging.getLogger(__name__)


class BatchProcessThread(QThread):
    """在后台线程中执行批量处理"""
    progress = Signal(int)
    log_message = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, calculator, file_list, output_dir, data_config, registry_db=None, project_data=None, timestamp_format: str = "%Y%m%d_%H%M%S"):
        super().__init__()
        self.calculator = calculator
        self.file_list = file_list
        self.output_dir = Path(output_dir)
        self.data_config = data_config
        self.registry_db = registry_db
        self._stop_requested = False
        self.project_data = project_data
        self.timestamp_format = timestamp_format

    def process_file(self, file_path):
        """处理单个文件并返回输出路径"""
        # 特殊格式分支：解析多 part 并按 target part 输出
        if self.project_data is not None and looks_like_special_format(file_path):
            overwrite_flag = False
            try:
                if isinstance(self.data_config, dict):
                    overwrite_flag = bool(self.data_config.get('overwrite', False))
                else:
                    overwrite_flag = bool(getattr(self.data_config, 'overwrite', False))
            except Exception:
                overwrite_flag = False

            outputs = process_special_format_file(
                Path(file_path),
                self.project_data,
                self.output_dir,
                timestamp_format=self.timestamp_format,
                overwrite=overwrite_flag,
            )
            return outputs

        cfg_to_use = self.data_config
        if getattr(self, 'enable_sidecar', False):
            try:
                from src.cli_helpers import resolve_file_format, BatchConfig as _BatchConfig
                base_cfg = _BatchConfig()
                if isinstance(self.data_config, dict):
                    base_cfg.skip_rows = int(self.data_config.get('skip_rows', base_cfg.skip_rows))
                    cols = self.data_config.get('columns') or {}
                    for k in base_cfg.column_mappings.keys():
                        if k in cols and cols.get(k) is not None:
                            base_cfg.column_mappings[k] = int(cols.get(k))
                    base_cfg.passthrough_columns = [int(x) for x in self.data_config.get('passthrough', base_cfg.passthrough_columns)]
                    if 'chunksize' in self.data_config:
                        try:
                            base_cfg.chunksize = int(self.data_config.get('chunksize'))
                        except Exception:
                            base_cfg.chunksize = None
                    if 'sample_rows' in self.data_config:
                        try:
                            base_cfg.sample_rows = int(self.data_config.get('sample_rows'))
                        except Exception:
                            base_cfg.sample_rows = base_cfg.sample_rows
                else:
                    base_cfg = self.data_config

                cfg_to_use = resolve_file_format(str(file_path), base_cfg, enable_sidecar=True, registry_db=self.registry_db)
            except Exception as e:
                self.log_message.emit(f"为文件 {file_path.name} 解析 per-file 配置失败: {e}")
                raise

        if file_path.suffix.lower() == '.csv':
            df = pd.read_csv(file_path, header=None, skiprows=cfg_to_use.get('skip_rows', 0))
        else:
            df = pd.read_excel(file_path, header=None, skiprows=cfg_to_use.get('skip_rows', 0))

        cols = cfg_to_use.get('columns', {})

        # 自动检测并跳过可能的表头行：
        # 如果在映射的关键力/力矩列中多数值在第一行无法解析为数值，判断第一行为表头并丢弃。
        try:
            required_keys = ['fx', 'fy', 'fz', 'mx', 'my', 'mz']
            mapped = [cols.get(k) for k in required_keys if cols.get(k) is not None]
            mapped = [int(x) for x in mapped if isinstance(x, (int, float)) or (isinstance(x, str) and str(x).isdigit())]
            if mapped:
                non_numeric_count = 0
                checked = 0
                for idx in mapped:
                    if 0 <= idx < len(df.columns):
                        checked += 1
                        val = df.iloc[0, idx]
                        # 使用 pandas 尝试转换为数值判断
                        try:
                            nv = pd.to_numeric(pd.Series([val]), errors='coerce').iloc[0]
                        except Exception:
                            nv = None
                        if pd.isna(nv) and pd.notna(val):
                            non_numeric_count += 1

                # 若大多数（>=60%）映射列在首行为非数值，则认为首行为表头并跳过
                if checked > 0 and non_numeric_count / checked >= 0.6:
                    try:
                        self.log_message.emit(f"检测到可能的表头，已跳过首行: {file_path.name}")
                    except Exception:
                        logger.debug("无法发送跳过表头的日志消息", exc_info=True)
                    df = df.iloc[1:].reset_index(drop=True)
        except Exception:
            logger.debug("表头自动检测发生异常，继续按原始数据处理", exc_info=True)

        def _col_to_numeric(df_local, col_idx, name):
            if col_idx is None:
                raise ValueError(f"缺失必需的列映射: {name}")
            if not (0 <= col_idx < len(df_local.columns)):
                raise IndexError(f"列索引越界: {name} -> {col_idx}")
            orig_col = df_local.iloc[:, col_idx]
            ser = pd.to_numeric(orig_col, errors='coerce')
            bad_mask = ser.isna() & orig_col.notna()
            if bad_mask.any():
                try:
                    bad_indices = orig_col.index[bad_mask].tolist()
                    sample_indices = bad_indices[:5]
                    sample_values = [str(v) for v in orig_col[bad_mask].head(5).tolist()]
                    self.log_message.emit(
                        f"列 {name} 有 {bad_mask.sum()} 个值无法解析为数值，示例索引: {sample_indices}，示例值: {sample_values}")
                except (IndexError, AttributeError, ValueError) as ex:
                    logger.debug("构建非数值示例时出错: %s", ex, exc_info=True)
            return ser.values.astype(float)

        try:
            fx = _col_to_numeric(df, cols.get('fx'), 'Fx')
            fy = _col_to_numeric(df, cols.get('fy'), 'Fy')
            fz = _col_to_numeric(df, cols.get('fz'), 'Fz')
            mx = _col_to_numeric(df, cols.get('mx'), 'Mx')
            my = _col_to_numeric(df, cols.get('my'), 'My')
            mz = _col_to_numeric(df, cols.get('mz'), 'Mz')
            forces = np.vstack([fx, fy, fz]).T
            moments = np.vstack([mx, my, mz]).T
        except (ValueError, IndexError, TypeError, OSError) as e:
            try:
                self.log_message.emit(f"数据列提取或转换失败: {e}")
            except Exception:
                logger.debug("无法通过 signal 发送失败消息: %s", e, exc_info=True)
            raise

        results = self.calculator.process_batch(forces, moments)
        output_df = pd.DataFrame()

        for col_idx in self.data_config.get('passthrough', []):
            try:
                idx = int(col_idx)
            except (ValueError, TypeError):
                try:
                    self.log_message.emit(f"透传列索引无效: {col_idx}")
                except Exception:
                    logger.debug("无法发送透传列无效消息: %s", col_idx, exc_info=True)
                continue
            if 0 <= idx < len(df.columns):
                output_df[f'Col_{idx}'] = df.iloc[:, idx]
            else:
                try:
                    self.log_message.emit(f"透传列索引越界: {idx}")
                except Exception:
                    logger.debug("无法发送透传列越界消息: %s", idx, exc_info=True)

        if cols.get('alpha') is not None and cols.get('alpha') < len(df.columns):
            output_df['Alpha'] = df.iloc[:, cols['alpha']]

        output_df['Fx_new'] = results['force_transformed'][:, 0]
        output_df['Fy_new'] = results['force_transformed'][:, 1]
        output_df['Fz_new'] = results['force_transformed'][:, 2]
        output_df['Mx_new'] = results['moment_transformed'][:, 0]
        output_df['My_new'] = results['moment_transformed'][:, 1]
        output_df['Mz_new'] = results['moment_transformed'][:, 2]
        output_df['Cx'] = results['coeff_force'][:, 0]
        output_df['Cy'] = results['coeff_force'][:, 1]
        output_df['Cz'] = results['coeff_force'][:, 2]
        output_df['Cl'] = results['coeff_moment'][:, 0]
        output_df['Cm'] = results['coeff_moment'][:, 1]
        output_df['Cn'] = results['coeff_moment'][:, 2]

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f"{file_path.stem}_result_{timestamp}.csv"
        output_df.to_csv(output_file, index=False)
        return output_file

    def request_stop(self):
        """请求停止后台线程的处理"""
        self._stop_requested = True

    def run(self):
        try:
            total = len(self.file_list)
            success = 0
            elapsed_list = []

            if self.registry_db:
                try:
                    self.log_message.emit(f"使用 format registry: {self.registry_db}")
                except RuntimeError as re:
                    logger.debug("Signal emit failed: %s", re, exc_info=True)
                except Exception:
                    logger.exception("Unexpected error when emitting registry message")

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
                    if isinstance(output_file, list):
                        out_names = ', '.join([p.name for p in output_file])
                        success_msg = f"生成 {len(output_file)} 个 part 输出: {out_names}"
                    else:
                        out_names = getattr(output_file, 'name', '未知输出')
                        success_msg = out_names

                    try:
                        self.log_message.emit(f"  ✓ 完成: {success_msg} (耗时: {file_elapsed:.2f}s)")
                    except Exception:
                        logger.debug("Cannot emit success message for %s", file_path, exc_info=True)

                    try:
                        self.log_message.emit(f"已完成 {i+1}/{total}，平均每文件耗时 {avg:.2f}s，预计剩余 {eta}s")
                    except Exception:
                        logger.debug("无法发出 ETA 消息", exc_info=True)

                    success += 1

                except (ValueError, IndexError, OSError) as e:
                    file_elapsed = (datetime.now() - file_start).total_seconds()
                    elapsed_list.append(file_elapsed)
                    logger.debug("File processing failed for %s: %s", file_path, e, exc_info=True)
                    try:
                        self.log_message.emit(f"  ✗ 失败: {e} (耗时: {file_elapsed:.2f}s)")
                    except Exception:
                        logger.debug("Cannot emit failure message for %s: %s", file_path, e, exc_info=True)

                except Exception as e:
                    file_elapsed = (datetime.now() - file_start).total_seconds()
                    elapsed_list.append(file_elapsed)
                    logger.exception("Unexpected error processing file %s", file_path)
                    try:
                        self.log_message.emit(f"  ✗ 未知错误 (耗时: {file_elapsed:.2f}s)")
                    except Exception:
                        logger.debug("Cannot emit unknown error message for %s", file_path, exc_info=True)

                try:
                    pct = int((i + 1) / total * 100)
                    self.progress.emit(pct)
                except Exception:
                    logger.debug("Unable to emit progress value for %s", file_path, exc_info=True)

            total_elapsed = sum(elapsed_list)
            try:
                msg = f"成功处理 {success}/{total} 个文件，耗时 {total_elapsed:.2f}s"
                if self._stop_requested:
                    msg = f"已取消：已处理 {success}/{total} 个文件，耗时 {total_elapsed:.2f}s"
                self.finished.emit(msg)
            except Exception:
                logger.debug("Cannot emit finished signal", exc_info=True)

        except Exception as e:
            logger.exception("BatchProcessThread.run 出现未处理异常")
            self.error.emit(str(e))
