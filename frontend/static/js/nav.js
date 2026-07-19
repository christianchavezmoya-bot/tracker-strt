/**
 * HOLO-RTLS — Global navigation drawer.
 * Injected on every page (no shared base template exists). Adds a menu toggle
 * (into the .topbar when present, floating otherwise) that opens a slide-out
 * drawer linking every page. Admin-only items are gated by the stored user role.
 */
(function () {
  if (window.__holoNavInjected) return;
  window.__holoNavInjected = true;

  var PAGES = [
    { href: '/',         label: 'Command Center',  icon: '🗺️' },
    { href: '/tracking', label: 'Live Tracking',   icon: '📡' },
    { href: '/trackers', label: 'Trackers',        icon: '🏷️' },
    { href: '/nodes',    label: 'Nodes / Anchors', icon: '📍' },
    { href: '/zones',    label: 'Zones & Sections',icon: '⬢' },
    { href: '/alerts',   label: 'Alerts',          icon: '🔔' },
    { href: '/reports',  label: 'Reports',         icon: '📊' },
    { href: '/search',   label: 'Search',          icon: '🔍' },
    { sep: 'Administration' },
    { href: '/hardware', label: 'Hardware Setup',  icon: '🖥️', admin: true },
    { href: '/settings', label: 'Settings',        icon: '⚙️', admin: true },
    { href: '/users',    label: 'Users',           icon: '👥', admin: true },
    { href: '/audit',    label: 'Audit Log',       icon: '📋', admin: true },
    { href: '/backup',   label: 'Backup & Restore',icon: '💾', admin: true },
    { href: '/apidocs',  label: 'API Docs',        icon: '📖', admin: true }
  ];

  // Role from the stored user; fail open (show everything) if unknown.
  var role = null;
  try { role = (JSON.parse(localStorage.getItem('holo_user') || 'null') || {}).role || null; } catch (e) {}
  var isAdmin = (role == null) || (String(role).toUpperCase() === 'ADMIN');

  var here = (location.pathname.replace(/\/+$/, '') || '/');

  // ── Styles ──────────────────────────────────────────────────────────────
  var css = ''
    + '.holonav-toggle{background:transparent;border:1px solid rgba(0,229,255,.35);color:#00e5ff;'
    + 'width:38px;height:38px;border-radius:8px;font-size:18px;line-height:1;cursor:pointer;'
    + 'display:inline-flex;align-items:center;justify-content:center;transition:all .15s;flex:0 0 auto;}'
    + '.holonav-toggle:hover{background:rgba(0,229,255,.12);}'
    + '.holonav-toggle.in-header{margin:0 12px 0 4px;}'
    + '.holonav-toggle.floating{position:fixed;top:12px;left:12px;z-index:100001;'
    + 'background:rgba(8,31,62,.92);box-shadow:0 2px 10px rgba(0,0,0,.5);}'
    + '.holonav-backdrop{position:fixed;inset:0;background:rgba(2,6,20,.55);z-index:100000;'
    + 'opacity:0;pointer-events:none;transition:opacity .2s;}'
    + '.holonav-backdrop.open{opacity:1;pointer-events:auto;}'
    + '.holonav-drawer{position:fixed;top:0;left:0;bottom:0;width:264px;z-index:100002;'
    + 'background:linear-gradient(180deg,#081f3e 0%,#050f24 100%);border-right:1px solid rgba(0,229,255,.25);'
    + 'box-shadow:4px 0 24px rgba(0,0,0,.55);transform:translateX(-100%);transition:transform .22s ease;'
    + 'font-family:system-ui,Segoe UI,Roboto,sans-serif;overflow-y:auto;padding-bottom:16px;}'
    + '.holonav-drawer.open{transform:translateX(0);}'
    + '.holonav-head{display:flex;align-items:center;gap:10px;padding:16px 18px;font-weight:700;'
    + 'font-size:15px;color:#e6f2ff;border-bottom:1px solid rgba(0,229,255,.18);letter-spacing:.5px;}'
    + '.holonav-logo{color:#00e5ff;font-size:18px;}'
    + '.holonav-sep{padding:14px 18px 6px;font-size:10.5px;letter-spacing:1.5px;text-transform:uppercase;'
    + 'color:#5b7699;font-weight:700;}'
    + '.holonav-item{display:flex;align-items:center;gap:12px;padding:10px 18px;color:#b9cbe4;'
    + 'text-decoration:none;font-size:13.5px;border-left:3px solid transparent;transition:all .12s;}'
    + '.holonav-item:hover{background:rgba(0,229,255,.08);color:#fff;}'
    + '.holonav-item.active{background:rgba(0,229,255,.14);color:#00e5ff;border-left-color:#00e5ff;font-weight:600;}'
    + '.holonav-ico{width:20px;text-align:center;font-size:15px;flex:0 0 auto;}'
    + '.holonav-logout{color:#ff8080;}.holonav-logout:hover{background:rgba(255,80,80,.1);color:#ff9d9d;}';
  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // ── DOM ─────────────────────────────────────────────────────────────────
  var backdrop = document.createElement('div');
  backdrop.className = 'holonav-backdrop';

  var drawer = document.createElement('nav');
  drawer.className = 'holonav-drawer';

  var parts = ['<div class="holonav-head"><span class="holonav-logo">◉</span> HOLO-RTLS</div>'];
  PAGES.forEach(function (p) {
    if (p.sep) { parts.push('<div class="holonav-sep">' + p.sep + '</div>'); return; }
    if (p.admin && !isAdmin) return;
    var target = (p.href.replace(/\/+$/, '') || '/');
    var active = (target === here) ? ' active' : '';
    parts.push('<a class="holonav-item' + active + '" href="' + p.href + '">'
      + '<span class="holonav-ico">' + p.icon + '</span>' + p.label + '</a>');
  });
  parts.push('<div class="holonav-sep"></div>');
  parts.push('<a class="holonav-item holonav-logout" href="#" id="holonavLogout">'
    + '<span class="holonav-ico">⎋</span>Logout</a>');
  drawer.innerHTML = parts.join('');

  var btn = document.createElement('button');
  btn.className = 'holonav-toggle';
  btn.type = 'button';
  btn.setAttribute('aria-label', 'Open navigation');
  btn.textContent = '☰';

  function openNav() { drawer.classList.add('open'); backdrop.classList.add('open'); }
  function closeNav() { drawer.classList.remove('open'); backdrop.classList.remove('open'); }
  btn.addEventListener('click', function (e) {
    e.stopPropagation();
    drawer.classList.contains('open') ? closeNav() : openNav();
  });
  backdrop.addEventListener('click', closeNav);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeNav(); });

  document.body.appendChild(backdrop);
  document.body.appendChild(drawer);

  drawer.querySelector('#holonavLogout').addEventListener('click', function (e) {
    e.preventDefault();
    try {
      ['holo_access_token', 'holo_refresh_token', 'holo_user'].forEach(function (k) {
        localStorage.removeItem(k);
      });
    } catch (_) {}
    location.href = '/login';
  });

  // Place the toggle: inline in the page header when one exists, else floating.
  function place() {
    var header = document.querySelector('.topbar')
      || document.querySelector('.tracking-topbar')
      || document.querySelector('header');
    if (header) { btn.classList.add('in-header'); header.insertBefore(btn, header.firstChild); }
    else { btn.classList.add('floating'); document.body.appendChild(btn); }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', place);
  } else {
    place();
  }
})();
