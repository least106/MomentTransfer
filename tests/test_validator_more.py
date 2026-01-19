import pandas as pd
import pytest

from src.validator import DataValidator, ValidationError


def test_validate_file_path_writable_check(monkeypatch, tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("x")

    # 强制目录不可写分支
    monkeypatch.setattr("src.validator.os.access", lambda path, mode: False)
    with pytest.raises(ValidationError):
        DataValidator.validate_file_path(str(p), writable=True)


def test_validate_csv_safety_parser_error(monkeypatch, tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text('bad"csv\n1,2,3')

    # 模拟 pandas 解析错误
    def raise_parser(path, nrows=100):
        raise pd.errors.ParserError("bad csv")

    monkeypatch.setattr("src.validator.pd.read_csv", raise_parser)
    with pytest.raises(ValidationError):
        DataValidator.validate_csv_safety(str(p))


def test_validate_csv_safety_row_count_exceeded(tmp_path):
    p = tmp_path / "many.csv"
    # 200 行，触发行数检查
    p.write_text("\n".join(["a,b,c"] * 200))
    with pytest.raises(ValidationError):
        DataValidator.validate_csv_safety(str(p), max_size_mb=10, max_rows=50)


def test_validate_data_frame_too_many_rows():
    import pandas as pd

    df = pd.DataFrame({"a": list(range(200))})
    with pytest.raises(ValidationError):
        DataValidator.validate_data_frame(df, max_rows=10)
