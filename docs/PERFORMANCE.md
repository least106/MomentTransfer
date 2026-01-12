**性能基准与示例**

- 脚本：`tools/benchmark.py`
- 说明：脚本对 `AeroCalculator.process_frame` 进行多次调用并统计平均耗时。可通过 `--iterations` 调整样本量。

示例：
```bash
# 在项目根目录运行（先激活 conda 环境或确保依赖已安装）
python tools/benchmark.py --iterations 5000 --warmup 200
```

注意：基准结果受 CPU、Python 版本、是否启用仿真环境等影响；在 CI 中运行基准时建议使用固定 runner 并多次取平均。

## 本次本地样本 (2026-01-09 16:34:22)

- Iterations: 2000
- Warmup: 100
- Total time: 0.096495 s
- Per call: 48.248 µs

> 说明：该测量在本地开发机、通过设置 `PYTHONPATH='.'` 后运行脚本得到，用于快速回归与对比。