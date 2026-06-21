package store

import "os"

// mkdirAll 创建目录（与 os.MkdirAll 等价，独立出来便于测试 mock）。
func mkdirAll(dir string) error {
	return os.MkdirAll(dir, 0o755)
}
