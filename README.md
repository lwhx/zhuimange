<p align="center">
  <h1 align="center">🎬 追漫阁 - 国漫追更系统</h1>
  <p align="center">一个自部署的国漫追更管理平台，专为国漫爱好者打造</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Go-1.25+-00ADD8?logo=go&logoColor=white" alt="Go">
  <img src="https://img.shields.io/badge/SQLite-嵌入式-lightblue?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Docker-支持-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">
</p>

---

## ✨ 功能特性

| 特性 | 描述 |
|------|------|
| 🔍 **TMDB 集成** | 自动从 TMDB 获取动漫信息、海报、集数数据 |
| 🎬 **视频源搜索** | 通过 Invidious API 搜索 YouTube 上的国漫视频源，多实例加权轮询 + 故障自动切换 |
| 🧠 **智能匹配** | 6 套模糊匹配算法（精确/包含/子序列/字符重叠/编辑距离/N-gram）+ 4 层置信分层评分 + 国漫别名库 |
| 🚫 **合集过滤** | 自动识别并过滤合集 / 剪辑 / 解说等非正片内容 |
| ⏰ **自动同步** | 支持全局和个别动漫的独立同步间隔，SSE 实时推送同步进度 |
| 📊 **进度管理** | 追踪观看进度，标记已看 / 未看状态 |
| 🗓️ **追更日历 / 看板** | 月历视图展示更新，Dashboard 一览追更进度与缺源提醒 |
| 🔔 **智能提醒** | 缺源检测、长时间未更新提醒、TMDB 相似推荐 |
| 💾 **数据备份** | JSON 导出/导入、Bangumi/CSV 互通、Telegram Bot 自动备份 |
| 🤖 **Telegram 通知** | 通过 Telegram Bot 推送新集通知与备份文件 |
| 📱 **PWA / RSS** | 支持添加到主屏幕离线访问，RSS 订阅更新源 |
| 🎨 **现代化 UI** | 6 套主题、响应式设计、移动端友好、键盘快捷键 |

---

## 🛠️ 技术栈

**后端：** Go 1.25+ · chi 路由 · SQLite（modernc.org/sqlite，纯 Go 无 CGO） · robfig/cron  
**前端：** HTML5 / CSS3 · Alpine.js · HTMX · 响应式设计  
**外部服务：** TMDB API · Invidious API · Telegram Bot API  
**部署：** 单二进制 · Docker & Docker Compose · systemd

> **历史版本**：项目最初基于 Python/Flask 实现（源码保留在 `app/` 目录作为历史快照），现已完整迁移到 Go。Go 版优势：单二进制部署、内存占用降至 ~30MB、无运行时依赖。

---

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

镜像已通过 GitHub Actions 自动构建并发布到 GHCR，支持 `linux/amd64` 和 `linux/arm64` 架构。

#### 使用 Docker Run

```bash
# 拉取镜像
docker pull ghcr.io/lwhx/zhuimange:latest

# 启动容器
docker run -d \
  --name zhuimange \
  --restart unless-stopped \
  -p 8280:8000 \
  -v $(pwd)/data:/app/data \
  -e TMDB_API_KEY=your_tmdb_api_key_here \
  -e INVIDIOUS_URL=http://your-invidious:3000 \
  -e DATABASE_PATH=/app/data/tracker.db \
  -e TZ=Asia/Shanghai \
  ghcr.io/lwhx/zhuimange:latest
```

#### 使用 Docker Compose（推荐）

**1. 创建项目目录**

```bash
mkdir zhuimange && cd zhuimange
```

**2. 创建 `.env` 文件**

```env
# 必需 - TMDB API 密钥 (https://www.themoviedb.org/settings/api)
TMDB_API_KEY=your_tmdb_api_key_here

# 必需 - Invidious 实例地址 (https://docs.invidious.io/instances/)
INVIDIOUS_URL=http://your-invidious:3000

# 可选 - 首次启动访问密码（不设置则随机生成并打印到日志）
# INITIAL_PASSWORD=change-me

# 可选
TZ=Asia/Shanghai
LOG_LEVEL=INFO
```

**3. 创建 `docker-compose.yml`**

```yaml
services:
  zhuimange:
    image: ghcr.io/lwhx/zhuimange:latest
    container_name: zhuimange
    restart: unless-stopped
    ports:
      - "8280:8000"
    volumes:
      - ./data:/app/data
    env_file:
      - .env
    environment:
      - DATABASE_PATH=/app/data/tracker.db
      - TZ=Asia/Shanghai
```

**4. 启动服务**

```bash
docker compose up -d
```

**5. 访问应用**

打开浏览器访问 `http://localhost:8280`

> 首次启动会在日志中打印随机生成的访问密码（设置 `INITIAL_PASSWORD` 可预置），登录后可在「设置」页修改。

### 方式二：单二进制部署

从 [Releases](https://github.com/lwhx/zhuimange/releases) 下载对应平台的二进制文件，或自行交叉编译：

```bash
cd go
# Linux amd64
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -trimpath -o zhuimange ./cmd/zhuimange

# 上传到服务器后
scp zhuimange user@server:/opt/zhuimange/
ssh user@server "cd /opt/zhuimange && ./zhuimange"
```

配合 systemd 实现开机自启（模板见 `go/zhuimange.service`）：

```bash
sudo cp go/zhuimange.service /etc/systemd/system/
sudo systemctl enable --now zhuimange
```

### 方式三：本地开发运行

**1. 环境要求**

- Go 1.25+

**2. 配置环境变量**

```bash
cp .env.example .env
# 编辑 .env 文件，至少填写 TMDB_API_KEY 和 INVIDIOUS_URL
```

**3. 运行**

```bash
cd go
go run ./cmd/zhuimange
# 或编译后运行
go build -o zhuimange ./cmd/zhuimange && ./zhuimange
```

访问 `http://localhost:8000`

---

## 📁 项目结构

```
zhuimange/
├── go/                            # Go 版主代码
│   ├── cmd/zhuimange/main.go      # 应用入口
│   ├── internal/
│   │   ├── config/                # 配置加载（env + .env + DB settings）
│   │   ├── model/                 # 数据结构定义
│   │   ├── store/                 # SQLite 数据访问层（WAL + 连接池）
│   │   │   └── migrations/        # SQL 迁移文件（go:embed）
│   │   ├── auth/                  # bcrypt + cookie session + CSRF
│   │   ├── tmdb/                  # TMDB API 客户端
│   │   ├── invidious/             # Invidious 客户端（加权轮询 + 故障切换）
│   │   ├── matcher/               # 评分引擎（模糊匹配 + 合集过滤 + 置信分层）
│   │   ├── source/                # 视频源发现（关键词生成 + 并发搜索）
│   │   ├── syncsvc/               # 同步服务 + 任务队列（内存 + DB 持久化）
│   │   ├── scheduler/             # cron 定时同步
│   │   ├── notify/                # Telegram 通知
│   │   ├── health/                # Invidious/视频源健康诊断
│   │   ├── backup/                # JSON/Bangumi/CSV 备份互通
│   │   └── web/
│   │       ├── handler/           # HTTP 路由处理器
│   │       ├── middleware/         # 认证守卫/限流/安全头
│   │       ├── template/          # html/template 渲染
│   │       └── sse/               # SSE 流式推送
│   ├── web/                       # 前端资源（go:embed 打包进二进制）
│   │   ├── templates/             # HTML 模板
│   │   └── static/                # CSS/JS（Alpine.js + HTMX）
│   ├── go.mod / go.sum
│   └── zhuimange.service          # systemd 服务模板
├── app/                           # Python 版历史源码（已废弃，保留作参考）
├── data/                          # 数据存储（SQLite 数据库，运行时生成）
├── .env.example                   # 环境变量模板
├── Dockerfile                     # Go 多阶段构建（golang:1.25-alpine → alpine:3.20）
├── docker-compose.yml             # Docker Compose 编排
└── README.md
```

---

## 📡 API 概览

> 完整 51 个路由，以下列出核心端点。

### 动漫管理

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/search?q={query}` | GET | 搜索动漫（TMDB） |
| `/api/anime/add` | POST | 从 TMDB 添加动漫 |
| `/api/anime/add_manual` | POST | 手动添加动漫 |
| `/api/anime/{id}` | GET | 动漫详情 |
| `/api/anime/{id}` | DELETE | 删除动漫 |
| `/api/anime/{id}/episode/{ep}/watch` | POST | 标记已看 |
| `/api/anime/{id}/episode/{ep}/unwatch` | POST | 标记未看 |
| `/api/anime/{id}/progress` | PUT | 批量更新观看进度 |
| `/api/anime/{id}/episode/{ep}/sources` | GET | 获取视频源列表 |

### 同步引擎

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/anime/{id}/sync` | POST | 提交同步任务（incremental/full） |
| `/api/sync_tasks/{task_id}` | GET | 任务快照 |
| `/api/sync_tasks/{task_id}/stream` | GET (SSE) | 实时同步进度流 |

### 体验增强

| 端点 | 方法 | 描述 |
|------|------|------|
| `/dashboard` | GET | 追更看板页面 |
| `/calendar` | GET | 追更日历页面 |
| `/api/dashboard` | GET | 看板数据（含缺源提醒） |
| `/api/calendar` | GET | 日历数据 |
| `/api/favorites` | GET/POST | 收藏夹 |
| `/feed.xml` | GET | RSS 订阅源 |
| `/manifest.json` | GET | PWA 清单 |

### 设置与备份

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/settings` | GET/PUT | 获取/更新设置 |
| `/api/change_password` | POST | 修改密码 |
| `/api/backup/export` | GET | JSON 导出 |
| `/api/backup/export_bangumi` | GET | Bangumi 格式导出 |
| `/api/backup/export_csv` | GET | CSV 导出 |
| `/api/backup/import` | POST | JSON 导入 |
| `/api/backup/telegram` | POST | 发送备份到 Telegram |

### 诊断

| 端点 | 方法 | 描述 |
|------|------|------|
| `/diagnostics` | GET | Invidious 健康诊断页 |
| `/api/diagnostics/invidious` | GET/POST | 实例健康检测 |
| `/api/diagnostics/sources` | POST | 视频源健康检测 |
| `/api/proxy_image?url=` | GET | 图片代理（解决 HTTPS 混合内容） |

---

## ⚙️ 配置说明

### 必需配置

| 配置项 | 说明 | 获取方式 |
|--------|------|----------|
| `TMDB_API_KEY` | TMDB API 密钥 | [申请地址](https://www.themoviedb.org/settings/api) |
| `INVIDIOUS_URL` | Invidious 实例地址（建议自建） | [实例列表](https://docs.invidious.io/instances/) |

### 可选配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `SECRET_KEY` | 自动生成 | 会话签名密钥（未设置时持久化到 `data/.secret_key`） |
| `INITIAL_PASSWORD` | 随机生成 | 首次启动访问密码；仅在数据库未设密码时生效 |
| `DATABASE_PATH` | `./data/tracker.db` | 数据库路径 |
| `TZ` | `Asia/Shanghai` | 时区 |
| `LOG_LEVEL` | `INFO` | 日志级别（DEBUG / INFO / WARNING / ERROR） |
| `PORT` | `8000` | 服务端口 |
| `SYNC_TASK_RETENTION_SECONDS` | `3600` | 已完成同步任务保留秒数 |
| `DISCOVER_TMDB_LATEST_EPISODES` | `false` | 是否为 TMDB 动漫额外用视频搜索探测最新集数 |
| `INVIDIOUS_FALLBACK_URLS` | 空 | 备用 Invidious 实例（逗号分隔） |
| `TG_BOT_TOKEN` / `TG_CHAT_ID` | 空 | Telegram Bot 推送 |

> Invidious 实例的权重、匹配阈值等更多配置可在登录后的「设置」页调整。

---

## 💾 数据备份

### JSON 备份

通过 Web 界面导出/导入，覆盖所有核心数据（动漫、集数、视频源、别名、规则、设置）。

### Bangumi / CSV 互通

支持导出为 Bangumi 追番列表格式或通用 CSV，便于与其他追番工具互通。

### Telegram 备份

配置 Telegram Bot 后支持手动触发或定时自动备份（可配置间隔）。

---

## 🔧 运维管理

### 查看日志

```bash
# Docker
docker compose logs -f zhuimange

# systemd
journalctl -u zhuimange -f
```

### 数据库备份

```bash
# 使用 sqlite3 备份（运行时）
sqlite3 data/tracker.db ".backup data/backup-$(date +%Y%m%d).db"
```

### 版本升级

```bash
# Docker
docker compose pull
docker compose up -d

# 单二进制
# 下载新版本二进制 → 停止旧进程 → 替换文件 → 重启
```

---

## 🧱 从 Python 版迁移

项目最初基于 Python/Flask 实现，现已完整迁移到 Go。Python 版源码保留在 `app/` 目录作为历史参考。

**数据库兼容**：Go 版表结构与 Python 版兼容，可直接复用原有 `data/tracker.db`。Go 版启动时会自动执行 schema 迁移（新增 `sync_jobs`/`watch_history`/`update_events`/`favorites` 等表），不影响原有数据。

---

## 🤝 贡献指南

1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 许可证

本项目采用 [MIT](LICENSE) 许可证
