# ============ 构建阶段 ============
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============ 运行阶段 ============
FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/lwhx/zhuimange"
LABEL org.opencontainers.image.description="追漫阁 - 番剧追踪管理工具"
LABEL org.opencontainers.image.authors="zhuimange"
LABEL security.scan.enabled="true"

# 安装安全更新
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

WORKDIR /app

# 从构建阶段复制依赖
COPY --from=builder /install /usr/local

# 只复制必要的应用代码
COPY app/ ./app/
COPY requirements.txt .

# 创建非 root 用户和必要的目录
RUN groupadd -r appuser && \
    useradd -r -g appuser -s /sbin/nologin -c "Application user" appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# 环境变量
ENV DATABASE_PATH=/app/data/tracker.db \
    TZ=Asia/Shanghai \
    PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 切换到非 root 用户
USER appuser

EXPOSE 8000

VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

CMD ["python", "-m", "app.main"]
