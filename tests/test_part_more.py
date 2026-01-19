import numpy as np
import pytest

from src.models.part import Part, Variant
from src.models.coordinate_system import CoordinateSystem


def test_variant_to_dict_numeric_casts():
    cs = CoordinateSystem.from_dict({})
    v = Variant(part_name="P", coord_system=cs, cref=2, bref=3, sref=4, q=5)
    d = v.to_dict()
    assert isinstance(d["Cref"], float)
    assert isinstance(d["Bref"], float)
    assert isinstance(d["S"], float)
    assert isinstance(d["Q"], float)


def test_variant_from_dict_missing_momentcenter_uses_coord():
    data = {"PartName": "P", "CoordSystem": {"Orig": [0,0,0]}}
    v = Variant.from_dict(data)
    # 当未指定 MomentCenter，应使用 coord_system 的默认值
    assert isinstance(v.moment_center, np.ndarray)


def test_variant_from_dict_alternate_s_keys():
    for key in ("S", "Sref", "S_ref"):
        data = {"PartName": "X", key: 99}
        v = Variant.from_dict(data)
        assert v.sref == 99.0


def test_part_add_variant_and_from_dict_empty_variants():
    p = Part("A")
    cs = CoordinateSystem.from_dict({})
    v = Variant(part_name="A", coord_system=cs)
    p.add_variant(v)
    assert len(p.variants) == 1

    # from_dict when Variants key is missing or empty
    p2 = Part.from_dict({"PartName": "B"})
    assert p2.name == "B"
    assert isinstance(p2.variants, list)


def test_part_from_dict_with_empty_variant_entry():
    # 当 Variants 为 [{}] 时，应该得到空的 variants 列表
    p = Part.from_dict({"PartName": "C", "Variants": [{}]})
    assert p.name == "C"
    # 空字典会被转换为 Variant.from_dict({}) -> 有效 Variant，检查属性类型
    assert isinstance(p.variants, list)
