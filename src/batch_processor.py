"""统一的批处理执行模块 - 为批处理和GUI提供一致的数据处理流程。

该模块将 ExecutionEngine 与数据加载/处理流程结合，
提供批量处理文件的统一接口。

设计思路：
1. BatchProcessor：处理单个或多个文件
2. 使用 ExecutionEngine 进行计算
3. 支持特殊格式和标准格式
4. 统一的进度跟踪和错误处理
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.execution import ExecutionContext, ExecutionEngine, ExecutionResult

logger = logging.getLogger(__name__)


@dataclass
class BatchProcessResult:
    """批处理结果容器。"""

    success: bool
    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    total_rows: int = 0
    processed_rows: int = 0
    failed_rows: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, file_path: str, error: str, details: str = None):
        """记录处理错误。"""
        self.errors.append(
            {
                "file": file_path,
                "error": error,
                "details": details,
            }
        )

    def add_warning(self, warning: str):
        """记录警告信息。"""
        self.warnings.append(warning)


class BatchProcessor:
    """批处理器：使用 ExecutionEngine 处理数据文件。

    该类提供了适应 CLI、批处理 CLI 和 GUI 的统一批处理接口。
    """

    def __init__(
        self,
        engine: ExecutionEngine,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ):
        """初始化批处理器。

        参数：
            engine: ExecutionEngine 实例
            on_progress: 进度回调函数 (processed, total)
        """
        self.engine = engine
        self.on_progress = on_progress
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def process_file(
        self,
        file_path: Path,
        output_path: Path,
        force_column: str = "力",
        moment_column: str = "力矩",
        skip_rows: int = 0,
    ) -> ExecutionResult:
        """处理单个文件。

        参数：
            file_path: 输入文件路径
            output_path: 输出文件路径
            force_column: 力数据的列前缀（或完整列名）
            moment_column: 力矩数据的列前缀（或完整列名）
            skip_rows: 跳过的行数

        返回：
            ExecutionResult 包含处理结果或错误信息
        """
        try:
            file_path = Path(file_path)
            output_path = Path(output_path)

            # 检查文件存在
            if not file_path.exists():
                raise FileNotFoundError(f"输入文件不存在: {file_path}")

            # 确保输出目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 根据文件扩展名选择读取方式
            if file_path.suffix.lower() in [".csv", ".txt", ".dat"]:
                df = pd.read_csv(file_path, skiprows=skip_rows)
            elif file_path.suffix.lower() in [".xlsx", ".xls"]:
                df = pd.read_excel(file_path, skiprows=skip_rows)
            else:
                raise ValueError(f"不支持的文件格式: {file_path.suffix}")

            # 提取力和力矩列
            forces, moments = self._extract_force_moment_data(
                df, force_column, moment_column
            )

            # 执行批量计算
            exec_result = self.engine.execute_batch(forces, moments)
            if not exec_result.success:
                return exec_result

            # 保存结果
            batch_result = exec_result.data
            self._save_results(output_path, df, batch_result)

            self.logger.info(f"✓ 处理完成: {file_path} → {output_path}")
            return ExecutionResult(
                success=True,
                data={"output": str(output_path), "rows_processed": len(df)},
                stats={"processed": len(df)},
            )

        except Exception as e:
            error_msg = f"文件处理失败 ({file_path}): {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return ExecutionResult(success=False, data=None, error=error_msg)

    def process_batch(
        self, file_list: List[Path], output_dir: Path, **kwargs
    ) -> BatchProcessResult:
        """处理多个文件（批处理）。

        参数：
            file_list: 输入文件列表
            output_dir: 输出目录
            **kwargs: 传递给 process_file 的额外参数

        返回：
            BatchProcessResult 包含聚合的处理结果
        """
        result = BatchProcessResult(success=True, total_files=len(file_list))

        for idx, file_path in enumerate(file_list):
            try:
                output_path = (
                    output_dir / file_path.stem / f"{file_path.stem}_result.csv"
                )
                exec_result = self.process_file(file_path, output_path, **kwargs)

                if exec_result.success:
                    result.processed_files += 1
                    result.processed_rows += exec_result.stats.get("processed", 0)
                else:
                    result.failed_files += 1
                    result.add_error(str(file_path), exec_result.error)

                result.total_rows += exec_result.stats.get("processed", 0)

            except Exception as e:
                result.failed_files += 1
                result.add_error(str(file_path), str(e))
                self.logger.exception(f"处理文件失败: {file_path}")

            finally:
                # 调用进度回调
                if self.on_progress:
                    self.on_progress(idx + 1, len(file_list))

        # 汇总结果
        result.success = result.failed_files == 0

        return result

    @staticmethod
    def _extract_force_moment_data(
        df: pd.DataFrame,
        force_column: str,
        moment_column: str,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """从数据框提取力和力矩数据。

        支持多种列名格式：
        - 完整列名: "力" 或 "力矩"
        - 前缀: "力_x", "力_y", "力_z" 或 "Fx", "Fy", "Fz"
        """
        # 查找匹配的列
        force_cols = [c for c in df.columns if force_column in c][:3]
        moment_cols = [c for c in df.columns if moment_column in c][:3]

        if len(force_cols) < 3:
            raise ValueError(f"未找到足够的力列 ({force_column})，找到: {force_cols}")
        if len(moment_cols) < 3:
            raise ValueError(
                f"未找到足够的力矩列 ({moment_column})，找到: {moment_cols}"
            )

        forces = df[force_cols].values.astype(float)
        moments = df[moment_cols].values.astype(float)

        return forces, moments

    @staticmethod
    def _save_results(
        output_path: Path,
        original_df: pd.DataFrame,
        batch_result: Dict[str, np.ndarray],
    ):
        """保存计算结果到文件。"""
        # 创建结果数据框
        result_df = original_df.copy()

        # 添加计算结果列
        if "force_transformed" in batch_result:
            force_t = batch_result["force_transformed"]
            result_df["力_变换_X"] = force_t[:, 0]
            result_df["力_变换_Y"] = force_t[:, 1]
            result_df["力_变换_Z"] = force_t[:, 2]

        if "moment_transformed" in batch_result:
            moment_t = batch_result["moment_transformed"]
            result_df["力矩_变换_X"] = moment_t[:, 0]
            result_df["力矩_变换_Y"] = moment_t[:, 1]
            result_df["力矩_变换_Z"] = moment_t[:, 2]

        if "coeff_force" in batch_result:
            coeff_f = batch_result["coeff_force"]
            result_df["Cx"] = coeff_f[:, 0]
            result_df["Cy"] = coeff_f[:, 1]
            result_df["Cz"] = coeff_f[:, 2]

        if "coeff_moment" in batch_result:
            coeff_m = batch_result["coeff_moment"]
            result_df["Cl"] = coeff_m[:, 0]
            result_df["Cm"] = coeff_m[:, 1]
            result_df["Cn"] = coeff_m[:, 2]

        # 保存到文件
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
