// 追漫阁 Go 版入口。
//
// 启动流程：加载配置 → 初始化数据库 → 初始化认证 → 注册路由 → 启动 HTTP 服务。
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"flag"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/lwhx/zhuimange/internal/auth"
	"github.com/lwhx/zhuimange/internal/config"
	"github.com/lwhx/zhuimange/internal/store"
	"github.com/lwhx/zhuimange/internal/web/handler"
	"github.com/lwhx/zhuimange/internal/web/middleware"
)

func main() {
	var portFlag = flag.Int("port", 0, "监听端口（覆盖环境变量 PORT）")
	flag.Parse()

	// baseDir 通常是仓库根（go/ 的上一级），用于定位 data 目录
	baseDir := filepath.Join(filepath.Dir(os.Args[0]), "..", "..")
	// 开发时直接 go run，baseDir 取当前工作区的上级
	if _, err := os.Stat(filepath.Join(baseDir, "data")); os.IsNotExist(err) {
		// 尝试 go/ 的上一级（仓库根）
		cwd, _ := os.Getwd()
		parent := filepath.Dir(cwd)
		if _, err := os.Stat(filepath.Join(parent, "data")); err == nil {
			baseDir = parent
		}
	}

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

	// 初始化首次密码（若未设置）
	if err := initPasswordIfNeeded(ctx, st); err != nil {
		slog.Warn("初始化密码失败（可能已设置）", "error", err)
	}

	// 限流器：200 请求/分钟（与 Python 版一致）
	limiter := middleware.NewRateLimiter(200, time.Minute)

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

// generateRandomPassword 生成 16 字节随机密码（hex 编码）。
func generateRandomPassword() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

// initPasswordIfNeeded 首次启动时若未设置密码，生成随机密码并打印到日志。
// 与 Python 版 _consume_initial_password 机制一致。
func initPasswordIfNeeded(ctx context.Context, st *store.Store) error {
	existing, err := st.GetSetting(ctx, "auth_password", "")
	if err != nil {
		return err
	}
	if existing != "" {
		return nil
	}
	// 生成随机密码
	pwd := generateRandomPassword()
	hash, err := auth.HashPassword(pwd)
	if err != nil {
		return err
	}
	if err := st.SetSetting(ctx, "auth_password", hash); err != nil {
		return err
	}
	slog.Info("========================================")
	slog.Info("首次启动：已生成随机访问密码", "password", pwd)
	slog.Info("请记录此密码，登录后可在设置页修改")
	slog.Info("========================================")
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
