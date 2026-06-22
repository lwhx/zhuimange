/**
 * 追漫阁 Go 版 - 详情页交互
 * 包含：同步SSE、标记已看/未看、进度更新、集数筛选、规则/别名管理
 * 公共工具函数（getCSRFToken/apiHeaders/apiRequest/toast/escapeHtml/setButtonLoading/withButtonLock）
 * 已抽取到 common.js，本文件不再重复定义。
 */

function toggleSection(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ==================== 同步 SSE ====================

const SyncState = { eventSource: null, taskId: null, mode: 'incremental' };

async function syncAnime(animeId, mode = 'incremental') {
    if (mode === 'full') {
        const ok = await showConfirm({
            icon: '🔄',
            iconType: 'warning',
            title: '全量刷新确认',
            desc: '全量刷新会重新搜索全部集数的视频源，并替换现有视频源。',
            details: [
                { icon: '⏱️', text: '耗时较长，集数越多越慢' },
                { icon: '🗑️', text: '现有视频源将被删除并重新搜索' },
                { icon: '📊', text: '匹配评分会重新计算' },
            ],
            confirmText: '开始全量刷新',
            cancelText: '取消',
            confirmType: 'danger',
        });
        if (!ok) return;
    }

    // 关闭旧连接
    if (SyncState.eventSource) { SyncState.eventSource.close(); SyncState.eventSource = null; }

    setButtonLoading(document.getElementById('sync-btn'), true, '同步中...');
    setButtonLoading(document.getElementById('full-sync-btn'), true, '同步中...');
    showSyncCard('准备中', 0, '正在创建同步任务...');

    try {
        const resp = await apiRequest(`/api/anime/${animeId}/sync`, {
            method: 'POST',
            body: JSON.stringify({ mode }),
        });
        const taskId = resp.data?.task?.id;
        if (!taskId) throw new Error('同步任务创建失败');
        SyncState.taskId = taskId;
        SyncState.mode = mode;
        showSyncCard(resp.data?.created ? '已加入队列' : '接入已有任务', 5,
            resp.data?.created ? '任务已加入队列...' : '正在接入已有任务...');
        openSyncStream(animeId, taskId);
    } catch (err) {
        hideSyncCard();
        setButtonLoading(document.getElementById('sync-btn'), false);
        setButtonLoading(document.getElementById('full-sync-btn'), false);
    }
}

function showSyncCard(stage, percent, text) {
    const card = document.getElementById('sync-progress');
    if (!card) return;
    card.style.display = 'block';
    document.getElementById('sync-stage').textContent = stage;
    document.getElementById('sync-percent').textContent = percent + '%';
    document.getElementById('sync-fill').style.width = percent + '%';
    document.getElementById('sync-text').textContent = text;
}

function hideSyncCard() {
    const card = document.getElementById('sync-progress');
    if (card) card.style.display = 'none';
}

function openSyncStream(animeId, taskId) {
    // 指数退避重连：网络抖动时自动恢复，最多重试 5 次。
    // 利用 Last-Event-ID 让后端续传未消费的事件（sync_api.go 已支持）。
    let retryCount = 0;
    let lastEventId = '';
    const maxRetries = 5;

    function connect() {
        const url = `/api/sync_tasks/${taskId}/stream` + (lastEventId ? `?last_event_id=${lastEventId}` : '');
        const es = new EventSource(url);
        SyncState.eventSource = es;

        es.onmessage = function (event) {
            retryCount = 0; // 收到消息说明连接正常，重置重试计数
            if (event.lastEventId) lastEventId = event.lastEventId;
            let data;
            try { data = JSON.parse(event.data); } catch (e) { return; }
            // done/error 事件由 finishSync/failSync 处理关闭
            if (data.type === 'done' || data.type === 'error') {
                handleSyncEvent(animeId, data);
                return;
            }
            handleSyncEvent(animeId, data);
        };
        es.onerror = function () {
            es.close();
            SyncState.eventSource = null;
            // 检查任务是否已完成（可能后端已结束但连接断了）
            fetch(`/api/sync_tasks/${taskId}`)
                .then(r => r.json())
                .then(d => {
                    const task = d.data;
                    if (task && (task.status === 'success' || task.status === 'error')) {
                        // 任务已完成，直接处理结果
                        if (task.status === 'success') {
                            finishSync(animeId, task.result || {});
                        } else {
                            failSync(task.message || '同步失败');
                        }
                        return;
                    }
                    // 任务未完成，尝试重连
                    retryCount++;
                    if (retryCount > maxRetries) {
                        showSyncCard('连接中断', 0, '多次重连失败，同步可能仍在后台继续');
                        setButtonLoading(document.getElementById('sync-btn'), false);
                        setButtonLoading(document.getElementById('full-sync-btn'), false);
                        return;
                    }
                    const delay = Math.min(1000 * Math.pow(2, retryCount - 1), 16000);
                    showSyncCard('重连中', 0, `连接中断，${delay / 1000}秒后重试 (${retryCount}/${maxRetries})`);
                    setTimeout(connect, delay);
                })
                .catch(() => {
                    // 查询也失败，按重连逻辑处理
                    retryCount++;
                    if (retryCount > maxRetries) {
                        showSyncCard('连接中断', 0, '同步可能仍在后台继续');
                        setButtonLoading(document.getElementById('sync-btn'), false);
                        setButtonLoading(document.getElementById('full-sync-btn'), false);
                        return;
                    }
                    setTimeout(connect, Math.min(1000 * Math.pow(2, retryCount - 1), 16000));
                });
        };
    }
    connect();
}

function handleSyncEvent(animeId, data) {
    const pct = (cur, total) => total > 0 ? Math.round(cur / total * 100) : 0;
    switch (data.type) {
        case 'queued': showSyncCard('排队中', 3, '排队中...'); break;
        case 'task_start': showSyncCard('任务启动', 8, '同步任务启动中...'); break;
        case 'discovering': showSyncCard('探测集数', 10, data.message || '探测集数...'); break;
        case 'discover':
            showSyncCard('集数已更新', 15, `探测到 ${data.total || 0} 集`);
            break;
        case 'start':
            showSyncCard(SyncState.mode === 'full' ? '全量刷新' : '增量同步', 20,
                `准备中，共 ${data.total || 0} 集`);
            break;
        case 'plan':
            showSyncCard('同步计划', data.target > 0 ? 24 : 100,
                `需同步 ${data.target || 0} 集，跳过 ${data.skipped || 0} 集`);
            break;
        case 'episode':
            showSyncCard('同步视频源', pct(data.current, data.total),
                `${data.current}/${data.total} · 源 +${data.source_count || 0}`);
            updateEpisodeSourceCount(data.ep_num, data.source_count || 0);
            break;
        case 'poster':
            // 可选：更新封面
            break;
        case 'done':
            finishSync(animeId, data);
            break;
        case 'error':
            failSync(data.message || '同步失败');
            break;
    }
}

function finishSync(animeId, data) {
    if (SyncState.eventSource) { SyncState.eventSource.close(); SyncState.eventSource = null; }
    showSyncCard('同步完成', 100,
        `同步 ${data.synced || 0} 集，找到 ${data.total_sources || 0} 个视频源`);
    setButtonLoading(document.getElementById('sync-btn'), false);
    setButtonLoading(document.getElementById('full-sync-btn'), false);
    toast(`同步完成: ${data.synced || 0} 集，${data.total_sources || 0} 个视频源`, 'success');
    // 延迟刷新页面以加载新数据
    setTimeout(() => location.reload(), 1500);
}

function failSync(msg) {
    if (SyncState.eventSource) { SyncState.eventSource.close(); SyncState.eventSource = null; }
    showSyncCard('同步失败', 0, msg);
    setButtonLoading(document.getElementById('sync-btn'), false);
    setButtonLoading(document.getElementById('full-sync-btn'), false);
    toast(msg, 'error');
}

function updateEpisodeSourceCount(epNum, count) {
    const item = document.querySelector(`.episode-item[data-ep="${epNum}"]`);
    if (!item) return;
    item.dataset.sources = String(count);
    const dateDiv = item.querySelector('.episode-item__date');
    if (!dateDiv) return;
    const dateText = dateDiv.textContent.replace(/\s*·?\s*\d+\s*个源/g, '').trim();
    dateDiv.textContent = dateText + (count > 0 ? ` · ${count} 个源` : '');
}

// ==================== 标记已看/未看 ====================

async function markWatched(animeId, epNum, btn) {
    return withButtonLock(btn, async () => {
        await apiRequest(`/api/anime/${animeId}/episode/${epNum}/watch`, { method: 'POST' });
        toast(`第${epNum}集已标记为看过`, 'success');
        updateEpisodeUI(epNum, true);
        updateProgressDisplay(animeId);
    }, '✓');
}

async function markUnwatched(animeId, epNum, btn) {
    return withButtonLock(btn, async () => {
        await apiRequest(`/api/anime/${animeId}/episode/${epNum}/unwatch`, { method: 'POST' });
        toast(`第${epNum}集已标记为未看`, 'success');
        updateEpisodeUI(epNum, false);
        updateProgressDisplay(animeId);
    }, '↩️');
}

function updateEpisodeUI(epNum, watched) {
    const item = document.querySelector(`.episode-item[data-ep="${epNum}"]`);
    if (!item) return;
    item.dataset.watched = watched ? '1' : '0';
    item.classList.toggle('episode-item--watched', watched);
    const numEl = item.querySelector('.episode-item__num');
    if (numEl) numEl.textContent = watched ? '✓' : String(epNum);
    // 只切换"标记已看/未看"按钮，保留"查看视频源"按钮（🎬）不被覆盖
    const animeId = currentAnimeId();
    const toggleBtn = item.querySelector('[data-role="toggle-watched"]');
    if (toggleBtn) {
        if (watched) {
            toggleBtn.className = 'btn btn--sm btn--secondary';
            toggleBtn.title = '标记未看';
            toggleBtn.textContent = '↩️';
            toggleBtn.setAttribute('onclick', `event.stopPropagation();markUnwatched(${animeId}, ${epNum}, this)`);
        } else {
            toggleBtn.className = 'btn btn--sm btn--success';
            toggleBtn.title = '标记已看';
            toggleBtn.textContent = '✓';
            toggleBtn.setAttribute('onclick', `event.stopPropagation();markWatched(${animeId}, ${epNum}, this)`);
        }
    }
    // 重新应用筛选
    applyEpisodeFilter();
}

function currentAnimeId() {
    const el = document.querySelector('[data-anime-id]');
    return el ? el.dataset.animeId : '';
}

function updateProgressDisplay(animeId) {
    const items = document.querySelectorAll('.episode-item');
    const total = items.length;
    const watched = document.querySelectorAll('.episode-item--watched').length;
    const fill = document.getElementById('progress-fill');
    const text = document.getElementById('progress-text');
    if (fill && total > 0) fill.style.width = (watched / total * 100) + '%';
    if (text) text.textContent = `${watched}/${total}`;
    // 更新"继续观看"按钮
    updateContinueWatchBtn();
}

function updateContinueWatchBtn() {
    const btn = document.getElementById('continue-watch-btn');
    if (!btn) return;
    const items = Array.from(document.querySelectorAll('.episode-item'));
    const next = items.find(i => i.dataset.watched !== '1');
    if (!next) {
        btn.disabled = true;
        btn.textContent = '✓ 已追完';
        btn.removeAttribute('onclick');
    } else {
        btn.disabled = false;
        const ep = next.dataset.ep;
        btn.textContent = `▶ 继续看第${ep}集`;
        btn.setAttribute('onclick', `continueWatching(${currentAnimeId()}, ${ep})`);
    }
}

// ==================== 继续观看 ====================

async function continueWatching(animeId, epNum) {
    if (!epNum) {
        const next = document.querySelector('.episode-item:not(.episode-item--watched)');
        if (!next) { toast('已追完所有集数'); return; }
        epNum = next.dataset.ep;
    }
    await openSources(animeId, epNum);
}

// ==================== 进度更新 ====================

async function updateProgress(animeId, btn) {
    const input = document.getElementById('progress-input');
    if (!input) return;
    const ep = parseInt(input.value, 10);
    if (isNaN(ep) || ep < 0) { toast('请输入有效集数', 'error'); return; }

    return withButtonLock(btn, async () => {
        await apiRequest(`/api/anime/${animeId}/progress`, {
            method: 'PUT',
            body: JSON.stringify({ watched_ep: ep }),
        });
        toast(`进度已更新至第${ep}集`, 'success');
        // 局部刷新各集状态
        document.querySelectorAll('.episode-item').forEach(item => {
            const itemEp = parseInt(item.dataset.ep || '0', 10);
            const shouldWatch = itemEp > 0 && itemEp <= ep;
            updateEpisodeUI(itemEp, shouldWatch);
        });
        updateProgressDisplay(animeId);
    }, '更新中...');
}

// ==================== 集数筛选 + 搜索 ====================

let episodeFilter = 'all';
let episodeSearchText = '';

function setEpisodeFilter(filter) {
    episodeFilter = filter;
    document.querySelectorAll('.ep-filter').forEach(b => {
        b.classList.toggle('active', b.dataset.filter === filter);
    });
    applyEpisodeFilter();
}

function filterEpisodes() {
    const input = document.getElementById('episode-search');
    episodeSearchText = input ? input.value.trim().toLowerCase() : '';
    applyEpisodeFilter();
}

function applyEpisodeFilter() {
    const items = document.querySelectorAll('.episode-item');
    let visibleCount = 0;
    items.forEach(item => {
        const watched = item.dataset.watched === '1';
        const sources = parseInt(item.dataset.sources || '0', 10);
        const title = (item.dataset.title || '').toLowerCase();
        const epNum = item.dataset.ep || '';
        let show = true;
        switch (episodeFilter) {
            case 'unwatched': show = !watched; break;
            case 'watched': show = watched; break;
            case 'with_sources': show = sources > 0; break;
            case 'without_sources': show = sources === 0; break;
        }
        if (show && episodeSearchText) {
            show = title.includes(episodeSearchText) || epNum.includes(episodeSearchText);
        }
        item.style.display = show ? '' : 'none';
        if (show) visibleCount++;
    });
    const empty = document.getElementById('episode-filter-empty');
    if (empty) empty.style.display = visibleCount === 0 && items.length > 0 ? 'block' : 'none';
}

// ==================== 搜索规则 ====================

async function saveRules(animeId, btn) {
    const rules = {
        allow_keywords: splitInput('rule-allow-keywords'),
        deny_keywords: splitInput('rule-deny-keywords'),
        allow_channels: splitInput('rule-allow-channels'),
        deny_channels: splitInput('rule-deny-channels'),
    };
    return withButtonLock(btn, async () => {
        await apiRequest(`/api/anime/${animeId}/rules`, {
            method: 'PUT',
            body: JSON.stringify(rules),
        });
        toast('搜索规则已保存', 'success');
    }, '保存中...');
}

function splitInput(id) {
    const el = document.getElementById(id);
    if (!el) return [];
    return el.value.split(',').map(s => s.trim()).filter(Boolean);
}

// ==================== 别名管理 ====================

async function addAlias(animeId, btn) {
    const input = document.getElementById('alias-input');
    if (!input) return;
    const alias = input.value.trim();
    if (!alias) { toast('请输入别名', 'error'); return; }

    return withButtonLock(btn, async () => {
        await apiRequest(`/api/anime/${animeId}/aliases`, {
            method: 'POST',
            body: JSON.stringify({ alias }),
        });
        toast('别名已添加', 'success');
        input.value = '';
        // 局部追加标签
        const list = document.getElementById('alias-list');
        if (list) {
            const tag = document.createElement('span');
            tag.style.cssText = 'padding:3px 10px;background:var(--bg-input);border-radius:var(--radius-xl);font-size:0.78rem;color:var(--text-muted);';
            tag.textContent = alias;
            list.appendChild(tag);
        }
    }, '添加中...');
}

// ==================== 删除动漫 ====================

async function deleteAnime(animeId) {
    const ok = await showConfirm({
        icon: '🗑️',
        iconType: 'danger',
        title: '删除动漫确认',
        desc: '删除后无法恢复，以下数据将永久丢失：',
        details: [
            { icon: '📺', text: '该动漫的所有集数记录' },
            { icon: '🎬', text: '所有视频源数据' },
            { icon: '🔖', text: '观看进度和别名' },
        ],
        confirmText: '确认删除',
        cancelText: '取消',
        confirmType: 'danger',
    });
    if (!ok) return;
    try {
        await apiRequest(`/api/anime/${animeId}`, { method: 'DELETE' });
        toast('删除成功', 'success');
        setTimeout(() => location.href = '/', 800);
    } catch (e) {}
}

// ==================== 视频源模态 ====================
// escapeHtml 已在 common.js 定义


async function openSources(animeId, epNum) {
    const overlay = document.getElementById('sources-modal-overlay');
    const body = document.getElementById('sources-modal-body');
    const title = document.getElementById('modal-title');
    if (!overlay || !body) return;

    if (title) title.textContent = `第 ${epNum} 集视频源`;
    body.innerHTML = `
        <div class="modal-state modal-state--loading">
            <div class="modal-state__spinner"></div>
            <div class="modal-state__title">正在加载第${epNum}集视频源</div>
            <div class="modal-state__desc">稍等一下，片源小队正在翻目录。</div>
        </div>`;
    overlay.style.display = 'flex';

    try {
        const resp = await fetch(`/anime/${animeId}/episode/${epNum}/sources`);
        if (!resp.ok) {
            const reason = (await resp.text()).trim();
            // 后端错误页可能含 HTML 标签，剥离后展示纯文本
            const hint = reason.replace(/<[^>]+>/g, '').trim() ||
                (resp.status === 404 ? '该集数暂不可用' : `加载失败 (${resp.status})`);
            const isNotAired = hint.includes('尚未开播') || hint.includes('不存在') || hint.includes('暂不可用');
            body.innerHTML = `
                <div class="modal-state modal-state--error">
                    <div class="modal-state__icon">${isNotAired ? '⏳' : '⚠️'}</div>
                    <div class="modal-state__title">${escapeHtml(hint)}</div>
                    <div class="modal-state__desc">${isNotAired ? '该集数尚未到播出时间，请稍后再来查看。' : '网络或服务开了小差，请稍后重试。'}</div>
                </div>`;
            return;
        }
        body.innerHTML = await resp.text();
    } catch (e) {
        body.innerHTML = `
            <div class="modal-state modal-state--error">
                <div class="modal-state__icon">⚠️</div>
                <div class="modal-state__title">视频源加载失败</div>
                <div class="modal-state__desc">网络连接异常，请检查网络后重试。</div>
            </div>`;
    }
}

// 主动搜索单集视频源（force=true 强制重新搜索）
async function findSources(animeId, epNum, force = false, btn) {
    return withButtonLock(btn, async () => {
        const resp = await apiRequest(`/api/anime/${animeId}/episode/${epNum}/find_sources`, {
            method: 'POST',
            body: JSON.stringify({ force }),
        });
        const count = resp.data?.count || resp.count || 0;
        updateEpisodeSourceCount(epNum, count);
        toast(`搜索完成，找到 ${count} 个视频源`, 'success');
        // 重新加载模态内容展示新源
        await openSources(animeId, epNum);
    }, '搜索中...');
}

// 检测单集视频源健康状态
async function checkSourcesHealth(animeId, epNum, btn) {
    return withButtonLock(btn, async () => {
        const resp = await apiRequest(`/api/anime/${animeId}/episode/${epNum}/check_sources`, {
            method: 'POST',
            body: JSON.stringify({}),
        });
        toast(resp.message || '检测完成', 'success');
        // 重新加载模态内容展示最新健康状态
        await openSources(animeId, epNum);
    }, '检测中...');
}

function closeModal() {
    const overlay = document.getElementById('sources-modal-overlay');
    if (overlay) overlay.style.display = 'none';
}

// ==================== 模态按钮事件委托 ====================
// 视频源模态通过 data-action/data-anime-id/data-ep-num 属性声明意图，
// 避免在 HTML 内联 JS 调用（Go 模板会转义引号导致内联 JS 失效）。

function handleModalAction(btn) {
    const action = btn.dataset.action;
    // data-anime-id / data-ep-num 可能在按钮自身或其祖先容器（如工具栏）上，
    // 用 closest 向上查找以兼容两种声明方式。
    const ctx = btn.closest('[data-anime-id]') || btn;
    const animeId = parseInt(ctx.dataset.animeId || '0', 10);
    const epNum = parseInt(ctx.dataset.epNum || '0', 10);
    const force = btn.dataset.force === '1';
    if (!animeId || !epNum) {
        toast('无法确定动漫或集数', 'error');
        return;
    }
    if (action === 'find-sources') {
        findSources(animeId, epNum, force, btn);
    } else if (action === 'check-health') {
        checkSourcesHealth(animeId, epNum, btn);
    }
}

document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (btn && (btn.dataset.action === 'find-sources' || btn.dataset.action === 'check-health')) {
        e.preventDefault();
        handleModalAction(btn);
    }
});

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    updateContinueWatchBtn();
    applyEpisodeFilter();
});
