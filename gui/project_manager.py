"""
Project 管理器 - 处理 MomentTransfer 项目文件的保存与恢复
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ProjectManager:
    """管理 Project 文件的加载、保存和恢复"""

    PROJECT_VERSION = "1.0"
    PROJECT_FILE_EXTENSION = ".mtproject"

    def __init__(self, gui_instance):
        """初始化 ProjectManager

        Args:
            gui_instance: 主窗口实例
        """
        self.gui = gui_instance
        self.current_project_file: Optional[Path] = None
        self.last_saved_state: Optional[Dict] = None

    def create_new_project(self) -> bool:
        """创建新项目（清除当前工作状态）"""
        try:
            # 清除当前项目文件路径
            self.current_project_file = None
            self.last_saved_state = None

            # 重置工作流程到 Step 1
            try:
                if (
                    hasattr(self.gui, "batch_manager")
                    and self.gui.batch_manager
                ):
                    self.gui.batch_manager._set_workflow_step("init")
            except Exception:
                logger.debug("reset workflow step failed", exc_info=True)

            # 清除配置
            try:
                if (
                    hasattr(self.gui, "config_manager")
                    and self.gui.config_manager
                ):
                    self.gui.config_manager.reset_config()
            except Exception:
                logger.debug("reset config failed", exc_info=True)

            # 标记为用户已修改，以便启用保存按钮和相关 UI 控件
            try:
                if hasattr(self.gui, "mark_user_modified") and callable(
                    self.gui.mark_user_modified
                ):
                    try:
                        self.gui.mark_user_modified()
                    except Exception:
                        logger.debug(
                            "mark_user_modified 调用失败（非致命）",
                            exc_info=True,
                        )
            except Exception:
                pass

            logger.info("新项目已创建")
            return True
        except Exception as e:
            logger.error("创建新项目失败: %s", e)
            return False

    def save_project(self, file_path: Optional[Path] = None) -> bool:
        """保存当前项目到文件

        Args:
            file_path: 保存路径，若为 None 则使用最后打开的路径

        Returns:
            是否保存成功
        """
        try:
            if file_path is None:
                file_path = self.current_project_file

            if file_path is None:
                logger.error("未指定保存路径")
                return False

            file_path = Path(file_path)
            if not file_path.suffix:
                file_path = file_path.with_suffix(self.PROJECT_FILE_EXTENSION)

            # 收集当前状态
            project_data = self._collect_current_state()

            # 保存到文件
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)

            self.current_project_file = file_path
            self.last_saved_state = project_data

            logger.info(f"项目已保存: {file_path}")
            return True
        except Exception as e:
            logger.error("保存项目失败: %s", e)
            return False

    def load_project(self, file_path: Path) -> bool:
        """加载项目文件

        Args:
            file_path: 项目文件路径

        Returns:
            是否加载成功
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.error(f"项目文件不存在: {file_path}")
                return False

            with open(file_path, "r", encoding="utf-8") as f:
                project_data = json.load(f)

            # 验证版本
            version = project_data.get("version")
            if version != self.PROJECT_VERSION:
                logger.warning(
                    f"项目版本不匹配: {version} (期望 {self.PROJECT_VERSION})"
                )

            # 恢复配置
            self._restore_config(project_data)

            # 恢复数据文件
            self._restore_data_files(project_data)

            # 恢复工作流程步骤
            self._restore_workflow_step(project_data)

            self.current_project_file = file_path
            self.last_saved_state = project_data

            logger.info(f"项目已加载: {file_path}")
            return True
        except Exception as e:
            logger.error("加载项目失败: %s", e)
            return False

    def _collect_current_state(self) -> Dict:
        """收集当前工作状态"""
        project_data = {
            "version": self.PROJECT_VERSION,
            "timestamp": datetime.now().isoformat(),
        }

        # 保存参考系配置
        try:
            config = None
            if hasattr(self.gui, "project_model") and self.gui.project_model:
                config = self._serialize_project_model(self.gui.project_model)
            elif (
                hasattr(self.gui, "current_config") and self.gui.current_config
            ):
                config = self._serialize_config(self.gui.current_config)

            if config:
                project_data["reference_config"] = {
                    "data": config,
                    "timestamp": datetime.now().isoformat(),
                }
        except Exception as e:
            logger.debug(f"收集配置失败: {e}", exc_info=True)

        # 保存数据文件及映射
        try:
            data_files = []
            if hasattr(self.gui, "file_selection_manager"):
                fsm = self.gui.file_selection_manager

                # 收集特殊格式映射
                special_mappings = (
                    getattr(fsm, "special_part_mapping_by_file", {}) or {}
                )
                table_selection = (
                    getattr(fsm, "table_row_selection_by_file", {}) or {}
                )

                for file_path, mapping in special_mappings.items():
                    row_sel = table_selection.get(file_path)
                    data_files.append(
                        {
                            "path": file_path,
                            "special_mappings": mapping,
                            "row_selection": list(row_sel) if row_sel else [],
                        }
                    )

            project_data["data_files"] = data_files
        except Exception as e:
            logger.debug(f"收集数据文件失败: {e}", exc_info=True)
            project_data["data_files"] = []

        # 保存工作流程步骤
        try:
            if hasattr(self.gui, "batch_manager"):
                step = getattr(
                    self.gui.batch_manager, "_current_workflow_step", 1
                )
                project_data["workflow_step"] = step
        except Exception:
            project_data["workflow_step"] = 1

        # 保存输出目录
        try:
            if hasattr(self.gui, "output_dir"):
                project_data["output_dir"] = str(self.gui.output_dir)
        except Exception:
            pass

        return project_data

    def _restore_config(self, project_data: Dict) -> bool:
        """恢复配置"""
        try:
            config_data = project_data.get("reference_config", {}).get("data")
            if not config_data:
                return False

            # 创建 ProjectConfigModel 并恢复
            try:
                from src.models import ProjectConfigModel

                model = ProjectConfigModel.from_dict(config_data)
                if hasattr(self.gui, "project_model"):
                    self.gui.project_model = model
            except Exception as e:
                logger.debug(f"恢复 ProjectConfigModel 失败: {e}")
                return False

            logger.info("配置已恢复")
            return True
        except Exception as e:
            logger.debug(f"恢复配置失败: {e}", exc_info=True)
            return False

    def _restore_data_files(self, project_data: Dict) -> bool:
        """恢复数据文件选择和映射"""
        try:
            data_files = project_data.get("data_files", [])
            if not data_files or not hasattr(
                self.gui, "file_selection_manager"
            ):
                return False

            fsm = self.gui.file_selection_manager

            # 恢复特殊格式映射
            for file_info in data_files:
                file_path = file_info.get("path")
                mappings = file_info.get("special_mappings", {})
                row_sel = file_info.get("row_selection", [])

                if file_path and mappings:
                    fsm.special_part_mapping_by_file[file_path] = mappings

                if file_path and row_sel:
                    fsm.table_row_selection_by_file[file_path] = set(row_sel)

            logger.info(f"已恢复 {len(data_files)} 个数据文件的配置")
            return True
        except Exception as e:
            logger.debug(f"恢复数据文件失败: {e}", exc_info=True)
            return False

    def _restore_workflow_step(self, project_data: Dict) -> bool:
        """恢复工作流程步骤"""
        try:
            step = project_data.get("workflow_step", 1)
            if hasattr(self.gui, "batch_manager"):
                # 映射步骤到字符串
                step_map = {1: "init", 2: "step2", 3: "step3"}
                step_str = step_map.get(step, "init")
                self.gui.batch_manager._set_workflow_step(step_str)

            logger.info(f"工作流程已恢复到步骤 {step}")
            return True
        except Exception as e:
            logger.debug(f"恢复工作流程失败: {e}", exc_info=True)
            return False

    @staticmethod
    def _serialize_project_model(model) -> Optional[Dict]:
        """序列化 ProjectConfigModel"""
        try:
            if hasattr(model, "to_dict"):
                return model.to_dict()

            # 回退：手动构建
            data = {
                "source_parts": {},
                "target_parts": {},
            }

            if hasattr(model, "source_parts"):
                for name, part in (model.source_parts or {}).items():
                    data["source_parts"][name] = (
                        ProjectManager._serialize_part(part)
                    )

            if hasattr(model, "target_parts"):
                for name, part in (model.target_parts or {}).items():
                    data["target_parts"][name] = (
                        ProjectManager._serialize_part(part)
                    )

            return data
        except Exception:
            return None

    @staticmethod
    def _serialize_part(part) -> Dict:
        """序列化 Part 对象"""
        try:
            data = {
                "name": getattr(part, "part_name", ""),
                "variants": [],
            }

            if hasattr(part, "variants"):
                for variant in part.variants or []:
                    var_data = ProjectManager._serialize_variant(variant)
                    if var_data:
                        data["variants"].append(var_data)

            return data
        except Exception:
            return {}

    @staticmethod
    def _serialize_variant(variant) -> Optional[Dict]:
        """序列化 Variant 对象"""
        try:
            data = {
                "part_name": getattr(variant, "part_name", ""),
            }

            # 坐标系
            if hasattr(variant, "coord_system"):
                cs = variant.coord_system
                data["coord_system"] = {
                    "origin": getattr(cs, "origin", [0, 0, 0]),
                    "moment_center": getattr(cs, "moment_center", [0, 0, 0]),
                }

            # 参考值
            if hasattr(variant, "refs"):
                refs = variant.refs
                data["refs"] = {
                    "q": getattr(refs, "q", 1.0),
                    "s_ref": getattr(refs, "s_ref", 1.0),
                    "c_ref": getattr(refs, "c_ref", 1.0),
                    "b_ref": getattr(refs, "b_ref", 1.0),
                }

            return data
        except Exception:
            return None

    @staticmethod
    def _serialize_config(config) -> Optional[Dict]:
        """序列化配置对象（备用方案）"""
        try:
            data = {
                "source_parts": {},
                "target_parts": {},
            }

            if hasattr(config, "source_parts"):
                for name, part in (config.source_parts or {}).items():
                    data["source_parts"][name] = str(part)

            if hasattr(config, "target_parts"):
                for name, part in (config.target_parts or {}).items():
                    data["target_parts"][name] = str(part)

            return data
        except Exception:
            return None


__all__ = ["ProjectManager"]
