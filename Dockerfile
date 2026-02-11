# ============ 构建阶段 ============
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============ 运行阶段 ============
FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/lwhx/zhuimange"
LABEL org.opencontainers.image.description="追漫阁 - 番剧追踪管理工具"

WORKDIR /app

# 从构建阶段复制依赖
COPY --from=builder /install /usr/local

# 只复制必要的应用代码
COPY app/ ./app/
COPY requirements.txt .

# 创建数据目录
RUN mkdir -p /app/data

# 环境变量
ENV DATABASE_PATH=/app/data/tracker.db \
    TZ=Asia/Shanghai \
    PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

VOLUME ["/app/data"]

CMD ["python", "-m", "app.main"]
