# 特殊格式数据文件解析器

## 功能说明

`src/special_format_parser.py` 提供了针对特殊格式数据文件的智能解析功能，能够：

1. **自动跳过元数据行**：识别并忽略文件开头的描述性文本（如"计算坐标系:X向后、Y向右、z向上"）
2. **智能识别 part 名称**：自动检测用户自定义的 part 名称（如 quanji、BODY、DUAHUI 等）
3. **过滤汇总行**：自动跳过 CLa、Cdmin、CmCL 等汇总统计行
4. **结构化输出**：将每个 part 的数据解析为 pandas DataFrame

## 文件格式示例

```
计算坐标系:X向后、Y向右、z向上
计算Ma:1.4 计算H:10000m 计算侧滑角:0°
参考面积:9.73m2 纵向参考长度:2.548m 横向参考长度:8.5m 参考重心:6.97m
quanji
Alpha CL CD Cm Cc Cn C1 K CDp CDv Swet Cx Cy Cz/FN CMx CMy CMz
-2.00 -0.10625 0.03809 0.00626 0.03059 -0.01136 0.01894 -2.78977 0.03161 0.00658 36.52923 0.03436 0.03059 -0.10751 -0.01894 0.00626 0.01136
0.00 0.00652 0.03443 -0.02196 0.02898 -0.01158 -0.00198 0.18941 0.02786 0.00667 36.52923 0.03443 0.02898 0.00652 0.00198 -0.02196 0.01158
CLa Cdmin CmCL Cm0 Kmax
0.05638 0.03443 -0.25025 -0.02033 5.01666

BODY
Alpha CL CD Cm Cc Cn C1 K CDp CDv Swet Cx Cy Cz/FN CMx CMy CMz
-2.00 -0.03869 0.02362 -0.00061 0.02961 -0.01279 0.00106 -1.63808 0.02046 0.00316 18.74060 0.02225 0.02961 -0.03949 -0.00106 -0.00061 0.01279
```

## 使用方法

### 1. 基本使用

```python
from pathlib import Path
from src.special_format_parser import parse_special_format_file, get_part_names

# 解析文件
file_path = Path('data/data_tmp')
data_dict = parse_special_format_file(file_path)

# data_dict 结构: {'quanji': DataFrame, 'BODY': DataFrame, ...}
for part_name, df in data_dict.items():
    print(f"Part: {part_name}")
    print(f"  行数: {len(df)}")
    print(f"  列数: {len(df.columns)}")
    print(df.head())
```

### 2. 快速获取 part 名称列表

```python
from src.special_format_parser import get_part_names

parts = get_part_names(Path('data/data_tmp'))
print(f"找到的 part: {parts}")
# 输出: ['quanji', 'BODY', 'DUAHUI', 'WING', 'YAYI']
```

### 3. 在批处理中使用

```python
from src.special_format_parser import parse_special_format_file
from src.physics import AeroCalculator

# 解析文件
data_dict = parse_special_format_file(file_path)

# 假设你的 ProjectData 中有对应的 Target part
for part_name, df in data_dict.items():
    # 检查配置中是否有对应的 Target part
    if part_name in project_data.Target:
        calculator = AeroCalculator(project_data)
        
        # 处理每一行数据
        for idx, row in df.iterrows():
            # 提取力和力矩（根据实际列名调整）
            force = [row['Cx'], row['Cy'], row['Cz/FN']]  # 示例
            moment = [row['CMx'], row['CMy'], row['CMz']]  # 示例
            
            result = calculator.process_frame(force, moment)
            # 处理结果...
```

## API 参考

### `parse_special_format_file(file_path: Path) -> Dict[str, pd.DataFrame]`

解析特殊格式文件，返回字典。

**参数：**
- `file_path`: 文件路径（Path 对象）

**返回：**
- 字典，键为 part 名称（字符串），值为对应的 DataFrame

**示例：**
```python
data_dict = parse_special_format_file(Path('data/data_tmp'))
# {'quanji': DataFrame(...), 'BODY': DataFrame(...), ...}
```

### `get_part_names(file_path: Path) -> List[str]`

快速获取文件中的所有 part 名称，不解析完整数据。

**参数：**
- `file_path`: 文件路径（Path 对象）

**返回：**
- part 名称列表

**示例：**
```python
parts = get_part_names(Path('data/data_tmp'))
# ['quanji', 'BODY', 'DUAHUI', 'WING', 'YAYI']
```

## 解析规则

### 元数据行识别规则

以下情况会被识别为元数据行并跳过：
- 空行
- 包含中文或英文冒号的描述行
- 包含中文字符的参数说明行

### Part 名称识别规则

满足以下条件会被识别为 part 名称：
- 单独一行，内容简短（少于 20 字符）
- 不是数字开头的行
- 下一行包含典型的表头关键词（Alpha, CL, CD, Cm 等）

### 数据行识别规则

满足以下条件会被识别为数据行：
- 第一个 token 可以转换为浮点数（可能带负号）
- 列数与表头一致

### 汇总行识别规则

满足以下条件会被识别为汇总行并跳过：
- 第一个 token 不是数字
- 包含 CLa、Cdmin、CmCL、Cm0、Kmax 等关键词

## 注意事项

1. **编码**：文件默认使用 UTF-8 编码读取
2. **列分隔符**：使用空白字符（空格/制表符）分隔
3. **数值转换**：所有可能的列都会尝试转换为数值类型
4. **Part 名称**：支持中文和英文，大小写敏感
5. **容错性**：列数不匹配的数据行会被跳过并记录日志

## 测试

运行测试：
```bash
conda activate MomentTransfer
python src/special_format_parser.py
```

## 故障排查

### Q: 某个 part 没有被识别？

A: 检查：
1. part 名称是否单独一行
2. part 名称后是否紧跟表头行（包含 Alpha, CL 等）
3. 是否有意外的空格或特殊字符

### Q: 数据行被跳过？

A: 检查：
1. 数据行列数是否与表头一致
2. 第一列是否为有效数字
3. 查看日志中的警告信息

### Q: 汇总行没有被过滤？

A: 如果汇总行格式特殊，可以修改 `is_summary_line()` 函数添加自定义关键词。
