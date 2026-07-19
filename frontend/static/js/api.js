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

// ── Utility: time ago ────────────────────────────────────────────────────────
function timeAgo(isoString) {
  if (!isoString) return '—';
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60)   return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
}
