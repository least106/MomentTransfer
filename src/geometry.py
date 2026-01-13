import warnings
from typing import List

import numpy as np

# 模块级常量：可根据不同应用场景调整
ORTHOGONALITY_THRESHOLD = 0.05  # 允许基向量之间一定误差
SINGULARITY_THRESHOLD = 1e-6  # 判断基矩阵是否接近奇异的阈值
# 用于判断零向量或在投影时分母接近零的阈值（与奇异性阈值分开，便于微调）
ZERO_VECTOR_THRESHOLD = 1e-10


# 基础向量工具
def to_numpy_vec(vec: List[float]) -> np.ndarray:
    """辅助函数：将列表转换为 Numpy 数组"""
    return np.array(vec, dtype=float)


def normalize(vec: np.ndarray) -> np.ndarray:
    """
    归一化向量 (Normalization)。
    确保坐标轴向量长度为 1，防止旋转矩阵缩放变形。

    Raises:
        ValueError: 当输入向量为零向量时抛出异常
    """
    norm = np.linalg.norm(vec)
    if norm < ZERO_VECTOR_THRESHOLD:  # 使用模块级阈值以便维护和统一
        raise ValueError(
            f"无法归一化零向量或接近零的向量: {vec}，模长: {norm}"
        )
    return vec / norm


# 矩阵构建与旋转逻辑
def construct_basis_matrix(
    x: List[float],
    y: List[float],
    z: List[float],
    orthogonality_threshold: float = ORTHOGONALITY_THRESHOLD,
    singularity_threshold: float = SINGULARITY_THRESHOLD,
    orthogonalize: bool = False,
    strict: bool = False,
) -> np.ndarray:
    """
    构建基向量矩阵 (3x3)。
    输入：三个轴的方向向量
    输出：Numpy矩阵，每一行是一个基向量

    可选参数:
        orthogonality_threshold: 正交性判定阈值，点积超过此值会触发警告。
        singularity_threshold: 行列式绝对值低于此值会被视为接近奇异并抛出异常。
        orthogonalize: 当检测到轻微不正交（超过 orthogonality_threshold）时，是否自动对基向量进行再正交化。
                       建议在允许对输入基向量做小幅修正、希望提高数值稳健性时开启。
        strict: 是否采用严格模式。为 True 时，一旦不满足正交性阈值将直接抛出 ValueError；
                为 False 时，仅给出 warnings 警告（配合 orthogonalize=False 可用于容忍轻微不正交的场景）。

    Raises:
        ValueError: 当输入向量为零或基矩阵接近奇异时抛出异常
    """
    vx = normalize(to_numpy_vec(x))
    vy = normalize(to_numpy_vec(y))
    vz = normalize(to_numpy_vec(z))

    # 检查基向量的正交性（可选但推荐）
    # 正交向量的点积应接近 0
    xy_dot = abs(np.dot(vx, vy))
    yz_dot = abs(np.dot(vy, vz))
    zx_dot = abs(np.dot(vz, vx))

    non_orthogonal = (
        xy_dot > orthogonality_threshold
        or yz_dot > orthogonality_threshold
        or zx_dot > orthogonality_threshold
    )

    if non_orthogonal:
        msg = (
            f"基向量可能不正交：X·Y={xy_dot:.6f}, Y·Z={yz_dot:.6f}, Z·X={zx_dot:.6f}。"
            "请检查输入或启用正交化（orthogonalize=True）。"
        )
        if orthogonalize:
            # 使用 Gram–Schmidt 进行正交化并归一化
            def proj(u, v):
                denom = np.dot(u, u)
                if denom < ZERO_VECTOR_THRESHOLD:
                    raise ValueError("Cannot project onto zero vector")
                return (np.dot(v, u) / denom) * u

            u1 = vx
            # 从 vy 中去掉在 u1 上的分量
            u2 = vy - proj(u1, vy)
            # 从 vz 中去掉在 u1,u2 上的分量
            u3 = vz - proj(u1, vz) - proj(u2, vz)

            # 检查正交化后是否退化
            try:
                u1 = normalize(u1)
                u2 = normalize(u2)
                u3 = normalize(u3)
            except ValueError as e:
                raise ValueError(
                    f"正交化失败：输入向量可能线性相关或接近退化，无法构造正交基。详情: {e}"
                ) from e

            basis = np.array([u1, u2, u3])
        else:
            if strict:
                raise ValueError(msg)
            else:
                warnings.warn(msg, UserWarning)
            basis = np.array([vx, vy, vz])
    else:
        basis = np.array([vx, vy, vz])

    # 进一步检查基矩阵的线性相关性（行列式接近零表示基向量线性相关 -> 奇异矩阵）
    det = np.linalg.det(basis)
    if abs(det) < singularity_threshold:
        raise ValueError(
            f"基矩阵接近奇异（行列式={det:.3e}），基向量可能线性相关或退化。"
        )

    return basis


def compute_rotation_matrix(
    source_basis: np.ndarray, target_basis: np.ndarray
) -> np.ndarray:
    """
    计算从源坐标系到目标坐标系的旋转矩阵 R。

    数学原理 (Linear Algebra):
    V_target = R · V_source
    推导公式: R = Target_Basis · Source_Basis.T
    """
    # 矩阵乘法：目标基向量矩阵 x 源基向量矩阵的转置
    return np.dot(target_basis, source_basis.T)


# 空间位置与投影逻辑
def compute_moment_arm_global(
    source_origin: List[float], target_moment_center: List[float]
) -> np.ndarray:
    """
    计算力臂矢量 r (在全局/绝对坐标系下)。

    对应笔记: "力矩转移"示意图
    数学公式: r = Source_Origin - Target_Center
    物理意义: 从“目标矩心(新)”指向“力的作用点(旧)”的矢量。
    """
    p_src = to_numpy_vec(source_origin)
    p_tgt = to_numpy_vec(target_moment_center)
    return p_src - p_tgt


def project_vector_to_frame(
    vec_global: np.ndarray, frame_basis: np.ndarray
) -> np.ndarray:
    """
    将全局坐标系下的向量投影到特定坐标系（如目标坐标系）。

    用途:
    我们需要计算 r x F，但 r 是在全局坐标系算出来的，F 是在目标坐标系下的。
    必须先把 r 投影到目标坐标系 (Target Frame)，才能进行叉乘。
    """
    # 输入校验：确保 frame_basis 为 3x3，vec_global 为长度 3 的向量
    fb = np.asarray(frame_basis, dtype=float)
    v = np.asarray(vec_global, dtype=float)
    if fb.shape != (3, 3):
        raise ValueError(f"frame_basis 必须为形状 (3,3)，当前形状: {fb.shape}")
    if v.shape not in ((3,), (3, 1)):
        # 允许 (3,) 或 (3,1) 的列向量输入
        raise ValueError(
            f"vec_global 必须为长度为3的向量，当前形状: {v.shape}"
        )

    # 计算：基矩阵的行向量为在全局坐标系下的轴方向，
    # 将全局向量投影到该坐标系的坐标分量相当于对每个基向量做点积
    return fb.dot(v).reshape(
        3,
    )


def euler_angles_to_basis(
    roll_deg: float, pitch_deg: float, yaw_deg: float
) -> np.ndarray:
    """
    将欧拉角转换为 3x3 基向量矩阵 (X, Y, Z 轴向量)。
    旋转顺序（对列向量右乘时的实际应用顺序）为: Roll (X) -> Pitch (Y) -> Yaw (Z)，对应组合矩阵 R = Rz @ Ry @ Rx

    :param roll_deg: 滚转角 (如上反角)
    :param pitch_deg: 俯仰角 (如安装角)
    :param yaw_deg: 偏航角 (如后掠角)
    :return: 3x3 矩阵，行0=X轴向量, 行1=Y轴向量, 行2=Z轴向量
    """
    roll_rad = np.radians(roll_deg)
    pitch_rad = np.radians(pitch_deg)
    yaw_rad = np.radians(yaw_deg)

    # 旋转矩阵构建
    # rotation_matrix_z (Yaw)
    rotation_matrix_z = np.array(
        [
            [np.cos(yaw_rad), -np.sin(yaw_rad), 0],
            [np.sin(yaw_rad), np.cos(yaw_rad), 0],
            [0, 0, 1],
        ]
    )

    # rotation_matrix_y (Pitch)
    rotation_matrix_y = np.array(
        [
            [np.cos(pitch_rad), 0, np.sin(pitch_rad)],
            [0, 1, 0],
            [-np.sin(pitch_rad), 0, np.cos(pitch_rad)],
        ]
    )

    # rotation_matrix_x (Roll)
    rotation_matrix_x = np.array(
        [
            [1, 0, 0],
            [0, np.cos(roll_rad), -np.sin(roll_rad)],
            [0, np.sin(roll_rad), np.cos(roll_rad)],
        ]
    )

    # 复合旋转矩阵（按顺序 Rz * Ry * Rx 得到最终变换）
    # 注意：这里的基向量是列向量概念，或者是将全局坐标转到局部。
    # 我们需要的是：在全局坐标系下，局部坐标轴指向哪里。
    # 这等同于旋转矩阵的 列 (Columns)。
    composite_rotation_matrix = (
        rotation_matrix_z @ rotation_matrix_y @ rotation_matrix_x
    )

    # composite_rotation_matrix 的第一列是 X轴，第二列是 Y轴，第三列是 Z轴
    x_axis = composite_rotation_matrix[:, 0]
    y_axis = composite_rotation_matrix[:, 1]
    z_axis = composite_rotation_matrix[:, 2]

    return np.array([x_axis, y_axis, z_axis])
