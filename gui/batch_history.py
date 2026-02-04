"""批处理历史侧边栏：持久化记录批处理结果并支持撤销。"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)


class BatchHistoryStore:
    """管理批处理历史的简单持久化存储。"""

    def __init__(self, *, store_path: Optional[Path] = None) -> None:
        import os
        
        # 测试环境检测：使用临时路径避免污染真实历史记录
        is_testing = bool(
            os.getenv("PYTEST_CURRENT_TEST") or 
            os.getenv("TESTING") == "1"
        )
        
        if is_testing:
            # 测试环境：使用临时目录
            import tempfile
            base_dir = Path(tempfile.gettempdir()) / ".momentconversion_test"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.store_path = store_path or base_dir / "batch_history_test.json"
            logger.debug("测试环境：使用临时历史存储路径 %s", self.store_path)
        else:
            # 生产环境：使用用户主目录
            base_dir = Path.home() / ".momentconversion"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.store_path = store_path or base_dir / "batch_history.json"
        
        self.records: List[Dict] = []
        self.redo_stack: List[Dict] = []  # 重做栈：存储被撤销的记录
        self._is_testing = is_testing
        self._load()

    def _load(self) -> None:
        try:
            if self.store_path.exists():
                try:
                    data = json.loads(self.store_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    # 兼容带 BOM 的文件
                    data = json.loads(
                        self.store_path.read_text(encoding="utf-8-sig")
                    )
                if isinstance(data, dict):
                    # 新格式：包含records和redo_stack
                    self.records = data.get("records", [])
                    self.redo_stack = data.get("redo_stack", [])
                elif isinstance(data, list):
                    # 兼容旧格式：仅有records列表
                    self.records = data
                    self.redo_stack = []
        except Exception:
            logger.debug("加载批处理历史失败，使用空记录", exc_info=True)
            self.records = []
            self.redo_stack = []

    def save(self) -> None:
        try:
            # 测试环境下记录到内存即可，不持久化到磁盘（额外保护）
            if getattr(self, "_is_testing", False):
                logger.debug("测试环境：跳过历史记录持久化")
                return
            
            data = {
                "records": self.records,
                "redo_stack": self.redo_stack,
            }
            self.store_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("保存批处理历史到 %s 失败", self.store_path)

    def add_record(
        self,
        *,
        input_path: str,
        output_dir: str,
        files: List[str],
        new_files: List[str],
        status: str = "completed",
        timestamp: Optional[datetime] = None,
        row_selections: Optional[Dict] = None,
        part_mappings: Optional[Dict] = None,
        file_configs: Optional[Dict] = None,
        parent_record_id: Optional[str] = None,
    ) -> Dict:
        """添加批处理记录

        Args:
            input_path: 输入路径
            output_dir: 输出目录
            files: 处理的文件列表
            new_files: 生成的新文件列表
            status: 状态
            timestamp: 时间戳
            row_selections: 数据行选择信息
                {file_path: {part: [row_indices]}}
            part_mappings: Part映射配置
                {file_path: {internal_part: {source: xx, target: yy}}}
            file_configs: 文件配置 {file_path: {source: xx, target: yy}}
            parent_record_id: 父记录 ID（用于树状结构，表示这是某个重做操作的子记录）
        """
        ts = timestamp or datetime.now()
        record = {
            "id": uuid.uuid4().hex,
            "timestamp": ts.isoformat(),
            "input_path": input_path,
            "output_dir": output_dir,
            "files": list(files or []),
            "new_files": list(new_files or []),
            "status": status,
        }

        # 添加数据选择信息
        if row_selections:
            record["row_selections"] = row_selections
        if part_mappings:
            record["part_mappings"] = part_mappings
        if file_configs:
            record["file_configs"] = file_configs
        
        # 添加父记录 ID（树状结构）
        if parent_record_id:
            record["parent_record_id"] = parent_record_id

        self.records.insert(0, record)
        # 新增记录时清空redo栈（标准Undo/Redo行为）
        self.redo_stack = []
        self.save()
        return record

    def get_records(self) -> List[Dict]:
        return list(self.records)

    def undo_record(self, record_id: str) -> Optional[Dict]:
        """撤销指定记录：标记为undone并移入redo栈"""
        for rec in self.records:
            if rec.get("id") == record_id:
                # 保存撤销前的状态到redo栈
                redo_item = {
                    "record": dict(rec),  # 深拷贝记录
                    "action": "undo",
                    "timestamp": datetime.now().isoformat(),
                }
                self.redo_stack.insert(0, redo_item)
                # 标记为已撤销
                rec["status"] = "undone"
                self.save()
                return rec
        return None

    def redo_record(self) -> Optional[Dict]:
        """重做最近一次撤销：从redo栈恢复记录"""
        if not self.redo_stack:
            return None

        redo_item = self.redo_stack.pop(0)
        record = redo_item.get("record")
        if not record:
            return None

        # 恢复记录状态
        record_id = record.get("id")
        for rec in self.records:
            if rec.get("id") == record_id:
                rec["status"] = record.get("status", "completed")
                self.save()
                return rec

        return None

    def get_redo_info(self) -> Optional[Dict]:
        """获取可重做的操作信息（用于按钮提示）"""
        if not self.redo_stack:
            return None

        redo_item = self.redo_stack[0]
        record = redo_item.get("record", {})
        return {
            "count": len(record.get("new_files", [])),
            "output_dir": record.get("output_dir", ""),
            "timestamp": record.get("timestamp", ""),
        }


class BatchHistoryPanel(QWidget):
    """右侧历史面板：按日期分组显示批处理记录，并提供撤销/重做按钮。"""

    def __init__(
        self,
        store: BatchHistoryStore,
        *,
        on_undo: Optional[Callable[[str], None]] = None,
        on_redo: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self._on_undo_cb = on_undo
        self._on_redo_cb = on_redo

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.lbl_title = QLabel("批处理历史")
        self.lbl_title.setProperty("class", "sidebar-title")
        lay.addWidget(self.lbl_title)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["时间", "摘要", "状态", "操作"])
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        lay.addWidget(self.tree)

        self.refresh()

    def set_undo_callback(self, cb: Callable[[str], None]) -> None:
        self._on_undo_cb = cb

    def set_redo_callback(self, cb: Callable[[str], None]) -> None:
        self._on_redo_cb = cb

    def refresh(self) -> None:
        """刷新历史面板，支持树状结构（父子记录关系）"""
        self.tree.clear()
        records = self.store.get_records()
        
        # 构建父子关系映射：parent_id -> [child_records]
        parent_children: Dict[str, List[Dict]] = defaultdict(list)
        top_level_records = []
        
        for rec in records:
            parent_id = rec.get("parent_record_id")
            if parent_id:
                parent_children[parent_id].append(rec)
            else:
                top_level_records.append(rec)
        
        # 按日期分组顶级记录
        grouped: Dict[str, List[Dict]] = defaultdict(list)
        for rec in top_level_records:
            ts = rec.get("timestamp") or ""
            try:
                d = ts.split("T")[0]
            except Exception:
                d = "未知日期"
            grouped[d].append(rec)

        # 显示日期分组和记录
        for day in sorted(grouped.keys(), reverse=True):
            day_item = QTreeWidgetItem([day])
            day_item.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(day_item)
            
            for rec in grouped[day]:
                # 添加主记录
                ts = rec.get("timestamp", "")
                time_part = ts.split("T")[-1][:8] if "T" in ts else ts
                summary = self._build_summary(rec)
                status = self._status_text(rec.get("status"))
                record_id = rec.get("id")
                
                # 如果有子记录（重做的结果），显示重做计数
                child_records = parent_children.get(record_id, [])
                if child_records:
                    summary += f" | 已重做 {len(child_records)} 次"
                
                row = QTreeWidgetItem([time_part, summary, status, ""])
                day_item.addChild(row)
                btn = self._make_action_button(rec)
                if btn is not None:
                    self.tree.setItemWidget(row, 3, btn)
                
                # 添加子记录（重做生成的记录）
                for child_rec in child_records:
                    child_ts = child_rec.get("timestamp", "")
                    child_time_part = child_ts.split("T")[-1][:8] if "T" in child_ts else child_ts
                    child_summary = self._build_summary(child_rec)
                    child_status = self._status_text(child_rec.get("status"))
                    
                    child_row = QTreeWidgetItem([
                        f"  → {child_time_part}",  # 使用箭头表示是重做的子记录
                        child_summary,
                        child_status,
                        ""
                    ])
                    # 将子记录设置为浅灰色以区分
                    for col in range(4):
                        child_row.setForeground(col, QColor(128, 128, 128))
                    
                    row.addChild(child_row)
                    child_btn = self._make_action_button(child_rec)
                    if child_btn is not None:
                        self.tree.setItemWidget(child_row, 3, child_btn)

        self.tree.expandAll()

    def _build_summary(self, rec: Dict) -> str:
        count = len(rec.get("files") or [])
        out_dir = rec.get("output_dir", "")

        # 添加数据选择信息
        summary = f"{count} 个文件 → {out_dir}"

        # 统计选中的数据行数
        row_selections = rec.get("row_selections", {})
        if row_selections:
            total_rows = 0
            for file_sels in row_selections.values():
                if isinstance(file_sels, dict):  # 特殊格式: {part: [rows]}
                    for rows in file_sels.values():
                        total_rows += len(rows) if rows else 0
                elif isinstance(file_sels, list):  # 常规格式: [rows]
                    total_rows += len(file_sels)
            if total_rows > 0:
                summary += f" | {total_rows} 行数据"

        return summary

    def _status_text(self, status: Optional[str]) -> str:
        if status == "undone":
            return "已撤销"
        if status == "failed":
            return "失败"
        return "完成"

    def get_record_details(self, record_id: str) -> Optional[str]:
        """获取记录的详细信息（用于tooltip）"""
        for rec in self.store.get_records():
            if rec.get("id") == record_id:
                details = []

                # 基本信息
                details.append(f"📁 输入: {rec.get('input_path', '')}")
                details.append(f"💾 输出: {rec.get('output_dir', '')}")
                details.append(f"📄 文件: {len(rec.get('files', []))} 个")
                details.append(f"✅ 生成: {len(rec.get('new_files', []))} 个")

                # 数据选择信息
                row_selections = rec.get("row_selections", {})
                if row_selections:
                    details.append("")
                    details.append("📋 数据选择:")
                    for file_path, sels in row_selections.items():
                        file_name = Path(file_path).name if file_path else "Unknown"
                        if isinstance(sels, dict):  # 特殊格式
                            for part, rows in sels.items():
                                count = len(rows) if rows else 0
                                details.append(f"  • {file_name} [{part}]: {count} 行")
                        elif isinstance(sels, list):  # 常规格式
                            details.append(f"  • {file_name}: {len(sels)} 行")

                # Part映射信息
                part_mappings = rec.get("part_mappings", {})
                if part_mappings:
                    details.append("")
                    details.append("🔗 Part映射:")
                    for file_path, mappings in part_mappings.items():
                        file_name = Path(file_path).name if file_path else "Unknown"
                        if isinstance(mappings, dict):
                            for internal_part, mapping in mappings.items():
                                if isinstance(mapping, dict):
                                    src = mapping.get("source", "?")
                                    tgt = mapping.get("target", "?")
                                    line = (
                                        f"  • {file_name} "
                                        f"[{internal_part}]: {src} → {tgt}"
                                    )
                                    details.append(line)

                return "\n".join(details)
        return None

    def _make_action_button(self, rec: Dict) -> Optional[QPushButton]:
        """根据记录状态创建撤销或重做按钮"""
        new_files = rec.get("new_files") or []
        if not new_files:
            return None

        record_id = rec.get("id")
        status = rec.get("status")

        # 获取详细信息用于tooltip
        details = self.get_record_details(record_id)

        if status == "undone":
            # 已撤销状态 → 显示重做按钮
            btn = QPushButton("重做")
            btn.setProperty("class", "primary")  # 使用主题色突出显示
            tooltip = f"重做此批处理（{len(new_files)} 个文件）"
            if details:
                tooltip += f"\n\n{details}"
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda _=False, rid=record_id: self._on_redo(rid))
        else:
            # 完成状态 → 显示撤销按钮
            btn = QPushButton("撤销")
            btn.setProperty("class", "ghost")
            tooltip = f"撤销此批处理（删除 {len(new_files)} 个文件）"
            if details:
                tooltip += f"\n\n{details}"
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda _=False, rid=record_id: self._on_undo(rid))

        return btn

    def _on_undo(self, record_id: Optional[str]) -> None:
        try:
            if not record_id or not callable(self._on_undo_cb):
                return

            # 查找记录以便显示提示信息
            record = None
            for rec in self.store.get_records():
                if rec.get("id") == record_id:
                    record = rec
                    break

            # 基本确认：显示输出目录与新文件数量
            try:
                from PySide6.QtWidgets import QMessageBox

                if record is not None:
                    out_dir = record.get("output_dir", "")
                    new_files = record.get("new_files") or []
                    count = len(new_files)
                else:
                    out_dir = ""
                    count = 0

                msg = f"确认撤销此批处理记录吗？\n将删除 {count} 个由该批处理生成的新文件\n输出目录: {out_dir}"
                resp = QMessageBox.question(
                    self,
                    "确认撤销",
                    msg,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if resp != QMessageBox.Yes:
                    return
            except Exception:
                # 若无法弹出确认对话，则直接返回
                return

            # 如果记录执行时间过早（超过 24 小时），进行二次确认并提示可能的风险
            try:
                ts = None
                if record is not None:
                    ts_str = record.get("timestamp")
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str)
                        except Exception:
                            ts = None
                if ts is not None:
                    from datetime import datetime as _dt
                    from datetime import timedelta

                    age = _dt.now() - ts
                    if age > timedelta(days=1):
                        warn = (
                            f"该记录创建于 {ts.isoformat()}，距今已超过 24 小时。\n"
                            "在此期间源文件或输出目录可能已被移动、修改或删除。\n"
                            "继续撤销可能会失败或删除非预期文件。是否仍要继续？"
                        )
                        resp2 = QMessageBox.question(
                            self,
                            "可能的风险",
                            warn,
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No,
                        )
                        if resp2 != QMessageBox.Yes:
                            return
            except Exception:
                # 忽略时间解析或对话失败，继续执行撤销
                pass

            # 最终调用回调并刷新面板
            self._on_undo_cb(record_id)
            try:
                self.refresh()
            except Exception:
                pass
        except Exception:
            logger.debug("撤销操作触发失败", exc_info=True)

    def _on_redo(self, record_id: Optional[str]) -> None:
        """处理重做按钮点击"""
        try:
            if not record_id or not callable(self._on_redo_cb):
                return

            # 查找记录以便显示提示信息
            record = None
            for rec in self.store.get_records():
                if rec.get("id") == record_id:
                    record = rec
                    break

            if record is None:
                return

            # 确认对话框
            try:
                from PySide6.QtWidgets import QMessageBox

                out_dir = record.get("output_dir", "")
                new_files = record.get("new_files") or []
                count = len(new_files)

                msg = (
                    f"确认重做此批处理操作吗？\n\n"
                    f"📁 输出目录: {out_dir}\n"
                    f"📄 涉及文件: {count} 个\n\n"
                    f"⚠️ 注意：重做只会恢复记录状态，不会重新生成已删除的文件。\n"
                    f"如需重新生成文件，请重新运行批处理。"
                )

                resp = QMessageBox.question(
                    self,
                    "确认重做",
                    msg,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )

                if resp != QMessageBox.Yes:
                    return
            except Exception:
                # 若无法弹出确认对话，则直接返回
                return

            # 调用回调并刷新
            self._on_redo_cb(record_id)
            try:
                self.refresh()
            except Exception:
                pass
        except Exception:
            logger.debug("重做操作触发失败", exc_info=True)
