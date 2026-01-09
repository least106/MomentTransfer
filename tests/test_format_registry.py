import tempfile
from pathlib import Path
import sqlite3

from src.format_registry import (
    init_db,
    register_mapping,
    list_mappings,
    get_format_for_file,
    delete_mapping,
    update_mapping,
)


def test_registry_crud_and_lookup(tmp_path):
    db_path = tmp_path / "formats.sqlite"
    init_db(str(db_path))

    fmt1 = tmp_path / "a.format.json"
    fmt1.write_text('{"skip_rows":0}')
    fmt2 = tmp_path / "b.format.json"
    fmt2.write_text('{"skip_rows":1}')

    # register two mappings
    register_mapping(str(db_path), "*.csv", str(fmt1))
    register_mapping(str(db_path), "special.csv", str(fmt2))

    items = list_mappings(str(db_path))
    assert len(items) >= 2

    # exact filename match should prefer specific mapping
    matched = get_format_for_file(str(db_path), "special.csv")
    assert matched is not None and Path(matched).name == fmt2.name

    # wildcard match should find fmt1 for other csv
    matched2 = get_format_for_file(str(db_path), "other.csv")
    assert matched2 is not None and Path(matched2).name == fmt1.name

    # update mapping: change pattern -> new format
    register_mapping(str(db_path), "special.csv", str(fmt1))
    matched3 = get_format_for_file(str(db_path), "special.csv")
    assert matched3 is not None and Path(matched3).name == fmt1.name

    # delete mapping by id
    # get current items and delete first
    items = list_mappings(str(db_path))
    first_id = items[0]["id"]
    delete_mapping(str(db_path), first_id)
    items2 = list_mappings(str(db_path))
    assert all(i["id"] != first_id for i in items2)
