"""
3D 可视化画布模块
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)

_HAS_MPL = False
try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    _HAS_MPL = True
except Exception:
    FigureCanvas = object
    Figure = object


if _HAS_MPL:
    class Mpl3DCanvas(FigureCanvas):
        """3D坐标系可视化画布"""

        def __init__(self, parent=None, width=5, height=4, dpi=100):
            self.fig = Figure(figsize=(width, height), dpi=dpi)
            self.axes = self.fig.add_subplot(111, projection='3d')
            super().__init__(self.fig)
            self.setParent(parent)

        def plot_systems(self, source_orig, source_basis, target_orig, target_basis, moment_center):
            self.axes.clear()

            # 源坐标系（灰色虚线）
            self._draw_frame(source_orig, source_basis, "Source", color=['gray'] * 3, alpha=0.3, linestyle='--')

            # 目标坐标系（彩色实线）
            self._draw_frame(target_orig, target_basis, "Target", color=['r', 'g', 'b'], length=1.5)

            # 力矩中心（紫色点）
            self.axes.scatter(moment_center[0], moment_center[1], moment_center[2],
                              c='m', marker='o', s=80, label='Moment Center', edgecolors='black', linewidths=1)

            # 自动调整显示范围
            all_points = np.array([source_orig, target_orig, moment_center], dtype=float)
            ranges = np.ptp(all_points, axis=0)
            max_span = float(np.max(ranges)) if ranges.size > 0 else 0.0
            eps = 1e-6
            if max_span < eps:
                max_range = 2.0
                logger.warning("coordinate systems are nearly coincident; using default visualization range.")
            else:  
                max_range = max_span * 0.6
                max_range = max(max_range, 2.0)

            center = np.mean(all_points, axis=0)
            self.axes.set_xlim([center[0] - max_range, center[0] + max_range])
            self.axes.set_ylim([center[1] - max_range, center[1] + max_range])
            self.axes.set_zlim([center[2] - max_range, center[2] + max_range])

            self.axes.set_xlabel('X', fontsize=10, fontweight='bold')
            self.axes.set_ylabel('Y', fontsize=10, fontweight='bold')
            self.axes.set_zlabel('Z', fontsize=10, fontweight='bold')
            self.axes.legend(loc='upper right', fontsize=9)
            self.axes.set_title('Coordinate Systems Visualization', fontsize=11, fontweight='bold')
            self.draw()

        def _draw_frame(self, o, basis, label_prefix, color, length=1.0, alpha=1.0, linestyle='-'):
            labels = ['X', 'Y', 'Z']
            for i in range(3):
                vec = basis[i] * length
                self.axes.quiver(o[0], o[1], o[2],
                                 vec[0], vec[1], vec[2],
                                 color=color[i], alpha=alpha, arrow_length_ratio=0.15,
                                 linewidth=2 if linestyle == '-' else 1,
                                 linestyle=linestyle)
                self.axes.text(o[0] + vec[0] * 1.1, o[1] + vec[1] * 1.1, o[2] + vec[2] * 1.1,
                               f"{label_prefix}_{labels[i]}", color=color[i], fontsize=9, fontweight='bold')
else:
    class Mpl3DCanvas:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("matplotlib not available or failed to initialize; 3D canvas is disabled")
