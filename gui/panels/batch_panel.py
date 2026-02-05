"""
批处理面板 - 包含文件树、Tab页、进度条、操作按钮
"""

import logging

from PySide6.QtCore import QEvent, QStringListModel, Qt, Signal
from PySide6.QtGui import QDoubleValidator, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# 本地 FilterLineEdit 实现已移除：事件由 BatchPanel 的全局 eventFilter 处理（运行时已确认生效）


class BatchPanel(QWidget):
    """批处理面板 - 封装文件树、Tab页、进度条和操作按钮"""

    # 信号定义
    batchStartRequested = Signal()  # 请求开始批处理
    undoRequested = Signal()  # 请求撤销
    browseRequested = Signal()  # 请求浏览输入路径
    selectAllRequested = Signal()  # 全选文件
    selectNoneRequested = Signal()  # 全不选
    invertSelectionRequested = Signal()  # 反选
    quickFilterChanged = Signal(str, str, str)  # 快速筛选变化(列名, 运算符, 筛选值)
    quickSelectRequested = Signal()  # 快速选择
    bottomBarToggled = Signal(bool)  # 切换底部栏显示/隐藏
    saveProjectRequested = Signal()  # 保存Project请求

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status_legend = None  # 状态符号说明面板（延迟初始化）
        self.btn_status_help = None  # 状态符号帮助按钮
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

        # 安装全局事件过滤器以拦截 Tab 导致的焦点切换（针对 inp_filter_column）
        try:
            app = QApplication.instance()
            if app is not None:
                try:
                    app.installEventFilter(self)
                except Exception:
                    logger.debug("安装全局事件过滤器失败", exc_info=True)
        except Exception:
            logger.debug("安装全局事件过滤器时发生错误", exc_info=True)

        # 初始化阶段：按流程先隐藏非必要控件
        try:
            self.set_workflow_step("init")
        except Exception:
            logger.debug("set_workflow_step init failed", exc_info=True)

        # 延迟创建状态符号说明面板（避免在初始化时创建过多 Qt 对象）
        self._init_status_legend_lazily()

    def _init_input_rows(self):
        """初始化输入路径与模式控件（兼容旧接口）。"""
        # 输入路径
        # 调整表单标签对齐为右侧垂直居中，确保标签与输入控件垂直对齐
        try:
            self.file_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        except Exception as e:
            logger.debug("设置表单标签对齐失败（非致命）: %s", e, exc_info=True)
        # 保留属性以兼容旧代码，但在首页不显示输入框
        self.inp_batch_input = QLineEdit()
        self.inp_batch_input.setPlaceholderText("选择文件或目录...")
        try:
            # 隐藏旧输入框，避免在首页展示
            self.inp_batch_input.setVisible(False)
        except Exception as e:
            logger.debug("隐藏旧输入框失败（非致命）: %s", e, exc_info=True)
        self.btn_browse_input = QPushButton("浏览文件")
        try:
            self.btn_browse_input.setObjectName("smallButton")
            self.btn_browse_input.setToolTip("选择输入文件或目录")
        except Exception as e:
            logger.debug(
                "设置 btn_browse_input 属性失败（非致命）: %s",
                e,
                exc_info=True,
            )
        self.btn_browse_input.clicked.connect(self.browseRequested.emit)
        # 保持输入框与按钮高度一致以使其与表单标签对齐
        try:
            h = max(self.inp_batch_input.sizeHint().height(), 26)
            self.inp_batch_input.setFixedHeight(h)
            self.btn_browse_input.setFixedHeight(h)
            # 增大“浏览”按钮的最小宽度，避免显示过窄显得不协调
            try:
                self.btn_browse_input.setMinimumWidth(80)
            except Exception:
                logger.debug(
                    "设置 btn_browse_input 最小宽度失败（非致命）",
                    exc_info=True,
                )
        except Exception:
            pass

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        # 不再将旧输入框加入布局，仅保留浏览/操作按钮
        input_row.addWidget(self.btn_browse_input)
        # 将“加载配置”和“开始处理”按钮放在“浏览文件”右侧
        self.btn_load_config = QPushButton("加载配置")
        try:
            self.btn_load_config.setMaximumWidth(90)
            self.btn_load_config.setToolTip(
                "加载配置文件（JSON），用于提供 Source/Target part 定义"
            )
        except Exception as e:
            logger.debug(
                "设置 btn_load_config 属性失败（非致命）: %s", e, exc_info=True
            )
        try:
            self.btn_load_config.clicked.connect(self._on_load_config_clicked)
        except Exception:
            logger.debug("无法连接 btn_load_config 信号", exc_info=True)

        self.btn_batch_in_toolbar = QPushButton("开始处理")
        try:
            self.btn_batch_in_toolbar.setMaximumWidth(80)
            self.btn_batch_in_toolbar.setToolTip("开始批量处理（Ctrl+R）")
        except Exception as e:
            logger.debug(
                "设置 btn_batch_in_toolbar 属性失败（非致命）: %s",
                e,
                exc_info=True,
            )
        try:
            self.btn_batch_in_toolbar.clicked.connect(self.batchStartRequested.emit)
        except Exception:
            logger.debug("无法连接 btn_batch_in_toolbar 信号", exc_info=True)

        self.btn_save_project = QPushButton("保存Project")
        try:
            self.btn_save_project.setMaximumWidth(90)
            self.btn_save_project.setToolTip("保存当前项目配置和状态")
        except Exception as e:
            logger.debug(
                "设置 btn_save_project 属性失败（非致命）: %s",
                e,
                exc_info=True,
            )
        try:
            self.btn_save_project.clicked.connect(self.saveProjectRequested.emit)
        except Exception:
            logger.debug("无法连接 btn_save_project 信号", exc_info=True)

        # 兼容旧字段名
        self.btn_batch = self.btn_batch_in_toolbar

        input_row.addWidget(self.btn_load_config)
        input_row.addWidget(self.btn_batch_in_toolbar)
        input_row.addWidget(self.btn_save_project)
        self.row_input_widget = QWidget()
        self.row_input_widget.setLayout(input_row)
        # 按钮已移至菜单栏，此行隐藏
        self.row_input_widget.setVisible(False)
        # 去除表单左侧的标签提示（首页不再展示输入路径标签）
        self.file_form.addRow("", self.row_input_widget)

        # 全局数据格式配置已移除：表格列映射改为自动识别。
        self.lbl_format_summary = None
        self.row_format_summary_widget = None

        # 匹配模式相关控件已移除，保留兼容性属性
        self.inp_pattern = None
        self.cmb_pattern_preset = None
        self._pattern_presets = []
        self.row_pattern_widget = None

    def _init_status_legend_lazily(self) -> None:
        """延迟创建状态符号说明面板

        在第一次点击帮助按钮时创建，而不是在初始化时创建，以提高启动速度。
        """
        def _create_legend():
            """创建说明面板并与按钮关联"""
            try:
                if self._status_legend is None and self.btn_status_help is not None:
                    from gui.status_symbol_legend import StatusSymbolLegend

                    # 创建说明面板（最初隐藏）
                    self._status_legend = StatusSymbolLegend(self.window())
                    self._status_legend.hide()

                    # 关联按钮和面板
                    self.btn_status_help.set_legend(self._status_legend)
            except Exception as e:
                logger.debug("延迟创建状态符号说明面板失败: %s", e, exc_info=True)

        # 在首次需要时创建
        if self.btn_status_help is not None:
            try:
                # 连接首次点击以创建面板
                original_click = self.btn_status_help.clicked

                def _on_first_click():
                    _create_legend()
                    # 取消首次点击处理，之后使用正常流程
                    self.btn_status_help.clicked.disconnect(_on_first_click)
                    if self._status_legend is not None:
                        self.btn_status_help.clicked.connect(
                            self._status_legend.toggle_legend
                        )
                    # 触发第一次点击的效果
                    if self._status_legend is not None:
                        self._status_legend.show_legend()

                self.btn_status_help.clicked.connect(_on_first_click)
            except Exception as e:
                logger.debug("连接状态符号帮助按钮失败: %s", e, exc_info=True)

    def set_workflow_step(self, step: str) -> None:
        """按流程显示/隐藏控件，并向用户显示明确的步骤提示。

        此方法：
        1. 根据步骤隐藏/显示相关控件
        2. 向用户显示当前步骤和下一步提示（通过 SignalBus）
        """
        step = (step or "").strip()

        # 导入步骤信息
        try:
            from gui.workflow_progress_indicator import WORKFLOW_STEPS
        except Exception:
            WORKFLOW_STEPS = {}

        def _set_row_visible(field_widget: QWidget, visible: bool) -> None:
            if field_widget is None:
                return
            try:
                label = self.file_form.labelForField(field_widget)
                if label is not None:
                    label.setVisible(visible)
            except Exception:
                logger.debug(
                    "尝试获取并设置表单标签可见性失败（非致命）", exc_info=True
                )
            try:
                field_widget.setVisible(visible)
            except Exception:
                logger.debug("设置字段可见性失败（非致命）", exc_info=True)

        # init 和 step1：只保留操作按钮
        if step in ("init", "step1"):
            _set_row_visible(getattr(self, "row_format_summary_widget", None), False)
            
            # 发送状态提示到用户
            try:
                from gui.signal_bus import SignalBus
                from gui.status_message_queue import MessagePriority
                
                step_info = WORKFLOW_STEPS.get(step, {})
                instruction = step_info.get("instruction", "")
                if instruction:
                    SignalBus.instance().statusMessage.emit(
                        f"📋 {instruction}",
                        0,  # 永久显示
                        MessagePriority.HIGH,
                    )
            except Exception:
                logger.debug("发送步骤提示失败（非致命）", exc_info=True)
            return

        # step2+：保持默认显示，发送相应提示
        if step in ("step2", "step3"):
            _set_row_visible(getattr(self, "row_format_summary_widget", None), False)
            
            # 发送状态提示到用户
            try:
                from gui.signal_bus import SignalBus
                from gui.status_message_queue import MessagePriority
                
                step_info = WORKFLOW_STEPS.get(step, {})
                instruction = step_info.get("instruction", "")
                if instruction:
                    SignalBus.instance().statusMessage.emit(
                        f"{'⚙️' if step == 'step3' else '📂'} {instruction}",
                        0,  # 永久显示
                        MessagePriority.HIGH,
                    )
            except Exception:
                logger.debug("发送步骤提示失败（非致命）", exc_info=True)
            
            # 标记为已加载数据（主要用于启用 Data 管理选项卡与开始按钮）
            try:
                win = self.window()
                if win is not None and hasattr(win, "mark_data_loaded"):
                    try:
                        win.mark_data_loaded()
                    except Exception:
                        pass
                elif win is not None:
                    try:
                        # 优先通过 UIStateManager 设置（若存在）
                        if hasattr(win, "ui_state_manager") and getattr(
                            win, "ui_state_manager"
                        ):
                            try:
                                win.ui_state_manager.set_data_loaded(True)
                                return
                            except Exception:
                                pass

                        # 兼容性回退：直接设置属性并刷新（若方法不存在）
                        try:
                            win.data_loaded = True
                            # 不再把加载标记视为用户修改：仅刷新状态
                            if hasattr(win, "_refresh_controls_state"):
                                try:
                                    win._refresh_controls_state()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass
            return

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
        self.btn_quick_select = QPushButton("快速选择")

        for btn in [
            self.btn_select_all,
            self.btn_select_none,
            self.btn_select_invert,
            self.btn_quick_select,
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
        self.btn_select_invert.clicked.connect(self.invertSelectionRequested.emit)
        self.btn_quick_select.clicked.connect(self.quickSelectRequested.emit)

        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_select_none)
        btn_row.addWidget(self.btn_select_invert)
        btn_row.addWidget(self.btn_quick_select)

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
        # 使用未过滤弹出模式，便于显示全部候选并使用 Tab 在候选间切换
        try:
            self._filter_completer.setCompletionMode(
                QCompleter.UnfilteredPopupCompletion
            )
        except Exception:
            pass
        self.inp_filter_column.setCompleter(self._filter_completer)
        # 避免 Tab 导致控件失去焦点，使 FilterLineEdit 能拦截 Tab 用于切换补全项
        try:
            self.inp_filter_column.setTabChangesFocus(False)
        except Exception:
            pass
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
            self.inp_filter_column.textChanged.connect(self._on_quick_filter_changed)
            self.cmb_filter_operator.currentTextChanged.connect(
                self._on_operator_changed
            )
            self.inp_filter_value.textChanged.connect(self._on_quick_filter_changed)
        except Exception:
            logger.debug("连接快速筛选信号失败", exc_info=True)

        btn_row.addStretch()

        # 添加状态符号帮助按钮
        try:
            from gui.status_symbol_legend import StatusSymbolButton
            self.btn_status_help = StatusSymbolButton(self)
            self.btn_status_help.setToolTip("点击查看文件验证状态说明（✓ ⚠ ❓）")
            btn_row.addWidget(self.btn_status_help)
        except Exception as e:
            logger.debug("创建状态符号帮助按钮失败: %s", e, exc_info=True)
            self.btn_status_help = None

        # 注意："加载配置" 与 "开始处理" 按钮已移至输入行，避免在此重复创建
        layout.addLayout(btn_row)

        # 文件树
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["文件/目录", "状态"])
        self.file_tree.setColumnWidth(0, 400)
        self.file_tree.setMinimumHeight(250)

        header = self.file_tree.header()
        try:
            # 允许用户拖动调整列宽
            header.setSectionResizeMode(0, QHeaderView.Interactive)
            header.setSectionResizeMode(1, QHeaderView.Interactive)
            # 设置默认列宽（11:4 比例）
            header.resizeSection(0, 1100)
            header.resizeSection(1, 200)
        except Exception:
            pass

        layout.addWidget(self.file_tree)

        # 启用右键菜单
        try:
            self.file_tree.setContextMenuPolicy(Qt.CustomContextMenu)
            self.file_tree.customContextMenuRequested.connect(
                self._show_file_tree_context_menu
            )
        except Exception:
            logger.debug("设置文件树右键菜单失败", exc_info=True)

        # 未保存配置指示器（在文件列表上方明显显示）
        try:
            self.lbl_unsaved_indicator = QLabel("● 有未保存配置")
            self.lbl_unsaved_indicator.setStyleSheet(
                "color: #d9534f; font-weight: bold;"
            )
            self.lbl_unsaved_indicator.setVisible(False)
            self.lbl_unsaved_indicator.setToolTip(
                "检测到未保存的配置。开始批处理会提示保存，或在文件列表中查看详情。"
            )
            layout.addWidget(self.lbl_unsaved_indicator)
        except Exception:
            logger.debug("创建未保存配置指示器失败（非致命）", exc_info=True)
        return widget


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
                self.inp_filter_value.setToolTip("输入文本（不区分大小写）")

            # 触发筛选更新
            self._on_quick_filter_changed()
        except Exception:
            logger.debug("运算符变化处理失败", exc_info=True)

    def update_filter_columns(self, columns: list) -> None:
        """更新快速筛选的列自动补全列表"""
        try:
            model = QStringListModel([str(col) for col in columns])
            self._filter_completer.setModel(model)
        except Exception:
            logger.debug("更新筛选列补全列表失败", exc_info=True)

    # eventFilter 安装：使用全局 eventFilter 处理 Tab 行为（运行时已确认生效）
    def eventFilter(self, obj, event):
        """全局事件过滤：拦截 Tab / Shift+Tab，当焦点在 `inp_filter_column` 时处理补全弹窗。

        采用全局过滤可以在 Windows/Qt 平台上可靠拦截导致的焦点切换。
        """
        try:
            if event.type() == QEvent.KeyPress:
                key = event.key()
                if key in (Qt.Key_Tab, Qt.Key_Backtab):
                    try:
                        app = QApplication.instance()
                        fw = app.focusWidget() if app is not None else None
                    except Exception:
                        fw = None

                    if fw is self.inp_filter_column:
                        comp = getattr(
                            self.inp_filter_column, "completer", lambda: None
                        )()
                        try:
                            popup = comp.popup() if comp is not None else None
                        except Exception:
                            popup = None

                        # 若未显示，先显示候选
                        try:
                            if (
                                popup is None
                                or not getattr(popup, "isVisible", lambda: False)()
                            ):
                                if comp is not None:
                                    comp.complete()
                                logger.debug(
                                    "BatchPanel.eventFilter: invoked completer.complete() (global filter)"
                                )
                                return True

                            # 已显示：在 popup 中循环选择（Tab 向前，Shift+Tab 向后）
                            model = popup.model()
                            if model is None:
                                return True
                            row_count = model.rowCount()
                            cur = popup.currentIndex()
                            cur_row = cur.row() if cur.isValid() else -1
                            if key == Qt.Key_Tab:
                                next_row = (cur_row + 1) % max(1, row_count)
                            else:
                                next_row = (cur_row - 1) % max(1, row_count)
                            try:
                                new_idx = model.index(next_row, 0)
                                popup.setCurrentIndex(new_idx)
                                logger.debug(
                                    "BatchPanel.eventFilter: cycled popup to row %s/%s (global filter)",
                                    next_row,
                                    row_count,
                                )
                                return True
                            except Exception:
                                logger.debug(
                                    "BatchPanel.eventFilter: failed to set popup index",
                                    exc_info=True,
                                )
                                return True
                        except Exception:
                            return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _create_tab_widget(self) -> QTabWidget:
        """创建Tab容器"""
        tab = QTabWidget()
        try:
            tab.setObjectName("mainTab")
        except Exception:
            pass

        # Tab 0: 参考系管理（将由主窗口替换为ConfigPanel）
        self.config_tab_placeholder = QWidget()
        tab.addTab(self.config_tab_placeholder, "参考系管理")

        # Tab 1: 数据管理（文件列表）
        tab.addTab(self.file_list_widget, "数据管理")

        # Tab 2: 操作日志
        self.log_tab = self._create_log_tab()
        tab.addTab(self.log_tab, "操作日志")

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
        self.txt_batch_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(self.txt_batch_log)

        return widget

    def _create_button_panel(self) -> QVBoxLayout:
        """创建按钮面板"""
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignTop)

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
        try:
            idx = self.tab_main.indexOf(getattr(self, "log_tab", None))
            if idx is not None and idx != -1:
                self.tab_main.setCurrentIndex(idx)
            else:
                # 兜底到最后一个 Tab（若找不到 log_tab）
                self.tab_main.setCurrentIndex(max(0, self.tab_main.count() - 1))
        except Exception:
            try:
                self.tab_main.setCurrentIndex(1)
            except Exception:
                pass

    def set_unsaved_indicator(self, unsaved: bool) -> None:
        """设置文件列表上方的未保存配置指示器的可见性和提示文本。"""
        try:
            if not hasattr(self, "lbl_unsaved_indicator"):
                return
            self.lbl_unsaved_indicator.setVisible(bool(unsaved))
            try:
                if unsaved:
                    self.lbl_unsaved_indicator.setToolTip(
                        "检测到未保存的配置。开始批处理会提示保存。"
                    )
                else:
                    self.lbl_unsaved_indicator.setToolTip("")
            except Exception:
                logger.debug("更新未保存指示器提示失败（非致命）", exc_info=True)
        except Exception:
            logger.debug("set_unsaved_indicator 失败（非致命）", exc_info=True)
    def _show_file_tree_context_menu(self, pos):
        """显示文件树右键菜单"""
        try:
            from PySide6.QtWidgets import QMenu

            menu = QMenu(self.file_tree)

            # 基础选择操作
            act_select_all = menu.addAction("全选 (Ctrl+A)")
            act_select_all.triggered.connect(self.selectAllRequested.emit)

            act_select_none = menu.addAction("全不选 (Ctrl+Shift+A)")
            act_select_none.triggered.connect(self.selectNoneRequested.emit)

            act_invert = menu.addAction("反选 (Ctrl+I)")
            act_invert.triggered.connect(self.invertSelectionRequested.emit)

            menu.addSeparator()

            # 智能筛选操作
            act_select_ready = menu.addAction("✓ 选择已就绪文件")
            act_select_ready.triggered.connect(lambda: self._select_files_by_status("✓"))

            act_select_warning = menu.addAction("⚠ 选择有警告的文件")
            act_select_warning.triggered.connect(lambda: self._select_files_by_status("⚠"))

            act_select_unverified = menu.addAction("❓ 选择未验证文件")
            act_select_unverified.triggered.connect(lambda: self._select_files_by_status("❓"))

            act_select_error = menu.addAction("❌ 选择有错误的文件")
            act_select_error.triggered.connect(lambda: self._select_files_by_status("❌"))

            # 在鼠标位置显示菜单
            global_pos = self.file_tree.viewport().mapToGlobal(pos)
            menu.exec(global_pos)

        except Exception:
            logger.debug("显示文件树右键菜单失败", exc_info=True)

    def _select_files_by_status(self, status_symbol: str):
        """按状态符号选择文件（仅选择文件节点，忽略目录节点）"""
        try:
            # 遍历所有树项
            def select_matching_items(parent_item):
                """递归遍历并选择匹配的文件项"""
                if parent_item is None:
                    # 根级遍历
                    for i in range(self.file_tree.topLevelItemCount()):
                        item = self.file_tree.topLevelItem(i)
                        select_matching_items(item)
                else:
                    # 检查是否是文件节点（通过 UserRole 数据判断）
                    file_path = parent_item.data(0, Qt.UserRole)
                    is_file = file_path is not None

                    if is_file:
                        # 获取状态文本
                        status_text = parent_item.text(1)
                        if status_text.startswith(status_symbol):
                            try:
                                parent_item.setCheckState(0, Qt.Checked)
                            except Exception:
                                pass  # 单文件模式下可能无法修改

                    # 递归处理子项
                    for i in range(parent_item.childCount()):
                        child = parent_item.child(i)
                        select_matching_items(child)

            select_matching_items(None)

        except Exception:
            logger.debug("按状态筛选文件失败: %s", status_symbol, exc_info=True)
