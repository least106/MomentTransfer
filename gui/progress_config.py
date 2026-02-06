"""进度反馈配置模块

集中管理长时间操作的进度反馈配置参数。
"""

# 文件加载进度配置
# 超过此大小（MB）的文件将显示进度对话框
FILE_LOADING_SIZE_THRESHOLD_MB = 2.0

# 批处理进度配置
# 大文件行数阈值：超过此行数将显示详细进度
BATCH_LARGE_FILE_ROW_THRESHOLD = 1000

# 批处理分块大小：超过此行数的文件将分块处理并显示进度
BATCH_CHUNK_SIZE = 5000

# 项目保存配置
# 保存操作超时时间（秒）
PROJECT_SAVE_TIMEOUT_SECONDS = 30

# 进度更新间隔（秒）：避免过于频繁的进度更新
PROGRESS_UPDATE_INTERVAL_SECONDS = 0.5
