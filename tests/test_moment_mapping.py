import numpy as np

from src.data_loader import (CoordSystemDefinition, FrameConfiguration,
                             ProjectData)
from src.physics import AeroCalculator


def create_test_project_data(q=10.0, s_ref=2.0, c_ref=1.0, b_ref=4.0):
    src_coord = CoordSystemDefinition(
        origin=[0.0, 0.0, 0.0],
        x_axis=[1.0, 0.0, 0.0],
        y_axis=[0.0, 1.0, 0.0],
        z_axis=[0.0, 0.0, 1.0],
    )
    tgt_coord = CoordSystemDefinition(
        origin=[0.0, 0.0, 0.0],
        x_axis=[1.0, 0.0, 0.0],
        y_axis=[0.0, 1.0, 0.0],
        z_axis=[0.0, 0.0, 1.0],
    )

    source_cfg = FrameConfiguration(part_name="Source", coord_system=src_coord)
    target_cfg = FrameConfiguration(
        part_name="Target",
        coord_system=tgt_coord,
        moment_center=[0.0, 0.0, 0.0],
        c_ref=c_ref,
        b_ref=b_ref,
        q=q,
        s_ref=s_ref,
    )

    # 新的 ProjectData 构造采用 parts 字典形式
    return ProjectData(
        source_parts={source_cfg.part_name: [source_cfg]},
        target_parts={target_cfg.part_name: [target_cfg]},
    )


def test_moment_coeff_mapping():
    # 设置已知参数
    q = 10.0
    s_ref = 2.0
    b_ref = 4.0
    c_ref = 1.0

    project = create_test_project_data(q=q, s_ref=s_ref, c_ref=c_ref, b_ref=b_ref)
    calc = AeroCalculator(project)
    # 为新版 AeroCalculator 注入 cfg 引用
    calc.cfg = project

    # 提供零力，只提供已知矩，旋转与移轴均为单位/零以简化验证
    forces = np.zeros((1, 3))
    moments = np.array([[8.0, 2.0, 12.0]])  # Roll, Pitch, Yaw

    res = calc.process_batch(forces, moments)
    coeff_m = res["coeff_moment"][0]

    # 预期系数：Cl = 8 / (q*s*b), Cm = 2 / (q*s*c), Cn = 12 / (q*s*b)
    expected_cl = 8.0 / (q * s_ref * b_ref)
    expected_cm = 2.0 / (q * s_ref * c_ref)
    expected_cn = 12.0 / (q * s_ref * b_ref)

    assert np.isclose(coeff_m[0], expected_cl, atol=1e-9)
    assert np.isclose(coeff_m[1], expected_cm, atol=1e-9)
    assert np.isclose(coeff_m[2], expected_cn, atol=1e-9)
