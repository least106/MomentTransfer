"""
单元测试：src.physics 模块（临时干净副本）

使用 `FrameConfiguration` 与 `ProjectData(source_config=..., target_config=...)`。
"""

import numpy as np
import pytest

from src.data_loader import CoordSystemDefinition, FrameConfiguration, ProjectData
from src.physics import AeroCalculator


def create_test_project_data(
    q=100.0,
    s_ref=1.0,
    c_ref=1.0,
    b_ref=2.0,
    source_origin=None,
    target_origin=None,
    target_moment_center=None,
):
    if source_origin is None:
        source_origin = [0.0, 0.0, 0.0]
    if target_origin is None:
        target_origin = [0.0, 0.0, 0.0]
    if target_moment_center is None:
        target_moment_center = [0.0, 0.0, 0.0]

    src_coord = CoordSystemDefinition(
        origin=source_origin,
        x_axis=[1.0, 0.0, 0.0],
        y_axis=[0.0, 1.0, 0.0],
        z_axis=[0.0, 0.0, 1.0],
    )
    tgt_coord = CoordSystemDefinition(
        origin=target_origin,
        x_axis=[1.0, 0.0, 0.0],
        y_axis=[0.0, 1.0, 0.0],
        z_axis=[0.0, 0.0, 1.0],
    )

    source_cfg = FrameConfiguration(part_name="Source", coord_system=src_coord)
    target_cfg = FrameConfiguration(
        part_name="TestPart",
        coord_system=tgt_coord,
        moment_center=target_moment_center,
        c_ref=c_ref,
        b_ref=b_ref,
        q=q,
        s_ref=s_ref,
    )

    return ProjectData(
        source_parts={source_cfg.part_name: [source_cfg]},
        target_parts={target_cfg.part_name: [target_cfg]},
    )


class TestAeroCalculatorProcessFrame:
    def test_identity_transformation(self):
        project = create_test_project_data(
            q=100.0,
            s_ref=1.0,
            source_origin=[0, 0, 0],
            target_moment_center=[0, 0, 0],
        )
        # 显式指定 target_part/variant
        calc = AeroCalculator(
            project, target_part="TestPart", target_variant=0
        )

        force = [100.0, 0.0, 1000.0]
        moment = [0.0, 50.0, 0.0]

        result = calc.process_frame(force, moment)

        assert np.allclose(result.force_transformed, force, atol=1e-6)
        assert np.allclose(result.moment_transformed, moment, atol=1e-6)
        assert np.isclose(result.coeff_force[0], 1.0, atol=1e-6)

    def test_moment_transfer(self):
        project = create_test_project_data(
            q=100.0,
            s_ref=1.0,
            source_origin=[1.0, 0.0, 0.0],
            target_moment_center=[0.0, 0.0, 0.0],
        )
        calc = AeroCalculator(
            project, target_part="TestPart", target_variant=0
        )

        force = [0.0, 0.0, 100.0]
        moment = [0.0, 0.0, 0.0]

        result = calc.process_frame(force, moment)

        assert np.isclose(result.moment_transformed[1], -100.0, atol=1e-6)


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
