/**
 * 追漫阁 Go 版 - 统计页交互
 * 从 /api/stats 获取完整统计数据，渲染概要卡、状态分布条、14天活动柱状图、TOP10、待追榜。
 * 公共工具函数已抽取到 common.js。
 */

async function loadStats() {
    const container = document.getElementById('stats-root');
    if (!container) return;
    container.innerHTML = '<div style="padding:48px;text-align:center;color:var(--text-muted);">加载中...</div>';
    try {
        const resp = await fetch('/api/stats', { headers: apiHeaders() });
        const d = await resp.json();
        const s = d.data || {};
        container.innerHTML = renderStats(s);
    } catch (e) {
        container.innerHTML = '<div style="padding:48px;text-align:center;color:var(--danger);">加载失败</div>';
    }
}

function renderStats(s) {
    const totalAnimes = s.anime_count || 0;
    const completion = s.completion_rate || 0;
    const hours = s.estimated_hours || 0;

    // 概要卡
    const cards = `
    <div class="stats-cards">
        <div class="stats-card"><div class="stats-card__icon">📺</div><div class="stats-card__value">${totalAnimes}</div><div class="stats-card__label">追番总数</div></div>
        <div class="stats-card"><div class="stats-card__icon">✅</div><div class="stats-card__value">${s.watched_count || 0}</div><div class="stats-card__label">已看集数</div></div>
        <div class="stats-card stats-card--accent"><div class="stats-card__icon">⏱️</div><div class="stats-card__value">${hours}</div><div class="stats-card__label">预计时长（小时）</div></div>
        <div class="stats-card"><div class="stats-card__icon">📈</div><div class="stats-card__value">${completion}%</div><div class="stats-card__label">集数完成率</div></div>
    </div>`;

    // 状态分布条形图
    let statusHTML = '<div class="stats-empty">暂无数据</div>';
    if (s.status_dist && s.status_dist.length) {
        statusHTML = s.status_dist.map(item => {
            const pct = totalAnimes > 0 ? (item.count / totalAnimes * 100) : 0;
            return `<div class="stat-bar-row">
                <span class="stat-bar-row__label">${escapeHtml(item.label)}</span>
                <div class="stat-bar-row__track"><div class="stat-bar-row__fill" style="width:${pct}%"></div></div>
                <span class="stat-bar-row__value">${item.count}</span>
            </div>`;
        }).join('');
    }

    // 14天同步活动柱状图
    let activityHTML = '<div class="stats-empty">暂无同步记录</div>';
    if (s.sync_activity && s.sync_activity.length) {
        const maxSync = s.max_sync_count || 1;
        activityHTML = `<div class="activity-chart">${s.sync_activity.map(day => {
            const h = Math.max((day.syncs / maxSync * 100), 4);
            return `<div class="activity-chart__col" title="${day.date}: ${day.syncs} 次同步，${day.sources} 个视频源">
                <div class="activity-chart__bar" style="height:${h}%"></div>
                <div class="activity-chart__label">${day.date.slice(5)}</div>
            </div>`;
        }).join('')}</div>`;
    }

    // 完成度 TOP 10
    let topHTML = '';
    if (s.top_progress && s.top_progress.length) {
        topHTML = `<div class="stats-section" style="margin-top:24px;">
            <h3 class="stats-section__title">完成度 TOP 10</h3>
            ${s.top_progress.map(a => `
            <div class="progress-row">
                <a href="/anime/${a.id}" class="progress-row__title">${escapeHtml(a.title_cn)}</a>
                <div class="progress-row__track"><div class="progress-row__fill" style="width:${a.pct}%"></div></div>
                <span class="progress-row__meta">${a.watched_count}/${a.ep_count}<em>${a.pct}%</em></span>
            </div>`).join('')}
        </div>`;
    }

    // 待追最多
    let pendingHTML = '';
    if (s.most_pending && s.most_pending.length) {
        pendingHTML = `<div class="stats-section" style="margin-top:24px;">
            <h3 class="stats-section__title">待追最多</h3>
            <div class="pending-list">
                ${s.most_pending.map(a => `
                <a href="/anime/${a.id}" class="pending-item">
                    <span class="pending-item__title">${escapeHtml(a.title_cn)}</span>
                    <span class="pending-item__badge">${a.unwatched} 集未看</span>
                </a>`).join('')}
            </div>
        </div>`;
    }

    return `${cards}
    <div class="stats-grid">
        <div class="stats-section"><h3 class="stats-section__title">追番状态分布</h3>${statusHTML}</div>
        <div class="stats-section"><h3 class="stats-section__title">近 14 天同步活动</h3>${activityHTML}</div>
    </div>
    ${topHTML}${pendingHTML}`;
}

document.addEventListener('DOMContentLoaded', loadStats);
