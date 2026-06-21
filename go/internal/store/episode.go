package store

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/lwhx/zhuimange/internal/model"
)

// ==================== Episode CRUD ====================

const episodeColumns = `id, anime_id, season_number, episode_number, absolute_num,
	title, overview, air_date, still_path, watched, created_at`

func scanEpisode(sc scanner) (*model.Episode, error) {
	e := &model.Episode{}
	var watched int
	err := sc.Scan(
		&e.ID, &e.AnimeID, &e.SeasonNumber, &e.EpisodeNumber, &e.AbsoluteNum,
		&e.Title, &e.Overview, &e.AirDate, &e.StillPath, &watched, &e.CreatedAt,
	)
	if err != nil {
		return nil, err
	}
	e.Watched = watched != 0
	return e, nil
}

// scanner 适配 *sql.Row 和 *sql.Rows 的 Scan 方法。
type scanner interface {
	Scan(...any) error
}

// AddEpisodes 批量插入集数（INSERT OR IGNORE，靠唯一约束去重）。
func (s *Store) AddEpisodes(ctx context.Context, eps []model.Episode) (int, error) {
	if len(eps) == 0 {
		return 0, nil
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()

	stmt, err := tx.PrepareContext(ctx, `
		INSERT OR IGNORE INTO episodes
			(anime_id, season_number, episode_number, absolute_num, title, overview, air_date, still_path, watched)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)`)
	if err != nil {
		return 0, err
	}
	defer stmt.Close()

	inserted := 0
	for _, e := range eps {
		res, err := stmt.ExecContext(ctx, e.AnimeID, e.SeasonNumber, e.EpisodeNumber, e.AbsoluteNum, e.Title, e.Overview, e.AirDate, e.StillPath)
		if err != nil {
			return inserted, fmt.Errorf("插入集数失败 ep%d: %w", e.AbsoluteNum, err)
		}
		if n, _ := res.RowsAffected(); n > 0 {
			inserted++
		}
	}
	return inserted, tx.Commit()
}

// ListEpisodes 返回某动漫的全部集数（按 absolute_num 升序）。
func (s *Store) ListEpisodes(ctx context.Context, animeID int64) ([]*model.Episode, error) {
	rows, err := s.db.QueryContext(ctx,
		fmt.Sprintf(`SELECT %s FROM episodes WHERE anime_id = ? ORDER BY absolute_num ASC`, episodeColumns), animeID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var list []*model.Episode
	for rows.Next() {
		e, err := scanEpisode(rows)
		if err != nil {
			return nil, err
		}
		list = append(list, e)
	}
	return list, rows.Err()
}

// FilterAiredEpisodes 过滤已开播集数（air_date 为空或早于等于 today）。
func (s *Store) FilterAiredEpisodes(ctx context.Context, animeID int64, today string) ([]*model.Episode, error) {
	rows, err := s.db.QueryContext(ctx,
		fmt.Sprintf(`SELECT %s FROM episodes WHERE anime_id = ? AND (air_date = '' OR air_date <= ?) ORDER BY absolute_num ASC`,
			episodeColumns), animeID, today)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var list []*model.Episode
	for rows.Next() {
		e, err := scanEpisode(rows)
		if err != nil {
			return nil, err
		}
		list = append(list, e)
	}
	return list, rows.Err()
}

// GetEpisodeByNum 按 absolute_num 查询单集。
func (s *Store) GetEpisodeByNum(ctx context.Context, animeID int64, epNum int) (*model.Episode, error) {
	row := s.db.QueryRowContext(ctx,
		fmt.Sprintf(`SELECT %s FROM episodes WHERE anime_id = ? AND absolute_num = ?`, episodeColumns),
		animeID, epNum)
	e, err := scanEpisode(row)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return e, err
}

// SetEpisodeWatched 标记集数已看/未看。
func (s *Store) SetEpisodeWatched(ctx context.Context, episodeID int64, watched bool) error {
	w := 0
	if watched {
		w = 1
	}
	_, err := s.db.ExecContext(ctx, `UPDATE episodes SET watched = ? WHERE id = ?`, w, episodeID)
	return err
}

// SetWatchedUpTo 批量标记从第1集到 maxEp 为已看，之后的为未看。
func (s *Store) SetWatchedUpTo(ctx context.Context, animeID int64, maxEp int) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.ExecContext(ctx,
		`UPDATE episodes SET watched = 1 WHERE anime_id = ? AND absolute_num <= ?`, animeID, maxEp); err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx,
		`UPDATE episodes SET watched = 0 WHERE anime_id = ? AND absolute_num > ?`, animeID, maxEp); err != nil {
		return err
	}
	return tx.Commit()
}

// DeleteEpisodesNotInAbsoluteNums 删除不在指定 absolute_num 列表中的集数（TMDB 集数刷新用）。
func (s *Store) DeleteEpisodesNotInAbsoluteNums(ctx context.Context, animeID int64, keepNums []int) error {
	if len(keepNums) == 0 {
		return nil
	}
	// 构造 NOT IN 占位符
	placeholders := ""
	args := []any{animeID}
	for i, n := range keepNums {
		if i > 0 {
			placeholders += ","
		}
		placeholders += "?"
		args = append(args, n)
	}
	_, err := s.db.ExecContext(ctx,
		fmt.Sprintf(`DELETE FROM episodes WHERE anime_id = ? AND absolute_num NOT IN (%s)`, placeholders), args...)
	return err
}

// EpisodeIsAired 判断集数是否已开播。
func (s *Store) EpisodeIsAired(ctx context.Context, animeID int64, epNum int, today string) (bool, error) {
	var airDate string
	err := s.db.QueryRowContext(ctx,
		`SELECT air_date FROM episodes WHERE anime_id = ? AND absolute_num = ?`, animeID, epNum).Scan(&airDate)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return airDate == "" || airDate <= today, nil
}

// EpisodeStats 返回动漫的集数统计（总数、已看数）。
func (s *Store) EpisodeStats(ctx context.Context, animeID int64) (total, watched int, err error) {
	err = s.db.QueryRowContext(ctx,
		`SELECT COUNT(*), COALESCE(SUM(watched), 0) FROM episodes WHERE anime_id = ?`, animeID).Scan(&total, &watched)
	return
}
