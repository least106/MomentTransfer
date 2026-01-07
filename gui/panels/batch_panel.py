"""
批处理面板 - 包含文件树、Tab页、进度条、操作按钮
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QProgressBar,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QTextEdit, QLabel,
    QGroupBox, QHeaderView, QSizePolicy, QLineEdit, QFormLayout, QComboBox
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

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

    def _init_input_rows(self):
        """初始化输入路径与模式控件（兼容旧接口）。"""
        # 输入路径
        self.inp_batch_input = QLineEdit()
        self.inp_batch_input.setPlaceholderText("选择文件或目录...")
        self.btn_browse_input = QPushButton("浏览")
        try:
            self.btn_browse_input.setObjectName('smallButton')
            self.btn_browse_input.setToolTip('选择输入文件或目录')
        except Exception:
            pass
        self.btn_browse_input.clicked.connect(self.browseRequested.emit)
        input_row = QHBoxLayout()
        input_row.addWidget(self.inp_batch_input)
        input_row.addWidget(self.btn_browse_input)
        self.file_form.addRow("输入路径:", input_row)

        # 匹配模式
        self.inp_pattern = QLineEdit("*.csv")
        self.inp_pattern.setToolTip("文件名匹配模式，如 *.csv;*.xlsx；支持分号多模式")
        self.cmb_pattern_preset = QComboBox()
        try:
            self.cmb_pattern_preset.setObjectName('patternPreset')
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
                logger.debug('apply preset failed', exc_info=True)

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
            logger.debug('无法连接 cmb_pattern_preset 信号', exc_info=True)

        try:
            self.inp_pattern.textEdited.connect(_mark_custom)
            self.inp_pattern.textChanged.connect(self.patternChanged.emit)
        except Exception:
            logger.debug("无法连接 inp_pattern 信号", exc_info=True)

        pattern_row = QHBoxLayout()
        pattern_row.addWidget(self.inp_pattern)
        pattern_row.addWidget(self.cmb_pattern_preset)
        self.file_form.addRow("匹配模式:", pattern_row)
    
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
        
        for btn in [self.btn_select_all, self.btn_select_none, self.btn_select_invert]:
            btn.setMaximumWidth(70)
        
        self.btn_select_all.clicked.connect(self.selectAllRequested.emit)
        self.btn_select_none.clicked.connect(self.selectNoneRequested.emit)
        self.btn_select_invert.clicked.connect(self.invertSelectionRequested.emit)
        
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_select_none)
        btn_row.addWidget(self.btn_select_invert)
        btn_row.addStretch()
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
    
    def _create_tab_widget(self) -> QTabWidget:
        """创建Tab容器"""
        tab = QTabWidget()
        try:
            tab.setObjectName('mainTab')
        except Exception:
            pass
        
        # Tab 0: 信息页
        self.info_tab = self._create_info_tab()
        tab.addTab(self.info_tab, "信息")
        
        # Tab 1: 文件列表（已在外部）
        tab.addTab(self.file_list_widget, "文件列表")
        
        # Tab 2: 处理日志
        self.log_tab = self._create_log_tab()
        tab.addTab(self.log_tab, "处理日志")
        
        return tab
    
    def _create_info_tab(self) -> QWidget:
        """创建信息Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # 配置状态
        self.lbl_status = QLabel("未加载配置")
        try:
            self.lbl_status.setObjectName('statusLabel')
            font = self.lbl_status.font()
            font.setPointSize(10)
            font.setBold(True)
            self.lbl_status.setFont(font)
        except Exception:
            pass
        layout.addWidget(self.lbl_status)
        
        # 数据格式预览
        format_group = QGroupBox("数据格式预览")
        format_layout = QVBoxLayout(format_group)
        format_layout.setSpacing(4)
        
        self.lbl_preview_skip = QLabel("跳过行: -")
        self.lbl_preview_passthrough = QLabel("保留列: -")
        self.lbl_preview_columns = QLabel("列映射: -")
        
        for w in [self.lbl_preview_skip, self.lbl_preview_passthrough, self.lbl_preview_columns]:
            try:
                w.setObjectName('previewText')
            except Exception:
                pass
            format_layout.addWidget(w)
        
        layout.addWidget(format_group)
        layout.addStretch()
        
        return widget
    
    def _create_log_tab(self) -> QWidget:
        """创建日志Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.txt_batch_log = QTextEdit()
        try:
            self.txt_batch_log.setObjectName('batchLog')
        except Exception:
            pass
        self.txt_batch_log.setReadOnly(True)
        self.txt_batch_log.setFont(QFont("Consolas", 9))
        self.txt_batch_log.setMinimumHeight(160)
        self.txt_batch_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
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
            self.btn_config_format.setObjectName('secondaryButton')
            self.btn_config_format.setShortcut('Ctrl+Shift+F')
        except Exception:
            pass
        self.btn_config_format.setToolTip("设置会话级别的全局数据格式")
        self.btn_config_format.setFixedWidth(100)
        self.btn_config_format.setFixedHeight(50)
        self.btn_config_format.clicked.connect(self.formatConfigRequested.emit)
        
        # 执行按钮
        self.btn_batch = QPushButton("开始\n批量处理")
        try:
            self.btn_batch.setObjectName('primaryButton')
            self.btn_batch.setShortcut('Ctrl+R')
            self.btn_batch.setToolTip('开始批量处理')
        except Exception:
            pass
        self.btn_batch.setFixedWidth(100)
        self.btn_batch.setFixedHeight(50)
        self.btn_batch.clicked.connect(self.batchStartRequested.emit)
        
        # 撤销按钮
        self.btn_undo = QPushButton("撤销\n批处理")
        try:
            self.btn_undo.setObjectName('secondaryButton')
            self.btn_undo.setShortcut('Ctrl+Z')
            self.btn_undo.setToolTip('撤销最近一次批处理')
        except Exception:
            pass
        self.btn_undo.setFixedWidth(100)
        self.btn_undo.setFixedHeight(50)
        self.btn_undo.clicked.connect(self.undoRequested.emit)
        self.btn_undo.setVisible(False)
        self.btn_undo.setEnabled(False)
        
        layout.addWidget(self.btn_config_format)
        layout.addWidget(self.btn_batch)
        layout.addWidget(self.btn_undo)
        layout.addStretch()
        
        return layout
    
    def show_progress(self, visible: bool):
        """显示/隐藏进度条"""
        self.progress_bar.setVisible(visible)
    
    def set_progress(self, value: int):
        """设置进度值"""
        self.progress_bar.setValue(value)
    
    def set_status(self, text: str):
        """设置状态文本"""
        self.lbl_status.setText(text)
    
    def update_format_preview(self, skip_rows: int, passthrough: list, columns: dict):
        """更新格式预览"""
        self.lbl_preview_skip.setText(f"跳过行: {skip_rows}")
        self.lbl_preview_passthrough.setText(f"保留列: {', '.join(map(str, passthrough)) if passthrough else '无'}")
        col_text = ', '.join([f"{k}→{v}" for k, v in columns.items()]) if columns else '无'
        self.lbl_preview_columns.setText(f"列映射: {col_text}")
    
    def append_log(self, message: str):
        """追加日志消息"""
        self.txt_batch_log.append(message)
    
    def switch_to_log_tab(self):
        """切换到日志Tab"""
        self.tab_main.setCurrentIndex(2)
