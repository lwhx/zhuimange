/**
 * 追漫阁 Go 版 - 日历页交互
 * 月历网格视图，支持月份导航、今天高亮、番剧徽章。
 * 公共工具函数已抽取到 common.js。
 */

// 每部番剧分配一种颜色（循环色板）
const BADGE_COLORS = [
    '#3b82f6', '#22c55e', '#f59e0b', '#ec4899', '#8b5cf6',
    '#06b6d4', '#ef4444', '#10b981', '#f97316', '#6366f1',
];

let viewYear, viewMonth; // 当前查看的年月
const today = new Date();
let itemsByDate = {}; // { 'YYYY-MM-DD': [{title_cn, absolute_num, anime_id}] }
let colorMap = {};    // { anime_id: '#color' }

async function loadCalendar(year, month) {
    viewYear = year;
    viewMonth = month;
    const titleEl = document.getElementById('cal-title');
    if (titleEl) titleEl.textContent = `${year}年${month}月`;

    const grid = document.getElementById('cal-grid');
    if (grid) grid.innerHTML = '<div class="cal-loading">加载中...</div>';

    // 计算该月前后各跨一周的日期范围（覆盖月历格子的首尾溢出）
    const firstDay = new Date(year, month - 1, 1);
    const gridStart = new Date(firstDay);
    gridStart.setDate(gridStart.getDate() - ((firstDay.getDay() + 6) % 7)); // 周一为首
    const gridEnd = new Date(gridStart);
    gridEnd.setDate(gridEnd.getDate() + 41); // 6 行 × 7 天

    const start = formatDate(gridStart);
    const end = formatDate(gridEnd);

    try {
        const resp = await fetch(`/api/calendar?start=${start}&end=${end}`, { headers: apiHeaders() });
        const d = await resp.json();
        const items = d.data?.items || [];
        buildIndex(items);
        renderCalendar(year, month);
    } catch (e) {
        if (grid) grid.innerHTML = '<div class="cal-loading cal-loading--error">加载失败</div>';
    }
}

function buildIndex(items) {
    itemsByDate = {};
    colorMap = {};
    let colorIdx = 0;
    for (const item of items) {
        const date = item.air_date;
        if (!itemsByDate[date]) itemsByDate[date] = [];
        itemsByDate[date].push(item);
        if (!colorMap[item.anime_id]) {
            colorMap[item.anime_id] = BADGE_COLORS[colorIdx % BADGE_COLORS.length];
            colorIdx++;
        }
    }
}

function renderCalendar(year, month) {
    const grid = document.getElementById('cal-grid');
    if (!grid) return;

    const firstDay = new Date(year, month - 1, 1);
    const lastDate = new Date(year, month, 0).getDate();
    const startOffset = (firstDay.getDay() + 6) % 7; // 周一为 0

    let html = '';
    // 表头
    const weekDays = ['一', '二', '三', '四', '五', '六', '日'];
    html += '<div class="cal-header">' + weekDays.map(d => `<div class="cal-header__cell">${d}</div>`).join('') + '</div>';

    // 格子（6 行 × 7 列）
    let dayCounter = 1;
    let nextMonthDay = 1;
    for (let row = 0; row < 6; row++) {
        for (let col = 0; col < 7; col++) {
            const cellIdx = row * 7 + col;
            if (cellIdx < startOffset) {
                // 上月日期（灰色）
                const prevDate = new Date(year, month - 1, 1);
                prevDate.setDate(prevDate.getDate() - (startOffset - cellIdx));
                html += renderCell(prevDate, true);
            } else if (dayCounter <= lastDate) {
                const cellDate = new Date(year, month - 1, dayCounter);
                html += renderCell(cellDate, false);
                dayCounter++;
            } else {
                // 下月日期（灰色）
                const nextDate = new Date(year, month, nextMonthDay);
                html += renderCell(nextDate, true);
                nextMonthDay++;
            }
        }
    }

    grid.innerHTML = html;
}

function renderCell(date, isOtherMonth) {
    const dateStr = formatDate(date);
    const day = date.getDate();
    const isToday = dateStr === formatDate(today);
    const items = itemsByDate[dateStr] || [];

    const classes = ['cal-cell'];
    if (isOtherMonth) classes.push('cal-cell--other');
    if (isToday) classes.push('cal-cell--today');

    let badges = '';
    if (items.length) {
        // 每部番剧最多显示 1 个徽章（同番剧多集合并），最多 3 个
        const seen = new Set();
        const unique = [];
        for (const item of items) {
            if (!seen.has(item.anime_id)) {
                seen.add(item.anime_id);
                unique.push(item);
            }
        }
        const showItems = unique.slice(0, 3);
        badges = showItems.map(item => {
            const color = colorMap[item.anime_id] || '#3b82f6';
            const epCount = items.filter(i => i.anime_id === item.anime_id).length;
            const epText = epCount > 1 ? `${epCount}集` : `第${item.absolute_num}集`;
            return `<span class="cal-badge" style="--badge-color:${color}" title="${escapeHtml(item.title_cn)} ${epText}">${escapeHtml(shortTitle(item.title_cn))}</span>`;
        }).join('');
        if (unique.length > 3) {
            badges += `<span class="cal-badge cal-badge--more">+${unique.length - 3}</span>`;
        }
    }

    const dayClass = isToday ? 'cal-cell__day cal-cell__day--today' : 'cal-cell__day';
    return `<div class="${classes.join(' ')}">
        <div class="${dayClass}">${day}</div>
        <div class="cal-cell__badges">${badges}</div>
    </div>`;
}

function shortTitle(title) {
    if (title.length <= 5) return title;
    return title.slice(0, 4) + '…';
}

function formatDate(d) {
    return d.getFullYear() + '-' +
           String(d.getMonth() + 1).padStart(2, '0') + '-' +
           String(d.getDate()).padStart(2, '0');
}

function prevMonth() {
    let m = viewMonth - 1, y = viewYear;
    if (m < 1) { m = 12; y--; }
    loadCalendar(y, m);
}
function nextMonth() {
    let m = viewMonth + 1, y = viewYear;
    if (m > 12) { m = 1; y++; }
    loadCalendar(y, m);
}
function goToday() {
    loadCalendar(today.getFullYear(), today.getMonth() + 1);
}

document.addEventListener('DOMContentLoaded', () => {
    loadCalendar(today.getFullYear(), today.getMonth() + 1);
});
