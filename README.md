# MomentConversion

[![Tests](https://github.com/least106/MomentConversion/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/least106/MomentConversion/actions/workflows/test.yml)
[![Code Style](https://github.com/least106/MomentConversion/actions/workflows/lint.yml/badge.svg?branch=main)](https://github.com/least106/MomentConversion/actions/workflows/lint.yml)
[![Code Quality](https://github.com/least106/MomentConversion/actions/workflows/quality.yml/badge.svg?branch=main)](https://github.com/least106/MomentConversion/actions/workflows/quality.yml)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
**MomentConversion** 是一个专业的气动力/力矩坐标变换与系数计算工具，主要用于风洞试验数据的坐标系转换和无量纲化计算。支持批量处理、命令行操作和可视化 GUI 界面。

## ✨ 主要特性

- 🔄 **坐标系变换**：支持任意坐标系之间的力和力矩转换
- 📊 **批量处理**：高效处理大规模风洞试验数据，支持并行计算
- 🎨 **可视化界面**：友好的 GUI 界面，项目管理和实时预览
- 🔌 **插件系统**：支持自定义坐标系和输出格式扩展
- 📝 **特殊格式支持**：自动检测和解析专有二进制数据格式
- ⚡ **性能优化**：缓存机制和并行处理，提升计算效率
- 🧪 **高测试覆盖率**：85%+ 测试覆盖率，保证代码质量

## 📋 系统要求

- **Python 版本**：3.8+ (最低兼容 3.7.9)
- **操作系统**：Windows / Linux / macOS
- **推荐环境**：Anaconda 或 Miniconda

## 🚀 快速开始

### 安装

#### 方式一：使用 conda（推荐）

```powershell
# 克隆仓库
git clone https://github.com/least106/MomentConversion.git
cd MomentConversion

# 创建 conda 环境
conda env create -f environment.yml
conda activate MomentConversion

# 安装依赖
pip install -r requirements.txt
```

#### 方式二：使用 pip

```powershell
# 克隆仓库
git clone https://github.com/least106/MomentConversion.git
cd MomentConversion

# 创建虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows PowerShell

# 安装依赖
pip install -r requirements.txt
```

> **提示**：国内用户建议使用清华镜像加速：
> ```powershell
> pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

### 基本使用

#### 1. GUI 界面（推荐新手）

启动可视化界面：

```powershell
conda activate MomentConversion
python gui_main.py
```

GUI 功能包括：
- 项目配置管理
- 坐标系可视化编辑
- 批量任务处理
- 实时数据预览
- 历史记录查看

#### 2. 批量处理

使用命令行进行批量数据处理：

```powershell
conda activate MomentConversion
python batch.py -c data/input.json -i data/loads.csv -o result.csv
```

**参数说明**：
- `-c, --config`：配置文件路径（JSON 格式）
- `-i, --input`：输入数据文件（CSV 或专有格式）
- `-o, --output`：输出结果文件路径
- `--source-part`：源坐标系名称（可选）
- `--target-part`：目标坐标系名称（多目标时必需）
- `--workers`：并行处理进程数（默认为 CPU 核心数）

**示例**：

```powershell
# 基本用法
python batch.py -c config.json -i forces.csv -o results.csv

# 指定源和目标坐标系
python batch.py -c config.json -i forces.csv -o results.csv --source-part WING --target-part BODY

# 使用 4 个进程并行处理
python batch.py -c config.json -i forces.csv -o results.csv --workers 4
```

#### 3. 交互式命令行

单点调试和快速验证：

```powershell
conda activate MomentConversion
python cli.py
```

交互式输入力和力矩数据，实时查看计算结果。

## 📖 配置文件格式

配置文件使用 JSON 格式，定义坐标系和参考量：

```json
{
  "project_name": "风洞试验A",
  "description": "某型号风洞试验数据处理",
  "source_parts": [
    {
      "part_name": "WING",
      "coord_system": {
        "origin": [0, 0, 0],
        "x_axis": [1, 0, 0],
        "y_axis": [0, 1, 0],
        "z_axis": [0, 0, 1]
      },
      "moment_center": [0.25, 0, 0],
      "reference_area": 1.5,
      "reference_length": 1.0,
      "reference_span": 2.0
    }
  ],
  "target_parts": [
    {
      "part_name": "BODY",
      "coord_system": {
        "origin": [0, 0, 0],
        "x_axis": [1, 0, 0],
        "y_axis": [0, 1, 0],
        "z_axis": [0, 0, 1]
      },
      "moment_center": [0, 0, 0],
      "reference_area": 2.0,
      "reference_length": 1.2,
      "reference_span": 2.4
    }
  ],
  "dynamic_pressure": 1000.0
}
```

**关键字段说明**：
- `part_name`：坐标系名称（唯一标识）
- `coord_system`：坐标系定义（原点和三轴方向）
- `moment_center`：力矩中心位置
- `reference_area`：参考面积（用于计算力系数）
- `reference_length`：参考长度（用于计算纵向力矩系数）
- `reference_span`：参考展长（用于计算横向力矩系数）
- `dynamic_pressure`：动压（用于无量纲化）

## 🏗️ 项目架构

### 核心模块

```
src/
├── data_loader.py          # 配置文件加载和数据结构
├── physics.py              # 核心物理计算（AeroCalculator）
├── calculator_factory.py   # 计算器工厂，简化初始化
├── cache.py                # 缓存机制，优化性能
├── batch_config.py         # 批量处理配置
├── special_format_*.py     # 特殊格式检测、解析、处理
└── plugin.py               # 插件系统
```

### GUI 模块

```
gui/
├── main_window.py          # 主窗口
├── managers.py             # 核心管理器（ModelManager 等）
├── part_manager.py         # 坐标系管理
├── project_manager.py      # 项目管理
├── batch_manager.py        # 批量任务管理
├── event_manager.py        # 事件总线
└── panels/                 # UI 面板组件
```

### 计算流程

```
输入数据 → 坐标系旋转 → 力矩移轴变换 → 无量纲化 → 输出结果
```

1. **坐标系旋转**：将力和力矩从源坐标系旋转到目标坐标系
2. **力矩移轴**：根据力矩中心差异进行力矩修正
3. **无量纲化**：使用动压和参考量计算气动系数

## 🔧 开发指南

### 环境配置

```powershell
# 激活开发环境
conda activate MomentConversion

# 安装开发依赖
pip install -r requirements-dev.txt
```

### 代码规范

项目遵循 **PEP 8** 规范，使用以下工具保证代码质量：

```powershell
# 代码格式化
python -m black src/ tests/ gui/ gui_main.py batch.py examples/
python -m isort src/ tests/ gui/ gui_main.py batch.py examples/

# 代码检查
python -m pylint src/ --output-format=text

# 运行测试
python -m pytest -q --cov=src --cov-report=term
```

### 测试要求

- **测试覆盖率**：≥ 80%（当前 85%）
- **测试框架**：pytest
- **覆盖范围**：单元测试、集成测试、边界条件测试

运行测试：

```powershell
# 运行所有测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=src --cov-report=html

# 运行特定测试文件
pytest tests/test_physics.py
```

### CI/CD 检查

每次提交会自动运行以下检查：

- ✅ **Black 格式检查**：代码格式必须符合 Black 规范
- ✅ **Isort 导入排序**：导入语句按规范排序
- ✅ **Pylint 代码质量**：评分 ≥ 7.0（当前 9.95）
- ✅ **完整测试套件**：所有测试必须通过

### 插件开发

创建自定义插件（以坐标系插件为例）：

```python
# plugins/my_custom_coord.py
from src.plugin import CoordSystemPlugin

class MyCustomCoordSystem(CoordSystemPlugin):
    """自定义坐标系插件"""
    
    def get_name(self):
        return "my_custom_coord"
    
    def get_transformation_matrix(self, source_config, target_config):
        # 实现自定义变换矩阵
        return transformation_matrix
```

## 📊 性能优化

- **缓存机制**：旋转矩阵和变换矩阵使用 `@lru_cache` 缓存
- **并行处理**：批量任务使用 `ProcessPoolExecutor` 多进程并行
- **内存优化**：大数据集分块处理，避免内存溢出
- **文件哈希**：避免重复计算相同文件

## 🐛 常见问题

### 1. 动压为零警告

**问题**：计算时提示"动压为零"警告。

**原因**：配置文件中 `dynamic_pressure` 设置为 0。

**解决**：在配置文件中设置正确的动压值。

### 2. 多目标坐标系错误

**问题**：提示"必须指定 target_part"。

**原因**：配置文件包含多个目标坐标系，但未指定使用哪个。

**解决**：在命令行使用 `--target-part` 参数或在 GUI 中选择目标坐标系。

### 3. 环境激活失败

**问题**：无法激活 conda 环境。

**原因**：Anaconda 未正确安装或环境未创建。

**解决**：
```powershell
# 重新创建环境
conda env create -f environment.yml -n MomentConversion
conda activate MomentConversion
```

### 4. 导入错误

**问题**：运行时提示模块导入错误。

**原因**：依赖包未安装或版本不匹配。

**解决**：
```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 📄 许可证

本项目采用 [MIT License](LICENSE)。

## 🤝 贡献指南

欢迎贡献代码！请遵循以下流程：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m '[功能] 添加某某特性'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

**提交规范**：
- 使用中文提交信息
- 格式：`[功能/修复/优化] + 描述`
- 示例：`[功能] 添加用户登录功能`

## 📧 联系方式

- **作者**：least10
- **邮箱**：least106@163.com
- **项目地址**：[https://github.com/least106/MomentConversion](https://github.com/least106/MomentConversion)

## 🙏 致谢

感谢所有为本项目做出贡献的开发者！

---

**MomentConversion** - 让气动力数据处理更简单！ 🚀