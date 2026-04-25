# 追漫阁项目全面解读报告

## 1. 项目背景与定位

“追漫阁”是一个个人自部署的动漫追更管理平台，核心目标是帮助用户管理追更列表、记录观看进度、自动搜索视频源，并通过定时同步和备份机制降低维护成本。项目特别偏向中文动漫/国漫场景，针对视频标题中的繁简混用、别名、谐音规避、合集、剪辑、解说等问题设计了专门的匹配与过滤逻辑。

项目整体定位是轻量级个人 Web 工具，而不是高并发多租户平台。因此它选择 Flask、SQLite、原生 JavaScript、Docker Compose 这类简单、稳定、易部署的技术组合。

## 2. 核心功能概览

| 功能模块 | 说明 |
| --- | --- |
| 动漫管理 | 支持从 TMDB 搜索并添加动漫，也支持手动添加动漫 |
| 集数管理 | 可从 TMDB 拉取集数，也可从视频搜索结果探测手动动漫最新集数 |
| 观看进度 | 支持单集标记已看/未看，支持批量更新已看进度 |
| 视频源搜索 | 使用 Invidious 搜索 YouTube 视频源，并通过评分算法筛选 |
| 自动同步 | 使用 APScheduler 定时同步所有需要更新的动漫 |
| 实时进度 | 使用 SSE 将同步进度实时推送给前端 |
| 搜索规则 | 支持每部动漫配置允许/拒绝关键词和频道 |
| 别名体系 | 支持单部动漫别名和全局别名库，提高匹配成功率 |
| 统计看板 | 展示总动漫数、总集数、已看集数、完成率、待看排行等 |
| 备份恢复 | 支持 JSON 导出导入、本地备份、Telegram 备份和备份日志 |
| 安全运维 | 登录认证、CSRF、防 XSS 响应头、限流、健康检查、Prometheus 指标 |

## 3. 技术架构与选型依据

### 3.1 后端技术栈

- Python 3.11：生态成熟，适合 Web、自动化和 API 聚合。
- Flask 3.0：轻量、灵活，适合个人工具和中小型应用。
- SQLite：零运维、本地持久化、备份方便，适合单用户部署。
- APScheduler：用于应用内定时同步和定时备份。
- requests：用于调用 TMDB、Invidious、Telegram API。
- Alembic：负责数据库结构迁移。
- bcrypt：用于安全存储访问密码。
- Flask-WTF：提供 CSRF 防护。
- Flask-Limiter：提供基础请求限流。
- Flask-Caching：缓存首页和详情页，降低重复查询开销。
- prometheus-client：暴露请求指标，方便监控。

### 3.2 前端技术栈

- Jinja2：服务端模板渲染，和 Flask 集成成本低。
- 原生 JavaScript：无需构建流程，部署简单。
- CSS 变量：实现深浅色和多主题切换。
- EventSource/SSE：用于同步任务实时进度推送，复杂度低于 WebSocket。

### 3.3 外部服务

- TMDB API：提供动漫元数据、封面、简介、季和集数信息。
- Invidious API：作为 YouTube 搜索代理，用于查找视频源。
- Telegram Bot API：用于发送新集通知和备份文件。

### 3.4 部署架构

项目通过 Dockerfile 多阶段构建镜像，运行时使用 gunicorn gthread worker 启动 Flask 应用。docker-compose 将端口绑定到 `127.0.0.1:8280:8000`，默认仅本机访问，适合配合反向代理使用。数据通过 `./data:/app/data` 持久化。

值得注意的是，Dockerfile 中创建了非 root 用户并切换到 `appuser`，但 docker-compose 中设置了 `user: "0:0"`，这会覆盖镜像中的非 root 策略。若部署到生产环境，建议确认是否确实需要 root 权限。

## 4. 项目目录结构

```text
zhuimange/
├── app/
│   ├── main.py                  # Flask 应用入口、页面路由、中间件、健康检查
│   ├── config.py                # 环境变量、匹配参数、外部 API、别名与排除词配置
│   ├── api/routes.py            # REST API、同步流、设置、备份、日志等接口
│   ├── core/                    # 业务核心模块
│   ├── db/                      # SQLite 数据库访问与迁移
│   └── web/                     # Jinja2 模板与静态资源
├── migrations/                  # Alembic 迁移脚本
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
└── DEVELOPMENT.md
```

## 5. 整体架构说明

项目采用轻量分层架构：

```text
浏览器
  ↓ HTTP / JSON / SSE
Flask 应用层
  ├── 页面路由：首页、详情、设置、统计
  ├── API 路由：动漫管理、视频源、同步、备份、设置
  ├── 中间件：认证、限流、缓存、安全响应头、指标
  ↓
业务核心层
  ├── TMDB 元数据获取
  ├── Invidious 视频搜索
  ├── 视频源匹配与评分
  ├── 自动同步和通知
  ├── 备份恢复
  ↓
数据访问层
  ├── SQLite 数据库
  ├── CRUD 函数
  ├── 统计查询
  ├── 日志记录
  ↓
外部服务
  ├── TMDB
  ├── Invidious
  └── Telegram
```

应用启动流程集中在 `create_app`：创建 Flask 实例，初始化 CSRF、限流、缓存，初始化数据库和默认密码，测试 Invidious 连接，注册 API 和页面路由，注册错误处理、安全响应头和健康检查，最后启动定时调度器。

## 6. 数据模型与数据流程

### 6.1 核心数据表

| 表名 | 用途 | 关键字段 |
| --- | --- | --- |
| animes | 动漫主表 | tmdb_id, title_cn, poster_url, total_episodes, watched_ep, status, last_sync_at |
| episodes | 集数表 | anime_id, season_number, episode_number, absolute_num, air_date, watched |
| sources | 视频源表 | episode_id, video_id, title, channel_id, duration, view_count, match_score, is_valid |
| custom_aliases | 单部动漫别名 | anime_id, alias |
| global_aliases | 全局别名库 | title, alias, category |
| anime_source_rules | 单部搜索规则 | allow_keywords, deny_keywords, allow_channels, deny_channels |
| settings | 系统设置 | key, value |
| sync_logs | 同步日志 | anime_id, sync_type, episodes_synced, sources_found, status |
| trusted_channels | 信任频道 | channel_id, channel_name, priority |
| backup_logs | 备份日志 | backup_type, status, file_size, file_name, error_code |

### 6.2 实体关系

```text
animes 1 ─── N episodes 1 ─── N sources
   │
   ├── N custom_aliases
   ├── 1 anime_source_rules
   └── N sync_logs

settings、global_aliases、trusted_channels、backup_logs 为独立辅助表。
```

### 6.3 数据库实现特点

数据库层直接使用 sqlite3，而不是 ORM。这样依赖更少、SQL 更可控，符合个人工具的轻量定位。实现中启用了 WAL 模式和外键约束，使用简易连接池降低连接创建成本，并对常用外键字段建立索引。`get_all_animes_with_stats` 使用 JOIN 聚合统计首页数据，避免对每部动漫重复查询集数造成 N+1 查询问题。

## 7. 主要模块解析

### 7.1 app/main.py

这是应用装配中心，负责 Flask 应用工厂、登录认证、页面路由、错误处理、安全响应头、健康检查和指标端点。它通过 session 判断用户是否已登录，并对 API 和页面请求采用不同处理方式：API 未认证返回 401，页面未认证跳转登录页。

该模块还实现了首次启动密码初始化。如果数据库中没有 `auth_password`，系统会生成随机初始密码并写入 settings 表。密码验证支持旧 SHA-256 哈希，并在登录成功后升级为 bcrypt。

### 7.2 app/api/routes.py

API 层承载主要业务入口，包括搜索动漫、添加动漫、删除动漫、更新观看进度、搜索视频源、同步视频源、设置管理、别名管理、备份恢复和日志查询。

其中 `/api/anime/<anime_id>/sync_stream` 是关键接口。它使用 SSE 分阶段输出同步状态：更新 TMDB 集数、探测手动动漫集数、逐集并发同步视频源、更新封面、写入同步日志并返回完成事件。前端可以实时显示同步进度，而不需要轮询。

### 7.3 app/db/database.py

该模块是数据访问层，负责数据库连接、初始化、CRUD、统计和日志。重要设计包括：

- `_ANIME_UPDATABLE_FIELDS` 白名单限制可更新字段，降低动态 SQL 风险。
- `mark_episode_watched` 在更新单集状态后同步更新 `animes.watched_ep`。
- `add_source` 避免同一集重复写入同一 video_id。
- `get_episode_source_counts` 用于详情页展示视频源数量，也用于同步前后比较新增视频源。
- `get_watch_stats` 汇总统计面板数据。

### 7.4 app/core/tmdb_client.py

TMDB 客户端负责元数据获取。它使用 `requests.Session` 统一携带 API key 和语言参数。获取详情时会过滤特别篇季，并将多季集数转换为连续的 `absolute_num`，这样前端和用户可以用“第 N 集”统一理解进度。

### 7.5 app/core/invidious_client.py

Invidious 客户端负责视频搜索，并支持备用实例故障切换。请求失败时会切换实例并重试一次。这对依赖公共 Invidious 实例的项目非常重要，因为公共实例稳定性通常不可控。

### 7.6 app/core/source_finder.py

这是视频源搜索和同步的核心模块。`find_sources_for_episode` 的流程是：

1. 查询动漫和集数。
2. 非强制搜索时优先返回缓存视频源。
3. 合并自定义别名和全局别名。
4. 生成搜索关键词，例如“动漫名 第12集”和“动漫名 EP12”。
5. 调用 Invidious 搜索。
6. 按 video_id 去重。
7. 应用允许/拒绝关键词和频道规则。
8. 根据是否手动添加动漫选择匹配阈值。
9. 对候选视频评分并过滤低分结果。
10. 保存排名靠前的视频源。

`sync_anime_sources` 负责整部动漫同步，先尝试从 TMDB 更新集数，再探测最新集数，最后通过线程池并发同步每集视频源。

### 7.7 app/core/matcher

匹配算法被拆成四个清晰模块：

- `preprocessor.py`：文本归一化、繁简转换、同音字替换、集数提取、中文数字转换。
- `fuzzy_matcher.py`：精确匹配、包含匹配、子序列匹配、字符重叠、编辑距离、N-gram 相似度。
- `collection_filter.py`：过滤合集、全集、剪辑、解说、预告、OP/ED/OST、AMV/MAD 等非正片内容。
- `scorer.py`：综合标题匹配、集数匹配、频道信任、时效性和画质加分，输出最终分数。

评分权重为：标题匹配 40%、集数匹配 30%、频道信任 15%、时效性 15%，并额外对 4K、1080p、蓝光、高清等画质关键词加分。

### 7.8 app/core/scheduler.py

调度器使用 APScheduler 在后台周期执行同步任务。它会读取 settings 表判断自动同步是否启用，并跳过已完结且已看完的动漫。若开启 Telegram 通知，则同步前后比较每集视频源数量，发现新增视频源后发送通知。它还支持定时 Telegram 备份，并允许运行时更新同步间隔和备份计划。

### 7.9 app/core/backup.py

备份模块支持完整数据导出和恢复。导出内容包括动漫、集数、视频源、别名、搜索规则和设置。导入采用合并模式，不删除现有数据。它还支持发送备份到 Telegram、本地保存备份、计算 SHA256 校验和、验证备份完整性，并将备份结果写入 `backup_logs`。

### 7.10 前端 app.js 与模板

前端采用 Jinja2 模板加原生 JavaScript。`base.html` 定义导航栏、主题切换、CSRF token、模态框和 Toast 容器。`index.html` 展示追更列表、搜索框和手动添加表单。`app.js` 负责主题管理、API 请求封装、搜索防抖、添加动漫、进度更新、视频源弹窗和 SSE 同步进度。

前端对动态插入内容使用 `escapeHtml`，并在 API 请求中自动带上 CSRF token，安全意识较好。

## 8. 关键算法解析

### 8.1 搜索关键词生成

关键词来源包括动漫中文标题、自定义别名和全局别名。每个名称会生成“第 N 集”和“EP N”两类关键词。这种方式兼顾中文标题和英文/缩写标题，有助于提升视频源命中率。

### 8.2 文本归一化

文本预处理会进行繁简转换、同音字替换、标点清理、空白归一化和小写化。该逻辑是国漫场景的关键，因为视频标题常见错别字、缺字、繁体字和规避版权写法。

### 8.3 集数提取

集数提取支持“第12集”“EP12”“E12”“#12”“12集”“第五集”等格式，并支持中文数字转换。这使系统可以从多种视频标题格式中识别目标集数。

### 8.4 模糊匹配

模糊匹配不是单一算法，而是综合多个维度并取最高分。包含匹配适合标题完整包含动漫名的情况，子序列匹配适合缺字标题，字符重叠适合同音字替换后仍有差异的情况，编辑距离和 N-gram 则补充一般相似度判断。

### 8.5 综合评分

综合评分先过滤明显非正片，再计算标题、集数、频道和时效分。集数完全匹配给 100 分，相邻集数只给 30 分，差距较大为 0 分。频道信任分优先看 trusted_channels，否则按观看量给分。时效分根据发布时间从 7 天内到 1 年以上逐级降低。

## 9. 设计理念

项目的核心设计理念可以概括为：

1. 轻量部署优先：使用 Flask、SQLite、原生前端和 Docker Compose，降低运行门槛。
2. 数据本地优先：追更数据保存在本地 SQLite，便于迁移和备份。
3. 自动化优先：通过 TMDB、Invidious、APScheduler 自动补充元数据和视频源。
4. 中文场景适配：通过别名库、繁简转换、同音字替换、中文集数提取适配国漫标题。
5. 可解释匹配：评分结果由多个维度组成，便于调试和调整阈值。
6. 安全基础完备：认证、CSRF、bcrypt、限流、安全响应头和指标都已具备。

## 10. 可扩展性评估

### 10.1 优势

- 模块边界清晰，API、数据库、核心服务、匹配算法、前端模板分离明确。
- 外部 API 客户端封装良好，未来可以新增 B站、Bangumi 等数据源。
- 匹配算法拆分合理，后续可替换为更高级的相似度算法或机器学习模型。
- settings 表支持运行时配置扩展。
- Alembic 已接入，便于数据库结构演进。

### 10.2 限制

- SQLite 适合单用户和低并发，不适合多用户高并发场景。
- 业务逻辑主要是函数式组织，规模继续扩大后可能需要服务类或领域层重构。
- 没有用户体系，当前更像单管理员应用。
- 调度器运行在 Web 进程内，横向扩容时可能出现重复任务问题。
- 视频源搜索依赖 Invidious 公共实例，稳定性受外部影响。

### 10.3 扩展建议

- 若支持多用户，应引入用户表、权限模型和数据隔离字段。
- 若支持高并发，应考虑 PostgreSQL/MySQL，并将调度器拆成独立 worker。
- 若增加多视频平台，可抽象 `VideoSearchProvider` 接口。
- 若增强匹配精度，可加入历史点击反馈、频道白名单权重和标题黑名单学习。

## 11. 可维护性评估

### 11.1 优点

- 目录结构清晰，文件职责明确。
- 统一响应封装降低 API 格式分散风险。
- 数据库访问集中在 database.py，便于统一修改。
- 匹配算法拆分清楚，便于单独测试和优化。
- README 和 DEVELOPMENT 文档较完整。

### 11.2 风险点

- `routes.py` 职责较多，包含大量接口和同步流逻辑，后续可按领域拆分为多个蓝图。
- `database.py` 文件较大，未来可拆分为 anime_repo、episode_repo、source_repo、settings_repo 等模块。
- 前端 `app.js` 承担了主题、搜索、同步、备份等多类逻辑，后续可拆分为多个 JS 文件。
- 部分业务配置写在 config.py 静态列表中，若希望在线维护，需要迁移到数据库。

## 12. 性能表现评估

### 12.1 已有优化

- 首页列表使用 JOIN 聚合，避免 N+1 查询。
- SQLite 开启 WAL，提高读写并发能力。
- 使用简单连接池复用连接。
- 首页和详情页使用缓存。
- 视频源同步使用线程池并发处理集数。
- Invidious 请求使用 Session 复用连接。
- 视频源结果会缓存到数据库，非强制模式下无需重复搜索。

### 12.2 潜在性能瓶颈

- 整部动漫同步时，每集会生成多个关键词并搜索，外部 API 请求量较大。
- SQLite 在高并发写入或多用户场景下会成为瓶颈。
- 同步任务在 Web 进程内执行，长任务可能影响 Web 服务资源。
- Flask-Caching 使用 SimpleCache，进程内缓存不适合多进程共享。
- `sync_stream` 中并发线程数量固定为 4，对不同 Invidious 实例的速率限制适配不足。

### 12.3 优化建议

- 为每部动漫设置更细粒度的同步策略，只同步最新若干集或未找到源的集数。
- 增加搜索结果缓存，避免相同关键词短时间重复请求 Invidious。
- 将同步任务迁移到独立 worker，Web 进程只负责触发和展示状态。
- 若部署规模扩大，可将 SQLite 替换为 PostgreSQL。
- 对 Invidious 请求增加退避重试和实例健康评分。

## 13. 安全性评估

### 13.1 已有安全措施

- 登录密码使用 bcrypt 哈希。
- 支持旧哈希自动升级。
- 使用 CSRF token。
- 登录接口限流。
- 设置 CSP、X-Frame-Options、X-Content-Type-Options 等响应头。
- API 未认证返回 401。
- 动态 SQL 更新字段使用白名单。
- 前端动态内容使用 HTML 转义。
- Prometheus 指标可配置 token。

### 13.2 安全风险与建议

- docker-compose 使用 root 用户运行，建议确认必要性，优先使用非 root。
- CSP 中允许 `unsafe-inline`，这是为了兼容当前模板内联脚本和样式，但安全性较弱。后续可逐步迁移到外部 JS/CSS 并收紧 CSP。
- SECRET_KEY 若不配置会随机生成，重启后 session 会失效。生产环境应显式配置。
- Telegram token 等敏感配置应只通过 `.env` 或 settings 存储，避免提交到仓库。
- 当前是单密码应用，不支持多用户审计和权限分级。

## 14. 潜在挑战与解决方案

| 挑战 | 影响 | 建议方案 |
| --- | --- | --- |
| Invidious 实例不稳定 | 视频源搜索失败 | 增加实例健康评分、自动降级、更多 fallback |
| 视频标题不规范 | 匹配误判或漏判 | 持续扩充别名库、同音字库和排除词库 |
| 外部 API 限流 | 同步失败或变慢 | 增加缓存、退避重试、减少全量同步 |
| SQLite 并发限制 | 多用户或高并发下写入瓶颈 | 迁移 PostgreSQL/MySQL |
| 调度器与 Web 进程耦合 | 横向扩容会重复执行任务 | 拆分 worker 或使用任务队列 |
| 单文件路由膨胀 | 维护成本上升 | 按业务拆分蓝图和服务层 |

## 15. 关键代码位置

| 文件 | 说明 |
| --- | --- |
| `app/main.py` | 应用入口、认证、中间件、页面路由、健康检查 |
| `app/api/routes.py` | API 路由、SSE 同步流、备份和设置接口 |
| `app/db/database.py` | 数据库连接、初始化、CRUD、统计 |
| `app/core/source_finder.py` | 视频源搜索、探测和同步核心逻辑 |
| `app/core/matcher/scorer.py` | 视频源综合评分算法 |
| `app/core/matcher/preprocessor.py` | 文本归一化与集数提取 |
| `app/core/matcher/fuzzy_matcher.py` | 模糊匹配算法 |
| `app/core/matcher/collection_filter.py` | 合集和非正片过滤 |
| `app/core/tmdb_client.py` | TMDB API 客户端 |
| `app/core/invidious_client.py` | Invidious API 客户端 |
| `app/core/scheduler.py` | 定时同步和通知 |
| `app/core/backup.py` | 备份、恢复和校验 |
| `app/web/static/app.js` | 前端交互逻辑 |
| `docker-compose.yml` | Docker Compose 部署配置 |
| `Dockerfile` | 镜像构建与运行配置 |

## 16. 总结

追漫阁是一个架构清晰、功能闭环较完整的个人动漫追更平台。它的最大亮点在于围绕“自动找源”建立了一套从关键词生成、标题归一化、集数提取、非正片过滤到综合评分的完整链路，并通过定时同步、SSE 进度推送和备份恢复增强了日常使用体验。

从当前规模看，Flask + SQLite + 原生前端的组合非常合适，部署简单、维护成本低。未来如果项目要从个人工具扩展为多人或公网服务，重点需要改进用户体系、任务队列、数据库扩展性、路由模块拆分和外部视频源提供者抽象。
