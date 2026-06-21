# 追漫阁 Go 重构 · 开发进度文档

> **用途**：记录 Go 重构的完整计划、已完成进度和剩余任务。下次开发时读取本文档继续。
>
> **当前分支**：`go-refactor`（Python 版在 `main` 分支，`app/` 目录保持不动）
> **Go 代码位置**：`go/` 子目录
> **最后更新**：阶段 3 大部分 + 阶段 4 已完成（代码核实，文档已同步）

---

## ⚠️ 文档校准说明（2026-06 更新）

此前文档仅记录到阶段 2，实际代码已推进到**阶段 3 大部分 + 阶段 4 全部**。本次校准依据代码实际存在性（非自述）。继续开发前请以本节为准。

---

## 快速恢复上下文

### 项目背景

追漫阁是个人动漫追更管理平台。核心循环：TMDB 拉动漫元数据 → Invidious 搜索/匹配视频源 → SQLite 存储 → SSR 渲染 → Telegram 推送。

Python/Flask 版（`main` 分支，`app/` 目录）功能成熟（6378 行），现用 Go 重写以获得：单二进制部署、更低内存、更易维护的评分器。

### 技术栈决策

| 层 | 选型 | 理由 |
|----|------|------|
| 语言 | Go 1.22+ | 静态编译、单二进制 |
| Web 框架 | `net/http` + `chi` | 轻量路由 |
| 数据库 | SQLite via `modernc.org/sqlite`（**纯 Go 无 CGO**） | 免交叉编译烦恼 |
| 前端 | Alpine.js 3 + HTMX 2 | 轻量、无构建、SSR 友好 |
| 调度 | `robfig/cron/v3` | 定时同步 |
| 模板 | `html/template` | 原生安全转义 |

### Go 环境配置（Windows）

Go SDK 安装在 `E:\go-sdk\go`（解压版，非系统安装）。执行 Go 命令需用完整路径或配置 PATH：

```bash
# 方式1：完整路径
E:/go-sdk/go/bin/go.exe build ./cmd/zhuimange

# 方式2：已 setx PATH 持久化（新终端生效）
set "PATH=E:\go-sdk\go\bin;%PATH%"
go build ./cmd/zhuimange
```

**Go 代理已设为国内源**：`go env -w GOPROXY=https://goproxy.cn,direct`

### 常用命令（在 `go/` 目录下执行）

```bash
cd go
go build -o zhuimange.exe ./cmd/zhuimange   # 编译
go run ./cmd/zhuimange -port 8001            # 直接运行
go mod tidy                                  # 整理依赖
go test ./...                                # 测试
GOOS=linux GOARCH=amd64 go build -o zhuimange-linux -ldflags="-s -w" ./cmd/zhuimange  # 交叉编译
```

---

## 总体进度

| 阶段 | 内容 | 状态 | 代码量 |
|------|------|------|--------|
| **1** | 地基（配置/数据库/认证/中间件） | ✅ 完成 | 2068 行 |
| **2** | 核心展示（TMDB/列表/详情/视频源/前端） | ✅ 完成 | 2061 行 |
| **3** | 同步引擎（Invidious/评分器/队列/SSE） | 🔶 大部分完成（缺 3.4 同步服务、3.5 队列+SSE） | 已写 1766 行 |
| **4** | 调度/通知/健康 | ✅ 完成（scheduler/health/notify 齐全） | 334 行 |
| **5** | 备份/导入导出 + 互通 | ⬜ 待开发 | — |
| **6** | 体验增强（日历/看板/播放/智能提醒） | ⬜ 待开发 | — |
| **7** | 部署/打磨/文档 | ⬜ 待开发 | — |

**累计**：约 6200 行 Go 代码（阶段1-4），20 个 .go 文件。

### 阶段 3 子任务细化（代码核实）

| 子任务 | 模块 | 状态 | 备注 |
|--------|------|------|------|
| 3.1 Invidious 客户端 | `internal/invidious/client.go` | ✅ 526 行 | 加权轮询/故障切换/重试/独立权重 |
| 3.2 评分器 | `internal/matcher/{filter,fuzzy,preprocessor,scorer}.go` | ✅ 552 行 | 4 文件，置信分层+多维排序 |
| 3.3 视频源发现 | `internal/source/finder.go` | ✅ 354 行 | 缓存/并发搜索/规则过滤 |
| 3.4 同步服务 | `internal/sync/` | ❌ **未创建** | run_anime_sync 主流程待写 |
| 3.5 同步队列+SSE | `internal/sync/` + `internal/web/sse/` | ❌ **未创建** | 任务持久化+流式推送待写 |

### 阶段 4 子任务细化（代码核实）

| 子任务 | 模块 | 状态 | 导出函数 |
|--------|------|------|---------|
| 调度器 | `internal/scheduler/scheduler.go` | ✅ 116 行 | New/Start/Stop/CheckAndSync |
| 健康诊断 | `internal/health/checker.go` | ✅ 119 行 | NewChecker/CheckInvidious/CheckSourceHealth/CheckSourcesBatch |
| Telegram 通知 | `internal/notify/telegram.go` | ✅ 99 行 | NewTelegram/SendMessage/SendNewEpisodeNotification/SendAlert |

---

## 下一步开发优先级

1. **阶段 3.4 同步服务** `internal/sync/service.go`——把 invidious/matcher/source 串成完整同步流程
2. **阶段 3.5 同步队列 + SSE**——任务持久化 + 流式进度推送，闭合"点同步→实时进度→入库"
3. 阶段 3 完成后做一次端到端冒烟（编译→运行→点同步→看进度）
4. 阶段 5-7 按计划推进

---

## 已完成阶段详情

### ✅ 阶段 1：地基（commit `b5d487c`）

**目录结构**（已创建）：
```
go/
├── cmd/zhuimange/main.go          # 入口（配置加载→数据库→认证→路由→HTTP服务→优雅关闭）
├── internal/
│   ├── config/                    # 配置
│   │   ├── config.go              # env 加载 + SecretKey 持久化 + 评分权重统一
│   │   └── dictionaries.go        # 业务字典（国漫别名/排除词/画质词/合集词）
│   ├── model/model.go            # 数据结构（Anime/Episode/Source/Alias/Rule/SyncJob 等）
│   ├── store/                     # SQLite 数据访问
│   │   ├── store.go              # 连接池(WAL+busy_timeout) + Open/Close
│   │   ├── migrate.go            # 自管理迁移 + settings CRUD + 全局别名种子
│   │   ├── anime.go              # Anime CRUD + scanAnime
│   │   └── migrations/0001_initial_schema.sql  # 16张表建表SQL
│   ├── auth/                      # 认证
│   │   ├── auth.go               # bcrypt + HMAC cookie session + Login/Logout
│   │   └── csrf.go               # CSRF 双重提交 cookie
│   └── web/
│       └── middleware/
│           ├── middleware.go      # 认证守卫 + 安全头(CSP) + 令牌桶限流
│           └── context.go        # session context
├── Makefile                       # build/run/test/migrate-linux
└── go.mod / go.sum
```

**关键设计**：
- 16 张表：兼容 Python 版 12 表 + 新增 4 表（sync_jobs/watch_history/update_events/favorites）
- 会话零存储：HMAC-SHA256 自签 cookie，无需服务端 session
- 评分权重统一：Python 版散落 4 处的阈值 + 死代码 `SCORE_WEIGHT_*`，Go 版归入 config
- 首次启动自动生成随机密码（打印到日志）

### ✅ 阶段 2：核心展示（commit `910b8b5`）

**新增文件**：
```
go/internal/
├── tmdb/tmdb.go                   # TMDB 客户端（搜索/详情/跨季集数）
├── store/
│   ├── episode.go                 # episodes CRUD（批量插入/已开播过滤/标记已看）
│   └── source.go                  # sources/aliases/rules/trusted_channels CRUD
└── web/
    ├── handler/
    │   ├── router.go              # 路由注册（含 AppHandlers 结构 + globalTmplMgr）
    │   ├── auth.go                # login/logout + 登录页HTML
    │   ├── page.go                # index/animeDetail/episodeSources 页面handler
    │   └── api.go                 # search/add/addManual/watch/progress/proxyImage API
    └── template/render.go         # 模板管理器（RenderPage + RenderPartial + 自定义函数）

go/web/
├── templates/
│   ├── base.html                  # 布局骨架（导航/Toast/模态容器）
│   ├── index.html                 # 首页卡片网格
│   ├── anime_detail.html          # 详情页+集数
│   └── sources_modal.html         # 视频源模态片段
└── static/
    ├── app.css                    # 主题CSS（6套配色）+ 组件样式
    ├── app.js                     # 前端交互（Toast/主题/搜索/CSRF/快捷键）
    ├── alpine.min.js              # Alpine.js 3.14.1（44KB）
    └── htmx.min.js                # HTMX 1.9.12（47KB）
```

**已实现的路由**：
- 页面：`GET /`（首页）、`GET /anime/{id}`（详情）、`GET /anime/{id}/episode/{ep}/sources`（源模态）
- API：`GET /api/search`、`POST /api/anime/add`、`POST /api/anime/add_manual`、`POST /api/anime/{id}/episode/{ep}/watch|unwatch`、`PUT /api/anime/{id}/progress`、`GET /api/proxy_image`
- 认证：`GET|POST /login`、`GET /logout`

**验证通过**：登录闭环、手动添加动漫、首页卡片、详情页集数、标记已看、进度更新、视频源模态、图片代理(SSRF拦截)。

---

### ✅ 阶段 3（部分）：同步引擎（commit 未单独标记）

> 阶段 3 的客户端/评分器/源发现已写完，但**同步服务主流程（3.4）和队列/SSE（3.5）尚未创建**，因此端到端同步闭环还未打通。

**已实现文件**：
```
go/internal/
├── invidious/client.go              # 加权轮询 + 故障切换 + 重试 + 每实例独立权重（526 行）
├── matcher/
│   ├── preprocessor.go              # 文本归一化 + 同音字 + 集数/季数提取
│   ├── fuzzy.go                     # 6 种模糊匹配取 max
│   ├── filter.go                    # 合集/非正片过滤
│   └── scorer.go                    # 置信分层 S/A/B/C + 多维 tie-breaker
└── source/finder.go                 # 缓存/并发搜索/规则过滤/评分入库（354 行）
```

**尚未创建**（阶段 3 收尾必需）：
```
go/internal/sync/service.go          # run_anime_sync 主流程（参考 app/core/sync_service.py）
go/internal/sync/queue.go            # 任务队列 + DB 持久化（参考 app/core/sync_queue.py）
go/internal/web/sse/                 # SSE 流式推送
```

---

### ✅ 阶段 4：调度/通知/健康

**已实现文件**：
```
go/internal/
├── scheduler/scheduler.go           # cron 定时同步（New/Start/Stop/CheckAndSync，116 行）
├── health/checker.go                # Invidious + 源健康（NewChecker/CheckInvidious/CheckSourceHealth/CheckSourcesBatch，119 行）
└── notify/telegram.go               # TG 推送（SendMessage/SendNewEpisodeNotification/SendAlert，99 行）
```

**待接线**：这些模块已写好但可能尚未在 router/main 中注册路由（诊断页 `/diagnostics`、统计页 `/stats` 需在阶段 5 设置页一起接入）。

---

## ⬜ 剩余阶段任务（待开发）

### 阶段 3：同步引擎（最复杂，核心价值）

> 这是整个重构的难点，也是选择 Go 重构的主要动机（"难以修改的用 Go 更方便"）。
> 建议分 3 步：① Invidious 客户端 → ② 评分器 → ③ 同步队列+SSE

#### 3.1 Invidious 客户端 `internal/invidious/`

**参考 Python 源码**：`app/core/invidious_client.py`（398 行）

需完全复刻的功能：
- [ ] 加权轮询 `_build_weighted_pool`：按每实例权重展开池（weight=3 → [url,url,url]）
- [ ] 轮询取实例 `_get_active_url`：`pool[_lb_index % len(pool)]`，`sync.Mutex` 保护 `_lb_index`
- [ ] 实例故障切换 `_switch_instance`：失败后逐个 `/api/v1/stats` 探测，`tried` 集合防死循环
- [ ] 请求重试循环 `_request`：失败→切换→重试，全失败抛错
- [ ] 每实例独立权重 `_load_instance_weights`：DB settings `invidious_instance_weights`（JSON `{url:weight}`）
- [ ] 默认权重 `_default_weights`：主实例固定7，备用把3整除均分（余数给前几个），精确复刻旧逻辑
- [ ] 配置热加载 `refresh_instances`：每次请求前从 DB 重载 primary/fallback/weights
- [ ] API 方法：`search_videos`（`/api/v1/search`）、`get_video_info`（`/api/v1/videos/{id}`）、`test_connection`
- [ ] 实例管理：`get_instance_urls`、`get_load_balance_summary`（生成 "7:2:1" 比例文本）
- [ ] 单例 + `reset`（设置变更时重建）

**关键文件**：`internal/invidious/client.go`

**Go 实现要点**：
- 用 `sync.Mutex` 替代 Python 的 `threading.Lock`
- HTTP 连接池复用：`http.Transport{MaxIdleConnsPerHost: N}`
- goroutine 安全（无 GIL）

#### 3.2 评分器 `internal/matcher/`（重构优化版）

**参考 Python 源码**：`app/core/matcher/`（scorer.py 303行 + preprocessor.py + fuzzy_matcher.py + collection_filter.py）

**你选择了"重构优化"策略**：统一权重配置，消除死代码。核心任务：

- [ ] **preprocessor.go**：文本归一化
  - OpenCC 繁简转换：用 `github.com/longbridgeapp/opencc`（纯 Go），迁移后用测试对比 Python 版输出
  - 同音字映射 `HOMOPHONE_MAP`（从 Python preprocessor.py 逐条迁移）
  - 去标点、空白归一、小写
  - 集数提取 `extract_episode_number`（5套正则 + 中文数字转换）
  - 季数提取 `extract_season_number`

- [ ] **fuzzy.go**：6种模糊匹配算法（取 max）
  - exact_match（100）、contains_match（85）
  - subsequence_match_ratio（≥0.8 ×80）、partial_char_match_ratio（≥0.7 ×70）
  - edit_distance（Levenshtein ×70）、ngram_similarity（Jaccard ×75）

- [ ] **filter.go**：合集/非正片过滤
  - 合集检测（关键词+范围正则`1-10集`+全集正则`全24集`+时长阈值）
  - 非正片检测（5组关键词 + 全局 EXCLUDE_KEYWORDS）

- [ ] **scorer.go**：综合评分（**最复杂**）
  - **置信分层**：S(90,集数+标题≥75+信任频道) / A(80,集数+标题≥75) / B(65,无集数+标题≥75) / C(35,其余)
  - **tie-breaker**：`base_score[tier] + min(9.99, (title×0.35+ep×0.20+ch×0.15+rec×0.15+view×0.10+qual×0.50)/10)`
  - **不变量**：tie_breaker ≤ 9.99 < 相邻 tier base 差(最小15)，保证跨层不越界
  - **统一配置**（重构重点）：所有权重和阈值写入 `config`，消除 Python 版硬编码
  - 维度分函数：`_get_quality_bonus`/`_get_channel_score`(trusted=100)/`_get_view_score`(阶梯)/`_get_recency_score`(阶梯)
  - 排序键 `source_sort_key`：置信等级优先，同级按多维度
  - `score_video`：硬过滤(合集/标题<30/集数不符)→阈值过滤→评分排序

- [ ] **验证**：用同一批 Invidious 搜索结果对比 Python 版评分，微调至一致

#### 3.3 视频源发现 `internal/source/`

**参考 Python 源码**：`app/core/source_finder.py`（432 行）

- [ ] `find_sources_for_episode(anime_id, ep_num, force)`
  - 缓存检查（非 force 直接返回已有源）
  - 取别名（custom + global）→ 生成关键词（名称+第N集+EPN，截断 SEARCH_KEYWORDS_LIMIT）
  - **并发搜索**：`errgroup` 替代 ThreadPoolExecutor，video_id 去重
  - 规则过滤（黑白名单 keywords/channels）
  - 评分排序，取前 MAX_SOURCES_PER_EPISODE 存库
- [ ] `discover_latest_episode(anime_id)`（手动动漫专用集数探测）

#### 3.4 同步服务 `internal/sync/`

**参考 Python 源码**：`app/core/sync_service.py`（330 行）

- [ ] `run_anime_sync(anime_id, mode, emit)`
  - 区分手动/TMDB 动漫
  - 刷新集数（TMDB: 拉季集数 / 手动: discover_latest_episode）
  - 过滤已开播、倒序
  - 规划同步清单（full全要 / incremental仅无源）
  - **并发同步单集**（errgroup + EPISODE_SYNC_WORKERS）
  - 发事件：start/plan/episode/poster/done/error
  - 手动动漫无封面→用首视频缩略图补封面

#### 3.5 同步队列 + SSE `internal/sync/` + `internal/web/sse/`

**参考 Python 源码**：`app/core/sync_queue.py`（216行）+ `app/api/routes.py:373-430`

- [ ] **任务队列**（内存 + DB持久化）
  - `SyncTask`：状态机 queued→running→success/error
  - 事件缓冲（环形/ring buffer，seq 单调递增）
  - `enqueue` 同动漫去重（已有 queued/running 则复用）
  - **DB持久化**：任务状态落 `sync_jobs` 表，进程重启可恢复（Python 版纯内存）
  - worker goroutine 消费队列
- [ ] **SSE 流式推送**（`internal/web/sse/`）
  - `channel` + `context` 实现事件推送
  - heartbeat 15s
  - seq 单调，断线重连
  - 响应头 `X-Accel-Buffering: no`（防 nginx 缓冲）

- [ ] **同步 API 路由**
  - `POST /api/anime/{id}/sync`（入队）
  - `GET /api/sync_tasks/{task_id}`（快照）
  - `GET /api/sync_tasks/{task_id}/stream`（SSE）

- [ ] **前端对接**：同步进度卡片（Alpine.js + SSE EventSource）

**阶段 3 交付物**：点同步→实时进度→视频源入库。

---

### 阶段 4：调度/通知/健康

**参考 Python 源码**：`scheduler.py`（277行）+ `backup.py`通知部分 + `invidious_health.py`（240行）

- [ ] **调度器** `internal/scheduler/`（`robfig/cron/v3`）
  - 定时自动同步（IntervalTrigger，间隔可配）
  - 动态 reschedule（设置页改间隔即时生效）
  - `check_and_sync`：遍历动漫，跳过已完结且已看完，串行同步
- [ ] **Telegram 通知** `internal/notify/`
  - `sendMessage`（新集推送 Markdown）
  - `sendDocument`（备份文件）
  - 告警（error/warning/info 带 emoji）
- [ ] **健康诊断** `internal/health/`
  - Invidious 实例健康（单飞锁 `sync.Once` + 并发探测各实例 stats + video）
  - 视频源健康（fail_count 累加，超阈值标 invalid）
- [ ] **诊断页** `GET /diagnostics` + `GET|POST /api/diagnostics/invidious`
- [ ] **统计页** `GET /stats`（概要卡片/状态分布/同步活动图）

**阶段 4 交付物**：自动同步、新集 TG 推送、诊断面板。

---

### 阶段 5：备份/导入导出 + 互通

**参考 Python 源码**：`backup.py`（373行）

- [ ] JSON 导出/导入（合并模式，按 tmdb_id 去重，恢复 watched）
- [ ] TG 备份 + 本地备份 + SHA256 校验
- [ ] **新增**：Bangumi 追番列表导入导出（animes 表已有 `bangumi_id` 字段）
- [ ] **新增**：通用追番列表 CSV 导出
- [ ] **设置页完整实现** `GET /settings`
  - 所有配置项（自动同步/匹配参数/Invidious实例编辑器+独立权重/TG/备份恢复）
  - `PUT /api/settings`（白名单字段 + 联动副作用：改间隔→reschedule、改实例→reset客户端）
  - 密码修改 `POST /api/change_password`

**阶段 5 交付物**：完整设置页 + 数据备份/互通。

---

### 阶段 6：体验增强（你选的 6 项功能）

- [ ] **追更日历 + 时间线**：`GET /calendar`（基于 air_date + sync_logs 展示每日更新）；时间线视图（watch_history 表）
- [ ] **追更看板/Dashboard**：聚合最新集、未看提醒、今日更新、快速标记卡片
- [ ] **播放体验增强**：视频源多源聚合、画质标记（quality_bonus）、收藏夹（favorites 表）、倍速记忆(localStorage)、预留弹幕接口
- [ ] **智能提醒推荐**：
  - 缺源提醒（有集无源的番）
  - 该追更了（超N天未更新）
  - TMDB 相似推荐（recommendations 表缓存）
- [ ] **导入导出互通**：Bangumi/CSV（阶段5）
- [ ] **移动端/订阅**：PWA（manifest + service worker）、RSS 订阅源 `/feed.xml`

**阶段 6 交付物**：完整的增强体验。

---

### 阶段 7：部署/打磨/文档

- [ ] **单二进制**：`go:embed` 嵌入静态资源；`make build` 产出 Linux/Windows 二进制；systemd service 模板
- [ ] **Docker**：多阶段 Dockerfile（builder + scratch 基础镜像），docker-compose.yml
- [ ] **数据迁移脚本** `go/web/migrate/`：从 Python 版 `data/tracker.db` 导入到新表
- [ ] 限流/Prometheus 指标/健康探针收尾
- [ ] README 更新（Go 版部署说明）
- [ ] Makefile 完善（build/run/test/migrate/cross-compile）

**阶段 7 交付物**：可部署的生产版本。

---

## 数据库表结构（16 张表）

兼容 Python 版（确保迁移脚本可直接导入）+ Go 版新增：

| 表 | 说明 | 来源 |
|----|------|------|
| animes | 动漫主表（新增 `bangumi_id`） | Python 兼容 |
| episodes | 集数（absolute_num 跨季连续编号，UNIQUE约束） | Python 兼容 |
| sources | 视频源（含健康字段） | Python 兼容 |
| custom_aliases | 自定义别名 | Python 兼容 |
| anime_source_rules | 搜索规则 | Python 兼容 |
| settings | 键值设置 | Python 兼容 |
| sync_logs | 同步日志 | Python 兼容 |
| trusted_channels | 信任频道 | Python 兼容 |
| global_aliases | 全局别名库（含18部国漫种子） | Python 兼容 |
| backup_logs | 备份日志 | Python 兼容 |
| **schema_migrations** | 迁移版本记录 | Go 新增 |
| **sync_jobs** | 同步任务持久化（进程重启可恢复） | Go 新增 |
| **watch_history** | 观看历史（时间线/统计） | Go 新增 |
| **update_events** | 更新事件流（日历/看板） | Go 新增 |
| **favorites** | 收藏夹 | Go 新增 |
| sqlite_sequence | SQLite 自增序列（自动） | 系统 |

迁移文件：`go/internal/store/migrations/0001_initial_schema.sql`

---

## 关键技术决策记录

1. **无 CGO**：用 `modernc.org/sqlite`，交叉编译 `GOOS=linux` 可直接产出服务器二进制
2. **会话零存储**：HMAC-SHA256 自签 cookie，无需服务端 session 表
3. **评分权重统一**：Python 版 `SCORE_WEIGHT_*` 是死代码，真实权重藏在 scorer 硬编码；Go 版归入 config 集中管理
4. **任务持久化**：Python 版同步队列纯内存（重启丢失），Go 版落 `sync_jobs` 表可恢复
5. **图片代理**：HTTPS 站点同源代理 HTTP 图片（CSP img-src 放宽 https/http），SSRF 白名单防护
6. **模板双模式**：`RenderPage`（base布局整页）+ `RenderPartial`（HTMX片段局部加载）

---

## Python 版参考文件索引

重构时对照阅读这些 Python 源码：

| Go 模块 | Python 参考文件 | 行数 |
|---------|----------------|------|
| config | `app/config.py` | 135 |
| model | `app/db/database.py`（表结构） | — |
| store | `app/db/database.py`（CRUD） | ~1000 |
| tmdb | `app/core/tmdb_client.py` | 180 |
| invidious | `app/core/invidious_client.py` | 398 |
| matcher/scorer | `app/core/matcher/scorer.py` | 303 |
| matcher/preprocessor | `app/core/matcher/preprocessor.py` | 160 |
| matcher/fuzzy | `app/core/matcher/fuzzy_matcher.py` | 185 |
| matcher/filter | `app/core/matcher/collection_filter.py` | 154 |
| source | `app/core/source_finder.py` | 432 |
| sync | `app/core/sync_service.py` | 330 |
| sync(queue) | `app/core/sync_queue.py` | 216 |
| scheduler | `app/core/scheduler.py` | 277 |
| health | `app/core/invidious_health.py` + `source_health.py` | 240+140 |
| backup | `app/core/backup.py` | 373 |
| web/handler | `app/api/routes.py` + `app/main.py` | 810+480 |
| auth | `app/core/auth.py` | 61 |

---

## 验证方法

每个阶段完成后，按此流程验证：

```bash
cd go

# 1. 编译
go build -o zhuimange.exe ./cmd/zhuimange

# 2. 清理旧测试数据，启动
rm -rf data && go run ./cmd/zhuimange -port 8001
# 记下日志里的随机密码

# 3. 功能测试（用 curl 或浏览器）
curl -s -c cookie.txt http://127.0.0.1:8001/login -o /dev/null
CSRF=$(grep zmg_csrf cookie.txt | awk '{print $NF}')
curl -s -b cookie.txt -c cookie.txt -X POST http://127.0.0.1:8001/login -d "password=<密码>" -H "X-CSRF-Token: $CSRF" -o /dev/null -w "%{http_code}\n"
# 应返回 302（登录成功）

# 4. 访问页面验证
curl -s -b cookie.txt http://127.0.0.1:8001/  # 首页

# 5. 清理
rm -rf data zhuimange.exe
```
