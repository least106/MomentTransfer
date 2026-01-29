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

logger = logging.getLogger(__name__)


class BatchHistoryStore:
    """管理批处理历史的简单持久化存储。"""

    def __init__(self, *, store_path: Optional[Path] = None) -> None:
        base_dir = Path.home() / ".momenttransfer"
        base_dir.mkdir(parents=True, exist_ok=True)
        self.store_path = store_path or base_dir / "batch_history.json"
        self.records: List[Dict] = []
        self._load()

    def _load(self) -> None:
        try:
            if self.store_path.exists():
                data = json.loads(self.store_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.records = data
        except Exception:
            logger.debug("加载批处理历史失败，使用空记录", exc_info=True)
            self.records = []

    def save(self) -> None:
        try:
            self.store_path.write_text(
                json.dumps(self.records, ensure_ascii=False, indent=2),
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
    ) -> Dict:
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
        self.records.insert(0, record)
        self.save()
        return record

    def mark_status(self, record_id: str, status: str) -> Optional[Dict]:
        for rec in self.records:
            if rec.get("id") == record_id:
                rec["status"] = status
                self.save()
                return rec
        return None

    def get_records(self) -> List[Dict]:
        return list(self.records)


class BatchHistoryPanel(QWidget):
    """右侧历史面板：按日期分组显示批处理记录，并提供撤销按钮。"""

    def __init__(
        self,
        store: BatchHistoryStore,
        *,
        on_undo: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self._on_undo_cb = on_undo

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.lbl_title = QLabel("批处理历史")
        self.lbl_title.setProperty("class", "sidebar-title")
        lay.addWidget(self.lbl_title)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["时间", "摘要", "状态", "操作"])
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.tree.header().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        lay.addWidget(self.tree)

        self.refresh()

    def set_undo_callback(self, cb: Callable[[str], None]) -> None:
        self._on_undo_cb = cb

    def refresh(self) -> None:
        self.tree.clear()
        records = self.store.get_records()
        grouped: Dict[str, List[Dict]] = defaultdict(list)
        for rec in records:
            ts = rec.get("timestamp") or ""
            try:
                d = ts.split("T")[0]
            except Exception:
                d = "未知日期"
            grouped[d].append(rec)

        for day in sorted(grouped.keys(), reverse=True):
            day_item = QTreeWidgetItem([day])
            day_item.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(day_item)
            for rec in grouped[day]:
                ts = rec.get("timestamp", "")
                time_part = ts.split("T")[-1][:8] if "T" in ts else ts
                summary = self._build_summary(rec)
                status = self._status_text(rec.get("status"))
                row = QTreeWidgetItem([time_part, summary, status, ""])
                day_item.addChild(row)
                btn = self._make_undo_button(rec)
                if btn is not None:
                    self.tree.setItemWidget(row, 3, btn)

        self.tree.expandAll()

    def _build_summary(self, rec: Dict) -> str:
        count = len(rec.get("files") or [])
        out_dir = rec.get("output_dir", "")
        return f"{count} 个文件 → {out_dir}"

    def _status_text(self, status: Optional[str]) -> str:
        if status == "undone":
            return "已撤销"
        if status == "failed":
            return "失败"
        return "完成"

    def _make_undo_button(self, rec: Dict) -> Optional[QPushButton]:
        if rec.get("status") == "undone":
            return None
        new_files = rec.get("new_files") or []
        if not new_files:
            return None
        btn = QPushButton("撤销")
        btn.setProperty("class", "ghost")
        btn.clicked.connect(
            lambda _=False, rid=rec.get("id"): self._on_undo(rid)
        )
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
                    self, "确认撤销", msg, QMessageBox.Yes | QMessageBox.No
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
