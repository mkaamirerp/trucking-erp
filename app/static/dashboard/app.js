(function () {
  const API = '/api/v1';
  const opts = { credentials: 'include' };

  function getSummary() {
    return fetch(API + '/dashboard/summary', opts).then(r => {
      if (!r.ok) throw new Error('Summary failed');
      return r.json();
    });
  }

  function getDrivers() {
    return fetch(API + '/drivers?limit=50', opts).then(r => {
      if (!r.ok) throw new Error('Drivers failed');
      return r.json();
    });
  }

  function getLoads() {
    return fetch(API + '/loads?size=50', opts).then(r => {
      if (!r.ok) throw new Error('Loads failed');
      return r.json();
    });
  }

  function seedDemo() {
    return fetch(API + '/dashboard/seed-demo', { ...opts, method: 'POST' }).then(r => {
      if (!r.ok) throw new Error('Seed failed');
      return r.json();
    });
  }

  function renderSummary(data) {
    document.getElementById('kpi-active-loads').textContent = data.active_loads ?? 0;
    document.getElementById('kpi-drivers').textContent = data.drivers_active ?? 0;
    document.getElementById('kpi-in-transit').textContent = data.in_transit ?? 0;
    document.getElementById('kpi-delayed').textContent = data.delayed ?? 0;
    const rev = data.revenue_this_week ?? 0;
    document.getElementById('kpi-revenue').textContent = '$' + (typeof rev === 'number' ? rev.toLocaleString() : rev);
  }

  function renderDrivers(list) {
    const ul = document.getElementById('driver-list');
    ul.innerHTML = '';
    (list || []).forEach(d => {
      const li = document.createElement('li');
      li.innerHTML =
        '<span class="name">' + (d.first_name || '') + ' ' + (d.last_name || '') + '</span>' +
        '<span class="location">—</span>' +
        '<span class="eta">—</span>';
      ul.appendChild(li);
    });
  }

  function renderLoads(data) {
    const tbody = document.getElementById('loads-tbody');
    tbody.innerHTML = '';
    const items = (data && data.items) ? data.items : (Array.isArray(data) ? data : []);
    items.forEach(l => {
      const tr = document.createElement('tr');
      const driverName = l.driver ? (l.driver.first_name + ' ' + l.driver.last_name) : '—';
      const status = (l.status || '').replace('_', ' ');
      tr.innerHTML =
        '<td>#' + (l.load_number || l.id) + '</td>' +
        '<td class="status ' + (status === 'delayed' ? 'delayed' : status === 'delivered' ? 'delivered' : '') + '">' + status + '</td>' +
        '<td>' + driverName + '</td>' +
        '<td>' + (l.pickup_location || '—') + '</td>' +
        '<td>' + (l.delivery_location || '—') + '</td>';
      tbody.appendChild(tr);
    });
    const available = items.filter(l => (l.status || '') === 'planned' || (l.status || '') === 'assigned').length;
    const el = document.getElementById('loads-available');
    if (el) el.textContent = '#' + (items.length || 0) + ' Loads';
  }

  function loadDashboard() {
    Promise.all([getSummary(), getDrivers(), getLoads()])
      .then(([summary, drivers, loads]) => {
        renderSummary(summary);
        renderDrivers(drivers);
        renderLoads(loads);
        const hasData = (summary.active_loads || 0) > 0 || (summary.drivers_active || 0) > 0;
        const banner = document.getElementById('seed-banner');
        if (banner) banner.classList.toggle('hidden', hasData);
      })
      .catch(() => {
        document.getElementById('seed-banner').classList.remove('hidden');
      });
  }

  function initSeedButton() {
    const btn = document.getElementById('seed-demo-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      btn.disabled = true;
      btn.textContent = 'Seeding…';
      seedDemo()
        .then(() => {
          btn.textContent = 'Done';
          loadDashboard();
        })
        .catch(() => {
          btn.disabled = false;
          btn.textContent = 'Seed demo data';
        });
    });
  }

  document.getElementById('date-display').textContent =
    'Today ' + new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });

  loadDashboard();
  initSeedButton();
})();
