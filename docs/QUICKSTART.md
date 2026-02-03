# 快速开始指南

本指南将帮助您快速上手 MomentConversion 工具。

## 前置条件

- Python 3.8 或更高版本
- Anaconda 或 Miniconda（推荐）
- Git

## 第一步：环境设置

### 使用 Conda 创建环境

```powershell
# 克隆仓库
git clone https://github.com/least106/MomentConversion.git
cd MomentConversion

# 创建虚拟环境
conda env create -f environment.yml

# 激活环境
conda activate MomentConversion
```

### 或手动配置

```powershell
# 创建虚拟环境
conda create -n MomentConversion python=3.8

# 激活环境
conda activate MomentConversion

# 安装依赖
pip install -r requirements.txt
pip install -e .
```

## 第二步：准备配置文件

配置文件使用 JSON 格式，定义坐标系、参考参数等。

```json
{
  "ProjectInfo": {
    "name": "我的项目",
    "description": "测试配置"
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
          "X": [0.866, 0.5, 0],
          "Y": [-0.5, 0.866, 0],
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

保存为 `config.json`。

## 第三步：选择使用方式

### 方式 1：命令行工具（CLI）

**单点计算**

```bash
python cli.py run -c config.json \
  --force 100 0 -50 \
  --moment 0 500 0
```

**输出到文件**

```bash
python cli.py run -c config.json \
  --force 100 0 -50 \
  --moment 0 500 0 \
  -o result.json
```

### 方式 2：批处理（Batch）

准备 CSV 文件 `data.csv`：

```csv
时间,力X,力Y,力Z,力矩X,力矩Y,力矩Z
0,100,0,-50,0,500,0
1,110,5,-45,10,510,5
2,105,-3,-55,-5,490,-10
```

执行批处理：

```bash
python batch.py -c config.json \
  -i data.csv \
  -o result.csv \
  --force-column 力 \
  --moment-column 力矩
```

### 方式 3：图形界面（GUI）

```bash
python gui_main.py
```

启动 GUI 后：
1. 点击"加载配置"选择 JSON 配置文件
2. 配置 Source 和 Target Part
3. 选择输入文件进行批处理
4. 查看结果和处理历史

## 常见操作

### 验证安装

```bash
# 运行测试
pytest tests/

# 检查代码质量
pylint src/
black src/ --check
```

### 检查日志

批处理时会自动生成日志。检查 `logs/` 目录：

```bash
# 查看最新日志
Get-Content logs/* -Tail 50
```

### 性能优化

如果处理大文件，调整 `src/config.py` 中的批处理配置：

```python
# src/config.py
@dataclass
class BatchProcessConfig:
    chunk_size: int = 50000  # 增大块大小以加快处理
    treat_non_numeric: str = DataTreatmentStrategy.DROP.value
```

## 故障排查

### 问题：找不到配置文件

```
Error: 配置文件未找到: config.json
```

**解决**：确保配置文件路径正确，使用绝对路径或相对路径。

```bash
python cli.py run -c ./data/config.json --force 100 0 -50 --moment 0 500 0
```

### 问题：部分列名不匹配

```
Error: 未找到列: 力X, 力Y, 力Z
```

**解决**：检查 CSV 文件中的实际列名，使用 `--force-column` 正确指定。

```bash
python batch.py -c config.json -i data.csv -o result.csv \
  --force-column "Force" --moment-column "Moment"
```

### 问题：GUI 启动缓慢或卡顿

**解决**：
1. 确保系统资源充足（内存 > 2GB，CPU 可用）
2. 关闭其他应用程序
3. 更新 PyQt6：`pip install --upgrade PySide6`

## 下一步

- 查看[用户手册](USER_GUIDE.md)了解更多功能
- 阅读[配置文件格式](CONFIG_FORMAT.md)学习高级配置
- 参考[API 文档](API.md)进行二次开发
- 查看[开发者指南](DEVELOPER_GUIDE.md)参与贡献
