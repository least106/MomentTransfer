"""格式 registry（基于 SQLite）

提供简单的持久化映射：pattern -> format_file_path

优先级解析策略（在查询时由调用方决定使用结果的优先级）：
- 精确完整路径匹配
- 文件名精确匹配
- glob 模式匹配（对完整路径和文件名进行 fnmatch）
"""

import datetime
import fnmatch
import sqlite3
from pathlib import Path
from typing import List, Optional


def _ensure_db(db_path: str):
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(p)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mappings (
                id INTEGER PRIMARY KEY,
                pattern TEXT NOT NULL,
                format_path TEXT NOT NULL,
                added_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def init_db(db_path: str):
    """初始化数据库文件（若已存在则无害）。"""
    _ensure_db(db_path)


def register_mapping(db_path: str, pattern: str, format_path: str):
    """向 registry 注册一条映射（pattern -> format_file_path）。

    pattern 可以是绝对路径、文件名、或 glob 模式（如 "*.csv" 或 "data_*.csv"）。
    """
    # 验证 pattern 的类型与非空性，尽早报错以避免后续 fnmatch 时抛出 TypeError/ValueError
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("pattern 必须为非空字符串")

    _ensure_db(db_path)
    # 如果已有相同的 pattern，则更新对应映射（避免为同一 pattern 重复插入），并刷新 added_at
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM mappings WHERE pattern = ?", (pattern,))
        row = cur.fetchone()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if row:
            mapping_id = int(row[0])
            cur.execute(
                "UPDATE mappings SET format_path = ?, added_at = ? WHERE id = ?",
                (str(format_path), now_iso, mapping_id),
            )
        else:
            cur.execute(
                "INSERT INTO mappings (pattern, format_path, added_at) VALUES (?, ?, ?)",
                (pattern, str(format_path), now_iso),
            )
        conn.commit()


def list_mappings(db_path: str) -> List[dict]:
    """返回按 id 升序的所有映射记录的列表。

    每个元素为字典，包含 `id`, `pattern`, `format_path`, `added_at`。
    """
    _ensure_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, pattern, format_path, added_at FROM mappings ORDER BY id ASC"
        )
        rows = cur.fetchall()
    return [
        {"id": r[0], "pattern": r[1], "format_path": r[2], "added_at": r[3]}
        for r in rows
    ]


def get_format_for_file(db_path: str, file_path: str) -> Optional[str]:
    """根据注册表返回最匹配的 format 文件路径，若无匹配返回 None。

    匹配顺序：
    1. 精确完整路径（file_path 与 pattern 完全相等）
    2. 文件名精确匹配
    3. fnmatch 对完整路径匹配
    4. fnmatch 对文件名匹配
    返回第一个存在且指向真实文件的 format_path。
    """
    p = Path(file_path)
    name = p.name
    _ensure_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT pattern, format_path FROM mappings ORDER BY id ASC")
        rows = cur.fetchall()

    # 尝试匹配
    # 说明：fnmatch.fnmatch 在 pattern 为 None 或非字符串类型时可能抛出 TypeError/ValueError，
    # 因此我们在插入时就验证 pattern（见 register_mapping），这里的异常处理是个防御性保障，
    # 遇到非法 pattern 会跳过该条记录而不会中断整个匹配过程。
    exact_matches = []
    fnmatch_candidates = []
    for pattern, fmt in rows:
        # 精确匹配优先收集
        if pattern == str(p):
            exact_matches.append(fmt)
            continue
        if pattern == name:
            exact_matches.append(fmt)
            continue
        # 非精确匹配的行，同时作为 fnmatch 候选项收集
        try:
            if fnmatch.fnmatch(str(p), pattern) or fnmatch.fnmatch(name, pattern):
                fnmatch_candidates.append(fmt)
        except (TypeError, ValueError):
            # 跳过不可匹配的 pattern
            continue

    # 若已有精确匹配，优先返回第一个有效的
    for fmt in exact_matches:
        if Path(fmt).exists():
            return str(Path(fmt))

    # 否则尝试 fnmatch 候选项
    for fmt in fnmatch_candidates:
        if Path(fmt).exists():
            return str(Path(fmt))

    return None


def delete_mapping(db_path: str, mapping_id: int) -> None:
    """按 id 删除映射记录（若不存在则无操作）。"""
    _ensure_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM mappings WHERE id = ?", (int(mapping_id),))
        conn.commit()


def update_mapping(
    db_path: str, mapping_id: int, pattern: str, format_path: str
) -> None:
    """更新映射的 pattern 与 format_path（按 id）。若 id 不存在则抛出异常。"""
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("pattern 必须为非空字符串")
    _ensure_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(1) FROM mappings WHERE id = ?", (int(mapping_id),))
        if cur.fetchone()[0] == 0:
            raise KeyError(f"映射 id={mapping_id} 不存在")
        cur.execute(
            "UPDATE mappings SET pattern = ?, format_path = ? WHERE id = ?",
            (pattern, str(format_path), int(mapping_id)),
        )
        conn.commit()
