# 追漫阁 Go 版 Makefile
# 用法：make <target>

GO        = go
BINARY    = zhuimange
MAIN_PKG  = ./cmd/zhuimange

.PHONY: all build run tidy test vet fmt clean migrate-linux migrate-windows help

## all: 默认目标，编译当前平台二进制
all: build

## build: 编译当前平台二进制
build:
	$(GO) build -o $(BINARY) $(MAIN_PKG)

## run: 直接运行（开发模式）
run:
	$(GO) run $(MAIN_PKG)

## tidy: 整理依赖
tidy:
	$(GO) mod tidy

## test: 运行测试
test:
	$(GO) test ./...

## vet: 静态检查
vet:
	$(GO) vet ./...

## fmt: 格式化代码
fmt:
	$(GO) fmt ./...

## clean: 清理构建产物
clean:
	rm -f $(BINARY) $(BINARY)-linux $(BINARY)-windows.exe

## migrate-linux: 交叉编译 Linux 二进制（服务器部署用）
migrate-linux:
	GOOS=linux GOARCH=amd64 $(GO) build -o $(BINARY)-linux -ldflags="-s -w" $(MAIN_PKG)

## migrate-windows: 交叉编译 Windows 二进制
migrate-windows:
	GOOS=windows GOARCH=amd64 $(GO) build -o $(BINARY)-windows.exe -ldflags="-s -w" $(MAIN_PKG)

## help: 显示帮助
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## //' | column -t -s ':'
