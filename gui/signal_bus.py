"""
中央信号总线：集中管理 GUI 内部通信，便于解耦。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """中央信号总线 - 单例。
    后续可在面板、管理器间复用，逐步替换分散连接。
    """

    # 配置相关
    configLoaded = Signal(object)  # 载入新模型（ProjectConfigModel 或兼容对象）
    configSaved = Signal(Path)  # 保存路径
    configApplied = Signal()  # 已应用配置
    configModified = Signal(bool)  # 配置修改状态变化 (True=已修改, False=未修改)

    # Part 相关
    sourcePartChanged = Signal(str)  # Source 当前 Part 名称
    targetPartChanged = Signal(str)  # Target 当前 Part 名称
    partAdded = Signal(str, str)  # side: 'Source'|'Target', part_name
    partRemoved = Signal(str, str)  # side: 'Source'|'Target', part_name
    # Part 请求（由面板发起，管理器响应）
    partAddRequested = Signal(
        str, str
    )  # side: 'Source'|'Target'|'src'|'tgt', desired_name
    partRemoveRequested = Signal(str, str)  # side: 'Source'|'Target'|'src'|'tgt', name

    # 批处理相关
    batchStarted = Signal(list)
    batchProgress = Signal(int, str)
    batchFinished = Signal(str)
    batchError = Signal(str)
    # 特殊格式解析完成（文件路径字符串）
    specialDataParsed = Signal(str)

    # UI 控制
    controlsLocked = Signal(bool)
    # 状态栏消息统一通道：message, timeout_ms, priority
    statusMessage = Signal(str, int, int)
    # Project 相关
    projectSaved = Signal(object)  # 保存项目，参数为 Path 或可序列化对象
    projectLoaded = Signal(object)  # 加载项目，参数为 Path 或可序列化对象

    _instance: Optional[SignalBus] = None

    @classmethod
    def instance(cls) -> "SignalBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()
