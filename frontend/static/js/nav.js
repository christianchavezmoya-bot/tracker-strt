/**
 * HOLO-RTLS — Global navigation drawer (professional shell).
 * Injected on every page. Icon + label nav; admin items gated by role.
 */
(function () {
  if (window.__holoNavInjected) return;
  window.__holoNavInjected = true;

  var PAGES = [
    { sep: 'Operate' },
    { href: '/',         label: 'Live Map',     icon: '▣' },
    { href: '/alerts',   label: 'Alerts',       icon: '⚑' },
    { href: '/search',   label: 'Search',       icon: '⌕' },
    { href: '/muster',   label: 'Muster',       icon: '☰' },
    { sep: 'Assets' },
    { href: '/trackers', label: 'Trackers',     icon: '◈' },
    { href: '/tracking', label: 'Commissioning',icon: '◎' },
    { sep: 'Site' },
    { href: '/nodes',    label: 'Anchors',      icon: '⌖' },
    { href: '/zones',    label: 'Zones',        icon: '⬡' },
    { href: '/hardware', label: 'Hardware',     icon: '⚙', admin: true },
    { sep: 'Insights' },
    { href: '/reports',  label: 'Reports',      icon: '▤' },
    { sep: 'Admin' },
    { href: '/settings', label: 'Settings',     icon: '☰', admin: true },
    { href: '/users',    label: 'Users',        icon: '☺', admin: true },
    { href: '/integrations', label: 'Integrations', icon: '⛓', admin: true },
    { href: '/audit',    label: 'Audit Log',    icon: '≡', admin: true },
    { href: '/backup',   label: 'Backup',       icon: '⬇', admin: true },
    { href: '/api/docs', label: 'API Docs',     icon: '¶', admin: true }
  ];

  var role = null;
  try { role = (JSON.parse(localStorage.getItem('holo_user') || 'null') || {}).role || null; } catch (e) {}
  var isAdmin = (role == null) || (String(role).toUpperCase() === 'ADMIN');
  var here = (location.pathname.replace(/\/+$/, '') || '/');

  var css = ''
    + '.holonav-toggle{background:transparent;border:1px solid rgba(14,165,164,.4);color:#0ea5a4;'
    + 'width:38px;height:38px;border-radius:8px;font-size:18px;line-height:1;cursor:pointer;'
    + 'display:inline-flex;align-items:center;justify-content:center;transition:all .15s;flex:0 0 auto;}'
    + '.holonav-toggle:hover{background:rgba(14,165,164,.12);}'
    + '.holonav-toggle.in-header{margin:0 12px 0 4px;}'
    + '.holonav-toggle.floating{position:fixed;top:12px;left:12px;z-index:100001;'
    + 'background:rgba(11,18,32,.92);box-shadow:0 2px 10px rgba(0,0,0,.45);}'
    + '.holonav-backdrop{position:fixed;inset:0;background:rgba(2,6,20,.55);z-index:100000;'
    + 'opacity:0;pointer-events:none;transition:opacity .2s;}'
    + '.holonav-backdrop.open{opacity:1;pointer-events:auto;}'
    + '.holonav-drawer{position:fixed;top:0;left:0;bottom:0;width:268px;z-index:100002;'
    + 'background:linear-gradient(180deg,#111827 0%,#0b1220 100%);border-right:1px solid rgba(148,163,184,.16);'
    + 'box-shadow:4px 0 24px rgba(0,0,0,.5);transform:translateX(-100%);transition:transform .22s ease;'
    + 'font-family:"IBM Plex Sans",system-ui,sans-serif;overflow-y:auto;padding-bottom:16px;}'
    + '.holonav-drawer.open{transform:translateX(0);}'
    + '.holonav-head{display:flex;align-items:center;gap:10px;padding:18px 18px 14px;font-weight:700;'
    + 'font-size:15px;color:#e8eef7;border-bottom:1px solid rgba(148,163,184,.14);letter-spacing:.04em;'
    + 'font-family:"Space Grotesk",sans-serif;}'
    + '.holonav-logo{color:#0ea5a4;font-size:18px;}'
    + '.holonav-sep{padding:14px 18px 6px;font-size:10.5px;letter-spacing:1.4px;text-transform:uppercase;'
    + 'color:#64748b;font-weight:700;}'
    + '.holonav-item{display:flex;align-items:center;gap:12px;padding:10px 18px;color:#9aabc2;'
    + 'text-decoration:none;font-size:13.5px;border-left:3px solid transparent;transition:all .12s;}'
    + '.holonav-item:hover{background:rgba(14,165,164,.08);color:#fff;}'
    + '.holonav-item.active{background:rgba(14,165,164,.14);color:#0ea5a4;border-left-color:#0ea5a4;font-weight:600;}'
    + '.holonav-ico{width:20px;text-align:center;font-size:14px;flex:0 0 auto;opacity:.9;}'
    + '.holonav-logout{color:#f87171;}.holonav-logout:hover{background:rgba(248,113,113,.1);color:#fca5a5;}';

  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  var backdrop = document.createElement('div');
  backdrop.className = 'holonav-backdrop';
  var drawer = document.createElement('nav');
  drawer.className = 'holonav-drawer';
  drawer.setAttribute('aria-label', 'Main navigation');

  var parts = ['<div class="holonav-head"><span class="holonav-logo">◈</span> HOLO-RTLS</div>'];
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
      ['holo_access_token', 'holo_refresh_token', 'holo_user', 'access_token'].forEach(function (k) {
        localStorage.removeItem(k);
      });
    } catch (_) {}
    location.href = '/login';
  });

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
