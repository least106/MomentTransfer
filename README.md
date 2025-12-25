# MomentTransfer - 气动力矩坐标变换工具

[![Python CI](https://github.com/YOUR_USERNAME/MomentTransfer/workflows/Python%20CI/badge.svg)](https://github.com/YOUR_USERNAME/MomentTransfer/actions)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)

## 项目简介

MomentTransfer 是一个用于航空航天领域的力矩坐标变换计算工具。主要功能包括：

- **坐标系变换**：将力和力矩从源坐标系（如天平坐标系）变换到目标坐标系（如体轴系或风轴系）
- **力矩移轴**：根据力矩中心的变化，自动计算由力产生的附加力矩（r × F）
- **无量纲化**：根据动压、参考面积和参考长度，计算气动力系数和力矩系数

本工具适用于风洞试验数据处理、CFD 后处理等场景。

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

项目提供了一个命令行示例程序：

```bash
python -m src.CL_main
```

程序会读取 `data/input.json` 配置文件，执行计算并将结果保存到 `data/output_result.json`。

**预期输出示例**：
```
[开始] 运行力矩变换程序...
[读取] 配置文件: .../data/input.json
[计算] 坐标系矩阵构建完成。
    - 源坐标系原点: [0.0, 0.0, 0.0]
    - 目标力矩中心: [0.5, 0.0, 0.0]
----------------------------------------
[输入] 原始数据 (Source Frame):
    Force : [100.0, 0.0, 1000.0]
    Moment: [0.0, 50.0, 0.0]
----------------------------------------
[完成] 计算完成 (Target Frame):
    Force (N)   : [272.0844, 0.0, 967.4555]
    Moment (N*m): [0.0, 550.0, 0.0]
----------------------------------------
[系数] 气动系数 (Coefficients):
    Force [Cx, Cy, Cz] : [0.0113, 0.0, 0.0403]
    Moment [Cl, Cm, Cn]: [0.0, 0.0153, 0.0]
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
├── src/
│   ├── data_loader.py      # 配置文件加载与数据校验
│   ├── geometry.py          # 几何计算（向量、矩阵、坐标变换）
│   ├── physics.py           # 核心物理计算（力矩变换、系数计算）
│   ├── CL_main.py          # 命令行示例程序
│   └── gui_main.py         # GUI 界面（可选）
├── tests/
│   ├── test_data_loader.py # 数据加载测试
│   ├── test_geometry.py    # 几何计算测试
│   └── test_physics.py     # 物理计算测试
├── data/
│   ├── input.json          # 输入配置文件
│   └── output_result.json  # 输出结果文件
├── requirements.txt         # Python 依赖列表
└── README.md               # 本文件
```

## 运行测试

项目包含完整的单元测试（36个测试用例），覆盖正常场景和边缘情况：

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_geometry.py -v

# 查看测试覆盖率（需安装 pytest-cov）
pip install pytest-cov
pytest tests/ --cov=src --cov-report=html
```

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
- `[功能]`: 新增功能
- `[修复]`: 修复 Bug
- `[优化]`: 性能优化或代码重构
- `[文档]`: 文档更新
- `[测试]`: 测试相关

## 常见问题

### Q: 为什么会提示"无法归一化零向量"？
**A**: 这说明输入的坐标轴向量为零或接近零。请检查 `input.json` 中的 `X`、`Y`、`Z` 字段，确保它们是有效的非零向量。

### Q: 动压为零时会发生什么？
**A**: 程序会发出警告并返回零系数，但力和力矩的坐标变换仍然有效。这是正常行为，因为无量纲化需要非零动压。

### Q: 如何处理非正交的坐标系？
**A**: 程序会在初始化时检测非正交基向量并发出警告。虽然可以继续计算，但结果可能不准确。建议检查输入数据。

### Q: 支持哪些 Python 版本？
**A**: 官方支持 Python 3.8-3.12。代码兼容 Python 3.7.9+，但建议使用 3.8 或更高版本。

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
- **pytest**: 单元测试框架

### 可选依赖
- **portalocker**: 可选依赖，用于在跨进程/跨平台场景下提供更一致的文件锁定语义。推荐在并发批处理或多进程写入同一输出目录时安装。

安装示例：
```bash
# 使用清华镜像源安装可选依赖
pip install portalocker -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 联系方式

- **作者**: least
- **邮箱**: least106@163.com
- **问题反馈**: [GitHub Issues](https://github.com/YOUR_USERNAME/MomentTransfer/issues)

## 更新日志

### v1.0.0 (2025-12-22)
- ✅ 完成核心功能实现
- ✅ 添加完整单元测试（36个测试用例）
- ✅ 实现输入数据校验和错误处理
- ✅ 添加 CI/CD 工作流
- ✅ 完善项目文档

---

**注意**: 使用前请确保已正确配置 `input.json` 文件，并检查坐标系定义的正确性。
