# Part 1: HTTP 客户端配置
HTTP_TIMEOUT = 120.0

# Part 2: WebSocket 客户端配置
WS_OPEN_TIMEOUT = 20.0
WS_PING_INTERVAL = 10.0
WS_PING_TIMEOUT = 30.0

# Part 3: 工作流执行配置
WORKFLOW_EXECUTION_TIMEOUT = 1145

# Part 4: 文件下载配置
DOWNLOAD_RETRY_ATTEMPTS = 3  # 下载失败时的最大重试次数
DOWNLOAD_RETRY_DELAY = 5     # 每次重试前的等待时间（秒）