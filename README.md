<p align="center">
  <h1 align="center">🎬 追漫阁 - 国漫追更系统</h1>
  <p align="center">一个自部署的国漫追更管理平台，专为国漫爱好者打造</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Flask-3.0-green?logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/SQLite-嵌入式-lightblue?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Docker-支持-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">
</p>

---

## ✨ 功能特性

| 特性 | 描述 |
|------|------|
| 🔍 **TMDB 集成** | 自动从 TMDB 获取动漫信息、海报、集数数据 |
| 🎬 **视频源搜索** | 通过 Invidious API 搜索 YouTube 上的国漫视频源 |
| 🧠 **智能匹配** | 多重匹配算法（编辑距离、N-gram、精确匹配）+ 国漫别名库 |
| 🚫 **合集过滤** | 自动识别并过滤合集 / 剪辑 / 解说等非正片内容 |
| ⏰ **自动同步** | 支持全局和个别动漫的独立同步间隔设置 |
| 📊 **进度管理** | 追踪观看进度，标记已看 / 未看状态 |
| 💾 **数据备份** | 支持 JSON 导出 / 导入，以及 Telegram Bot 自动备份 |
| 🤖 **Telegram 通知** | 通过 Telegram Bot 推送更新通知与备份文件 |
| 🎨 **现代化 UI** | 深色主题、响应式设计、移动端友好 |

---

## 🛠️ 技术栈

**后端：** Python 3.11 · Flask 3.0 · SQLite · APScheduler  
**前端：** HTML5 / CSS3 / JavaScript（原生）· 响应式设计  
**外部服务：** TMDB API · Invidious API · Telegram Bot API  
**部署：** Docker & Docker Compose

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
  -e INVIDIOUS_URL=https://invidious.snopyta.org \
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
INVIDIOUS_URL=https://invidious.snopyta.org

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

### 方式二：本地运行

**1. 环境要求**

- Python 3.11+

**2. 安装依赖**

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

**3. 配置环境变量**

```bash
cp .env.example .env
# 编辑 .env 文件
```

**4. 启动应用**

```bash
python -m app.main
```

访问 `http://localhost:8000`

---

## 📁 项目结构

```
zhuimange/
├── app/
│   ├── main.py                  # 应用入口
│   ├── config.py                # 配置文件
│   ├── api/                     # API 路由
│   │   └── routes.py
│   ├── core/                    # 核心业务模块
│   │   ├── tmdb_client.py       # TMDB API 客户端
│   │   ├── invidious_client.py  # Invidious API 客户端
│   │   ├── source_finder.py     # 视频源查找器
│   │   ├── link_converter.py    # 链接转换器
│   │   ├── scheduler.py         # 任务调度器
│   │   ├── backup.py            # 数据备份与恢复
│   │   └── matcher/             # 匹配算法子模块
│   │       ├── preprocessor.py  # 文本预处理
│   │       ├── fuzzy_matcher.py # 模糊匹配
│   │       ├── collection_filter.py # 合集过滤
│   │       └── scorer.py        # 评分系统
│   ├── db/                      # 数据库模块
│   │   └── database.py
│   └── web/                     # Web 前端
│       ├── static/              # 静态资源
│       └── templates/           # HTML 模板
├── data/                        # 数据存储
│   └── tracker.db
├── .env.example                 # 环境变量模板
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 📡 API 概览

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/search?q={query}` | GET | 搜索动漫 |
| `/api/anime/add` | POST | 从 TMDB 添加动漫 |
| `/api/anime/add_manual` | POST | 手动添加动漫 |
| `/api/anime/{id}/sync` | POST | 同步视频源 |
| `/api/anime/{id}/episode/{num}/watch` | POST | 标记已看 |
| `/api/anime/{id}/progress` | PUT | 更新观看进度 |
| `/api/anime/{id}/rules` | PUT | 更新搜索规则 |
| `/api/settings` | GET/PUT | 获取 / 更新设置 |

> 完整 API 文档请参阅 [DEVELOPMENT.md](DEVELOPMENT.md)

---

## ⚙️ 配置说明

### 必需配置

| 配置项 | 说明 | 获取方式 |
|--------|------|----------|
| `TMDB_API_KEY` | TMDB API 密钥 | [申请地址](https://www.themoviedb.org/settings/api) |
| `INVIDIOUS_URL` | Invidious 实例地址 | [实例列表](https://docs.invidious.io/instances/) |

### 可选配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DATABASE_PATH` | `./data/tracker.db` | 数据库路径 |
| `TZ` | `Asia/Shanghai` | 时区 |
| `LOG_LEVEL` | `INFO` | 日志级别（DEBUG / INFO / WARNING / ERROR） |
| `SECRET_KEY` | - | Flask 密钥 |
| `PORT` | `8000` | 服务端口 |

---

## 💾 数据备份

### JSON 备份

系统支持通过 Web 界面进行数据的 JSON 导出和导入，覆盖所有核心数据（动漫、集数、视频源、别名、设置等）。

### Telegram 备份

可配置 Telegram Bot 自动备份：

1. 在设置页面填写 Telegram Bot Token 和 Chat ID
2. 支持手动触发备份
3. 支持定时自动备份（可配置间隔）

---

## 🔧 运维管理

### 查看日志

```bash
docker compose logs -f zhuimange
```

### 数据库备份

```bash
# 使用 sqlite3 备份
sqlite3 data/tracker.db ".backup data/backup-$(date +%Y%m%d).db"
```

### 版本升级

```bash
docker compose pull
docker compose up -d
```

---

## 🤝 贡献指南

1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

> 开发细节请参阅 [DEVELOPMENT.md](DEVELOPMENT.md)

---

## 📄 许可证

本项目采用 [MIT](LICENSE) 许可证
