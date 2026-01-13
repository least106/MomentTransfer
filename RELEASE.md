发布与打包说明

## v0.1.0rc1 (2026-01-13) 测试版发布流程演示

本版本用于演示和测试发布流程，非正式版本。

### 测试范围
- 本地构建和打包
- 版本号管理
- 环境验证

## v0.1.0 (计划中) 首次正式发布

### 计划功能
- 完整的坐标系变换计算引擎
- GUI 和 CLI 两种使用方式
- 批处理支持（串行与并行）
- 特殊格式解析器（支持气象文件格式）
- 缓存优化和性能监控
- 配置管理与验证

### 支持平台
- Python 3.8+
- Windows/Linux/macOS
- 依赖：numpy, pandas, PySide6, matplotlib 等

### 已知限制
- GUI 在某些 Qt 版本下布局刷新需要 workaround（已处理）
- 特殊格式解析需要正确的编码声明
- 并行处理受系统可用 CPU 数限制

## 发布流程

1. 更新版本号
   - 在 `pyproject.toml` 中修改 `version` 字段为新的语义化版本，例如 `0.1.0`。

2. 本地构建
```bash
# 激活环境
conda activate mt
# 安装构建工具
python -m pip install --upgrade build twine
# 构建源与 wheel
python -m build
```

3. 本地验证安装
```bash
pip install dist/momenttransfer-0.1.0rc1-py3-none-any.whl
# 或者使用当前目录进行可编辑安装
pip install -e .
```

4. 发布到 PyPI
```bash
python -m twine upload dist/*
```

5. 备注
- 若包中包含二进制依赖（如 PySide6），建议在发布说明中注明兼容平台或在文档中提供 conda 安装示例。
- 发布前请确保所有单元测试通过并更新 `CHANGELOG` 或 `RELEASE.md` 中的变更说明。
