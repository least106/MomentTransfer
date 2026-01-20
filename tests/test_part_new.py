import numpy as np

from src.models.coordinate_system import CoordinateSystem
from src.models.part import Part, Variant


def make_cs():
    return CoordinateSystem.from_dict(
        {
            "Orig": [0, 0, 0],
            "X": [1, 0, 0],
            "Y": [0, 1, 0],
            "Z": [0, 0, 1],
            "MomentCenter": [0.5, 0.5, 0.5],
        }
    )


def test_variant_from_dict_alternate_field_names():
    data = {
        "PartName": "P",
        "CoordSystem": {},
        "MomentCenter": [1, 2, 3],
        "Sref": 12,
        "C_ref": 2.5,
        "B_ref": 3.5,
        "Q": 42,
    }
    v = Variant.from_dict(data)
    assert v.part_name == "P"
    assert np.allclose(v.moment_center, [1.0, 2.0, 3.0])
    assert v.sref == 12.0
    assert v.cref == 2.5
    assert v.bref == 3.5
    assert v.q == 42.0


def test_part_to_dict_empty_variants_and_roundtrip():
    p = Part(name="Empty")
    d = p.to_dict()
    assert d["PartName"] == "Empty"
    # 当没有变体时，Variants 应为 [{}]
    assert d["Variants"] == [{}]

    # 从带有 variants 的 dict 恢复
    cs = make_cs()
    v = Variant(part_name="P", coord_system=cs)
    p2 = Part(name="X", variants=[v])
    d2 = p2.to_dict()
    p3 = Part.from_dict(d2)
    assert p3.name == "X"
    assert len(p3.variants) == 1
    assert np.allclose(p3.variants[0].moment_center, [0.5, 0.5, 0.5])
