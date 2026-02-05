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
from gui.status_message_queue import MessagePriority

logger = logging.getLogger(__name__)


def _collect_checked_files_from_tree(manager) -> list:
    """从文件树收集用户勾选的文件。

    返回勾选的文件路径列表，如果没有勾选项或树不存在则返回空列表。
    """
    checked_files = []
    try:
        if not hasattr(manager.gui, "file_tree") or not hasattr(
            manager.gui, "_file_tree_items"
        ):
            return checked_files

        items_dict = manager.gui._file_tree_items

        # 遍历所有树项，收集勾选的文件
        for path_str, item in items_dict.items():
            try:
                # 检查勾选状态
                if item.checkState(0) == Qt.Checked:
                    # 检查是否为文件项（通过 meta 判断）
                    meta = getattr(item, "_meta", None) or {}
                    if meta.get("kind") == "file":
                        file_path = Path(path_str)
                        if file_path.exists() and file_path.is_file():
                            checked_files.append(file_path)
            except Exception:
                logger.debug("读取树项 %s 勾选状态失败", path_str, exc_info=True)

    except Exception:
        logger.debug("收集文件树勾选项失败", exc_info=True)

    return checked_files


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
                logger.debug(
                    "设置 manager.gui.output_dir 失败（非致命）", exc_info=True
                )
            base_path = p.parent
        elif p.is_dir():
            # 使用默认的文件匹配模式（支持所有常见格式）
            pattern_text = "*.csv;*.xlsx;*.xls;*.mtfmt;*.mtdata;*.txt;*.dat"

            patterns = [x.strip() for x in pattern_text.split(";") if x.strip()]
            if not patterns:
                patterns = ["*.csv"]

            try:
                from gui.signal_bus import SignalBus

                SignalBus.instance().statusMessage.emit(
                    f"正在扫描目录：{p}",
                    0,
                    MessagePriority.MEDIUM,
                )
            except Exception:
                logger.debug("发送扫描提示失败（非致命）", exc_info=True)

            try:
                from PySide6.QtWidgets import QApplication

                tick = 0
                for file_path in p.rglob("*"):
                    if not file_path.is_file():
                        continue
                    if any(fnmatch.fnmatch(file_path.name, pat) for pat in patterns):
                        files.append(file_path)
                    tick += 1
                    if tick % 500 == 0:
                        try:
                            QApplication.processEvents()
                        except Exception:
                            pass
            except Exception:
                logger.debug("目录扫描失败", exc_info=True)

            files = sorted(set(files))

            try:
                manager.gui.output_dir = p
            except Exception:
                logger.debug(
                    "设置 manager.gui.output_dir 为目录失败（非致命）",
                    exc_info=True,
                )

            base_path = p

            try:
                from gui.signal_bus import SignalBus

                SignalBus.instance().statusMessage.emit(
                    f"目录扫描完成：共 {len(files)} 个文件",
                    5000,
                    MessagePriority.MEDIUM,
                )
            except Exception:
                logger.debug("发送扫描完成提示失败（非致命）", exc_info=True)

    except Exception:
        logger.debug("收集文件失败", exc_info=True)

    return files, base_path


def _populate_file_tree_from_files(manager, files, base_path, p: Path) -> None:
    """根据 files 填充 `manager.gui.file_tree` 并显示文件列表区域。"""
    dir_items = {}
    for fp in files:
        _safe_add_file_tree_entry(manager, base_path, dir_items, fp, p.is_file())

    try:
        from PySide6.QtCore import QTimer

        def _expand_tree():
            try:
                manager.gui.file_tree.expandAll()
            except Exception:
                logger.debug("展开文件树失败（非致命）", exc_info=True)
            try:
                from gui.signal_bus import SignalBus

                SignalBus.instance().statusMessage.emit(
                    "文件列表已展开",
                    2000,
                    MessagePriority.LOW,
                )
            except Exception:
                logger.debug("发送展开完成提示失败（非致命）", exc_info=True)

        QTimer.singleShot(0, _expand_tree)
    except Exception:
        logger.debug("调度展开文件树失败（非致命）", exc_info=True)

    try:
        manager.gui.file_list_widget.setVisible(True)
    except Exception:
        logger.debug("设置 file_list_widget 可见性失败（非致命）", exc_info=True)

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
            # 移除旧的 selector 节点（支持旧的 file_source/target 名称与新的 file_part_selectors）
            if isinstance(meta, dict) and meta.get("kind") in (
                "file_source_selector",
                "file_target_selector",
                "file_part_selectors",
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
            # 优先使用 GUI 的树形选择（若存在且有勾选项）
            if hasattr(manager.gui, "file_tree") and hasattr(
                manager.gui, "_file_tree_items"
            ):
                # 尝试收集树中勾选的文件
                checked_files = _collect_checked_files_from_tree(manager)
                if checked_files:
                    # 只使用用户勾选的文件
                    files_to_process.extend(checked_files)
                else:
                    # 没有勾选项则提示用户选择文件，避免误处理整目录
                    get_patterns = getattr(manager, "_get_patterns_from_widget", None)
                    if callable(get_patterns):
                        _, pattern_display = get_patterns()
                    else:
                        pattern_display = "*.csv"
                    msg = (
                        f"未选择任何文件，请在文件列表中勾选后再开始处理。"
                        f"（当前匹配规则: {pattern_display}）"
                    )
                    return [], None, msg
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
                # 如果有文件树，说明是目录扫描模式；否则是树形勾选模式
                if not hasattr(manager.gui, "file_tree"):
                    msg = f"在目录中未找到匹配 '{pattern_display}' 的文件"
                else:
                    msg = f"文件树中未勾选任何文件（当前匹配规则: {pattern_display}）"
                return [], None, msg
            return files_to_process, output_dir, None

        # 路径既不是文件也不是目录
        error_details = ""
        if not input_path.exists():
            error_details = f"路径不存在: {input_path}"
        else:
            try:
                input_path.stat()
                error_details = f"路径无效或无权限访问: {input_path}"
            except PermissionError:
                error_details = f"权限不足，无法访问: {input_path}"
            except Exception as e:
                error_details = f"路径访问失败: {input_path}（{str(e)}）"
        return [], None, error_details
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
    try:
        # 仅清理旧的 selector 子节点（映射已移到集中面板）
        _remove_old_selector_children(manager, file_item)
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
    manager,
    file_path: Path,
    part_names: list,
    source_names: list,
    target_names: list,
    mapping: dict,
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
                    inferred_target = _infer_target_part(
                        manager, source_part, target_names
                    )
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
    from PySide6.QtWidgets import QTreeWidgetItem

    try:
        internal_part_name = str(internal_part_name)

        # 确保mapping中有该部件的数据结构
        if internal_part_name not in mapping:
            mapping[internal_part_name] = {"source": "", "target": ""}

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

        # Source/Target 选择器已移动到集中映射面板

        # 填充数据预览
        manager._safe_populate_special_preview(
            part_item, file_path, internal_part_name, data_dict
        )

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
                # 检查 Source Part 可用性
                missing_source = [pn for pn in part_names if pn not in source_parts]
                if missing_source:
                    # 提供更清晰的错误信息，说明哪个 Part 不可用
                    unavailable = ", ".join(missing_source)
                    status = f"❌ Source缺失: {unavailable}（需在配置中添加）"
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
                        status = f"⚠ 未映射: {', '.join(unmapped)}（需配置映射）"
                    elif missing_target:
                        # 提供更清晰的错误信息，说明哪个 Target Part 不可用
                        unavailable = ", ".join(missing_target)
                        status = f"❌ Target缺失: {unavailable}（需在配置中添加）"
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
