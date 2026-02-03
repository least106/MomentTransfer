# MomentConversion

[![Tests](https://github.com/least106/MomentConversion/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/least106/MomentConversion/actions/workflows/test.yml)
[![Code Style](https://github.com/least106/MomentConversion/actions/workflows/lint.yml/badge.svg?branch=main)](https://github.com/least106/MomentConversion/actions/workflows/lint.yml)
[![Code Quality](https://github.com/least106/MomentConversion/actions/workflows/quality.yml/badge.svg?branch=main)](https://github.com/least106/MomentConversion/actions/workflows/quality.yml)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)

坐标系间的力/力矩变换与气动力系数计算工具。支持 CLI 单点计算、批量文件处理和图形化交互界面。

## 🎯 主要功能

- **坐标系变换**：支持三维空间中不同坐标系间的力和力矩转换
- **气动系数计算**：无量纲化处理，转换为标准气动系数
- **多入口支持**：
  - 📟 **CLI**：命令行单点计算
  - 📦 **批处理**：大批量文件处理（支持特殊数据格式）
  - 🖥️ **GUI**：PyQt6 交互式界面
- **性能优化**：LRU 缓存加速重复计算
- **灵活配置**：JSON 配置文件管理项目和坐标系信息

## 📦 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/least106/MomentConversion.git
cd MomentConversion

# 使用 conda 创建环境
conda env create -f environment.yml
conda activate MomentConversion

# 安装开发依赖
pip install -e .
pip install -r requirements-dev.txt
```

### 基本使用

#### 1. CLI - 单点计算

```bash
# 基本用法：指定配置、力和力矩向量
python cli.py run -c data/input.json \
  --force 100 0 -50 \
  --moment 0 500 0

# 输出结果到 JSON 文件
python cli.py run -c data/input.json \
  --force 100 0 -50 \
  --moment 0 500 0 \
  -o result.json
```

#### 2. 批处理 - 文件处理

```bash
# 处理 CSV 文件
python batch.py -c data/input.json \
  -i data/loads.csv \
  -o data/result.csv

# 指定力和力矩列前缀
python batch.py -c data/input.json \
  -i data/loads.csv \
  -o data/result.csv \
  --force-column 力 \
  --moment-column 力矩
```

#### 3. GUI - 交互式界面

```bash
python gui_main.py
```

功能包括：
- 配置加载和编辑
- 文件批处理
- 处理历史记录
- 结果预览

## 📋 文档导航

| 文档 | 说明 |
|------|------|
| [快速开始指南](docs/QUICKSTART.md) | 详细的快速开始步骤 |
| [用户手册](docs/USER_GUIDE.md) | 三个入口的详细使用说明 |
| [开发者指南](docs/DEVELOPER_GUIDE.md) | 架构、开发工作流、常见修改模式 |
| [API 文档](docs/API.md) | 核心模块的 API 参考 |
| [配置文件格式](docs/CONFIG_FORMAT.md) | JSON 配置文件详细说明 |
| [贡献指南](docs/CONTRIBUTING.md) | 代码提交、测试、代码风格要求 |

## 🏗️ 项目结构

```
MomentConversion/
├── src/                          # 核心库代码
│   ├── physics.py               # 物理计算引擎（AeroCalculator）
│   ├── data_loader.py           # 配置加载和数据结构
│   ├── execution.py             # 统一执行上下文和引擎
│   ├── batch_processor.py       # 批处理接口
│   ├── validator.py             # 输入校验
│   ├── cache.py                 # 缓存系统
│   └── special_format_*.py      # 特殊格式处理
├── gui/                          # 图形界面
│   ├── main_window.py           # 主窗口
│   ├── signal_bus.py            # 中央信号总线
│   ├── managers.py              # UI 管理器
│   ├── batch_manager*.py        # 批处理 UI 逻辑
│   └── panels/                  # 功能面板
├── tests/                        # 单元测试和集成测试
├── data/                         # 示例配置和数据
├── cli.py                        # CLI 入口
├── batch.py                      # 批处理入口
├── gui_main.py                   # GUI 入口
└── docs/                         # 项目文档
```

## 🧪 测试

运行所有测试：

```bash
pytest tests/
```

运行特定测试：

```bash
pytest tests/test_physics.py -v
```

生成覆盖率报告：

```bash
pytest tests/ --cov=src --cov-report=html
```

## 🔍 代码质量

检查代码风格和质量：

```bash
# 代码格式检查
black src/ gui/ --check

# 导入排序检查
isort src/ gui/ --check-only

# 代码质量分析
pylint src/ gui/
```

## 🔧 配置示例

项目配置采用 JSON 格式，包含坐标系定义和参考参数。示例配置见 `data/input.json`。

```json
{
  "ProjectInfo": {
    "name": "示例项目",
    "description": "坐标系变换配置"
  },
  "FrameConfiguration": {
    "SourceFrame": {
      "BODY": [
        {
          "Orig": [0, 0, 0],
          "X": [1, 0, 0],
          "Y": [0, 1, 0],
          "Z": [0, 0, 1]
        }
      ]
    },
    "TargetFrame": {
      "WIND": [
        {
          "Orig": [0, 0, 0],
          "X": [1, 0, 0],
          "Y": [0, 1, 0],
          "Z": [0, 0, 1]
        }
      ]
    },
    "ReferenceArea": 10.5,
    "ReferenceLength": 1.0,
    "DynamicPressure": 500.0
  }
}
```

## 📊 依赖

- **Python**: 3.8+
- **NumPy**: 数值计算
- **Pandas**: 数据处理
- **Click**: CLI 框架
- **PySide6**: GUI 框架
- **pytest**: 测试框架
- **black, pylint, isort**: 代码质量工具
