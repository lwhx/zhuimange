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

// ==================== 确认弹窗 ====================
// showConfirm 返回 Promise<boolean>，替代原生 confirm()。
// 支持自定义图标、标题、描述、确认/取消按钮文案与风格。
function showConfirm(opts = {}) {
    return new Promise((resolve) => {
        const {
            icon = '⚠️',
            iconType = 'warning', // warning | danger | info
            title = '确认操作',
            desc = '',
            details = [], // 额外说明列表 [{icon, text}]
            confirmText = '确认',
            cancelText = '取消',
            confirmType = 'danger', // primary | danger | warning
        } = opts;

        const overlay = document.createElement('div');
        overlay.className = 'confirm-overlay';

        const detailsHTML = details.length
            ? `<div class="confirm-body__details">${details.map(d =>
                `<div class="confirm-detail"><span class="confirm-detail__icon">${d.icon}</span><span class="confirm-detail__text">${d.text}</span></div>`
              ).join('')}</div>`
            : '';

        overlay.innerHTML = `
            <div class="confirm-dialog confirm-dialog--${iconType}">
                <div class="confirm-dialog__icon confirm-dialog__icon--${iconType}">${icon}</div>
                <div class="confirm-dialog__body">
                    <div class="confirm-dialog__title">${title}</div>
                    ${desc ? `<div class="confirm-dialog__desc">${desc}</div>` : ''}
                    ${detailsHTML}
                </div>
                <div class="confirm-dialog__actions">
                    <button class="btn btn--secondary confirm-cancel">${cancelText}</button>
                    <button class="btn btn--${confirmType} confirm-ok">${confirmText}</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
        // 触发动画
        requestAnimationFrame(() => overlay.classList.add('confirm-overlay--open'));

        let resolved = false;
        const close = (result) => {
            if (resolved) return;
            resolved = true;
            overlay.classList.remove('confirm-overlay--open');
            setTimeout(() => overlay.remove(), 250);
            resolve(result);
        };

        overlay.querySelector('.confirm-ok').addEventListener('click', () => close(true));
        overlay.querySelector('.confirm-cancel').addEventListener('click', () => close(false));
        // 点击遮罩取消
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });
        // Esc 取消
        const escHandler = (e) => { if (e.key === 'Escape') { close(false); document.removeEventListener('keydown', escHandler); } };
        document.addEventListener('keydown', escHandler);
        // 聚焦确认按钮
        setTimeout(() => overlay.querySelector('.confirm-ok').focus(), 100);
    });
}

// ==================== 主题切换 ====================
// 主题同时写入 localStorage（客户端即时生效）和 cookie（服务端渲染 data-theme 一致），
// 避免跨页面/刷新出现首页与详情页主题不同步的问题。

function setTheme(theme) {
    if (!theme) return;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('zmg-theme', theme);
    // cookie 有效期 1 年，path=/ 确保所有页面共享
    document.cookie = 'zmg-theme=' + encodeURIComponent(theme) + ';path=/;max-age=31536000;SameSite=Lax';
    // 更新下拉菜单选中态
    document.querySelectorAll('.theme-option').forEach(btn => {
        btn.classList.toggle('theme-option--active', btn.dataset.theme === theme);
    });
    ToastManager.info('主题已切换');
}

function toggleThemeDropdown() {
    const dropdown = document.getElementById('theme-dropdown');
    if (!dropdown) return;
    const isOpen = dropdown.classList.toggle('theme-dropdown--open');
    if (isOpen) {
        // 标记当前主题
        const current = document.documentElement.getAttribute('data-theme') || 'midnight';
        document.querySelectorAll('.theme-option').forEach(btn => {
            btn.classList.toggle('theme-option--active', btn.dataset.theme === current);
        });
    }
}

// 点击下拉外部关闭
document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('theme-dropdown');
    const selector = document.querySelector('.navbar__theme-selector');
    if (dropdown && dropdown.classList.contains('theme-dropdown--open') &&
        selector && !selector.contains(e.target)) {
        dropdown.classList.remove('theme-dropdown--open');
    }
});

// 兼容旧调用（详情页/其他页面可能引用 toggleTheme）
function toggleTheme() {
    const THEMES = ['midnight', 'ocean', 'forest', 'sunset', 'light'];
    const current = document.documentElement.getAttribute('data-theme') || 'midnight';
    const idx = THEMES.indexOf(current);
    setTheme(THEMES[(idx + 1) % THEMES.length]);
}

// CSRF Token / API 请求封装 / toast / escapeHtml 等公共函数已抽取到 common.js，
// 本文件仅保留主站专属逻辑：主题切换、ToastManager、showConfirm、搜索、添加动漫。

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
                没有找到"${escapeHtml(query)}"相关动漫<br>
                <a href="#" onclick="event.preventDefault();prefillManualAdd('${escapeHtml(query)}')" style="color:var(--accent);font-size:0.85rem;">✏️ 手动添加"${escapeHtml(query)}"</a></div>`;
            return;
        }
        results.innerHTML = items.map(item => `
            <div class="search-result-item" onclick="addAnime(${item.tmdb_id})">
                ${item.poster_url ? `<img class="search-result-item__poster" src="${escapeAttr(item.poster_url)}" alt="">` : ''}
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

// ==================== 首页集数操作（简化版，详情页用 detail.js 的完整版）====================
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

// ==================== 手动添加动漫 ====================

function toggleManualAdd() {
    const form = document.getElementById('manual-add-form');
    if (!form) return;
    const visible = form.style.display !== 'none';
    form.style.display = visible ? 'none' : 'block';
    if (!visible) {
        const title = document.getElementById('manual-title');
        if (title) title.focus();
    }
}

function prefillManualAdd(title = '') {
    const form = document.getElementById('manual-add-form');
    if (form) form.style.display = 'block';
    const titleInput = document.getElementById('manual-title');
    if (titleInput) {
        titleInput.value = title;
        titleInput.focus();
    }
    const results = document.getElementById('search-results');
    if (results) results.classList.remove('visible');
}

async function submitManualAdd(btn) {
    const title = document.getElementById('manual-title').value.trim();
    const totalEp = parseInt(document.getElementById('manual-total-ep').value || '0', 10);
    const aliases = document.getElementById('manual-aliases').value
        .split(',').map(a => a.trim()).filter(Boolean);

    if (!title) {
        toast('请输入动漫名称', 'error');
        return;
    }

    const originalText = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = '添加中...'; }
    try {
        const data = await apiRequest('/api/anime/add_manual', {
            method: 'POST',
            body: JSON.stringify({ title, total_episodes: totalEp, aliases }),
        });
        const animeId = data.data.anime_id;
        toast('添加成功，正在跳转...', 'success');

        // 清空表单并跳转详情页（手动添加的动漫同样需要同步视频源）
        document.getElementById('manual-title').value = '';
        document.getElementById('manual-total-ep').value = '';
        document.getElementById('manual-aliases').value = '';
        toggleManualAdd();

        setTimeout(() => location.href = '/anime/' + animeId, 800);
    } catch (e) {
        // apiRequest 已弹 toast
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = originalText; }
    }
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
