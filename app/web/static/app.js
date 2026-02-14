/**
 * 追漫阁 - 前端交互
 */

// ==================== 主题管理 ====================

const ThemeManager = {
    STORAGE_KEY: 'zhuimange-theme',
    MODE_KEY: 'zhuimange-theme-mode',

    themes: [
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

        const theme = savedTheme || 'neon-purple';
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
        const saved = localStorage.getItem(this.STORAGE_KEY) || 'neon-purple';
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
    results.innerHTML = '<div class="p-4" style="padding:16px;color:var(--text-muted);text-align:center;">搜索中...</div>';
    results.classList.add('visible');

    try {
        const data = await apiRequest(`/api/search?q=${encodeURIComponent(query)}`);
        if (data.length === 0) {
            results.innerHTML = '<div style="padding:16px;color:var(--text-muted);text-align:center;">没有找到相关动漫</div>';
            return;
        }

        results.innerHTML = data.map(item => `
            <div class="search-result-item" data-tmdb-id="${item.tmdb_id}">
                <img class="search-result-item__poster"
                     src="${item.poster_url || ''}"
                     alt="${item.title_cn}"
                     onerror="this.style.background='var(--bg-tertiary)'">
                <div class="search-result-item__info">
                    <div class="search-result-item__title">${item.title_cn}</div>
                    <div class="search-result-item__meta">
                        ${item.title_en ? item.title_en + ' · ' : ''}
                        ${item.air_date || '未知'} · ${item.total_episodes || '?'}集
                    </div>
                </div>
                <button class="search-result-item__add-btn"
                        onclick="event.stopPropagation(); addAnime(${item.tmdb_id})">
                    + 添加
                </button>
            </div>
        `).join('');
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
            ${anime.poster_url ? `<img class="anime-card__poster" src="${anime.poster_url}" alt="${anime.title_cn}" loading="lazy" onerror="this.style.display='none'">` : ''}
            ${badge}
        </div>
        <div class="anime-card__body">
            <div class="anime-card__title" title="${anime.title_cn}">${anime.title_cn}</div>
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

    body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">加载中...</div>';
    overlay.classList.add('visible');

    try {
        const resp = await fetch(`/anime/${animeId}/episode/${epNum}/sources`);
        body.innerHTML = await resp.text();
    } catch (err) {
        body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--danger);">加载失败</div>';
    }
}

function closeSourcesModal() {
    const overlay = document.getElementById('sources-modal-overlay');
    overlay.classList.remove('visible');
}

async function findSources(animeId, epNum, force = false) {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '搜索中...';

    try {
        await apiRequest(`/api/anime/${animeId}/episode/${epNum}/find_sources`, {
            method: 'POST',
            body: JSON.stringify({ force }),
        });
        ToastManager.success('搜索完成');
        // 重新打开模态框以刷新结果
        openSourcesModal(animeId, epNum);
    } catch (err) {
        btn.disabled = false;
        btn.textContent = '搜索视频源';
    }
}

// ==================== 同步 ====================

function syncAnime(animeId) {
    const btn = document.getElementById('sync-btn');
    const progressDiv = document.getElementById('sync-progress');
    const progressFill = document.getElementById('sync-progress-fill');
    const progressText = document.getElementById('sync-progress-text');

    btn.disabled = true;
    btn.textContent = '同步中...';
    progressDiv.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = '准备中...';

    const es = new EventSource(`/api/anime/${animeId}/sync_stream`);

    es.onmessage = function (event) {
        const data = JSON.parse(event.data);

        if (data.type === 'start') {
            progressText.textContent = `0/${data.total}`;
        }
        else if (data.type === 'episode') {
            const pct = Math.round(data.current / data.total * 100);
            progressFill.style.width = pct + '%';
            progressText.textContent = `${data.current}/${data.total}`;

            // 实时更新对应集数的视频源数量
            const epItem = document.querySelector(`.episode-item[data-ep="${data.ep_num}"]`);
            if (epItem) {
                const dateDiv = epItem.querySelector('.episode-item__date');
                if (dateDiv && data.source_count > 0) {
                    // 更新或追加源数量
                    const existing = dateDiv.textContent;
                    const srcText = `${data.source_count} 个视频源`;
                    if (existing.includes('个视频源')) {
                        dateDiv.textContent = existing.replace(/\d+ 个视频源/, srcText);
                    } else {
                        dateDiv.textContent = (existing.trim() ? existing.trim() + ' · ' : '') + srcText;
                    }
                }
            }
        }
        else if (data.type === 'done') {
            es.close();
            progressFill.style.width = '100%';
            progressText.textContent = '✓ 完成';
            ToastManager.success(
                `同步完成: ${data.synced} 集找到 ${data.total_sources} 个视频源`
            );
            setTimeout(() => {
                btn.disabled = false;
                btn.textContent = '🔄 同步视频源';
                progressDiv.style.display = 'none';
            }, 2000);
        }
    };

    es.onerror = function () {
        es.close();
        btn.disabled = false;
        btn.textContent = '🔄 同步视频源';
        progressDiv.style.display = 'none';
        ToastManager.error('同步连接中断');
    };
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

async function saveSettings() {
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

    // 翻转 DOM 顺序
    const items = Array.from(grid.children);
    items.reverse();
    items.forEach(item => grid.appendChild(item));

    // 切换按钮文字
    const btn = document.getElementById('sort-toggle-btn');
    const isDesc = btn.textContent.trim().includes('倒序');
    const newOrder = isDesc ? 'asc' : 'desc';
    btn.textContent = newOrder === 'desc' ? '↓ 倒序' : '↑ 正序';

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
    document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');

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

    try {
        const resp = await fetch('/api/backup/import', {
            method: 'POST',
            body: formData,
        });
        const data = await resp.json();
        if (data.success) {
            ToastManager.success(
                `导入完成: ${data.animes_imported} 部动漫, ${data.episodes_imported} 集, ${data.sources_imported} 个源`
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
        ToastManager.success(`备份已发送到 Telegram: ${data.filename}`);
    } catch (err) {
        // handled by apiRequest
    }
    btn.disabled = false;
    btn.textContent = '📨 发送到 TG';
}

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    ThemeManager.init();
    ToastManager.init();
    initSearch();

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
