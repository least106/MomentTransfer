# API 文档

MomentConversion 核心模块的 API 参考。

## 目录

1. [data_loader - 配置加载](#data_loader---配置加载)
2. [physics - 物理计算](#physics---物理计算)
3. [execution - 执行引擎](#execution---执行引擎)
4. [batch_processor - 批处理](#batch_processor---批处理)
5. [validator - 输入校验](#validator---输入校验)

---

## data_loader - 配置加载

### 函数：load_data

从 JSON 配置文件加载项目数据。

```python
from src.data_loader import load_data

project_data = load_data("config.json")
```

**参数：**
- `config_path` (str): 配置文件路径

**返回：**
- `ProjectData`: 项目数据对象

**异常：**
- `FileNotFoundError`: 文件不存在
- `JSONDecodeError`: JSON 格式错误
- `ValueError`: 配置数据不完整或无效

### 类：ProjectData

项目配置的容器类。

```python
@dataclass
class ProjectData:
    project_info: Dict[str, str]
    frame_config: FrameConfiguration
```

**属性：**
- `project_info`: 项目信息字典
- `frame_config`: 坐标系配置对象

### 类：FrameConfiguration

坐标系配置。

```python
@dataclass
class FrameConfiguration:
    source_frames: Dict[str, List[CoordSystemDefinition]]
    target_frames: Dict[str, List[CoordSystemDefinition]]
    reference_area: float
    reference_length: float
    dynamic_pressure: float
```

**属性：**
- `source_frames`: 源坐标系字典 {Part名: [变体列表]}
- `target_frames`: 目标坐标系字典
- `reference_area`: 参考面积 (m²)
- `reference_length`: 参考长度 (m)
- `dynamic_pressure`: 动压 (Pa)

### 类：CoordSystemDefinition

单个坐标系定义。

```python
@dataclass
class CoordSystemDefinition:
    origin: List[float]      # 原点 [x, y, z]
    x_axis: List[float]      # X轴向量
    y_axis: List[float]      # Y轴向量
    z_axis: List[float]      # Z轴向量
```

---

## physics - 物理计算

### 类：AeroCalculator

气动力计算核心类。

```python
from src.physics import AeroCalculator

calculator = AeroCalculator(
    project_data,
    source_part="BODY",
    source_variant=0,
    target_part="WIND",
    target_variant=0
)
```

**参数：**
- `project_data` (ProjectData): 项目配置
- `source_part` (str, 可选): 源 Part 名称
- `source_variant` (int): 源 Part 变体索引（默认 0）
- `target_part` (str, 可选): 目标 Part 名称
- `target_variant` (int): 目标 Part 变体索引（默认 0）
- `cache_cfg` (CacheConfig, 可选): 缓存配置

### 方法：process_frame

计算单点的力和力矩变换。

```python
result = calculator.process_frame(
    force=[100, 0, -50],
    moment=[0, 500, 0]
)
```

**参数：**
- `force` (List[float]): 源坐标系下的力向量 [Fx, Fy, Fz]
- `moment` (List[float]): 源坐标系下的力矩向量 [Mx, My, Mz]

**返回：**
- `AeroResult`: 结果对象

**示例：**
```python
from src.physics import AeroResult

result = calculator.process_frame([100, 0, -50], [0, 500, 0])
print(result.force_transformed)   # 变换后的力
print(result.moment_transformed)  # 变换后的力矩
print(result.coeff_force)         # 力系数
print(result.coeff_moment)        # 力矩系数
```

### 方法：process_batch

批量计算多个数据点。

```python
import numpy as np

forces = np.array([
    [100, 0, -50],
    [110, 5, -45],
    [105, -3, -55]
])

moments = np.array([
    [0, 500, 0],
    [10, 510, 5],
    [-5, 490, -10]
])

result = calculator.process_batch(forces, moments)
```

**参数：**
- `forces` (np.ndarray): (N, 3) 力向量数组
- `moments` (np.ndarray): (N, 3) 力矩向量数组

**返回：**
- `Dict[str, np.ndarray]`: 结果字典
  - `force_transformed`: (N, 3) 变换后的力
  - `moment_transformed`: (N, 3) 变换后的力矩
  - `coeff_force`: (N, 3) 力系数
  - `coeff_moment`: (N, 3) 力矩系数

### 类：AeroResult

单点计算结果。

```python
@dataclass
class AeroResult:
    force_transformed: List[float]
    moment_transformed: List[float]
    coeff_force: List[float]
    coeff_moment: List[float]
```

---

## execution - 执行引擎

### 类：ExecutionContext

统一的执行配置容器。

```python
from src.execution import ExecutionContext, create_execution_context

ctx = create_execution_context(
    "config.json",
    source_part="BODY",
    target_part="WIND"
)
```

**属性：**
- `project_data`: 项目配置
- `calculator`: AeroCalculator 实例
- `source_part`、`target_part`: Part 名称
- `source_variant`、`target_variant`: 变体索引

### 类：ExecutionEngine

通用执行引擎。

```python
from src.execution import ExecutionEngine

engine = ExecutionEngine(ctx)

# 单点执行
result = engine.execute_frame([100, 0, -50], [0, 500, 0])

# 批量执行
results = engine.execute_batch(forces_array, moments_array)
```

**方法：**

#### execute_frame

```python
result = engine.execute_frame(force, moment)
```

返回 `ExecutionResult` 对象。

#### execute_batch

```python
result = engine.execute_batch(forces, moments, on_progress=None)
```

**参数：**
- `forces`: (N, 3) 力数组
- `moments`: (N, 3) 力矩数组
- `on_progress`: 进度回调函数 (processed_count, total_count)

**返回：**
- `ExecutionResult` 对象

### 函数：create_execution_context

便捷函数，创建执行上下文。

```python
from src.execution import create_execution_context

ctx = create_execution_context(
    "config.json",
    source_part="BODY",
    target_part="WIND"
)
calculator = ctx.calculator
```

---

## batch_processor - 批处理

### 类：BatchProcessor

批处理器，处理文件和批量数据。

```python
from src.batch_processor import BatchProcessor
from src.execution import ExecutionEngine

engine = ExecutionEngine(ctx)
processor = BatchProcessor(
    engine,
    on_progress=lambda processed, total: print(f"{processed}/{total}")
)
```

**参数：**
- `engine`: ExecutionEngine 实例
- `on_progress`: 进度回调 (processed_count, total_count)

### 方法：process_file

处理单个文件。

```python
result = processor.process_file(
    file_path="data/input.csv",
    output_path="data/output.csv",
    force_column="力",
    moment_column="力矩"
)
```

**参数：**
- `file_path` (Path): 输入文件路径
- `output_path` (Path): 输出文件路径
- `force_column` (str): 力列前缀
- `moment_column` (str): 力矩列前缀
- `skip_rows` (int): 跳过的行数

**返回：**
- `ExecutionResult`: 处理结果

### 类：BatchProcessResult

批处理结果。

```python
@dataclass
class BatchProcessResult:
    success: bool
    total_files: int
    processed_files: int
    failed_files: int
    total_rows: int
    processed_rows: int
    failed_rows: int
    errors: List[Dict[str, Any]]
    warnings: List[str]
```

---

## validator - 输入校验

### 函数：validate_file_path

校验文件路径安全性。

```python
from src.validator import validate_file_path

validate_file_path("data/input.csv", must_exist=True, writable=False)
```

**参数：**
- `path` (str): 文件路径
- `must_exist` (bool): 文件是否必须存在
- `writable` (bool): 是否需要可写权限

**异常：**
- `ValueError`: 路径不安全或不满足条件

### 函数：validate_csv_safety

校验 CSV 文件大小和安全性。

```python
from src.validator import validate_csv_safety

validate_csv_safety("data/input.csv", max_rows=100000)
```

**参数：**
- `path` (str): CSV 文件路径
- `max_rows` (int): 最大允许行数

**异常：**
- `ValueError`: 文件过大或不安全

### 函数：validate_data_frame

校验 DataFrame 的列和数据。

```python
import pandas as pd
from src.validator import validate_data_frame

df = pd.read_csv("data.csv")
validate_data_frame(
    df,
    column_mapping={"力X": "force_x", "力Y": "force_y"},
    max_rows=100000
)
```

**参数：**
- `df` (DataFrame): 数据框
- `column_mapping` (Dict): 列名映射
- `max_rows` (int): 最大行数限制

**异常：**
- `ValueError`: 数据不符合要求

---

## 使用示例

### 完整的单点计算流程

```python
from src.data_loader import load_data
from src.physics import AeroCalculator

# 1. 加载配置
project_data = load_data("config.json")

# 2. 创建计算器
calculator = AeroCalculator(
    project_data,
    source_part="BODY",
    target_part="WIND"
)

# 3. 执行计算
result = calculator.process_frame(
    force=[100, 0, -50],
    moment=[0, 500, 0]
)

# 4. 使用结果
print(f"变换力: {result.force_transformed}")
print(f"力系数: {result.coeff_force}")
```

### 完整的批处理流程

```python
from src.execution import create_execution_context, ExecutionEngine
from src.batch_processor import BatchProcessor

# 1. 创建执行上下文
ctx = create_execution_context(
    "config.json",
    source_part="BODY",
    target_part="WIND"
)

# 2. 创建执行引擎和批处理器
engine = ExecutionEngine(ctx)
processor = BatchProcessor(engine)

# 3. 处理文件
result = processor.process_file(
    "data/input.csv",
    "data/output.csv"
)

# 4. 检查结果
if result.success:
    print(f"处理完成：{result.processed_rows} 行")
else:
    print(f"处理失败：{result.errors}")
```

### 进度跟踪

```python
def progress_callback(processed, total):
    percent = (processed / total) * 100
    print(f"进度: {processed}/{total} ({percent:.1f}%)")

processor = BatchProcessor(engine, on_progress=progress_callback)
processor.process_file("data/input.csv", "data/output.csv")
```
