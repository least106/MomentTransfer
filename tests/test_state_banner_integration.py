#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试状态横幅集成 - 验证全局状态管理器与 batch_manager 的交互
"""

import logging
import sys
from pathlib import Path

# 配置日志以查看详细信息
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_state_manager_import():
    """测试全局状态管理器导入"""
    try:
        from gui.global_state_manager import AppState, GlobalStateManager

        logger.info("✓ 全局状态管理器导入成功")

        # 测试单例模式
        sm1 = GlobalStateManager.instance()
        sm2 = GlobalStateManager.instance()
        assert sm1 is sm2, "单例模式失败"
        logger.info("✓ 单例模式正确")

        # 测试初始状态
        assert (
            sm1.current_state == AppState.NORMAL
        ), f"初始状态应为NORMAL，但为 {sm1.current_state}"
        logger.info("✓ 初始状态正确")

        return True
    except Exception as e:
        logger.error(f"✗ 测试失败: {e}", exc_info=True)
        return False


def test_state_transitions():
    """测试状态转换"""
    try:
        from gui.global_state_manager import AppState, GlobalStateManager

        sm = GlobalStateManager.instance()

        # 测试进入重做模式
        sm.set_redo_mode("parent_123", {"input_path": "test.csv"})
        assert sm.current_state == AppState.REDO_MODE, "进入重做模式失败"
        assert sm.redo_parent_id == "parent_123", "父记录ID设置失败"
        logger.info("✓ 进入重做模式成功")

        # 测试退出重做模式
        sm.exit_redo_mode()
        assert sm.current_state == AppState.NORMAL, "退出重做模式失败"
        assert sm.redo_parent_id is None, "退出后应清除父记录ID"
        logger.info("✓ 退出重做模式成功")

        # 测试项目加载模式
        sm.set_loading_project("/path/to/project.json")
        assert sm.current_state == AppState.PROJECT_LOADING, "进入项目加载模式失败"
        logger.info("✓ 进入项目加载模式成功")

        # 验证项目加载时自动清除重做模式
        sm.set_redo_mode("redo_123", {})
        assert sm.current_state == AppState.REDO_MODE, "应该在重做模式"
        sm.set_loading_project("/another/project.json")
        assert sm.current_state == AppState.PROJECT_LOADING, "加载项目应覆盖重做模式"
        assert sm.redo_parent_id is None, "进入项目加载模式应清除重做状态"
        logger.info("✓ 项目加载模式自动清除重做状态正确")

        # 重置状态
        sm.reset()
        assert sm.current_state == AppState.NORMAL, "重置失败"
        logger.info("✓ 重置状态成功")

        return True
    except Exception as e:
        logger.error(f"✗ 测试失败: {e}", exc_info=True)
        return False


def test_signal_emissions():
    """测试信号发送"""
    try:
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtWidgets import QApplication

        from gui.global_state_manager import AppState, GlobalStateManager

        # 需要 QApplication 来处理信号
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        sm = GlobalStateManager.instance()

        # 记录信号发送情况
        signal_emissions = []

        def on_state_changed(new_state):
            signal_emissions.append(("stateChanged", new_state))
            logger.debug(f"信号: stateChanged -> {new_state}")

        def on_redo_mode_changed(is_entering, record_id):
            signal_emissions.append(("redoModeChanged", is_entering, record_id))
            logger.debug(
                f"信号: redoModeChanged -> is_entering={is_entering}, record_id={record_id}"
            )

        sm.stateChanged.connect(on_state_changed)
        sm.redoModeChanged.connect(on_redo_mode_changed)

        # 触发状态变更
        sm.set_redo_mode("test_123", {})
        app.processEvents()

        # 验证信号发送
        assert any(
            e[0] == "redoModeChanged" and e[1] == True for e in signal_emissions
        ), "进入重做模式应发送 redoModeChanged 信号"
        logger.info("✓ 进入重做模式信号正确发送")

        signal_emissions.clear()
        sm.exit_redo_mode()
        app.processEvents()

        assert any(
            e[0] == "redoModeChanged" and e[1] == False for e in signal_emissions
        ), "退出重做模式应发送 redoModeChanged 信号"
        logger.info("✓ 退出重做模式信号正确发送")

        return True
    except Exception as e:
        logger.error(f"✗ 测试失败: {e}", exc_info=True)
        return False


def test_state_banner_import():
    """测试状态横幅导入"""
    try:
        from PySide6.QtWidgets import QApplication

        from gui.state_banner import StateBanner

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        banner = StateBanner()
        logger.info("✓ 状态横幅导入成功")

        # 测试显示重做状态
        banner.show_redo_state({"input_path": "test.csv"})
        app.processEvents()
        logger.info("✓ 状态横幅可显示重做状态")

        # 测试清除
        banner.clear()
        app.processEvents()
        logger.info("✓ 状态横幅可清除")

        return True
    except Exception as e:
        logger.error(f"✗ 测试失败: {e}", exc_info=True)
        return False


def main():
    """运行所有测试"""
    logger.info("=" * 60)
    logger.info("开始测试状态横幅集成")
    logger.info("=" * 60)

    tests = [
        ("导入全局状态管理器", test_state_manager_import),
        ("状态转换", test_state_transitions),
        ("信号发送", test_signal_emissions),
        ("状态横幅导入", test_state_banner_import),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"\n测试: {test_name}")
        logger.info("-" * 40)
        result = test_func()
        results.append((test_name, result))
        logger.info("-" * 40)

    # 总结
    logger.info("\n" + "=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")

    logger.info(f"\n总计: {passed}/{total} 通过")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
