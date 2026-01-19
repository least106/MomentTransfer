import numpy as np
import pytest

from src.models.coordinate_system import _vec3, CoordinateSystem


def test_vec3_valid_and_invalid():
    arr = _vec3([1, 2, 3])
    assert isinstance(arr, np.ndarray)
    assert arr.shape == (3,)

    with pytest.raises(ValueError):
        _vec3([1, 2])


def test_coordinate_system_to_matrix_and_dict():
    cs = CoordinateSystem(
        origin=[0, 0, 0],
        x_axis=[1, 0, 0],
        y_axis=[0, 1, 0],
        z_axis=[0, 0, 1],
        moment_center=[0.1, 0.2, 0.3],
    )
    mat = cs.to_matrix()
    assert mat.shape == (3, 3)
    assert np.allclose(mat[:, 0], [1, 0, 0])

    d = cs.to_dict()
    assert d["Orig"] == [0.0, 0.0, 0.0]
    assert d["MomentCenter"] == [0.1, 0.2, 0.3]


def test_from_dict_defaults_and_alternative_key():
    # default when data is None
    with pytest.raises(ValueError):
        CoordinateSystem.from_dict(None)

    data = {"Orig": [1, 1, 1], "TargetMomentCenter": [9, 9, 9]}
    cs = CoordinateSystem.from_dict(data)
    assert cs.origin.tolist() == [1.0, 1.0, 1.0]
    assert cs.moment_center.tolist() == [9.0, 9.0, 9.0]
