import sys
import logging

import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import fnmatch
_HAS_MPL = False
try:
    import matplotlib
    matplotlib.use('Qt5Agg')

    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    _HAS_MPL = True
except Exception:
    # 在测试或无 GUI/绘图库环境中，避免在模块导入时抛出异常。
    # 提供最小占位符，实际使用时会抛出运行时错误。
    FigureCanvas = object
    Figure = object

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox, QFormLayout, QFileDialog,
    QTextEdit, QMessageBox, QProgressBar, QSplitter, QCheckBox, QSpinBox,
    QComboBox,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QScrollArea, QSizePolicy, QGridLayout
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QEvent
from src.physics import AeroCalculator
from src.data_loader import ProjectData
from typing import Optional, List, Tuple
from src.format_registry import get_format_for_file, list_mappings, register_mapping, delete_mapping, update_mapping, init_db

logger = logging.getLogger(__name__)

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
            # 计算每个轴的范围，并检测坐标是否几乎重合，避免数值问题
            ranges = np.ptp(all_points, axis=0)
            max_span = float(np.max(ranges)) if ranges.size > 0 else 0.0
            eps = 1e-6  # 判断“几乎重合”的数值阈值
            if max_span < eps:
                # 所有点几乎在同一位置：使用默认可视化范围
                max_range = 2.0
                # 可根据需要改为日志记录或 GUI 提示，这里使用 logging 记录
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


class ColumnMappingDialog(QDialog):
    """列映射配置对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据格式配置")
        self.resize(500, 600)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 跳过行数
        grp_skip = QGroupBox("表头设置")
        form_skip = QFormLayout()
        self.spin_skip_rows = QSpinBox()
        self.spin_skip_rows.setRange(0, 100)
        self.spin_skip_rows.setValue(0)
        form_skip.addRow("跳过行数:", self.spin_skip_rows)
        grp_skip.setLayout(form_skip)

        # 列映射
        grp_columns = QGroupBox("数据列映射 (列号从0开始)")
        form_cols = QFormLayout()

        self.col_alpha = QSpinBox()
        self.col_alpha.setRange(-1, 1000)
        self.col_alpha.setValue(-1)
        self.col_alpha.setSpecialValueText("不存在")

        self.col_fx = QSpinBox()
        self.col_fy = QSpinBox()
        self.col_fz = QSpinBox()
        self.col_mx = QSpinBox()
        self.col_my = QSpinBox()
        self.col_mz = QSpinBox()

        for spin in [self.col_fx, self.col_fy, self.col_fz,
                     self.col_mx, self.col_my, self.col_mz]:
            spin.setRange(0, 1000)
            spin.setValue(0)

        form_cols.addRow("迎角 Alpha (可选):", self.col_alpha)
        form_cols.addRow("轴向力 Fx:", self.col_fx)
        form_cols.addRow("侧向力 Fy:", self.col_fy)
        form_cols.addRow("法向力 Fz:", self.col_fz)
        form_cols.addRow("滚转力矩 Mx:", self.col_mx)
        form_cols.addRow("俯仰力矩 My:", self.col_my)
        form_cols.addRow("偏航力矩 Mz:", self.col_mz)

        grp_columns.setLayout(form_cols)

        # 保留列
        grp_pass = QGroupBox("需要保留输出的其他列")
        layout_pass = QVBoxLayout()
        self.txt_passthrough = QLineEdit()
        self.txt_passthrough.setPlaceholderText("用逗号分隔列号，如: 0,1,2")
        layout_pass.addWidget(QLabel("列号:"))
        layout_pass.addWidget(self.txt_passthrough)
        grp_pass.setLayout(layout_pass)

        # 按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

        layout.addWidget(grp_skip)
        layout.addWidget(grp_columns)
        layout.addWidget(grp_pass)
        layout.addWidget(btn_box)

    def get_config(self):
        """获取并返回配置字典"""
        passthrough = []
        text = self.txt_passthrough.text().strip()
        if text:
            toks = [t.strip() for t in text.split(',') if t.strip()]
            invalid = []
            for tok in toks:
                try:
                    passthrough.append(int(tok))
                except ValueError:
                    invalid.append(tok)
            if invalid:
                QMessageBox.warning(self, "透传列解析警告",
                                    f"以下透传列索引无法解析，已被忽略：{', '.join(invalid)}")

        return {
            'skip_rows': self.spin_skip_rows.value(),
            'columns': {
                'alpha': self.col_alpha.value() if self.col_alpha.value() >= 0 else None,
                'fx': self.col_fx.value(),
                'fy': self.col_fy.value(),
                'fz': self.col_fz.value(),
                'mx': self.col_mx.value(),
                'my': self.col_my.value(),
                'mz': self.col_mz.value()
            },
            'passthrough': passthrough
        }

    def set_config(self, cfg: dict):
        """用已有配置填充对话框控件，兼容部分字段缺失的情况。"""
        if not isinstance(cfg, dict):
            return

        if 'skip_rows' in cfg:
            try:
                self.spin_skip_rows.setValue(int(cfg.get('skip_rows', 0)))
            except (ValueError, TypeError) as e:
                logger.warning("Invalid skip_rows value %r: %s", cfg.get('skip_rows'), e, exc_info=True)

        cols = cfg.get('columns') or cfg.get('Columns') or {}
        try:
            if 'alpha' in cols and cols.get('alpha') is not None:
                self.col_alpha.setValue(int(cols.get('alpha')))
            if 'fx' in cols and cols.get('fx') is not None:
                self.col_fx.setValue(int(cols.get('fx')))
            if 'fy' in cols and cols.get('fy') is not None:
                self.col_fy.setValue(int(cols.get('fy')))
            if 'fz' in cols and cols.get('fz') is not None:
                self.col_fz.setValue(int(cols.get('fz')))
            if 'mx' in cols and cols.get('mx') is not None:
                self.col_mx.setValue(int(cols.get('mx')))
            if 'my' in cols and cols.get('my') is not None:
                self.col_my.setValue(int(cols.get('my')))
            if 'mz' in cols and cols.get('mz') is not None:
                self.col_mz.setValue(int(cols.get('mz')))
        except (ValueError, TypeError) as e:
            logger.warning("Invalid column indices in %r: %s", cols, e, exc_info=True)

        passthrough = cfg.get('passthrough') or cfg.get('Passthrough') or []
        try:
            if isinstance(passthrough, (list, tuple)):
                self.txt_passthrough.setText(','.join(str(int(x)) for x in passthrough))
            elif isinstance(passthrough, str):
                self.txt_passthrough.setText(passthrough)
        except (ValueError, TypeError) as e:
            logger.warning("Invalid passthrough values %r: %s", passthrough, e, exc_info=True)

class BatchProcessThread(QThread):
    """在后台线程中执行批量处理，发出进度与日志信号"""
    progress = Signal(int)
    log_message = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, calculator, file_list, output_dir, data_config, registry_db=None):
        super().__init__()
        self.calculator = calculator
        self.file_list = file_list
        self.output_dir = Path(output_dir)
        self.data_config = data_config
        # 可选的 format registry 数据库路径（字符串或 None）
        self.registry_db = registry_db
        # 取消标志，用于请求优雅停止（线程内检查）
        self._stop_requested = False

    def process_file(self, file_path):
        """处理单个文件并返回输出路径

        若线程属性 `enable_sidecar` 为 True，则按文件计算最终的 `data_config`（通过 `resolve_file_format`），
        否则使用 `self.data_config`。
        """
        # 若启用了 per-file 覆盖，则为当前文件解析最终的 data_config
        cfg_to_use = self.data_config
        if getattr(self, 'enable_sidecar', False):
            try:
                from src.cli_helpers import resolve_file_format, BatchConfig as _BatchConfig
                # 将现有 self.data_config（可能为 dict）转换为 BatchConfig
                base_cfg = _BatchConfig()
                if isinstance(self.data_config, dict):
                    # 只覆盖部分字段（常用的 skip_rows, columns, passthrough, chunksize, sample_rows）
                    base_cfg.skip_rows = int(self.data_config.get('skip_rows', base_cfg.skip_rows))
                    cols = self.data_config.get('columns') or {}
                    for k in base_cfg.column_mappings.keys():
                        if k in cols and cols.get(k) is not None:
                            base_cfg.column_mappings[k] = int(cols.get(k))
                    base_cfg.passthrough_columns = [int(x) for x in self.data_config.get('passthrough', base_cfg.passthrough_columns)]
                    if 'chunksize' in self.data_config:
                        try:
                            base_cfg.chunksize = int(self.data_config.get('chunksize'))
                        except Exception:
                            base_cfg.chunksize = None
                    if 'sample_rows' in self.data_config:
                        try:
                            base_cfg.sample_rows = int(self.data_config.get('sample_rows'))
                        except Exception:
                            base_cfg.sample_rows = base_cfg.sample_rows
                else:
                    base_cfg = self.data_config

                cfg_to_use = resolve_file_format(str(file_path), base_cfg, enable_sidecar=True, registry_db=self.registry_db)
            except Exception as e:
                self.log_message.emit(f"为文件 {file_path.name} 解析 per-file 配置失败: {e}")
                raise

        if file_path.suffix.lower() == '.csv':
            df = pd.read_csv(file_path, header=None, skiprows=cfg_to_use.get('skip_rows', 0))
        else:
            df = pd.read_excel(file_path, header=None, skiprows=cfg_to_use.get('skip_rows', 0))

        cols = cfg_to_use.get('columns', {})

        def _col_to_numeric(df_local, col_idx, name):
            if col_idx is None:
                raise ValueError(f"缺失必需的列映射: {name}")
            if not (0 <= col_idx < len(df_local.columns)):
                raise IndexError(f"列索引越界: {name} -> {col_idx}")
            orig_col = df_local.iloc[:, col_idx]
            ser = pd.to_numeric(orig_col, errors='coerce')
            bad_mask = ser.isna() & orig_col.notna()
            if bad_mask.any():
                try:
                    bad_indices = orig_col.index[bad_mask].tolist()
                    sample_indices = bad_indices[:5]
                    sample_values = [str(v) for v in orig_col[bad_mask].head(5).tolist()]
                    self.log_message.emit(
                        f"列 {name} 有 {bad_mask.sum()} 个值无法解析为数值，示例索引: {sample_indices}，示例值: {sample_values}")
                except (IndexError, AttributeError, ValueError) as ex:
                    logger.debug("构建非数值示例时出错（忽略示例）: %s", ex, exc_info=True)
            return ser.values.astype(float)

        try:
            fx = _col_to_numeric(df, cols.get('fx'), 'Fx')
            fy = _col_to_numeric(df, cols.get('fy'), 'Fy')
            fz = _col_to_numeric(df, cols.get('fz'), 'Fz')

            mx = _col_to_numeric(df, cols.get('mx'), 'Mx')
            my = _col_to_numeric(df, cols.get('my'), 'My')
            mz = _col_to_numeric(df, cols.get('mz'), 'Mz')

            forces = np.vstack([fx, fy, fz]).T
            moments = np.vstack([mx, my, mz]).T
        except (ValueError, IndexError, TypeError, OSError) as e:
            try:
                self.log_message.emit(f"数据列提取或转换失败: {e}")
            except Exception:
                logger.debug("无法通过 signal 发送失败消息: %s", e, exc_info=True)
            raise

        results = self.calculator.process_batch(forces, moments)

        output_df = pd.DataFrame()

        for col_idx in self.data_config.get('passthrough', []):
            try:
                idx = int(col_idx)
            except (ValueError, TypeError):
                try:
                    self.log_message.emit(f"透传列索引无效（非整数）：{col_idx}")
                except Exception:
                    logger.debug("无法通过 signal 发送透传列无效消息: %s", col_idx, exc_info=True)
                continue
            if 0 <= idx < len(df.columns):
                output_df[f'Col_{idx}'] = df.iloc[:, idx]
            else:
                try:
                    self.log_message.emit(f"透传列索引越界: {idx}")
                except Exception:
                    logger.debug("无法通过 signal 发送透传列越界消息: %s", idx, exc_info=True)

        if cols.get('alpha') is not None and cols.get('alpha') < len(df.columns):
            output_df['Alpha'] = df.iloc[:, cols['alpha']]

        output_df['Fx_new'] = results['force_transformed'][:, 0]
        output_df['Fy_new'] = results['force_transformed'][:, 1]
        output_df['Fz_new'] = results['force_transformed'][:, 2]
        output_df['Mx_new'] = results['moment_transformed'][:, 0]
        output_df['My_new'] = results['moment_transformed'][:, 1]
        output_df['Mz_new'] = results['moment_transformed'][:, 2]
        output_df['Cx'] = results['coeff_force'][:, 0]
        output_df['Cy'] = results['coeff_force'][:, 1]
        output_df['Cz'] = results['coeff_force'][:, 2]
        output_df['Cl'] = results['coeff_moment'][:, 0]
        output_df['Cm'] = results['coeff_moment'][:, 1]
        output_df['Cn'] = results['coeff_moment'][:, 2]

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f"{file_path.stem}_result_{timestamp}.csv"
        output_df.to_csv(output_file, index=False)
        return output_file

    def request_stop(self):
        """请求停止后台线程的处理（线程在处理间检查此标志）。"""
        self._stop_requested = True

    def run(self):
        try:
            total = len(self.file_list)
            success = 0
            elapsed_list = []

            if self.registry_db:
                try:
                    self.log_message.emit(f"使用 format registry: {self.registry_db}")
                except RuntimeError as re:
                    logger.debug("Signal emit failed for registry_db message: %s", re, exc_info=True)
                except Exception:
                    logger.exception("Unexpected error when emitting registry message")

            for i, file_path in enumerate(self.file_list):
                # 在每个文件开始前检查取消请求
                if self._stop_requested:
                    try:
                        self.log_message.emit("用户取消：正在停止批处理")
                    except Exception:
                        logger.debug("Cannot emit cancel log message", exc_info=True)
                    break
                # per-file timing
                file_start = datetime.now()
                try:
                    self.log_message.emit(f"处理 [{i+1}/{total}]: {file_path.name}")
                except Exception:
                    logger.debug("无法发出开始处理消息: %s", file_path, exc_info=True)

                try:
                    output_file = self.process_file(file_path)
                    file_elapsed = (datetime.now() - file_start).total_seconds()
                    elapsed_list.append(file_elapsed)
                    avg = sum(elapsed_list) / len(elapsed_list)
                    remaining = total - (i + 1)
                    eta = int(avg * remaining)

                    try:
                        self.log_message.emit(f"  ✓ 完成: {output_file.name} (耗时: {file_elapsed:.2f}s)")
                    except Exception:
                        logger.debug("Cannot emit success message for %s", file_path, exc_info=True)

                    # 记录 ETA 与平均耗时
                    try:
                        self.log_message.emit(f"已完成 {i+1}/{total}，平均每文件耗时 {avg:.2f}s，预计剩余 {eta}s")
                    except Exception:
                        logger.debug("无法发出 ETA 消息", exc_info=True)

                    success += 1

                except (ValueError, IndexError, OSError) as e:
                    file_elapsed = (datetime.now() - file_start).total_seconds()
                    elapsed_list.append(file_elapsed)
                    logger.debug("File processing failed for %s: %s", file_path, e, exc_info=True)
                    try:
                        self.log_message.emit(f"  ✗ 失败: {e} (耗时: {file_elapsed:.2f}s)")
                    except Exception:
                        logger.debug("Cannot emit failure message for %s: %s", file_path, e, exc_info=True)

                except Exception as e:
                    file_elapsed = (datetime.now() - file_start).total_seconds()
                    elapsed_list.append(file_elapsed)
                    logger.exception("Unexpected error processing file %s", file_path)
                    try:
                        self.log_message.emit(f"  ✗ 未知错误: 请查看日志以获取详细信息 (耗时: {file_elapsed:.2f}s)")
                    except Exception:
                        logger.debug("Cannot emit unknown error message for %s", file_path, exc_info=True)

                # 更新进度条
                try:
                    pct = int((i + 1) / total * 100)
                    self.progress.emit(pct)
                except Exception:
                    logger.debug("Unable to emit progress value for %s", file_path, exc_info=True)

            # 结束
            total_elapsed = sum(elapsed_list)
            try:
                msg = f"成功处理 {success}/{total} 个文件，耗时 {total_elapsed:.2f}s"
                if self._stop_requested:
                    msg = f"已取消：已处理 {success}/{total} 个文件，耗时 {total_elapsed:.2f}s"
                self.finished.emit(msg)
            except Exception:
                logger.debug("Cannot emit finished signal", exc_info=True)

        except Exception as e:
            logger.exception("BatchProcessThread.run 出现未处理异常")
            self.error.emit(str(e))


class IntegratedAeroGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MomentTransfer v2.0 - 气动载荷坐标变换工具")
        self.resize(1400, 850)

        self.calculator = None
        self.current_config = None
        self.data_config = None
        self.canvas3d = None
        self.visualization_window = None

        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.create_config_panel())
        splitter.addWidget(self.create_operation_panel())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        # 初始 splitter 大小，优先显示左侧配置和右侧操作（近似匹配图一布局）
        try:
            splitter.setSizes([520, 880])
        except Exception:
            logger.debug("splitter.setSizes failed (non-fatal)", exc_info=True)

        main_layout.addWidget(splitter)
        self.statusBar().showMessage("就绪 - 请加载或创建配置")

        # 根据当前窗口宽度设置按钮初始布局
        try:
            self.update_button_layout()
        except Exception:
            # 若方法尚未定义或出现异常，记录调试堆栈以便诊断，但不阻止 UI 启动
            logger.debug("update_button_layout failed (non-fatal)", exc_info=True)

    def create_config_panel(self):
        """创建左侧配置编辑面板"""
        panel = QWidget()
        # 给左侧配置面板一个合理的最小宽度，避免在窄窗口时完全压扁
        panel.setMinimumWidth(420)
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        # 标题与可视化按钮
        header_layout = QHBoxLayout()
        title = QLabel("配置编辑器")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")

        # 允许用户显示实验性选项（默认隐藏）
        self.chk_show_experimental = QCheckBox("显示实验性选项（实验）")
        self.chk_show_experimental.setToolTip("显示/隐藏实验性功能：包括 3D 可视化 与 per-file 覆盖（仅用于调试/示例）")
        try:
            self.chk_show_experimental.stateChanged.connect(lambda _: self._toggle_experimental_visibility())
        except Exception:
            logger.debug("Failed to connect chk_show_experimental signal", exc_info=True)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.chk_show_experimental)

        # 当实验选项切换时刷新布局显示
        try:
            self.chk_show_experimental.stateChanged.connect(lambda _: self._toggle_experimental_visibility())
        except Exception:
            logger.debug("Failed to connect chk_show_experimental (second)", exc_info=True)

        layout.addLayout(header_layout)

        # === Source 坐标系（可折叠） ===
        self.chk_show_source = QCheckBox("显示 Source 坐标系设置")
        self.chk_show_source.setStyleSheet("font-weight: bold; color: #0078d7;")
        self.chk_show_source.stateChanged.connect(self.toggle_source_visibility)
        layout.addWidget(self.chk_show_source)

        self.grp_source = QGroupBox("Source Coordinate System")
        self.grp_source.setStyleSheet("QGroupBox { font-weight: bold; }")
        # 允许在垂直方向扩展以填充空间，使底部按钮保持在窗口底部
        self.grp_source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form_source = QFormLayout()

        self.src_ox = self._create_input("0.0")
        self.src_oy = self._create_input("0.0")
        self.src_oz = self._create_input("0.0")

        # Source Part Name（与 Target 对等）
        self.src_part_name = self._create_input("Global")

        self.src_xx = self._create_input("1.0")
        self.src_xy = self._create_input("0.0")
        self.src_xz = self._create_input("0.0")

        self.src_yx = self._create_input("0.0")
        self.src_yy = self._create_input("1.0")
        self.src_yz = self._create_input("0.0")

        self.src_zx = self._create_input("0.0")
        self.src_zy = self._create_input("0.0")
        self.src_zz = self._create_input("1.0")

        # Source 力矩中心
        self.src_mcx = self._create_input("0.0")
        self.src_mcy = self._create_input("0.0")
        self.src_mcz = self._create_input("0.0")

        form_source.addRow("Part Name:", self.src_part_name)
        form_source.addRow("Orig:", self._create_vector_row(self.src_ox, self.src_oy, self.src_oz))
        form_source.addRow("X:", self._create_vector_row(self.src_xx, self.src_xy, self.src_xz))
        form_source.addRow("Y:", self._create_vector_row(self.src_yx, self.src_yy, self.src_yz))
        form_source.addRow("Z:", self._create_vector_row(self.src_zx, self.src_zy, self.src_zz))

        # Source 参考量（与 Target 对等）
        self.src_cref = self._create_input("1.0")
        self.src_bref = self._create_input("1.0")
        self.src_sref = self._create_input("10.0")
        self.src_q = self._create_input("1000.0")

        form_source.addRow("Moment Center:", self._create_vector_row(self.src_mcx, self.src_mcy, self.src_mcz))
        form_source.addRow("C_ref (m):", self.src_cref)
        form_source.addRow("B_ref (m):", self.src_bref)
        form_source.addRow("S_ref (m²):", self.src_sref)
        form_source.addRow("Q (Pa):", self.src_q)

        self.grp_source.setLayout(form_source)
        self.grp_source.setVisible(False)
        layout.addWidget(self.grp_source)

        # === Target 配置 ===
        grp_target = QGroupBox("Target Configuration")
        grp_target.setStyleSheet("QGroupBox { font-weight: bold; }")
        grp_target.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form_target = QFormLayout()

        # Part Name
        self.tgt_part_name = QLineEdit("TestModel")
        form_target.addRow("Part Name:", self.tgt_part_name)

        # 当加载 ProjectData 时，展示可选的 Part 下拉框与 Variant 索引选择器
        self.cmb_target_parts = QComboBox()
        self.cmb_target_parts.setVisible(False)
        self.spin_target_variant = QSpinBox()
        self.spin_target_variant.setRange(0, 100)
        self.spin_target_variant.setValue(0)
        self.spin_target_variant.setVisible(False)
        # 当选择不同 part 时，更新 variant 最大值（在 load_config 中设置）
        self.cmb_target_parts.currentTextChanged.connect(lambda _: self._on_target_part_changed())
        form_target.addRow("选择 Target Part:", self.cmb_target_parts)
        form_target.addRow("Variant 索引:", self.spin_target_variant)

        # Target 坐标系
        self.tgt_ox = self._create_input("0.0")
        self.tgt_oy = self._create_input("0.0")
        self.tgt_oz = self._create_input("0.0")

        self.tgt_xx = self._create_input("1.0")
        self.tgt_xy = self._create_input("0.0")
        self.tgt_xz = self._create_input("0.0")

        self.tgt_yx = self._create_input("0.0")
        self.tgt_yy = self._create_input("1.0")
        self.tgt_yz = self._create_input("0.0")

        self.tgt_zx = self._create_input("0.0")
        self.tgt_zy = self._create_input("0.0")
        self.tgt_zz = self._create_input("1.0")

        form_target.addRow("Orig:", self._create_vector_row(self.tgt_ox, self.tgt_oy, self.tgt_oz))
        form_target.addRow("X:", self._create_vector_row(self.tgt_xx, self.tgt_xy, self.tgt_xz))
        form_target.addRow("Y:", self._create_vector_row(self.tgt_yx, self.tgt_yy, self.tgt_yz))
        form_target.addRow("Z:", self._create_vector_row(self.tgt_zx, self.tgt_zy, self.tgt_zz))

        # Moment Center
        self.tgt_mcx = self._create_input("0.5")
        self.tgt_mcy = self._create_input("0.0")
        self.tgt_mcz = self._create_input("0.0")
        form_target.addRow("Moment Center:", self._create_vector_row(self.tgt_mcx, self.tgt_mcy, self.tgt_mcz))

        # Target 参考量（与 Source 对等）
        self.tgt_cref = self._create_input("1.0")
        self.tgt_bref = self._create_input("1.0")
        self.tgt_sref = self._create_input("10.0")
        self.tgt_q = self._create_input("1000.0")

        form_target.addRow("C_ref (m):", self.tgt_cref)
        form_target.addRow("B_ref (m):", self.tgt_bref)
        form_target.addRow("S_ref (m²):", self.tgt_sref)
        form_target.addRow("Q (Pa):", self.tgt_q)
        grp_target.setLayout(form_target)

        # === 配置操作按钮 ===
        btn_layout = QHBoxLayout()

        self.btn_load = QPushButton("加载配置")
        self.btn_load.setFixedHeight(34)
        self.btn_load.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_load.clicked.connect(self.load_config)

        self.btn_save = QPushButton("保存配置")
        self.btn_save.setFixedHeight(34)
        self.btn_save.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_save.clicked.connect(self.save_config)

        self.btn_apply = QPushButton("应用配置")
        self.btn_apply.setFixedHeight(34)
        self.btn_apply.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold;")
        self.btn_apply.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_apply.clicked.connect(self.apply_config)

        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_apply)

        # 添加到主布局
        layout.addWidget(grp_target)
        # layout.addWidget(grp_global)  # 删除未定义的grp_global，避免报错
        layout.addLayout(btn_layout)
        # 设置伸缩：让 Source/Target 在垂直方向扩展以填充空间
        # header_layout index 0, chk_show_source index 1, grp_source index 2, grp_target index 3, btn_layout index 4
        try:
            layout.setStretch(2, 1)
            layout.setStretch(3, 1)
        except Exception:
            logger.debug("layout.setStretch failed (non-fatal)", exc_info=True)
        layout.addStretch()

        return panel

    def create_operation_panel(self):
        """创建右侧操作面板"""
        panel = QWidget()
        # 给右侧操作面板设定最小宽度，保证批处理控件可见性
        panel.setMinimumWidth(600)
        layout = QVBoxLayout(panel)
        layout.setSpacing(15)

        # === 配置状态显示 ===
        status_group = QGroupBox("当前配置状态")
        status_layout = QHBoxLayout()
        self.lbl_status = QLabel("未加载配置")
        self.lbl_status.setStyleSheet("color: red; font-weight: bold; font-size: 13px;")
        status_layout.addWidget(self.lbl_status)
        status_layout.addStretch()
        status_group.setLayout(status_layout)

        # === 批量处理区 ===
        grp_batch = QGroupBox("批量处理 (Batch Processing)")
        grp_batch.setStyleSheet("QGroupBox { font-weight: bold; }")
        grp_batch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout_batch = QVBoxLayout()

        # 文件选择
        file_form = QFormLayout()

        input_row = QHBoxLayout()
        self.inp_batch_input = QLineEdit()
        self.inp_batch_input.setPlaceholderText("选择文件或目录...")
        btn_browse_input = QPushButton("浏览")
        btn_browse_input.setMaximumWidth(80)
        btn_browse_input.clicked.connect(self.browse_batch_input)
        input_row.addWidget(self.inp_batch_input)
        input_row.addWidget(btn_browse_input)

        # 文件匹配模式
        pattern_row = QHBoxLayout()
        self.inp_pattern = QLineEdit("*.csv")
        self.inp_pattern.setToolTip("文件名匹配模式，如 *.csv, data_*.xlsx")
        pattern_row.addWidget(QLabel("匹配模式:"))
        pattern_row.addWidget(self.inp_pattern)

        # Registry DB 输入行（可选，实验性）
        registry_row = QHBoxLayout()
        self.inp_registry_db = QLineEdit()
        self.inp_registry_db.setPlaceholderText("可选: format registry 数据库 (.sqlite) - 实验性")
        # 当 registry 路径变化时刷新文件来源标签（实时反馈）
        try:
            self.inp_registry_db.textChanged.connect(lambda _: self._refresh_format_labels())
        except Exception:
            logger.debug("Failed to connect inp_registry_db.textChanged signal", exc_info=True)
        btn_browse_registry = QPushButton("浏览")
        btn_browse_registry.setMaximumWidth(80)
        btn_browse_registry.clicked.connect(self.browse_registry_db)
        registry_row.addWidget(QLabel("格式注册表 (实验):"))
        registry_row.addWidget(self.inp_registry_db)
        registry_row.addWidget(btn_browse_registry)

        # 启用 per-file 覆盖（启用后会使用侧车/目录/registry 覆盖每个文件的格式）
        self.chk_enable_sidecar = QCheckBox("启用 per-file 覆盖（sidecar/registry，实验）")
        self.chk_enable_sidecar.setChecked(False)
        self.chk_enable_sidecar.setToolTip("默认关闭；启用后会按文件尝试使用侧车/目录或 registry 来覆盖全局配置。建议仅在需要时启用。")
        registry_row.addWidget(self.chk_enable_sidecar)

        # 注意：不要把 registry_row 直接添加到 file_form（我们会把它放到实验性组中）
        # file_form.addRow("", registry_row)  # 已移至实验性组

        # Registry 映射管理区（列表 + 注册/删除）
        self.grp_registry_list = QGroupBox("Registry 映射管理 (可选)")
        self.grp_registry_list.setVisible(False)
        reg_layout = QVBoxLayout()

        # 列表
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        self.lst_registry = QListWidget()
        self.lst_registry.setSelectionMode(QListWidget.SingleSelection)
        self.lst_registry.setMinimumHeight(100)

        # 注册行：pattern + format path + browse + 预览
        reg_form = QHBoxLayout()
        self.inp_registry_pattern = QLineEdit()
        self.inp_registry_pattern.setPlaceholderText("Pattern，例如: sample.csv 或 *.csv")
        self.inp_registry_format = QLineEdit()
        self.inp_registry_format.setPlaceholderText("Format 文件路径 (JSON)")
        btn_browse_format = QPushButton("浏览格式文件")
        btn_browse_format.setMaximumWidth(90)
        btn_browse_format.clicked.connect(self._browse_registry_format)
        btn_preview_format = QPushButton("预览格式")
        btn_preview_format.setMaximumWidth(90)
        btn_preview_format.clicked.connect(self._on_preview_format)
        reg_form.addWidget(self.inp_registry_pattern)
        reg_form.addWidget(self.inp_registry_format)
        reg_form.addWidget(btn_browse_format)
        reg_form.addWidget(btn_preview_format)

        # 操作按钮
        ops_row = QHBoxLayout()
        self.btn_registry_register = QPushButton("注册映射")
        self.btn_registry_edit = QPushButton("编辑选中")
        self.btn_registry_remove = QPushButton("删除选中")
        self.btn_registry_register.clicked.connect(self._on_registry_register)
        self.btn_registry_edit.clicked.connect(self._on_registry_edit)
        self.btn_registry_remove.clicked.connect(self._on_registry_remove)
        ops_row.addWidget(self.btn_registry_register)
        ops_row.addWidget(self.btn_registry_edit)
        ops_row.addWidget(self.btn_registry_remove)

        reg_layout.addWidget(self.lst_registry)
        reg_layout.addLayout(reg_form)
        reg_layout.addLayout(ops_row)
        self.grp_registry_list.setLayout(reg_layout)

        file_form.addRow("输入路径:", input_row)
        file_form.addRow("", pattern_row)
        # registry_row 已放入实验性功能组，避免在主表单重复显示

        # 文件列表（可复选、可滚动），默认位于数据格式配置之上
        self.grp_file_list = QGroupBox("找到的文件列表")
        self.grp_file_list.setVisible(False)
        file_list_layout = QVBoxLayout()
        self.file_scroll = QScrollArea()
        self.file_scroll.setWidgetResizable(True)
        self.file_list_widget = QWidget()
        self.file_list_layout_inner = QVBoxLayout(self.file_list_widget)
        # 保证复选框列表从顶部开始排列
        try:
            self.file_list_layout_inner.setAlignment(Qt.AlignTop)
        except Exception as e:
            logger.debug("Error while setting file list layout alignment", exc_info=True)
        self.file_list_layout_inner.setContentsMargins(4, 4, 4, 4)
        self.file_scroll.setWidget(self.file_list_widget)
        # 给文件滚动区域一个最小高度，避免在窄窗口或重排时过度收缩
        self.file_scroll.setMinimumHeight(180)
        file_list_layout.addWidget(self.file_scroll)
        self.grp_file_list.setLayout(file_list_layout)

        # 存储文件复选框相关信息的元组列表。
        # 每个元素为 (checkbox: QCheckBox, path: Path, label: Optional[QLabel])，
        # 其中 label 可选，因此在使用处可能通过 *rest 等方式解包。
        self._file_check_items: List[Tuple[QCheckBox, Path, Optional[QLabel]]] = []


        # 数据格式配置按钮（并作为实例属性，放入可切换的容器）
        self.btn_config_format = QPushButton("⚙ 配置数据格式")
        self.btn_config_format.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        self.btn_config_format.setToolTip("设置跳过行数、列映射等")
        self.btn_config_format.clicked.connect(self.configure_data_format)

        # 进度条（隐藏，运行时显示）
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        # 执行按钮（作为实例属性）
        self.btn_batch = QPushButton("开始批量处理")
        self.btn_batch.setFixedHeight(34)
        self.btn_batch.setStyleSheet("background-color: #ff6b6b; color: white; font-weight: bold;")
        self.btn_batch.clicked.connect(self.run_batch_processing)

        # 取消按钮（仅在任务运行时显示并可用）
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold;")
        self.btn_cancel.clicked.connect(self.request_cancel_batch)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(False)

        # 日志
        self.txt_batch_log = QTextEdit()
        self.txt_batch_log.setReadOnly(True)
        self.txt_batch_log.setFont(QFont("Consolas", 9))
        self.txt_batch_log.setMinimumHeight(160)
        self.txt_batch_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 按钮容器（使用 QGridLayout，后续由 update_button_layout 切换位置）
        self.btn_widget = QWidget()
        # 确保按钮区域在布局收缩时仍可见，允许在垂直方向上保留最小高度但可在必要时伸缩
        self.btn_widget.setMinimumHeight(44)
        self.btn_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        grid = QGridLayout(self.btn_widget)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)
        # 平分列的伸缩因子，避免第二列在窗口恢复时被挤出可见区域
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.btn_config_format.setFixedHeight(34)
        self.btn_config_format.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_batch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 初始放置为一行两列（取消按钮放在第二行右侧）
        grid.addWidget(self.btn_config_format, 0, 0)
        grid.addWidget(self.btn_batch, 0, 1)
        grid.addWidget(self.btn_cancel, 1, 1)
        # 固定并复用这个 grid，避免后续替换 layout 导致 Qt 布局对象延迟删除出现几何错误
        self.btn_grid = grid

        layout_batch.addLayout(file_form)
        layout_batch.addWidget(self.grp_registry_list)
        layout_batch.addWidget(self.grp_file_list)
        layout_batch.addWidget(self.progress_bar)
        layout_batch.addWidget(self.btn_widget)

        # === 实验性功能组（包含 3D 可视化与 per-file 覆盖相关控件） ===
        self.grp_experimental = QGroupBox("实验性功能（实验）")
        self.grp_experimental.setVisible(False)
        exp_layout = QVBoxLayout()

        # 3D 可视化按钮（移入实验组）
        self.btn_visualize = QPushButton("3D可视化")
        self.btn_visualize.setMaximumWidth(120)
        self.btn_visualize.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold;")
        self.btn_visualize.setToolTip("打开3D坐标系可视化窗口（实验）")
        self.btn_visualize.clicked.connect(self.toggle_visualization)
        exp_layout.addWidget(self.btn_visualize)

        # 把 registry_row 放到实验组
        exp_layout.addLayout(registry_row)

        self.grp_experimental.setLayout(exp_layout)
        layout_batch.addWidget(self.grp_experimental)

        layout_batch.addWidget(QLabel("处理日志:"))
        layout_batch.addWidget(self.txt_batch_log)
        # 让日志框占据剩余垂直空间，从而使外部 groupbox 底部贴近窗口底部
        # 对应索引: 0=file_form,1=grp_registry_list,2=grp_file_list,3=progress_bar,4=btn_widget,5=Label,6=txt_batch_log
        try:
            # 使文件列表与日志框可以拉伸（优先日志框）
            layout_batch.setStretch(2, 0)
            layout_batch.setStretch(6, 1)
        except Exception:
            logger.debug("layout_batch.setStretch failed (non-fatal)", exc_info=True)

        grp_batch.setLayout(layout_batch)

        # === 配置预览（在状态栏下方）===
        self.grp_config_preview = QGroupBox("数据格式预览")
        # 限制预览面板高度，避免在右侧占用过多空间
        try:
            self.grp_config_preview.setMaximumHeight(140)
            self.grp_config_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass
        pv_layout = QVBoxLayout()
        # 显示当前数据格式的关键信息：跳过行、列映射摘要、保留列
        self.lbl_preview_skip = QLabel("跳过行: -")
        self.lbl_preview_columns = QLabel("列映射: -")
        self.lbl_preview_passthrough = QLabel("保留列: -")
        for w in (self.lbl_preview_skip, self.lbl_preview_columns, self.lbl_preview_passthrough):
            w.setStyleSheet("font-size:12px;")
            pv_layout.addWidget(w)
        self.grp_config_preview.setLayout(pv_layout)

        # === 最近项目与快捷操作 ===
        recent_group = QGroupBox("最近项目 & 快捷操作")
        recent_layout = QVBoxLayout()
        from PySide6.QtWidgets import QListWidget
        self.lst_recent = QListWidget()
        self.lst_recent.setMaximumHeight(120)
        self.lst_recent.itemActivated.connect(lambda it: self.inp_batch_input.setText(it.text()))
        recent_layout.addWidget(QLabel("最近打开的配置/项目（双击以填充输入路径）:"))
        recent_layout.addWidget(self.lst_recent)

        # 默认输出目录行
        out_row = QHBoxLayout()
        self.inp_default_output = QLineEdit()
        self.inp_default_output.setPlaceholderText("默认输出目录，可选")
        btn_browse_default_out = QPushButton("浏览")
        btn_browse_default_out.clicked.connect(lambda: self._browse_default_output())
        out_row.addWidget(self.inp_default_output)
        out_row.addWidget(btn_browse_default_out)
        recent_layout.addLayout(out_row)

        # 一键处理按钮
        self.btn_quick = QPushButton("一键处理")
        self.btn_quick.setToolTip("使用当前配置与默认输出目录快速开始批处理")
        self.btn_quick.clicked.connect(self.one_click_process)
        recent_layout.addWidget(self.btn_quick)
        recent_group.setLayout(recent_layout)

        layout.addWidget(status_group)
        layout.addWidget(self.grp_config_preview)
        # 将最近项目与快捷操作移动到实验性组，避免在默认界面显示
        try:
            if hasattr(self, 'grp_experimental') and self.grp_experimental is not None:
                exp_layout.addWidget(recent_group)
            else:
                layout.addWidget(recent_group)
        except Exception:
            # 若实验组不可用，退回到主布局以保证可访问性
            layout.addWidget(recent_group)
        layout.addWidget(grp_batch)
        # 为了让右侧的 grp_batch 在垂直方向上拉伸并触底，设置 layout 的 stretch
        try:
            # status_group 在顶部不拉伸，grp_batch 占据剩余空间
            try:
                idx_status = layout.indexOf(status_group)
                if idx_status >= 0:
                    layout.setStretch(idx_status, 0)
            except Exception:
                pass
            try:
                idx_batch = layout.indexOf(grp_batch)
                if idx_batch >= 0:
                    layout.setStretch(idx_batch, 1)
            except Exception:
                # 备用：如果 indexOf 不可用，尝试保守设置原来的索引
                try:
                    layout.setStretch(0, 0)
                    layout.setStretch(1, 1)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("layout.setStretch failed (non-fatal)", exc_info=True)
        # 保留一个小的伸缩因子以兼容不同平台的行为
        layout.addStretch()

        return panel

    def _create_input(self, default_value):
        """创建输入框"""
        inp = QLineEdit(default_value)
        # 提高最大宽度以适配高 DPI 和更长的数值输入，同时使用合适的 sizePolicy
        inp.setMaximumWidth(120)
        try:
            inp.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        except Exception:
            logger.debug("inp.setSizePolicy failed (non-fatal)", exc_info=True)
        return inp

    def _create_vector_row(self, inp1, inp2, inp3):
        """创建向量输入行 [x, y, z]"""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        layout.addWidget(QLabel("["))
        layout.addWidget(inp1)
        layout.addWidget(QLabel(","))
        layout.addWidget(inp2)
        layout.addWidget(QLabel(","))
        layout.addWidget(inp3)
        layout.addWidget(QLabel("]"))
        # 使用小间距替代 stretch，避免把右侧控件挤出可见区域
        layout.addSpacing(6)

        return row

    def toggle_source_visibility(self, state):
        """切换 Source 坐标系的显示/隐藏"""
        self.grp_source.setVisible(state == Qt.Checked)
        # 切换后刷新布局以确保组框填满高度并使右侧底部元素可见
        try:
            QTimer.singleShot(30, self._refresh_layouts)
        except RuntimeError as re:
            logger.debug("QTimer.singleShot 调度失败: %s", re, exc_info=True)
            try:
                self._refresh_layouts()
            except Exception as e:
                logger.exception("_refresh_layouts 直接调用时出现异常")
        except Exception as e:
            logger.exception("调度 _refresh_layouts 时出现意外异常")

    def toggle_visualization(self):
        """切换3D可视化窗口"""
        if self.visualization_window is None or not self.visualization_window.isVisible():
            self.show_visualization()
        else:
            self.visualization_window.close()
            self.visualization_window = None

    def show_visualization(self):
        """显示3D可视化窗口"""
        try:
            # 读取当前配置
            source_orig = [float(self.src_ox.text()), float(self.src_oy.text()), float(self.src_oz.text())]
            source_basis = np.array([
                [float(self.src_xx.text()), float(self.src_xy.text()), float(self.src_xz.text())],
                [float(self.src_yx.text()), float(self.src_yy.text()), float(self.src_yz.text())],
                [float(self.src_zx.text()), float(self.src_zy.text()), float(self.src_zz.text())]
            ])

            target_orig = [float(self.tgt_ox.text()), float(self.tgt_oy.text()), float(self.tgt_oz.text())]
            target_basis = np.array([
                [float(self.tgt_xx.text()), float(self.tgt_xy.text()), float(self.tgt_xz.text())],
                [float(self.tgt_yx.text()), float(self.tgt_yy.text()), float(self.tgt_yz.text())],
                [float(self.tgt_zx.text()), float(self.tgt_zy.text()), float(self.tgt_zz.text())]
            ])

            moment_center = [float(self.tgt_mcx.text()), float(self.tgt_mcy.text()), float(self.tgt_mcz.text())]

            # 创建可视化窗口
            self.visualization_window = QWidget()
            self.visualization_window.setWindowTitle(f"3D坐标系可视化 - {self.tgt_part_name.text()}")
            self.visualization_window.resize(800, 600)

            layout = QVBoxLayout(self.visualization_window)

            # 创建3D画布
            self.canvas3d = Mpl3DCanvas(self.visualization_window, width=8, height=6, dpi=100)
            self.canvas3d.plot_systems(source_orig, source_basis, target_orig, target_basis, moment_center)

            # 添加说明文本
            info_label = QLabel(
                "灰色虚线: Source坐标系 | 彩色实线: Target坐标系 | 紫色点: 力矩中心\n"
                "提示: 可以使用鼠标拖动旋转视角"
            )
            info_label.setStyleSheet("background-color: #f0f0f0; padding: 8px; border-radius: 4px; font-size: 10px;")

            layout.addWidget(info_label)
            layout.addWidget(self.canvas3d)

            self.visualization_window.show()

        except ValueError as e:
            QMessageBox.warning(self, "输入错误", f"请检查坐标系数值输入:\n{str(e)}")

    def load_config(self):
        """加载配置文件"""
        try:
            fname, _ = QFileDialog.getOpenFileName(self, '打开配置', '.', 'JSON Files (*.json)')
            if not fname:
                # 用户取消选择时不进行任何操作
                return
            with open(fname, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 解析为严格的 ProjectData（新版格式，包含 Parts）
            project = ProjectData.from_dict(data)
            self.current_config = project

            # 填充下拉列表与 variant 控件
            self.cmb_target_parts.clear()
            for part in project.target_parts.keys():
                self.cmb_target_parts.addItem(part)
            if self.cmb_target_parts.count() > 0:
                self.cmb_target_parts.setVisible(True)
                self.spin_target_variant.setVisible(True)
                first = self.cmb_target_parts.currentText() or self.cmb_target_parts.itemText(0)
                variants = project.target_parts.get(first, [])
                self.spin_target_variant.setRange(0, max(0, len(variants) - 1))

            # 使用选定的 variant 填充 Target 表单
            try:
                sel_part = self.cmb_target_parts.currentText() or self.cmb_target_parts.itemText(0)
                sel_variant = int(self.spin_target_variant.value())
                frame = project.get_target_part(sel_part, sel_variant)
                cs = frame.coord_system
                mc = frame.moment_center or [0.0, 0.0, 0.0]

                self.tgt_part_name.setText(frame.part_name)
                self.tgt_ox.setText(str(cs.origin[0]))
                self.tgt_oy.setText(str(cs.origin[1]))
                self.tgt_oz.setText(str(cs.origin[2]))
                self.tgt_xx.setText(str(cs.x_axis[0]))
                self.tgt_xy.setText(str(cs.x_axis[1]))
                self.tgt_xz.setText(str(cs.x_axis[2]))
                self.tgt_yx.setText(str(cs.y_axis[0]))
                self.tgt_yy.setText(str(cs.y_axis[1]))
                self.tgt_yz.setText(str(cs.y_axis[2]))
                self.tgt_zx.setText(str(cs.z_axis[0]))
                self.tgt_zy.setText(str(cs.z_axis[1]))
                self.tgt_zz.setText(str(cs.z_axis[2]))
                self.tgt_mcx.setText(str(mc[0]))
                self.tgt_mcy.setText(str(mc[1]))
                self.tgt_mcz.setText(str(mc[2]))
                self.tgt_cref.setText(str(frame.c_ref or 1.0))
                self.tgt_bref.setText(str(frame.b_ref or 1.0))
                self.tgt_sref.setText(str(frame.s_ref or 10.0))
                self.tgt_q.setText(str(frame.q or 1000.0))

            except Exception as e:
                logger.debug("在填充 Target 表单时发生错误: %s", e, exc_info=True)

            QMessageBox.information(self, "成功", f"配置已加载:\n{fname}")
            self.statusBar().showMessage(f"已加载: {fname}")

            # 自动应用（会使用 project + 选定的 target part/variant）
            try:
                self.apply_config()
            except Exception:
                logger.debug("自动应用配置时出错（忽略）", exc_info=True)

            try:
                self.add_recent_project(fname)
            except Exception:
                logger.debug("add_recent_project failed", exc_info=True)

        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法加载配置文件:\n{str(e)}")

    def save_config(self):
        """保存配置到JSON"""
        try:
            # 按新版 Parts/Variants 格式保存（保证与 data_loader 的严格解析兼容）
            src_part = {
                "PartName": self.src_part_name.text() if hasattr(self, 'src_part_name') else "Global",
                "Variants": [
                    {
                        "PartName": self.src_part_name.text() if hasattr(self, 'src_part_name') else "Global",
                        "CoordSystem": {
                            "Orig": [float(self.src_ox.text()), float(self.src_oy.text()), float(self.src_oz.text())],
                            "X": [float(self.src_xx.text()), float(self.src_xy.text()), float(self.src_xz.text())],
                            "Y": [float(self.src_yx.text()), float(self.src_yy.text()), float(self.src_yz.text())],
                            "Z": [float(self.src_zx.text()), float(self.src_zy.text()), float(self.src_zz.text())]
                        },
                        "MomentCenter": [float(self.src_mcx.text()), float(self.src_mcy.text()), float(self.src_mcz.text())],
                        "Cref": float(self.src_cref.text()) if hasattr(self, 'src_cref') else 1.0,
                        "Bref": float(self.src_bref.text()) if hasattr(self, 'src_bref') else 1.0,
                        "Q": float(self.src_q.text()) if hasattr(self, 'src_q') else 1000.0,
                        "S": float(self.src_sref.text()) if hasattr(self, 'src_sref') else 10.0
                    }
                ]
            }

            tgt_part = {
                "PartName": self.tgt_part_name.text(),
                "Variants": [
                    {
                        "PartName": self.tgt_part_name.text(),
                        "CoordSystem": {
                            "Orig": [float(self.tgt_ox.text()), float(self.tgt_oy.text()), float(self.tgt_oz.text())],
                            "X": [float(self.tgt_xx.text()), float(self.tgt_xy.text()), float(self.tgt_xz.text())],
                            "Y": [float(self.tgt_yx.text()), float(self.tgt_yy.text()), float(self.tgt_yz.text())],
                            "Z": [float(self.tgt_zx.text()), float(self.tgt_zy.text()), float(self.tgt_zz.text())]
                        },
                        "MomentCenter": [float(self.tgt_mcx.text()), float(self.tgt_mcy.text()), float(self.tgt_mcz.text())],
                        "Cref": float(self.tgt_cref.text()) if hasattr(self, 'tgt_cref') else 1.0,
                        "Bref": float(self.tgt_bref.text()) if hasattr(self, 'tgt_bref') else 1.0,
                        "Q": float(self.tgt_q.text()) if hasattr(self, 'tgt_q') else 1000.0,
                        "S": float(self.tgt_sref.text()) if hasattr(self, 'tgt_sref') else 10.0
                    }
                ]
            }

            data = {
                "Source": {"Parts": [src_part]},
                "Target": {"Parts": [tgt_part]}
            }

            fname, _ = QFileDialog.getSaveFileName(self, '保存配置', 'config.json', 'JSON Files (*.json)')
            # 用户取消保存时立即返回，避免继续执行或触发异常处理逻辑
            if not fname:
                return
            with open(fname, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "成功", f"配置已保存:\n{fname}")
            self.statusBar().showMessage(f"已保存: {fname}")

        except ValueError as e:
            QMessageBox.warning(self, "输入错误", f"请检查数值输入是否正确:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def apply_config(self):
        """应用当前配置到计算器"""
        try:
            # 使用对等结构构建配置，方便 ProjectData.from_dict 解析
            data = {
                "Source": {
                    "PartName": self.src_part_name.text() if hasattr(self, 'src_part_name') else "Global",
                    "CoordSystem": {
                        "Orig": [float(self.src_ox.text()), float(self.src_oy.text()), float(self.src_oz.text())],
                        "X": [float(self.src_xx.text()), float(self.src_xy.text()), float(self.src_xz.text())],
                        "Y": [float(self.src_yx.text()), float(self.src_yy.text()), float(self.src_yz.text())],
                        "Z": [float(self.src_zx.text()), float(self.src_zy.text()), float(self.src_zz.text())]
                    },
                    "SourceMomentCenter": [float(self.src_mcx.text()), float(self.src_mcy.text()), float(self.src_mcz.text())],
                    "Cref": float(self.src_cref.text()) if hasattr(self, 'src_cref') else 1.0,
                    "Bref": float(self.src_bref.text()) if hasattr(self, 'src_bref') else 1.0,
                    "Q": float(self.src_q.text()) if hasattr(self, 'src_q') else 1000.0,
                    "S": float(self.src_sref.text()) if hasattr(self, 'src_sref') else 10.0
                },
                "Target": {
                    "PartName": self.tgt_part_name.text(),
                    "CoordSystem": {
                        "Orig": [float(self.tgt_ox.text()), float(self.tgt_oy.text()), float(self.tgt_oz.text())],
                        "X": [float(self.tgt_xx.text()), float(self.tgt_xy.text()), float(self.tgt_xz.text())],
                        "Y": [float(self.tgt_yx.text()), float(self.tgt_yy.text()), float(self.tgt_yz.text())],
                        "Z": [float(self.tgt_zx.text()), float(self.tgt_zy.text()), float(self.tgt_zz.text())]
                    },
                    "TargetMomentCenter": [float(self.tgt_mcx.text()), float(self.tgt_mcy.text()), float(self.tgt_mcz.text())],
                    "Cref": float(self.tgt_cref.text()) if hasattr(self, 'tgt_cref') else 1.0,
                    "Bref": float(self.tgt_bref.text()) if hasattr(self, 'tgt_bref') else 1.0,
                    "Q": float(self.tgt_q.text()) if hasattr(self, 'tgt_q') else 1000.0,
                    "S": float(self.tgt_sref.text()) if hasattr(self, 'tgt_sref') else 10.0
                }
            }

            # 解析为 ProjectData（严格格式），并使用显式的 target part/variant 构造计算器
            self.current_config = ProjectData.from_dict(data)

            # 决定要使用的 target part 与 variant（优先使用 GUI 下拉框）
            if hasattr(self, 'cmb_target_parts') and self.cmb_target_parts.isVisible() and self.cmb_target_parts.count() > 0:
                sel_part = self.cmb_target_parts.currentText()
                sel_variant = int(self.spin_target_variant.value())
            else:
                sel_part = self.tgt_part_name.text()
                sel_variant = 0

            # 构造时传入 project + 显式 target_part/variant，由 AeroCalculator 再次校验
            self.calculator = AeroCalculator(self.current_config, target_part=sel_part, target_variant=sel_variant)

            part_name = sel_part
            self.lbl_status.setText(f"已加载配置: {part_name}")
            self.lbl_status.setStyleSheet("color: green; font-weight: bold; font-size: 13px;")
            self.statusBar().showMessage(f"配置已应用: {part_name}")

            QMessageBox.information(self, "成功", f"配置已应用!\n组件: {part_name}\n现在可以进行计算了。")
            try:
                # 更新 GUI 的配置预览
                self.update_config_preview()
            except Exception:
                logger.debug("update_config_preview failed", exc_info=True)

        except ValueError as e:
            QMessageBox.warning(self, "输入错误", f"请检查数值输入:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "应用失败", f"配置应用失败:\n{str(e)}")

    def configure_data_format(self):
        """配置数据格式

        行为说明：
        - 如果在文件列表中选择了一个或多个文件，会尝试基于所选第一个文件查找可用的格式定义（优先级：registry -> file-sidecar -> dir -> global）。
        - 若找到多个候选格式文件，弹出候选选择对话让用户选择要加载的格式。
        - 若未找到任何格式文件，则打开空白/默认的列映射对话。
        """
        # 1) 确定目标文件（优先使用文件列表中勾选的项）
        chosen_fp = None
        try:
            items = getattr(self, '_file_check_items', None)
            if items:
                checked = [fp for cb, fp, *_ in items if cb.isChecked()]
                if len(checked) == 1:
                    chosen_fp = checked[0]
                elif len(checked) > 1:
                    # 多选时使用第一个作为配置目标，并提示用户
                    chosen_fp = checked[0]
                    self.txt_batch_log.append(f"注意：有多个文件被选中，正在为第一个选中项配置格式: {chosen_fp.name}")
        except (AttributeError, IndexError, TypeError) as e:
            logger.debug("Failed to determine chosen_fp", exc_info=True)
            chosen_fp = None

        # 1.5) 检查用户是否在 registry 列表中选中了某条映射；若有则优先作为编辑目标
        selected_registry_entry = None
        selected_format_path = None
        selected_source = None  # 'registry' | 'candidate' | None
        try:
            sel_entry = None
            if hasattr(self, 'lst_registry'):
                sel_items = self.lst_registry.selectedItems()
                if sel_items:
                    # 解析选中项的 id（格式为 [id] ...）
                    text = sel_items[0].text()
                    try:
                        if text.startswith('['):
                            end = text.find(']')
                            mid = text[1:end]
                            sel_id = int(mid)
                            dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
                            if dbp:
                                try:
                                    mappings = list_mappings(dbp)
                                    sel_entry = next((m for m in mappings if m['id'] == sel_id), None)
                                except (OSError, ValueError) as e:
                                    logger.debug("list_mappings failed while selecting registry entry: %s", e, exc_info=True)
                                    sel_entry = None
                    except (ValueError, IndexError, TypeError) as e:
                        logger.debug("Failed to parse selected registry item text", exc_info=True)
                        sel_entry = None
            if sel_entry:
                # 将选中 registry 映射作为预选格式
                selected_registry_entry = sel_entry
                selected_source = 'registry'
                try:
                    pf = Path(sel_entry['format_path'])
                    if pf.exists():
                        selected_format_path = pf
                except (OSError, KeyError, TypeError, ValueError) as e:
                    logger.debug("Failed to stat selected format path: %s", e, exc_info=True)
                    selected_format_path = None
        except (OSError, ValueError, TypeError) as e:
            logger.debug("Error while resolving selected registry entry", exc_info=True)

        # 2) 收集候选格式文件路径（仅在用户未显式选中 registry 映射时进行）
        candidate_paths = []
        try:
            if chosen_fp and selected_source != 'registry':
                # registry 优先查询（若用户提供了 registry 路径）
                try:
                    dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
                    if dbp:
                        try:
                            fmtp = get_format_for_file(dbp, str(chosen_fp))
                            if fmtp:
                                p = Path(fmtp)
                                if p.exists():
                                    candidate_paths.append(p)
                        except Exception:
                            logger.debug("get_format_for_file failed", exc_info=True)
                except Exception:
                    logger.debug("Error while checking registry DB path", exc_info=True)

                # sidecar 文件优先级（.format.json, .json）
                for suf in ('.format.json', '.json'):
                    cand = chosen_fp.parent / f"{chosen_fp.stem}{suf}"
                    if cand.exists():
                        candidate_paths.append(cand)

                # 目录级默认
                dir_cand = chosen_fp.parent / 'format.json'
                if dir_cand.exists():
                    candidate_paths.append(dir_cand)
        except Exception as e:
            logger.debug("Error while collecting candidate paths (outer)", exc_info=True)

        # 3) 如果找到多个候选，弹出选择对话
        try:
            if selected_source == 'registry':
                # 已有明确 registry 选择，跳过候选收集/选择
                pass
            elif len(candidate_paths) > 1:
                # 创建一个简易选择对话
                dlg = QDialog(self)
                dlg.setWindowTitle('选择要加载的格式文件')
                v = QVBoxLayout(dlg)
                from PySide6.QtWidgets import QListWidget, QListWidgetItem
                lw = QListWidget()
                for p in candidate_paths:
                    lw.addItem(str(p))
                v.addWidget(QLabel('找到多个格式定义，请选择要用于该文件的格式：'))
                v.addWidget(lw)
                btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                btns.accepted.connect(dlg.accept)
                btns.rejected.connect(dlg.reject)
                v.addWidget(btns)
                dlg.resize(600, 300)
                if dlg.exec() == QDialog.Accepted:
                    sel = lw.currentItem()
                    if sel:
                        selected_format_path = Path(sel.text())
                        selected_source = 'candidate'
                else:
                    # 用户取消选择：退回，不打开配置对话
                    return
            elif len(candidate_paths) == 1:
                selected_format_path = candidate_paths[0]
                selected_source = 'candidate'
        except Exception:
            selected_format_path = None

        # 4) 如果找到格式文件则尝试解析并用其内容预填充对话框
        initial_cfg = None
        if selected_format_path:
            try:
                fmt_path = Path(selected_format_path)
                with open(fmt_path, 'r', encoding='utf-8') as fh:
                    initial_cfg = json.load(fh)
                # 若 source 为 registry 但 selected_registry_entry 尚未指明（可能是通过 format_path 设置），尝试同步 entry
                if selected_source == 'registry' and selected_registry_entry is None:
                    try:
                        dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
                        if dbp:
                            mappings = list_mappings(dbp)
                            sel = next((m for m in mappings if Path(m['format_path']) == fmt_path), None)
                            if sel:
                                selected_registry_entry = sel
                    except Exception:
                        pass
            except Exception as e:
                QMessageBox.warning(self, '警告', f'无法加载格式文件: {selected_format_path}\n{e}')

        # 5) 打开 ColumnMappingDialog，并在可能时预填充
        dialog = ColumnMappingDialog(self)
        if initial_cfg:
            dialog.set_config(initial_cfg)

        if dialog.exec() == QDialog.Accepted:
            self.data_config = dialog.get_config()
            try:
                self.update_config_preview()
            except Exception:
                logger.debug("update_config_preview failed after configure_data_format", exc_info=True)

            # 在写文件/注册前询问用户意图，避免自动注册到 registry（registry 为实验性功能）
            try:
                cfg_to_write = self.data_config

                resp = QMessageBox.question(
                    self,
                    '保存数据格式',
                    '请选择保存方式：\n是: 保存并注册到 registry\n否: 仅保存为格式文件\n取消: 不保存',
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                )

                if resp == QMessageBox.Cancel:
                    self.txt_batch_log.append('已取消保存格式文件')
                    return

                # Helper to write cfg to path
                def _write_json(pth: Path):
                    pth.parent.mkdir(parents=True, exist_ok=True)
                    with open(pth, 'w', encoding='utf-8') as fh:
                        json.dump(cfg_to_write, fh, indent=2, ensure_ascii=False)

                # 若用户选择基于已有 registry 条目进行编辑（selected_registry_entry），总是写回到该 format 文件
                if selected_registry_entry is not None:
                    try:
                        fmtp = Path(selected_registry_entry['format_path'])
                        _write_json(fmtp)
                        # 仅在用户选择 "保存并注册" 时更新映射（触发 timestamp 刷新）
                        if resp == QMessageBox.Yes:
                            try:
                                dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
                                update_mapping(dbp, int(selected_registry_entry['id']), selected_registry_entry['pattern'], str(fmtp))
                                try:
                                    self._refresh_registry_list()
                                except Exception:
                                    pass
                            except Exception:
                                pass
                        self.txt_batch_log.append(f"已保存格式文件: {fmtp} (编辑 registry 条目 id={selected_registry_entry.get('id')})")
                    except Exception as e:
                        QMessageBox.warning(self, '保存失败', f'无法保存到 registry 指向的文件: {e}')
                        return

                else:
                    # 未基于 registry 映射：写为 sidecar（chosen file 的同名 .format.json）或 data 下的 timestamp 文件
                    try:
                        if chosen_fp:
                            sidecar = chosen_fp.parent / f"{chosen_fp.stem}.format.json"
                        else:
                            sidecar = Path('data') / f"format_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                        _write_json(sidecar)
                        self.txt_batch_log.append(f"已保存格式文件: {sidecar}")

                        # 仅在用户选择保存并注册时尝试注册到 registry
                        if resp == QMessageBox.Yes:
                            # 如果用户在界面中指定了 registry 路径，优先使用；否则使用项目默认 data/formats.sqlite
                            dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
                            if not dbp:
                                dbp = str(Path('data') / 'formats.sqlite')
                            try:
                                init_db(str(dbp))
                                default_pattern = chosen_fp.name if chosen_fp else sidecar.name
                                register_mapping(str(dbp), default_pattern, str(sidecar))
                                self.txt_batch_log.append(f"已注册到 registry: {dbp} (pattern={default_pattern})")
                            except Exception:
                                self.txt_batch_log.append(f"已保存格式文件: {sidecar} (注册到 registry 失败)")

                    except Exception as e:
                        QMessageBox.warning(self, '保存失败', f'无法保存格式文件: {e}')
                        return

            except Exception as e:
                QMessageBox.warning(self, '错误', f'保存格式时出错: {e}')

            # 提示用户保存结果摘要
            try:
                QMessageBox.information(self, "完成", "数据格式配置已处理（已写入/已注册的详情见处理日志）。")
            except Exception:
                pass

    def browse_batch_input(self):
        """选择输入文件或目录（单一对话框，支持切换文件/目录模式）。"""
        dlg = QFileDialog(self, '选择输入文件或目录')
        dlg.setOption(QFileDialog.DontUseNativeDialog, True)
        # 默认允许选择单个文件
        dlg.setFileMode(QFileDialog.ExistingFile)
        dlg.setNameFilter('Data Files (*.csv *.xlsx *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls)')

        # 添加切换目录选择的复选框（仅在非原生对话框时可用）
        chk_dir = QCheckBox('选择目录（切换到目录选择模式）')
        chk_dir.setToolTip('勾选后可以直接选择文件夹；不勾选则选择单个数据文件。')

        layout = dlg.layout()
        try:
            layout.addWidget(chk_dir)
        except Exception:
            # 若布局操作失败，忽略并继续（兼容不同平台）
            pass

        def on_toggle_dir(checked):
            if checked:
                dlg.setFileMode(QFileDialog.Directory)
                dlg.setOption(QFileDialog.ShowDirsOnly, True)
            else:
                dlg.setFileMode(QFileDialog.ExistingFile)
                dlg.setOption(QFileDialog.ShowDirsOnly, False)

        chk_dir.toggled.connect(on_toggle_dir)

        if dlg.exec() != QDialog.Accepted:
            return

        selected = dlg.selectedFiles()
        if not selected:
            return

        chosen_path = selected[0]
        self.inp_batch_input.setText(chosen_path)
        # 扫描并在界面上列出文件，用户可勾选要处理的文件
        try:
            self._scan_and_populate_files(chosen_path)
        except Exception as e:
            QMessageBox.warning(self, "扫描失败", f"扫描文件失败: {e}")

    def browse_registry_db(self):
        """选择 format registry 数据库文件（可选）"""
        fname, _ = QFileDialog.getOpenFileName(self, '选择 format registry 数据库', '.', 'SQLite DB Files (*.sqlite *.db);;All Files (*)')
        if fname:
            try:
                self.inp_registry_db.setText(fname)
                self.txt_batch_log.append(f"已选择 registry: {fname}")
                # 选择后刷新已有文件的来源标签
                try:
                    self._refresh_format_labels()
                except Exception:
                    pass
                # 刷新 registry 映射显示
                try:
                    self._refresh_registry_list()
                except Exception:
                    pass
            except Exception:
                pass

    def _browse_registry_format(self):
        """选择一个 format JSON 文件以便注册映射时使用"""
        fname, _ = QFileDialog.getOpenFileName(self, '选择 format JSON', '.', 'JSON Files (*.json);;All Files (*)')
        if fname:
            try:
                self.inp_registry_format.setText(fname)
            except Exception:
                pass

    def _on_registry_register(self):
        dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
        if not dbp:
            QMessageBox.warning(self, '错误', '请先选择 registry 数据库文件')
            return
        pat = self.inp_registry_pattern.text().strip()
        fmt = self.inp_registry_format.text().strip()
        if not pat or not fmt:
            QMessageBox.warning(self, '错误', '请填写 pattern 与 format 文件路径')
            return
        # 校验 format 文件是否存在且为合法 JSON
        try:
            fpath = Path(fmt)
            if not fpath.exists():
                QMessageBox.warning(self, '错误', f'格式文件不存在: {fmt}')
                return
            # 尝试解析 JSON
            with open(fpath, 'r', encoding='utf-8') as _fh:
                try:
                    json.load(_fh)
                except Exception as e:
                    QMessageBox.warning(self, '错误', f'格式文件不是有效的 JSON: {e}')
                    return
        except Exception:
            QMessageBox.warning(self, '错误', '无法访问或验证格式文件')
            return

        # 确认注册
        resp = QMessageBox.question(self, '确认', f'确定要注册映射吗？\n{pat} -> {fmt}', QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return

        # 如果处于编辑模式（存在 _editing_mapping_id），则执行 update
        if hasattr(self, '_editing_mapping_id') and self._editing_mapping_id is not None:
            try:
                update_mapping(dbp, self._editing_mapping_id, pat, fmt)
                self.txt_batch_log.append(f"已更新映射 id={self._editing_mapping_id}: {pat} -> {fmt}")
                # 清除编辑标识
                self._editing_mapping_id = None
                self._refresh_registry_list()
                return
            except Exception as e:
                QMessageBox.critical(self, '更新失败', str(e))
                return

        try:
            register_mapping(dbp, pat, fmt)
            self.txt_batch_log.append(f"已注册: {pat} -> {fmt}")
            self._refresh_registry_list()
        except Exception as e:
            QMessageBox.critical(self, '注册失败', str(e))

    def _on_registry_edit(self):
        """编辑选中映射：把选中项加载到输入框并在用户修改后更新。"""
        dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
        if not dbp:
            QMessageBox.warning(self, '错误', '请先选择 registry 数据库文件')
            return
        sel = self.lst_registry.selectedItems()
        if not sel:
            QMessageBox.warning(self, '错误', '请先选择要编辑的映射项')
            return
        text = sel[0].text()
        try:
            if text.startswith('['):
                end = text.find(']')
                mid = text[1:end]
                mapping_id = int(mid)
            else:
                raise ValueError('无法解析选中项 ID')
        except Exception as e:
            QMessageBox.critical(self, '错误', str(e))
            return

        # 把当前值填入输入框，允许用户修改并点击注册以提交（我们将把注册按钮作为新增/覆盖两用）
        # 也可以直接弹出编辑对话；这里采用填充方式并记录待编辑 id
        try:
            # 从 registry 读取当前映射详情
            mappings = list_mappings(dbp)
            entry = next((m for m in mappings if m['id'] == mapping_id), None)
            if not entry:
                QMessageBox.warning(self, '错误', f'映射 id={mapping_id} 未找到')
                return
            self.inp_registry_pattern.setText(entry['pattern'])
            self.inp_registry_format.setText(entry['format_path'])
            # 将编辑 id 存入属性以供后续保存
            self._editing_mapping_id = mapping_id
            QMessageBox.information(self, '编辑模式', f'已加载 id={mapping_id} 到输入框，修改后点击"注册映射"以保存')
        except Exception as e:
            QMessageBox.critical(self, '错误', str(e))

    def _on_registry_remove(self):
        dbp = self.inp_registry_db.text().strip() if hasattr(self, 'inp_registry_db') else ''
        if not dbp:
            QMessageBox.warning(self, '错误', '请先选择 registry 数据库文件')
            return
        sel = self.lst_registry.selectedItems()
        if not sel:
            QMessageBox.warning(self, '错误', '请先选择要删除的映射项')
            return
        # 解析选中项的 id（格式为 [id] ...）
        text = sel[0].text()
        try:
            if text.startswith('['):
                end = text.find(']')
                mid = text[1:end]
                mapping_id = int(mid)
            else:
                raise ValueError('无法解析选中项 ID')
            # 确认删除
            resp = QMessageBox.question(self, '确认删除', f'确认要删除映射 id={mapping_id} ?', QMessageBox.Yes | QMessageBox.No)
            if resp != QMessageBox.Yes:
                return
            delete_mapping(dbp, mapping_id)
            self.txt_batch_log.append(f"已删除映射 id={mapping_id}")
            self._refresh_registry_list()
        except Exception as e:
            QMessageBox.critical(self, '删除失败', str(e))

    def _on_preview_format(self):
        """显示当前输入格式文件的 JSON 摘要（前几行或 keys）。"""
        fmt = self.inp_registry_format.text().strip()
        if not fmt:
            QMessageBox.warning(self, '预览', '请先填写或选择格式文件路径')
            return
        try:
            p = Path(fmt)
            if not p.exists():
                QMessageBox.warning(self, '预览', f'格式文件不存在: {fmt}')
                return
            with open(p, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            # 构建简短摘要
            if isinstance(data, dict):
                keys = list(data.keys())[:10]
                preview = json.dumps({k: data[k] for k in keys}, indent=2, ensure_ascii=False)
            else:
                preview = json.dumps(data, indent=2, ensure_ascii=False)
            dlg = QDialog(self)
            dlg.setWindowTitle('格式文件预览')
            v = QVBoxLayout(dlg)
            te = QTextEdit()
            te.setReadOnly(True)
            te.setPlainText(preview)
            v.addWidget(te)
            btn = QDialogButtonBox(QDialogButtonBox.Ok)
            btn.accepted.connect(dlg.accept)
            v.addWidget(btn)
            dlg.resize(600, 400)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, '预览失败', str(e))

    def _scan_and_populate_files(self, chosen_path):
        """扫描所选路径并在滚动区域中生成复选框列表（默认全选）。"""
        p = Path(chosen_path)
        files = []
        if p.is_file():
            files = [p]

            self.output_dir = p.parent
        elif p.is_dir():
            pattern = self.inp_pattern.text() if hasattr(self, 'inp_pattern') else "*.csv"
            for file_path in p.rglob('*'):
                if file_path.is_file() and fnmatch.fnmatch(file_path.name, pattern):
                    files.append(file_path)
            self.output_dir = p
        # 清空旧的复选框
        # 清空旧的复选框及标签
        for i in reversed(range(self.file_list_layout_inner.count())):
            item = self.file_list_layout_inner.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w:
                w.setParent(None)
        self._file_check_items = []

        if not files:
            self.grp_file_list.setVisible(False)
            return

        # 创建复选框
        # 创建复选框并显示格式来源标签
        for fp in files:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox(fp.name)
            cb.setChecked(True)
            src_label = QLabel("")
            src_label.setStyleSheet("color: #666; font-size: 11px;")
            # 解析并设置来源（同步快速判断）
            try:
                src, src_path = self._determine_format_source(fp)
                disp, tip, color = self._format_label_from(src, src_path)
                src_label.setText(disp)
                src_label.setToolTip(tip or "")
                src_label.setStyleSheet(f"color: {color}; font-size: 11px;")
            except Exception:
                src_label.setText("未知")
                src_label.setStyleSheet("color: #dc3545; font-size: 11px;")

            row_layout.addWidget(cb)
            # 保持标签靠近复选框，并限制标签宽度，避免在窄窗口下被推到最右侧
            row_layout.addSpacing(8)
            src_label.setFixedWidth(300)
            src_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(src_label)
            self.file_list_layout_inner.addWidget(row)
            # 存储三元组 (checkbox, Path, label) 以便后续使用或更新
            self._file_check_items.append((cb, fp, src_label))

        # 显示并自动滚动到顶部
        self.grp_file_list.setVisible(True)
        self.file_scroll.verticalScrollBar().setValue(0)

    def _determine_format_source(self, fp: Path):
        """快速判断单个文件的格式来源，返回 (label, path_or_None)。

        label: 'registry' | 'sidecar' | 'dir' | 'global' | 'unknown'
        path_or_None: 指向具体的 format 文件（Path）或 None
        """
        try:
            # 1) registry 优先（若界面提供了 db 路径）
            if hasattr(self, 'inp_registry_db'):
                dbp = self.inp_registry_db.text().strip()
                if dbp:
                    try:
                        fmt = get_format_for_file(dbp, str(fp))
                        if fmt:
                            return ("registry", Path(fmt))
                    except Exception:
                        # registry 查询不应阻塞 UI，降级处理
                        pass

            # 2) file-sidecar
            for suf in ('.format.json', '.json'):
                cand = fp.parent / f"{fp.stem}{suf}"
                if cand.exists():
                    return ("sidecar", cand)

            # 3) 目录级默认
            dir_cand = fp.parent / 'format.json'
            if dir_cand.exists():
                return ("dir", dir_cand)

            # 4) 全局
            return ("global", None)
        except Exception:
            return ("unknown", None)

    def _format_label_from(self, src: str, src_path: Optional[Path]):
        """将源类型与路径格式化为显示文本、tooltip 与颜色。

        返回 (display_text, tooltip_text_or_empty, css_color)
        """
        try:
            if src == 'registry':
                name = Path(src_path).name if src_path else ''
                return (f"registry ({name})" if name else "registry", str(src_path) if src_path else "", '#1f77b4')
            if src == 'sidecar':
                name = Path(src_path).name if src_path else ''
                return (f"sidecar ({name})" if name else "sidecar", str(src_path) if src_path else "", '#28a745')
            if src == 'dir':
                name = Path(src_path).name if src_path else ''
                return (f"dir ({name})" if name else "dir", str(src_path) if src_path else "", '#ff8c00')
            if src == 'global':
                return ("global", "", '#6c757d')
            return ("unknown", "", '#dc3545')
        except Exception as e:
            logger.debug("_format_label_from encountered error", exc_info=True)
            return ("unknown", "", '#dc3545')

    def _refresh_format_labels(self):
        """遍历当前文件列表，重新解析并更新每个文件旁的来源标签及 tooltip。"""
        try:
            items = getattr(self, '_file_check_items', None)
            if not items:
                return
            for tup in items:
                # 支持旧的 (cb, fp) 形式或新的 (cb, fp, label)
                if len(tup) == 2:
                    # 旧结构 (cb, fp) 无标签，跳过
                    continue
                cb, fp, lbl = tup
                try:
                    src, src_path = self._determine_format_source(fp)
                    disp, tip, color = self._format_label_from(src, src_path)
                    lbl.setText(disp)
                    lbl.setToolTip(tip or "")
                    lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
                except Exception as e:
                    logger.debug("Failed to set label text from format source", exc_info=True)
                    try:
                        lbl.setText('未知')
                        lbl.setToolTip("")
                        lbl.setStyleSheet("color: #dc3545; font-size: 11px;")
                    except Exception:
                        logger.debug("Failed to set fallback 'unknown' label", exc_info=True)
        except Exception as e:
            logger.debug("_refresh_format_labels failed", exc_info=True)


    def _refresh_registry_list(self):
        """将当前 registry 的映射列表渲染到 `self.lst_registry`。"""
        try:
            dbp = ''
            if hasattr(self, 'inp_registry_db'):
                dbp = self.inp_registry_db.text().strip()
            if not dbp:
                self.grp_registry_list.setVisible(False)
                return
            try:
                mappings = list_mappings(dbp)
            except Exception as e:
                self.lst_registry.clear()
                self.lst_registry.addItem(f"无法读取 registry: {e}")
                self.grp_registry_list.setVisible(True)
                return

            self.lst_registry.clear()
            if not mappings:
                self.lst_registry.addItem("(空)")
            else:
                for m in mappings:
                    text = f"[{m['id']}] {m['pattern']} -> {m['format_path']}  (added: {m['added_at']})"
                    self.lst_registry.addItem(text)

            self.grp_registry_list.setVisible(True)
        except Exception as e:
            logger.debug("_refresh_registry_list encountered error", exc_info=True)
            try:
                self.grp_registry_list.setVisible(False)
            except Exception:
                logger.debug("Failed to hide grp_registry_list after error", exc_info=True)

    def run_batch_processing(self):
        """运行批处理"""
        if not self.calculator:
            QMessageBox.warning(self, "警告", '请先点击"应用配置"按钮!')
            return

        if not self.data_config:
            reply = QMessageBox.question(
                self, "未配置数据格式", 
                '尚未配置数据格式，是否使用默认配置?\n\n'
                '默认: 跳过0行, Fx-Fz=列0-2, Mx-Mz=列3-5',
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.data_config = {
                    'skip_rows': 0,
                    'columns': {'alpha': None, 'fx': 0, 'fy': 1, 'fz': 2, 'mx': 3, 'my': 4, 'mz': 5},
                    'passthrough': []
                }
            else:
                return

        input_path = Path(self.inp_batch_input.text())
        if not input_path.exists():
            QMessageBox.warning(self, "错误", "输入路径不存在")
            return

        # 确定文件列表
        files_to_process = []
        if input_path.is_file():
            files_to_process = [input_path]
            # 优先使用由浏览操作设置的 output_dir（self.output_dir），否则使用文件所在目录
            output_dir = getattr(self, 'output_dir', input_path.parent)

        elif input_path.is_dir():
            # 若界面上存在由 _scan_and_populate_files 填充的复选框列表，则以复选框选择为准
            if getattr(self, '_file_check_items', None):
                files_to_process = []
                for item in self._file_check_items:
                    # 兼容可能只包含 cb 或 (cb, fp) 等不同结构的条目
                    if not item:
                        continue
                    try:
                        cb = item[0]
                        fp = item[1]
                    except (TypeError, IndexError):
                        # 条目结构不符合预期时跳过，避免批处理直接崩溃
                        continue
                    if cb.isChecked():
                        files_to_process.append(fp)
                output_dir = getattr(self, 'output_dir', input_path)
            else:
                pattern = self.inp_pattern.text()
                for file_path in input_path.rglob('*'):
                    if file_path.is_file() and fnmatch.fnmatch(file_path.name, pattern):
                        files_to_process.append(file_path)
                output_dir = input_path

            if not files_to_process:
                QMessageBox.warning(self, "警告", f"未找到匹配 '{self.inp_pattern.text()}' 的文件或未选择任何文件")
                return
        else:
            QMessageBox.warning(self, "错误", "无效的输入路径")
            return

        # 确认处理：先展示找到的文件列表，用户确认后再执行
        file_list_text = "\n".join([str(p) for p in files_to_process])
        confirm_dlg = QMessageBox(self)
        confirm_dlg.setWindowTitle("确认处理")
        confirm_dlg.setText(f"准备处理 {len(files_to_process)} 个文件\n输出目录: {output_dir}\n\n确认开始?")
        # 将完整文件列表放在可展开的详细文本中，便于查看长列表
        confirm_dlg.setDetailedText(file_list_text)
        confirm_dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        reply = confirm_dlg.exec()

        if reply != QMessageBox.Yes:
            self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 已取消：用户未确认文件列表。")
            return

        # 开始处理
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.txt_batch_log.clear()
        self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 开始批量处理...")
        self.txt_batch_log.append(f"共 {len(files_to_process)} 个文件")

        # 读取可选的 registry DB 路径（仅当启用 per-file 覆盖时生效）
        registry_db_path = None
        enable_sidecar = False
        if hasattr(self, 'chk_enable_sidecar') and self.chk_enable_sidecar.isChecked():
            enable_sidecar = True
            if hasattr(self, 'inp_registry_db'):
                val = self.inp_registry_db.text().strip()
                if val:
                    registry_db_path = val

        self.batch_thread = BatchProcessThread(
            self.calculator, files_to_process, output_dir, self.data_config, registry_db=registry_db_path
        )
        # 将 enable_sidecar 状态附到线程上以便日志或后续使用（线程内部使用 registry_db 来决定是否启用覆盖）
        self.batch_thread.enable_sidecar = enable_sidecar

        self.batch_thread.progress.connect(self.progress_bar.setValue)
        self.batch_thread.log_message.connect(
            lambda msg: self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"))
        self.batch_thread.finished.connect(self.on_batch_finished)
        self.batch_thread.error.connect(self.on_batch_error)
        self.batch_thread.start()
        # 锁定配置相关控件，提示用户当前运行使用启动时的配置快照
        try:
            self._set_controls_locked(True)
            self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 注意：当前任务使用启动时配置；在运行期间对配置/格式的修改不会影响本次任务。")
        except Exception:
            logger.debug("Failed to lock controls at batch start", exc_info=True)
        # 显示并启用取消按钮
        try:
            if hasattr(self, 'btn_cancel'):
                self.btn_cancel.setVisible(True)
                self.btn_cancel.setEnabled(True)
        except Exception:
            logger.debug("Failed to show/enable cancel button", exc_info=True)

    def on_batch_finished(self, message):
        """批处理完成"""
        try:
            self._set_controls_locked(False)
        except Exception:
            logger.debug("Failed to unlock controls on batch finished", exc_info=True)
        self.txt_batch_log.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✓ {message}")
        self.statusBar().showMessage("批量处理完成")
        # 隐藏取消按钮并禁用
        try:
            if hasattr(self, 'btn_cancel'):
                self.btn_cancel.setVisible(False)
                self.btn_cancel.setEnabled(False)
        except Exception:
            logger.debug("Failed to hide/disable cancel button", exc_info=True)

        QMessageBox.information(self, "完成", message)

    def on_batch_error(self, error_msg):
        """批处理出错"""
        try:
            self._set_controls_locked(False)
        except Exception:
            logger.debug("Failed to unlock controls on batch error", exc_info=True)
        self.txt_batch_log.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✗ 错误: {error_msg}")
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("批量处理失败")
        # 隐藏并禁用取消按钮
        try:
            if hasattr(self, 'btn_cancel'):
                self.btn_cancel.setVisible(False)
                self.btn_cancel.setEnabled(False)
        except Exception:
            logger.debug("Failed to hide/disable cancel button after error", exc_info=True)

        # 友好的错误提示，包含可行建议
        try:
            dlg = QMessageBox(self)
            dlg.setIcon(QMessageBox.Critical)
            dlg.setWindowTitle("处理失败")
            dlg.setText("批处理过程中发生错误，已记录到日志。请检查输入文件与数据格式配置。")
            dlg.setInformativeText("建议：检查数据格式映射（列索引）、Target 配置中的 MomentCenter/Q/S，或在 GUI 中打开“配置数据格式”进行修正。")
            dlg.setDetailedText(str(error_msg))

        except Exception:
            logger.debug("Failed to show error dialog", exc_info=True)

    BUTTON_LAYOUT_THRESHOLD = 720
    def update_button_layout(self, threshold=None):
        """根据窗口宽度在网格中切换按钮位置。

        参数 `threshold` 的单位为像素（px）。当窗口宽度大于或等于阈值时，
        按钮按一行两列排列；当宽度小于阈值时，按钮按两行单列排列（便于窄屏显示）。

        默认阈值 720px 由类常量 ``BUTTON_LAYOUT_THRESHOLD`` 提供，可根据实际布局和用户屏幕密度微调该值。
        可根据实际布局和用户屏幕密度微调该值。
        """
        if threshold is None:
            threshold = self.BUTTON_LAYOUT_THRESHOLD
        
        if not hasattr(self, 'btn_widget'):
            return
        try:
            w = self.width()
        except Exception:
            w = threshold

        # 取出已有按钮实例
        btns = [getattr(self, 'btn_config_format', None), getattr(self, 'btn_batch', None), getattr(self, 'btn_cancel', None)]

        # 安全地移除旧布局但保留按钮 widget 本身，避免双重删除或内存泄漏。
        # 我们会从旧布局中取出 widget 引用并在最后调用 deleteLater() 删除旧布局对象。
        # 我们不再替换已有的 layout 对象（self.btn_grid），而是复用并清空它的内容
        extracted_widgets = []
        grid = getattr(self, 'btn_grid', None)
        if grid is None:
            grid = QGridLayout()
            grid.setSpacing(8)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            self.btn_grid = grid
        else:
            # 从现有 grid 中提取 widget（不删除 layout 本身）
            while grid.count():
                item = grid.takeAt(0)
                wdg = item.widget()
                if wdg:
                    try:
                        grid.removeWidget(wdg)
                    except Exception:
                        logger.debug("grid.removeWidget failed", exc_info=True)
                    extracted_widgets.append(wdg)
            # 重新确保列伸缩
            try:
                grid.setColumnStretch(0, 1)
                grid.setColumnStretch(1, 1)
            except Exception:
                logger.debug("grid.setColumnStretch failed", exc_info=True)

        if w >= threshold:
            # 宽窗口：一行两列
            # 如果我们刚才从旧布局提取了 widgets，优先使用它们以保持实例不变
            if extracted_widgets:
                if len(extracted_widgets) >= 1 and extracted_widgets[0]:
                    grid.addWidget(extracted_widgets[0], 0, 0)
                if len(extracted_widgets) >= 2 and extracted_widgets[1]:
                    grid.addWidget(extracted_widgets[1], 0, 1)
            else:
                if btns[0]:
                    grid.addWidget(btns[0], 0, 0)
                if btns[1]:
                    grid.addWidget(btns[1], 0, 1)
            self._btn_orientation = 'horizontal'
        else:
            # 窄窗口：两行布局（第一列靠左）
            if extracted_widgets:
                if len(extracted_widgets) >= 1 and extracted_widgets[0]:
                    grid.addWidget(extracted_widgets[0], 0, 0)
                if len(extracted_widgets) >= 2 and extracted_widgets[1]:
                    grid.addWidget(extracted_widgets[1], 1, 0)
            else:
                if btns[0]:
                    grid.addWidget(btns[0], 0, 0)
                if btns[1]:
                    grid.addWidget(btns[1], 1, 0)
            self._btn_orientation = 'vertical'

        # 将清理后的 grid 重新应用到 btn_widget（若尚未设置）
        if self.btn_widget.layout() is not grid:
            try:
                self.btn_widget.setLayout(grid)
            except Exception:
                logger.debug("btn_widget.setLayout failed", exc_info=True)
        # 确保按钮容器在布局更改后更新尺寸与几何，以免在窗口状态切换时被临时挤出视口
        try:
            self.btn_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            # 尝试通过标准方式强制刷新布局：使布局失效并激活布局，更新几何信息
            cw = self.centralWidget()
            if cw:
                layout = cw.layout()
                if layout:
                    layout.invalidate()
                    layout.activate()
                cw.updateGeometry()
                for child in cw.findChildren(QWidget):
                    child.updateGeometry()
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            except Exception:
                logger.debug("QApplication.processEvents failed in update_button_layout", exc_info=True)
        except Exception:
            logger.debug("update_button_layout failed during size policy/layout refresh", exc_info=True)

    def resizeEvent(self, event):
        try:
            self.update_button_layout()
        except Exception:
            logger.debug("resizeEvent update_button_layout failed", exc_info=True)
        return super().resizeEvent(event)

    def showEvent(self, event):
        """在窗口首次显示后延迟触发一次布局更新以确保初始可见性。"""
        try:
            QTimer.singleShot(50, self.update_button_layout)
            QTimer.singleShot(120, self._force_layout_refresh)
        except Exception:
            logger.debug("showEvent scheduling failed", exc_info=True)
        return super().showEvent(event)

    def _force_layout_refresh(self):
        """
        尝试强制刷新布局：激活布局并做一个极小的像素级尺寸微调以触发布局重算。

        说明：
        由于 Qt（包括 PySide6/PyQt5）在某些复杂嵌套布局下，调用 layout().activate() 或 processEvents() 可能无法立即刷新所有控件的实际显示，
        尤其是涉及 QSplitter/QScrollArea/QTabWidget 等嵌套时。此处采用“窗口宽度+2像素再还原”的 hack，
        能强制 Qt 的底层布局引擎重新计算和应用所有控件的尺寸与位置。
        该方法在 Windows/Linux/Mac 下 Qt 5/6 均有效，但未来 Qt 版本可能修复此类刷新 bug 时可移除。
        若主窗口被设置为不可调整大小，则此 hack 可能无效。
        """
        try:
            cw = self.centralWidget()
            if cw and cw.layout():
                cw.layout().activate()
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            except Exception:
                logger.debug("QApplication.processEvents failed in _force_layout_refresh", exc_info=True)

            # --- Qt 布局刷新 hack ---
            # 微调窗口宽度 (+2 然后恢复) 以触发底层布局引擎重新布局。
            w = self.width()
            h = self.height()
            # 如果主窗口是可调整大小的，做一次非常小的尺寸变动并回滚
            self.resize(w + 2, h)
            QTimer.singleShot(20, lambda: self.resize(w, h))
        except Exception:
            logger.debug("_force_layout_refresh failed", exc_info=True)

    def _refresh_layouts(self):
        """激活并刷新主要布局与 splitter，以保证子控件正确伸缩。"""
        try:
            cw = self.centralWidget()
            if cw and cw.layout():
                cw.layout().activate()
            # 激活左右 splitter 的布局
            try:
                # 触发按钮布局更新和一次强制刷新
                self.update_button_layout()
            except Exception:
                logger.debug("update_button_layout failed in _refresh_layouts", exc_info=True)
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            except Exception:
                logger.debug("QApplication.processEvents failed in _refresh_layouts", exc_info=True)
            # 轻微调整 splitter 大小以促使 Qt 重新布局（仅在必要时）
            try:
                s = self.findChild(QSplitter)
                if s:
                    sizes = s.sizes()
                    s.setSizes(sizes)
            except Exception:
                logger.debug("Splitter resize refresh failed in _refresh_layouts", exc_info=True)
        except Exception:
            logger.debug("_refresh_layouts failed", exc_info=True)

    # ----- 新增辅助方法：配置预览 / 最近项目 / 快速处理 -----
    def update_config_preview(self):
        """根据当前的 `self.data_config` 显示数据格式预览（跳过行、列映射、保留列）。"""
        try:
            cfg = getattr(self, 'data_config', None)
            if cfg is None:
                self.lbl_preview_skip.setText('跳过行: -')
                self.lbl_preview_columns.setText('列映射: -')
                self.lbl_preview_passthrough.setText('保留列: -')
                return

            # 支持 dict 或具有属性的对象
            if isinstance(cfg, dict):
                skip = cfg.get('skip_rows')
                cols = cfg.get('columns', {}) or {}
                passth = cfg.get('passthrough', []) or []
            else:
                skip = getattr(cfg, 'skip_rows', None)
                cols = getattr(cfg, 'columns', {}) or {}
                # 兼容不同命名
                passth = getattr(cfg, 'passthrough', None) or getattr(cfg, 'passthrough_columns', []) or []

            # 跳过行
            self.lbl_preview_skip.setText(f"跳过行: {skip if skip is not None else '-'}")

            # 列映射摘要
            def _col_val(k):
                v = cols.get(k)
                return str(v) if v is not None else '缺失'

            col_keys = ['alpha', 'fx', 'fy', 'fz', 'mx', 'my', 'mz']
            col_parts = [f"{k.upper()}={_col_val(k)}" for k in col_keys]
            cols_text = ", ".join(col_parts)
            # 若关键力列缺失，标红提示
            if cols.get('fx') is None or cols.get('fy') is None or cols.get('fz') is None:
                self.lbl_preview_columns.setStyleSheet('color: red; font-size:12px;')
            else:
                self.lbl_preview_columns.setStyleSheet('color: black; font-size:12px;')
            self.lbl_preview_columns.setText(f"列映射: {cols_text}")

            # 保留列
            try:
                pt_display = ','.join(str(int(x)) for x in (passth or [])) if passth else '-'
            except Exception:
                pt_display = str(passth)
            self.lbl_preview_passthrough.setText(f"保留列: {pt_display}")

        except Exception:
            logger.debug("update_config_preview failed", exc_info=True)

    def add_recent_project(self, path_str: str):
        """将最近打开的配置/项目加入列表（去重，保持最新在上）。"""
        try:
            if not hasattr(self, 'recent_projects'):
                self.recent_projects = []
            p = str(path_str)
            if p in self.recent_projects:
                self.recent_projects.remove(p)
            self.recent_projects.insert(0, p)
            # 限制数量
            self.recent_projects = self.recent_projects[:10]
            # 更新 UI 列表
            try:
                self.lst_recent.clear()
                for rp in self.recent_projects:
                    self.lst_recent.addItem(rp)
            except Exception:
                logger.debug("Failed to update lst_recent", exc_info=True)
        except Exception:
            logger.debug("add_recent_project failed", exc_info=True)

    def _browse_default_output(self):
        try:
            d = QFileDialog.getExistingDirectory(self, '选择默认输出目录', '.')
            if d:
                self.inp_default_output.setText(d)
        except Exception:
            logger.debug("_browse_default_output failed", exc_info=True)

    def _toggle_experimental_visibility(self):
        """显示或隐藏实验性组，并刷新布局。"""
        try:
            visible = bool(self.chk_show_experimental.isChecked())
            if hasattr(self, 'grp_experimental'):
                self.grp_experimental.setVisible(visible)
            try:
                self._refresh_layouts()
            except Exception:
                logger.debug("_refresh_layouts failed after toggling experimental", exc_info=True)
        except Exception:
            logger.debug("_toggle_experimental_visibility failed", exc_info=True)

    def _on_target_part_changed(self):
        """当用户在下拉框选择不同 Part 时，更新 Variant 的上限并刷新 Target 表单。"""
        try:
            if not hasattr(self, 'current_config') or self.current_config is None:
                return
            if not isinstance(self.current_config, ProjectData):
                return
            sel = self.cmb_target_parts.currentText()
            variants = self.current_config.target_parts.get(sel, [])
            max_idx = max(0, len(variants) - 1)
            self.spin_target_variant.setRange(0, max_idx)
            # 尝试用第一个 variant 填充 Target 表单
            if variants:
                frame = variants[0]
                cs = frame.coord_system
                mc = frame.moment_center or [0.0, 0.0, 0.0]
                self.tgt_part_name.setText(frame.part_name)
                self.tgt_ox.setText(str(cs.origin[0]))
                self.tgt_oy.setText(str(cs.origin[1]))
                self.tgt_oz.setText(str(cs.origin[2]))
                self.tgt_xx.setText(str(cs.x_axis[0]))
                self.tgt_xy.setText(str(cs.x_axis[1]))
                self.tgt_xz.setText(str(cs.x_axis[2]))
                self.tgt_yx.setText(str(cs.y_axis[0]))
                self.tgt_yy.setText(str(cs.y_axis[1]))
                self.tgt_yz.setText(str(cs.y_axis[2]))
                self.tgt_zx.setText(str(cs.z_axis[0]))
                self.tgt_zy.setText(str(cs.z_axis[1]))
                self.tgt_zz.setText(str(cs.z_axis[2]))
                self.tgt_mcx.setText(str(mc[0]))
                self.tgt_mcy.setText(str(mc[1]))
                self.tgt_mcz.setText(str(mc[2]))
                self.tgt_cref.setText(str(frame.c_ref or 1.0))
                self.tgt_bref.setText(str(frame.b_ref or 1.0))
                self.tgt_sref.setText(str(frame.s_ref or 10.0))
                self.tgt_q.setText(str(frame.q or 1000.0))
            # 更新预览
            try:
                self.update_config_preview()
            except Exception:
                logger.debug("update_config_preview failed in _on_target_part_changed", exc_info=True)
        except Exception:
            logger.debug("_on_target_part_changed failed", exc_info=True)

    def one_click_process(self):
        """使用当前配置和默认输出目录快速启动批处理（单次、非交互）。"""
        try:
            # 初始化基本前置条件
            if not hasattr(self, 'calculator') or self.calculator is None:
                QMessageBox.warning(self, "错误", "尚未应用配置，请先点击“应用配置”。")
                return
            inp = self.inp_batch_input.text().strip()
            if not inp:
                # 若最近项目可用，则使用第一个
                if hasattr(self, 'recent_projects') and self.recent_projects:
                    inp = self.recent_projects[0]
                    self.inp_batch_input.setText(inp)
                else:
                    QMessageBox.warning(self, "错误", "请先选择输入文件或目录（或在最近项目中选择一项）。")
                    return

            output_dir = self.inp_default_output.text().strip() or None
            if output_dir:
                self.output_dir = Path(output_dir)
            else:
                self.output_dir = None

            # 将输入路径设置到控件并调用 run_batch_processing
            self.inp_batch_input.setText(inp)
            # 如果指定了默认输出目录，设置为实例属性，run_batch_processing 会优先使用它
            try:
                self.run_batch_processing()
            except Exception as e:
                logger.exception("one_click_process failed: %s", e)
        except Exception:
            logger.debug("one_click_process failed", exc_info=True)

    def request_cancel_batch(self):
        """UI 回调：请求取消正在运行的批处理任务"""
        try:
            if hasattr(self, 'batch_thread') and self.batch_thread is not None:
                self.txt_batch_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 用户请求取消任务，正在停止...")
                try:
                    self.batch_thread.request_stop()
                except Exception:
                    logger.debug("batch_thread.request_stop 调用失败（可能已结束）", exc_info=True)
                # 禁用取消按钮以避免重复点击
                try:
                    if hasattr(self, 'btn_cancel'):
                        self.btn_cancel.setEnabled(False)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("request_cancel_batch 失败", exc_info=True)

    def _set_controls_locked(self, locked: bool):
        """锁定或解锁与配置相关的控件，防止用户在批处理运行期间修改配置。

        locked=True 时禁用；locked=False 时恢复。此方法尽量保持幂等并静默忽略缺失控件。
        """
        widgets = [
            getattr(self, 'btn_load', None),
            getattr(self, 'btn_save', None),
            getattr(self, 'btn_apply', None),
            getattr(self, 'btn_config_format', None),
            getattr(self, 'btn_registry_register', None),
            getattr(self, 'btn_registry_edit', None),
            getattr(self, 'btn_registry_remove', None),
            getattr(self, 'btn_batch', None),
            getattr(self, 'inp_registry_db', None),
            getattr(self, 'inp_registry_pattern', None),
            getattr(self, 'inp_registry_format', None),
        ]
        for w in widgets:
            try:
                if w is not None:
                    w.setEnabled(not locked)
            except Exception:
                pass

        # 取消按钮在锁定时仍应保持可见/可用以提供取消能力
        try:
            if hasattr(self, 'btn_cancel'):
                # 当 locked=True 时显示取消按钮并保持启用；当 locked=False 时隐藏
                if locked:
                    self.btn_cancel.setVisible(True)
                    self.btn_cancel.setEnabled(True)
                else:
                    self.btn_cancel.setVisible(False)
                    self.btn_cancel.setEnabled(False)
        except Exception:
            logger.debug("Failed to set btn_cancel visibility/state in _set_controls_locked", exc_info=True)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = IntegratedAeroGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()