# syntax=docker/dockerfile:1
# ============ 构建阶段 ============
# Go 版追漫阁多阶段构建：编译纯静态二进制（CGO_ENABLED=0，modernc.org/sqlite 无需 CGO）
FROM golang:1.25-alpine AS builder

WORKDIR /build

# 先复制依赖文件，利用 Docker 层缓存
COPY go/go.mod go/go.sum ./
RUN go mod download

# 复制全部 Go 源码
COPY go/ ./

# 编译纯静态二进制（去除调试符号减小体积）
# CGO_ENABLED=0：modernc.org/sqlite 是纯 Go 实现，无需 CGO
# -ldflags="-s -w"：去除调试符号和 DWARF 信息
# -trimpath：去除构建路径信息
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-s -w" \
    -trimpath \
    -o /zhuimange \
    ./cmd/zhuimange

# ============ 运行阶段 ============
FROM alpine:3.20

LABEL org.opencontainers.image.source="https://github.com/lwhx/zhuimange"
LABEL org.opencontainers.image.description="追漫阁 - 番剧追踪管理工具（Go 版）"
LABEL org.opencontainers.image.authors="zhuimange"

# 安装最小依赖：ca-certificates（HTTPS 必需）+ tzdata（时区）+ curl（健康检查）
RUN apk add --no-cache ca-certificates tzdata curl && \
    # 创建非 root 用户（固定 UID=1000，便于宿主卷权限对齐）
    addgroup -g 1000 -S appuser && \
    adduser -u 1000 -S -G appuser -s /sbin/nologin -D appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

WORKDIR /app

# 从构建阶段复制编译好的二进制（资源已用 //go:embed 打包进二进制）
COPY --from=builder /zhuimange /app/zhuimange

# 环境变量
ENV DATABASE_PATH=/app/data/tracker.db \
    TZ=Asia/Shanghai \
    PORT=8000

# 切换到非 root 用户
USER appuser

EXPOSE 8000

VOLUME ["/app/data"]

# 健康检查（Go 版有 /api/health 端点）
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["/app/zhuimange"]
