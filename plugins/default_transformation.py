"""默认转换插件：提供参考的坐标旋转与移轴（r x F）实现。"""

from typing import Dict

import numpy as np

from src.plugin import PluginMetadata, TransformationPlugin


class DefaultTransformationPlugin(TransformationPlugin):
    """将力与力矩按给定旋转矩阵变换并对力矩应用移轴修正。"""

    def __init__(self, meta: PluginMetadata):
        self._meta = meta

    @property
    def metadata(self) -> PluginMetadata:
        return self._meta

    def transform(
        self,
        forces: np.ndarray,
        moments: np.ndarray,
        rotation_matrix: np.ndarray,
        moment_arm: np.ndarray,
    ) -> Dict[str, np.ndarray]:
        """参考实现：

        - 力按旋转矩阵右乘转置（批量计算）：forces @ R.T
        - 力矩按相同旋转变换并加上 r x f' 移轴项
        """
        # 力的旋转（假设每行是一个向量）
        forces_t = np.asarray(forces)
        moments_t = np.asarray(moments)
        R = np.asarray(rotation_matrix)

        if forces_t.ndim == 1:
            forces_t = forces_t.reshape(1, 3)
        if moments_t.ndim == 1:
            moments_t = moments_t.reshape(1, 3)

        forces_rot = forces_t @ R.T
        moments_rot = moments_t @ R.T

        # 扩展 moment_arm 到与 forces_rot 相同的批量形状
        r = np.asarray(moment_arm).reshape(1, 3)
        r_rep = np.repeat(r, forces_rot.shape[0], axis=0)

        moments_corrected = moments_rot + np.cross(r_rep, forces_rot)

        return {"forces": forces_rot, "moments": moments_corrected}


def create_plugin() -> DefaultTransformationPlugin:
    meta = PluginMetadata(
        name="default_transformation",
        version="0.1",
        author="example",
        description="默认的坐标变换与移轴实现",
        plugin_type="transformation",
    )

    return DefaultTransformationPlugin(meta)
