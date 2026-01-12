发布与打包说明

1. 更新版本号
   - 在 `pyproject.toml` 中修改 `version` 字段为新的语义化版本，例如 `0.1.0`。

2. 本地构建
```bash
# 激活环境
conda activate mt
# 安装构建工具
python -m pip install --upgrade build twine -i https://pypi.tuna.tsinghua.edu.cn/simple
# 构建源与 wheel
python -m build
```

3. 本地验证安装
```bash
pip install dist/momenttransfer-0.1.0-py3-none-any.whl
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
