package store

import "context"

// DashboardItem 表示看板上的动漫进度卡片。
type DashboardItem struct {
	AnimeID        int64  `json:"anime_id"`
	TitleCN        string `json:"title_cn"`
	PosterURL      string `json:"poster_url"`
	WatchedEp      int    `json:"watched_ep"`
	TotalEpisodes  int    `json:"total_episodes"`
	MissingSources int    `json:"missing_sources"`
}

// CalendarItem 表示日历中的开播集数。
type CalendarItem struct {
	AnimeID     int64  `json:"anime_id"`
	TitleCN     string `json:"title_cn"`
	EpisodeID   int64  `json:"episode_id"`
	AbsoluteNum int    `json:"absolute_num"`
	AirDate     string `json:"air_date"`
}

// ListDashboardItems 查询看板数据。
func (s *Store) ListDashboardItems(ctx context.Context, limit int) ([]DashboardItem, error) {
	if limit <= 0 {
		limit = 50
	}
	rows, err := s.db.QueryContext(ctx, `
		SELECT a.id, a.title_cn, a.poster_url, a.watched_ep, a.total_episodes,
		       SUM(CASE WHEN src.id IS NULL THEN 1 ELSE 0 END) AS missing_sources
		FROM animes a
		LEFT JOIN episodes e ON e.anime_id = a.id
		LEFT JOIN sources src ON src.episode_id = e.id AND src.is_valid = 1
		GROUP BY a.id
		ORDER BY a.updated_at DESC
		LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []DashboardItem{}
	for rows.Next() {
		item := DashboardItem{}
		if err := rows.Scan(&item.AnimeID, &item.TitleCN, &item.PosterURL, &item.WatchedEp, &item.TotalEpisodes, &item.MissingSources); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

// ListCalendarItems 查询指定日期范围内的开播集数。
func (s *Store) ListCalendarItems(ctx context.Context, start string, end string) ([]CalendarItem, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT a.id, a.title_cn, e.id, e.absolute_num, e.air_date
		FROM episodes e
		JOIN animes a ON a.id = e.anime_id
		WHERE e.air_date >= ? AND e.air_date <= ?
		ORDER BY e.air_date ASC, a.title_cn ASC`, start, end)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []CalendarItem{}
	for rows.Next() {
		item := CalendarItem{}
		if err := rows.Scan(&item.AnimeID, &item.TitleCN, &item.EpisodeID, &item.AbsoluteNum, &item.AirDate); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

// CreateFavorite 创建收藏夹。
func (s *Store) CreateFavorite(ctx context.Context, name string, animeIDsJSON string) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO favorites (name, anime_ids) VALUES (?, ?)`, name, animeIDsJSON)
	return err
}

// ListFavorites 查询收藏夹。
func (s *Store) ListFavorites(ctx context.Context) ([]map[string]any, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT id, name, anime_ids, created_at FROM favorites ORDER BY created_at DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []map[string]any{}
	for rows.Next() {
		var id int64
		var name, animeIDs, createdAt string
		if err := rows.Scan(&id, &name, &animeIDs, &createdAt); err != nil {
			return nil, err
		}
		items = append(items, map[string]any{"id": id, "name": name, "anime_ids": animeIDs, "created_at": createdAt})
	}
	return items, rows.Err()
}
