package store

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/lwhx/zhuimange/internal/model"
)

// ==================== Anime CRUD ====================

// scanAnime 将行扫描到 Anime 结构（统一字段顺序）。
func scanAnime(scan interface{ Scan(...any) error }) (*model.Anime, error) {
	a := &model.Anime{}
	var lastSync sql.NullTime
	var tmdbID, bangumiID sql.NullInt64
	err := scan.Scan(
		&a.ID, &tmdbID, &bangumiID, &a.TitleCN, &a.TitleEN, &a.PosterURL,
		&a.Overview, &a.AirDate, &a.TotalEpisodes, &a.WatchedEp, &a.Status,
		&a.SyncInterval, &lastSync, &a.CreatedAt, &a.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	if tmdbID.Valid {
		v := tmdbID.Int64
		a.TMDBID = &v
	}
	if bangumiID.Valid {
		v := bangumiID.Int64
		a.BangumiID = &v
	}
	if lastSync.Valid {
		a.LastSyncAt = &lastSync.Time
	}
	return a, nil
}

// animeColumns 是查询 anime 时的字段列表（与 scanAnime 顺序一致）。
const animeColumns = `id, tmdb_id, bangumi_id, title_cn, title_en, poster_url,
	overview, air_date, total_episodes, watched_ep, status,
	sync_interval, last_sync_at, created_at, updated_at`

// GetAnime 按 ID 查询单部动漫。
func (s *Store) GetAnime(ctx context.Context, id int64) (*model.Anime, error) {
	row := s.db.QueryRowContext(ctx,
		fmt.Sprintf(`SELECT %s FROM animes WHERE id = ?`, animeColumns), id)
	a, err := scanAnime(row)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return a, err
}

// ListAnimes 返回全部动漫（按更新时间倒序）。
func (s *Store) ListAnimes(ctx context.Context) ([]*model.Anime, error) {
	rows, err := s.db.QueryContext(ctx,
		fmt.Sprintf(`SELECT %s FROM animes ORDER BY updated_at DESC`, animeColumns))
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var list []*model.Anime
	for rows.Next() {
		a, err := scanAnime(rows)
		if err != nil {
			return nil, err
		}
		list = append(list, a)
	}
	return list, rows.Err()
}

// CreateAnime 插入新动漫，返回带 ID 的完整对象。
func (s *Store) CreateAnime(ctx context.Context, a *model.Anime) (*model.Anime, error) {
	res, err := s.db.ExecContext(ctx, `
		INSERT INTO animes (tmdb_id, bangumi_id, title_cn, title_en, poster_url, overview,
			air_date, total_episodes, watched_ep, status, sync_interval)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		nilIf(a.TMDBID), nilIf(a.BangumiID), a.TitleCN, a.TitleEN, a.PosterURL,
		a.Overview, a.AirDate, a.TotalEpisodes, a.WatchedEp, a.Status, a.SyncInterval)
	if err != nil {
		return nil, fmt.Errorf("创建动漫失败: %w", err)
	}
	id, err := res.LastInsertId()
	if err != nil {
		return nil, err
	}
	a.ID = id
	a.CreatedAt = time.Now()
	a.UpdatedAt = a.CreatedAt
	return a, nil
}

// UpdateAnime 更新动漫字段（仅非空字段），使用 upsert 模式。
func (s *Store) UpdateAnime(ctx context.Context, id int64, fields map[string]any) error {
	if len(fields) == 0 {
		return nil
	}
	sets := make([]string, 0, len(fields)+1)
	args := make([]any, 0, len(fields)+1)
	for k, v := range fields {
		sets = append(sets, k+" = ?")
		args = append(args, v)
	}
	sets = append(sets, "updated_at = CURRENT_TIMESTAMP")
	args = append(args, id)

	_, err := s.db.ExecContext(ctx,
		fmt.Sprintf(`UPDATE animes SET %s WHERE id = ?`, joinStrings(sets, ", ")), args...)
	return err
}

// DeleteAnime 删除动漫（级联删除集数/源/别名等，由外键 ON DELETE CASCADE 处理）。
func (s *Store) DeleteAnime(ctx context.Context, id int64) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM animes WHERE id = ?`, id)
	return err
}

// TouchAnimeSync 更新动漫的最后同步时间。
func (s *Store) TouchAnimeSync(ctx context.Context, id int64) error {
	_, err := s.db.ExecContext(ctx,
		`UPDATE animes SET last_sync_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?`, id)
	return err
}

// nilIf 把可能为 0 的指针逻辑转换为 NULL（用于 *int64 字段插入）。
// 传入 nil 返回 NULL；传入有效指针返回其值。
func nilIf(p *int64) any {
	if p == nil {
		return nil
	}
	return *p
}

// joinStrings 拼接字符串切片（避免引入 strings 包的 Join，此处语义更明确）。
func joinStrings(parts []string, sep string) string {
	out := ""
	for i, p := range parts {
		if i > 0 {
			out += sep
		}
		out += p
	}
	return out
}
