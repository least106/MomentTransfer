"""
特殊格式数据文件解析器
处理包含多个 part 数据块的文件，自动识别 part 名称和数据行
"""
import re
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


def is_metadata_line(line: str) -> bool:
    """判断是否为元数据行（非数据内容的描述行）"""
    line = line.strip()
    if not line:
        return True
    
    # 包含中文冒号或英文冒号的描述行
    if '：' in line or (': ' in line and not line[0].isdigit()):
        return True
    
    # 包含中文字符且不是纯英文单词的行
    if re.search(r'[\u4e00-\u9fff]', line) and '：' not in line:
        # 可能是参数描述行，如"计算坐标系:X向后、Y向右、z向上"
        return True
    
    return False


def is_summary_line(line: str) -> bool:
    """判断是否为汇总行（CLa Cdmin CmCL Cm0 Kmax 等）"""
    line = line.strip()
    if not line:
        return False
    
    # 汇总行特征：首个token不是数字，且包含特定关键词
    tokens = line.split()
    if not tokens:
        return False
    
    first_token = tokens[0]
    # 如果第一个token不像数字（不是负号开头或纯数字）
    if not (first_token.replace('-', '').replace('.', '').replace('+', '').isdigit()):
        # 检查是否包含典型的汇总指标名
        summary_keywords = ['CLa', 'Cdmin', 'CmCL', 'Cm0', 'Kmax', 'Alpha']
        if any(kw in line for kw in summary_keywords):
            return True
    
    return False


def is_data_line(line: str) -> bool:
    """判断是否为数据行（以数字开头的行）"""
    line = line.strip()
    if not line:
        return False
    
    tokens = line.split()
    if not tokens:
        return False
    
    first_token = tokens[0]
    # 数据行特征：第一个token是数字（可能带负号）
    try:
        float(first_token)
        return True
    except ValueError:
        return False


def is_part_name_line(line: str, next_line: Optional[str] = None) -> bool:
    """
    判断是否为 part 名称行
    特征：
    1. 单独一行，内容简短
    2. 可能是纯英文单词或中文
    3. 下一行很可能是表头（包含 Alpha, CL, CD 等）
    """
    line = line.strip()
    if not line:
        return False
    
    # 如果是元数据行或汇总行，肯定不是 part 名
    if is_metadata_line(line) or is_summary_line(line):
        return False
    
    # 如果是数据行，肯定不是 part 名
    if is_data_line(line):
        return False
    
    # part 名特征：简短的文本（通常少于20个字符）
    tokens = line.split()
    if len(tokens) == 1 and len(line) < 20:
        # 如果下一行是表头，更有可能是 part 名
        if next_line:
            next_tokens = next_line.split()
            header_keywords = ['Alpha', 'CL', 'CD', 'Cm', 'Cx', 'Cy', 'Cz']
            if any(kw in next_tokens for kw in header_keywords):
                return True
        return True
    
    return False


def parse_special_format_file(file_path: Path) -> Dict[str, pd.DataFrame]:
    """
    解析特殊格式文件，返回 {part_name: DataFrame} 字典
    
    Args:
        file_path: 文件路径
        
    Returns:
        字典，键为 part 名称，值为对应的 DataFrame
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    result = {}
    current_part = None
    current_header = None
    current_data = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # 跳过空行
        if not line:
            i += 1
            continue
        
        # 跳过元数据行
        if is_metadata_line(line):
            i += 1
            continue
        
        # 检查是否为 part 名称
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else None
        if is_part_name_line(line, next_line):
            # 保存上一个 part 的数据
            if current_part and current_header and current_data:
                try:
                    df = pd.DataFrame(current_data, columns=current_header)
                    # 转换数值列
                    for col in df.columns:
                        try:
                            df[col] = pd.to_numeric(df[col])
                        except:
                            pass
                    result[current_part] = df
                    logger.info(f"解析 part '{current_part}': {len(df)} 行数据")
                except Exception as e:
                    logger.warning(f"创建 DataFrame 失败 (part={current_part}): {e}")
            
            # 开始新的 part
            current_part = line
            current_header = None
            current_data = []
            i += 1
            continue
        
        # 检查是否为表头行（包含 Alpha, CL 等关键词）
        if current_part and not current_header:
            tokens = line.split()
            header_keywords = ['Alpha', 'CL', 'CD', 'Cm', 'Cx', 'Cy', 'Cz']
            if any(kw in tokens for kw in header_keywords):
                current_header = tokens
                i += 1
                continue
        
        # 检查是否为数据行
        if current_part and current_header and is_data_line(line):
            tokens = line.split()
            if len(tokens) == len(current_header):
                current_data.append(tokens)
            else:
                logger.debug(f"数据行列数不匹配，跳过: {line[:50]}")
            i += 1
            continue
        
        # 检查是否为汇总行（跳过）
        if is_summary_line(line):
            i += 1
            continue
        
        # 其他情况：跳过
        i += 1
    
    # 保存最后一个 part 的数据
    if current_part and current_header and current_data:
        try:
            df = pd.DataFrame(current_data, columns=current_header)
            for col in df.columns:
                try:
                    df[col] = pd.to_numeric(df[col])
                except:
                    pass
            result[current_part] = df
            logger.info(f"解析 part '{current_part}': {len(df)} 行数据")
        except Exception as e:
            logger.warning(f"创建 DataFrame 失败 (part={current_part}): {e}")
    
    return result


def get_part_names(file_path: Path) -> List[str]:
    """
    快速获取文件中的所有 part 名称（不解析完整数据）
    
    Args:
        file_path: 文件路径
        
    Returns:
        part 名称列表
    """
    part_names = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if not line or is_metadata_line(line):
            i += 1
            continue
        
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else None
        if is_part_name_line(line, next_line):
            part_names.append(line)
        
        i += 1
    
    return part_names


if __name__ == '__main__':
    # 测试
    logging.basicConfig(level=logging.INFO)
    
    test_file = Path('data/data_tmp')
    if test_file.exists():
        print(f"解析文件: {test_file}")
        
        # 获取 part 名称
        parts = get_part_names(test_file)
        print(f"\n找到 {len(parts)} 个 part:")
        for p in parts:
            print(f"  - {p}")
        
        # 解析完整数据
        data_dict = parse_special_format_file(test_file)
        print(f"\n解析结果:")
        for part_name, df in data_dict.items():
            print(f"\n{part_name}:")
            print(df.head())
            print(f"  形状: {df.shape}")
