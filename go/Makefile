# 追漫阁 Go 版 Makefile
# 用法：make <target>

GO        = go
BINARY    = zhuimange
MAIN_PKG  = ./cmd/zhuimange
VERSION  ?= dev
# CGO_ENABLED=0：modernc.org/sqlite 是纯 Go，可纯静态交叉编译
# -s -w：去除调试符号和 DWARF，减小体积
# -X main.version=$(VERSION)：注入版本号（可用 make VERSION=1.0.0）
LDFLAGS   = -s -w -X main.version=$(VERSION)

.PHONY: all build run tidy test vet fmt clean build-linux build-linux-arm64 build-windows build-darwin build-darwin-arm64 release help

## all: 默认目标，编译当前平台二进制
all: build

## build: 编译当前平台二进制（开发用，含调试符号）
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
	rm -rf $(BINARY) $(BINARY)-* dist/

## build-linux: 交叉编译 Linux amd64 二进制（服务器部署用）
build-linux:
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
	  $(GO) build -trimpath -ldflags="$(LDFLAGS)" -o $(BINARY)-linux-amd64 $(MAIN_PKG)

## build-linux-arm64: 交叉编译 Linux arm64 二进制（树莓派/ARM 服务器）
build-linux-arm64:
	CGO_ENABLED=0 GOOS=linux GOARCH=arm64 \
	  $(GO) build -trimpath -ldflags="$(LDFLAGS)" -o $(BINARY)-linux-arm64 $(MAIN_PKG)

## build-windows: 交叉编译 Windows amd64 二进制
build-windows:
	CGO_ENABLED=0 GOOS=windows GOARCH=amd64 \
	  $(GO) build -trimpath -ldflags="$(LDFLAGS)" -o $(BINARY)-windows-amd64.exe $(MAIN_PKG)

## build-darwin: 交叉编译 macOS amd64 二进制
build-darwin:
	CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 \
	  $(GO) build -trimpath -ldflags="$(LDFLAGS)" -o $(BINARY)-darwin-amd64 $(MAIN_PKG)

## build-darwin-arm64: 交叉编译 macOS arm64 二进制（Apple Silicon）
build-darwin-arm64:
	CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 \
	  $(GO) build -trimpath -ldflags="$(LDFLAGS)" -o $(BINARY)-darwin-arm64 $(MAIN_PKG)

## release: 本地打包所有平台二进制到 dist/（CI 用 GitHub Actions，此目标供本地测试）
release: clean build-linux build-linux-arm64 build-windows build-darwin build-darwin-arm64
	mkdir -p dist
	mv $(BINARY)-* dist/
	@cd dist && sha256sum * | tee SHA256SUMS.txt

## help: 显示帮助
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## //' | column -t -s ':'
