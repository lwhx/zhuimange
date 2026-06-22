// Package webassets 嵌入 Go 版前端模板和静态资源。
package webassets

import "embed"

// Templates 嵌入 HTML 模板文件。
//
//go:embed templates/*.html
var Templates embed.FS

// Static 嵌入静态资源文件。
//
//go:embed static/*
var Static embed.FS
