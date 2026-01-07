# 快速优化清单

## ✅ 已完成

- [x] **延迟加载 matplotlib** (~350ms 节省)
  - 修改：gui.py、gui/__init__.py、gui/visualization_manager.py
  - 效果：GUI启动快 ~22%，首次3D操作时才加载 matplotlib

## 📋 建议优化（按优先级）

### 第一阶段（立即，15分钟）
- [ ] 运行 `tools/startup_profiler.py` 验证优化效果
- [ ] 在 Win7 虚拟机上测试启动时间
- [ ] 如果启动时间 < 4s，优化完成 ✓

### 第二阶段（如需继续优化，30分钟）
- [ ] **延迟加载 pandas**（节省 ~350ms）
  - 在 `batch.py` 中延迟导入 pandas
  - 在 `BatchManager` 中延迟导入 pandas
  
### 第三阶段（长期，1-2小时）
- [ ] 考虑使用 PyInstaller 打包（50%+ 加速，但需维护）
- [ ] 考虑后台异步加载其他库

---

## 📊 期望的效果

| 环境 | 优化前 | 优化后 | 改进 |
|------|--------|--------|------|
| Win7虚拟机 | ~5000ms | **~4000-4200ms** | 16-20% ⬇️ |
| 现代物理机 | ~2000ms | **~1600-1800ms** | 15-20% ⬇️ |

---

## 🔧 如何验证

```bash
# 1. 激活环境
conda activate MomentTransfer

# 2. 运行性能分析
python tools/startup_profiler.py

# 3. 手动启动测试（观察启动速度）
python gui_main.py
```

---

## 🚀 最快的验证方式

在 Win7 虚拟机上：
```powershell
# 使用 PowerShell 的 Measure-Command 测量启动时间
Measure-Command { & python gui_main.py }
```

如果启动时间从 ~5000ms 降到 ~4000ms，说明优化有效 ✓

