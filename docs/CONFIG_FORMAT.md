# 配置文件格式

详细的 JSON 配置文件格式说明。

## 文件结构

MomentConversion 使用 JSON 配置文件定义项目和坐标系信息。

```json
{
  "ProjectInfo": {
    "name": "项目名称",
    "description": "项目描述"
  },
  "FrameConfiguration": {
    "SourceFrame": { ... },
    "TargetFrame": { ... },
    "ReferenceArea": 10.5,
    "ReferenceLength": 1.0,
    "DynamicPressure": 500.0
  }
}
```

## 详细说明

### ProjectInfo 段

项目基本信息。

```json
"ProjectInfo": {
  "name": "我的风洞项目",
  "description": "某型飞行器气动力测量"
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 项目名称 |
| `description` | string | 否 | 项目描述 |

### FrameConfiguration 段

坐标系配置和参考参数。

#### SourceFrame 和 TargetFrame

定义源坐标系和目标坐标系。

```json
"SourceFrame": {
  "BODY": [
    {
      "Orig": [0, 0, 0],
      "X": [1, 0, 0],
      "Y": [0, 1, 0],
      "Z": [0, 0, 1]
    }
  ],
  "STAB": [
    {
      "Orig": [0, 0, 0],
      "X": [0.866, 0.5, 0],
      "Y": [-0.5, 0.866, 0],
      "Z": [0, 0, 1]
    }
  ]
}
```

**结构**：
- 第一层：Part 名称（如 "BODY"、"STAB"）
- 第二层：该 Part 的多个变体（数组）
  - `Orig`：原点坐标 (X, Y, Z)
  - `X`、`Y`、`Z`：三个轴方向的单位向量

**说明**：
- 一个 Part 可以有多个变体（如多个工况下的坐标系）
- 第一个变体（索引 0）为默认使用
- 坐标系必须为标准正交基

#### ReferenceArea

参考面积，用于无量纲化。

```json
"ReferenceArea": 10.5
```

| 参数 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `ReferenceArea` | float | m² | 飞行器翼面积或迎风面积 |

#### ReferenceLength

参考长度，用于力矩系数计算。

```json
"ReferenceLength": 1.0
```

| 参数 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `ReferenceLength` | float | m | 飞行器特征长度（如弦长） |

#### DynamicPressure

动压，用于无量纲化。

```json
"DynamicPressure": 500.0
```

| 参数 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `DynamicPressure` | float | Pa | 动压 (Q = 0.5ρV²) |

## 完整示例

### 最小配置

```json
{
  "ProjectInfo": {
    "name": "基础项目"
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
    "ReferenceArea": 1.0,
    "ReferenceLength": 1.0,
    "DynamicPressure": 1.0
  }
}
```

### 完整配置（多 Part，多变体）

```json
{
  "ProjectInfo": {
    "name": "某型飞行器风洞试验",
    "description": "攻角0-90度气动力测量"
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
      ],
      "WING": [
        {
          "Orig": [5, 0, 0],
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
          "X": [0.9848, 0.1736, 0],
          "Y": [-0.1736, 0.9848, 0],
          "Z": [0, 0, 1]
        },
        {
          "Orig": [0, 0, 0],
          "X": [0.9397, 0.3420, 0],
          "Y": [-0.3420, 0.9397, 0],
          "Z": [0, 0, 1]
        }
      ],
      "STAB": [
        {
          "Orig": [0, 0, 0],
          "X": [0.9848, 0.1736, 0],
          "Y": [-0.1736, 0.9848, 0],
          "Z": [0, 0, 1]
        }
      ]
    },
    "ReferenceArea": 122.5,
    "ReferenceLength": 11.25,
    "DynamicPressure": 2500.0
  }
}
```

### 坐标系变换示例

**机体坐标系到风坐标系的 10° 攻角变换**

```json
{
  "ProjectInfo": {
    "name": "10度攻角变换"
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
          "X": [0.9848, 0.1736, 0],
          "Y": [-0.1736, 0.9848, 0],
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

说明：
- cos(10°) ≈ 0.9848
- sin(10°) ≈ 0.1736

## 验证和调试

### 验证配置文件

使用 Python 验证配置的正确性：

```python
from src.data_loader import load_data

try:
    project_data = load_data("config.json")
    print("配置加载成功")
    print(f"坐标系数量：{len(project_data.frame_config.source_frames)}")
except Exception as e:
    print(f"配置加载失败：{e}")
```

### 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `坐标系定义缺少必须字段: X` | 缺少向量定义 | 检查 X、Y、Z、Orig 是否完整 |
| `字段 X 必须包含 3 个元素` | 向量长度不对 | 确保向量为 [x, y, z] 格式 |
| `向量不是单位向量` | 向量长度 ≠ 1 | 标准化向量：v / \|v\| |
| `坐标系不是标准正交基` | 轴向量不正交 | 确保 X⊥Y、Y⊥Z、Z⊥X |

## 最佳实践

1. **单位一致性**
   - 长度：统一使用米 (m)
   - 压力：统一使用帕斯卡 (Pa)
   - 力矩：统一使用牛·米 (N·m)

2. **向量标准化**
   - 确保所有轴向量为单位向量
   - 检查向量之间的正交性

3. **坐标系命名**
   - 使用有意义的英文名称（如 BODY、WIND、STAB）
   - 避免使用特殊字符

4. **参考参数**
   - 根据实际试验条件填写
   - 不要使用默认值（0 或 1）
   - 检查动压单位和数值合理性

5. **版本控制**
   - 将配置文件纳入 Git 管理
   - 为不同工况维护不同的配置文件
   - 使用版本号标记重要变更
