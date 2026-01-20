import math
import os

import numpy as np
import pandas as pd
import pytest

from src.validator import (
    DataValidator,
    ValidationError,
    validate_coordinates,
    validate_numeric,
)


def test_validate_coordinate_success_and_errors():
    assert DataValidator.validate_coordinate([1, 2, 3]) == (1.0, 2.0, 3.0)
    arr = np.array([4.0, 5.0, 6.0])
    assert DataValidator.validate_coordinate(arr) == (4.0, 5.0, 6.0)

    with pytest.raises(ValidationError):
        DataValidator.validate_coordinate([1, 2])

    with pytest.raises(ValidationError):
        DataValidator.validate_coordinate(np.array([[1, 2, 3]]))

    with pytest.raises(ValidationError):
        DataValidator.validate_coordinate([1, math.nan, 3])


def test_validate_numeric_range_cases():
    assert DataValidator.validate_numeric_range(3, min_val=0, max_val=10) == 3.0

    with pytest.raises(ValidationError):
        DataValidator.validate_numeric_range("not-a-number")

    with pytest.raises(ValidationError):
        DataValidator.validate_numeric_range(100, max_val=10)

    with pytest.raises(ValidationError):
        DataValidator.validate_numeric_range(math.inf)


def test_validate_file_path_traversal_and_nonexist(tmp_path):
    # 路径遍历
    with pytest.raises(ValidationError):
        DataValidator.validate_file_path("..\\secret.txt")

    # 不存在的文件
    with pytest.raises(ValidationError):
        DataValidator.validate_file_path(str(tmp_path / "nope.txt"), must_exist=True)


def test_validate_csv_safety_size(tmp_path):
    p = tmp_path / "big.csv"
    # 写入较大内容以超过阈值
    p.write_text("\n".join(["a,b,c"] * 1000))
    with pytest.raises(ValidationError):
        DataValidator.validate_csv_safety(str(p), max_size_mb=0.0001)


def test_validate_data_frame_and_column_mapping():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    assert DataValidator.validate_data_frame(df) is df

    with pytest.raises(ValidationError):
        DataValidator.validate_data_frame("not-a-df")

    # missing required columns
    with pytest.raises(ValidationError):
        DataValidator.validate_data_frame(df, required_columns=["x"])

    # invalid column name type
    df2 = pd.DataFrame({(1, 2): [1]})
    with pytest.raises(ValidationError):
        DataValidator.validate_data_frame(df2)

    # validate_column_mapping
    available = ["a", "b"]
    with pytest.raises(ValidationError):
        DataValidator.validate_column_mapping("not-a-dict", available)

    with pytest.raises(ValidationError):
        DataValidator.validate_column_mapping({1: 0}, available)

    with pytest.raises(ValidationError):
        DataValidator.validate_column_mapping({"x": "z"}, available)

    with pytest.raises(ValidationError):
        DataValidator.validate_column_mapping({"k": 10}, available)

    # valid mapping
    m = DataValidator.validate_column_mapping({"k": "a", "i": 1}, available)
    assert m["k"] == "a" and m["i"] == 1


def test_quick_helpers():
    coords = [[0, 0, 0], [1, 2, 3]]
    res = validate_coordinates(coords)
    assert len(res) == 2
    assert validate_numeric(5, min_val=0, max_val=10) == 5.0
