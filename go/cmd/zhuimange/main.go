// 追漫阁 Go 版入口。
//
// 启动流程：加载配置 → 初始化数据库 → 初始化认证 → 注册路由 → 启动 HTTP 服务。
package main

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/lwhx/zhuimange/internal/auth"
	"github.com/lwhx/zhuimange/internal/backup"
	"github.com/lwhx/zhuimange/internal/config"
	"github.com/lwhx/zhuimange/internal/invidious"
	"github.com/lwhx/zhuimange/internal/notify"
	"github.com/lwhx/zhuimange/internal/scheduler"
	"github.com/lwhx/zhuimange/internal/source"
	"github.com/lwhx/zhuimange/internal/store"
	"github.com/lwhx/zhuimange/internal/syncsvc"
	"github.com/lwhx/zhuimange/internal/tmdb"
	"github.com/lwhx/zhuimange/internal/web/handler"
	"github.com/lwhx/zhuimange/internal/web/middleware"
)

// version 在 release 构建时由 -ldflags="-X main.version=..." 注入；
// 默认 dev 标记本地编译版本。
var version = "dev"

func main() {
	var (
		portFlag    = flag.Int("port", 0, "监听端口（覆盖环境变量 PORT）")
		versionFlag = flag.Bool("version", false, "打印版本号并退出")
	)
	flag.Parse()
	if *versionFlag {
		fmt.Println("zhuimange", version)
		return
	}

	// baseDir 优先使用当前工作目录的上级（仓库根），再退回到可执行文件位置。
	baseDir, _ := os.Getwd()
	if baseDir != "" {
		baseDir = filepath.Dir(baseDir)
	}
	if baseDir == "" {
		baseDir = filepath.Join(filepath.Dir(os.Args[0]), "..", "..")
	}
	if _, err := os.Stat(filepath.Join(baseDir, "data")); os.IsNotExist(err) {
		baseDir = filepath.Join(filepath.Dir(os.Args[0]), "..", "..")
	}

	// 加载 .env 文件（环境变量优先级高于 .env）
	config.LoadEnvFile(baseDir)

	// 加载配置
	cfg, err := config.Load(baseDir)
	if err != nil {
		slog.Error("加载配置失败", "error", err)
		os.Exit(1)
	}

	// 配置日志级别
	var level slog.Level
	switch cfg.LogLevel {
	case "DEBUG":
		level = slog.LevelDebug
	case "WARN":
		level = slog.LevelWarn
	case "ERROR":
		level = slog.LevelError
	default:
		level = slog.LevelInfo
	}
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: level})))

	slog.Info("追漫阁 Go 版启动中", "base_dir", baseDir, "port", effectivePort(cfg.Port, *portFlag))

	// 初始化数据库
	ctx := context.Background()
	st, err := store.Open(ctx, cfg.DatabasePath)
	if err != nil {
		slog.Error("数据库初始化失败", "error", err)
		os.Exit(1)
	}
	defer st.Close()

	// 初始化认证
	authenticator := auth.New(st, cfg.SecretKey, cfg.AuthSessionDays)

	// 初始化首次密码（仅在未设置时生成随机密码）
	if err := initPasswordIfNeeded(ctx, st, baseDir); err != nil {
		slog.Warn("初始化密码失败", "error", err)
	}

	// 限流器：200 请求/分钟（与 Python 版一致）
	limiter := middleware.NewRateLimiter(200, time.Minute)

	// 初始化调度器依赖并启动自动同步与定时备份
	invidiousClient := invidious.New(cfg, st)
	tmdbClient := tmdb.New(cfg)
	finder := source.NewFinder(cfg, st, invidiousClient)
	syncService := syncsvc.NewService(cfg, st, tmdbClient, finder)
	syncQueue := syncsvc.NewQueue(st, syncService)
	backupService := backup.NewService(st)
	scheduler.New(st, syncQueue, notify.NewTelegram(st), backupService).Start(ctx)

	// 路由（含静态文件服务）
	mux := handler.NewRouter(st, authenticator, limiter, cfg)

	// 启动 HTTP 服务
	addr := ":" + itoa(effectivePort(cfg.Port, *portFlag))
	srv := &http.Server{
		Addr:         addr,
		Handler:      mux,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 60 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	// 优雅关闭
	go func() {
		slog.Info("HTTP 服务监听", "addr", addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("HTTP 服务异常", "error", err)
			os.Exit(1)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	slog.Info("正在关闭服务...")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		slog.Error("强制关闭", "error", err)
	}
	slog.Info("服务已停止")
}

// generateRandomPassword 生成 URL-safe 随机密码（对齐 Python secrets.token_urlsafe(12)）。
func generateRandomPassword() string {
	b := make([]byte, 12)
	_, _ = rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}

// initPasswordIfNeeded 仅在 auth_password 未设置（首次启动）时初始化密码。
// 优先使用环境变量 INITIAL_PASSWORD（可在 .env 中填写）；未设置则生成随机密码。
// 已有密码绝不覆盖（避免重启覆盖用户修改过的密码）。
func initPasswordIfNeeded(ctx context.Context, st *store.Store, baseDir string) error {
	stored, _ := st.GetSetting(ctx, "auth_password", "")
	if strings.TrimSpace(stored) != "" {
		return nil // 已有密码，跳过
	}

	// 优先用 .env / 环境变量里的 INITIAL_PASSWORD
	password := strings.TrimSpace(os.Getenv("INITIAL_PASSWORD"))
	if password != "" {
		hash, err := auth.HashPassword(password)
		if err != nil {
			return err
		}
		if err := st.SetSetting(ctx, "auth_password", hash); err != nil {
			return err
		}
		slog.Info("已使用 INITIAL_PASSWORD 环境变量设置初始密码")
		return nil
	}

	// 未配置则生成随机密码（对齐 Python secrets.token_urlsafe(12)）
	password = generateRandomPassword()
	hash, err := auth.HashPassword(password)
	if err != nil {
		return err
	}
	if err := st.SetSetting(ctx, "auth_password", hash); err != nil {
		return err
	}

	slog.Warn("未配置 INITIAL_PASSWORD，已生成随机初始密码（可在 .env 设置 INITIAL_PASSWORD 预置密码），请立即登录并在设置中修改！此密码仅显示一次", "password", password)

	// 兜底留存：写入 data/.initial_password（仅属主可读）
	secretFile := filepath.Join(baseDir, "data", ".initial_password")
	_ = os.MkdirAll(filepath.Dir(secretFile), 0o755)
	if err := os.WriteFile(secretFile, []byte(password), 0o600); err != nil {
		slog.Warn("写入初始密码兜底文件失败", "error", err)
	}
	return nil
}

// effectivePort 优先用命令行参数，其次配置。
func effectivePort(cfgPort, flagPort int) int {
	if flagPort > 0 {
		return flagPort
	}
	return cfgPort
}

// itoa 简单的 int→string 转换（避免引入 strconv 仅为此）。
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [12]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
