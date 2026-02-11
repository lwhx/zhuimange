FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 环境变量
ENV DATABASE_PATH=/app/data/tracker.db
ENV TZ=Asia/Shanghai
ENV PORT=8000

EXPOSE 8000

CMD ["python", "-m", "app.main"]
