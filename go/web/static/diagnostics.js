/**
 * 追漫阁 Go 版 - 诊断页交互
 * 检测 Invidious 实例连通性与视频详情链路，渲染多状态卡、实例列表、视频探针。
 * 公共工具函数已抽取到 common.js。
 */

const statusMap = {
    healthy: { text: '健康', class: 'diag-card--healthy' },
    degraded: { text: '链路异常', class: 'diag-card--degraded' },
    down: { text: '不可用', class: 'diag-card--down' },
    unknown: { text: '未检测', class: '' },
};

async function checkInvidiousHealth() {
    const videoID = document.getElementById('diag-video-id')?.value?.trim() || 'dQw4w9WgXcQ';
    // 设置 loading 态
    setOverall('loading');
    const list = document.getElementById('diag-instance-list');
    const probeList = document.getElementById('diag-video-probe-list');
    if (list) list.innerHTML = '<div class="diag-empty">检测中...</div>';
    if (probeList) probeList.innerHTML = '<div class="diag-empty">检测中...</div>';

    try {
        const resp = await fetch('/api/diagnostics/invidious?video_id=' + encodeURIComponent(videoID), {
            method: 'POST',
            headers: apiHeaders(),
        });
        const d = await resp.json();
        const data = d.data || {};
        renderHealth(data);
    } catch (e) {
        setOverall('error');
        if (list) list.innerHTML = '<div class="diag-empty diag-empty--error">检测失败：网络错误</div>';
    }
}

function setOverall(state) {
    const card = document.getElementById('diag-overall');
    const text = document.getElementById('diag-overall-text');
    const hint = document.getElementById('diag-checked-at');
    if (card) card.className = 'diag-card diag-card--status';
    if (state === 'loading') {
        if (text) text.textContent = '检测中...';
        if (hint) hint.textContent = '正在探测各实例';
    } else if (state === 'error') {
        if (text) text.textContent = '检测失败';
        if (hint) hint.textContent = '请检查网络或服务状态';
    }
}

function renderHealth(data) {
    const status = data.overall_status || 'unknown';
    const info = statusMap[status] || statusMap.unknown;
    const card = document.getElementById('diag-overall');
    const text = document.getElementById('diag-overall-text');
    const hint = document.getElementById('diag-checked-at');
    const activeUrl = document.getElementById('diag-active-url');
    const timeout = document.getElementById('diag-timeout');
    const lbRatio = document.getElementById('diag-lb-ratio');
    const lbDetail = document.getElementById('diag-lb-detail');
    const lb = data.load_balance || {};

    if (card) card.className = 'diag-card diag-card--status ' + info.class;
    if (text) text.textContent = info.text;
    if (hint) hint.textContent = data.checked_at ? '最近检测：' + formatTime(data.checked_at) : '等待首次健康检测';
    if (activeUrl) activeUrl.textContent = data.active_url || '-';
    if (timeout) timeout.textContent = '超时配置：' + (data.timeout || '-') + ' 秒';
    if (lbRatio) lbRatio.textContent = lb.ratio_text || '-';
    if (lbDetail) lbDetail.textContent = (lb.description || '各实例按权重轮询') + ' · 可用 ' + (lb.available_count ?? 0) + '/' + (lb.total_count ?? 0);

    // 视频详情链路状态
    const videoStatus = document.getElementById('diag-video-status');
    const videoDetail = document.getElementById('diag-video-detail');
    const probe = data.video_probe || {};
    if (videoStatus) {
        videoStatus.textContent = probe.available ? '正常' : (probe.url ? '异常' : '未检测');
        videoStatus.className = 'diag-card__value ' + (probe.available ? 'diag-card__value--ok' : (probe.url ? 'diag-card__value--err' : ''));
    }
    if (videoDetail) videoDetail.textContent = probe.error ? '错误：' + probe.error : '视频 ' + (probe.video_id || '-') + ' 探测 ' + (probe.latency_ms || 0) + 'ms';

    renderInstances(data.instances || []);
    renderVideoProbes(data.video_probes || []);
}

function renderInstances(instances) {
    const list = document.getElementById('diag-instance-list');
    if (!list) return;
    if (!instances.length) {
        list.innerHTML = '<div class="diag-empty">暂无实例数据</div>';
        return;
    }
    const primaryURL = document.getElementById('diag-active-url')?.dataset?.primary || '';
    list.innerHTML = instances.map((inst, idx) => {
        const isPrimary = idx === 0;
        const latencyClass = inst.latency_ms < 500 ? 'diag-latency--ok' :
                             inst.latency_ms < 2000 ? 'diag-latency--warn' : 'diag-latency--err';
        return `
        <div class="diag-instance ${inst.available ? 'diag-instance--ok' : 'diag-instance--bad'}">
            <div class="diag-instance__main">
                <span class="diag-dot ${inst.available ? '' : 'diag-dot--err'}"></span>
                <span class="diag-instance__url">${escapeHtml(inst.url)}</span>
            </div>
            <div class="diag-instance__side">
                ${isPrimary ? '<span class="diag-role diag-role--primary">主实例</span>' : '<span class="diag-role">备用</span>'}
                <span class="diag-instance__meta ${inst.available ? latencyClass : 'diag-latency--err'}">
                    ${inst.available ? inst.latency_ms + 'ms · HTTP ' + inst.status_code : escapeHtml(inst.error)}
                </span>
            </div>
        </div>`;
    }).join('');
}

function renderVideoProbes(probes) {
    const list = document.getElementById('diag-video-probe-list');
    if (!list) return;
    if (!probes.length) {
        list.innerHTML = '<div class="diag-empty">暂无视频详情检测数据</div>';
        return;
    }
    list.innerHTML = probes.map((p, idx) => {
        const isPrimary = idx === 0;
        return `
        <div class="diag-instance ${p.available ? 'diag-instance--ok' : 'diag-instance--bad'}">
            <div class="diag-instance__main">
                <span class="diag-dot ${p.available ? '' : 'diag-dot--err'}"></span>
                <span class="diag-instance__url">${escapeHtml(p.url)}</span>
            </div>
            <div class="diag-instance__side">
                ${isPrimary ? '<span class="diag-role diag-role--primary">主实例</span>' : '<span class="diag-role">备用</span>'}
                <span class="diag-instance__meta ${p.available ? 'diag-latency--ok' : 'diag-latency--err'}">
                    ${p.available ? p.latency_ms + 'ms · HTTP ' + p.status_code : escapeHtml(p.error)}
                </span>
            </div>
        </div>`;
    }).join('');
}

function formatTime(iso) {
    try {
        const d = new Date(iso);
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' +
               String(d.getDate()).padStart(2, '0') + ' ' +
               String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    } catch (e) { return iso; }
}

// 页面加载时自动检测一次
document.addEventListener('DOMContentLoaded', () => {
    checkInvidiousHealth();
});
