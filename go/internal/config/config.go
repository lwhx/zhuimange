// Package config 加载应用配置，支持环境变量与数据库设置双层配置。
//
// 环境变量在启动时加载（基础配置）；数据库 settings 表的配置可在运行时
// 通过设置页修改（如 invidious_url、match_threshold 等），由 store 层按需读取。
package config

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Config 持有应用启动时从环境变量加载的全部配置。
// 运行时可变的配置（如评分阈值、Invidious 实例）不在此处，由 store 层从 DB 读取。
type Config struct {
	// 基础
	BaseDir          string
	DatabasePath     string
	LogLevel         string
	Debug            bool
	TZ               string
	Port             int
	MetricsToken     string
	ProxyTrustedHops int

	// 会话安全
	SecretKey       string
	AuthSessionDays int

	// TMDB
	TMDBAPIKey   string
	TMDBBaseURL  string
	TMDBLanguage string

	// Invidious 基础（实例 URL 等运行时可改的配置由 store 层管理）
	InvidiousURL            string
	InvidiousFallbackURLs   []string
	InvidiousAPITimeout     int
	InvidiousPrimaryWeight  int
	InvidiousFallbackWeight int

	// 匹配参数（默认值，运行时部分可被 DB settings 覆盖）
	MatchThreshold          int
	MatchRecommendThreshold int
	MaxSearchResults        int
	SearchKeywordsLimit     int
	SourceSearchWorkers     int
	EpisodeSyncWorkers      int
	FuzzyNGramSize          int
	CollectionMaxDuration   int
	MaxSourcesPerEpisode    int

	// 评分权重（tie-breaker 六维权重，Go 版统一管理，消除 Python 版死代码）
	TieWeightTitle   float64
	TieWeightEpisode float64
	TieWeightChannel float64
	TieWeightRecency float64
	TieWeightView    float64
	TieWeightQuality float64

	// 评分阈值（集中管理，Python 版散落在多处）
	TitleStrongThreshold float64 // 标题强匹配阈值（75）
	TitleAcceptThreshold float64 // 标题接受阈值（30）
	ManualMatchThreshold int     // 手动添加动漫的匹配阈值（30）

	// 缓存与保留
	SyncTaskRetentionSeconds int
	SyncLogKeepDays          int

	// Telegram 基础（运行时可改的 token/chat_id 由 store 层管理）
	TgNotifyEnabled bool
}

// Load 从环境变量加载配置，应用默认值并持久化 SecretKey。
// baseDir 通常是仓库根目录（go 目录的上一级），用于定位 data 目录。
func Load(baseDir string) (*Config, error) {
	c := &Config{BaseDir: baseDir}

	// 基础配置
	c.DatabasePath = envStr("DATABASE_PATH", filepath.Join(baseDir, "data", "tracker.db"))
	c.LogLevel = envStr("LOG_LEVEL", "INFO")
	c.Debug = envBool("DEBUG", false)
	c.TZ = envStr("TZ", "Asia/Shanghai")
	c.Port = envInt("PORT", 8000)
	c.MetricsToken = envStr("METRICS_TOKEN", "")
	c.ProxyTrustedHops = envInt("PROXY_FIX_TRUSTED_HOPS", 1)
	c.AuthSessionDays = envInt("AUTH_SESSION_DAYS", 30)

	// TMDB
	c.TMDBAPIKey = envStr("TMDB_API_KEY", "")
	c.TMDBBaseURL = envStr("TMDB_BASE_URL", "https://api.themoviedb.org/3")
	c.TMDBLanguage = envStr("TMDB_LANGUAGE", "zh-CN")

	// Invidious
	c.InvidiousURL = strings.TrimRight(envStr("INVIDIOUS_URL", "https://yewtu.be"), "/")
	c.InvidiousFallbackURLs = envCSV("INVIDIOUS_FALLBACK_URLS", nil)
	c.InvidiousAPITimeout = envInt("INVIDIOUS_API_TIMEOUT", 30)
	c.InvidiousPrimaryWeight = envInt("INVIDIOUS_PRIMARY_WEIGHT", 7)
	c.InvidiousFallbackWeight = envInt("INVIDIOUS_FALLBACK_WEIGHT", 3)

	// 匹配参数
	c.MatchThreshold = envInt("MATCH_THRESHOLD", 50)
	c.MatchRecommendThreshold = envInt("MATCH_RECOMMEND_THRESHOLD", 70)
	c.MaxSearchResults = envInt("MAX_SEARCH_RESULTS", 50)
	c.SearchKeywordsLimit = envInt("SEARCH_KEYWORDS_LIMIT", 5)
	c.SourceSearchWorkers = envInt("SOURCE_SEARCH_WORKERS", 6)
	c.EpisodeSyncWorkers = envInt("EPISODE_SYNC_WORKERS", 6)
	c.FuzzyNGramSize = envInt("FUZZY_NGRAM_SIZE", 2)
	c.CollectionMaxDuration = envInt("COLLECTION_MAX_DURATION", 3600)
	c.MaxSourcesPerEpisode = envInt("MAX_SOURCES_PER_EPISODE", 10)

	// 评分权重（统一管理，与 Python 版 scorer._get_tiered_score 的硬编码值一致）
	c.TieWeightTitle = 0.35
	c.TieWeightEpisode = 0.20
	c.TieWeightChannel = 0.15
	c.TieWeightRecency = 0.15
	c.TieWeightView = 0.10
	c.TieWeightQuality = 0.50

	// 评分阈值集中管理（Python 版散落在 scorer.py / config.py 多处）
	c.TitleStrongThreshold = 75.0
	c.TitleAcceptThreshold = 30.0
	c.ManualMatchThreshold = 30

	// 缓存与保留
	c.SyncTaskRetentionSeconds = envInt("SYNC_TASK_RETENTION_SECONDS", 3600)
	c.SyncLogKeepDays = 90

	// Telegram
	c.TgNotifyEnabled = envBool("TG_NOTIFY_ENABLED", false)

	// SecretKey：持久化到 data/.secret_key，避免重启导致会话失效
	if err := c.loadOrGenerateSecretKey(); err != nil {
		return nil, fmt.Errorf("加载 SecretKey 失败: %w", err)
	}

	return c, nil
}

// loadOrGenerateSecretKey 优先用环境变量；未设置则持久化生成值到 data/.secret_key 复用。
func (c *Config) loadOrGenerateSecretKey() error {
	fromEnv := strings.TrimSpace(os.Getenv("SECRET_KEY"))
	placeholders := map[string]bool{"": true, "your-secret-key-change-this": true, "change-me": true}
	fromEnvLower := strings.ToLower(fromEnv)

	if fromEnv != "" && !placeholders[fromEnvLower] {
		c.SecretKey = fromEnv
		return nil
	}

	secretFile := filepath.Join(c.BaseDir, "data", ".secret_key")

	// 尝试读取已持久化的密钥
	if persisted, err := os.ReadFile(secretFile); err == nil {
		if v := strings.TrimSpace(string(persisted)); v != "" {
			c.SecretKey = v
			return nil
		}
	}

	// 生成新密钥并持久化
	bytes := make([]byte, 32)
	if _, err := rand.Read(bytes); err != nil {
		return fmt.Errorf("生成随机密钥失败: %w", err)
	}
	c.SecretKey = hex.EncodeToString(bytes)

	dataDir := filepath.Join(c.BaseDir, "data")
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		slog.Warn("无法创建 data 目录，使用临时密钥（重启后会话失效）", "error", err)
		return nil
	}
	if err := os.WriteFile(secretFile, []byte(c.SecretKey), 0o600); err != nil {
		slog.Warn("无法持久化 SecretKey，使用临时密钥（重启后会话失效）", "error", err)
		return nil
	}
	slog.Warn("SECRET_KEY 未配置，已自动生成并持久化。生产环境建议显式设置环境变量", "file", secretFile)
	return nil
}

// ==================== 环境变量辅助函数 ====================

func envStr(key, def string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v, ok := os.LookupEnv(key); ok {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func envBool(key string, def bool) bool {
	if v, ok := os.LookupEnv(key); ok {
		switch strings.ToLower(v) {
		case "true", "1", "yes":
			return true
		case "false", "0", "no":
			return false
		}
	}
	return def
}

func envCSV(key string, def []string) []string {
	v, ok := os.LookupEnv(key)
	if !ok {
		return def
	}
	parts := strings.Split(v, ",")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		item := strings.TrimSpace(part)
		if item != "" {
			result = append(result, strings.TrimRight(item, "/"))
		}
	}
	return result
}
