package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"

	"github.com/lwhx/zhuimange/internal/model"
)

// ==================== Source CRUD ====================

const sourceColumns = `id, episode_id, video_id, title, channel_id, channel_name,
	duration, view_count, published_at, match_score, is_valid, created_at,
	health_status, last_checked_at, last_check_error, fail_count`

func scanSource(sc scanner) (*model.Source, error) {
	src := &model.Source{}
	var isValid int
	var lastChecked sql.NullTime
	err := sc.Scan(
		&src.ID, &src.EpisodeID, &src.VideoID, &src.Title, &src.ChannelID, &src.ChannelName,
		&src.Duration, &src.ViewCount, &src.PublishedAt, &src.MatchScore, &isValid, &src.CreatedAt,
		&src.HealthStatus, &lastChecked, &src.LastCheckError, &src.FailCount,
	)
	if err != nil {
		return nil, err
	}
	src.IsValid = isValid != 0
	if lastChecked.Valid {
		src.LastCheckedAt = &lastChecked.Time
	}
	return src, nil
}

// AddSource 添加视频源（INSERT OR IGNORE，唯一约束 episode_id+video_id 去重）。
func (s *Store) AddSource(ctx context.Context, src *model.Source) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT OR IGNORE INTO sources
			(episode_id, video_id, title, channel_id, channel_name, duration, view_count,
			 published_at, match_score, is_valid)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)`,
		src.EpisodeID, src.VideoID, src.Title, src.ChannelID, src.ChannelName,
		src.Duration, src.ViewCount, src.PublishedAt, src.MatchScore)
	return err
}

// GetSourcesForEpisode 返回某集的全部视频源（按评分降序）。
func (s *Store) GetSourcesForEpisode(ctx context.Context, episodeID int64) ([]*model.Source, error) {
	rows, err := s.db.QueryContext(ctx,
		fmt.Sprintf(`SELECT %s FROM sources WHERE episode_id = ? ORDER BY match_score DESC`, sourceColumns), episodeID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var list []*model.Source
	for rows.Next() {
		src, err := scanSource(rows)
		if err != nil {
			return nil, err
		}
		list = append(list, src)
	}
	return list, rows.Err()
}

// DeleteSourcesForEpisode 删除某集的全部视频源（force 重新搜索时用）。
func (s *Store) DeleteSourcesForEpisode(ctx context.Context, episodeID int64) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM sources WHERE episode_id = ?`, episodeID)
	return err
}

// CountSourcesForEpisode 统计某集视频源数量。
func (s *Store) CountSourcesForEpisode(ctx context.Context, episodeID int64) (int, error) {
	var count int
	err := s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM sources WHERE episode_id = ?`, episodeID).Scan(&count)
	return count, err
}

// UpdateSourceHealth 更新视频源健康状态。
func (s *Store) UpdateSourceHealth(ctx context.Context, sourceID int64, status string, failCount int, lastErr string) error {
	_, err := s.db.ExecContext(ctx, `
		UPDATE sources SET health_status = ?, fail_count = ?, last_check_error = ?,
			last_checked_at = CURRENT_TIMESTAMP WHERE id = ?`,
		status, failCount, lastErr, sourceID)
	return err
}

// ==================== CustomAlias CRUD ====================

// AddAlias 添加自定义别名（唯一约束 anime_id+alias 去重）。
func (s *Store) AddAlias(ctx context.Context, animeID int64, alias string) error {
	_, err := s.db.ExecContext(ctx,
		`INSERT OR IGNORE INTO custom_aliases (anime_id, alias) VALUES (?, ?)`, animeID, alias)
	return err
}

// GetAliases 返回某动漫的自定义别名列表。
func (s *Store) GetAliases(ctx context.Context, animeID int64) ([]string, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT alias FROM custom_aliases WHERE anime_id = ?`, animeID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var list []string
	for rows.Next() {
		var alias string
		if err := rows.Scan(&alias); err != nil {
			return nil, err
		}
		list = append(list, alias)
	}
	return list, rows.Err()
}

// DeleteAlias 删除自定义别名。
func (s *Store) DeleteAlias(ctx context.Context, animeID int64, alias string) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM custom_aliases WHERE anime_id = ? AND alias = ?`, animeID, alias)
	return err
}

// ==================== GlobalAlias 查询 ====================

// GetGlobalAliasesByTitle 查询某标题的全局别名。
func (s *Store) GetGlobalAliasesByTitle(ctx context.Context, title string) ([]string, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT alias FROM global_aliases WHERE title = ?`, title)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var list []string
	for rows.Next() {
		var alias string
		if err := rows.Scan(&alias); err != nil {
			return nil, err
		}
		list = append(list, alias)
	}
	return list, rows.Err()
}

// ==================== SourceRule CRUD ====================

// GetSourceRule 获取某动漫的搜索规则，不存在返回 nil。
func (s *Store) GetSourceRule(ctx context.Context, animeID int64) (*model.SourceRule, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT id, anime_id, allow_keywords, deny_keywords, allow_channels, deny_channels, created_at, updated_at
		FROM anime_source_rules WHERE anime_id = ?`, animeID)

	r := &model.SourceRule{}
	var allowKw, denyKw, allowCh, denyCh string
	err := row.Scan(&r.ID, &r.AnimeID, &allowKw, &denyKw, &allowCh, &denyCh, &r.CreatedAt, &r.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	// 反序列化 JSON 数组字段
	_ = json.Unmarshal([]byte(allowKw), &r.AllowKeywords)
	_ = json.Unmarshal([]byte(denyKw), &r.DenyKeywords)
	_ = json.Unmarshal([]byte(allowCh), &r.AllowChannels)
	_ = json.Unmarshal([]byte(denyCh), &r.DenyChannels)
	return r, nil
}

// UpsertSourceRule 插入或更新搜索规则。
func (s *Store) UpsertSourceRule(ctx context.Context, r *model.SourceRule) error {
	allowKw, _ := json.Marshal(r.AllowKeywords)
	denyKw, _ := json.Marshal(r.DenyKeywords)
	allowCh, _ := json.Marshal(r.AllowChannels)
	denyCh, _ := json.Marshal(r.DenyChannels)
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO anime_source_rules (anime_id, allow_keywords, deny_keywords, allow_channels, deny_channels)
		VALUES (?, ?, ?, ?, ?)
		ON CONFLICT(anime_id) DO UPDATE SET
			allow_keywords = excluded.allow_keywords,
			deny_keywords = excluded.deny_keywords,
			allow_channels = excluded.allow_channels,
			deny_channels = excluded.deny_channels,
			updated_at = CURRENT_TIMESTAMP`,
		r.AnimeID, string(allowKw), string(denyKw), string(allowCh), string(denyCh))
	return err
}

// ==================== TrustedChannel 查询 ====================

// IsTrustedChannel 判断频道是否受信任。
func (s *Store) IsTrustedChannel(ctx context.Context, channelID string) (bool, error) {
	var exists int
	err := s.db.QueryRowContext(ctx,
		`SELECT 1 FROM trusted_channels WHERE channel_id = ? LIMIT 1`, channelID).Scan(&exists)
	if err == sql.ErrNoRows {
		return false, nil
	}
	return exists == 1, err
}

// ==================== SyncLog ====================

// AddSyncLog 记录同步日志。
func (s *Store) AddSyncLog(ctx context.Context, animeID int64, syncType string, epsSynced, sourcesFound int, status, message string) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO sync_logs (anime_id, sync_type, episodes_synced, sources_found, status, message)
		VALUES (?, ?, ?, ?, ?, ?)`, nullableInt64(animeID), syncType, epsSynced, sourcesFound, status, message)
	return err
}

// nullableInt64 0 值转 NULL（anime_id 可能被 SET NULL）。
func nullableInt64(v int64) any {
	if v == 0 {
		return nil
	}
	return v
}
