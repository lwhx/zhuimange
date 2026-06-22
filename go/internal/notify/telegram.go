// Package notify 实现 Telegram 通知能力。
package notify

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/lwhx/zhuimange/internal/store"
)

// Telegram 封装 Telegram Bot API。
type Telegram struct {
	store *store.Store
	http  *http.Client
}

// NewTelegram 创建 Telegram 通知器。
func NewTelegram(st *store.Store) *Telegram {
	return &Telegram{store: st, http: &http.Client{Timeout: 10 * time.Second}}
}

// SendMessage 发送 Markdown 文本消息。
func (t *Telegram) SendMessage(ctx context.Context, text string) error {
	token, chatID, err := t.credentials(ctx)
	if err != nil {
		return err
	}
	endpoint := fmt.Sprintf("https://api.telegram.org/bot%s/sendMessage", token)
	form := url.Values{}
	form.Set("chat_id", chatID)
	form.Set("text", text)
	form.Set("parse_mode", "Markdown")
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, strings.NewReader(form.Encode()))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := t.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("Telegram 返回 HTTP %d", resp.StatusCode)
	}
	return nil
}

// SendNewEpisodeNotification 发送新集视频源通知。
func (t *Telegram) SendNewEpisodeNotification(ctx context.Context, updates map[string][]EpisodeUpdate) error {
	if len(updates) == 0 {
		return nil
	}
	lines := []string{"追漫阁更新提醒\n"}
	for title, episodes := range updates {
		lines = append(lines, fmt.Sprintf("《%s》新增 %d 集视频源", title, len(episodes)))
		for index, episode := range episodes {
			if index >= 5 {
				lines = append(lines, fmt.Sprintf("  · 还有 %d 集...", len(episodes)-5))
				break
			}
			lines = append(lines, fmt.Sprintf("  · 第 %d 集（%d 个源）", episode.EpisodeNum, episode.SourceCount))
		}
		lines = append(lines, "")
	}
	return t.SendMessage(ctx, strings.TrimSpace(strings.Join(lines, "\n")))
}

// SendAlert 发送告警消息。
func (t *Telegram) SendAlert(ctx context.Context, alertType string, message string) error {
	text := fmt.Sprintf("追漫阁告警\n\n时间: %s\n类型: %s\n消息: %s", time.Now().Format("2006-01-02 15:04:05"), strings.ToUpper(alertType), message)
	return t.SendMessage(ctx, text)
}

// EpisodeUpdate 表示某集新增源信息。
type EpisodeUpdate struct {
	EpisodeNum  int
	SourceCount int
}

// credentials 读取 Telegram 配置。
func (t *Telegram) credentials(ctx context.Context) (string, string, error) {
	token, err := t.store.GetSetting(ctx, "tg_bot_token", "")
	if err != nil {
		return "", "", err
	}
	chatID, err := t.store.GetSetting(ctx, "tg_chat_id", "")
	if err != nil {
		return "", "", err
	}
	if strings.TrimSpace(token) == "" || strings.TrimSpace(chatID) == "" {
		return "", "", fmt.Errorf("未配置 Telegram Bot Token 或 Chat ID")
	}
	return strings.TrimSpace(token), strings.TrimSpace(chatID), nil
}
