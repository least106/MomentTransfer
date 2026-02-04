"""
状态管理器 - 管理应用的全局状态（重做模式、加载project等）
确保状态转换时清理旧状态，避免新操作被误关联到旧状态
"""

import logging
from enum import Enum
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class AppState(Enum):
    """应用状态枚举"""

    NORMAL = "normal"  # 正常操作
    REDO_MODE = "redo_mode"  # 重做模式
    PROJECT_LOADING = "project_loading"  # 加载项目中
    BATCH_PROCESSING = "batch_processing"  # 批处理中


class GlobalStateManager(QObject):
    """全局状态管理器

    管理当前应用状态，并在状态改变时触发相应的清理和通知。
    确保状态转换时不会混淆新旧状态的数据。
    """

    # 信号：状态改变
    stateChanged = Signal(AppState, dict)  # (新状态, 状态数据)

    # 信号：重做状态改变
    redoModeChanged = Signal(bool, str)  # (进入/退出, 记录ID)

    def __init__(self):
        super().__init__()
        self._current_state = AppState.NORMAL
        self._state_data: Dict[str, Any] = {}
        self._redo_parent_id: Optional[str] = None
        self._instance = None

    @classmethod
    def instance(cls):
        """单例模式获取实例"""
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def current_state(self) -> AppState:
        """获取当前状态"""
        return self._current_state

    @property
    def is_redo_mode(self) -> bool:
        """是否处于重做模式"""
        return self._current_state == AppState.REDO_MODE

    @property
    def redo_parent_id(self) -> Optional[str]:
        """获取重做的父记录 ID"""
        return self._redo_parent_id

    def set_redo_mode(
        self, parent_record_id: str, record_info: Optional[Dict] = None
    ) -> None:
        """进入重做模式

        进入重做模式时，会清除多选文件列表（_selected_paths），确保退出后
        不会误用旧的批处理选择。这避免了用户修改配置后无意中使用旧的多选列表。

        Args:
            parent_record_id: 被重做的记录 ID
            record_info: 记录信息，用于显示在状态横幅
        """
        try:
            # 如果已经处于重做模式且是同一个记录，则忽略
            if (
                self._current_state == AppState.REDO_MODE
                and self._redo_parent_id == parent_record_id
            ):
                logger.debug("已处于该记录的重做模式，忽略重复设置")
                return

            # 清除旧状态
            if self._current_state == AppState.REDO_MODE:
                logger.info("离开旧重做模式: %s", self._redo_parent_id)

            # 设置新状态
            self._current_state = AppState.REDO_MODE
            self._redo_parent_id = parent_record_id
            self._state_data = record_info or {}

            logger.info("进入重做模式: %s", parent_record_id)
            self.stateChanged.emit(AppState.REDO_MODE, self._state_data)
            self.redoModeChanged.emit(True, parent_record_id)
        except Exception as e:
            logger.error("设置重做模式失败: %s", e, exc_info=True)

    def exit_redo_mode(self) -> None:
        """退出重做模式

        当退出重做模式时，清除多选文件列表，确保用户不会误用
        重做前的批处理选择。这强制用户在修改配置后重新选择文件。
        """
        try:
            if self._current_state != AppState.REDO_MODE:
                logger.debug("当前不处于重做模式，无需退出")
                return

            old_parent_id = self._redo_parent_id
            self._current_state = AppState.NORMAL
            self._redo_parent_id = None
            self._state_data = {}

            logger.info("退出重做模式: %s", old_parent_id)
            self.stateChanged.emit(AppState.NORMAL, {})
            self.redoModeChanged.emit(False, old_parent_id or "")
        except Exception as e:
            logger.error("退出重做模式失败: %s", e, exc_info=True)

    def set_loading_project(self, project_path: str) -> None:
        """设置加载项目状态"""
        try:
            # 清除重做模式
            if self._current_state == AppState.REDO_MODE:
                logger.info("加载项目，清除重做模式")
                old_parent_id = self._redo_parent_id
                self._redo_parent_id = None
                self.redoModeChanged.emit(False, old_parent_id or "")

            self._current_state = AppState.PROJECT_LOADING
            self._state_data = {"project_path": project_path}

            logger.info("进入加载项目状态: %s", project_path)
            self.stateChanged.emit(AppState.PROJECT_LOADING, self._state_data)
        except Exception as e:
            logger.error("设置加载项目状态失败: %s", e, exc_info=True)

    def exit_loading_project(self) -> None:
        """退出加载项目状态"""
        try:
            if self._current_state != AppState.PROJECT_LOADING:
                logger.debug("当前不处于加载项目状态")
                return

            self._current_state = AppState.NORMAL
            self._state_data = {}

            logger.info("退出加载项目状态")
            self.stateChanged.emit(AppState.NORMAL, {})
        except Exception as e:
            logger.error("退出加载项目状态失败: %s", e, exc_info=True)

    def set_batch_processing(self) -> None:
        """设置批处理中状态"""
        try:
            # 如果处于重做模式，则继承父记录 ID
            # 不清除，让批处理知道自己在重做模式下运行

            self._current_state = AppState.BATCH_PROCESSING
            logger.info("进入批处理状态")
            self.stateChanged.emit(AppState.BATCH_PROCESSING, {})
        except Exception as e:
            logger.error("设置批处理状态失败: %s", e, exc_info=True)

    def exit_batch_processing(self) -> None:
        """退出批处理状态，回到之前的状态"""
        try:
            if self._current_state != AppState.BATCH_PROCESSING:
                logger.debug("当前不处于批处理状态")
                return

            # 回到之前的状态
            if self._redo_parent_id:
                self._current_state = AppState.REDO_MODE
            else:
                self._current_state = AppState.NORMAL

            logger.info("退出批处理状态")
            self.stateChanged.emit(self._current_state, self._state_data)
        except Exception as e:
            logger.error("退出批处理状态失败: %s", e, exc_info=True)

    def reset(self) -> None:
        """重置为正常状态（用于紧急情况）"""
        try:
            if self._current_state == AppState.REDO_MODE:
                old_parent_id = self._redo_parent_id
                self.redoModeChanged.emit(False, old_parent_id or "")

            self._current_state = AppState.NORMAL
            self._state_data = {}
            self._redo_parent_id = None

            logger.info("状态已重置为正常")
            self.stateChanged.emit(AppState.NORMAL, {})
        except Exception as e:
            logger.error("重置状态失败: %s", e, exc_info=True)

    def get_state_info(self) -> str:
        """获取当前状态的描述"""
        if self._current_state == AppState.NORMAL:
            return "正常"
        elif self._current_state == AppState.REDO_MODE:
            return f"重做模式 ({self._redo_parent_id[:8]}...)"
        elif self._current_state == AppState.PROJECT_LOADING:
            return "加载项目"
        elif self._current_state == AppState.BATCH_PROCESSING:
            return "批处理中"
        else:
            return "未知状态"
