# Docker 容器同步问题调试指南

## 问题现象
在 Docker 容器中运行同步功能时，显示"同步完成: 0 集找到 0 个视频源"。

## 已修复的配置问题

### 1. 健康检查端点修复
**问题**: Dockerfile 和 docker-compose.yml 中的健康检查端点与实际实现不匹配
- 错误: `/health`
- 正确: `/api/health`

**修复文件**:
- [Dockerfile](e:\qb\trae\16\zhuimange\Dockerfile#L57) - 健康检查端点
- [docker-compose.yml](e:\qb\trae\16\zhuimange\docker-compose.yml#L37) - 健康检查配置

### 2. 增强日志输出
**新增配置**:
- 日志级别提升为 `DEBUG`
- 添加日志卷挂载
- 明确指定 `INVIDIOUS_URL`

**修改文件**:
- [docker-compose.yml](e:\qb\trae\16\zhuimange\docker-compose.yml) - 添加日志挂载和调试配置

### 3. .dockerignore 优化
**修复**: 确保 logs 目录不被排除，以便日志可以正确写入

## 排查步骤

### 步骤 1: 检查容器日志
```bash
docker logs zhuimange -f --tail 100
```

**关注以下日志**:
- `Invidious 实例: http://...` - 确认 Invidious URL
- `Invidious 连接测试: ... → HTTP 200` - 确认连接正常
- `搜索视频: '...' (实例: ...)` - 确认搜索正在执行
- `关键词 '...' 搜索到 X 个视频` - 确认搜索结果
- `搜索关键词出错` - 查看具体错误信息

### 步骤 2: 测试 Invidious 连接
进入容器执行:
```bash
docker exec -it zhuimange bash
curl -f http://localhost:8000/api/health
curl http://invidious.snopyta.org/api/v1/stats
```

### 步骤 3: 检查数据库
```bash
docker exec -it zhuimange bash
sqlite3 /app/data/tracker.db "SELECT id, title_cn, tmdb_id FROM animes;"
```

### 步骤 4: 查看 Docker 日志文件
```bash
# 检查挂载的日志目录
ls -la ./logs/

# 查看最新的日志文件
tail -f ./logs/*.log
```

## 常见问题和解决方案

### 问题 1: Invidious 实例不可访问
**症状**: 日志显示 "Invidious 连接失败" 或 "Invidious 请求失败"

**解决方案**:
1. 更换 Invidious 实例，编辑 `.env` 文件:
   ```bash
   INVIDIOUS_URL=https://yewtu.be
   # 或其他实例:
   # https://invidious.kavin.rocks
   # https://invidious.nerdvpn.de
   ```

2. 重启容器:
   ```bash
   docker-compose restart zhuimange
   ```

### 问题 2: 搜索结果为空
**症状**: 日志显示 `关键词 '...' 搜索到 0 个视频`

**可能原因**:
1. 网络问题: Invidious 实例无法访问
2. 关键词匹配失败: 动漫标题与实际视频标题差异较大
3. 搜索规则过滤: 视频被排除关键词过滤

**解决方案**:
1. 降低匹配阈值 (在 `.env` 中):
   ```bash
   MATCH_THRESHOLD=30  # 默认 50，手动添加动漫自动使用 30
   ```

2. 检查排除关键词配置

3. 手动测试搜索:
   ```bash
   docker exec -it zhuimange bash
   curl "https://invidious.snopyta.org/api/v1/search?q=斗破苍穹第1集&type=video"
   ```

### 问题 3: 集数数据缺失
**症状**: 同步显示"同步完成: 0/0 集找到视频源"

**解决方案**:
1. 检查动漫是否有集数数据:
   ```bash
   docker exec -it zhuimange bash
   sqlite3 /app/data/tracker.db "SELECT COUNT(*) FROM episodes WHERE anime_id=X;"
   ```

2. 手动添加动漫时，确保输入了正确的集数

3. 对于 TMDB 动漫，检查 TMDB API 是否正常工作

### 问题 4: 速率限制
**症状**: 日志显示 "Invidious 请求失败" 或搜索结果不完整

**解决方案**:
1. 使用自建 Invidious 实例（无速率限制）
2. 降低并发数:
   - 修改 `source_finder.py` 中的 `BATCH_SIZE` 和 `max_workers`
   - 默认每批并发 4 集

### 问题 5: 权限问题
**症状**: 日志显示数据库访问错误

**解决方案**:
```bash
# 检查数据目录权限
ls -la ./data/

# 修复权限
docker exec -it zhuimange chown -R appuser:appuser /app/data
```

## 配置优化建议

### 生产环境配置
```yaml
environment:
  - LOG_LEVEL=INFO  # 生产环境使用 INFO 级别
  - INVIDIOUS_URL=https://your-invidious-instance.com
  - MATCH_THRESHOLD=50
```

### 开发环境配置
```yaml
environment:
  - LOG_LEVEL=DEBUG  # 开发环境使用 DEBUG 级别
  - INVIDIOUS_URL=https://invidious.snopyta.org
  - MATCH_THRESHOLD=30
```

## 自建 Invidious 实例
如果公共实例不稳定，建议自建 Invidious 实例:

```yaml
services:
  invidious:
    image: quay.io/invidious/invidious:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      - INVIDIOUS_CONFIG_PATH=/config/config.yml
    volumes:
      - ./invidious-config:/config
      - invidious-db:/var/lib/invidious
```

然后在 `.env` 中配置:
```bash
INVIDIOUS_URL=http://invidious:3000
```

## 联系支持
如果以上步骤都无法解决问题，请提供以下信息:
1. Docker 日志: `docker logs zhuimange`
2. 同步日志: `./logs/` 目录中的日志文件
3. 数据库状态: 动漫和集数的基本信息
4. 网络测试结果: Invidious 实例的连接测试
