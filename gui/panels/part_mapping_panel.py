"""
Part 映射面板 - 集中管理文件的 Source/Target Part 选择
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.special_format_detector import looks_like_special_format
from src.special_format_parser import get_part_names

logger = logging.getLogger(__name__)


class PartMappingPanel(QGroupBox):
    """集中管理文件 Source/Target Part 选择的面板"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("文件部件映射", parent)
        self.setMinimumWidth(440)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("集中管理 Source/Target Part 映射")
        try:
            title.setObjectName("panelTitle")
        except Exception:
            pass
        layout.addWidget(title)

        self.mapping_tree = QTreeWidget()
        self.mapping_tree.setColumnCount(4)
        self.mapping_tree.setHeaderLabels(
            ["文件/部件", "Source Part", "Target Part", "状态"]
        )
        self.mapping_tree.setAlternatingRowColors(True)
        self.mapping_tree.setRootIsDecorated(True)
        self.mapping_tree.setUniformRowHeights(True)
        self.mapping_tree.setExpandsOnDoubleClick(True)
        self.mapping_tree.setIndentation(16)
        try:
            self.mapping_tree.setMinimumHeight(240)
        except Exception:
            pass
        try:
            self.mapping_tree.setStyleSheet("QTreeWidget::item { height: 22px; }")
        except Exception:
            pass
        try:
            self.mapping_tree.setObjectName("partMappingTree")
        except Exception:
            pass
        try:
            header = self.mapping_tree.header()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            self.mapping_tree.setColumnWidth(1, 140)
            self.mapping_tree.setColumnWidth(2, 140)
            self.mapping_tree.setColumnWidth(3, 140)
        except Exception:
            pass

        layout.addWidget(self.mapping_tree, 1)

    def refresh_from_manager(self, manager) -> None:
        """从 BatchManager 刷新映射列表"""
        try:
            self.mapping_tree.clear()
            files = self._collect_files(manager)
            if not files:
                return

            source_names = manager._get_source_part_names()
            target_names = manager._get_target_part_names()

            # 获取默认的 Source/Target Part（用于尚无选择的文件）
            default_source = self._get_default_part("source", manager, source_names)
            default_target = self._get_default_part("target", manager, target_names)

            for file_path in files:
                try:
                    file_item = QTreeWidgetItem([str(file_path.name), "", "", ""])
                    file_item.setData(0, int(Qt.UserRole) + 1, {"file": str(file_path)})
                    self.mapping_tree.addTopLevelItem(file_item)

                    try:
                        status_text = manager._validate_file_config(file_path)
                        file_item.setText(3, status_text)
                    except Exception:
                        pass

                    if looks_like_special_format(file_path):
                        self._populate_special_file(
                            manager,
                            file_item,
                            file_path,
                            source_names,
                            target_names,
                            default_source,
                            default_target,
                        )
                    else:
                        self._populate_regular_file(
                            manager,
                            file_item,
                            file_path,
                            source_names,
                            target_names,
                            default_source,
                            default_target,
                        )
                    file_item.setExpanded(True)
                except Exception:
                    logger.debug("填充映射行失败: %s", file_path, exc_info=True)
        except Exception:
            logger.debug("刷新映射面板失败", exc_info=True)

    def _collect_files(self, manager) -> list:
        files = []
        try:
            items = getattr(manager.gui, "_file_tree_items", {}) or {}
            for fp_str in items.keys():
                try:
                    files.append(Path(fp_str))
                except Exception:
                    continue
        except Exception:
            logger.debug("读取文件列表失败", exc_info=True)
        return sorted({f for f in files if f.exists()})

    def _get_default_part(
        self, kind: str, manager, available_names: list
    ) -> Optional[str]:
        """获取默认的 Source/Target Part（优先级：Panel选择 > 配置中的第一个 > None）"""
        try:
            # 优先从面板中读取当前选择
            if kind == "source":
                panel = getattr(manager.gui, "source_panel", None)
            else:
                panel = getattr(manager.gui, "target_panel", None)

            if panel is not None:
                try:
                    selector = getattr(panel, "part_selector", None)
                    if selector is not None:
                        current_text = (selector.currentText() or "").strip()
                        if current_text and current_text in (available_names or []):
                            return current_text
                except Exception:
                    logger.debug(f"从 {kind}_panel 读取选择失败", exc_info=True)

            # 回退：使用配置中的第一个部件
            if available_names:
                return str(available_names[0])
        except Exception:
            logger.debug(f"获取默认 {kind} part 失败", exc_info=True)
        return None

    def _populate_regular_file(
        self,
        manager,
        file_item: QTreeWidgetItem,
        file_path: Path,
        source_names: list,
        target_names: list,
        default_source: Optional[str] = None,
        default_target: Optional[str] = None,
    ) -> None:
        try:
            sel = manager._ensure_file_part_selection_storage(file_path)

            # 智能推测（文件名推测）
            try:
                stem = file_path.stem
                if not (sel.get("source") or "").strip() and source_names:
                    inferred_s = manager._infer_part_from_text(stem, source_names)
                    if inferred_s:
                        sel["source"] = inferred_s
                if not (sel.get("target") or "").strip() and target_names:
                    inferred_t = manager._infer_part_from_text(stem, target_names)
                    if inferred_t:
                        sel["target"] = inferred_t
            except Exception:
                pass

            # 如果文件还没有选择，则使用传入的默认值
            if not (sel.get("source") or "").strip() and default_source:
                sel["source"] = default_source
            if not (sel.get("target") or "").strip() and default_target:
                sel["target"] = default_target

            source_combo = self._create_part_combo(
                "(选择source)", source_names, sel.get("source")
            )
            target_combo = self._create_part_combo(
                "(选择target)", target_names, sel.get("target")
            )

            source_combo.currentTextChanged.connect(
                lambda text, fp=str(file_path): self._on_regular_changed(
                    manager, fp, "source", text
                )
            )
            target_combo.currentTextChanged.connect(
                lambda text, fp=str(file_path): self._on_regular_changed(
                    manager, fp, "target", text
                )
            )

            self.mapping_tree.setItemWidget(file_item, 1, source_combo)
            self.mapping_tree.setItemWidget(file_item, 2, target_combo)

            # 确保默认值已被正式保存到字典
            if sel.get("source"):
                self._on_regular_changed(
                    manager, str(file_path), "source", sel.get("source")
                )
            if sel.get("target"):
                self._on_regular_changed(
                    manager, str(file_path), "target", sel.get("target")
                )
        except Exception:
            logger.debug("填充常规文件映射失败", exc_info=True)

    def _populate_special_file(
        self,
        manager,
        file_item: QTreeWidgetItem,
        file_path: Path,
        source_names: list,
        target_names: list,
        default_source: Optional[str] = None,
        default_target: Optional[str] = None,
    ) -> None:
        try:
            part_names = get_part_names(file_path)
            mapping = manager._get_or_init_special_mapping(file_path)

            try:
                if source_names and target_names:
                    manager._auto_fill_special_mappings(
                        file_path, part_names, source_names, target_names, mapping
                    )
            except Exception:
                logger.debug("自动补全映射失败", exc_info=True)

            for part_name in part_names:
                part_name = str(part_name)
                if part_name not in mapping:
                    mapping[part_name] = {"source": "", "target": ""}
                part_mapping = mapping.get(part_name, {})

                # 如果没有显式映射，则使用传入的默认值
                if not (part_mapping.get("source") or "").strip() and default_source:
                    part_mapping["source"] = default_source
                if not (part_mapping.get("target") or "").strip() and default_target:
                    part_mapping["target"] = default_target

                child = QTreeWidgetItem([part_name, "", "", ""])
                file_item.addChild(child)

                source_combo = self._create_part_combo(
                    "(选择source)", source_names, part_mapping.get("source")
                )
                target_combo = self._create_part_combo(
                    "(选择target)", target_names, part_mapping.get("target")
                )

                source_combo.currentTextChanged.connect(
                    lambda text, fp=str(
                        file_path
                    ), internal=part_name: self._on_special_changed(
                        manager, fp, internal, "source", text
                    )
                )
                target_combo.currentTextChanged.connect(
                    lambda text, fp=str(
                        file_path
                    ), internal=part_name: self._on_special_changed(
                        manager, fp, internal, "target", text
                    )
                )

                self.mapping_tree.setItemWidget(child, 1, source_combo)
                self.mapping_tree.setItemWidget(child, 2, target_combo)

                # 确保默认值已被正式保存到字典
                if part_mapping.get("source"):
                    self._on_special_changed(
                        manager,
                        str(file_path),
                        part_name,
                        "source",
                        part_mapping.get("source"),
                    )
                if part_mapping.get("target"):
                    self._on_special_changed(
                        manager,
                        str(file_path),
                        part_name,
                        "target",
                        part_mapping.get("target"),
                    )
        except Exception:
            logger.debug("填充特殊文件映射失败", exc_info=True)

    def _create_part_combo(
        self, placeholder: str, names: list, current_value: Optional[str]
    ) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(False)
        combo.setMinimumWidth(150)
        combo.addItem(placeholder, "")
        for name in names or []:
            combo.addItem(str(name), str(name))

        if not names:
            combo.setEnabled(False)
            combo.setToolTip("请先加载配置以获得部件列表")
        else:
            combo.setEnabled(True)

        try:
            combo.blockSignals(True)
            if current_value and current_value in (names or []):
                combo.setCurrentText(str(current_value))
            else:
                combo.setCurrentIndex(0)
        finally:
            try:
                combo.blockSignals(False)
            except Exception:
                pass

        return combo

    def _on_regular_changed(self, manager, fp_str: str, key: str, text: str) -> None:
        try:
            d = (
                getattr(manager.gui, "file_part_selection_by_file", {}) or {}
            ).setdefault(fp_str, {"source": "", "target": ""})
            d[key] = (text or "").strip()
            self._mark_modified(manager)
            self._refresh_status(manager, fp_str)
        except Exception:
            logger.debug("更新常规文件映射失败", exc_info=True)

    def _on_special_changed(
        self, manager, fp_str: str, internal: str, key: str, text: str
    ) -> None:
        try:
            tmp = getattr(manager.gui, "special_part_mapping_by_file", {}) or {}
            m = tmp.setdefault(fp_str, {})
            if internal not in m:
                m[internal] = {"source": "", "target": ""}
            m[internal][key] = (text or "").strip()
            self._mark_modified(manager)
            self._refresh_status(manager, fp_str)
        except Exception:
            logger.debug("更新特殊文件映射失败", exc_info=True)

    def _mark_modified(self, manager) -> None:
        try:
            if (
                hasattr(manager.gui, "ui_state_manager")
                and manager.gui.ui_state_manager
            ):
                manager.gui.ui_state_manager.mark_operation_performed()
        except Exception:
            logger.debug("标记未保存状态失败（非致命）", exc_info=True)

    def _refresh_status(self, manager, fp_str: str) -> None:
        try:
            file_path = Path(fp_str)
            status_text = manager._validate_file_config(file_path)
            # 更新映射面板中的状态列
            for i in range(self.mapping_tree.topLevelItemCount()):
                item = self.mapping_tree.topLevelItem(i)
                if not item:
                    continue
                meta = item.data(0, int(Qt.UserRole) + 1) or {}
                if meta.get("file") == fp_str:
                    item.setText(3, status_text)
                    break
            # 同步更新文件树的状态列
            try:
                node = getattr(manager.gui, "_file_tree_items", {}).get(fp_str)
                if node is not None:
                    node.setText(1, status_text)
            except Exception:
                pass
        except Exception:
            logger.debug("刷新状态失败", exc_info=True)
