package config

import (
	"bufio"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
)

// LoadEnvFile 从候选目录中查找并加载 .env 文件。
// 依次尝试每个候选目录，找到的第一个 .env 生效。
// 已存在的环境变量不会被覆盖（环境变量优先级高于 .env）。
func LoadEnvFile(dirs ...string) {
	for _, dir := range dirs {
		if dir == "" {
			continue
		}
		envPath := filepath.Join(dir, ".env")
		if info, err := os.Stat(envPath); err != nil || info.IsDir() {
			continue
		}
		if loaded := loadEnvFromFile(envPath); loaded > 0 {
			slog.Info("已加载 .env 文件", "path", envPath, "vars", loaded)
			return // 找到一个生效即可
		}
	}
	slog.Warn("未找到 .env 文件，请在仓库根或运行目录放置（环境变量仍可直接设置）")
}

// loadEnvFromFile 解析单个 .env 文件，返回成功加载的变量数。
func loadEnvFromFile(envPath string) int {
	f, err := os.Open(envPath)
	if err != nil {
		return 0
	}
	defer f.Close()

	loaded := 0
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		// 找第一个 = 号
		idx := strings.IndexByte(line, '=')
		if idx < 0 {
			continue
		}
		key := strings.TrimSpace(line[:idx])
		value := strings.TrimSpace(line[idx+1:])
		// 去掉首尾引号
		value = trimQuotes(value)
		// 已存在的环境变量不覆盖
		if os.Getenv(key) != "" {
			continue
		}
		os.Setenv(key, value)
		loaded++
	}
	return loaded
}

func trimQuotes(s string) string {
	if len(s) >= 2 {
		if (s[0] == '"' && s[len(s)-1] == '"') || (s[0] == '\'' && s[len(s)-1] == '\'') {
			return s[1 : len(s)-1]
		}
	}
	return s
}

