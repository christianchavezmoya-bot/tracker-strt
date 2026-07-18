/**
 * HOLO-RTLS — API Client
 * Centralised fetch wrapper with JWT token handling.
 */

const API = {
  base: '/api',

  _token: localStorage.getItem('holo_access_token'),
  _refresh: localStorage.getItem('holo_refresh_token'),
  _user: JSON.parse(localStorage.getItem('holo_user') || 'null'),

  // ── Token management ───────────────────────────────────────────────────────
  setTokens(access, refresh, user) {
    this._token = access;
    this._refresh = refresh;
    this._user = user;
    if (access) localStorage.setItem('holo_access_token', access);
    else        localStorage.removeItem('holo_access_token');
    if (refresh) localStorage.setItem('holo_refresh_token', refresh);
    else         localStorage.removeItem('holo_refresh_token');
    if (user)    localStorage.setItem('holo_user', JSON.stringify(user));
    else         localStorage.removeItem('holo_user');
  },

  clearTokens() {
    this.setTokens(null, null, null);
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

  // ── Parse JSON safely ──────────────────────────────────────────────────────
  async json(res) {
    if (!res) return null;
    const text = await res.text();
    try { return JSON.parse(text); } catch { return { error: text }; }
  },
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
