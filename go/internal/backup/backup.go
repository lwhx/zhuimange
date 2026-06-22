package backup

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"mime/multipart"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/lwhx/zhuimange/internal/model"
	"github.com/lwhx/zhuimange/internal/store"
)

// Service 封装备份导入导出依赖。
type Service struct {
	store *store.Store
	http  *http.Client
}

// ExportData 是 JSON 备份根结构。
type ExportData struct {
	Version    string            `json:"version"`
	ExportedAt string            `json:"exported_at"`
	App        string            `json:"app"`
	Settings   map[string]string `json:"settings"`
	Animes     []AnimeExport     `json:"animes"`
}

// AnimeExport 是单部动漫完整导出结构。
type AnimeExport struct {
	Anime    *model.Anime      `json:"anime"`
	Episodes []EpisodeExport   `json:"episodes"`
	Aliases  []string          `json:"aliases"`
	Rules    *model.SourceRule `json:"rules,omitempty"`
}

// EpisodeExport 是单集导出结构。
type EpisodeExport struct {
	Episode *model.Episode  `json:"episode"`
	Sources []*model.Source `json:"sources"`
}

// ImportStats 表示导入统计。
type ImportStats struct {
	AnimesImported   int `json:"animes_imported"`
	EpisodesImported int `json:"episodes_imported"`
	SourcesImported  int `json:"sources_imported"`
	Skipped          int `json:"skipped"`
}

var importableSettings = map[string]bool{
	"auto_sync_enabled":          true,
	"auto_sync_interval":         true,
	"match_threshold":            true,
	"match_recommend_threshold":  true,
	"invidious_url":              true,
	"invidious_fallback_urls":    true,
	"invidious_instance_weights": true,
	"tg_notify_enabled":          true,
	"tg_backup_enabled":          true,
	"tg_backup_interval_days":    true,
	"episode_sort_order":         true,
}

// NewService 创建备份服务。
func NewService(st *store.Store) *Service {
	return &Service{store: st, http: &http.Client{Timeout: 30 * time.Second}}
}

// ExportData 导出完整数据。
func (s *Service) ExportData(ctx context.Context) (*ExportData, error) {
	settings, err := s.store.GetAllSettings(ctx)
	if err != nil {
		return nil, err
	}
	animes, err := s.store.ListAnimes(ctx)
	if err != nil {
		return nil, err
	}
	result := &ExportData{Version: "1.0", ExportedAt: time.Now().Format(time.RFC3339), App: "追漫阁", Settings: settings, Animes: []AnimeExport{}}
	for _, anime := range animes {
		episodes, err := s.store.ListEpisodes(ctx, anime.ID)
		if err != nil {
			return nil, err
		}
		epExports := make([]EpisodeExport, 0, len(episodes))
		for _, episode := range episodes {
			sources, err := s.store.GetSourcesForEpisode(ctx, episode.ID)
			if err != nil {
				return nil, err
			}
			epExports = append(epExports, EpisodeExport{Episode: episode, Sources: sources})
		}
		aliases, err := s.store.GetAliases(ctx, anime.ID)
		if err != nil {
			return nil, err
		}
		rule, err := s.store.GetSourceRule(ctx, anime.ID)
		if err != nil {
			return nil, err
		}
		result.Animes = append(result.Animes, AnimeExport{Anime: anime, Episodes: epExports, Aliases: aliases, Rules: rule})
	}
	return result, nil
}

// ExportJSON 导出 JSON 字节。
func (s *Service) ExportJSON(ctx context.Context) ([]byte, error) {
	data, err := s.ExportData(ctx)
	if err != nil {
		return nil, err
	}
	return json.MarshalIndent(data, "", "  ")
}

// ImportJSON 从 JSON 合并导入。
func (s *Service) ImportJSON(ctx context.Context, payload []byte) (ImportStats, error) {
	var data ExportData
	if err := json.Unmarshal(payload, &data); err != nil {
		return ImportStats{}, err
	}
	stats := ImportStats{}
	for _, entry := range data.Animes {
		if entry.Anime == nil || strings.TrimSpace(entry.Anime.TitleCN) == "" {
			continue
		}
		anime := entry.Anime
		created, err := s.store.CreateAnime(ctx, anime)
		if err != nil {
			stats.Skipped++
			continue
		}
		stats.AnimesImported++
		for _, episodeEntry := range entry.Episodes {
			if episodeEntry.Episode == nil {
				continue
			}
			episode := *episodeEntry.Episode
			episode.AnimeID = created.ID
			inserted, err := s.store.AddEpisodes(ctx, []model.Episode{episode})
			if err == nil {
				stats.EpisodesImported += inserted
			}
			storedEpisode, err := s.store.GetEpisodeByNum(ctx, created.ID, episode.AbsoluteNum)
			if err != nil || storedEpisode == nil {
				continue
			}
			if episode.Watched {
				_ = s.store.SetEpisodeWatched(ctx, storedEpisode.ID, true)
			}
			for _, source := range episodeEntry.Sources {
				copySource := *source
				copySource.EpisodeID = storedEpisode.ID
				if err := s.store.AddSource(ctx, &copySource); err == nil {
					stats.SourcesImported++
				}
			}
		}
		for _, alias := range entry.Aliases {
			_ = s.store.AddAlias(ctx, created.ID, alias)
		}
		if entry.Rules != nil {
			entry.Rules.AnimeID = created.ID
			_ = s.store.UpsertSourceRule(ctx, entry.Rules)
		}
	}
	for key, value := range data.Settings {
		if !importableSettings[key] {
			continue
		}
		_ = s.store.SetSetting(ctx, key, value)
	}
	return stats, nil
}

// ExportCSV 导出通用追番列表 CSV。
func (s *Service) ExportCSV(ctx context.Context) ([]byte, error) {
	animes, err := s.store.ListAnimes(ctx)
	if err != nil {
		return nil, err
	}
	buffer := &bytes.Buffer{}
	writer := csv.NewWriter(buffer)
	_ = writer.Write([]string{"title_cn", "title_en", "tmdb_id", "bangumi_id", "watched_ep", "total_episodes", "status"})
	for _, anime := range animes {
		_ = writer.Write([]string{anime.TitleCN, anime.TitleEN, int64PtrToString(anime.TMDBID), int64PtrToString(anime.BangumiID), fmt.Sprintf("%d", anime.WatchedEp), fmt.Sprintf("%d", anime.TotalEpisodes), anime.Status})
	}
	writer.Flush()
	return buffer.Bytes(), writer.Error()
}

// ExportBangumi 导出 Bangumi 互通 JSON。
func (s *Service) ExportBangumi(ctx context.Context) ([]byte, error) {
	animes, err := s.store.ListAnimes(ctx)
	if err != nil {
		return nil, err
	}
	items := []map[string]any{}
	for _, anime := range animes {
		items = append(items, map[string]any{"bangumi_id": anime.BangumiID, "title": anime.TitleCN, "watched_ep": anime.WatchedEp, "total_episodes": anime.TotalEpisodes, "status": anime.Status})
	}
	return json.MarshalIndent(map[string]any{"version": "1.0", "items": items}, "", "  ")
}

// SendBackupToTelegram 发送 JSON 备份文件到 Telegram。
func (s *Service) SendBackupToTelegram(ctx context.Context) (map[string]any, error) {
	content, err := s.ExportJSON(ctx)
	if err != nil {
		return nil, err
	}
	token, _ := s.store.GetSetting(ctx, "tg_bot_token", "")
	chatID, _ := s.store.GetSetting(ctx, "tg_chat_id", "")
	if strings.TrimSpace(token) == "" || strings.TrimSpace(chatID) == "" {
		_ = s.store.AddBackupLog(ctx, "telegram", "error", "未配置 Telegram", 0, "", "NO_CONFIG")
		return nil, fmt.Errorf("未配置 Telegram")
	}
	filename := "zhuimange_backup_" + time.Now().Format("20060102_150405") + ".json"
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	_ = writer.WriteField("chat_id", chatID)
	_ = writer.WriteField("caption", "追漫阁备份 "+time.Now().Format("2006-01-02 15:04:05"))
	part, err := writer.CreateFormFile("document", filename)
	if err != nil {
		return nil, err
	}
	_, _ = part.Write(content)
	_ = writer.Close()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, "https://api.telegram.org/bot"+token+"/sendDocument", body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	resp, err := s.http.Do(req)
	if err != nil {
		_ = s.store.AddBackupLog(ctx, "telegram", "error", err.Error(), 0, filename, "NETWORK_ERROR")
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		message := fmt.Sprintf("Telegram HTTP %d", resp.StatusCode)
		_ = s.store.AddBackupLog(ctx, "telegram", "error", message, 0, filename, "TG_API_ERROR")
		return nil, fmt.Errorf("%s", message)
	}
	checksum := sha256.Sum256(content)
	_ = s.store.AddBackupLog(ctx, "telegram", "success", "备份发送成功", int64(len(content)), filename, "")
	return map[string]any{"success": true, "filename": filename, "size": len(content), "sha256": hex.EncodeToString(checksum[:])}, nil
}

// SaveBackupLocal 将备份 JSON 保存到本地 data/backups 目录。
func (s *Service) SaveBackupLocal(ctx context.Context) (map[string]any, error) {
	backupDir := "data/backups"
	if err := os.MkdirAll(backupDir, 0o755); err != nil {
		return nil, fmt.Errorf("创建备份目录失败: %w", err)
	}

	content, err := s.ExportJSON(ctx)
	if err != nil {
		return nil, err
	}
	filename := "zhuimange_backup_" + time.Now().Format("20060102_150405") + ".json"
	fullPath := backupDir + string(os.PathSeparator) + filename
	if err := os.WriteFile(fullPath, content, 0o644); err != nil {
		_ = s.store.AddBackupLog(ctx, "local", "error", err.Error(), 0, filename, "FILESYSTEM_ERROR")
		return nil, err
	}
	checksum := sha256.Sum256(content)
	_ = s.store.AddBackupLog(ctx, "local", "success", "备份保存成功", int64(len(content)), filename, "")
	return map[string]any{
		"success":  true,
		"filename": filename,
		"filepath": fullPath,
		"size":     len(content),
		"sha256":   hex.EncodeToString(checksum[:]),
	}, nil
}

// int64PtrToString 将整数指针转字符串。
func int64PtrToString(value *int64) string {
	if value == nil {
		return ""
	}
	return fmt.Sprintf("%d", *value)
}
