/**
 * HOLO-RTLS — Global navigation drawer (professional shell).
 * Font Awesome icons; admin items gated by role; viewers hide manage pages.
 */
(function () {
  if (window.__holoNavInjected) return;
  window.__holoNavInjected = true;

  var PAGES = [
    { sep: 'Operate' },
    { href: '/',         label: 'Live Map',      icon: 'fa-solid fa-map-location-dot' },
    { href: '/alerts',   label: 'Alerts',        icon: 'fa-solid fa-bell' },
    { href: '/search',   label: 'Search',        icon: 'fa-solid fa-magnifying-glass' },
    { href: '/muster',   label: 'Muster',        icon: 'fa-solid fa-clipboard-user' },
    { sep: 'Assets' },
    { href: '/trackers', label: 'Trackers',      icon: 'fa-solid fa-tags' },
    { href: '/?mode=setup', label: 'Map Setup',   icon: 'fa-solid fa-wrench', operator: true },
    { sep: 'Site' },
    { href: '/nodes',    label: 'Anchors',       icon: 'fa-solid fa-broadcast-tower', operator: true },
    { href: '/zones',    label: 'Zones',         icon: 'fa-solid fa-draw-polygon', operator: true },
    { href: '/hardware', label: 'Hardware',      icon: 'fa-solid fa-microchip', admin: true },
    { sep: 'Insights' },
    { href: '/reports',  label: 'Reports',       icon: 'fa-solid fa-chart-line', operator: true },
    { sep: 'Admin' },
    { href: '/settings', label: 'Settings',      icon: 'fa-solid fa-gear', admin: true },
    { href: '/users',    label: 'Users',         icon: 'fa-solid fa-users', admin: true },
    { href: '/integrations', label: 'Integrations', icon: 'fa-solid fa-plug', admin: true },
    { href: '/audit',    label: 'Audit Log',     icon: 'fa-solid fa-clipboard-list', admin: true },
    { href: '/backup',   label: 'Backup',        icon: 'fa-solid fa-database', admin: true },
    { href: '/api/docs', label: 'API Docs',      icon: 'fa-solid fa-book', admin: true }
  ];

  var role = null;
  try { role = (JSON.parse(localStorage.getItem('holo_user') || 'null') || {}).role || null; } catch (e) {}
  var roleU = String(role || '').toUpperCase();
  var isAdmin = roleU === 'ADMIN';
  var isViewer = roleU === 'VIEWER';
  var isOperator = roleU === 'OPERATOR' || isAdmin;
  var here = (location.pathname.replace(/\/+$/, '') || '/');

  var css = ''
    + '.holonav-toggle{background:transparent;border:1px solid rgba(10,132,255,.4);color:#0a84ff;'
    + 'width:38px;height:38px;border-radius:8px;font-size:16px;line-height:1;cursor:pointer;'
    + 'display:inline-flex;align-items:center;justify-content:center;transition:all .15s;flex:0 0 auto;}'
    + '.holonav-toggle:hover{background:rgba(10,132,255,.12);}'
    + '.holonav-toggle.in-header{margin:0 12px 0 4px;}'
    + '.holonav-toggle.floating{position:fixed;top:12px;left:12px;z-index:100001;'
    + 'background:rgba(28,28,30,.92);box-shadow:0 2px 10px rgba(0,0,0,.45);}'
    + '.holonav-backdrop{position:fixed;inset:0;background:rgba(2,6,20,.55);z-index:100000;'
    + 'opacity:0;pointer-events:none;transition:opacity .2s;}'
    + '.holonav-backdrop.open{opacity:1;pointer-events:auto;}'
    + '.holonav-drawer{position:fixed;top:0;left:0;bottom:0;width:268px;z-index:100002;'
    + 'background:linear-gradient(180deg,#2c2c2e 0%,#1c1c1e 100%);border-right:1px solid rgba(255,255,255,.1);'
    + 'box-shadow:4px 0 24px rgba(0,0,0,.5);transform:translateX(-100%);transition:transform .22s ease;'
    + 'font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif;overflow-y:auto;padding-bottom:16px;}'
    + '.holonav-drawer.open{transform:translateX(0);}'
    + '.holonav-head{display:flex;align-items:center;gap:10px;padding:18px 18px 14px;font-weight:700;'
    + 'font-size:15px;color:#f5f5f7;border-bottom:1px solid rgba(255,255,255,.1);letter-spacing:.04em;'
    + 'font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display",system-ui,sans-serif;}'
    + '.holonav-logo{color:#0a84ff;font-size:18px;}'
    + '.holonav-sep{padding:14px 18px 6px;font-size:10.5px;letter-spacing:1.4px;text-transform:uppercase;'
    + 'color:#98989d;font-weight:700;}'
    + '.holonav-item{display:flex;align-items:center;gap:12px;padding:10px 18px;color:#e5e5ea;'
    + 'text-decoration:none;font-size:13.5px;border-left:3px solid transparent;transition:all .12s;}'
    + '.holonav-item:hover{background:rgba(10,132,255,.08);color:#fff;}'
    + '.holonav-item.active{background:rgba(10,132,255,.14);color:#0a84ff;border-left-color:#0a84ff;font-weight:600;}'
    + '.holonav-ico{width:20px;text-align:center;font-size:13px;flex:0 0 auto;opacity:.9;}'
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
    if (p.operator && isViewer) return;
    var active = false;
    var hrefPath = p.href.split('?')[0];
    var hrefQuery = p.href.includes('?') ? p.href.split('?')[1] : '';
    if (p.href === '/') {
      active = (here === '/' && location.search.indexOf('mode=setup') < 0);
    } else if (hrefQuery.indexOf('mode=setup') >= 0) {
      active = (here === '/' && location.search.indexOf('mode=setup') >= 0);
    } else {
      active = here.indexOf(hrefPath) === 0;
    }
    parts.push(
      '<a class="holonav-item' + (active ? ' active' : '') + '" href="' + p.href + '">'
      + '<span class="holonav-ico"><i class="' + p.icon + '"></i></span>' + p.label + '</a>'
    );
  });
  parts.push('<div class="holonav-sep">Account</div>');
  parts.push('<a class="holonav-item" href="#" id="holoNavPalette"><span class="holonav-ico"><i class="fa-solid fa-terminal"></i></span>Command palette <span style="opacity:.5;margin-left:auto;font-size:11px">Ctrl+K</span></a>');
  parts.push('<a class="holonav-item holonav-logout" href="#" id="holoNavLogout"><span class="holonav-ico"><i class="fa-solid fa-right-from-bracket"></i></span>Sign out</a>');
  drawer.innerHTML = parts.join('');

  document.body.appendChild(backdrop);
  document.body.appendChild(drawer);

  function openNav() { backdrop.classList.add('open'); drawer.classList.add('open'); }
  function closeNav() { backdrop.classList.remove('open'); drawer.classList.remove('open'); }

  var btn = document.createElement('button');
  btn.className = 'holonav-toggle';
  btn.type = 'button';
  btn.setAttribute('aria-label', 'Open navigation');
  btn.innerHTML = '<i class="fa-solid fa-bars"></i>';
  btn.addEventListener('click', openNav);
  backdrop.addEventListener('click', closeNav);

  var topbar = document.querySelector('.topbar, .shell-topbar, .tracking-topbar, header');
  if (topbar) {
    btn.classList.add('in-header');
    topbar.insertBefore(btn, topbar.firstChild);
  } else {
    btn.classList.add('floating');
    document.body.appendChild(btn);
  }

  drawer.querySelector('#holoNavLogout').addEventListener('click', function (e) {
    e.preventDefault();
    try {
      if (window.API && API.post) API.post('/auth/logout').catch(function () {});
      if (window.API && API.clearTokens) API.clearTokens();
      else {
        localStorage.removeItem('holo_access_token');
        localStorage.removeItem('holo_refresh_token');
        localStorage.removeItem('holo_user');
      }
    } catch (err) {}
    location.href = '/login';
  });
  var pal = drawer.querySelector('#holoNavPalette');
  if (pal) pal.addEventListener('click', function (e) {
    e.preventDefault();
    closeNav();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }));
  });

  // Load shell.js for Ctrl+K if not already present
  if (!document.querySelector('script[src*="shell.js"]')) {
    var s = document.createElement('script');
    s.src = '/static/js/shell.js';
    document.head.appendChild(s);
  }
})();
