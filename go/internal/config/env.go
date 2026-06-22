package config

import (
	"bufio"
	"os"
	"path/filepath"
	"strings"
)

// LoadEnvFile 从 baseDir 下的 .env 文件加载环境变量。
// 格式：KEY=VALUE，支持 # 注释和空行。
// 已存在的环境变量不会被覆盖（环境变量优先级高于 .env）。
func LoadEnvFile(baseDir string) {
	envPath := filepath.Join(baseDir, ".env")
	f, err := os.Open(envPath)
	if err != nil {
		return // .env 不存在则跳过
	}
	defer f.Close()

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
	}
}

func trimQuotes(s string) string {
	if len(s) >= 2 {
		if (s[0] == '"' && s[len(s)-1] == '"') || (s[0] == '\'' && s[len(s)-1] == '\'') {
			return s[1 : len(s)-1]
		}
	}
	return s
}
