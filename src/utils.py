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
