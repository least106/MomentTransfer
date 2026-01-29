from typing import Any


def build_table_row_preview_text(row_index: int, row_series: Any) -> str:
    """构造表格数据行预览文本，显示最多前 6 列的文本值。

    该函数为稳定的公共实现，用于替换多个模块中重复的逻辑。
    """
    try:
        values = []
        try:
            vals = getattr(row_series, "values", row_series)
            for v in list(vals)[:6]:
                try:
                    s = "" if v is None else str(v)
                except Exception:
                    s = ""
                values.append(s)
        except Exception:
            values = []
        if values:
            return f"第{row_index + 1}行：" + " | ".join(values)
    except Exception:
        pass
    return f"第{row_index + 1}行"
from pathlib import Path


def csv_has_header(path: Path) -> bool:
    """简单探测 CSV 首行是否为表头：若首行包含非数值 token 则视为表头。

    该工具用于预览表格时判断是否应将首行作为 header。
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            first_line = fh.readline()
        if not first_line:
            return False
        if "," in first_line:
            tokens = [t.strip() for t in first_line.split(",")]
        elif "\t" in first_line:
            tokens = [t.strip() for t in first_line.split("\t")]
        else:
            tokens = first_line.split()
        non_numeric = 0
        total = 0
        for t in tokens:
            if not t:
                continue
            total += 1
            try:
                float(t)
            except Exception:
                non_numeric += 1
        return total > 0 and non_numeric >= max(1, total // 2)
    except Exception:
        return False


def read_table_preview(path: Path, max_rows: int = 200):
    """读取 CSV 或 Excel 的预览数据（不做缓存）。

    返回一个 pandas.DataFrame 或 None（读取失败时）。
    """
    try:
        if path.suffix.lower() == ".csv":
            header_opt = 0 if csv_has_header(path) else None
            import pandas as _pd

            return _pd.read_csv(path, header=header_opt, nrows=int(max_rows))
        else:
            import pandas as _pd

            df = _pd.read_excel(path, header=None)
            try:
                return df.head(int(max_rows))
            except Exception:
                return df
    except Exception:
        return None
