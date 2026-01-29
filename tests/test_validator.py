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
    assert DataValidator.validate_coordinate((4, 5, 6)) == (4.0, 5.0, 6.0)
    assert DataValidator.validate_coordinate(np.array([7, 8, 9])) == (
        7.0,
        8.0,
        9.0,
    )

    with pytest.raises(ValidationError):
        DataValidator.validate_coordinate([1, 2])

    with pytest.raises(ValidationError):
        DataValidator.validate_coordinate("not a coord")

    with pytest.raises(ValidationError):
        DataValidator.validate_coordinate(np.array([1.0, np.nan, 3.0]))


def test_validate_numeric_range_and_wrapper():
    assert (
        DataValidator.validate_numeric_range("3.5", min_val=0, max_val=10)
        == 3.5
    )
    assert validate_numeric("2.2", min_val=-10, max_val=10) == 2.2

    with pytest.raises(ValidationError):
        DataValidator.validate_numeric_range(float("nan"))

    with pytest.raises(ValidationError):
        DataValidator.validate_numeric_range(100, max_val=10)

    with pytest.raises(ValidationError):
        DataValidator.validate_numeric_range(-5, min_val=0)


def test_validate_file_path_and_writable(tmp_path, monkeypatch):
    # must_exist True and missing
    missing = tmp_path / "no_such_file.txt"
    with pytest.raises(ValidationError):
        DataValidator.validate_file_path(str(missing), must_exist=True)

    # create a file and validate
    f = tmp_path / "ok.txt"
    f.write_text("hello", encoding="utf-8")
    p = DataValidator.validate_file_path(str(f), must_exist=True)
    assert p.exists()

    # writable check: monkeypatch os.access to simulate non-writable
    monkeypatch.setattr(os, "access", lambda *_: False)
    with pytest.raises(ValidationError):
        DataValidator.validate_file_path(
            str(f), must_exist=True, writable=True
        )


def test_validate_csv_safety_basic_and_errors(tmp_path, monkeypatch):
    csv = tmp_path / "small.csv"
    csv.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    # small file should pass with large limits
    p = DataValidator.validate_csv_safety(str(csv), max_size_mb=1)
    assert p.exists()

    # make max_size_mb extremely small to trigger size error
    with pytest.raises(ValidationError):
        DataValidator.validate_csv_safety(str(csv), max_size_mb=1e-9)

    # simulate pandas ParserError
    def fake_read_csv(*args, **kwargs):
        raise pd.errors.ParserError("bad csv")

    monkeypatch.setattr(pd, "read_csv", fake_read_csv)
    with pytest.raises(ValidationError):
        DataValidator.validate_csv_safety(str(csv))


def test_validate_data_frame_checks():
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    assert DataValidator.validate_data_frame(df, required_columns=["x"]) is df

    with pytest.raises(ValidationError):
        DataValidator.validate_data_frame("not a df")

    with pytest.raises(ValidationError):
        DataValidator.validate_data_frame(pd.DataFrame([[1]]), max_rows=0)

    # missing required column
    with pytest.raises(ValidationError):
        DataValidator.validate_data_frame(df, required_columns=["z"])

    # invalid column name type (use tuple as column)
    df2 = pd.DataFrame([[1]], columns=[(1, 2)])
    with pytest.raises(ValidationError):
        DataValidator.validate_data_frame(df2)


def test_validate_column_mapping_success_and_errors():
    available = ["a", "b", "c"]
    mapping = {"x": "a", "y": 1}
    validated = DataValidator.validate_column_mapping(mapping, available)
    assert validated["x"] == "a" and validated["y"] == 1

    with pytest.raises(ValidationError):
        DataValidator.validate_column_mapping("not a dict", available)

    with pytest.raises(ValidationError):
        DataValidator.validate_column_mapping({1: "a"}, available)

    with pytest.raises(ValidationError):
        DataValidator.validate_column_mapping({"z": "nope"}, available)

    with pytest.raises(ValidationError):
        DataValidator.validate_column_mapping({"i": 99}, available)


def test_validate_coordinates_wrapper():
    coords = [[0, 0, 0], (1, 2, 3)]
    out = validate_coordinates(coords)
    assert isinstance(out, list) and out[0] == (0.0, 0.0, 0.0)
