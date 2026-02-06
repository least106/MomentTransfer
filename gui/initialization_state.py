"""初始化状态管理器

解决初始化顺序依赖和竞态条件问题。
提供：
- 集中的初始化状态跟踪
- 功能就绪状态检查
- 用户操作防护
- 初始化进度反馈
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class InitializationStage(Enum):
    """初始化阶段"""

    NOT_STARTED = "not_started"  # 未开始
    UI_SETUP = "ui_setup"  # UI 设置中
    MANAGERS_SETUP = "managers_setup"  # 管理器设置中
    CONNECTIONS = "connections"  # 信号连接中
    DATA_LOADING = "data_loading"  # 数据加载中
    FINALIZING = "finalizing"  # 最终化中
    COMPLETED = "completed"  # 完成


class ComponentState(Enum):
    """组件状态"""

    NOT_INITIALIZED = "not_initialized"  # 未初始化
    INITIALIZING = "initializing"  # 初始化中
    READY = "ready"  # 就绪
    ERROR = "error"  # 错误


@dataclass
class ComponentInfo:
    """组件信息"""

    name: str
    state: ComponentState = ComponentState.NOT_INITIALIZED
    dependencies: Set[str] = field(default_factory=set)  # 依赖的其他组件
    init_time: Optional[datetime] = None
    error: Optional[str] = None


class InitializationStateManager(QObject):
    """初始化状态管理器（单例）

    职责：
    1. 跟踪初始化阶段和组件状态
    2. 检查功能就绪状态
    3. 防止未就绪时的用户操作
    4. 提供初始化进度反馈
    """

    # 信号：初始化阶段变化 (stage)
    stageChanged = Signal(object)

    # 信号：组件状态变化 (component_name, state)
    componentStateChanged = Signal(str, object)

    # 信号：初始化完成
    initializationCompleted = Signal()

    # 信号：初始化失败 (error_message)
    initializationFailed = Signal(str)

    _instance: Optional["InitializationStateManager"] = None

    @classmethod
    def instance(cls) -> "InitializationStateManager":
        """获取单例"""
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            QObject.__init__(cls._instance)
            cls._instance._initialize()
        return cls._instance

    def __init__(self):
        # 禁止直接实例化，必须使用 instance()
        if InitializationStateManager._instance is not None:
            raise RuntimeError(
                "InitializationStateManager 是单例，请使用 instance() 方法"
            )

    def _initialize(self):
        """初始化实例（内部方法）"""
        # 当前阶段
        self._current_stage = InitializationStage.NOT_STARTED

        # 组件信息
        self._components: Dict[str, ComponentInfo] = {}

        # 阻塞的操作（在未就绪时被阻止）
        self._blocked_operations: List[tuple] = []

        # 是否已完成初始化
        self._is_completed = False

        # 主窗口引用（用于显示提示）
        self._main_window: Optional[QWidget] = None

    def set_main_window(self, window: QWidget):
        """设置主窗口"""
        self._main_window = window

    def register_component(
        self, name: str, dependencies: Optional[Set[str]] = None
    ):
        """注册组件

        Args:
            name: 组件名称
            dependencies: 依赖的其他组件名称集合
        """
        if name not in self._components:
            self._components[name] = ComponentInfo(
                name=name, dependencies=dependencies or set()
            )
            logger.debug(f"注册组件: {name}, 依赖: {dependencies}")

    def set_stage(self, stage: InitializationStage):
        """设置当前初始化阶段"""
        if self._current_stage != stage:
            self._current_stage = stage
            logger.info(f"初始化阶段: {stage.value}")
            self.stageChanged.emit(stage)

    def mark_component_initializing(self, name: str):
        """标记组件开始初始化"""
        if name not in self._components:
            self.register_component(name)

        component = self._components[name]
        component.state = ComponentState.INITIALIZING
        logger.debug(f"组件开始初始化: {name}")
        self.componentStateChanged.emit(name, ComponentState.INITIALIZING)

    def mark_component_ready(self, name: str):
        """标记组件就绪"""
        if name not in self._components:
            logger.warning(f"未注册的组件: {name}")
            self.register_component(name)

        component = self._components[name]
        component.state = ComponentState.READY
        component.init_time = datetime.now()
        logger.info(f"组件就绪: {name}")
        self.componentStateChanged.emit(name, ComponentState.READY)

        # 检查是否所有组件都就绪
        if self._all_components_ready():
            self._complete_initialization()

    def mark_component_error(self, name: str, error: str):
        """标记组件初始化失败"""
        if name not in self._components:
            self.register_component(name)

        component = self._components[name]
        component.state = ComponentState.ERROR
        component.error = error
        logger.error(f"组件初始化失败: {name} - {error}")
        self.componentStateChanged.emit(name, ComponentState.ERROR)

        # 发送初始化失败信号
        self.initializationFailed.emit(f"组件 {name} 初始化失败: {error}")

    def is_component_ready(self, name: str) -> bool:
        """检查组件是否就绪"""
        if name not in self._components:
            return False
        return self._components[name].state == ComponentState.READY

    def are_components_ready(self, names: List[str]) -> bool:
        """检查多个组件是否都就绪"""
        return all(self.is_component_ready(name) for name in names)

    def check_dependencies_ready(self, name: str) -> bool:
        """检查组件的依赖是否都就绪"""
        if name not in self._components:
            return True

        component = self._components[name]
        return all(
            self.is_component_ready(dep) for dep in component.dependencies
        )

    def is_initialized(self) -> bool:
        """检查是否已完成初始化"""
        return self._is_completed

    def require_initialized(
        self, operation_name: str, show_message: bool = True
    ) -> bool:
        """要求初始化完成后才能执行操作

        Args:
            operation_name: 操作名称
            show_message: 是否显示提示消息

        Returns:
            是否可以执行操作
        """
        if self._is_completed:
            return True

        # 未就绪，记录并提示
        logger.warning(f"操作 '{operation_name}' 被阻止：初始化未完成")

        if show_message and self._main_window is not None:
            self._show_not_ready_message(operation_name)

        return False

    def require_components(
        self,
        component_names: List[str],
        operation_name: str,
        show_message: bool = True,
    ) -> bool:
        """要求特定组件就绪后才能执行操作

        Args:
            component_names: 需要的组件名称列表
            operation_name: 操作名称
            show_message: 是否显示提示消息

        Returns:
            是否可以执行操作
        """
        if self.are_components_ready(component_names):
            return True

        # 查找未就绪的组件
        not_ready = [
            name
            for name in component_names
            if not self.is_component_ready(name)
        ]

        logger.warning(
            f"操作 '{operation_name}' 被阻止：组件未就绪: {', '.join(not_ready)}"
        )

        if show_message and self._main_window is not None:
            self._show_not_ready_message(
                operation_name, not_ready_components=not_ready
            )

        return False

    def get_component_state(self, name: str) -> Optional[ComponentState]:
        """获取组件状态"""
        if name in self._components:
            return self._components[name].state
        return None

    def get_all_components_info(self) -> Dict[str, ComponentInfo]:
        """获取所有组件信息"""
        return self._components.copy()

    def get_initialization_progress(self) -> tuple:
        """获取初始化进度

        Returns:
            (已就绪组件数, 总组件数, 百分比)
        """
        total = len(self._components)
        ready = sum(
            1
            for c in self._components.values()
            if c.state == ComponentState.READY
        )
        percentage = (ready / total * 100) if total > 0 else 0.0
        return (ready, total, percentage)

    def _all_components_ready(self) -> bool:
        """检查是否所有组件都就绪"""
        if not self._components:
            return False
        return all(
            c.state == ComponentState.READY for c in self._components.values()
        )

    def _complete_initialization(self):
        """完成初始化"""
        if self._is_completed:
            return

        self._is_completed = True
        self.set_stage(InitializationStage.COMPLETED)

        logger.info("初始化完成")
        self.initializationCompleted.emit()

        # 显示初始化统计
        ready, total, percentage = self.get_initialization_progress()
        logger.info(f"组件就绪: {ready}/{total} ({percentage:.1f}%)")

    def _show_not_ready_message(
        self, operation_name: str, not_ready_components: Optional[List[str]] = None
    ):
        """显示未就绪提示消息"""
        try:
            # 使用状态栏提示（非模态）
            from gui.signal_bus import SignalBus
            from gui.status_message_queue import MessagePriority

            message = f"功能未就绪：{operation_name}"

            if not_ready_components:
                components_str = "、".join(not_ready_components)
                message += f"（等待组件: {components_str}）"
            else:
                ready, total, _ = self.get_initialization_progress()
                message += f"（初始化进度: {ready}/{total}）"

            SignalBus.instance().statusMessage.emit(
                message, 3000, MessagePriority.HIGH
            )

        except Exception as e:
            logger.debug(f"显示未就绪消息失败: {e}")


def guard_initialization(component_name: str = None):
    """装饰器：保护需要初始化完成的操作

    Args:
        component_name: 如果指定，则检查特定组件是否就绪；否则检查全局初始化状态

    Example:
        @guard_initialization()
        def start_batch_process(self):
            ...

        @guard_initialization("batch_manager")
        def configure_batch(self):
            ...
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            state_manager = InitializationStateManager.instance()
            operation_name = func.__name__

            if component_name:
                # 检查特定组件
                if not state_manager.require_components(
                    [component_name], operation_name
                ):
                    logger.debug(
                        f"操作 {operation_name} 被阻止：组件 {component_name} 未就绪"
                    )
                    return None
            else:
                # 检查全局初始化状态
                if not state_manager.require_initialized(operation_name):
                    logger.debug(
                        f"操作 {operation_name} 被阻止：初始化未完成"
                    )
                    return None

            return func(*args, **kwargs)

        return wrapper

    return decorator
