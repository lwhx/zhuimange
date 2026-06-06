/**
 * 追漫阁 - 前端交互
 */

// ==================== HTML 转义（防 XSS） ====================

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ==================== 主题管理 ====================

const ThemeManager = {
    STORAGE_KEY: 'zhuimange-theme',
    MODE_KEY: 'zhuimange-theme-mode',

    themes: [
        { id: 'anime-cyber', name: '动漫赛博', icon: '🦾' },
        { id: 'neon-purple', name: '霓虹紫', icon: '💜' },
        { id: 'ocean-blue', name: '海洋蓝', icon: '🌊' },
        { id: 'sunset-orange', name: '日落橙', icon: '🌅' },
        { id: 'emerald-green', name: '翡翠绿', icon: '💚' },
        { id: 'sakura-pink', name: '樱花粉', icon: '🌸' }
    ],

    init() {
        const savedTheme = localStorage.getItem(this.STORAGE_KEY);
        const savedMode = localStorage.getItem(this.MODE_KEY);
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

        const theme = savedTheme || 'anime-cyber';
        const mode = savedMode || (prefersDark ? 'dark' : 'light');

        this.applyTheme(theme, mode, false);

        // 监听系统主题变化
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem(this.MODE_KEY)) {
                const newMode = e.matches ? 'dark' : 'light';
                this.setMode(newMode);
            }
        });
    },

    setTheme(themeId, save = true) {
        const theme = this.themes.find(t => t.id === themeId) || this.themes[0];
        const mode = this.getCurrentMode();
        this.applyTheme(theme.id, mode, save);
        if (save) localStorage.setItem(this.STORAGE_KEY, theme.id);
    },

    setMode(mode, save = true) {
        const theme = this.getCurrentTheme();
        this.applyTheme(theme.id, mode, save);
        if (save) localStorage.setItem(this.MODE_KEY, mode);
    },

    applyTheme(themeId, mode, save) {
        const fullTheme = `${themeId}-${mode}`;
        document.documentElement.setAttribute('data-theme', fullTheme);

        // 清除可能残留的内联样式覆盖
        document.documentElement.style.removeProperty('--bg-primary');
        document.documentElement.style.removeProperty('--text-primary');

        this.updateIcon(themeId, mode);
        updateThemeDropdownActive();
    },

    getCurrentTheme() {
        const saved = localStorage.getItem(this.STORAGE_KEY) || 'anime-cyber';
        return this.themes.find(t => t.id === saved) || this.themes[0];
    },

    getCurrentMode() {
        return localStorage.getItem(this.MODE_KEY) || 'dark';
    },

    updateIcon(themeId, mode) {
        const btn = document.querySelector('.navbar__theme-toggle');
        if (!btn) return;
        btn.innerHTML = mode === 'dark' ? '☀️' : '🌙';
        const theme = this.themes.find(t => t.id === themeId) || this.themes[0];
        btn.title = `${theme.name} (${mode === 'dark' ? '深色' : '浅色'})`;
    },
};

function toggleThemeDropdown() {
    const dropdown = document.getElementById('theme-dropdown');
    if (dropdown) dropdown.classList.toggle('active');
}

function closeThemeDropdown() {
    const dropdown = document.getElementById('theme-dropdown');
    if (dropdown) dropdown.classList.remove('active');
}

function updateThemeDropdownActive() {
    const currentTheme = ThemeManager.getCurrentTheme();
    const currentMode = ThemeManager.getCurrentMode();

    document.querySelectorAll('.theme-mode-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.classList.contains(`theme-mode-btn--${currentMode}`)) {
            btn.classList.add('active');
        }
    });

    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.theme === currentTheme.id) {
            btn.classList.add('active');
        }
    });
}

// ==================== Toast 通知 ====================

const ToastManager = {
    container: null,

    init() {
        this.container = document.getElementById('toast-container');
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    },

    show(message, type = 'info', duration = 3000) {
        if (!this.container) this.init();
        const toast = document.createElement('div');
        toast.className = `toast toast--${type}`;
        toast.textContent = message;
        this.container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error'); },
    info(msg) { this.show(msg, 'info'); },
};

// ==================== API 请求 ====================

async function apiRequest(url, options = {}) {
    try {
        const headers = {};
        // 只在有 body 时设置 Content-Type
        if (options.body) {
            headers['Content-Type'] = 'application/json';
        }
        // 添加 CSRF token
        const csrfToken = document.querySelector('meta[name="csrf-token"]');
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken.getAttribute('content');
        }
        const resp = await fetch(url, {
            ...options,
            headers: { ...headers, ...(options.headers || {}) },
        });
        const data = await resp.json();
        if (!resp.ok) {
            throw new Error(data.error || `请求失败 (${resp.status})`);
        }
        return data;
    } catch (err) {
        ToastManager.error(err.message);
        throw err;
    }
}

// ==================== 详情页追更工作台 ====================

const EpisodeWorkbench = {
    filter: 'all',
    search: '',
};

function getEpisodeItems() {
    return Array.from(document.querySelectorAll('.episode-item'));
}

function getEpisodeSnapshot() {
    return getEpisodeItems()
        .map(item => ({
            item,
            ep: Number(item.dataset.ep || 0),
            title: (item.dataset.title || item.textContent || '').toLowerCase(),
            watched: item.dataset.watched === '1' || item.classList.contains('episode-item--watched'),
            sources: Number(item.dataset.sources || 0),
        }))
        .filter(ep => ep.ep > 0)
        .sort((a, b) => a.ep - b.ep);
}

function getEpisodeSortOrder() {
    const btn = document.getElementById('sort-toggle-btn');
    if (btn?.dataset.sortOrder) {
        return btn.dataset.sortOrder === 'asc' ? 'asc' : 'desc';
    }
    return btn?.textContent.trim().includes('倒序') ? 'desc' : 'asc';
}

function getCurrentActionButton() {
    const currentEvent = typeof event !== 'undefined' ? event : null;
    return currentEvent?.target?.closest?.('button') || null;
}

function updateEpisodeSourceCount(epNum, sourceCount) {
    const item = document.querySelector(`.episode-item[data-ep="${epNum}"]`);
    if (!item) return;

    const normalized = Math.max(0, Number(sourceCount || 0));
    item.dataset.sources = String(normalized);

    const dateDiv = item.querySelector('.episode-item__date');
    if (!dateDiv) return;

    const dateOnly = dateDiv.textContent.replace(/\s*·?\s*\d+\s*个视频源/g, '').trim();
    dateDiv.textContent = normalized > 0
        ? `${dateOnly ? `${dateOnly} · ` : ''}${normalized} 个视频源`
        : dateOnly;
}

function updateContinueWatchButton() {
    const btn = document.getElementById('continue-watch-btn');
    if (!btn) return;

    const next = getEpisodeSnapshot().find(ep => !ep.watched);
    if (!next) {
        btn.dataset.nextEp = '';
        btn.disabled = true;
        btn.textContent = '✓ 已追完';
        btn.setAttribute('aria-label', '已追完所有集数');
        return;
    }

    btn.dataset.nextEp = String(next.ep);
    btn.disabled = false;
    btn.textContent = `▶ 继续看第${next.ep}集`;
    btn.setAttribute('aria-label', `继续观看第${next.ep}集`);
}

function continueWatching(animeId) {
    const btn = document.getElementById('continue-watch-btn');
    const epNum = Number(btn?.dataset.nextEp || 0);
    if (!epNum) {
        ToastManager.info('已经追完啦，今天的修仙任务完成。');
        return;
    }
    openSourcesModal(animeId, epNum);
}

function setEpisodeFilter(filter) {
    EpisodeWorkbench.filter = filter || 'all';
    document.querySelectorAll('.episode-filter-tab').forEach(btn => {
        const active = btn.dataset.filter === EpisodeWorkbench.filter;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    applyEpisodeFilters();
}

function setEpisodeSearch(value) {
    EpisodeWorkbench.search = (value || '').trim().toLowerCase();
    applyEpisodeFilters();
}

function applyEpisodeFilters() {
    const query = EpisodeWorkbench.search;
    let visibleCount = 0;

    getEpisodeSnapshot().forEach(({ item, ep, title, watched, sources }) => {
        let matchesFilter = true;
        if (EpisodeWorkbench.filter === 'watched') matchesFilter = watched;
        if (EpisodeWorkbench.filter === 'unwatched') matchesFilter = !watched;
        if (EpisodeWorkbench.filter === 'with_sources') matchesFilter = sources > 0;
        if (EpisodeWorkbench.filter === 'without_sources') matchesFilter = sources <= 0;

        const searchable = `${ep} ${title}`;
        const matchesSearch = !query || searchable.includes(query);
        const visible = matchesFilter && matchesSearch;
        item.hidden = !visible;
        if (visible) visibleCount += 1;
    });

    const empty = document.getElementById('episode-filter-empty');
    if (empty) empty.hidden = visibleCount > 0 || getEpisodeItems().length === 0;
}

function ensureEpisodeToolbar() {
    if (document.querySelector('.episodes-toolbar')) return;

    const section = document.querySelector('.episodes-section');
    const header = document.querySelector('.episodes-section__header');
    if (!section || !header) return;

    const toolbar = document.createElement('div');
    toolbar.className = 'episodes-toolbar';
    toolbar.setAttribute('aria-label', '集数筛选工具');
    toolbar.innerHTML = `
        <div class="episodes-filter-tabs" role="group" aria-label="按观看状态或视频源筛选">
            <button type="button" class="episode-filter-tab active" data-filter="all" onclick="setEpisodeFilter('all')" aria-pressed="true">全部</button>
            <button type="button" class="episode-filter-tab" data-filter="unwatched" onclick="setEpisodeFilter('unwatched')" aria-pressed="false">未看</button>
            <button type="button" class="episode-filter-tab" data-filter="watched" onclick="setEpisodeFilter('watched')" aria-pressed="false">已看</button>
            <button type="button" class="episode-filter-tab" data-filter="with_sources" onclick="setEpisodeFilter('with_sources')" aria-pressed="false">有源</button>
            <button type="button" class="episode-filter-tab" data-filter="without_sources" onclick="setEpisodeFilter('without_sources')" aria-pressed="false">无源</button>
        </div>
        <label class="episode-search" for="episode-search-input">
            <span class="episode-search__icon">🔎</span>
            <span class="visually-hidden">搜索集数</span>
            <input type="search" id="episode-search-input" placeholder="搜索集数或标题" oninput="setEpisodeSearch(this.value)" autocomplete="off">
        </label>
    `;

    const empty = document.createElement('div');
    empty.id = 'episode-filter-empty';
    empty.className = 'episodes-filter-empty';
    empty.hidden = true;
    empty.textContent = '没有符合条件的集数，换个筛选试试。';

    header.insertAdjacentElement('afterend', toolbar);
    toolbar.insertAdjacentElement('afterend', empty);
    setEpisodeFilter(EpisodeWorkbench.filter);
    const searchInput = document.getElementById('episode-search-input');
    if (searchInput) searchInput.value = EpisodeWorkbench.search;
}

function updateEpisodeItemState(item, episode) {
    if (!item || !episode) return;

    const epNum = Number(episode.absolute_num || item.dataset.ep || 0);
    const title = episode.title || `第${epNum}集`;
    const sourceCount = Number(episode.source_count || 0);
    const watched = Boolean(episode.watched);

    item.dataset.ep = String(epNum);
    item.dataset.title = title;
    item.dataset.watched = watched ? '1' : '0';
    item.dataset.sources = String(sourceCount);
    item.classList.toggle('episode-item--watched', watched);

    const titleEl = item.querySelector('.episode-item__title');
    if (titleEl) titleEl.textContent = title;

    const numEl = item.querySelector('.episode-item__num');
    if (numEl) numEl.textContent = watched ? '✓' : String(epNum);

    const dateDiv = item.querySelector('.episode-item__date');
    if (dateDiv) {
        let dateText = episode.air_date || '';
        if (sourceCount > 0) {
            dateText += (dateText ? ' · ' : '') + `${sourceCount} 个视频源`;
        }
        dateDiv.textContent = dateText;
    }

    const buttons = item.querySelectorAll('.episode-item__actions .btn');
    buttons.forEach(btn => {
        const text = btn.textContent.trim();
        if (text === '✓') btn.style.display = watched ? 'none' : '';
        if (text === '↩️') btn.style.display = watched ? '' : 'none';
    });
}

function createEpisodeItem(animeId, episode) {
    const epNum = Number(episode.absolute_num || episode);
    const title = episode.title || `第${epNum}集`;
    const sourceCount = Number(episode.source_count || 0);
    const watched = Boolean(episode.watched);
    let dateText = episode.air_date || '';
    if (sourceCount > 0) {
        dateText += (dateText ? ' · ' : '') + `${sourceCount} 个视频源`;
    }

    const item = document.createElement('div');
    item.className = `episode-item ${watched ? 'episode-item--watched' : ''}`;
    item.dataset.ep = String(epNum);
    item.dataset.title = title;
    item.dataset.watched = watched ? '1' : '0';
    item.dataset.sources = String(sourceCount);
    item.innerHTML = `
        <div class="episode-item__num">${watched ? '✓' : epNum}</div>
        <div class="episode-item__info">
            <div class="episode-item__title">${escapeHtml(title)}</div>
            <div class="episode-item__date">${escapeHtml(dateText)}</div>
        </div>
        <div class="episode-item__actions">
            <button type="button" class="btn btn--sm btn--secondary" onclick="openSourcesModal(${animeId}, ${epNum})" aria-label="查看第${epNum}集视频源" title="查看视频源">🎬</button>
            <button type="button" class="btn btn--sm btn--success" onclick="markWatched(${animeId}, ${epNum})" aria-label="标记第${epNum}集已看" title="标记已看"${watched ? ' style="display:none;"' : ''}>✓</button>
            <button type="button" class="btn btn--sm btn--secondary" onclick="markUnwatched(${animeId}, ${epNum})" aria-label="取消第${epNum}集已看" title="标记未看"${watched ? '' : ' style="display:none;"'}>↩️</button>
        </div>
    `;
    return item;
}

function insertEpisodeItemSorted(grid, item) {
    const epNum = Number(item.dataset.ep || 0);
    const sortOrder = getEpisodeSortOrder();
    let inserted = false;
    grid.querySelectorAll('.episode-item').forEach(existing => {
        const existingEp = Number(existing.dataset.ep || 0);
        const shouldInsert = sortOrder === 'desc' ? existingEp < epNum : existingEp > epNum;
        if (!inserted && shouldInsert) {
            grid.insertBefore(item, existing);
            inserted = true;
        }
    });
    if (!inserted) grid.appendChild(item);
}

function setButtonLoading(btn, loading = true, fallbackText = '处理中...') {
    if (!btn) return;
    if (loading) {
        if (!btn.dataset.originalText) {
            btn.dataset.originalText = btn.textContent.trim();
        }
        btn.disabled = true;
        btn.textContent = btn.dataset.loadingText || fallbackText;
        return;
    }
    btn.disabled = false;
    if (btn.dataset.originalText) {
        btn.textContent = btn.dataset.originalText;
        delete btn.dataset.originalText;
    }
}

function initEpisodeWorkbench() {
    document.querySelectorAll('.episode-filter-tab').forEach(btn => {
        btn.setAttribute('aria-pressed', btn.classList.contains('active') ? 'true' : 'false');
    });
    updateContinueWatchButton();
    applyEpisodeFilters();
}


// ==================== 搜索功能 ====================

let searchTimer = null;

function initSearch() {
    const input = document.getElementById('search-input');
    const results = document.getElementById('search-results');
    const clearBtn = document.getElementById('search-clear');

    if (!input) return;

    input.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        clearBtn.classList.toggle('visible', query.length > 0);

        if (query.length < 2) {
            results.classList.remove('visible');
            return;
        }

        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => searchAnime(query), 400);
    });

    clearBtn.addEventListener('click', () => {
        input.value = '';
        results.classList.remove('visible');
        clearBtn.classList.remove('visible');
    });

    // 点击外部关闭
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-box')) {
            results.classList.remove('visible');
        }
    });
}

async function searchAnime(query) {
    const results = document.getElementById('search-results');
    results.innerHTML = '<div style="padding:16px;color:var(--text-muted);text-align:center;">搜索中...</div>';
    results.classList.add('visible');

    try {
        const url = `/api/search?q=${encodeURIComponent(query)}`;
        const resp = await apiRequest(url);
        const items = resp.data || resp;
        if (items.length === 0) {
            results.innerHTML = '<div style="padding:16px;color:var(--text-muted);text-align:center;">没有找到相关动漫</div>';
            return;
        }

        results.innerHTML = items.map(item => {
            const id = item.tmdb_id;
            return `
            <div class="search-result-item" data-id="${id}">
                <img class="search-result-item__poster"
                     src="${escapeHtml(item.poster_url || '')}"
                     alt="${escapeHtml(item.title_cn)}"
                     onerror="this.style.background='var(--bg-tertiary)'">
                <div class="search-result-item__info">
                    <div class="search-result-item__title">${escapeHtml(item.title_cn)}</div>
                    <div class="search-result-item__meta">
                        ${item.title_en ? escapeHtml(item.title_en) + ' · ' : ''}
                        ${escapeHtml(item.air_date || '未知')} · ${item.total_episodes || '?'}集
                    </div>
                </div>
                <button type="button" class="search-result-item__add-btn"
                        onclick="event.stopPropagation(); addAnime(${id})">
                    + 添加
                </button>
            </div>`;
        }).join('');
    } catch (err) {
        results.innerHTML = '<div style="padding:16px;color:var(--danger);text-align:center;">搜索失败</div>';
    }
}

async function addAnime(tmdbId) {
    try {
        const data = await apiRequest('/api/anime/add', {
            method: 'POST',
            body: JSON.stringify({ tmdb_id: tmdbId }),
        });
        ToastManager.success('添加成功！');

        const animeId = data.data.anime_id;
        const animeData = await apiRequest(`/api/anime/${animeId}`);
        const anime = animeData.data;

        createAnimeCard(anime);

        document.getElementById('search-results').classList.remove('visible');
        document.getElementById('search-input').value = '';
    } catch (err) {
        // error already shown by apiRequest
    }
}

function createAnimeCard(anime) {
    const grid = document.querySelector('.anime-grid');
    const emptyState = document.querySelector('.empty-state');
    const headerSubtitle = document.querySelector('.page-header__subtitle');
    const filterTabs = document.querySelector('.filter-tabs');

    if (emptyState) {
        emptyState.remove();
    }

    if (!filterTabs) {
        const tabsDiv = document.createElement('div');
        tabsDiv.className = 'filter-tabs';
        tabsDiv.innerHTML = `
            <button class="filter-tab active" onclick="filterAnimes('all')">全部</button>
            <button class="filter-tab" onclick="filterAnimes('airing')">连载中</button>
            <button class="filter-tab" onclick="filterAnimes('ended')">已完结</button>
            <button class="filter-tab" onclick="filterAnimes('unwatched')">有更新</button>
        `;
        headerSubtitle.parentElement.after(tabsDiv);
    }

    const card = document.createElement('a');
    card.href = `/anime/${anime.id}`;
    card.className = 'anime-card';
    card.dataset.status = anime.status || '';
    card.dataset.unwatched = anime.unwatched_count || 0;

    let badge = '';
    if (anime.unwatched_count > 0) {
        badge = `<span class="anime-card__badge anime-card__badge--new">${anime.unwatched_count}集更新</span>`;
    } else if (anime.status === 'Returning Series') {
        badge = `<span class="anime-card__badge anime-card__badge--airing">连载中</span>`;
    } else if (anime.status === 'Ended') {
        badge = `<span class="anime-card__badge anime-card__badge--ended">已完结</span>`;
    }

    const watchedEp = anime.watched_ep || 0;
    const totalEp = anime.episode_count || anime.total_episodes || 1;
    const progressPercent = Math.round(watchedEp / totalEp * 100);

    card.innerHTML = `
        <div class="anime-card__poster-wrap">
            ${anime.poster_url ? `<img class="anime-card__poster" src="${escapeHtml(anime.poster_url)}" alt="${escapeHtml(anime.title_cn)}" loading="lazy" onerror="this.style.display='none'">` : ''}
            ${badge}
        </div>
        <div class="anime-card__body">
            <div class="anime-card__title" title="${escapeHtml(anime.title_cn)}">${escapeHtml(anime.title_cn)}</div>
            <div class="anime-card__progress">
                <div class="anime-card__progress-bar">
                    <div class="anime-card__progress-fill" style="width: ${progressPercent}%"></div>
                </div>
                <span class="anime-card__progress-text">${watchedEp}/${anime.episode_count || anime.total_episodes || '?'}</span>
            </div>
        </div>
    `;

    grid.insertBefore(card, grid.firstChild);

    const currentCount = parseInt(headerSubtitle.textContent.match(/\d+/) || '0', 10);
    headerSubtitle.textContent = `共 ${currentCount + 1} 部动漫`;
}

// ==================== 手动添加 ====================

function toggleManualAdd() {
    const form = document.getElementById('manual-add-form');
    form.classList.toggle('visible');
}

async function submitManualAdd() {
    const title = document.getElementById('manual-title').value.trim();
    const totalEp = parseInt(document.getElementById('manual-total-ep').value || '0', 10);
    const aliases = document.getElementById('manual-aliases').value
        .split(',')
        .map(a => a.trim())
        .filter(Boolean);

    if (!title) {
        ToastManager.error('请输入动漫名称');
        return;
    }

    try {
        const data = await apiRequest('/api/anime/add_manual', {
            method: 'POST',
            body: JSON.stringify({
                title,
                total_episodes: totalEp,
                aliases,
            }),
        });
        ToastManager.success('添加成功！');

        const animeId = data.data.anime_id;
        const animeData = await apiRequest(`/api/anime/${animeId}`);
        const anime = animeData.data;

        createAnimeCard(anime);

        document.getElementById('manual-title').value = '';
        document.getElementById('manual-total-ep').value = '';
        document.getElementById('manual-aliases').value = '';
        toggleManualAdd();
    } catch (err) { /* handled */ }
}

// ==================== 进度管理 ====================

async function markWatched(animeId, epNum) {
    try {
        await apiRequest(`/api/anime/${animeId}/episode/${epNum}/watch`, {
            method: 'POST',
        });
        ToastManager.success(`第${epNum}集已标记为看过`);
        // 更新 UI
        const item = document.querySelector(`[data-ep="${epNum}"]`);
        if (item) {
            item.classList.add('episode-item--watched');
            item.dataset.watched = '1';
            const numEl = item.querySelector('.episode-item__num');
            if (numEl) numEl.innerHTML = '✓';
            // 切换按钮显示
            const btns = item.querySelectorAll('.episode-item__actions .btn');
            btns.forEach(btn => {
                if (btn.textContent.trim() === '✓') btn.style.display = 'none';
                if (btn.textContent.trim() === '↩️') btn.style.display = '';
            });
        }
        updateProgressBar(animeId);
        updateContinueWatchButton();
        applyEpisodeFilters();
    } catch (err) { /* handled */ }
}

async function markUnwatched(animeId, epNum) {
    try {
        await apiRequest(`/api/anime/${animeId}/episode/${epNum}/unwatch`, {
            method: 'POST',
        });
        ToastManager.success(`第${epNum}集已标记为未看`);
        const item = document.querySelector(`[data-ep="${epNum}"]`);
        if (item) {
            item.classList.remove('episode-item--watched');
            item.dataset.watched = '0';
            const numEl = item.querySelector('.episode-item__num');
            if (numEl) numEl.textContent = epNum;
            // 切换按钮显示
            const btns = item.querySelectorAll('.episode-item__actions .btn');
            btns.forEach(btn => {
                if (btn.textContent.trim() === '✓') btn.style.display = '';
                if (btn.textContent.trim() === '↩️') btn.style.display = 'none';
            });
        }
        updateProgressBar(animeId);
        updateContinueWatchButton();
        applyEpisodeFilters();
    } catch (err) { /* handled */ }
}

async function updateProgress(animeId) {
    const input = document.getElementById('progress-input');
    if (!input) return;
    const ep = parseInt(input.value, 10);
    if (isNaN(ep) || ep < 0) {
        ToastManager.error('请输入有效集数');
        return;
    }

    try {
        await apiRequest(`/api/anime/${animeId}/progress`, {
            method: 'PUT',
            body: JSON.stringify({ watched_ep: ep }),
        });
        ToastManager.success(`进度已更新至第${ep}集`);
        setTimeout(() => location.reload(), 800);
    } catch (err) { /* handled */ }
}

function updateProgressBar(animeId) {
    // 刷新进度条
    const watched = document.querySelectorAll('.episode-item--watched').length;
    const total = document.querySelectorAll('.episode-item').length;
    const fill = document.getElementById('progress-fill');
    const text = document.getElementById('progress-text');
    if (fill && total > 0) {
        fill.style.width = `${(watched / total) * 100}%`;
    }
    if (text) {
        text.textContent = `${watched}/${total}`;
    }
}

// ==================== 视频源 ====================

async function openSourcesModal(animeId, epNum) {
    const overlay = document.getElementById('sources-modal-overlay');
    const body = document.getElementById('sources-modal-body');
    if (!overlay || !body) return;

    body.innerHTML = `
        <div class="modal-state modal-state--loading">
            <div class="modal-state__spinner"></div>
            <div class="modal-state__title">正在加载第${epNum}集视频源</div>
            <div class="modal-state__desc">稍等一下，片源小队正在翻目录。</div>
        </div>
    `;
    overlay.classList.add('visible');

    try {
        const resp = await fetch(`/anime/${animeId}/episode/${epNum}/sources`);
        if (!resp.ok) throw new Error(`加载失败 (${resp.status})`);
        body.innerHTML = await resp.text();
    } catch (err) {
        body.innerHTML = `
            <div class="modal-state modal-state--error">
                <div class="modal-state__icon">⚠️</div>
                <div class="modal-state__title">视频源加载失败</div>
                <div class="modal-state__desc">网络或服务开了小差，请稍后重试。</div>
            </div>
        `;
    }
}

function closeSourcesModal() {
    const overlay = document.getElementById('sources-modal-overlay');
    if (!overlay) return;
    overlay.classList.remove('visible');
}

async function findSources(animeId, epNum, force = false) {
    const btn = getCurrentActionButton() || document.querySelector(`[data-ep="${epNum}"] .btn[onclick*="findSources"]`);
    setButtonLoading(btn, true, '搜索中...');

    try {
        const resp = await apiRequest(`/api/anime/${animeId}/episode/${epNum}/find_sources`, {
            method: 'POST',
            body: JSON.stringify({ force }),
        });
        updateEpisodeSourceCount(epNum, resp.data?.count || 0);
        applyEpisodeFilters();
        ToastManager.success('搜索完成');
        openSourcesModal(animeId, epNum);
    } catch (err) {
        setButtonLoading(btn, false);
    }
}

async function checkSourcesHealth(animeId, epNum) {
    const btn = getCurrentActionButton();
    setButtonLoading(btn, true, '检测中...');

    try {
        const resp = await apiRequest(`/api/anime/${animeId}/episode/${epNum}/check_sources`, {
            method: 'POST',
            body: JSON.stringify({}),
        });
        ToastManager.success(resp.message || '检测完成');
        openSourcesModal(animeId, epNum);
    } catch (err) {
        setButtonLoading(btn, false);
    }
}

// ==================== 同步 ====================

const SyncWorkbench = {
    sessionId: 0,
    taskId: '',
    animeId: 0,
    mode: 'incremental',
    latestSources: 0,
    eventSource: null,
    summaryTimer: null,
    doneTaskIds: new Set(),
};

function getSyncElements() {
    return {
        btn: document.getElementById('sync-btn'),
        fullBtn: document.getElementById('full-sync-btn'),
        progressDiv: document.getElementById('sync-progress'),
        progressFill: document.getElementById('sync-progress-fill'),
        progressText: document.getElementById('sync-progress-text'),
        stageText: document.getElementById('sync-status-stage'),
        percentText: document.getElementById('sync-status-percent'),
        targetMetric: document.getElementById('sync-metric-target'),
        skippedMetric: document.getElementById('sync-metric-skipped'),
        sourcesMetric: document.getElementById('sync-metric-sources'),
        reconnectBtn: document.getElementById('sync-reconnect-btn'),
    };
}

function updateSyncCard({ stage, percent, text, target, skipped, sources }) {
    const els = getSyncElements();
    if (els.progressDiv) els.progressDiv.classList.add('visible');
    if (els.stageText && stage) els.stageText.textContent = stage;
    if (typeof percent === 'number') {
        const normalized = Math.max(0, Math.min(100, Math.round(percent)));
        if (els.progressFill) els.progressFill.style.width = `${normalized}%`;
        if (els.percentText) els.percentText.textContent = `${normalized}%`;
    }
    if (els.progressText && text) els.progressText.textContent = text;
    if (els.targetMetric && typeof target === 'number') els.targetMetric.textContent = `目标 ${target} 集`;
    if (els.skippedMetric && typeof skipped === 'number') els.skippedMetric.textContent = `跳过 ${skipped} 集`;
    if (els.sourcesMetric && typeof sources === 'number') els.sourcesMetric.textContent = `视频源 ${sources} 个`;
}

function setSyncButtonsBusy(isBusy, mode = SyncWorkbench.mode) {
    const { btn, fullBtn } = getSyncElements();
    if (btn) {
        btn.disabled = isBusy;
        btn.textContent = isBusy
            ? (mode === 'full' ? '全量刷新中...' : '同步中...')
            : '⚡ 同步视频源';
    }
    if (fullBtn) fullBtn.disabled = isBusy;
}

function setSyncReconnectVisible(visible) {
    const { reconnectBtn } = getSyncElements();
    if (!reconnectBtn) return;

    if (visible) {
        setButtonLoading(reconnectBtn, false);
    }
    reconnectBtn.hidden = !visible;
    const actions = reconnectBtn.closest('.sync-status-card__actions');
    if (actions) actions.hidden = !visible;
}

function closeSyncEventSource() {
    if (SyncWorkbench.eventSource) {
        SyncWorkbench.eventSource.close();
        SyncWorkbench.eventSource = null;
    }
}

function clearSyncSummaryTimer() {
    if (SyncWorkbench.summaryTimer) {
        clearTimeout(SyncWorkbench.summaryTimer);
        SyncWorkbench.summaryTimer = null;
    }
}

function openSyncTaskStream({ animeId, taskId, mode, reconnect = false }) {
    if (!taskId) return;

    closeSyncEventSource();
    clearSyncSummaryTimer();

    const sessionId = ++SyncWorkbench.sessionId;
    SyncWorkbench.taskId = taskId;
    SyncWorkbench.animeId = animeId;
    SyncWorkbench.mode = mode || 'incremental';
    SyncWorkbench.latestSources = 0;

    setSyncButtonsBusy(true, SyncWorkbench.mode);
    setSyncReconnectVisible(false);
    updateSyncCard({
        stage: reconnect ? '重新接入' : '接入任务',
        text: reconnect ? '正在重新接入同步任务...' : '正在接入同步事件流...',
    });

    const es = new EventSource(`/api/sync_tasks/${taskId}/stream`);
    SyncWorkbench.eventSource = es;

    es.onmessage = function (event) {
        if (sessionId !== SyncWorkbench.sessionId) {
            es.close();
            return;
        }
        handleSyncStreamEvent(JSON.parse(event.data), sessionId);
    };

    es.onerror = function () {
        if (sessionId !== SyncWorkbench.sessionId) return;
        closeSyncEventSource();
        setSyncButtonsBusy(false);
        setSyncReconnectVisible(Boolean(SyncWorkbench.taskId));
        updateSyncCard({
            stage: '连接中断',
            text: '同步可能仍在后台继续，可点击重新接入。',
        });
        ToastManager.error('同步连接中断');
    };
}

function handleSyncStreamEvent(data, sessionId) {
    if (data.type === 'heartbeat') {
        return;
    }
    else if (data.type === 'queued') {
        updateSyncCard({ stage: '排队中', text: '排队中，轮到它就开搜。' });
    }
    else if (data.type === 'task_start') {
        updateSyncCard({ stage: '任务启动', text: '同步任务启动中...' });
    }
    else if (data.type === 'discovering') {
        updateSyncCard({ stage: '探测集数', percent: 8, text: data.message || '正在探测集数...' });
    }
    else if (data.type === 'discover') {
        if (data.new_episodes && data.new_episodes.length > 0) {
            _insertNewEpisodes(SyncWorkbench.animeId, data.new_episodes);
            ToastManager.success(`探测到 ${data.total} 集`);
        }
        updateSyncCard({
            stage: '集数已更新',
            percent: 15,
            text: `探测到 ${data.total} 集${data.new_episodes?.length ? `，新增 ${data.new_episodes.length} 集` : ''}`,
        });
    }
    else if (data.type === 'start') {
        updateSyncCard({
            stage: SyncWorkbench.mode === 'full' ? '全量刷新' : '增量同步',
            percent: 20,
            text: SyncWorkbench.mode === 'full' ? `全量刷新准备中，共 ${data.total} 集` : `增量同步准备中，共 ${data.total} 集`,
            target: data.total || 0,
        });
    }
    else if (data.type === 'plan') {
        updateSyncCard({
            stage: '同步计划',
            percent: data.target > 0 ? 24 : 100,
            text: SyncWorkbench.mode === 'full' ? `需刷新 ${data.target}/${data.total} 集` : `需同步 ${data.target} 集，跳过 ${data.skipped} 集`,
            target: data.target || 0,
            skipped: data.skipped || 0,
        });
    }
    else if (data.type === 'episode') {
        const pct = data.total > 0 ? Math.round(data.current / data.total * 100) : 100;
        const sourceCount = Number(data.source_count || 0);
        SyncWorkbench.latestSources += sourceCount;
        updateSyncCard({
            stage: '同步视频源',
            percent: pct,
            text: SyncWorkbench.mode === 'full' ? `${data.current}/${data.total}` : `${data.current}/${data.total} · 已跳过 ${data.skipped || 0}`,
            target: data.total || 0,
            skipped: data.skipped || 0,
            sources: SyncWorkbench.latestSources,
        });
        updateEpisodeSourceCount(data.ep_num, sourceCount);
        applyEpisodeFilters();
    }
    else if (data.type === 'poster') {
        const posterContainer = document.querySelector('.anime-detail__poster');
        if (posterContainer && data.poster_url) {
            posterContainer.innerHTML = `<img src="${escapeHtml(data.poster_url)}" alt="封面" style="opacity:0;transition:opacity 0.5s;">`;
            const img = posterContainer.querySelector('img');
            img.onload = () => { img.style.opacity = '1'; };
        }
    }
    else if (data.type === 'done') {
        finishSyncTask(data, sessionId);
    }
    else if (data.type === 'task_done' && data.task_status !== 'success') {
        failSyncTask(data.message || '同步任务异常结束');
    }
    else if (data.type === 'error') {
        failSyncTask(data.message || '同步失败');
    }
}

function finishSyncTask(data, sessionId) {
    closeSyncEventSource();
    setSyncReconnectVisible(false);
    updateSyncCard({
        stage: '同步完成',
        percent: 100,
        text: SyncWorkbench.mode === 'full'
            ? `全量刷新完成：${data.synced} 集，${data.total_sources} 个视频源`
            : `增量同步完成：同步 ${data.synced} 集，跳过 ${data.skipped || 0} 集`,
        target: data.target || 0,
        skipped: data.skipped || 0,
        sources: data.total_sources || SyncWorkbench.latestSources,
    });

    const taskId = data.task_id || SyncWorkbench.taskId;
    if (!SyncWorkbench.doneTaskIds.has(taskId)) {
        SyncWorkbench.doneTaskIds.add(taskId);
        ToastManager.success(
            SyncWorkbench.mode === 'full'
                ? `全量刷新完成: ${data.synced} 集找到 ${data.total_sources} 个视频源`
                : `增量同步完成: 同步 ${data.synced} 集，跳过 ${data.skipped || 0} 集，找到 ${data.total_sources} 个视频源`
        );
    }

    setTimeout(() => {
        if (sessionId !== SyncWorkbench.sessionId) return;
        setSyncButtonsBusy(false);
        _refreshEpisodeList(SyncWorkbench.animeId);
        SyncWorkbench.summaryTimer = setTimeout(() => {
            if (sessionId === SyncWorkbench.sessionId) {
                const { progressDiv } = getSyncElements();
                if (progressDiv) progressDiv.classList.remove('visible');
            }
        }, 3500);
    }, 900);
}

function failSyncTask(message) {
    closeSyncEventSource();
    setSyncButtonsBusy(false);
    setSyncReconnectVisible(false);
    updateSyncCard({ stage: '同步失败', text: message });
    ToastManager.error(message);
}

async function syncAnime(animeId, mode = 'incremental') {
    if (mode === 'full' && !confirm('全量刷新会重新搜索全部集数并替换旧视频源，耗时较长，确定继续？')) return;

    SyncWorkbench.sessionId += 1;
    closeSyncEventSource();
    clearSyncSummaryTimer();
    setSyncButtonsBusy(true, mode);
    setSyncReconnectVisible(false);
    updateSyncCard({
        stage: '准备中',
        percent: 0,
        text: '正在创建同步任务...',
        target: 0,
        skipped: 0,
        sources: 0,
    });

    try {
        const resp = await apiRequest(`/api/anime/${animeId}/sync`, {
            method: 'POST',
            body: JSON.stringify({ mode }),
        });
        const taskId = resp.data?.task?.id;
        if (!taskId) throw new Error('同步任务创建失败');
        updateSyncCard({
            stage: resp.data?.created ? '已加入队列' : '接入已有任务',
            text: resp.data?.created ? '任务已加入队列，等待执行...' : '正在接入已有同步任务...',
        });
        openSyncTaskStream({ animeId, taskId, mode });
    } catch (err) {
        setSyncButtonsBusy(false);
        setSyncReconnectVisible(false);
        const { progressDiv } = getSyncElements();
        if (progressDiv) progressDiv.classList.remove('visible');
    }
}

async function reconnectSyncTask() {
    if (!SyncWorkbench.taskId || !SyncWorkbench.animeId) {
        ToastManager.info('暂无可重新接入的同步任务');
        return;
    }

    const { reconnectBtn } = getSyncElements();
    setButtonLoading(reconnectBtn, true, '接入中...');
    try {
        const resp = await apiRequest(`/api/sync_tasks/${SyncWorkbench.taskId}`);
        const task = resp.data;
        if (task.status === 'success') {
            updateSyncCard({ stage: '同步已完成', percent: 100, text: '任务已在后台完成，正在刷新列表...' });
            setSyncButtonsBusy(false);
            setSyncReconnectVisible(false);
            _refreshEpisodeList(SyncWorkbench.animeId);
            return;
        }
        if (task.status === 'error') {
            failSyncTask(task.error || '同步任务已失败');
            return;
        }
        openSyncTaskStream({
            animeId: SyncWorkbench.animeId,
            taskId: SyncWorkbench.taskId,
            mode: task.mode || SyncWorkbench.mode,
            reconnect: true,
        });
    } catch (err) {
        setButtonLoading(reconnectBtn, false);
    }
}

/**
 * 动态插入新发现的集数到集数列表
 */
function _insertNewEpisodes(animeId, epNums) {
    // 移除空状态提示
    const emptyState = document.querySelector('.episodes-section .empty-state');
    if (emptyState) {
        emptyState.remove();
    }

    // 确保 episodes-grid 容器存在
    let grid = document.querySelector('.episodes-grid');
    if (!grid) {
        const section = document.querySelector('.episodes-section');
        if (section) {
            grid = document.createElement('div');
            grid.className = 'episodes-grid';
            section.appendChild(grid);
        } else {
            return;
        }
    }

    // 收集已存在的集数
    const existingNums = new Set();
    grid.querySelectorAll('.episode-item').forEach(el => {
        existingNums.add(parseInt(el.dataset.ep));
    });

    // 排序后插入
    const sortedEpNums = [...epNums].map(Number).sort((a, b) => a - b);
    for (const epNum of sortedEpNums) {
        if (existingNums.has(epNum)) continue;

        const item = createEpisodeItem(animeId, {
            absolute_num: epNum,
            title: `第${epNum}集`,
            source_count: 0,
            watched: false,
        });
        insertEpisodeItemSorted(grid, item);
    }

    // 更新进度文字和集数统计
    const totalEps = grid.querySelectorAll('.episode-item').length;
    const metaItem = document.querySelector('.anime-detail__meta-item span strong');
    if (metaItem) {
        // 更新 "N 集" 数字
        const metaItems = document.querySelectorAll('.anime-detail__meta-item');
        metaItems.forEach(mi => {
            if (mi.textContent.includes('集') && !mi.textContent.includes('已看')) {
                const strong = mi.querySelector('strong');
                if (strong) strong.textContent = totalEps;
            }
        });
    }
    ensureEpisodeToolbar();
    updateContinueWatchButton();
    applyEpisodeFilters();
}

/**
 * 同步完成后通过 API 刷新集数列表和页面统计数据
 */
async function _refreshEpisodeList(animeId) {
    try {
        const resp = await apiRequest(`/api/anime/${animeId}`);
        const anime = resp.data;
        if (!anime) return;

        const episodes = anime.episodes || [];
        const grid = document.querySelector('.episodes-grid');

        if (grid && episodes.length > 0) {
            const emptyState = document.querySelector('.episodes-section .empty-state');
            if (emptyState) emptyState.remove();

            const existingNums = new Set();
            grid.querySelectorAll('.episode-item').forEach(el => {
                existingNums.add(parseInt(el.dataset.ep));
            });

            for (const ep of episodes) {
                const epNum = ep.absolute_num;
                if (existingNums.has(epNum)) {
                    const epItem = grid.querySelector(`.episode-item[data-ep="${epNum}"]`);
                    updateEpisodeItemState(epItem, ep);
                    continue;
                }

                const item = createEpisodeItem(animeId, ep);
                insertEpisodeItemSorted(grid, item);
            }
        } else if (!grid && episodes.length > 0) {
            const section = document.querySelector('.episodes-section');
            if (section) {
                const emptyState = section.querySelector('.empty-state');
                if (emptyState) emptyState.remove();
                const newGrid = document.createElement('div');
                newGrid.className = 'episodes-grid';
                for (const ep of episodes) {
                    const item = createEpisodeItem(animeId, ep);
                    newGrid.appendChild(item);
                }
                section.appendChild(newGrid);
            }
        }

        const totalEps = episodes.length;
        const watchedCount = episodes.filter(ep => ep.watched).length;
        const unwatchedCount = totalEps - watchedCount;

        const metaItems = document.querySelectorAll('.anime-detail__meta-item');
        metaItems.forEach(mi => {
            const strong = mi.querySelector('strong');
            if (!strong) return;
            const text = mi.textContent;
            if (text.includes('集') && !text.includes('已看')) {
                strong.textContent = totalEps;
            }
            if (text.includes('已看')) {
                strong.textContent = `${watchedCount}/${totalEps}`;
            }
        });

        const unwatchedSpan = document.querySelector('.episodes-section__header span');
        if (unwatchedSpan) {
            unwatchedSpan.textContent = `${unwatchedCount} 集未看`;
        }

        const progressFill = document.getElementById('progress-fill');
        if (progressFill && totalEps > 0) {
            progressFill.style.width = `${(watchedCount / totalEps * 100)}%`;
        }
        const progressText = document.getElementById('progress-text');
        if (progressText) {
            progressText.textContent = `${watchedCount}/${totalEps}`;
        }

        const progressInput = document.getElementById('progress-input');
        if (progressInput) {
            progressInput.max = totalEps;
        }
        ensureEpisodeToolbar();
        updateContinueWatchButton();
        applyEpisodeFilters();
    } catch (err) {
        location.reload();
    }
}

// ==================== 删除动漫 ====================

async function deleteAnime(animeId) {
    if (!confirm('确定要删除这部动漫吗？相关数据将一并删除。')) return;

    try {
        await apiRequest(`/api/anime/${animeId}`, { method: 'DELETE' });
        ToastManager.success('删除成功');
        setTimeout(() => location.href = '/', 800);
    } catch (err) { /* handled */ }
}

// ==================== 设置 ====================

function initInvidiousFallbackEditor() {
    const editor = document.getElementById('invidious-fallback-editor');
    const hidden = document.getElementById('invidious-fallback-urls');
    if (!editor || !hidden) return;
    const urls = parseInvidiousFallbackUrls(hidden.value);
    editor.innerHTML = '';
    urls.forEach(url => addInvidiousFallbackRow(url));
    if (!urls.length) {
        editor.innerHTML = '<div class="invidious-instance-empty">暂无备用实例，点击下方按钮添加自部署实例</div>';
    }
}

function parseInvidiousFallbackUrls(rawValue) {
    const text = (rawValue || '').trim();
    if (!text) return [];
    try {
        const parsed = JSON.parse(text);
        if (Array.isArray(parsed)) {
            return parsed.map(item => String(item).trim()).filter(Boolean);
        }
    } catch (err) { }
    return text.split(/[\n,]/).map(item => item.trim()).filter(Boolean);
}

function addInvidiousFallbackRow(value = '') {
    const editor = document.getElementById('invidious-fallback-editor');
    if (!editor) return;
    const empty = editor.querySelector('.invidious-instance-empty');
    if (empty) empty.remove();
    const row = document.createElement('div');
    row.className = 'invidious-instance-row';
    row.innerHTML = `
        <span class="invidious-instance-row__badge">备用</span>
        <input type="text" class="invidious-instance-row__input" value="${escapeHtml(value)}" placeholder="https://backup-invidious.example.com" oninput="syncInvidiousFallbackSetting()">
        <button type="button" class="invidious-instance-row__remove" onclick="removeInvidiousFallbackRow(this)" aria-label="删除备用实例">删除</button>
    `;
    editor.appendChild(row);
    syncInvidiousFallbackSetting();
}

function removeInvidiousFallbackRow(button) {
    const row = button.closest('.invidious-instance-row');
    if (row) row.remove();
    const editor = document.getElementById('invidious-fallback-editor');
    if (editor && !editor.querySelector('.invidious-instance-row')) {
        editor.innerHTML = '<div class="invidious-instance-empty">暂无备用实例，点击下方按钮添加自部署实例</div>';
    }
    syncInvidiousFallbackSetting();
}

function syncInvidiousFallbackSetting() {
    const hidden = document.getElementById('invidious-fallback-urls');
    if (!hidden) return;
    const urls = Array.from(document.querySelectorAll('.invidious-instance-row__input'))
        .map(input => input.value.trim().replace(/\/+$/, ''))
        .filter(Boolean)
        .filter((url, index, list) => list.indexOf(url) === index);
    hidden.value = JSON.stringify(urls);
}

async function saveSettings() {
    syncInvidiousFallbackSetting();
    const settings = {};
    document.querySelectorAll('[data-setting]').forEach(el => {
        const key = el.dataset.setting;
        if (el.type === 'checkbox') {
            settings[key] = el.checked ? 'true' : 'false';
        } else {
            settings[key] = el.value;
        }
    });

    try {
        await apiRequest('/api/settings', {
            method: 'PUT',
            body: JSON.stringify(settings),
        });
        ToastManager.success('设置已保存');
    } catch (err) { /* handled */ }
}

// ==================== 搜索规则 ====================

async function saveRules(animeId) {
    const allow = document.getElementById('rule-allow-keywords');
    const deny = document.getElementById('rule-deny-keywords');
    const allowCh = document.getElementById('rule-allow-channels');
    const denyCh = document.getElementById('rule-deny-channels');

    const rules = {
        allow_keywords: allow ? allow.value.split(',').map(s => s.trim()).filter(Boolean) : [],
        deny_keywords: deny ? deny.value.split(',').map(s => s.trim()).filter(Boolean) : [],
        allow_channels: allowCh ? allowCh.value.split(',').map(s => s.trim()).filter(Boolean) : [],
        deny_channels: denyCh ? denyCh.value.split(',').map(s => s.trim()).filter(Boolean) : [],
    };

    try {
        await apiRequest(`/api/anime/${animeId}/rules`, {
            method: 'PUT',
            body: JSON.stringify(rules),
        });
        ToastManager.success('搜索规则已保存');
    } catch (err) { /* handled */ }
}

// ==================== 别名管理 ====================

async function addAlias(animeId) {
    const input = document.getElementById('alias-input');
    const alias = input.value.trim();
    if (!alias) {
        ToastManager.error('请输入别名');
        return;
    }

    try {
        await apiRequest(`/api/anime/${animeId}/aliases`, {
            method: 'POST',
            body: JSON.stringify({ alias }),
        });
        ToastManager.success('别名已添加');
        input.value = '';
        setTimeout(() => location.reload(), 800);
    } catch (err) { /* handled */ }
}

// ==================== 集数排序 ====================

function toggleEpisodeSort() {
    const grid = document.querySelector('.episodes-grid');
    if (!grid) return;
    const btn = document.getElementById('sort-toggle-btn');
    if (!btn) return;

    // 翻转 DOM 顺序
    const items = Array.from(grid.children);
    items.reverse();
    items.forEach(item => grid.appendChild(item));

    // 切换按钮文字
    const currentOrder = getEpisodeSortOrder();
    const newOrder = currentOrder === 'desc' ? 'asc' : 'desc';
    btn.dataset.sortOrder = newOrder;
    btn.textContent = newOrder === 'desc' ? '↓ 倒序' : '↑ 正序';
    btn.setAttribute('aria-label', `当前${newOrder === 'desc' ? '倒序' : '正序'}，点击切换集数排序`);

    // 保存偏好
    apiRequest('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ episode_sort_order: newOrder }),
    }).then(() => {
        ToastManager.info(newOrder === 'desc' ? '已切换为倒序' : '已切换为正序');
    }).catch(() => { });
}

// ==================== 筛选 ====================

function filterAnimes(filter) {
    document.querySelectorAll('.filter-tab').forEach(t => {
        t.classList.remove('active');
        if (t.textContent.trim() === {
            'all': '全部', 'airing': '连载中', 'ended': '已完结', 'unwatched': '有更新'
        }[filter]) t.classList.add('active');
    });

    const cards = document.querySelectorAll('.anime-card');
    cards.forEach(card => {
        const status = card.dataset.status || '';
        const unwatched = parseInt(card.dataset.unwatched || '0', 10);

        let show = true;
        if (filter === 'airing') show = status === 'Returning Series';
        else if (filter === 'ended') show = status === 'Ended';
        else if (filter === 'unwatched') show = unwatched > 0;

        card.style.display = show ? '' : 'none';
    });
}

// ==================== 修改密码 ====================

async function changePassword() {
    const oldPwd = document.getElementById('old-password').value;
    const newPwd = document.getElementById('new-password').value;

    if (!oldPwd || !newPwd) {
        ToastManager.error('请填写当前密码和新密码');
        return;
    }

    try {
        const data = await apiRequest('/api/change_password', {
            method: 'POST',
            body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }),
        });
        ToastManager.success('密码修改成功');
        document.getElementById('old-password').value = '';
        document.getElementById('new-password').value = '';
    } catch (err) {
        // handled by apiRequest
    }
}

// ==================== 备份与恢复 ====================

async function importBackup(input) {
    const file = input.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    // 获取 CSRF token
    const csrfToken = document.querySelector('meta[name="csrf-token"]');
    const headers = {};
    if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken.getAttribute('content');
    }

    try {
        const resp = await fetch('/api/backup/import', {
            method: 'POST',
            headers,
            body: formData,
        });
        const data = await resp.json();
        if (data.success) {
            const stats = data.data || {};
            ToastManager.success(
                `导入完成: ${stats.animes_imported || 0} 部动漫, ${stats.episodes_imported || 0} 集, ${stats.sources_imported || 0} 个源`
            );
            setTimeout(() => location.reload(), 1500);
        } else {
            ToastManager.error(data.error || '导入失败');
        }
    } catch (err) {
        ToastManager.error('导入请求失败');
    }
    input.value = '';  // 重置文件选择
}

async function telegramBackup() {
    const btn = document.getElementById('tg-backup-btn');
    btn.disabled = true;
    btn.textContent = '发送中...';

    try {
        const data = await apiRequest('/api/backup/telegram', {
            method: 'POST',
        });
        ToastManager.success(`备份已发送到 Telegram: ${data.data?.filename || '成功'}`);
    } catch (err) {
        // handled by apiRequest
    }
    btn.disabled = false;
    btn.textContent = '📨 发送到 TG';
}

// ==================== 诊断中心 ====================

async function loadInvidiousHealth() {
    if (!document.getElementById('invidious-overall-card')) return;
    try {
        const resp = await apiRequest('/api/diagnostics/invidious');
        renderInvidiousHealth(resp.data || {});
    } catch (err) {
        // handled by apiRequest
    }
}

async function checkInvidiousHealth() {
    const btn = document.getElementById('invidious-check-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '检测中...';
    }
    try {
        const videoIdInput = document.getElementById('invidious-video-id-input');
        const videoId = videoIdInput ? videoIdInput.value.trim() : '';
        const resp = await apiRequest('/api/diagnostics/invidious', {
            method: 'POST',
            body: JSON.stringify({ video_id: videoId }),
        });
        renderInvidiousHealth(resp.data || {});
        ToastManager.success(resp.message || 'Invidious 健康检测完成');
    } catch (err) {
        // handled by apiRequest
    }
    if (btn) {
        btn.disabled = false;
        btn.textContent = '🔎 立即检测';
    }
}

function renderInvidiousHealth(data) {
    const status = data.overall_status || 'unknown';
    const statusMap = {
        healthy: '健康',
        degraded: '链路异常',
        down: '不可用',
        unknown: '未检测',
    };
    const overallCard = document.getElementById('invidious-overall-card');
    const overallText = document.getElementById('invidious-overall-text');
    const checkedAt = document.getElementById('invidious-checked-at');
    const activeUrl = document.getElementById('invidious-active-url');
    const timeout = document.getElementById('invidious-timeout');
    const lbRatio = document.getElementById('invidious-lb-ratio');
    const lbDetail = document.getElementById('invidious-lb-detail');
    const loadBalance = data.load_balance || {};

    if (overallCard) overallCard.dataset.status = status;
    if (overallText) overallText.textContent = statusMap[status] || status;
    if (checkedAt) checkedAt.textContent = data.checked_at ? `最近检测：${data.checked_at}` : '等待首次健康检测';
    if (activeUrl) activeUrl.textContent = data.active_url || '-';
    if (timeout) timeout.textContent = `超时配置：${data.timeout || '-'} 秒`;
    if (lbRatio) lbRatio.textContent = loadBalance.ratio_text || '7:3';
    if (lbDetail) lbDetail.textContent = `${loadBalance.description || '主实例约 70%，备用实例整体约 30%'} · 可用 ${loadBalance.available_count ?? 0}/${loadBalance.total_count ?? 0}`;

    renderInvidiousInstances(data.instances || []);
    renderInvidiousVideoProbe(data.video_probe || {});
    renderInvidiousVideoProbes(data.video_probes || []);
}

function renderInvidiousInstances(instances) {
    const list = document.getElementById('invidious-instance-list');
    if (!list) return;
    if (!instances.length) {
        list.innerHTML = '<div class="diagnostics-empty">暂无检测数据</div>';
        return;
    }
    list.innerHTML = instances.map((item, index) => `
        <div class="diagnostics-instance diagnostics-instance--${item.available ? 'ok' : 'bad'}">
            <div class="diagnostics-instance__main">
                <span class="diagnostics-dot"></span>
                <div>
                    <div class="diagnostics-instance__url">${escapeHtml(item.url || '-')}</div>
                    <div class="diagnostics-instance__meta">
                        ${escapeHtml(item.role_text || (index === 0 ? '主实例' : '备用实例'))} · 权重 ${item.weight ?? '-'} · HTTP ${item.status_code || '-'} · ${item.latency_ms ?? '-'} ms
                    </div>
                </div>
            </div>
            <div class="diagnostics-instance__side">
                <span class="diagnostics-role diagnostics-role--${item.role || 'fallback'}">${escapeHtml(item.role_text || '备用实例')}</span>
                <span class="diagnostics-badge diagnostics-badge--${item.available ? 'ok' : 'bad'}">${item.available ? '可用' : '异常'}</span>
                <span>${escapeHtml(item.version || item.error || '')}</span>
            </div>
        </div>
    `).join('');
}

function renderInvidiousVideoProbe(probe) {
    const status = document.getElementById('invidious-video-status');
    const detail = document.getElementById('invidious-video-detail');
    const box = document.getElementById('invidious-video-probe');
    if (status) status.textContent = probe.available ? '可用' : (probe.error ? '异常' : '未检测');
    if (detail) detail.textContent = probe.available ? `${probe.title || '视频详情可访问'} · ${probe.latency_ms ?? '-'} ms` : (probe.error || '使用默认公开视频 ID 进行探测');
    if (!box) return;
    if (!probe.video_id) {
        box.innerHTML = '<div class="diagnostics-empty">暂无视频详情检测数据</div>';
        return;
    }
    box.innerHTML = `
        <div class="diagnostics-probe__row">
            <span>视频 ID</span>
            <strong>${escapeHtml(probe.video_id || '-')}</strong>
        </div>
        <div class="diagnostics-probe__row">
            <span>HTTP 状态</span>
            <strong>${probe.status_code || '-'}</strong>
        </div>
        <div class="diagnostics-probe__row">
            <span>响应耗时</span>
            <strong>${probe.latency_ms ?? '-'} ms</strong>
        </div>
        <div class="diagnostics-probe__row">
            <span>视频标题</span>
            <strong>${escapeHtml(probe.title || '-')}</strong>
        </div>
        <div class="diagnostics-probe__row diagnostics-probe__row--full">
            <span>最近错误</span>
            <strong>${escapeHtml(probe.error || '无')}</strong>
        </div>
    `;
}

function renderInvidiousVideoProbes(probes) {
    const list = document.getElementById('invidious-video-probe-list');
    if (!list) return;
    if (!probes.length) {
        list.innerHTML = '<div class="diagnostics-empty">暂无逐实例视频详情探针数据</div>';
        return;
    }
    list.innerHTML = probes.map(item => `
        <div class="diagnostics-instance diagnostics-instance--${item.available ? 'ok' : 'bad'}">
            <div class="diagnostics-instance__main">
                <span class="diagnostics-dot"></span>
                <div>
                    <div class="diagnostics-instance__url">${escapeHtml(item.url || '-')}</div>
                    <div class="diagnostics-instance__meta">
                        ${escapeHtml(item.role_text || '实例')} · 视频 ID ${escapeHtml(item.video_id || '-')} · HTTP ${item.status_code || '-'} · ${item.latency_ms ?? '-'} ms
                    </div>
                </div>
            </div>
            <div class="diagnostics-instance__side">
                <span class="diagnostics-role diagnostics-role--${item.role || 'fallback'}">${escapeHtml(item.role_text || '实例')}</span>
                <span class="diagnostics-badge diagnostics-badge--${item.available ? 'ok' : 'bad'}">${item.available ? '详情可用' : '详情异常'}</span>
                <span>${escapeHtml(item.title || item.error || '')}</span>
            </div>
        </div>
    `).join('');
}

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    ThemeManager.init();
    ToastManager.init();
    initSearch();
    initEpisodeWorkbench();
    initInvidiousFallbackEditor();
    loadInvidiousHealth();

    // 主题切换按钮
    const themeToggle = document.querySelector('.navbar__theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleThemeDropdown();
        });
    }

    updateThemeDropdownActive();

    // ESC 关闭模态框和主题下拉菜单
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSourcesModal();
            closeThemeDropdown();
        }
    });

    // 点击外部关闭主题下拉菜单
    document.addEventListener('click', (e) => {
        const themeSelector = document.querySelector('.navbar__theme-selector');
        if (themeSelector && !themeSelector.contains(e.target)) {
            closeThemeDropdown();
        }
    });
});
