"""子模块：`batch_manager_files` — 承担 `BatchManager` 的文件扫描与文件树填充相关 helper。

这些函数使用 `manager` 作为第一个参数（`BatchManager` 实例），以便于逐步将方法从原模块迁移到独立模块，迁移期间保持兼容性。
"""

# 临时抑制行过长（将逐步清理长行）
# pylint: disable=line-too-long, import-outside-toplevel, reimported

import fnmatch
import logging
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem

from src.cli_helpers import BatchConfig, resolve_file_format
from src.file_cache import get_file_cache
from src.special_format_detector import looks_like_special_format
from src.special_format_parser import get_part_names

logger = logging.getLogger(__name__)


def _collect_files_for_scan(manager, p: Path) -> Tuple[list, Path]:
    """根据路径 `p` 和当前 UI 设置收集匹配的文件列表，返回 (files, base_path)。"""
    files = []
    base_path = p

    try:
        if p.is_file():
            files = [p]
            try:
                manager.gui.output_dir = p.parent
            except Exception:
                pass
            base_path = p.parent
        elif p.is_dir():
            # 使用默认的文件匹配模式（支持所有常见格式）
            pattern_text = "*.csv;*.xlsx;*.xls;*.mtfmt;*.mtdata;*.txt;*.dat"

            patterns = [x.strip() for x in pattern_text.split(";") if x.strip()]
            if not patterns:
                patterns = ["*.csv"]

            for file_path in p.rglob("*"):
                if not file_path.is_file():
                    continue
                if any(fnmatch.fnmatch(file_path.name, pat) for pat in patterns):
                    files.append(file_path)
            files = sorted(set(files))

            try:
                manager.gui.output_dir = p
            except Exception:
                pass

            base_path = p

    except Exception:
        logger.debug("收集文件失败", exc_info=True)

    return files, base_path


def _populate_file_tree_from_files(manager, files, base_path, p: Path) -> None:
    """根据 files 填充 `manager.gui.file_tree` 并显示文件列表区域。"""
    dir_items = {}
    for fp in files:
        _safe_add_file_tree_entry(manager, base_path, dir_items, fp, p.is_file())

    try:
        manager.gui.file_tree.expandAll()
    except Exception:
        pass

    try:
        manager.gui.file_list_widget.setVisible(True)
    except Exception:
        pass

    logger.info(f"已扫描到 {len(files)} 个文件")


def _safe_add_file_tree_entry(
    manager, base_path: Path, dir_items: dict, fp: Path, single_file_mode: bool
) -> None:
    """安全地调用 `_add_file_tree_entry` 并在发生异常时记录调试信息。"""
    try:
        try:
            _add_file_tree_entry(manager, base_path, dir_items, fp, single_file_mode)
        except Exception:
            logger.debug("添加文件树项失败（外层）", exc_info=True)
    except Exception:
        logger.debug("_safe_add_file_tree_entry 内部错误", exc_info=True)


def _add_file_tree_entry(
    manager, base_path: Path, dir_items: dict, fp: Path, single_file_mode: bool
) -> None:
    """将单个文件添加到文件树，包含目录节点构建与状态校验。"""
    try:
        try:
            rel_path = fp.relative_to(base_path)
        except ValueError:
            rel_path = fp

        parts = rel_path.parts[:-1]
        parent_item = None
        current_path = Path()

        for part in parts:
            current_path = current_path / part
            if current_path not in dir_items:
                dir_item = QTreeWidgetItem([str(part), ""])
                dir_item.setData(0, Qt.UserRole, None)
                if parent_item is None:
                    manager.gui.file_tree.addTopLevelItem(dir_item)
                else:
                    parent_item.addChild(dir_item)
                dir_items[current_path] = dir_item
                parent_item = dir_item
            else:
                parent_item = dir_items[current_path]

        file_item = QTreeWidgetItem([rel_path.name, ""])
        file_item.setCheckState(0, Qt.Checked)
        file_item.setData(0, Qt.UserRole, str(fp))

        if single_file_mode:
            try:
                file_item.setCheckState(0, Qt.Checked)
                flags = file_item.flags()
                file_item.setFlags(flags & ~Qt.ItemIsUserCheckable)
                try:
                    file_item.setToolTip(0, "单文件模式，无法修改选择状态")
                except Exception:
                    pass
            except Exception:
                pass

        # 访问 BatchManager 的受保护方法以复用验证逻辑（短期抑制）
        # pylint: disable=protected-access
        status_text = manager._validate_file_config(fp)
        # pylint: enable=protected-access
        file_item.setText(1, status_text)

        if parent_item is None:
            manager.gui.file_tree.addTopLevelItem(file_item)
        else:
            parent_item.addChild(file_item)

        # 访问 GUI 的受保护属性以维护文件树映射。
        # pylint: disable=protected-access
        manager.gui._file_tree_items[str(fp)] = file_item
        # pylint: enable=protected-access
    except Exception:
        logger.debug("添加文件树项失败", exc_info=True)


def _ensure_file_part_selection_storage(manager, file_path: Path) -> dict:
    """确保常规文件的 source/target 选择缓存存在。"""
    try:
        if not hasattr(manager.gui, "file_part_selection_by_file"):
            manager.gui.file_part_selection_by_file = {}
        by_file = getattr(manager.gui, "file_part_selection_by_file", {}) or {}
        by_file.setdefault(str(file_path), {"source": "", "target": ""})
        manager.gui.file_part_selection_by_file = by_file
        return by_file[str(file_path)]
    except Exception:
        return {"source": "", "target": ""}


def _remove_old_selector_children(manager, file_item) -> None:
    """移除文件节点中已存在的 source/target selector 子节点。"""
    for i in range(file_item.childCount() - 1, -1, -1):
        try:
            child = file_item.child(i)
            # 访问 BatchManager 的受保护方法以解析 item 元数据（短期抑制）
            # pylint: disable=protected-access
            meta = manager._get_item_meta(child)
            # pylint: enable=protected-access
            if isinstance(meta, dict) and meta.get("kind") in (
                "file_source_selector",
                "file_target_selector",
            ):
                file_item.removeChild(child)
        except Exception:
            pass


def _collect_files_to_process(manager, input_path: Path):
    """根据输入路径和 GUI 当前选择收集要处理的文件列表。

    返回 (files_list, output_dir_or_none, error_message_or_none)
    """
    try:
        files_to_process = []
        output_dir = getattr(manager.gui, "output_dir", None)

        if input_path.is_file():
            files_to_process = [input_path]
            if output_dir is None:
                output_dir = input_path.parent
            return files_to_process, output_dir, None

        if input_path.is_dir():
            # 优先使用 GUI 的树形选择（若存在）
            if hasattr(manager.gui, "file_tree") and hasattr(
                manager.gui, "_file_tree_items"
            ):
                files_to_process.extend(_collect_files_for_scan(manager, input_path)[0])
                if output_dir is None:
                    output_dir = input_path
            else:
                get_patterns = getattr(manager, "_get_patterns_from_widget", None)
                if callable(get_patterns):
                    patterns, _ = get_patterns()
                else:
                    patterns, _ = ([], "*.csv")
                files_to_process.extend(
                    _scan_dir_for_patterns(manager, input_path, patterns)
                )
                if output_dir is None:
                    output_dir = input_path

            if not files_to_process:
                get_patterns = getattr(manager, "_get_patterns_from_widget", None)
                if callable(get_patterns):
                    _, pattern_display = get_patterns()
                else:
                    pattern_display = "*.csv"
                msg = f"未找到匹配 '{pattern_display}' 的文件或未选择任何文件"
                return [], None, msg
            return files_to_process, output_dir, None

        return [], None, "输入路径无效"
    except Exception:
        logger.debug("收集待处理文件失败", exc_info=True)
        return [], None, "收集待处理文件时发生错误"


def _scan_dir_for_patterns(manager, input_path: Path, patterns: list) -> list:
    """扫描目录并返回匹配指定模式的文件路径列表。"""
    found = []
    try:
        for file_path in input_path.rglob("*"):
            try:
                if not file_path.is_file():
                    continue
                if any(fnmatch.fnmatch(file_path.name, pat) for pat in patterns):
                    found.append(file_path)
            except Exception:
                pass
    except Exception:
        logger.debug("按模式扫描目录失败", exc_info=True)
    return found


def _ensure_regular_file_selector_rows(manager, file_item, file_path: Path) -> None:
    """为常规文件创建 source/target 选择行（并排双下拉，与特殊格式统一）。"""
    from PySide6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QTreeWidgetItem
    
    try:
        sel = _ensure_file_part_selection_storage(manager, file_path)
        source_names = manager._get_source_part_names()
        target_names = manager._get_target_part_names()

        # 智能推测：首次进入时，尝试用文件名推测
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

        # 清理旧的 selector 子节点（避免重复）
        _remove_old_selector_children(manager, file_item)

        # 创建一个包含并排双下拉的节点
        selector_item = QTreeWidgetItem(["", ""])
        selector_item.setData(0, int(Qt.UserRole) + 1, {"kind": "file_part_selectors", "file": str(file_path)})
        file_item.addChild(selector_item)
        
        # 创建容器widget
        selector_widget = QWidget()
        selector_layout = QHBoxLayout(selector_widget)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(4)
        
        # Source部分选择器
        current_src = (sel.get("source") or "").strip()
        source_combo = QComboBox()
        source_combo.setEditable(False)
        source_combo.setMinimumWidth(140)
        source_combo.addItem("(选择source)", "")
        for sn in source_names:
            source_combo.addItem(str(sn), str(sn))
        
        if not source_names:
            source_combo.setEnabled(False)
            source_combo.setToolTip("请先加载配置以获得 Source parts")
        else:
            source_combo.setEnabled(True)
            source_combo.setToolTip("选择该文件对应的 Source part")
        
        _safe_set_combo_selection(manager, source_combo, current_src, source_names)
        
        # Target部分选择器
        current_tgt = (sel.get("target") or "").strip()
        target_combo = QComboBox()
        target_combo.setEditable(False)
        target_combo.setMinimumWidth(140)
        target_combo.addItem("(选择target)", "")
        for tn in target_names:
            target_combo.addItem(str(tn), str(tn))
        
        if not target_names:
            target_combo.setEnabled(False)
            target_combo.setToolTip("请先加载配置以获得 Target parts")
        else:
            target_combo.setEnabled(True)
            target_combo.setToolTip("选择该文件对应的 Target part")
        
        _safe_set_combo_selection(manager, target_combo, current_tgt, target_names)
        
        # 绑定source改变事件
        src_handler = manager._make_part_change_handler(str(file_path), "source")
        source_combo.currentTextChanged.connect(src_handler)
        
        # 绑定target改变事件
        tgt_handler = manager._make_part_change_handler(str(file_path), "target")
        target_combo.currentTextChanged.connect(tgt_handler)
        
        selector_layout.addWidget(source_combo, 1)
        selector_layout.addWidget(target_combo, 1)
        
        manager.gui.file_tree.setItemWidget(selector_item, 0, selector_widget)

        try:
            file_item.setExpanded(True)
        except Exception:
            pass
    except Exception:
        logger.debug("_ensure_regular_file_selector_rows failed", exc_info=True)


def _infer_source_part(manager, part_name: str, source_names: list) -> Optional[str]:
    """智能推测source part（内部部件名与配置中的source part对应关系）。
    
    策略：
    1. 在source_names中查找同名的
    2. 不区分大小写查找
    3. 若找不到，默认返回"Global"（如果存在的话）
    """
    result = None
    try:
        pn = (part_name or "").strip()
        if pn:
            sns = [str(x) for x in (source_names or []) if str(x).strip()]
            if sns:
                # 策略1：完全匹配
                if pn in sns:
                    result = pn
                else:
                    # 策略2：不区分大小写
                    pn_lower = pn.lower()
                    ci = [s for s in sns if s.lower() == pn_lower]
                    if len(ci) == 1:
                        result = ci[0]
                    else:
                        # 策略3：移除特殊字符后比较
                        def norm(s: str) -> str:
                            try:
                                s2 = "".join(
                                    ch
                                    for ch in (s or "")
                                    if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff")
                                )
                                return s2.lower()
                            except Exception:
                                return (s or "").lower()

                        pn_norm = norm(pn)
                        if pn_norm:
                            nm = [s for s in sns if norm(s) == pn_norm]
                            if len(nm) == 1:
                                result = nm[0]
                # 策略4：未找到则默认选择"Global"
                if result is None and "Global" in sns:
                    result = "Global"
    except Exception:
        logger.debug("推测 source part 失败", exc_info=True)
        result = None
    return result


def _infer_target_part(manager, source_part: str, target_names: list) -> Optional[str]:
    """智能推测 source->target 映射。"""
    result = None
    try:
        sp = (source_part or "").strip()
        if sp:
            tns = [str(x) for x in (target_names or []) if str(x).strip()]
            if tns:
                if sp in tns:
                    result = sp
                else:
                    sp_lower = sp.lower()
                    ci = [t for t in tns if t.lower() == sp_lower]
                    if len(ci) == 1:
                        result = ci[0]
                    else:

                        def norm(s: str) -> str:
                            try:
                                s2 = "".join(
                                    ch
                                    for ch in (s or "")
                                    if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff")
                                )
                                return s2.lower()
                            except Exception:
                                return (s or "").lower()

                        sp_norm = norm(sp)
                        if sp_norm:
                            nm = [t for t in tns if norm(t) == sp_norm]
                            if len(nm) == 1:
                                result = nm[0]
    except Exception:
        logger.debug("推测 target part 失败", exc_info=True)
        result = None
    return result


def _make_part_change_handler(manager, fp_str: str, key: str):
    def _handler(text: str):
        try:
            d = (
                getattr(manager.gui, "file_part_selection_by_file", {}) or {}
            ).setdefault(fp_str, {"source": "", "target": ""})
            d[key] = (text or "").strip()
            try:
                node = getattr(manager.gui, "_file_tree_items", {}).get(fp_str)
                if node is not None:
                    node.setText(1, manager._validate_file_config(Path(fp_str)))
            except Exception:
                pass
        except Exception:
            logger.debug(f"更新文件 {key} 选择失败", exc_info=True)

    return _handler


def _auto_fill_special_mappings(
    manager, file_path: Path, part_names: list, source_names: list, target_names: list, mapping: dict
) -> bool:
    """自动推断并填充特殊格式文件的内部部件->source部件->target部件映射。
    
    mapping结构：
    {
        "internal_part_name": {
            "source": "配置中的Source Part",
            "target": "配置中的Target Part"  
        }
    }
    
    策略：
    1. 为每个内部部件名推断对应的source part（查找配置中的同名，未找到则用"Global"）
    2. 为每个source part推断对应的target part（查找配置中的同名）
    """
    changed = False
    try:
        if mapping is None or not isinstance(mapping, dict):
            return False
        
        for part_name in part_names or []:
            part_name = str(part_name)
            
            # 初始化该部件的映射
            if part_name not in mapping:
                mapping[part_name] = {"source": "", "target": ""}
                changed = True
            
            # 步骤1：推断source part
            if not (mapping[part_name].get("source") or "").strip():
                inferred_source = _infer_source_part(manager, part_name, source_names)
                if inferred_source:
                    mapping[part_name]["source"] = inferred_source
                    changed = True
            
            # 步骤2：推断target part（基于已有或推断的source part）
            if not (mapping[part_name].get("target") or "").strip():
                source_part = mapping[part_name].get("source", "").strip()
                if source_part:
                    inferred_target = _infer_target_part(manager, source_part, target_names)
                    if inferred_target:
                        mapping[part_name]["target"] = inferred_target
                        changed = True
    except Exception:
        logger.debug("自动补全映射失败", exc_info=True)
    return changed


def _get_or_init_special_mapping(manager, file_path: Path) -> dict:
    try:
        mapping_by_file = getattr(manager.gui, "special_part_mapping_by_file", None)
        if mapping_by_file is None:
            manager.gui.special_part_mapping_by_file = {}
            mapping_by_file = manager.gui.special_part_mapping_by_file
        mapping_by_file.setdefault(str(file_path), {})
        mapping = mapping_by_file[str(file_path)]
        return mapping
    except Exception:
        logger.debug("获取或初始化 special mapping 失败", exc_info=True)
        return {}


def _create_part_mapping_combo(
    manager, file_path: Path, source_part, target_names: list, mapping: dict
):
    from PySide6.QtWidgets import QComboBox

    combo = QComboBox(manager.gui.file_tree)
    combo.setEditable(False)
    combo.setMinimumWidth(160)
    combo.addItem("（未选择）", "")
    for tn in target_names:
        combo.addItem(tn, tn)

    if not target_names:
        combo.setEnabled(False)
        combo.setToolTip("请先加载配置或创建 Target Part")
    else:
        combo.setEnabled(True)
        combo.setToolTip("选择该 Source part 对应的 Target part")

    current = (mapping or {}).get(source_part) or ""
    _safe_set_combo_selection(manager, combo, current, target_names)

    def _on_changed(text: str, *, fp_str=str(file_path), sp=str(source_part)):
        try:
            tmp = getattr(manager.gui, "special_part_mapping_by_file", {}) or {}
            m = tmp.setdefault(fp_str, {})
            val = (text or "").strip()
            if not val or val == "（未选择）":
                m.pop(sp, None)
            else:
                m[sp] = val
            try:
                tmp_items = getattr(manager.gui, "_file_tree_items", {}) or {}
                file_node = tmp_items.get(fp_str)
                if file_node is not None:
                    file_node.setText(1, manager._validate_file_config(Path(fp_str)))
            except Exception:
                pass
        except Exception:
            logger.debug("special mapping changed handler failed", exc_info=True)

    combo.currentTextChanged.connect(_on_changed)
    return combo


def _safe_set_combo_selection(manager, combo, current, names):
    try:
        combo.blockSignals(True)
        if current and current in (names or []):
            combo.setCurrentText(current)
        else:
            combo.setCurrentIndex(0)
    finally:
        try:
            combo.blockSignals(False)
        except Exception:
            pass


def _create_special_part_node(
    manager,
    file_item,
    file_path: Path,
    internal_part_name: str,
    source_names: list,
    target_names: list,
    mapping: dict,
    data_dict: dict,
) -> None:
    """为特殊格式文件的每个内部部件创建一个节点，包含source和target两个选择器。
    
    布局：
    第1行：内部部件名 | (空)
    第2行：(选择source) | (选择target)
    第3行：数据预览表格
    """
    from PySide6.QtWidgets import QTreeWidgetItem, QWidget, QHBoxLayout, QComboBox

    try:
        internal_part_name = str(internal_part_name)
        
        # 确保mapping中有该部件的数据结构
        if internal_part_name not in mapping:
            mapping[internal_part_name] = {"source": "", "target": ""}
        
        part_mapping = mapping[internal_part_name]
        
        # 创建部件名节点
        part_item = QTreeWidgetItem([internal_part_name, ""])
        part_item.setData(
            0,
            int(Qt.UserRole) + 1,
            {
                "kind": "special_part",
                "file": str(file_path),
                "internal_name": internal_part_name,
            },
        )
        file_item.addChild(part_item)
        
        # 创建source和target选择器行
        selector_item = QTreeWidgetItem(["", ""])
        selector_item.setData(0, int(Qt.UserRole) + 1, {"kind": "special_part_selectors"})
        part_item.addChild(selector_item)
        
        # 创建一个容器widget来放置两个下拉框
        selector_widget = QWidget()
        selector_layout = QHBoxLayout(selector_widget)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(4)
        
        # Source部分选择器
        source_combo = QComboBox()
        source_combo.setEditable(False)
        source_combo.setMinimumWidth(140)
        source_combo.addItem("(选择source)", "")
        for sn in source_names:
            source_combo.addItem(str(sn), str(sn))
        
        if not source_names:
            source_combo.setEnabled(False)
            source_combo.setToolTip("请先加载配置以获得 Source parts")
        else:
            source_combo.setEnabled(True)
            source_combo.setToolTip("选择该部件对应的 Source part")
        
        current_source = (part_mapping.get("source") or "").strip()
        _safe_set_combo_selection(manager, source_combo, current_source, source_names)
        
        # Target部分选择器
        target_combo = QComboBox()
        target_combo.setEditable(False)
        target_combo.setMinimumWidth(140)
        target_combo.addItem("(选择target)", "")
        for tn in target_names:
            target_combo.addItem(str(tn), str(tn))
        
        if not target_names:
            target_combo.setEnabled(False)
            target_combo.setToolTip("请先加载配置以获得 Target parts")
        else:
            target_combo.setEnabled(True)
            target_combo.setToolTip("选择该 Source part 对应的 Target part")
        
        current_target = (part_mapping.get("target") or "").strip()
        _safe_set_combo_selection(manager, target_combo, current_target, target_names)
        
        # 绑定source改变事件
        def _on_source_changed(text: str, *, fp_str=str(file_path), internal=internal_part_name):
            try:
                tmp = getattr(manager.gui, "special_part_mapping_by_file", {}) or {}
                m = tmp.setdefault(fp_str, {})
                if internal not in m:
                    m[internal] = {"source": "", "target": ""}
                val = (text or "").strip()
                if not val or val == "(选择source)":
                    m[internal]["source"] = ""
                else:
                    m[internal]["source"] = val
                try:
                    tmp_items = getattr(manager.gui, "_file_tree_items", {}) or {}
                    file_node = tmp_items.get(fp_str)
                    if file_node is not None:
                        file_node.setText(1, manager._validate_file_config(Path(fp_str)))
                except Exception:
                    pass
            except Exception:
                logger.debug("source part changed handler failed", exc_info=True)
        
        # 绑定target改变事件
        def _on_target_changed(text: str, *, fp_str=str(file_path), internal=internal_part_name):
            try:
                tmp = getattr(manager.gui, "special_part_mapping_by_file", {}) or {}
                m = tmp.setdefault(fp_str, {})
                if internal not in m:
                    m[internal] = {"source": "", "target": ""}
                val = (text or "").strip()
                if not val or val == "(选择target)":
                    m[internal]["target"] = ""
                else:
                    m[internal]["target"] = val
                try:
                    tmp_items = getattr(manager.gui, "_file_tree_items", {}) or {}
                    file_node = tmp_items.get(fp_str)
                    if file_node is not None:
                        file_node.setText(1, manager._validate_file_config(Path(fp_str)))
                except Exception:
                    pass
            except Exception:
                logger.debug("target part changed handler failed", exc_info=True)
        
        source_combo.currentTextChanged.connect(_on_source_changed)
        target_combo.currentTextChanged.connect(_on_target_changed)
        
        selector_layout.addWidget(source_combo, 1)
        selector_layout.addWidget(target_combo, 1)
        
        manager.gui.file_tree.setItemWidget(selector_item, 0, selector_widget)
        
        # 缓存combo引用
        key = (str(file_path), internal_part_name)
        if not hasattr(manager, "_special_part_source_combo"):
            manager._special_part_source_combo = {}
        if not hasattr(manager, "_special_part_target_combo"):
            manager._special_part_target_combo = {}
        manager._special_part_source_combo[key] = source_combo
        manager._special_part_target_combo[key] = target_combo
        
        # 填充数据预览
        manager._safe_populate_special_preview(part_item, file_path, internal_part_name, data_dict)
        
    except Exception:
        logger.debug("创建 special part 节点失败（内部）", exc_info=True)


def _get_format_info(manager, file_path: Path):
    """从缓存或解析器获取文件格式信息，若未知返回 None。"""
    try:
        cache = get_file_cache()
        cached_format = cache.get_metadata(file_path, "format_info")
        if cached_format:
            return cached_format

        base_cfg = BatchConfig()
        base_cfg.skip_rows = 0
        base_cfg.columns = {}
        base_cfg.passthrough = []

        fmt_info = resolve_file_format(str(file_path), base_cfg)
        if fmt_info:
            try:
                cache.set_metadata(file_path, "format_info", fmt_info)
            except Exception:
                pass
        return fmt_info
    except Exception:
        return None


def _get_special_mapping_if_exists(manager, file_path: Path):
    try:
        tmp = getattr(manager.gui, "special_part_mapping_by_file", {}) or {}
        return tmp.get(str(file_path))
    except Exception:
        return None


def _get_project_parts(manager):
    source_parts = {}
    target_parts = {}
    try:
        model = getattr(manager.gui, "project_model", None)
        if model is not None:
            source_parts = getattr(model, "source_parts", {}) or {}
            target_parts = getattr(model, "target_parts", {}) or {}
    except Exception:
        pass
    try:
        cfg = getattr(manager.gui, "current_config", None)
        if cfg is not None:
            source_parts = source_parts or (getattr(cfg, "source_parts", {}) or {})
            target_parts = target_parts or (getattr(cfg, "target_parts", {}) or {})
    except Exception:
        pass
    return source_parts, target_parts


def _validate_special_format(manager, file_path: Path) -> Optional[str]:
    status = None
    try:
        if not looks_like_special_format(file_path):
            status = None
        else:
            part_names = get_part_names(file_path)

            mapping = _get_special_mapping_if_exists(manager, file_path)
            source_parts, target_parts = _get_project_parts(manager)

            if not source_parts and not target_parts:
                status = "✓ 特殊格式(待配置)"
            else:
                missing_source = [pn for pn in part_names if pn not in source_parts]
                if missing_source:
                    status = f"⚠ Source缺失: {', '.join(missing_source)}"
                else:
                    mapping = mapping or {}
                    # reuse manager-side analyze if exists
                    analyze_fn = getattr(manager, "_analyze_special_mapping", None)
                    if callable(analyze_fn):
                        unmapped, missing_target = analyze_fn(
                            part_names, mapping, list(target_parts.keys())
                        )
                    else:
                        unmapped, missing_target = ([], [])

                    if unmapped:
                        status = f"⚠ 未映射: {', '.join(unmapped)}"
                    elif missing_target:
                        status = f"⚠ Target缺失: {', '.join(missing_target)}"
                    else:
                        status = "✓ 特殊格式(可处理)"
    except Exception:
        logger.debug("特殊格式校验失败", exc_info=True)
        status = None
    return status


def _validate_file_config(manager, file_path: Path) -> str:
    status = None
    try:
        try:
            special_status = _validate_special_format(manager, file_path)
        except Exception:
            special_status = None

        if special_status is not None:
            status = special_status
        else:
            fmt_info = _get_format_info(manager, file_path)
            if not fmt_info:
                status = "❌ 未知格式"
            else:
                project_data = getattr(manager.gui, "current_config", None)
                # delegate to manager's non-special evaluator if present
                eval_fn = getattr(manager, "_evaluate_file_config_non_special", None)
                if callable(eval_fn):
                    status = eval_fn(file_path, fmt_info, project_data)
                else:
                    status = "❓ 未验证"
    except Exception:
        logger.debug("验证文件配置失败", exc_info=True)
        status = "❓ 未验证"
    return status or "❓ 未验证"
