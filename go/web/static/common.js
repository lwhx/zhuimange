/**
 * 追漫阁 Go 版 - 公共工具函数
 * 所有页面共享，避免 detail.js/settings.js/stats.js 等重复定义。
 * 必须在其他页面 JS 之前加载。
 */

// ==================== CSRF Token ====================

function getCSRFToken() {
    const m = document.cookie.match(/zmg_csrf=([^;]+)/);
    return m ? m[1] : '';
}

function apiHeaders(json = true) {
    const h = { 'X-CSRF-Token': getCSRFToken() };
    if (json) h['Content-Type'] = 'application/json';
    return h;
}

// ==================== 统一 API 请求 ====================
// 自动注入 CSRF token，处理 401 重定向，统一错误提示。
// 支持 body 为 object（自动 JSON.stringify + Content-Type）。

async function apiRequest(url, options = {}) {
    const opts = { ...options, headers: { ...(options.headers || {}) } };
    // 写操作带 CSRF token（兼容 POST/PUT/PATCH/DELETE）
    if (opts.method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(opts.method.toUpperCase())) {
        opts.headers['X-CSRF-Token'] = getCSRFToken();
    }
    // body 为 object 时自动 JSON 序列化
    if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(opts.body);
    }
    try {
        const resp = await fetch(url, opts);
        // 登录态失效：重定向到登录页
        if (resp.status === 401) {
            toast('登录已过期，请重新登录', 'warning');
            setTimeout(() => { window.location.href = '/login'; }, 1000);
            throw new Error('未授权');
        }
        const contentType = resp.headers.get('content-type') || '';
        if (!resp.ok) {
            let errMsg = `请求失败 (${resp.status})`;
            if (contentType.includes('application/json')) {
                const err = await resp.json();
                errMsg = err.error || err.message || errMsg;
            }
            toast(errMsg, 'error');
            throw new Error(errMsg);
        }
        // 返回 JSON 或文本
        if (contentType.includes('application/json')) {
            return resp.json();
        }
        return resp.text();
    } catch (err) {
        if (err.message !== '未授权') {
            toast(err.message || '请求失败', 'error');
        }
        throw err;
    }
}

// ==================== Toast 通知 ====================
// 优先使用 app.js 的 ToastManager（详情页等主站页面），否则用简易版（独立页）。

function toast(msg, type = 'info') {
    if (typeof ToastManager !== 'undefined' && ToastManager.show) {
        const fn = ToastManager[type] || ToastManager.info;
        fn.call(ToastManager, msg);
        return;
    }
    // 独立页（统计/诊断/看板/日历）无 ToastManager，用简易 toast
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const t = document.createElement('div');
    t.className = 'toast toast--' + type;
    t.textContent = msg;
    container.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 3000);
}

// ==================== 工具函数 ====================

function escapeHtml(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function escapeAttr(s) {
    return String(s ?? '').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/'/g, '&#39;');
}

function proxyImg(url) {
    if (!url) return '';
    if (url.startsWith('https://')) return '/api/proxy_image?url=' + encodeURIComponent(url);
    return url;
}

// 按钮防连点 loading
function setButtonLoading(btn, loading, text = '处理中...') {
    if (!btn) return;
    if (loading) {
        if (!btn.dataset.originalText) btn.dataset.originalText = btn.textContent.trim();
        btn.disabled = true;
        btn.textContent = text;
    } else {
        btn.disabled = false;
        if (btn.dataset.originalText) {
            btn.textContent = btn.dataset.originalText;
            delete btn.dataset.originalText;
        }
    }
}

async function withButtonLock(btn, fn, loadingText = '处理中...') {
    setButtonLoading(btn, true, loadingText);
    try {
        return await fn();
    } finally {
        setButtonLoading(btn, false);
    }
}
