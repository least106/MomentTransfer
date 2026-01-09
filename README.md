# MomentTransfer - 气动力矩坐标变换工具

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)

## 项目简介

MomentTransfer 是一个用于航空航天领域的力矩坐标变换计算工具。主要功能包括：

- **坐标系变换**：将力和力矩从源坐标系（如天平坐标系）变换到目标坐标系（如体轴系或风轴系）
- **力矩移轴**：根据力矩中心的变化，自动计算由力产生的附加力矩（r × F）
- **无量纲化**：根据动压、参考面积和参考长度，计算气动力系数和力矩系数
- **GUI/CLI 工具**：提供图形界面和命令行界面，支持单文件和批量处理
- **批处理能力**：支持并行处理大量数据文件，提高效率
- **灵活的数据格式**：支持 JSON、CSV 等多种数据格式，提供特殊格式解析器

本工具适用于风洞试验数据处理、CFD 后处理、数据格式转换等场景。

## 快速开始

### 环境要求

- Python 3.8 或更高版本
- 推荐使用 Anaconda 环境管理

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/YOUR_USERNAME/MomentTransfer.git
cd MomentTransfer
```

2. **创建并激活 Conda 环境**（推荐）
```bash
conda create -n MomentTransfer python=3.8
conda activate MomentTransfer
```

3. **安装依赖**
```bash
# 使用清华镜像源加速（国内推荐）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 运行示例

项目提供了多种使用方式：

#### 1. 命令行工具（推荐）

```bash
# 交互式命令行界面
python cli.py
```

可选子命令：
- `calculate` - 执行单次坐标变换计算
- `batch` - 批量处理多个数据文件
- `registry` - 管理坐标系注册表

详见 [CLI_HELPERS.md](docs/CLI_HELPERS.md)

#### 2. GUI 图形界面

```bash
# 启动图形界面（需要 PySide6）
python gui.py
```

提供直观的图形界面，支持实时预览和交互式配置。

#### 3. 批量处理

```bash
# 处理整个目录的文件
python batch.py process --input-dir ./data/input --output-dir ./data/output

# 查看批处理帮助
python batch.py --help
```

详见 [BATCH_USAGE.md](docs/BATCH_USAGE.md)

#### 4. Python 脚本调用

```python
from src.data_loader import load_data
from src.physics import AeroCalculator

# 加载配置
proj = load_data('data/input.json')

# 初始化计算器
calc = AeroCalculator(proj)

# 执行计算
result = calc.process_frame([100, 0, 1000], [0, 50, 0])

# 查看结果
print(f"变换后的力: {result.force_transformed}")
print(f"气动系数: {result.coeff_force}, {result.coeff_moment}")
```

**预期输出示例**：
```
Force (N)   : [272.0844, 0.0, 967.4555]
Moment (N*m): [0.0, 550.0, 0.0]
系数 [Cx, Cy, Cz] : [0.0113, 0.0, 0.0403]
系数 [Cl, Cm, Cn]: [0.0, 0.0153, 0.0]
```

## 配置文件格式

`data/input.json` 的示例结构：

```json
{
  "SourceCoordSystem": {
    "Orig": [0.0, 0.0, 0.0],
    "X": [0.9659, 0.0, 0.2588],
    "Y": [0.0, 1.0, 0.0],
    "Z": [-0.2588, 0.0, 0.9659]
  },
  "Target": {
    "PartName": "TestModel",
    "TargetCoordSystem": {
      "Orig": [0.0, 0.0, 0.0],
      "X": [1.0, 0.0, 0.0],
      "Y": [0.0, 1.0, 0.0],
      "Z": [0.0, 0.0, 1.0]
    },
    "TargetMomentCenter": [0.5, 0.0, 0.0],
    "Q": 24000.0,
    "S": 0.024,
    "Cref": 0.15,
    "Bref": 0.3
  }
}
```

**字段说明**：
- `SourceCoordSystem`: 源坐标系定义（原点和三个基向量）
- `TargetCoordSystem`: 目标坐标系定义
- `TargetMomentCenter`: 目标力矩中心位置
- `Q`: 动压（Pa）
- `S`: 参考面积（m²）
- `Cref`: 参考弦长（m）
- `Bref`: 参考展长（m）

## 项目结构

```
MomentTransfer/
├── src/                    # 核心源代码
│   ├── data_loader.py     # 配置文件加载与数据校验
│   ├── geometry.py        # 几何计算（向量、矩阵、坐标变换）
│   ├── physics.py         # 核心物理计算（力矩变换、系数计算）
│   ├── cli_helpers.py     # CLI 辅助函数
│   ├── config.py          # 配置管理
│   ├── logging_system.py  # 日志系统
│   └── models/            # 数据模型
│       └── ...
├── gui/                    # GUI 相关模块
│   ├── main_window.py     # 主窗口
│   ├── panels/            # UI 面板组件
│   └── ...
├── cli.py                 # 命令行主程序
├── batch.py               # 批量处理程序
├── gui.py                 # GUI 启动脚本
├── tests/                 # 单元测试
│   ├── test_*.py          # 各模块测试
│   └── ...
├── docs/                  # 文档
│   ├── CLI_HELPERS.md     # CLI 使用指南
│   ├── BATCH_USAGE.md     # 批处理使用指南
│   └── SPECIAL_FORMAT_PARSER.md
├── data/                  # 数据文件
│   ├── input.json         # 输入配置文件
│   ├── output/            # 输出目录
│   └── ...
├── requirements.txt       # Python 依赖列表
└── README.md             # 本文件
```

## 运行测试

项目包含完整的单元测试，覆盖正常场景和边缘情况：

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_geometry.py -v

# 查看测试覆盖率（需安装 pytest-cov）
pip install pytest-cov
pytest tests/ --cov=src --cov-report=html

# 运行特定的测试
pytest tests/test_cli_click.py::test_cli_structure -v
```

## 使用场景

### 风洞试验数据处理
将风洞天平数据从天平坐标系变换到机体坐标系，并计算气动系数。

### CFD 后处理
处理 CFD 仿真输出的力矩数据，转换到工程坐标系。

### 数据格式转换
将多种数据格式（CSV、JSON、特殊格式）统一转换为标准格式进行处理。

### 批量数据处理
使用批处理功能高效处理大量试验数据。

## 开发指南

### 代码规范
- 遵循 PEP 8 编码规范
- 使用中文注释和文档字符串
- 所有公共函数需包含类型注解
- 变量命名使用 `snake_case`，类名使用 `CamelCase`

### 贡献流程
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交改动 (`git commit -m '[功能] 添加某某特性'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

### 提交信息规范
- `[功能]`: 新增功能，例如 `[功能] 添加坐标系验证`
- `[修复]`: 修复 Bug，例如 `[修复] 修复矩阵计算精度问题`
- `[优化]`: 性能优化或代码重构，例如 `[优化] 提升批处理速度`
- `[文档]`: 文档更新，例如 `[文档] 更新使用指南`
- `[测试]`: 测试相关，例如 `[测试] 添加边界条件测试`

### 环境配置
```bash
# 使用 Anaconda 创建开发环境
conda create -n MomentTransfer python=3.8
conda activate MomentTransfer
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装开发依赖
pip install pytest pytest-cov black pylint -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 代码风格检查
```bash
# 使用 pylint 检查代码质量
pylint src/ --disable=C0111

# 使用 black 格式化代码
black src/ tests/
```

## 常见问题

### Q: 如何选择 GUI、CLI 还是批处理？
**A**: 
- **GUI**: 适合单个或少量文件的交互式操作，提供可视化配置
- **CLI**: 适合脚本集成或单次计算，支持标准输入输出
- **批处理**: 适合大量文件并行处理，提高处理效率

### Q: 为什么会提示"无法归一化零向量"？
**A**: 这说明输入的坐标轴向量为零或接近零。请检查 `input.json` 中的 `X`、`Y`、`Z` 字段，确保它们是有效的非零向量。

### Q: 如何处理自定义的数据格式？
**A**: 可以使用特殊格式解析器或编写自定义的数据加载脚本。详见 [SPECIAL_FORMAT_PARSER.md](docs/SPECIAL_FORMAT_PARSER.md)。

### Q: 动压为零时会发生什么？
**A**: 程序会发出警告并返回零系数，但力和力矩的坐标变换仍然有效。这是正常行为，因为无量纲化需要非零动压。

### Q: 如何处理非正交的坐标系？
**A**: 程序会在初始化时检测非正交基向量并发出警告。虽然可以继续计算，但结果可能不准确。建议检查输入数据。

### Q: 支持哪些 Python 版本？
**A**: 官方支持 Python 3.8-3.12。代码兼容 Python 3.7.9+，但建议使用 3.8 或更高版本。

### Q: 批处理时如何处理错误文件？
**A**: 批处理会自动跳过错误文件并记录日志。使用 `--continue-on-error` 标志可在遇到错误时继续处理。详见 [BATCH_USAGE.md](docs/BATCH_USAGE.md)。

### Q: 如何提高批处理性能？
**A**: 可以调整并发工作进程数：
```bash
python batch.py process --workers 8 --input-dir ./data/input --output-dir ./data/output
```

## 技术细节

### 坐标变换原理
程序使用以下数学公式进行坐标变换：

1. **旋转矩阵**：R = Target_Basis · Source_Basis^T
2. **力变换**：F_target = R · F_source
3. **力矩移轴**：ΔM = r × F，其中 r = Source_Origin - Target_Center
4. **总力矩**：M_target = R · M_source + ΔM
5. **系数计算**：
   - C_F = F / (q × S)
   - C_M[roll] = M[roll] / (q × S × b)
   - C_M[pitch] = M[pitch] / (q × S × c)
   - C_M[yaw] = M[yaw] / (q × S × b)

### 依赖说明
- **numpy**: 用于矩阵运算和向量计算
- **pandas**: 用于数据处理和 CSV 文件处理
- **click**: 用于构建命令行界面
- **PySide6**: 用于 GUI 界面（可选）
- **matplotlib**: 用于数据可视化（可选）
- **pytest**: 单元测试框架
- **portalocker**: 文件锁定，用于并发文件写入
- **openpyxl**: Excel 文件处理（可选）

### 可选依赖
某些高级功能可选安装额外依赖：
```bash
# 安装 GUI 相关依赖
pip install PySide6 matplotlib -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装数据导出依赖
pip install openpyxl xlsxwriter -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 性能考虑

- 单文件处理：快速，毫秒级
- 批处理 1000 个文件：约 10-30 秒（取决于硬件和文件大小）
- 内存使用：每个进程约 50-100 MB
- 支持自定义工作进程数以优化性能


## 相关资源

- [CLI 使用指南](docs/CLI_HELPERS.md)
- [批处理使用指南](docs/BATCH_USAGE.md)
- [特殊格式解析器文档](docs/SPECIAL_FORMAT_PARSER.md)

## 联系方式

- **作者**: least
- **邮箱**: least106@163.com
- **问题反馈**: 提交 Issue 或 Discussion

## 更新日志

### v2.0.0 (2026-01-09)
-  新增完整的 GUI 图形界面
-  实现批量处理功能，支持并行处理
-  增强 CLI 工具，支持交互式配置
-  优化数据加载和格式处理
-  添加数据可视化功能
-  扩展单元测试覆盖
-  完善项目文档

### v1.0.0 (2025-12-22)
-  完成核心功能实现
-  添加完整单元测试
-  实现输入数据校验和错误处理
-  完善项目文档

---

**注意**: 使用前请确保已正确配置输入文件，并检查坐标系定义的正确性。如遇问题，请参考相关文档或提交 Issue。
