"""
对话框模块：包含列映射配置对话框和实验性功能对话框
"""

import json
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from src.format_registry import delete_mapping, list_mappings, register_mapping

logger = logging.getLogger(__name__)


class ColumnMappingDialog(QDialog):
    """列映射配置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据格式配置")
        self.resize(500, 200)
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

        for spin in [
            self.col_fx,
            self.col_fy,
            self.col_fz,
            self.col_mx,
            self.col_my,
            self.col_mz,
        ]:
            spin.setRange(0, 1000)
            spin.setValue(0)

        # 默认将列映射控件置为不可编辑（灰显），需要用户显式启用后才能修改
        # 这样可以避免误操作。若需要立即启用，请在代码中调用控件的 setEnabled(True)。
        for spin in [
            self.col_alpha,
            self.col_fx,
            self.col_fy,
            self.col_fz,
            self.col_mx,
            self.col_my,
            self.col_mz,
        ]:
            try:
                spin.setEnabled(False)
            except Exception:
                pass

        form_cols.addRow("迎角 Alpha (可选):", self.col_alpha)
        form_cols.addRow("轴向力 Fx:", self.col_fx)
        form_cols.addRow("侧向力 Fy:", self.col_fy)
        form_cols.addRow("法向力 Fz:", self.col_fz)
        form_cols.addRow("滚转力矩 Mx:", self.col_mx)
        form_cols.addRow("俯仰力矩 My:", self.col_my)
        form_cols.addRow("偏航力矩 Mz:", self.col_mz)

        grp_columns.setLayout(form_cols)
        # 临时隐藏列映射分组（用户要求先隐藏这些控件）
        try:
            grp_columns.setVisible(False)
        except Exception:
            pass

        # 保留列
        grp_pass = QGroupBox("需要保留输出的其他列")
        layout_pass = QVBoxLayout()
        self.txt_passthrough = QLineEdit()
        self.txt_passthrough.setPlaceholderText("用逗号分隔列号，如: 0,1,2")
        layout_pass.addWidget(QLabel("列号:"))
        layout_pass.addWidget(self.txt_passthrough)
        grp_pass.setLayout(layout_pass)

        # 标准按钮 OK/Cancel
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

        # 额外的保存按钮
        self.btn_save_format = QPushButton("保存")
        self.btn_save_format.setToolTip("将当前数据格式保存为 JSON 文件")
        self.btn_save_format.clicked.connect(self._on_dialog_save)
        try:
            self.btn_save_format.setObjectName("secondaryButton")
        except Exception:
            pass

        # 额外的加载按钮
        self.btn_load_format = QPushButton("加载")
        self.btn_load_format.setToolTip("从 JSON 文件加载数据格式到当前对话框")
        self.btn_load_format.clicked.connect(self._on_dialog_load)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.btn_save_format)
        btn_row.addWidget(self.btn_load_format)
        btn_row.addWidget(btn_box)

        layout.addWidget(grp_skip)
        layout.addWidget(grp_columns)
        layout.addWidget(grp_pass)
        layout.addLayout(btn_row)

    def get_config(self):
        """获取并返回配置字典"""
        passthrough = []
        text = self.txt_passthrough.text().strip()
        if text:
            toks = [t.strip() for t in text.split(",") if t.strip()]
            invalid = []
            for tok in toks:
                try:
                    passthrough.append(int(tok))
                except ValueError:
                    invalid.append(tok)
            if invalid:
                QMessageBox.warning(
                    self,
                    "透传列解析警告",
                    f"以下透传列索引无法解析，已被忽略：{', '.join(invalid)}",
                )

        return {
            "skip_rows": self.spin_skip_rows.value(),
            "columns": {
                "alpha": (
                    self.col_alpha.value() if self.col_alpha.value() >= 0 else None
                ),
                "fx": self.col_fx.value(),
                "fy": self.col_fy.value(),
                "fz": self.col_fz.value(),
                "mx": self.col_mx.value(),
                "my": self.col_my.value(),
                "mz": self.col_mz.value(),
            },
            "passthrough": passthrough,
        }

    def set_config(self, cfg: dict):
        """用已有配置填充对话框控件"""
        if not isinstance(cfg, dict):
            return

        if "skip_rows" in cfg:
            try:
                self.spin_skip_rows.setValue(int(cfg.get("skip_rows", 0)))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Invalid skip_rows value %r: %s",
                    cfg.get("skip_rows"),
                    e,
                    exc_info=True,
                )

        cols = cfg.get("columns") or cfg.get("Columns") or {}
        try:
            if "alpha" in cols and cols.get("alpha") is not None:
                self.col_alpha.setValue(int(cols.get("alpha")))
            if "fx" in cols and cols.get("fx") is not None:
                self.col_fx.setValue(int(cols.get("fx")))
            if "fy" in cols and cols.get("fy") is not None:
                self.col_fy.setValue(int(cols.get("fy")))
            if "fz" in cols and cols.get("fz") is not None:
                self.col_fz.setValue(int(cols.get("fz")))
            if "mx" in cols and cols.get("mx") is not None:
                self.col_mx.setValue(int(cols.get("mx")))
            if "my" in cols and cols.get("my") is not None:
                self.col_my.setValue(int(cols.get("my")))
            if "mz" in cols and cols.get("mz") is not None:
                self.col_mz.setValue(int(cols.get("mz")))
        except (ValueError, TypeError) as e:
            logger.warning("Invalid column indices in %r: %s", cols, e, exc_info=True)

        passthrough = cfg.get("passthrough") or cfg.get("Passthrough") or []
        try:
            if isinstance(passthrough, (list, tuple)):
                self.txt_passthrough.setText(",".join(str(int(x)) for x in passthrough))
            elif isinstance(passthrough, str):
                self.txt_passthrough.setText(passthrough)
        except (ValueError, TypeError) as e:
            logger.warning(
                "Invalid passthrough values %r: %s",
                passthrough,
                e,
                exc_info=True,
            )

    def _on_dialog_save(self):
        """把当前对话框配置另存为 JSON 文件"""
        try:
            cfg = self.get_config()
            fname, _ = QFileDialog.getSaveFileName(
                self, "保存格式为", "format.json", "JSON Files (*.json)"
            )
            if not fname:
                return
            p = Path(fname)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "已保存", f"格式已保存到: {fname}")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法保存格式: {e}")

    def _on_dialog_load(self):
        """从 JSON 文件加载数据格式并填充对话框"""
        try:
            fname, _ = QFileDialog.getOpenFileName(
                self, "加载格式文件", "", "JSON Files (*.json)"
            )
            if not fname:
                return
            with open(fname, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            if not isinstance(cfg, dict):
                raise ValueError("格式文件应为 JSON 对象")
            self.set_config(cfg)
            QMessageBox.information(
                self, "已加载", f"已从 {fname} 加载格式并填充对话框"
            )
        except Exception as e:
            QMessageBox.warning(self, "加载失败", f"无法加载格式: {e}")


class ExperimentalDialog(QDialog):
    """实验性功能对话框"""

    def __init__(self, parent=None, initial_settings: dict = None):
        super().__init__(parent)
        self.setWindowTitle("实验性功能")
        self.resize(700, 480)
        self.initial_settings = initial_settings or {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # registry DB 行
        reg_row = QHBoxLayout()
        reg_row.addWidget(QLabel("格式注册表 (.sqlite):"))
        self.inp_registry_db = QLineEdit()
        self.inp_registry_db.setPlaceholderText("可选: registry 数据库 (.sqlite)")
        reg_row.addWidget(self.inp_registry_db)
        btn_browse = QPushButton("浏览")
        btn_browse.setMaximumWidth(90)
        btn_browse.clicked.connect(self._browse_registry_db)
        reg_row.addWidget(btn_browse)
        layout.addLayout(reg_row)

        # registry 映射列表
        self.lst_registry = QListWidget()
        self.lst_registry.setMinimumHeight(120)
        layout.addWidget(QLabel("Registry 映射:"))
        layout.addWidget(self.lst_registry)

        reg_ops = QHBoxLayout()
        self.inp_registry_pattern = QLineEdit()
        self.inp_registry_pattern.setPlaceholderText("Pattern，例如: *.csv")
        self.inp_registry_format = QLineEdit()
        self.inp_registry_format.setPlaceholderText("Format JSON 文件")
        reg_ops.addWidget(self.inp_registry_pattern)
        reg_ops.addWidget(self.inp_registry_format)
        btn_browse_fmt = QPushButton("浏览格式")
        btn_browse_fmt.setMaximumWidth(90)
        btn_browse_fmt.clicked.connect(self._browse_format_file)
        reg_ops.addWidget(btn_browse_fmt)
        layout.addLayout(reg_ops)

        btn_row = QHBoxLayout()
        self.btn_registry_register = QPushButton("注册映射")
        self.btn_registry_edit = QPushButton("编辑选中")
        self.btn_registry_remove = QPushButton("删除选中")
        btn_row.addStretch()
        btn_row.addWidget(self.btn_registry_register)
        btn_row.addWidget(self.btn_registry_edit)
        btn_row.addWidget(self.btn_registry_remove)
        layout.addLayout(btn_row)

        # 实验性开关
        self.chk_show_visual = QCheckBox("启用 3D 可视化（实验）")
        layout.addWidget(self.chk_show_visual)
        layout.addWidget(QLabel("最近项目（只作展示）"))
        self.lst_recent = QListWidget()
        self.lst_recent.setMaximumHeight(80)
        layout.addWidget(self.lst_recent)

        # 按钮
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        # 连接按钮
        self.btn_registry_register.clicked.connect(self._on_registry_register)
        self.btn_registry_edit.clicked.connect(self._on_registry_edit)
        self.btn_registry_remove.clicked.connect(self._on_registry_remove)

        self._load_initial()

    def _load_initial(self):
        s = self.initial_settings
        try:
            self.inp_registry_db.setText(s.get("registry_db", "") or "")
            for rp in s.get("recent_projects", [])[:10]:
                self.lst_recent.addItem(rp)
        except Exception:
            pass
        self._refresh_registry_list()

    def _browse_registry_db(self):
        fname, _ = QFileDialog.getOpenFileName(
            self,
            "选择 registry 数据库",
            ".",
            "SQLite Files (*.sqlite *.db);;All Files (*)",
        )
        if fname:
            self.inp_registry_db.setText(fname)
            self._refresh_registry_list()

    def _browse_format_file(self):
        fname, _ = QFileDialog.getOpenFileName(
            self, "选择 format JSON", ".", "JSON Files (*.json);;All Files (*)"
        )
        if fname:
            self.inp_registry_format.setText(fname)

    def _refresh_registry_list(self):
        dbp = self.inp_registry_db.text().strip()
        self.lst_registry.clear()
        if not dbp:
            self.lst_registry.addItem("(未选择 registry)")
            return
        try:
            mappings = list_mappings(dbp)
            if not mappings:
                self.lst_registry.addItem("(空)")
            else:
                for m in mappings:
                    self.lst_registry.addItem(
                        f"[{m['id']}] {m['pattern']} -> {m['format_path']}"
                    )
        except Exception as e:
            self.lst_registry.addItem(f"无法读取 registry: {e}")

    def _on_registry_register(self):
        dbp = self.inp_registry_db.text().strip()
        pat = self.inp_registry_pattern.text().strip()
        fmt = self.inp_registry_format.text().strip()
        if not dbp:
            QMessageBox.warning(self, "错误", "请先选择 registry 数据库文件")
            return
        if not pat or not fmt:
            QMessageBox.warning(self, "错误", "请填写 pattern 与 format 文件路径")
            return
        try:
            register_mapping(dbp, pat, fmt)
            QMessageBox.information(self, "已注册", f"{pat} -> {fmt}")
            self._refresh_registry_list()
        except Exception as e:
            QMessageBox.critical(self, "注册失败", str(e))

    def _on_registry_edit(self):
        QMessageBox.information(self, "提示", "请在主界面中编辑后再注册（简化实现）")

    def _on_registry_remove(self):
        dbp = self.inp_registry_db.text().strip()
        sel = self.lst_registry.selectedItems()
        if not dbp or not sel:
            QMessageBox.warning(self, "错误", "请先选择 registry 与项目")
            return
        text = sel[0].text()
        try:
            if text.startswith("["):
                end = text.find("]")
                mapping_id = int(text[1:end])
            else:
                raise ValueError("无法解析选中项 ID")
            resp = QMessageBox.question(
                self,
                "确认删除",
                f"确认删除映射 id={mapping_id}?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if resp != QMessageBox.Yes:
                return
            delete_mapping(dbp, mapping_id)
            self._refresh_registry_list()
        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))

    def get_settings(self) -> dict:
        return {
            "registry_db": self.inp_registry_db.text().strip(),
            "recent_projects": [
                self.lst_recent.item(i).text() for i in range(self.lst_recent.count())
            ],
        }
