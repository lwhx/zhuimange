/**
 * 追漫阁 Go 版 - 看板页交互
 * 渲染追更进度卡片网格，支持全部/缺源/连载中筛选。
 * 公共工具函数已抽取到 common.js。
 */

let allItems = [];
let currentFilter = 'all';

async function loadDashboard() {
    const root = document.getElementById('dash-root');
    if (!root) return;
    root.innerHTML = '<div class="dash-loading">加载中...</div>';
    try {
        const resp = await fetch('/api/dashboard?limit=50', { headers: apiHeaders() });
        const d = await resp.json();
        allItems = d.data || [];
        renderDashboard();
    } catch (e) {
        root.innerHTML = '<div class="dash-loading dash-loading--error">加载失败</div>';
    }
}

function renderDashboard() {
    const root = document.getElementById('dash-root');
    if (!root) return;

    let items = allItems;
    if (currentFilter === 'missing') {
        items = items.filter(x => x.missing_sources > 0);
    }

    if (!items.length) {
        root.innerHTML = '<div class="dash-empty"><div class="dash-empty__icon">📭</div><div class="dash-empty__title">' +
            (currentFilter === 'missing' ? '没有缺源的动漫' : '还没有追更的动漫') +
            '</div><div class="dash-empty__desc">去首页添加几部动漫吧</div></div>';
        return;
    }

    root.innerHTML = '<div class="dash-grid">' + items.map(renderCard).join('') + '</div>';
}

function renderCard(item) {
    const watched = item.watched_ep || 0;
    const total = item.total_episodes || 0;
    const pct = total > 0 ? Math.round(watched / total * 100) : 0;
    const missing = item.missing_sources || 0;
    const hasPoster = item.poster_url && item.poster_url !== '';

    const sourceBadge = missing > 0
        ? `<span class="dash-card__badge dash-card__badge--warn">⚠️ 缺 ${missing} 源</span>`
        : `<span class="dash-card__badge dash-card__badge--ok">✓ 源齐全</span>`;

    const poster = hasPoster
        ? `<img class="dash-card__poster" src="${proxyImg(item.poster_url)}" alt="${escapeHtml(item.title_cn)}" loading="lazy">`
        : `<div class="dash-card__poster dash-card__poster--empty">📺</div>`;

    return `<a href="/anime/${item.anime_id}" class="dash-card ${missing > 0 ? 'dash-card--missing' : ''}">
        <div class="dash-card__poster-wrap">${poster}
            <div class="dash-card__pct">${pct}%</div>
        </div>
        <div class="dash-card__body">
            <div class="dash-card__title">${escapeHtml(item.title_cn)}</div>
            <div class="dash-card__progress">
                <div class="dash-card__progress-fill" style="width:${pct}%"></div>
            </div>
            <div class="dash-card__meta">
                <span class="dash-card__count">${watched}/${total}</span>
                ${sourceBadge}
            </div>
        </div>
    </a>`;
}

function setDashboardFilter(filter) {
    currentFilter = filter;
    document.querySelectorAll('.dash-filter').forEach(btn => {
        btn.classList.toggle('dash-filter--active', btn.dataset.filter === filter);
    });
    renderDashboard();
}

document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
});
