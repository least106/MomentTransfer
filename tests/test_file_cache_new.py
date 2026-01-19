import hashlib
from pathlib import Path

from src.file_cache import FileCache, get_file_cache, get_file_hash


def test_get_file_content_and_cache(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("hello\nworld", encoding="utf-8")
    fc = FileCache(max_file_size_mb=1)
    assert fc.get_file_content(p) == "hello\nworld"
    stats = fc.get_cache_stats()
    assert stats["content_cached"] == 1
    # 二次读取走缓存
    assert fc.get_file_content(p) == "hello\nworld"
    assert fc.get_cache_stats()["content_cached"] == 1


def test_large_file_not_cached(tmp_path):
    p = tmp_path / "big.txt"
    content = "x" * 5000
    p.write_text(content)
    # 设置极小的最大缓存限制，强制走不缓存分支
    fc = FileCache(max_file_size_mb=0.0001)
    res = fc.get_file_content(p)
    assert res == content
    assert fc.get_cache_stats()["content_cached"] == 0


def test_header_and_metadata(tmp_path):
    p = tmp_path / "h.txt"
    p.write_text("\n".join([f"line{i}" for i in range(20)]))
    fc = FileCache()
    header = fc.get_file_header(p, num_lines=5)
    assert header == [f"line{i}\n" for i in range(5)]
    assert fc.get_cache_stats()["metadata_cached"] == 1
    fc.set_metadata(p, "fmt", "mtfmt")
    assert fc.get_metadata(p, "fmt") == "mtfmt"
    fc.clear_file(p)
    assert fc.get_metadata(p, "fmt") is None


def test_clear_and_singleton(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("a")
    mgr_cache = get_file_cache()
    mgr_cache.clear()
    mgr_cache.set_metadata(p, "k", "v")
    assert mgr_cache.get_metadata(p, "k") == "v"
    mgr_cache.clear()
    assert mgr_cache.get_metadata(p, "k") is None


def test_get_file_hash(tmp_path):
    p = tmp_path / "h.bin"
    p.write_bytes(b"abc")
    h = get_file_hash(str(p))
    assert h == hashlib.md5(b"abc").hexdigest()
    assert get_file_hash(str(p) + "_notexist") is None
