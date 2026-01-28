"""
坐标系配置面板 - Source和Target共用的基础面板
"""

# 部分 Qt 导入在运行时按需延迟，允许 import-outside-toplevel 降低 lint 噪音
# pylint: disable=import-outside-toplevel

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from src.models import CSModel as CSModelAlias
from src.models import ReferenceValues as RefModel

logger = logging.getLogger(__name__)


class CoordinateSystemPanel(QGroupBox):
    """通用坐标系配置面板 - Source和Target共用"""

    # 信号定义
    valuesChanged = Signal()  # 值发生变化
    partNameChanged = Signal(str)  # Part名称变化
    partSelected = Signal(str)  # 选择了Part

    def __init__(self, title: str, prefix: str, parent=None):
        """
        Args:
            title: GroupBox标题（如 "Source Configuration"）
            prefix: 控件前缀（如 "src" 或 "tgt"）
            parent: 父窗口
        """
        super().__init__(title, parent)
        self.prefix = prefix
        # 在程序化更新面板值时抑制 valuesChanged 发射
        # 使用计数以支持嵌套的静默更新调用
        self._silent_update_count = 0
        self._current_part_name = "TestModel"

        # 获取 SignalBus 并连接监听
        try:
            from gui.signal_bus import SignalBus

            self.signal_bus = SignalBus.instance()
            self.signal_bus.partAdded.connect(self._on_part_added)
            self.signal_bus.partRemoved.connect(self._on_part_removed)
        except Exception:
            logger.debug("SignalBus 初始化失败，Part 更新将不可用", exc_info=True)
            self.signal_bus = None

        # 初始化UI
        self._init_ui()

    def _emit_values_changed(self, *args):
        """统一处理带参数的信号，转为无参 valuesChanged。"""
        try:
            if getattr(self, "_silent_update_count", 0) > 0:
                return
            self.valuesChanged.emit()
        except Exception:
            logger.debug("valuesChanged 发射失败", exc_info=True)

    def begin_silent_update(self):
        """在批量程序化更新前调用以抑制 valuesChanged 信号（可嵌套）。"""
        try:
            self._silent_update_count = getattr(self, "_silent_update_count", 0) + 1
        except Exception:
            self._silent_update_count = 1

    def end_silent_update(self):
        """结束一次静默更新调用；仅当计数归零时恢复 valuesChanged。"""
        try:
            cnt = getattr(self, "_silent_update_count", 0) - 1
            self._silent_update_count = cnt if cnt > 0 else 0
        except Exception:
            self._silent_update_count = 0

    @staticmethod
    def _get_float(widget, default: float = 0.0) -> float:
        """从输入框获取浮点数，失败时返回默认值。"""
        try:
            return float(widget.text())
        except Exception:
            return default

    def _init_ui(self):
        """初始化UI布局"""
        # 设置尺寸约束
        # 侧边栏默认宽度有限，面板内容不要被强行压缩到不可读；
        # 交给外层 QScrollArea 负责横向滚动展示。
        self.setMinimumWidth(320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # 创建表单布局
        self.form_layout = QFormLayout()
        # 略微收紧外边距与间距，使面板更紧凑
        self.form_layout.setContentsMargins(8, 8, 8, 8)
        self.form_layout.setSpacing(4)
        self.form_layout.setHorizontalSpacing(6)
        self.form_layout.setVerticalSpacing(4)
        try:
            self.form_layout.setLabelAlignment(Qt.AlignRight)
        except Exception:
            pass

        # Part Name输入
        self.part_name_input = self._create_input("TestModel")
        self.part_name_input.textChanged.connect(self._on_part_name_changed)
        lbl_part = QLabel("Part Name:")
        lbl_part.setFixedWidth(90)
        self.form_layout.addRow(lbl_part, self.part_name_input)

        # Part选择器（用于加载配置后选择不同的Part）
        self.part_selector = QComboBox(self)
        # 限制下拉框宽度并使用紧凑尺寸策略，确保与 + - 按钮同行
        try:
            self.part_selector.setMaximumWidth(160)
            self.part_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass
        self.part_selector.currentTextChanged.connect(self._on_part_selected)

        # Part管理按钮
        part_widget = QWidget()
        part_layout = QHBoxLayout(part_widget)
        part_layout.setContentsMargins(0, 0, 0, 0)
        part_layout.setSpacing(6)
        part_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        part_layout.addWidget(self.part_selector)

        self.btn_add_part = QPushButton("+")
        self.btn_add_part.setMaximumWidth(28)
        self.btn_remove_part = QPushButton("−")
        self.btn_remove_part.setMaximumWidth(28)
        try:
            self.btn_add_part.setObjectName("smallButton")
            self.btn_remove_part.setObjectName("smallButton")
        except Exception:
            pass

        part_layout.addWidget(self.btn_add_part)
        part_layout.addWidget(self.btn_remove_part)
        # 保证容器在表单里不会垂直拉伸
        try:
            part_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass

        lbl_select = QLabel(f"选择 {self.prefix.upper()} Part:")
        lbl_select.setFixedWidth(90)
        self.form_layout.addRow(lbl_select, part_widget)

        # 坐标系表格 — 放到一个容器中作为整行项，避免被左侧标签列缩进
        self.coord_table = self._create_coord_table()
        table_container = QWidget()
        table_layout = QHBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        table_layout.addWidget(self.coord_table)
        table_layout.setAlignment(self.coord_table, Qt.AlignLeft | Qt.AlignTop)
        # 作为单列行添加，避免使用空字符串标签造成缩进
        self.form_layout.addRow(table_container)

        # 参考量输入
        self.cref_input = self._create_input("1.0")
        self.bref_input = self._create_input("1.0")
        self.sref_input = self._create_input("10.0")
        self.q_input = self._create_input("1000.0")

        lbl_cref = QLabel("C_ref (m):")
        lbl_cref.setFixedWidth(90)
        self.form_layout.addRow(lbl_cref, self.cref_input)

        lbl_bref = QLabel("B_ref (m):")
        lbl_bref.setFixedWidth(90)
        self.form_layout.addRow(lbl_bref, self.bref_input)

        lbl_sref = QLabel("S_ref (m²):")
        lbl_sref.setFixedWidth(90)
        self.form_layout.addRow(lbl_sref, self.sref_input)

        lbl_q = QLabel("Q (Pa):")
        lbl_q.setFixedWidth(90)
        self.form_layout.addRow(lbl_q, self.q_input)

        # 连接值变化信号
        for widget in [
            self.cref_input,
            self.bref_input,
            self.sref_input,
            self.q_input,
        ]:
            widget.textChanged.connect(self._emit_values_changed)

        self.setLayout(self.form_layout)
        # 将按钮连接到 SignalBus 请求信号
        try:
            if self.signal_bus:
                side = "Source" if self.prefix.lower() == "src" else "Target"
                self.btn_add_part.clicked.connect(
                    lambda: self.signal_bus.partAddRequested.emit(
                        side, self.get_part_name()
                    )
                )
                self.btn_remove_part.clicked.connect(
                    lambda: self.signal_bus.partRemoveRequested.emit(
                        side, self.get_part_name()
                    )
                )
                logger.debug("%s 面板按钮已连接到 SignalBus", side)
        except Exception as e:
            logger.warning("连接面板按钮到请求信号失败: %s", e, exc_info=True)

    def _create_input(self, default_text: str) -> QLineEdit:
        """创建紧凑型输入框"""
        inp = QLineEdit(default_text)
        try:
            inp.setProperty("compact", "true")
            inp.setMaximumWidth(120)
        except Exception:
            pass
        return inp

    def _create_coord_table(self) -> QTableWidget:
        """创建坐标系输入表格（5行×3列）"""
        table = QTableWidget(5, 3)
        table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        table.setVerticalHeaderLabels(["Orig", "X轴", "Y轴", "Z轴", "力矩中心"])

        # 设置默认值
        default_values = [
            [0.0, 0.0, 0.0],  # Orig
            [1.0, 0.0, 0.0],  # X轴
            [0.0, 1.0, 0.0],  # Y轴
            [0.0, 0.0, 1.0],  # Z轴
            [0.0, 0.0, 0.0],  # 力矩中心
        ]

        for row in range(5):
            for col in range(3):
                item = QTableWidgetItem(str(default_values[row][col]))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
            table.setRowHeight(row, 26)

        # 设置表格尺寸
        table.setMinimumHeight(170)
        table.setMaximumHeight(190)
        table.setMinimumWidth(250)
        # 不限制最大宽度，避免在更宽布局下仍被“挤成一条”
        table.setMaximumWidth(16777215)

        # 列宽自适应
        h_header = table.horizontalHeader()
        h_header.setSectionResizeMode(QHeaderView.Stretch)

        # 行标题列更窄
        v_header = table.verticalHeader()
        v_header.setMinimumWidth(60)
        v_header.setMaximumWidth(65)

        # 样式优化
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 连接值变化信号
        table.itemChanged.connect(self._emit_values_changed)

        try:
            table.setObjectName(f"{self.prefix}_coord_table")
        except Exception:
            pass

        return table

    def _on_part_name_changed(self, new_name: str):
        """Part名称改变时触发"""
        if new_name != self._current_part_name:
            self._current_part_name = new_name
            self.partNameChanged.emit(new_name)

    def _on_part_selected(self, part_name: str):
        """选择了不同的Part时触发"""
        if part_name:
            self.partSelected.emit(part_name)

    def get_coord_data(self) -> dict:
        """获取坐标系数据"""
        data = {"Orig": [], "X": [], "Y": [], "Z": [], "MomentCenter": []}

        row_keys = ["Orig", "X", "Y", "Z", "MomentCenter"]
        for row, key in enumerate(row_keys):
            for col in range(3):
                item = self.coord_table.item(row, col)
                value = float(item.text()) if item and item.text() else 0.0
                data[key].append(value)

        return data

    def _get_coord_from_table(self) -> dict:
        """从表格读取坐标数据的私有辅助方法。"""
        return self.get_coord_data()

    def set_coord_data(self, data: dict):
        """设置坐标系数据"""
        row_keys = ["Orig", "X", "Y", "Z", "MomentCenter"]
        # 使用静默更新以避免程序化设置时触发 valuesChanged
        try:
            self.begin_silent_update()
            for row, key in enumerate(row_keys):
                if key in data:
                    values = data[key]
                    for col in range(min(3, len(values))):
                        self.coord_table.setItem(
                            row, col, QTableWidgetItem(str(values[col]))
                        )
        finally:
            try:
                self.end_silent_update()
            except Exception:
                pass

    def get_reference_values(self) -> dict:
        """获取参考量"""
        return {
            "C_ref": float(self.cref_input.text()),
            "B_ref": float(self.bref_input.text()),
            "S_ref": float(self.sref_input.text()),
            "Q": float(self.q_input.text()),
        }

    def get_reference_values_model(self) -> RefModel:
        """以强类型模型返回参考量。"""
        try:
            return RefModel(
                cref=float(self.cref_input.text() or 1.0),
                bref=float(self.bref_input.text() or 1.0),
                sref=float(self.sref_input.text() or 10.0),
                q=float(self.q_input.text() or 1000.0),
            )
        except Exception:
            return RefModel()

    def get_coordinate_system(self):
        """以强类型模型返回坐标系（别名）。"""
        return self.get_coordinate_system_model()

    def set_reference_values(self, cref: float, bref: float, sref: float, q: float):
        """设置参考量"""
        # 使用静默更新以避免程序化设置时触发 valuesChanged
        try:
            self.begin_silent_update()
            self.cref_input.setText(str(cref))
            self.bref_input.setText(str(bref))
            self.sref_input.setText(str(sref))
            self.q_input.setText(str(q))
        finally:
            try:
                self.end_silent_update()
            except Exception:
                pass

    def apply_variant_payload(self, payload: dict):
        """将 Variant 字典数据填充到面板。"""
        if not payload:
            logger.debug("%s apply_variant_payload: payload 为空", self.prefix)
            return

        part_name = payload.get("PartName") or "Part"
        logger.debug("%s apply_variant_payload: PartName=%s", self.prefix, part_name)
        try:
            self.part_name_input.blockSignals(True)
            self.part_name_input.setText(str(part_name))
        finally:
            try:
                self.part_name_input.blockSignals(False)
            except Exception:
                pass

        cs = payload.get("CoordSystem", {}) or {}
        mc = payload.get("MomentCenter")
        if mc is None:
            mc = cs.get("MomentCenter")
        coord_data = {
            "Orig": cs.get("Orig", [0.0, 0.0, 0.0]),
            "X": cs.get("X", [1.0, 0.0, 0.0]),
            "Y": cs.get("Y", [0.0, 1.0, 0.0]),
            "Z": cs.get("Z", [0.0, 0.0, 1.0]),
            "MomentCenter": mc if mc is not None else [0.0, 0.0, 0.0],
        }
        logger.debug("%s apply_variant_payload: coord_data=%s", self.prefix, coord_data)
        # 参考量
        cref = payload.get("Cref", payload.get("C_ref", 1.0))
        bref = payload.get("Bref", payload.get("B_ref", 1.0))
        sref = payload.get("Sref", payload.get("S_ref", 10.0))
        q_val = payload.get("Q", 1000.0)
        logger.debug(
            f"{self.prefix} apply_variant_payload: cref={cref}, bref={bref}, sref={sref}, q={q_val}"
        )

        # 在批量填充时使用静默更新，避免触发 valuesChanged
        try:
            self.begin_silent_update()
            self.set_coord_data(coord_data)
            self.set_reference_values(cref, bref, sref, q_val)
        finally:
            try:
                self.end_silent_update()
            except Exception:
                pass

    def to_variant_payload(self, override_part_name: str = None) -> dict:
        """从面板生成 Variant 字典数据。"""
        coord = self.get_coord_data()
        part_name = override_part_name or self.part_name_input.text().strip() or "Part"
        return {
            "PartName": part_name,
            "CoordSystem": {
                "Orig": coord.get("Orig", [0.0, 0.0, 0.0]),
                "X": coord.get("X", [1.0, 0.0, 0.0]),
                "Y": coord.get("Y", [0.0, 1.0, 0.0]),
                "Z": coord.get("Z", [0.0, 0.0, 1.0]),
            },
            "MomentCenter": coord.get("MomentCenter", [0.0, 0.0, 0.0]),
            "Cref": self._get_float(self.cref_input, 1.0),
            "Bref": self._get_float(self.bref_input, 1.0),
            "Sref": self._get_float(self.sref_input, 10.0),
            "Q": self._get_float(self.q_input, 1000.0),
        }

    def get_coordinate_system_model(self) -> CSModelAlias:
        """以强类型模型返回坐标系。"""
        try:
            coord = self.get_coord_data()
            return CSModelAlias.from_dict(
                {
                    "Orig": coord.get("Orig", [0.0, 0.0, 0.0]),
                    "X": coord.get("X", [1.0, 0.0, 0.0]),
                    "Y": coord.get("Y", [0.0, 1.0, 0.0]),
                    "Z": coord.get("Z", [0.0, 0.0, 1.0]),
                    "MomentCenter": coord.get("MomentCenter", [0.0, 0.0, 0.0]),
                }
            )
        except Exception:
            return CSModelAlias()

    def get_part_name(self) -> str:
        """获取当前Part名称"""
        return self.part_name_input.text()

    def set_part_name(self, name: str):
        """设置Part名称"""
        self.part_name_input.blockSignals(True)
        self.part_name_input.setText(name)
        self._current_part_name = name
        self.part_name_input.blockSignals(False)

    def update_part_list(self, part_names: list):
        """更新Part选择器列表"""
        self.part_selector.blockSignals(True)
        self.part_selector.clear()
        self.part_selector.addItems(part_names)
        self.part_selector.blockSignals(False)

    def _on_part_added(self, side: str, part_name: str):
        """SignalBus 事件：Part 被添加时更新选择器列表"""
        # 只更新对应侧的面板
        side_norm = (side or "").strip().lower()
        prefix_norm = (self.prefix or "").strip().lower()
        if side_norm in ("source", "src"):
            side_norm = "src"
        elif side_norm in ("target", "tgt"):
            side_norm = "tgt"
        if side_norm != prefix_norm:
            return
        try:
            current_items = [
                self.part_selector.itemText(i)
                for i in range(self.part_selector.count())
            ]
            if part_name not in current_items:
                self.part_selector.blockSignals(True)
                self.part_selector.addItem(part_name)
                self.part_selector.blockSignals(False)
                logger.debug("%s Part选择器已添加项目: %s", self.prefix, part_name)
        except Exception as e:
            logger.warning("Part添加事件处理失败: %s", e, exc_info=True)

    def _on_part_removed(self, side: str, part_name: str):
        """SignalBus 事件：Part 被移除时更新选择器列表"""
        # 只更新对应侧的面板
        side_norm = (side or "").strip().lower()
        prefix_norm = (self.prefix or "").strip().lower()
        if side_norm in ("source", "src"):
            side_norm = "src"
        elif side_norm in ("target", "tgt"):
            side_norm = "tgt"
        if side_norm != prefix_norm:
            return
        try:
            idx = self.part_selector.findText(part_name)
            if idx >= 0:
                self.part_selector.blockSignals(True)
                self.part_selector.removeItem(idx)
                self.part_selector.blockSignals(False)
                logger.debug("%s Part选择器已移除项目: %s", self.prefix, part_name)
        except Exception as e:
            logger.warning("Part移除事件处理失败: %s", e, exc_info=True)
