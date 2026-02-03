# 开发者指南

MomentConversion 的架构设计、开发工作流和常见修改模式。

## 目录

1. [架构概览](#架构概览)
2. [开发环境设置](#开发环境设置)
3. [代码组织](#代码组织)
4. [常见修改模式](#常见修改模式)
5. [测试策略](#测试策略)
6. [代码质量](#代码质量)
7. [调试技巧](#调试技巧)

---

## 架构概览

### 核心设计原则

1. **统一计算管道**：三个入口（CLI、批处理、GUI）共享同一个 `ExecutionEngine` 和 `AeroCalculator`
2. **关注点分离**：数据加载、计算、UI 逻辑分离
3. **配置外部化**：坐标系和参数完全通过 JSON 配置文件定义
4. **可缓存性**：性能敏感的操作（旋转矩阵、变换矩阵）支持 LRU 缓存

### 数据流

```
JSON 配置文件
    ↓
ProjectData (数据加载层)
    ↓
ExecutionContext (执行上下文)
    ↓
AeroCalculator (计算核心)
    ↓
ExecutionEngine (执行引擎)
    ↓
CLI / BatchProcessor / GUI
```

### 模块职责

| 模块 | 职责 | 位置 |
|------|------|------|
| **data_loader** | 加载 JSON 配置到内存数据结构 | `src/data_loader.py` |
| **physics** | 坐标系变换、无量纲化计算 | `src/physics.py` |
| **execution** | 统一的执行上下文和引擎 | `src/execution.py` |
| **batch_processor** | 文件批处理接口 | `src/batch_processor.py` |
| **validator** | 输入校验和安全检查 | `src/validator.py` |
| **cache** | LRU 缓存系统 | `src/cache.py` |
| **CLI** | 命令行单点计算入口 | `cli.py` |
| **Batch** | 命令行批处理入口 | `batch.py` |
| **GUI** | PyQt6 交互式界面 | `gui_main.py` + `gui/` |

---

## 开发环境设置

### 1. 克隆仓库

```bash
git clone https://github.com/least106/MomentConversion.git
cd MomentConversion
```

### 2. 创建虚拟环境

```powershell
# 使用 environment.yml
conda env create -f environment.yml
conda activate MomentConversion

# 或手动创建
conda create -n MomentConversion python=3.8
conda activate MomentConversion
```

### 3. 安装依赖

```bash
# 开发模式安装
pip install -e .

# 安装开发依赖
pip install -r requirements-dev.txt
```

### 4. 验证安装

```bash
# 运行测试
pytest tests/ -v

# 检查代码质量
pylint src/ --disable=all --enable=E

# 检查格式
black src/ --check
```

---

## 代码组织

### 源代码结构

```
src/
├── __init__.py
├── __main__.py
├── physics.py              # AeroCalculator - 核心计算
├── data_loader.py          # ProjectData - 配置加载
├── execution.py            # ExecutionEngine - 统一执行
├── batch_processor.py      # BatchProcessor - 批处理
├── validator.py            # 输入校验
├── cache.py                # LRU 缓存
├── calculator_factory.py   # 工厂函数
├── config.py               # 系统配置
├── geometry.py             # 几何计算
├── special_format_*.py     # 特殊格式处理
├── config/                 # 配置文件
└── models/                 # 数据模型
```

### GUI 结构

```
gui/
├── main_window.py          # 主窗口容器
├── signal_bus.py           # 中央信号总线（解耦组件通信）
├── managers.py             # UI 管理器
├── batch_manager*.py       # 批处理相关管理器
├── background_worker.py    # 后台任务执行
├── panels/                 # 功能面板
│   ├── config_panel.py
│   ├── part_mapping_panel.py
│   └── operation_panel.py
└── ...
```

### 测试结构

```
tests/
├── test_physics.py              # 物理计算单元测试
├── test_data_loader.py          # 配置加载测试
├── test_batch_*.py              # 批处理集成测试
├── test_validator.py            # 校验函数测试
├── test_cache.py                # 缓存测试
└── test_architecture.py         # 架构集成测试
```

---

## 常见修改模式

### 模式 1：添加新的计算功能

**目标**：在 AeroCalculator 中添加新的物理计算方法，使三个入口自动获得该功能。

**步骤**：

1. **修改 `src/physics.py`**

```python
class AeroCalculator:
    def process_frame(self, force, moment):
        # 现有逻辑
        force_transformed = self._rotate_force(force)
        # ... 无量纲化等
        return AeroResult(...)
    
    # 新方法
    def calculate_aerodynamic_center(self, forces_array):
        """计算气动中心"""
        # 实现新功能
        pass
```

2. **添加单元测试 `tests/test_physics.py`**

```python
def test_calculate_aerodynamic_center():
    calculator = AeroCalculator(project_data)
    result = calculator.calculate_aerodynamic_center(forces_array)
    assert result is not None
    # 其他断言
```

3. **无需改动 CLI/Batch/GUI** - 它们会自动调用新方法

### 模式 2：修改配置加载逻辑

**目标**：扩展 JSON 配置格式支持新的参数。

**步骤**：

1. **修改 `src/data_loader.py`**

```python
@dataclass
class FrameConfiguration:
    # 现有字段
    source_frames: Dict[str, List[CoordSystemDefinition]]
    target_frames: Dict[str, List[CoordSystemDefinition]]
    
    # 新字段
    temperature: float = 15.0  # 温度用于空气密度计算
    
    @classmethod
    def from_dict(cls, data):
        # 加载新字段
        temperature = data.get("Temperature", 15.0)
        return cls(..., temperature=temperature)
```

2. **更新 `src/execution.py`** 中的 `create_execution_context`

```python
def create_execution_context(config_path, ...):
    project_data = load_data(config_path)
    # 新字段自动被 project_data 包含
    ctx = ExecutionContext(project_data=project_data, ...)
    return ctx
```

3. **在 `src/physics.py` 中使用新参数**

```python
class AeroCalculator:
    def __init__(self, project_data, ...):
        self.temperature = project_data.frame_config.temperature
        # 用于计算空气密度或其他目的
```

4. **三个入口自动适配新配置**

### 模式 3：GUI 中添加新的用户交互

**目标**：在 GUI 中添加新的参数设置或功能面板。

**步骤**：

1. **在 `gui/signal_bus.py` 定义新 Signal**

```python
class SignalBus(QObject):
    # 现有信号
    configLoaded = Signal(object)
    
    # 新信号
    temperatureChanged = Signal(float)  # 温度变化
```

2. **创建或修改管理器 `gui/managers.py`**

```python
class ParameterManager:
    def __init__(self):
        self.signal_bus = SignalBus.instance()
        self.signal_bus.temperatureChanged.connect(self._on_temperature_changed)
    
    def _on_temperature_changed(self, temperature):
        # 处理温度变化
        self.update_air_properties(temperature)
```

3. **在面板中发送信号**

```python
class ParameterPanel(QWidget):
    def __init__(self):
        self.signal_bus = SignalBus.instance()
        self.temp_spinbox.valueChanged.connect(
            self.signal_bus.temperatureChanged.emit
        )
```

4. **使用后台工作线程处理耗时操作**

```python
from gui.background_worker import BackgroundWorker

def on_temperature_changed(self, temp):
    # 重新计算（可能耗时）
    self.worker = BackgroundWorker(
        self.calculator.recalculate_with_temperature,
        temp
    )
    self.worker.result_ready.connect(self.on_calculation_done)
    self.worker.start()
```

### 模式 4：处理特殊数据格式

**目标**：支持新的数据格式（如某个风洞的特殊输出格式）。

**步骤**：

1. **创建检测函数 `src/special_format_detector.py`**

```python
def looks_like_special_format(file_path):
    """检测是否为特殊格式"""
    with open(file_path, 'r') as f:
        header = f.readline()
    return "特殊标记" in header
```

2. **创建解析函数 `src/special_format_parser.py`**

```python
def parse_special_format(file_path):
    """解析特殊格式，转换为标准 DataFrame"""
    # 读取和转换
    df = pd.read_csv(file_path, ...)
    df = df.rename(columns={'旧列名': '力X'})
    return df
```

3. **集成到批处理 `src/batch_processor.py`**

```python
def process_file(self, file_path, ...):
    if looks_like_special_format(file_path):
        df = parse_special_format(file_path)
    else:
        df = pd.read_csv(file_path)
    # 继续处理
```

4. **GUI 自动支持**（无需改动 GUI 代码）

---

## 测试策略

### 测试分类

1. **单元测试** - 测试单个函数或类
2. **集成测试** - 测试模块间的交互
3. **端到端测试** - 测试完整的工作流

### 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定文件
pytest tests/test_physics.py -v

# 运行特定测试函数
pytest tests/test_physics.py::test_process_frame -v

# 生成覆盖率报告
pytest tests/ --cov=src --cov-report=html
```

### 编写测试

```python
import pytest
from src.physics import AeroCalculator
from src.data_loader import load_data

class TestAeroCalculator:
    @pytest.fixture
    def calculator(self):
        """测试前准备"""
        project_data = load_data("tests/fixtures/config.json")
        return AeroCalculator(project_data)
    
    def test_process_frame_basic(self, calculator):
        """测试基本功能"""
        result = calculator.process_frame([100, 0, -50], [0, 500, 0])
        assert result.force_transformed is not None
        assert len(result.force_transformed) == 3
    
    def test_process_frame_edge_cases(self, calculator):
        """测试边界情况"""
        # 零向量
        result = calculator.process_frame([0, 0, 0], [0, 0, 0])
        assert result.force_transformed == [0, 0, 0]
        
        # 大数值
        result = calculator.process_frame([1e6, 1e6, 1e6], [1e6, 1e6, 1e6])
        assert result is not None
```

### 测试覆盖率目标

- **最低要求**：80% 的代码覆盖率
- **关键模块**：95%+ 的覆盖率（physics.py、data_loader.py）
- **UI 模块**：50%+ 的覆盖率（难以全覆盖，重点测试业务逻辑）

---

## 代码质量

### 代码风格

遵循 PEP 8 标准和项目约定：

```python
# 好
def calculate_force_coefficient(force, reference_area):
    """计算力系数
    
    参数：
        force: 力向量 [Fx, Fy, Fz]
        reference_area: 参考面积
    
    返回：
        list: 力系数 [Cx, Cy, Cz]
    """
    return [f / reference_area for f in force]

# 不好
def calc_f(f, s):  # 缩写不清楚
    return [x/s for x in f]  # 缺少文档
```

### 代码检查

```bash
# 自动格式化
black src/ gui/

# 导入排序
isort src/ gui/

# 代码质量分析
pylint src/ gui/

# 类型检查
mypy src/ --ignore-missing-imports
```

### 文档要求

```python
class AeroCalculator:
    """气动力计算器
    
    负责坐标系变换和无量纲化计算。
    
    属性：
        project_data: 项目配置
        source_part: 源坐标系 Part 名称
        target_part: 目标坐标系 Part 名称
    
    示例：
        >>> calculator = AeroCalculator(project_data)
        >>> result = calculator.process_frame([100, 0, -50], [0, 500, 0])
        >>> print(result.coeff_force)
    """
    pass
```

---

## 调试技巧

### 1. 启用详细日志

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug(f"坐标系变换矩阵:\n{transform_matrix}")
logger.info(f"处理完成：{processed_rows} 行")
logger.warning(f"发现非数值数据：第 {row_idx} 行")
logger.error(f"文件读取失败：{error}")
```

### 2. 检查坐标系正确性

```python
from src.data_loader import load_data

project_data = load_data("config.json")
frame_cfg = project_data.frame_config

# 检查向量是否为单位向量
for part_name, coords in frame_cfg.source_frames.items():
    for i, coord in enumerate(coords):
        x_norm = sum(xi**2 for xi in coord.x_axis) ** 0.5
        print(f"{part_name}[{i}] X轴长度: {x_norm}")  # 应为 1.0
```

### 3. 比较变换结果

```python
# 手工计算验证
import numpy as np

matrix = np.array([
    [0.9848, 0.1736, 0],
    [-0.1736, 0.9848, 0],
    [0, 0, 1]
])

force = np.array([100, 0, -50])
force_transformed = matrix @ force
print(f"计算结果：{force_transformed}")

# 与 AeroCalculator 结果比较
result = calculator.process_frame(force.tolist(), [0, 0, 0])
print(f"Calculator 结果：{result.force_transformed}")
```

### 4. 性能分析

```python
import cProfile
import pstats

# 分析性能瓶颈
profiler = cProfile.Profile()
profiler.enable()

# 执行要分析的代码
calculator.process_batch(forces, moments)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)  # 显示前 10 个最耗时的函数
```

### 5. 调试 GUI

```python
# 在 GUI 中添加调试输出
from gui.signal_bus import SignalBus

signal_bus = SignalBus.instance()

# 连接信号到调试函数
def on_config_loaded(data):
    print(f"配置加载完成：{data.project_info}")

signal_bus.configLoaded.connect(on_config_loaded)
```

---

## 常见问题

**Q：修改了 AeroCalculator 但测试失败**

A：检查是否：
1. 更新了对应的单元测试
2. 修改了返回值格式（检查 AeroResult）
3. 修改了输入参数格式
4. 修改了计算逻辑（需要验证数学正确性）

**Q：GUI 中数据不同步**

A：检查是否：
1. 通过 `signal_bus` 发送了信号
2. 管理器正确连接了信号和槽
3. 后台线程正确处理了耗时操作

**Q：批处理性能慢**

A：优化方向：
1. 增加 `chunk_size` 参数
2. 启用缓存（`cache_cfg`）
3. 使用并行处理（batch.py 支持多进程）
4. 分析性能瓶颈（见上面的性能分析）

---

## 相关资源

- [快速开始指南](QUICKSTART.md)
- [API 文档](API.md)
- [配置文件格式](CONFIG_FORMAT.md)
- [代码风格指南](../prompts/环境.instructions.md)
