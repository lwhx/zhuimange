// Package template 封装 HTML 模板渲染。
//
// 设计：base.html 定义布局骨架（含 {{block "content" .}}），
// 每个页面模板文件定义 {{define "content"}}...{{end}} 填充内容。
// 渲染某页面时，加载 base.html + 该页面文件组成独立 template set，
// 避免多个页面的 content block 冲突。
package template

import (
	"fmt"
	"html/template"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Manager 管理模板渲染。预加载 base 布局源码，渲染时合并具体页面。
type Manager struct {
	templateDir string
	baseSource  string // base.html 的源码，缓存避免重复读取
	funcMap     template.FuncMap
}

// New 创建模板管理器。
func New(templateDir string) (*Manager, error) {
	funcMap := template.FuncMap{
		"add":       func(a, b int) int { return a + b },
		"sub":       func(a, b int) int { return a - b },
		"mod":       func(a, b int) int { return a % b },
		"join":      strings.Join,
		"hasPrefix": strings.HasPrefix,
		"lower":     strings.ToLower,
		"proxyImg":  proxyImgFilter,
		// sinceCN 将时间格式化为中文相对时间（如"3小时前"）
		"sinceCN": func(t time.Time, now time.Time) string {
			d := now.Sub(t)
			switch {
			case d < time.Minute:
				return "刚刚"
			case d < time.Hour:
				return fmt.Sprintf("%d 分钟前", int(d.Minutes()))
			case d < 24*time.Hour:
				return fmt.Sprintf("%d 小时前", int(d.Hours()))
			case d < 30*24*time.Hour:
				return fmt.Sprintf("%d 天前", int(d.Hours()/24))
			default:
				return t.Format("2006-01-02")
			}
		},
		// progressPercent 计算观看进度百分比
		"progressPercent": func(watched, total int) int {
			if total <= 0 {
				return 0
			}
			p := watched * 100 / total
			if p > 100 {
				p = 100
			}
			return p
		},
		// youtubeURL 拼接 YouTube 观看链接
		"youtubeURL": func(videoID string) string {
			return "https://www.youtube.com/watch?v=" + videoID
		},
		// thumbURL 生成视频缩略图 URL（Invidious 代理路径）
		"thumbURL": func(videoID string) string {
			return "/api/proxy_image?url=https://i.ytimg.com/vi/" + videoID + "/mqdefault.jpg"
		},
		// formatDuration 格式化时长为 H:MM:SS
		"formatDuration": func(seconds int) string {
			h := seconds / 3600
			m := (seconds % 3600) / 60
			s := seconds % 60
			if h > 0 {
				return fmt.Sprintf("%d:%02d:%02d", h, m, s)
			}
			return fmt.Sprintf("%d:%02d", m, s)
		},
		// formatViews 格式化播放量
		"formatViews": func(views int64) string {
			if views >= 100000000 {
				return fmt.Sprintf("%.1f亿", float64(views)/1e8)
			}
			if views >= 10000 {
				return fmt.Sprintf("%.1f万", float64(views)/1e4)
			}
			if views >= 1000 {
				return fmt.Sprintf("%.1f千", float64(views)/1e3)
			}
			return fmt.Sprintf("%d", views)
		},
	}

	baseSource, err := os.ReadFile(filepath.Join(templateDir, "base.html"))
	if err != nil {
		return nil, fmt.Errorf("读取 base.html 失败: %w", err)
	}

	return &Manager{
		templateDir: templateDir,
		baseSource:  string(baseSource),
		funcMap:     funcMap,
	}, nil
}

// RenderData 渲染上下文，传入页面模板的数据。
type RenderData struct {
	Title   string
	Theme   string
	Flashes []string
	IsHTTPS bool
	Data    any // 页面专用数据，模板内通过 .Data 访问
}

// RenderPage 渲染指定页面：合并 base.html + 页面文件，执行 base.html。
func (m *Manager) RenderPage(w io.Writer, pageTemplate string, data *RenderData) error {
	pageSource, err := os.ReadFile(filepath.Join(m.templateDir, pageTemplate))
	if err != nil {
		return fmt.Errorf("读取页面模板 %s 失败: %w", pageTemplate, err)
	}

	// 创建独立 template set：base 在前，页面在后
	tmpl := template.New("base").Funcs(m.funcMap)
	if _, err := tmpl.Parse(m.baseSource); err != nil {
		return fmt.Errorf("解析 base.html 失败: %w", err)
	}
	if _, err := tmpl.New(pageTemplate).Parse(string(pageSource)); err != nil {
		return fmt.Errorf("解析 %s 失败: %w", pageTemplate, err)
	}

	if data.Theme == "" {
		data.Theme = "midnight"
	}

	return tmpl.Execute(w, data)
}

// RenderPartial 渲染片段模板（不走 base 布局，用于 HTMX 局部加载）。
// data 直接作为模板根上下文（.）传入。
func (m *Manager) RenderPartial(w io.Writer, partialTemplate string, data any) error {
	source, err := os.ReadFile(filepath.Join(m.templateDir, partialTemplate))
	if err != nil {
		return fmt.Errorf("读取片段模板 %s 失败: %w", partialTemplate, err)
	}
	tmpl := template.New(partialTemplate).Funcs(m.funcMap)
	if _, err := tmpl.Parse(string(source)); err != nil {
		return fmt.Errorf("解析片段 %s 失败: %w", partialTemplate, err)
	}
	return tmpl.Execute(w, data)
}

// proxyImgFilter HTTPS 站点下把 http:// 图片改写为代理 URL。
func proxyImgFilter(url string, isHTTPS bool) string {
	if url == "" || !strings.HasPrefix(url, "http://") {
		return url
	}
	if !isHTTPS {
		return url
	}
	return "/api/proxy_image?url=" + url
}

// IsHTTPSRequest 判断请求是否 HTTPS（含反代 X-Forwarded-Proto）。
func IsHTTPSRequest(r *http.Request) bool {
	if r.TLS != nil {
		return true
	}
	return r.Header.Get("X-Forwarded-Proto") == "https"
}
