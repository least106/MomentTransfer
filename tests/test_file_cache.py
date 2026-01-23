from pathlib import Path
import hashlib

from src.file_cache import FileCache, get_file_hash


def test_get_file_content_and_cache(tmp_path):
    f = tmp_path / "a.txt"
    content = "hello world"
    f.write_text(content, encoding="utf-8")

    fc = FileCache(max_file_size_mb=1)
    got = fc.get_file_content(f)
    assert got == content

    stats = fc.get_cache_stats()
    assert stats["content_cached"] == 1

    # 再次读取应来自缓存
    got2 = fc.get_file_content(f)
    assert got2 == content


def test_get_file_content_large_not_cached(tmp_path):
    f = tmp_path / "big.bin"
    # 创建一个较大的文件
    data = "x" * 2048
    f.write_text(data, encoding="utf-8")

    # 限制为 0 MB，保证不缓存
    fc = FileCache(max_file_size_mb=0)
    got = fc.get_file_content(f)
    assert got == data
    stats = fc.get_cache_stats()
    assert stats["content_cached"] == 0


def test_get_file_header_and_metadata(tmp_path):
    f = tmp_path / "h.txt"
    lines = ["l1", "l2", "l3"]
    f.write_text("\n".join(lines), encoding="utf-8")

    fc = FileCache()
    hdr = fc.get_file_header(f, num_lines=2)
    assert hdr == ["l1\n", "l2\n"]

    # note: get_file_header stores header under a header-specific cache key;
    # get_metadata with plain key is expected to return None unless set via set_metadata
    meta = fc.get_metadata(f, "header")
    assert meta is None

    # 使用 set_metadata 后应能读取
    fc.set_metadata(f, "detected", True)
    assert fc.get_metadata(f, "detected") is True


def test_clear_and_clear_file(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text("abc", encoding="utf-8")
    fc = FileCache()
    assert fc.get_file_content(f) == "abc"
    stats = fc.get_cache_stats()
    assert stats["content_cached"] == 1

    fc.clear_file(f)
    stats2 = fc.get_cache_stats()
    assert stats2["content_cached"] == 0


def test_get_file_hash(tmp_path):
    f = tmp_path / "d.bin"
    b = b"bytes-data"
    f.write_bytes(b)

    got = get_file_hash(str(f))
    expected = hashlib.md5(b).hexdigest()
    assert got == expected


def test_get_file_content_missing(tmp_path):
    f = tmp_path / "nope.txt"
    fc = FileCache()
    assert fc.get_file_content(f) is None
