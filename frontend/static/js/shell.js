/**
 * HOLO-RTLS — Shell utilities: Ctrl+K command palette + permission helpers.
 */
(function () {
  if (window.__holoShell) return;
  window.__holoShell = true;

  var COMMANDS = [
    { label: 'Live Map', href: '/', keys: 'map live' },
    { label: 'Alerts', href: '/alerts', keys: 'alerts' },
    { label: 'Search', href: '/search', keys: 'search find' },
    { label: 'Muster', href: '/muster', keys: 'muster checkin' },
    { label: 'Trackers', href: '/trackers', keys: 'trackers tags assets' },
    { label: 'Commissioning', href: '/tracking', keys: 'commissioning scanner setup' },
    { label: 'Anchors / Nodes', href: '/nodes', keys: 'anchors nodes' },
    { label: 'Zones', href: '/zones', keys: 'zones geofence' },
    { label: 'Hardware', href: '/hardware', keys: 'hardware', admin: true },
    { label: 'Reports', href: '/reports', keys: 'reports analytics' },
    { label: 'Settings', href: '/settings', keys: 'settings', admin: true },
    { label: 'Users', href: '/users', keys: 'users', admin: true },
    { label: 'Integrations', href: '/integrations', keys: 'api keys webhooks', admin: true },
    { label: 'Audit Log', href: '/audit', keys: 'audit', admin: true },
    { label: 'Backup', href: '/backup', keys: 'backup', admin: true }
  ];

  function role() {
    try { return (JSON.parse(localStorage.getItem('holo_user') || 'null') || {}).role || ''; }
    catch (e) { return ''; }
  }
  function isAdmin() { return String(role()).toUpperCase() === 'ADMIN'; }
  function isViewer() { return String(role()).toUpperCase() === 'VIEWER'; }

  window.HoloRBAC = {
    role: role,
    isAdmin: isAdmin,
    isViewer: isViewer,
    canManage: function () { return !isViewer(); },
    hideViewerActions: function (sel) {
      if (!isViewer()) return;
      document.querySelectorAll(sel || '[data-role-min="operator"]').forEach(function (el) {
        el.style.display = 'none';
      });
    }
  };

  function ensurePalette() {
    if (document.getElementById('holoPalette')) return;
    var css = document.createElement('style');
    css.textContent = ''
      + '#holoPaletteBackdrop{position:fixed;inset:0;background:rgba(2,6,20,.65);z-index:200000;display:none}'
      + '#holoPalette{position:fixed;top:12vh;left:50%;transform:translateX(-50%);width:min(520px,92vw);'
      + 'background:#111827;border:1px solid rgba(45,212,191,.35);z-index:200001;display:none;'
      + 'font-family:"IBM Plex Sans",system-ui,sans-serif;box-shadow:0 20px 50px rgba(0,0,0,.5)}'
      + '#holoPalette input{width:100%;box-sizing:border-box;padding:14px 16px;border:0;border-bottom:1px solid rgba(148,163,184,.2);'
      + 'background:transparent;color:#e2e8f0;font-size:15px;outline:none}'
      + '#holoPaletteList{max-height:50vh;overflow:auto}'
      + '#holoPaletteList a{display:block;padding:10px 16px;color:#94a3b8;text-decoration:none;font-size:14px}'
      + '#holoPaletteList a:hover,#holoPaletteList a.active{background:rgba(45,212,191,.12);color:#2dd4bf}'
      + '#holoPaletteHint{padding:8px 16px;font-size:11px;color:#64748b;border-top:1px solid rgba(148,163,184,.15)}';
    document.head.appendChild(css);

    var backdrop = document.createElement('div');
    backdrop.id = 'holoPaletteBackdrop';
    var box = document.createElement('div');
    box.id = 'holoPalette';
    box.innerHTML = '<input id="holoPaletteInput" placeholder="Jump to…" autocomplete="off" />'
      + '<div id="holoPaletteList"></div>'
      + '<div id="holoPaletteHint">Ctrl+K · Esc to close</div>';
    document.body.appendChild(backdrop);
    document.body.appendChild(box);

    backdrop.addEventListener('click', closePalette);
    document.getElementById('holoPaletteInput').addEventListener('input', renderList);
    document.getElementById('holoPaletteInput').addEventListener('keydown', function (e) {
      var items = Array.prototype.slice.call(document.querySelectorAll('#holoPaletteList a'));
      var cur = items.findIndex(function (a) { return a.classList.contains('active'); });
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (items[cur]) items[cur].classList.remove('active');
        var n = items[(cur + 1) % items.length];
        if (n) n.classList.add('active');
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (items[cur]) items[cur].classList.remove('active');
        var p = items[(cur - 1 + items.length) % items.length];
        if (p) p.classList.add('active');
      } else if (e.key === 'Enter') {
        e.preventDefault();
        var a = items[cur] || items[0];
        if (a) location.href = a.getAttribute('href');
      } else if (e.key === 'Escape') {
        closePalette();
      }
    });
  }

  function renderList() {
    var q = (document.getElementById('holoPaletteInput').value || '').toLowerCase().trim();
    var list = document.getElementById('holoPaletteList');
    var admin = isAdmin();
    var html = COMMANDS.filter(function (c) {
      if (c.admin && !admin) return false;
      if (!q) return true;
      return (c.label + ' ' + c.keys).toLowerCase().indexOf(q) >= 0;
    }).map(function (c, i) {
      return '<a href="' + c.href + '" class="' + (i === 0 ? 'active' : '') + '">' + c.label + '</a>';
    }).join('');
    list.innerHTML = html || '<div style="padding:14px 16px;color:#64748b">No matches</div>';
  }

  function openPalette() {
    ensurePalette();
    document.getElementById('holoPaletteBackdrop').style.display = 'block';
    document.getElementById('holoPalette').style.display = 'block';
    var input = document.getElementById('holoPaletteInput');
    input.value = '';
    renderList();
    setTimeout(function () { input.focus(); }, 10);
  }
  function closePalette() {
    var b = document.getElementById('holoPaletteBackdrop');
    var p = document.getElementById('holoPalette');
    if (b) b.style.display = 'none';
    if (p) p.style.display = 'none';
  }

  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      openPalette();
    }
    if (e.key === 'Escape') closePalette();
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (window.HoloRBAC) window.HoloRBAC.hideViewerActions();
  });
})();
