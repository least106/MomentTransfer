"""统一执行引擎：为CLI、批处理和GUI提供一致的计算流程。

该模块封装了 AeroCalculator 的初始化和执行逻辑，使得三个主要入口
可以共享相同的计算管道，避免重复代码和逻辑分散。

设计原则：
1. ExecutionContext：统一的配置和计算器容器
2. ExecutionEngine：通用的执行流程和错误处理
3. 向后兼容：保持现有 CLI/batch 接口不变
4. 易于测试：使用依赖注入，便于单元测试

使用示例：
    # 创建执行上下文
    ctx = create_execution_context(
        config_path="config.json",
        target_part="BODY",
        target_variant=0
    )

    # 执行单点计算
    engine = ExecutionEngine(ctx)
    result = engine.execute_frame([100, 0, -50], [0, 500, 0])

    # 执行批量计算
    results = engine.execute_batch(forces_array, moments_array)
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

import numpy as np

from src.data_loader import ProjectData, load_data
from src.physics import AeroCalculator, AeroResult

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """执行上下文：封装所有执行所需的配置和对象。

    该类作为 CLI、批处理和 GUI 之间的统一配置接口，
    避免在三处地方分别管理计算器创建逻辑。
    """

    # 配置数据
    project_data: ProjectData
    config_path: str

    # 计算器参数
    source_part: Optional[str] = None
    source_variant: int = 0
    target_part: Optional[str] = None
    target_variant: int = 0

    # 缓存和优化选项
    use_cache: bool = True
    cache_cfg: Optional[Any] = None

    # 执行选项
    strict_mode: bool = False  # True: 异常中止；False: 记录并继续
    log_level: int = logging.INFO

    # 已初始化的计算器（延迟创建）
    _calculator: Optional[AeroCalculator] = None

    @property
    def calculator(self) -> AeroCalculator:
        """获取或创建计算器（延迟初始化）。"""
        if self._calculator is None:
            self._calculator = AeroCalculator(
                self.project_data,
                source_part=self.source_part,
                source_variant=self.source_variant,
                target_part=self.target_part,
                target_variant=self.target_variant,
                cache_cfg=self.cache_cfg if self.use_cache else None,
            )
        return self._calculator

    def reset_calculator(self) -> None:
        """重置计算器（用于改变参数时）。"""
        self._calculator = None

    def update_target(self, target_part: Optional[str], target_variant: int = 0) -> None:
        """更新目标坐标系并重置计算器。"""
        self.target_part = target_part
        self.target_variant = target_variant
        self.reset_calculator()


@dataclass
class ExecutionResult:
    """单点或批量执行的结果容器。"""

    success: bool
    data: Any  # AeroResult 或字典数组
    error: Optional[str] = None
    warning: Optional[str] = None
    stats: Optional[dict] = None


class ExecutionEngine:
    """执行引擎：使用统一的计算流程处理所有类型的输入。

    该类提供统一的计算接口，隐藏了 AeroCalculator 的复杂性，
    并提供标准的错误处理和日志记录。
    """

    def __init__(self, context: ExecutionContext):
        """初始化执行引擎。

        参数：
            context: ExecutionContext 实例
        """
        self.context = context
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def execute_frame(
        self,
        force: Union[List[float], np.ndarray],
        moment: Union[List[float], np.ndarray],
    ) -> ExecutionResult:
        """执行单点计算。

        参数：
            force: 力向量 [Fx, Fy, Fz]
            moment: 力矩向量 [Mx, My, Mz]

        返回：
            ExecutionResult 包含计算结果或错误信息
        """
        try:
            # 验证输入
            force = self._validate_vector(force, "力")
            moment = self._validate_vector(moment, "力矩")

            # 执行计算
            calculator = self.context.calculator
            result: AeroResult = calculator.process_frame(force, moment)

            # 返回成功结果
            return ExecutionResult(
                success=True,
                data=result,
                stats={"processed": 1},
            )
        except Exception as e:
            error_msg = f"单点计算失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            if self.context.strict_mode:
                raise
            return ExecutionResult(success=False, data=None, error=error_msg)

    def execute_batch(
        self,
        forces: np.ndarray,
        moments: np.ndarray,
        sample_failures: int = 5,
    ) -> ExecutionResult:
        """执行批量计算。

        参数：
            forces: (N, 3) 的力数组
            moments: (N, 3) 的力矩数组
            sample_failures: 失败时记录的示例行数

        返回：
            ExecutionResult 包含计算结果数组或错误信息
        """
        try:
            # 验证输入形状
            if forces.shape != moments.shape or forces.shape[1] != 3:
                raise ValueError(f"输入形状不匹配：forces={forces.shape}，moments={moments.shape}，" "期望 (N, 3)")

            # 执行批量计算
            calculator = self.context.calculator
            batch_result = calculator.process_batch(forces, moments)

            # 收集统计信息
            num_processed = batch_result.get("force_transformed", np.array([])).shape[0]

            return ExecutionResult(
                success=True,
                data=batch_result,
                stats={"processed": num_processed},
            )
        except Exception as e:
            error_msg = f"批量计算失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            if self.context.strict_mode:
                raise
            return ExecutionResult(success=False, data=None, error=error_msg)

    def update_target(self, target_part: Optional[str], target_variant: int = 0) -> ExecutionResult:
        """动态更新目标坐标系。

        参数：
            target_part: 目标 part 名称
            target_variant: 目标 variant 索引

        返回：
            ExecutionResult 指示是否成功
        """
        try:
            self.context.update_target(target_part, target_variant)
            self.logger.info("目标坐标系已更新: %s (variant=%d)", target_part, target_variant)
            return ExecutionResult(
                success=True,
                data={"target_part": target_part, "target_variant": target_variant},
            )
        except Exception as e:
            error_msg = f"更新目标坐标系失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            if self.context.strict_mode:
                raise
            return ExecutionResult(success=False, data=None, error=error_msg)

    def get_available_targets(self) -> Tuple[List[str], dict]:
        """获取所有可用的目标坐标系。

        返回：
            (target_names, target_info_dict)
            其中 target_info_dict 包含每个 target 的 variants 数量
        """
        target_parts = self.context.project_data.target_parts
        target_names = list(target_parts.keys())
        target_info = {
            name: len(parts_variants) if isinstance(parts_variants, list) else 1
            for name, parts_variants in target_parts.items()
        }
        return target_names, target_info

    @staticmethod
    def _validate_vector(v: Union[List[float], np.ndarray], name: str) -> List[float]:
        """验证并转换向量输入。

        参数：
            v: 向量数据
            name: 向量名称（用于错误消息）

        返回：
            转换后的 list 类型向量

        异常：
            ValueError: 如果向量无效
        """
        try:
            if isinstance(v, np.ndarray):
                v = v.tolist()
            if not isinstance(v, (list, tuple)) or len(v) != 3:
                v_len = len(v) if hasattr(v, "__len__") else "N/A"
                raise ValueError(f"{name}必须是长度为3的序列，得到 {type(v)} {v_len}")
            return list(float(x) for x in v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{name}验证失败: {str(e)}") from e


def create_execution_context(  # pylint: disable=too-many-arguments
    config_path: Union[str, Path],
    *,
    target_part: Optional[str] = None,
    target_variant: int = 0,
    source_part: Optional[str] = None,
    source_variant: int = 0,
    use_cache: bool = True,
    strict_mode: bool = False,
    log_level: int = logging.INFO,
) -> ExecutionContext:
    """工厂函数：创建执行上下文。

    这是所有入口（CLI、批处理、GUI）创建计算环境的统一接口。

    参数：
        config_path: JSON 配置文件路径
        target_part: 目标 part 名称（可选）
        target_variant: 目标 variant 索引
        source_part: 源 part 名称（可选）
        source_variant: 源 variant 索引
        use_cache: 是否启用缓存
        strict_mode: 严格模式（异常中止）
        log_level: 日志级别

    返回：
        ExecutionContext 实例

    异常：
        FileNotFoundError: 配置文件不存在
        ValueError: 配置无效
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    # 加载项目配置
    logger.debug("加载项目配置: %s", config_path)
    project_data = load_data(str(config_path))

    # 创建并返回执行上下文
    context = ExecutionContext(
        project_data=project_data,
        config_path=str(config_path),
        source_part=source_part,
        source_variant=source_variant,
        target_part=target_part,
        target_variant=target_variant,
        use_cache=use_cache,
        strict_mode=strict_mode,
        log_level=log_level,
    )

    return context


def create_execution_engine(config_path: Union[str, Path], **options) -> Tuple[ExecutionContext, ExecutionEngine]:
    """便捷工厂函数：一次创建上下文和引擎。

    参数：
        config_path: 配置文件路径
        **options: 传递给 create_execution_context 的关键字参数

    返回：
        (ExecutionContext, ExecutionEngine) 元组
    """
    context = create_execution_context(config_path, **options)
    engine = ExecutionEngine(context)
    return context, engine
