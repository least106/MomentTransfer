"""
批处理面板 - 包含文件树、Tab页、进度条、操作按钮
"""

import logging
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QProgressBar,
    QTabWidget,
    QTreeWidget,
    QTextEdit,
    QLabel,
    QHeaderView,
    QSizePolicy,
    QLineEdit,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QCompleter,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont, QDoubleValidator

logger = logging.getLogger(__name__)


class BatchPanel(QWidget):
    """批处理面板 - 封装文件树、Tab页、进度条和操作按钮"""

    # 信号定义
    batchStartRequested = Signal()  # 请求开始批处理
    formatConfigRequested = Signal()  # 请求配置数据格式
    undoRequested = Signal()  # 请求撤销
    browseRequested = Signal()  # 请求浏览输入路径
    patternChanged = Signal(str)  # 匹配模式变化
    selectAllRequested = Signal()  # 全选文件
    selectNoneRequested = Signal()  # 全不选
    invertSelectionRequested = Signal()  # 反选
    quickFilterChanged = Signal(
        str, str, str
    )  # 快速筛选变化(列名, 运算符, 筛选值)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 左侧：输入行 + 文件列表 + Tab
        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)

        # 输入与模式表单
        self.file_form = QFormLayout()
        self.file_form.setSpacing(4)
        self.file_form.setContentsMargins(2, 2, 2, 2)
        self._init_input_rows()
        left_layout.addLayout(self.file_form)

        # 文件列表区域
        self.file_list_widget = self._create_file_list()

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)

        # Tab容器
        self.tab_main = self._create_tab_widget()
        left_layout.addWidget(self.tab_main)

        # 右侧：操作按钮
        right_layout = self._create_button_panel()

        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 0)

        # 兼容字段：存储文件节点
        self._file_tree_items = {}

        # 初始化阶段：按流程先隐藏非必要控件
        try:
            self.set_workflow_step("init")
        except Exception:
            logger.debug("set_workflow_step init failed", exc_info=True)

    def _init_input_rows(self):
        """初始化输入路径与模式控件（兼容旧接口）。"""
        # 输入路径
        # 调整表单标签对齐为右侧垂直居中，确保标签与输入控件垂直对齐
        try:
            self.file_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        except Exception:
            pass
        self.inp_batch_input = QLineEdit()
        self.inp_batch_input.setPlaceholderText("选择文件或目录...")
        self.btn_browse_input = QPushButton("浏览")
        try:
            self.btn_browse_input.setObjectName("smallButton")
            self.btn_browse_input.setToolTip("选择输入文件或目录")
        except Exception:
            pass
        self.btn_browse_input.clicked.connect(self.browseRequested.emit)
        # 保持输入框与按钮高度一致以使其与表单标签对齐
        try:
            h = max(self.inp_batch_input.sizeHint().height(), 26)
            self.inp_batch_input.setFixedHeight(h)
            self.btn_browse_input.setFixedHeight(h)
        except Exception:
            pass

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(self.inp_batch_input)
        input_row.addWidget(self.btn_browse_input)
        self.row_input_widget = QWidget()
        self.row_input_widget.setLayout(input_row)
        self.file_form.addRow("输入路径:", self.row_input_widget)

        # 全局数据格式配置已移除：表格列映射由 per-file sidecar/目录 format.json/registry 自动解析。
        self.lbl_format_summary = None
        self.row_format_summary_widget = None

        # 匹配模式
        self.inp_pattern = QLineEdit("*.csv")
        self.inp_pattern.setToolTip(
            "文件名匹配模式，如 *.csv;*.xlsx；支持分号多模式"
        )
        self.cmb_pattern_preset = QComboBox()
        try:
            self.cmb_pattern_preset.setObjectName("patternPreset")
        except Exception:
            pass
        self._pattern_presets = [
            ("自定义", None),
            ("仅 CSV", "*.csv"),
            ("CSV + Excel", "*.csv;*.xlsx;*.xls"),
            ("特殊格式", "*.mtfmt;*.mtdata;*.txt;*.dat"),
            ("全部支持", "*.csv;*.xlsx;*.xls;*.mtfmt;*.mtdata;*.txt;*.dat"),
        ]
        for name, _pat in self._pattern_presets:
            self.cmb_pattern_preset.addItem(name)

        def _apply_preset(idx: int) -> None:
            try:
                if idx < 0 or idx >= len(self._pattern_presets):
                    return
                pat = self._pattern_presets[idx][1]
                if not pat:
                    return
                try:
                    self.inp_pattern.blockSignals(True)
                    self.inp_pattern.setText(pat)
                finally:
                    self.inp_pattern.blockSignals(False)
                self.patternChanged.emit(pat)
            except Exception:
                logger.debug("apply preset failed", exc_info=True)

        def _mark_custom(_text: str) -> None:
            try:
                if self.cmb_pattern_preset.currentIndex() != 0:
                    self.cmb_pattern_preset.blockSignals(True)
                    self.cmb_pattern_preset.setCurrentIndex(0)
                    self.cmb_pattern_preset.blockSignals(False)
            except Exception:
                pass

        try:
            self.cmb_pattern_preset.currentIndexChanged.connect(_apply_preset)
        except Exception:
            logger.debug("无法连接 cmb_pattern_preset 信号", exc_info=True)

        try:
            self.inp_pattern.textEdited.connect(_mark_custom)
            self.inp_pattern.textChanged.connect(self.patternChanged.emit)
        except Exception:
            logger.debug("无法连接 inp_pattern 信号", exc_info=True)

        # 保持匹配模式输入与下拉高度一致
        try:
            h2 = max(self.inp_pattern.sizeHint().height(), 26)
            self.inp_pattern.setFixedHeight(h2)
            self.cmb_pattern_preset.setFixedHeight(h2)
        except Exception:
            pass

        pattern_row = QHBoxLayout()
        pattern_row.setContentsMargins(0, 0, 0, 0)
        pattern_row.addWidget(self.inp_pattern)
        pattern_row.addWidget(self.cmb_pattern_preset)
        self.row_pattern_widget = QWidget()
        self.row_pattern_widget.setLayout(pattern_row)
        self.file_form.addRow("匹配模式:", self.row_pattern_widget)

    def set_workflow_step(self, step: str) -> None:
        """按流程显示/隐藏控件，减少初始化时的注意力分散。"""
        step = (step or "").strip()

        def _set_row_visible(field_widget: QWidget, visible: bool) -> None:
            if field_widget is None:
                return
            try:
                label = self.file_form.labelForField(field_widget)
                if label is not None:
                    label.setVisible(visible)
            except Exception:
                pass
            try:
                field_widget.setVisible(visible)
            except Exception:
                pass

        # init：只保留“输入路径”；其他行隐藏
        if step in ("init", "step1"):
            _set_row_visible(
                getattr(self, "row_format_summary_widget", None), False
            )
            _set_row_visible(getattr(self, "row_pattern_widget", None), False)
            return

        # step2：展示文件列表相关（匹配模式在目录模式下才有意义，默认显示）
        if step == "step2":
            _set_row_visible(
                getattr(self, "row_format_summary_widget", None), False
            )
            _set_row_visible(getattr(self, "row_pattern_widget", None), True)
            return

        # step3+：全部显示
        _set_row_visible(
            getattr(self, "row_format_summary_widget", None), False
        )
        _set_row_visible(getattr(self, "row_pattern_widget", None), True)

    def _create_file_list(self) -> QWidget:
        """创建文件列表区域"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 文件选择按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self.btn_select_all = QPushButton("全选")
        self.btn_select_none = QPushButton("全不选")
        self.btn_select_invert = QPushButton("反选")

        for btn in [
            self.btn_select_all,
            self.btn_select_none,
            self.btn_select_invert,
        ]:
            btn.setMaximumWidth(70)

        try:
            # 设置快捷键：Ctrl+A 全选，Ctrl+Shift+A 全不选，Ctrl+I 反选
            self.btn_select_all.setShortcut("Ctrl+A")
            self.btn_select_all.setToolTip("全选（Ctrl+A）")
            self.btn_select_none.setShortcut("Ctrl+Shift+A")
            self.btn_select_none.setToolTip("全不选（Ctrl+Shift+A）")
            self.btn_select_invert.setShortcut("Ctrl+I")
            self.btn_select_invert.setToolTip("反选（Ctrl+I）")
        except Exception:
            pass

        self.btn_select_all.clicked.connect(self.selectAllRequested.emit)
        self.btn_select_none.clicked.connect(self.selectNoneRequested.emit)
        self.btn_select_invert.clicked.connect(
            self.invertSelectionRequested.emit
        )

        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_select_none)
        btn_row.addWidget(self.btn_select_invert)

        # 配置编辑器显示控制：默认不弹出，用户勾选后再显示
        self.chk_show_config = QCheckBox("显示配置编辑器")
        try:
            self.chk_show_config.setChecked(False)
            self.chk_show_config.setToolTip(
                "勾选后显示配置编辑器；不勾选则保持隐藏"
            )
        except Exception:
            pass
        try:
            self.chk_show_config.toggled.connect(self._on_toggle_config_panel)
        except Exception:
            logger.debug("无法连接 chk_show_config 信号", exc_info=True)
        btn_row.addWidget(self.chk_show_config)

        # 行选择批量作用域：当用户在数据行上执行“全选/全不选/反选”时，可对所有选中文件生效
        self.chk_bulk_row_selection = QCheckBox("行选择批量作用域")
        try:
            self.chk_bulk_row_selection.setChecked(True)
            self.chk_bulk_row_selection.setToolTip(
                "勾选后：在数据行上点击全选/全不选/反选，会对所有选中文件生效"
            )
        except Exception:
            pass
        btn_row.addWidget(self.chk_bulk_row_selection)

        # 快速筛选：简洁的单列筛选
        filter_label = QLabel("快速筛选:")
        filter_label.setStyleSheet("margin-left: 10px;")
        btn_row.addWidget(filter_label)

        # 列名输入框（带自动补全）
        self.inp_filter_column = QLineEdit()
        self.inp_filter_column.setPlaceholderText("列名...")
        self.inp_filter_column.setMaximumWidth(100)
        self.inp_filter_column.setToolTip("输入列名（支持自动补全）")
        self._filter_completer = QCompleter()
        self._filter_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.inp_filter_column.setCompleter(self._filter_completer)
        btn_row.addWidget(self.inp_filter_column)

        # 运算符选择
        self.cmb_filter_operator = QComboBox()
        self.cmb_filter_operator.addItems(
            ["包含", "不包含", "=", "≠", "<", ">", "≤", "≥", "≈"]
        )
        self.cmb_filter_operator.setMaximumWidth(60)
        self.cmb_filter_operator.setToolTip("选择筛选运算符")
        btn_row.addWidget(self.cmb_filter_operator)

        # 值输入框
        self.inp_filter_value = QLineEdit()
        self.inp_filter_value.setPlaceholderText("筛选值...")
        self.inp_filter_value.setMaximumWidth(100)
        self.inp_filter_value.setToolTip("输入筛选值")
        btn_row.addWidget(self.inp_filter_value)

        # 连接筛选信号
        try:
            self.inp_filter_column.textChanged.connect(
                self._on_quick_filter_changed
            )
            self.cmb_filter_operator.currentTextChanged.connect(
                self._on_operator_changed
            )
            self.inp_filter_value.textChanged.connect(
                self._on_quick_filter_changed
            )
        except Exception:
            logger.debug("连接快速筛选信号失败", exc_info=True)

        btn_row.addStretch()

        # 加载配置：移动到文件列表右上角（替代旧的全局 Source 显示）
        self.btn_load_config = QPushButton("加载配置")
        try:
            self.btn_load_config.setMaximumWidth(90)
            self.btn_load_config.setToolTip(
                "加载配置文件（JSON），用于提供 Source/Target part 定义"
            )
        except Exception:
            pass
        try:
            self.btn_load_config.clicked.connect(self._on_load_config_clicked)
        except Exception:
            logger.debug("无法连接 btn_load_config 信号", exc_info=True)

        # 开始批量处理：紧跟在加载配置后
        self.btn_batch_in_toolbar = QPushButton("开始处理")
        try:
            self.btn_batch_in_toolbar.setMaximumWidth(80)
            self.btn_batch_in_toolbar.setToolTip("开始批量处理（Ctrl+R）")
        except Exception:
            pass
        try:
            self.btn_batch_in_toolbar.clicked.connect(
                self.batchStartRequested.emit
            )
        except Exception:
            logger.debug("无法连接 btn_batch_in_toolbar 信号", exc_info=True)

        # 兼容旧字段名
        self.btn_batch = self.btn_batch_in_toolbar

        btn_row.addWidget(self.btn_load_config)
        btn_row.addWidget(self.btn_batch_in_toolbar)
        layout.addLayout(btn_row)

        # 文件树
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["文件/目录", "状态"])
        self.file_tree.setColumnWidth(0, 400)
        self.file_tree.setMinimumHeight(250)

        header = self.file_tree.header()
        try:
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        except Exception:
            pass

        layout.addWidget(self.file_tree)

        return widget

    def _on_toggle_config_panel(self, checked: bool) -> None:
        """用户勾选后再显示配置编辑器，避免点击文件时突然弹出。"""
        try:
            win = self.window()
            if win is not None and hasattr(win, "set_config_panel_visible"):
                win.set_config_panel_visible(bool(checked))
        except Exception:
            logger.debug("toggle config panel failed", exc_info=True)

    def _on_load_config_clicked(self) -> None:
        """从文件列表入口加载配置（替代旧的全局 Source 显示区）。"""
        try:
            win = self.window()
            if win is not None and hasattr(win, "load_config"):
                win.load_config()
        except Exception:
            logger.debug("load config from file list failed", exc_info=True)

    def _on_quick_filter_changed(self) -> None:
        """快速筛选条件变化"""
        try:
            column = self.inp_filter_column.text().strip()
            operator = self.cmb_filter_operator.currentText()
            value = self.inp_filter_value.text()
            self.quickFilterChanged.emit(column, operator, value)
        except Exception:
            logger.debug("快速筛选变化处理失败", exc_info=True)

    def _on_operator_changed(self) -> None:
        """运算符变化时更新值输入框验证器"""
        try:
            operator = self.cmb_filter_operator.currentText()
            # 数值运算符：=、≠、<、>、≤、≥、≈
            if operator in ["=", "≠", "<", ">", "≤", "≥", "≈"]:
                # 设置数值验证器
                validator = QDoubleValidator()
                validator.setNotation(QDoubleValidator.StandardNotation)
                self.inp_filter_value.setValidator(validator)
                self.inp_filter_value.setToolTip("输入数值")
            else:
                # 字符串运算符：包含、不包含
                self.inp_filter_value.setValidator(None)
                self.inp_filter_value.setToolTip("输入文本（区分大小写）")

            # 触发筛选更新
            self._on_quick_filter_changed()
        except Exception:
            logger.debug("运算符变化处理失败", exc_info=True)

    def update_filter_columns(self, columns: list) -> None:
        """更新快速筛选的列自动补全列表"""
        try:
            from PySide6.QtCore import QStringListModel

            model = QStringListModel([str(col) for col in columns])
            self._filter_completer.setModel(model)
        except Exception:
            logger.debug("更新筛选列补全列表失败", exc_info=True)

    def _create_tab_widget(self) -> QTabWidget:
        """创建Tab容器"""
        tab = QTabWidget()
        try:
            tab.setObjectName("mainTab")
        except Exception:
            pass

        # Tab 0: 文件列表
        tab.addTab(self.file_list_widget, "文件列表")

        # Tab 1: 处理日志
        self.log_tab = self._create_log_tab()
        tab.addTab(self.log_tab, "处理日志")

        return tab

    def _create_log_tab(self) -> QWidget:
        """创建日志Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.txt_batch_log = QTextEdit()
        try:
            self.txt_batch_log.setObjectName("batchLog")
        except Exception:
            pass
        self.txt_batch_log.setReadOnly(True)
        self.txt_batch_log.setFont(QFont("Consolas", 9))
        self.txt_batch_log.setMinimumHeight(160)
        self.txt_batch_log.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )

        layout.addWidget(self.txt_batch_log)

        return widget

    def _create_button_panel(self) -> QVBoxLayout:
        """创建按钮面板"""
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignTop)

        # 数据格式配置按钮
        self.btn_config_format = QPushButton("⚙ 配置\n数据格式")
        try:
            self.btn_config_format.setObjectName("secondaryButton")
            self.btn_config_format.setShortcut("Ctrl+Shift+F")
        except Exception:
            pass
        self.btn_config_format.setToolTip("设置会话级别的全局数据格式")
        self.btn_config_format.setFixedWidth(100)
        self.btn_config_format.setFixedHeight(50)
        self.btn_config_format.clicked.connect(self.formatConfigRequested.emit)
        # 新流程：不再使用“配置数据格式”按钮（格式相关逻辑交由 per-file/特殊格式解析负责）。
        # 为保持旧代码兼容，保留对象但隐藏/禁用。
        self.btn_config_format.setVisible(False)
        self.btn_config_format.setEnabled(False)

        # 撤销按钮
        self.btn_undo = QPushButton("撤销\n批处理")
        try:
            self.btn_undo.setObjectName("secondaryButton")
            self.btn_undo.setShortcut("Ctrl+Z")
            self.btn_undo.setToolTip("撤销最近一次批处理")
        except Exception:
            pass
        self.btn_undo.setFixedWidth(100)
        self.btn_undo.setFixedHeight(50)
        self.btn_undo.clicked.connect(self.undoRequested.emit)
        self.btn_undo.setVisible(False)
        self.btn_undo.setEnabled(False)

        # layout.addWidget(self.btn_config_format)  # 已移除
        layout.addWidget(self.btn_undo)
        layout.addStretch()

        return layout

    def show_progress(self, visible: bool):
        """显示/隐藏进度条"""
        self.progress_bar.setVisible(visible)

    def set_progress(self, value: int):
        """设置进度值"""
        self.progress_bar.setValue(value)

    def append_log(self, message: str):
        """追加日志消息"""
        self.txt_batch_log.append(message)

    def switch_to_log_tab(self):
        """切换到日志Tab"""
        self.tab_main.setCurrentIndex(1)
