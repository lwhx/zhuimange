/**
 * 追漫阁 Go 版 - 设置页交互
 * 包含：设置加载/保存、Invidious 实例编辑器、备份导入导出、改密码
 * 公共工具函数已抽取到 common.js，本文件不再重复定义。
 */

// ==================== 设置加载/保存 ====================

let invidiousState = {
    fallbacks: [],    // [{url, weight}]
    primaryWeight: 5,
};

async function loadSettings() {
    try {
        const resp = await fetch('/api/settings', { headers: apiHeaders() });
        if (resp.status === 401) {
            toast('登录已过期，请重新登录', 'warning');
            setTimeout(() => { window.location.href = '/login'; }, 1000);
            return;
        }
        const data = await resp.json();
        const s = data.data || {};
        // 普通字段
        document.querySelectorAll('[data-key]').forEach(el => {
            if (el.tagName === 'INPUT' && el.type === 'hidden' &&
                (el.dataset.key === 'invidious_fallback_urls' || el.dataset.key === 'invidious_instance_weights')) {
                return; // Invidious 隐藏字段由编辑器单独管理
            }
            const v = s[el.dataset.key] ?? '';
            if (el.type === 'checkbox') {
                el.checked = (v === 'true' || v === true);
            } else {
                el.value = v;
            }
        });
        // Invidious 实例编辑器
        loadInvidiousEditor(s);
    } catch (e) {
        toast('加载设置失败', 'error');
    }
}

async function saveSettings(btn) {
    const original = btn ? btn.textContent : null;
    setButtonLoading(btn, true, '保存中...');
    // 先同步隐藏字段
    syncInvidiousWeights();
    const payload = {};
    document.querySelectorAll('[data-key]').forEach(el => {
        payload[el.dataset.key] = el.type === 'checkbox' ? (el.checked ? 'true' : 'false') : el.value;
    });
    try {
        const resp = await fetch('/api/settings', {
            method: 'PUT',
            headers: apiHeaders(),
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (data.success === false) {
            toast(data.error || '保存失败', 'error');
        } else {
            toast('设置已保存', 'success');
        }
    } catch (e) {
        toast('保存失败', 'error');
    } finally {
        setButtonLoading(btn, false);
    }
}

// ==================== Invidious 实例编辑器 ====================

function loadInvidiousEditor(s) {
    let fallbacks = [];
    let weights = {};
    try { fallbacks = JSON.parse(s.invidious_fallback_urls || '[]'); } catch (e) {}
    try { weights = JSON.parse(s.invidious_instance_weights || '{}'); } catch (e) {}

    const primaryUrl = s.invidious_url || '';
    invidiousState.primaryWeight = parseInt(weights[primaryUrl] || 5, 10) || 5;
    invidiousState.fallbacks = fallbacks.map(u => ({
        url: u,
        weight: parseInt(weights[u] || 3, 10) || 3,
    }));

    const pwInput = document.getElementById('invidious-primary-weight');
    if (pwInput) pwInput.value = invidiousState.primaryWeight;

    renderInvidiousFallbackEditor();
    syncInvidiousWeights();
}

function renderInvidiousFallbackEditor() {
    const editor = document.getElementById('invidious-fallback-editor');
    if (!editor) return;
    editor.innerHTML = '';
    if (invidiousState.fallbacks.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'invidious-instance-empty';
        empty.textContent = '暂无备用实例，点击下方按钮添加';
        editor.appendChild(empty);
        return;
    }
    invidiousState.fallbacks.forEach((item, idx) => {
        const row = document.createElement('div');
        row.className = 'invidious-instance-row';
        row.innerHTML = `
            <span class="invidious-instance-row__badge">备用</span>
            <input type="text" class="invidious-instance-row__input" value="${escapeAttr(item.url)}"
                   placeholder="https://invidious-fallback.example.com" data-fallback-idx="${idx}" data-field="url">
            <span class="invidious-weight-inline">
                权重 <input type="number" min="1" max="100" style="width:60px;"
                    value="${item.weight}" data-fallback-idx="${idx}" data-field="weight">
            </span>
            <button type="button" class="invidious-instance-row__remove" data-remove-idx="${idx}">✕</button>
        `;
        editor.appendChild(row);
    });
    // 绑定输入事件
    editor.querySelectorAll('[data-fallback-idx]').forEach(input => {
        input.addEventListener('input', () => {
            const idx = parseInt(input.dataset.fallbackIdx, 10);
            const field = input.dataset.field;
            if (field === 'weight') {
                invidiousState.fallbacks[idx].weight = parseInt(input.value, 10) || 0;
            } else {
                invidiousState.fallbacks[idx].url = input.value;
            }
            syncInvidiousWeights();
        });
    });
    editor.querySelectorAll('[data-remove-idx]').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.removeIdx, 10);
            invidiousState.fallbacks.splice(idx, 1);
            renderInvidiousFallbackEditor();
            syncInvidiousWeights();
        });
    });
}

function addInvidiousFallbackRow() {
    invidiousState.fallbacks.push({ url: '', weight: 3 });
    renderInvidiousFallbackEditor();
    syncInvidiousWeights();
    // 聚焦新行
    const inputs = document.querySelectorAll('[data-fallback-idx][data-field="url"]');
    if (inputs.length) inputs[inputs.length - 1].focus();
}

function syncInvidiousWeights() {
    const primaryUrl = document.getElementById('invidious-primary-url')?.value || '';
    const pwInput = document.getElementById('invidious-primary-weight');
    if (pwInput) invidiousState.primaryWeight = parseInt(pwInput.value, 10) || 1;

    const fallbackUrls = invidiousState.fallbacks.map(f => f.url).filter(Boolean);
    const weights = {};
    if (primaryUrl) weights[primaryUrl] = invidiousState.primaryWeight;
    invidiousState.fallbacks.forEach(f => {
        if (f.url) weights[f.url] = f.weight;
    });

    const fu = document.getElementById('invidious-fallback-urls');
    const iw = document.getElementById('invidious-instance-weights');
    if (fu) fu.value = JSON.stringify(fallbackUrls);
    if (iw) iw.value = JSON.stringify(weights);
}

// ==================== 备份与恢复 ====================

async function importBackup(input) {
    const file = input.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
        const resp = await fetch('/api/backup/import', {
            method: 'POST',
            headers: { 'X-CSRF-Token': getCSRFToken() },
            body: form,
        });
        const data = await resp.json();
        toast(data.message || data.error || '导入完成', data.success ? 'success' : 'error');
    } catch (e) {
        toast('导入失败', 'error');
    }
    input.value = '';
}

async function telegramBackup(btn) {
    setButtonLoading(btn, true, '发送中...');
    try {
        const resp = await fetch('/api/backup/telegram', { method: 'POST', headers: apiHeaders() });
        const d = await resp.json();
        toast(d.message || d.error || '完成', d.success ? 'success' : 'error');
    } catch (e) {
        toast('发送失败', 'error');
    } finally {
        setButtonLoading(btn, false);
    }
}

async function localBackup(btn) {
    setButtonLoading(btn, true, '备份中...');
    try {
        const resp = await fetch('/api/backup/local', { method: 'POST', headers: apiHeaders() });
        const d = await resp.json();
        toast(d.message || d.error || '完成', d.success ? 'success' : 'error');
    } catch (e) {
        toast('备份失败', 'error');
    } finally {
        setButtonLoading(btn, false);
    }
}

// ==================== 修改密码 ====================

async function changePassword(btn) {
    const oldPwd = document.getElementById('old-password').value;
    const newPwd = document.getElementById('new-password').value;
    if (!oldPwd || !newPwd) { toast('请填写完整', 'error'); return; }
    if (newPwd.length < 8) { toast('新密码至少 8 位', 'error'); return; }

    setButtonLoading(btn, true, '修改中...');
    try {
        const resp = await fetch('/api/change_password', {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }),
        });
        const data = await resp.json();
        if (data.success) {
            toast('密码修改成功，即将重新登录...', 'success');
            document.getElementById('old-password').value = '';
            document.getElementById('new-password').value = '';
            // 改密码后旧 session 会失效（session_version 递增），提示用户重新登录
            setTimeout(() => { window.location.href = '/login'; }, 1500);
        } else {
            toast(data.error || '修改失败', 'error');
        }
    } catch (e) {
        toast('修改失败', 'error');
    } finally {
        setButtonLoading(btn, false);
    }
}

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', loadSettings);
