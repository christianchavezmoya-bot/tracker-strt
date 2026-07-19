/**
 * HOLO-RTLS — API Client
 * Centralised fetch wrapper with JWT token handling.
 */

const API = {
  base: '/api',

  _remember: localStorage.getItem('holo_remember') !== '0',
  _token: null,
  _refresh: null,
  _user: null,

  _store() {
    return this._remember ? localStorage : sessionStorage;
  },

  _otherStore() {
    return this._remember ? sessionStorage : localStorage;
  },

  _readStored(key, asJson) {
    const primary = this._store().getItem(key);
    if (primary != null) return asJson ? JSON.parse(primary) : primary;
    const fallback = this._otherStore().getItem(key);
    if (fallback == null) return asJson ? null : null;
    return asJson ? JSON.parse(fallback) : fallback;
  },

  setRemember(remember) {
    this._remember = remember !== false;
    localStorage.setItem('holo_remember', this._remember ? '1' : '0');
  },

  // ── Token management ───────────────────────────────────────────────────────
  setTokens(access, refresh, user) {
    this._token = access;
    this._refresh = refresh;
    this._user = user;
    const store = this._store();
    const other = this._otherStore();
    const pairs = [
      ['holo_access_token', access],
      ['holo_refresh_token', refresh],
      ['holo_user', user ? JSON.stringify(user) : null],
    ];
    pairs.forEach(([key, val]) => {
      if (val) store.setItem(key, val);
      else store.removeItem(key);
      other.removeItem(key);
    });
  },

  clearTokens() {
    this.setTokens(null, null, null);
    ['holo_access_token', 'holo_refresh_token', 'holo_user'].forEach(k => {
      localStorage.removeItem(k);
      sessionStorage.removeItem(k);
    });
  },

  getUser() { return this._user; },
  isLoggedIn() { return !!this._token; },

  // ── HTTP ───────────────────────────────────────────────────────────────────
  async _fetch(path, options = {}) {
    const url = `${this.base}${path}`;
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };
    if (this._token) {
      headers['Authorization'] = `Bearer ${this._token}`;
    }
    const res = await fetch(url, { ...options, headers });

    // Handle 401 — attempt token refresh once
    if (res.status === 401 && this._refresh) {
      const refreshed = await this._attemptRefresh();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${this._token}`;
        const retry = await fetch(url, { ...options, headers });
        if (retry.status >= 200 && retry.status < 300) return retry;
        return retry;
      }
      this.clearTokens();
      window.location.href = '/login';
      return null;
    }
    return res;
  },

  async _attemptRefresh() {
    try {
      const res = await fetch(`${this.base}/auth/refresh`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${this._refresh}` },
      });
      if (res.ok) {
        const data = await res.json();
        this._token = data.access_token;
        localStorage.setItem('holo_access_token', data.access_token);
        return true;
      }
    } catch (e) { /* silent */ }
    return false;
  },

  // ── Convenience methods ─────────────────────────────────────────────────────
  get(path)         { return this._fetch(path); },
  post(path, body)  { return this._fetch(path, { method: 'POST', body: JSON.stringify(body) }); },
  patch(path, body) { return this._fetch(path, { method: 'PATCH', body: JSON.stringify(body) }); },
  put(path, body)   { return this._fetch(path, { method: 'PUT', body: JSON.stringify(body) }); },
  del(path, body)   { return this._fetch(path, { method: 'DELETE', body: body ? JSON.stringify(body) : undefined }); },

  // ── FormData (file uploads — skips JSON Content-Type) ──────────────────────
  async postForm(path, formData) {
    const url = `${this.base}${path}`;
    const headers = {};
    if (this._token) headers['Authorization'] = `Bearer ${this._token}`;
    const res = await fetch(url, { method: 'POST', headers, body: formData });
    if (res.status === 401 && this._refresh) {
      const refreshed = await this._attemptRefresh();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${this._token}`;
        return fetch(url, { method: 'POST', headers, body: formData });
      }
      this.clearTokens();
      window.location.href = '/login';
      return null;
    }
    return res;
  },

  // ── Parse JSON safely ──────────────────────────────────────────────────────
  async json(res) {
    if (!res) return null;
    const text = await res.text();
    try { return JSON.parse(text); } catch { return { error: text }; }
  },
};

// Hydrate tokens from preferred storage (remember-me)
API._token = API._readStored('holo_access_token');
API._refresh = API._readStored('holo_refresh_token');
API._user = API._readStored('holo_user', true);

// ── Global toast (shell + admin pages) ───────────────────────────────────────
window.showToast = function (message, type = 'info') {
  const colors = {
    success: { border: '#34d399', text: '#34d399' },
    error: { border: '#f87171', text: '#f87171' },
    warning: { border: '#fbbf24', text: '#fbbf24' },
    info: { border: '#0ea5a4', text: '#2dd4bf' },
  };
  const c = colors[type] || colors.info;
  let host = document.getElementById('holoToastHost');
  if (!host) {
    host = document.createElement('div');
    host.id = 'holoToastHost';
    host.setAttribute('aria-live', 'polite');
    host.setAttribute('aria-atomic', 'true');
    host.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:99999;display:flex;flex-direction:column;gap:8px;pointer-events:none';
    document.body.appendChild(host);
  }
  const t = document.createElement('div');
  t.setAttribute('role', 'status');
  t.style.cssText = `padding:10px 18px;background:rgba(8,15,30,0.96);border:1px solid ${c.border};color:${c.text};border-radius:10px;font-size:13px;font-family:IBM Plex Sans,system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.45);animation:holoToastIn .2s ease`;
  t.textContent = message;
  host.appendChild(t);
  setTimeout(() => {
    t.style.opacity = '0';
    t.style.transition = 'opacity .25s';
    setTimeout(() => t.remove(), 280);
  }, 3200);
};

if (!document.getElementById('holoToastStyles')) {
  const s = document.createElement('style');
  s.id = 'holoToastStyles';
  s.textContent = '@keyframes holoToastIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}';
  document.head.appendChild(s);
}

// ── Accessible confirm modal (replaces window.confirm) ───────────────────────
window.holoConfirm = function holoConfirm(message, options = {}) {
  const title = options.title || 'Confirm action';
  const confirmLabel = options.confirmLabel || 'Confirm';
  const cancelLabel = options.cancelLabel || 'Cancel';
  const danger = !!options.danger;

  const esc = (s) => String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  return new Promise((resolve) => {
    document.getElementById('holoConfirmBackdrop')?.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'holoConfirmBackdrop';
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(2,6,20,.65);z-index:100000;display:flex;align-items:center;justify-content:center;padding:16px;backdrop-filter:blur(3px)';

    const dlg = document.createElement('div');
    dlg.setAttribute('role', 'alertdialog');
    dlg.setAttribute('aria-modal', 'true');
    dlg.setAttribute('aria-labelledby', 'holoConfirmTitle');
    dlg.setAttribute('aria-describedby', 'holoConfirmMsg');
    dlg.style.cssText = 'width:min(420px,92vw);background:#111827;border:1px solid rgba(148,163,184,.25);border-radius:12px;padding:20px 22px;font-family:IBM Plex Sans,system-ui,sans-serif;box-shadow:0 20px 50px rgba(0,0,0,.5)';

    const okColor = danger ? '#f87171' : '#0ea5a4';
    dlg.innerHTML = `
      <h2 id="holoConfirmTitle" style="margin:0 0 10px;font-size:1.05rem;font-family:Space Grotesk,IBM Plex Sans,sans-serif;color:#e2e8f0">${esc(title)}</h2>
      <p id="holoConfirmMsg" style="margin:0 0 18px;font-size:14px;line-height:1.5;color:#94a3b8">${esc(message).replace(/\n/g, '<br>')}</p>
      <div style="display:flex;gap:10px;justify-content:flex-end">
        <button type="button" id="holoConfirmCancel" style="padding:9px 14px;border-radius:8px;border:1px solid rgba(148,163,184,.3);background:transparent;color:#94a3b8;cursor:pointer;font-size:13px">${esc(cancelLabel)}</button>
        <button type="button" id="holoConfirmOk" style="padding:9px 14px;border-radius:8px;border:0;background:${okColor};color:#041416;font-weight:700;cursor:pointer;font-size:13px">${esc(confirmLabel)}</button>
      </div>`;

    backdrop.appendChild(dlg);
    document.body.appendChild(backdrop);

    const finish = (val) => {
      document.removeEventListener('keydown', onKey);
      backdrop.remove();
      resolve(val);
    };

    const onKey = (e) => {
      if (e.key === 'Escape') finish(false);
      if (e.key === 'Tab') {
        const focusables = dlg.querySelectorAll('button');
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    dlg.querySelector('#holoConfirmCancel').onclick = () => finish(false);
    dlg.querySelector('#holoConfirmOk').onclick = () => finish(true);
    backdrop.onclick = (e) => { if (e.target === backdrop) finish(false); };
    document.addEventListener('keydown', onKey);
    dlg.querySelector('#holoConfirmOk').focus();
  });
};

// ── Utility: time ago ────────────────────────────────────────────────────────
function timeAgo(isoString) {
  if (!isoString) return '—';
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60)   return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
}
