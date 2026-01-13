# -*- coding: utf-8 -*-
"""
针对 `src.special_format_parser` 的单元测试。
包含：
- `is_part_name_line` 的中/英/边界场景测试
- `parse_special_format_file` 的基本解析流程测试（含表头与数据行）
- `_process_single_part` 的集成行为测试（通过 monkeypatch 替换 AeroCalculator）

测试实现以中文注释，便于维护。
"""

from pathlib import Path
import pandas as pd
import numpy as np
import builtins

import pytest

from src import special_format_parser as sfp


def test_is_part_name_line_short_single_token():
    """短单词单 token 应判定为 part 名。"""
    assert sfp.is_part_name_line("wing1") is True
    # 中文短词也应判定为 part
    assert sfp.is_part_name_line("机翼") is True


def test_is_part_name_line_long_or_multi_token_with_header():
    """多 token 或较长文本：仅当下一行是表头时判定为 part 名。"""
    line = "Wing A"
    next_line = "Alpha CL CD"
    assert sfp.is_part_name_line(line, next_line) is True

    # 多 token 且下一行不是表头，则按中文/非中文规则决定
    assert sfp.is_part_name_line("Wing A", "Some summary") is True

    # 中文长描述（超过20）应被视为非 part
    long_chinese = (
        "这是一个非常非常长的描述文本，用来测试是否超过二十个字符并被判定为描述"
    )
    assert sfp.is_part_name_line(long_chinese, "Alpha CL") is False


def test_parse_special_format_file_basic(tmp_path):
    """创建一个临时特殊格式文件，验证 parse 能正确提取 part 与 DataFrame。"""
    content_lines = [
        "元数据: 这是文件说明",
        "PartOne",
        "Alpha Cx Cy Cz/FN CMx CMy CMz",
        "1 0.1 0.2 0.3 0.01 0.02 0.03",
        "2 0.11 0.21 0.31 0.011 0.021 0.031",
    ]
    file_path = tmp_path / "test1.mtfmt"
    file_path.write_text("\n".join(content_lines), encoding="utf-8")

    data = sfp.parse_special_format_file(file_path)
    assert isinstance(data, dict)
    assert "PartOne" in data
    df = data["PartOne"]
    assert isinstance(df, pd.DataFrame)
    # 列名应被标准化，如 'Cx','Cy','Cz/FN','CMx','CMy','CMz'
    for col in ["Cx", "Cy", "Cz/FN", "CMx", "CMy", "CMz"]:
        assert col in df.columns
    assert df.shape[0] == 2


def test__process_single_part_writes_output(tmp_path, monkeypatch):
    """用 monkeypatch 替换 AeroCalculator，使 _process_single_part 能运行并写出文件。"""
    part_name = "PartX"
    # 构造简单 DataFrame，包含必需列
    df = pd.DataFrame(
        {
            "Cx": [0.1, 0.2],
            "Cy": [0.2, 0.3],
            "Cz/FN": [0.3, 0.4],
            "CMx": [0.01, 0.02],
            "CMy": [0.02, 0.03],
            "CMz": [0.03, 0.04],
        }
    )

    file_path = tmp_path / "srcfile.mtfmt"
    file_path.write_text("dummy", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    # 构造最小化的 project_data，使得 source_parts/target_parts 校验通过
    class PD:
        source_parts = {part_name: {}}
        target_parts = {part_name: {}}

    project_data = PD()

    # monkeypatch AeroCalculator，使其返回与输入行数匹配的零数据
    class DummyCalc:
        def __init__(self, *args, **kwargs):
            pass

        def process_batch(self, forces, moments):
            n = forces.shape[0]
            zero3 = np.zeros((n, 3))
            return {
                "force_transformed": zero3,
                "moment_transformed": zero3,
                "coeff_force": zero3,
                "coeff_moment": zero3,
            }

    monkeypatch.setattr(sfp, "AeroCalculator", DummyCalc)

    out_path, report = sfp._process_single_part(
        part_name, df, file_path, project_data, output_dir, overwrite=True
    )

    assert out_path is not None
    assert out_path.exists()
    assert report.get("status") == "success"

    # 检查输出文件包含期望的新增列
    out_df = pd.read_csv(out_path)
    for col in ["Fx_new", "Fy_new", "Fz_new", "Mx_new", "My_new", "Mz_new"]:
        assert col in out_df.columns


if __name__ == "__main__":
    pytest.main(["-q", "tests/test_special_format_parser.py"])
