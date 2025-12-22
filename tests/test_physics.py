"""
测试 physics 模块的核心计算功能
"""
import pytest
import numpy as np
import warnings
from src.data_loader import ProjectData, CoordSystemDefinition, TargetDefinition
from src.physics import AeroCalculator, AeroResult


def create_test_project_data(
    q=100.0, 
    s_ref=1.0, 
    c_ref=1.0, 
    b_ref=2.0,
    source_origin=None,
    target_origin=None,
    target_moment_center=None
):
    """创建测试用的 ProjectData"""
    if source_origin is None:
        source_origin = [0.0, 0.0, 0.0]
    if target_origin is None:
        target_origin = [0.0, 0.0, 0.0]
    if target_moment_center is None:
        target_moment_center = [0.0, 0.0, 0.0]
    
    source_coord = CoordSystemDefinition(
        origin=source_origin,
        x_axis=[1.0, 0.0, 0.0],
        y_axis=[0.0, 1.0, 0.0],
        z_axis=[0.0, 0.0, 1.0]
    )
    
    target_coord_def = CoordSystemDefinition(
        origin=target_origin,
        x_axis=[1.0, 0.0, 0.0],
        y_axis=[0.0, 1.0, 0.0],
        z_axis=[0.0, 0.0, 1.0]
    )
    
    target_config = TargetDefinition(
        part_name="TestPart",
        coord_system=target_coord_def,
        moment_center=target_moment_center,
        c_ref=c_ref,
        b_ref=b_ref,
        q=q,
        s_ref=s_ref
    )
    
    return ProjectData(source_coord=source_coord, target_config=target_config)


class TestAeroCalculatorInitialization:
    """测试 AeroCalculator 初始化"""
    
    def test_valid_initialization(self):
        """测试正常初始化"""
        project = create_test_project_data()
        calc = AeroCalculator(project)
        
        assert calc.cfg == project
        assert calc.R_matrix.shape == (3, 3)
        assert calc.r_target.shape == (3,)
    
    def test_singular_basis_matrix(self):
        """测试奇异基矩阵应抛出异常"""
        source_coord = CoordSystemDefinition(
            origin=[0, 0, 0],
            x_axis=[1.0, 0.0, 0.0],
            y_axis=[1.0, 0.0, 0.0],  # 与 x_axis 相同，导致奇异
            z_axis=[0.0, 0.0, 1.0]
        )
        
        target_config = TargetDefinition(
            part_name="Test",
            coord_system=CoordSystemDefinition(
                origin=[0, 0, 0],
                x_axis=[1.0, 0.0, 0.0],
                y_axis=[0.0, 1.0, 0.0],
                z_axis=[0.0, 0.0, 1.0]
            ),
            moment_center=[0, 0, 0],
            c_ref=1.0,
            b_ref=2.0,
            q=100.0,
            s_ref=1.0
        )
        
        project = ProjectData(source_coord=source_coord, target_config=target_config)
        
        # 应在初始化时检测到基矩阵奇异
        with pytest.raises(ValueError, match="基矩阵接近奇异"):
            AeroCalculator(project)


class TestAeroCalculatorProcessFrame:
    """测试 process_frame 方法"""
    
    def test_identity_transformation(self):
        """测试相同坐标系且无移轴的情况"""
        project = create_test_project_data(
            q=100.0, 
            s_ref=1.0,
            source_origin=[0, 0, 0],
            target_moment_center=[0, 0, 0]
        )
        calc = AeroCalculator(project)
        
        # 输入力和力矩
        force = [100.0, 0.0, 1000.0]
        moment = [0.0, 50.0, 0.0]
        
        result = calc.process_frame(force, moment)
        
        # 坐标系相同且无移轴，力和力矩应不变
        assert np.allclose(result.force_transformed, force, atol=1e-6)
        assert np.allclose(result.moment_transformed, moment, atol=1e-6)
        
        # 验证系数计算
        # Cx = Fx / (q * S) = 100 / 100 = 1.0
        assert np.isclose(result.coeff_force[0], 1.0, atol=1e-6)
    
    def test_moment_transfer(self):
        """测试力矩移轴效应"""
        project = create_test_project_data(
            q=100.0,
            s_ref=1.0,
            source_origin=[1.0, 0.0, 0.0],  # 源原点在 x=1
            target_moment_center=[0.0, 0.0, 0.0]  # 目标矩心在原点
        )
        calc = AeroCalculator(project)
        
        # 纯 Z 方向力
        force = [0.0, 0.0, 100.0]
        moment = [0.0, 0.0, 0.0]
        
        result = calc.process_frame(force, moment)
        
        # r = [1, 0, 0], F = [0, 0, 100]
        # delta_M = r x F = [1, 0, 0] x [0, 0, 100] = [0, -100, 0]
        # 最终力矩应该是 [0, -100, 0]
        assert np.isclose(result.moment_transformed[1], -100.0, atol=1e-6)
    
    def test_zero_dynamic_pressure(self):
        """测试 q=0 时返回零系数并发出警告"""
        project = create_test_project_data(q=0.0)
        calc = AeroCalculator(project)
        
        force = [100.0, 0.0, 1000.0]
        moment = [0.0, 50.0, 0.0]
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = calc.process_frame(force, moment)
            
            # 应发出警告
            assert len(w) >= 1
            assert "动压" in str(w[0].message) or "无法计算" in str(w[0].message)
        
        # 系数应全为零
        assert result.coeff_force == [0.0, 0.0, 0.0]
        assert result.coeff_moment == [0.0, 0.0, 0.0]
        
        # 但力和力矩的变换值仍然有效
        assert result.force_transformed == force
    
    def test_coefficient_calculation(self):
        """测试系数计算的正确性"""
        project = create_test_project_data(
            q=50.0,  # 动压
            s_ref=2.0,  # 参考面积
            c_ref=1.0,  # 参考弦长
            b_ref=2.0   # 参考展长
        )
        calc = AeroCalculator(project)
        
        # 简单输入便于计算
        force = [100.0, 0.0, 0.0]  # 只有 X 方向力
        moment = [10.0, 20.0, 30.0]
        
        result = calc.process_frame(force, moment)
        
        # q * S = 50 * 2 = 100
        # Cx = Fx / (q * S) = 100 / 100 = 1.0
        assert np.isclose(result.coeff_force[0], 1.0, atol=1e-6)
        
        # Cl = Mx / (q * S * b) = 10 / (100 * 2) = 0.05
        assert np.isclose(result.coeff_moment[0], 0.05, atol=1e-6)
        
        # Cm = My / (q * S * c) = 20 / (100 * 1) = 0.2
        assert np.isclose(result.coeff_moment[1], 0.2, atol=1e-6)
        
        # Cn = Mz / (q * S * b) = 30 / (100 * 2) = 0.15
        assert np.isclose(result.coeff_moment[2], 0.15, atol=1e-6)
    
    def test_result_dataclass_structure(self):
        """测试返回结果的数据结构"""
        project = create_test_project_data()
        calc = AeroCalculator(project)
        
        result = calc.process_frame([100, 0, 1000], [0, 50, 0])
        
        # 验证返回类型
        assert isinstance(result, AeroResult)
        
        # 验证所有字段都存在且为列表
        assert isinstance(result.force_transformed, list)
        assert isinstance(result.moment_transformed, list)
        assert isinstance(result.coeff_force, list)
        assert isinstance(result.coeff_moment, list)
        
        # 验证长度
        assert len(result.force_transformed) == 3
        assert len(result.moment_transformed) == 3
        assert len(result.coeff_force) == 3
        assert len(result.coeff_moment) == 3


class TestEdgeCases:
    """测试边缘情况"""
    
    def test_very_small_forces(self):
        """测试极小的力"""
        project = create_test_project_data()
        calc = AeroCalculator(project)
        
        force = [1e-10, 1e-10, 1e-10]
        moment = [0, 0, 0]
        
        result = calc.process_frame(force, moment)
        
        # 应能正常处理，不崩溃
        assert all(isinstance(x, float) for x in result.force_transformed)
    
    def test_large_moment_arm(self):
        """测试大力臂情况"""
        project = create_test_project_data(
            source_origin=[1000.0, 0.0, 0.0],
            target_moment_center=[0.0, 0.0, 0.0]
        )
        calc = AeroCalculator(project)
        
        force = [0.0, 0.0, 1.0]
        moment = [0.0, 0.0, 0.0]
        
        result = calc.process_frame(force, moment)
        
        # r x F 应产生很大的力矩
        # r = [1000, 0, 0], F = [0, 0, 1]
        # delta_M = [0, -1000, 0]
        assert np.isclose(result.moment_transformed[1], -1000.0, atol=1e-6)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
