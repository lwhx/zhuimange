// 追漫阁 Go 版前端交互（Alpine.js + HTMX 增强）

// ==================== Toast 通知 ====================
const ToastManager = {
    show(msg, type = 'info', duration = 3000) {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `toast toast--${type}`;
        toast.textContent = msg;
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },
    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error', 5000); },
    info(msg) { this.show(msg, 'info'); },
    warning(msg) { this.show(msg, 'warning', 5000); },
};

// ==================== 主题切换 ====================
const THEMES = ['midnight', 'ocean', 'forest', 'sunset', 'nord', 'light'];
function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'midnight';
    const idx = THEMES.indexOf(current);
    const next = THEMES[(idx + 1) % THEMES.length];
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('zmg-theme', next);
    ToastManager.info(`主题已切换为 ${next}`);
}

// ==================== CSRF Token（双重提交 cookie）====================
function getCSRFToken() {
    const match = document.cookie.match(/zmg_csrf=([^;]+)/);
    return match ? match[1] : '';
}

// ==================== API 请求封装 ====================
async function apiRequest(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    // 写操作带 CSRF token
    if (options.method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(options.method.toUpperCase())) {
        headers['X-CSRF-Token'] = getCSRFToken();
    }
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(options.body);
    }
    const resp = await fetch(url, { ...options, headers });
    const contentType = resp.headers.get('content-type') || '';
    if (!resp.ok) {
        let errMsg = `请求失败 (${resp.status})`;
        if (contentType.includes('application/json')) {
            const err = await resp.json();
            errMsg = err.error || errMsg;
        }
        ToastManager.error(errMsg);
        throw new Error(errMsg);
    }
    if (contentType.includes('application/json')) {
        return resp.json();
    }
    return resp.text();
}

// ==================== 搜索动漫 ====================
let searchTimer = null;
let searchAbort = null;

function initSearch() {
    const input = document.getElementById('search-input');
    const results = document.getElementById('search-results');
    if (!input || !results) return;

    input.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        if (query.length < 2) {
            results.classList.remove('visible');
            return;
        }
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => searchAnime(query), 400);
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const query = input.value.trim();
            if (query.length >= 2) {
                e.preventDefault();
                clearTimeout(searchTimer);
                searchAnime(query);
            }
        }
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-box')) {
            results.classList.remove('visible');
        }
    });
}

async function searchAnime(query) {
    const results = document.getElementById('search-results');
    if (searchAbort) searchAbort.abort();
    searchAbort = new AbortController();

    results.innerHTML = '<div style="padding:16px;color:var(--text-muted);text-align:center;">搜索中...</div>';
    results.classList.add('visible');

    try {
        const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}`, { signal: searchAbort.signal });
        if (searchAbort.signal.aborted) return;
        const data = await resp.json();
        const items = data.data || [];
        if (items.length === 0) {
            results.innerHTML = `<div style="padding:16px;color:var(--text-muted);text-align:center;">
                没有找到"${escapeHtml(query)}"相关动漫</div>`;
            return;
        }
        results.innerHTML = items.map(item => `
            <div class="search-result-item" onclick="addAnime(${item.tmdb_id})">
                ${item.poster_url ? `<img class="search-result-item__poster" src="${item.poster_url}" alt="">` : ''}
                <div class="search-result-item__info">
                    <div class="search-result-item__title">${escapeHtml(item.title_cn)}</div>
                    <div class="search-result-item__meta">${escapeHtml(item.air_date || '')} · ${item.total_episodes || '?'} 集</div>
                </div>
                <button class="search-result-item__add-btn" onclick="event.stopPropagation();addAnime(${item.tmdb_id})">+ 添加</button>
            </div>
        `).join('');
    } catch (err) {
        if (err.name === 'AbortError') return;
        results.innerHTML = '<div style="padding:16px;color:var(--danger);text-align:center;">搜索失败</div>';
    }
}

async function addAnime(tmdbId) {
    try {
        await apiRequest('/api/anime/add', {
            method: 'POST',
            body: { tmdb_id: tmdbId },
        });
        ToastManager.success('添加成功！即将跳转详情页');
        // 重新加载以显示新卡片（或跳转详情）
        setTimeout(() => location.reload(), 800);
    } catch (err) {
        // handled by apiRequest
    }
}

// ==================== 辅助函数 ====================
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ==================== 集数操作 ====================
async function markWatched(animeId, epNum) {
    try {
        await apiRequest(`/api/anime/${animeId}/episode/${epNum}/watch`, { method: 'POST' });
        location.reload();
    } catch (err) { /* handled */ }
}

async function openSources(animeId, epNum) {
    const overlay = document.getElementById('sources-modal-overlay');
    overlay.style.display = 'flex';
    overlay.innerHTML = '<div style="padding:40px;color:var(--text-muted);">加载中...</div>';
    try {
        const html = await apiRequest(`/anime/${animeId}/episode/${epNum}/sources`);
        overlay.innerHTML = html;
        overlay.onclick = (e) => { if (e.target === overlay) overlay.style.display = 'none'; };
    } catch (err) {
        overlay.innerHTML = '<div style="padding:40px;color:var(--danger);">加载失败</div>';
    }
}

function closeModal() {
    const overlay = document.getElementById('sources-modal-overlay');
    if (overlay) overlay.style.display = 'none';
}

// ==================== 全局键盘快捷键 ====================
document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) {
        const input = document.getElementById('search-input');
        if (input) { e.preventDefault(); input.focus(); }
    }
    if (e.key === 'Escape') closeModal();
});

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    initSearch();
});
