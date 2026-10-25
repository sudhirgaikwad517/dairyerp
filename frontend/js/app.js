/**
 * Dairy ERP Enterprise Dashboard UI Logic
 */

let milkFlowChart = null;
let profitabilityChart = null;
let customersCache = [];
let productsCache = [];
let ordersCache = [];
let tripsCache = [];

// Escape text before putting it into HTML (customer names can contain quotes or &)
// ₹ amount with Indian grouping
const inr = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

document.addEventListener('DOMContentLoaded', async () => {
  // Admin panel needs an admin login
  if (!Auth.require()) return;
  try {
    const me = await DairyAPI.me();
    if (!['super_admin', 'admin'].includes(me.role)) {
      Auth.logout();
      return;
    }
    document.getElementById('header-user-name').innerText = me.full_name;
    document.getElementById('sidebar-user-name').innerText = me.full_name;
  } catch (err) {
    return; // apiRequest already sent the user to the login page
  }
  initClock();
  setupNavigation();
  await loadDashboardMetrics();
  try {
    productsCache = await DairyAPI.getProducts();
  } catch (err) {
    console.error('Failed to load products:', err);
  }
  await loadCustomerTable();
  await loadPricingTable();
  await loadOrdersTable();
  await loadTransportTrips();
  await loadProcurementTable();
  await loadProductionTable();
  await loadProfitabilityTable();
  await loadInvoicesTable();
  await setupClaimsAndDispatch();
  setupModalForms();
  setupBillingForms();
  await setupSalesReport();
});

// Real-Time Clock
function initClock() {
  const clockEl = document.getElementById('live-clock');
  function updateTime() {
    if (clockEl) {
      const now = new Date();
      clockEl.innerText = now.toLocaleDateString('en-IN', {
        weekday: 'short', day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
      });
    }
  }
  updateTime();
  setInterval(updateTime, 1000);
}

// Mobile sidebar open/close
window.toggleSidebar = function(open) {
  document.getElementById('sidebar').classList.toggle('open', open);
};

// Sidebar Navigation Tab Switcher
function setupNavigation() {
  const navBtns = document.querySelectorAll('.nav-item-btn[data-target]');
  const views = document.querySelectorAll('.module-view');

  const showView = (targetId) => {
    const btn = [...navBtns].find(b => b.getAttribute('data-target') === targetId);
    if (!btn) return false;
    navBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    toggleSidebar(false);
    window.scrollTo(0, 0);

    views.forEach(v => {
      if (v.id === targetId) {
        v.classList.remove('d-none');
        v.classList.add('active-view');
      } else {
        v.classList.add('d-none');
        v.classList.remove('active-view');
      }
    });
    return true;
  };

  navBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = btn.getAttribute('data-target');
      // Keep the open tab in the URL so a refresh stays on it
      if (location.hash !== '#' + targetId) location.hash = targetId;
      else showView(targetId);
    });
  });

  // Browser back/forward and refresh restore the tab from the URL
  window.addEventListener('hashchange', () => showView(location.hash.slice(1)));
  if (location.hash) showView(location.hash.slice(1));
}

// 1. Dashboard Metrics & Charts
async function loadDashboardMetrics() {
  loadTomorrowPanel();
  try {
    const dateInput = document.getElementById('dash-date');
    if (!dateInput.value) {
      const now = new Date();
      dateInput.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    }
    const data = await DairyAPI.getDashboardOverview(dateInput.value);
    const num = (n) => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
    const rupees = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const setText = (id, text) => { document.getElementById(id).innerText = text; };
    const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
    const { procurement, production, dispatch, wastage, closing_stock, financials, operations } = data;

    // Overview Metrics (all values are for today)
    setText('metric-procured', num(procurement.today_total_litres));
    setText('metric-procured-sub',
      `${plural(procurement.collections_count, 'collection')} • ${procurement.accepted_pct}% accepted • Avg fat ${procurement.avg_fat_pct}%`);

    setText('metric-production', num(production.today_total_litres));
    setText('metric-production-sub',
      `Packed milk • ${production.today_total_kg > 0 ? `+${num(production.today_total_kg)} KG curd/paneer • ` : ''}${num(production.raw_milk_used_litres)} L raw milk used`);

    setText('metric-dispatched', num(dispatch.today_dispatched_litres));
    setText('metric-dispatched-sub',
      `${plural(dispatch.trips_count, 'trip')} • ${operations.delivered_orders_today} of ${financials.today_orders_count} orders delivered`);

    setText('metric-wastage', num(wastage.today_wastage_litres) + ' L');
    setText('metric-wastage-sub', `Wastage (${wastage.wastage_pct}%)`);
    setText('metric-closing-stock', num(closing_stock.closing_stock_litres) + ' L');
    setText('metric-raw-balance', `Raw milk balance: ${num(closing_stock.raw_milk_balance_litres)} L`);

    // Sales = delivered milk less claims (same as the Sales Register); undelivered orders shown apart
    setText('metric-sales', rupees(financials.today_sales));
    const salesNotes = [`${num(financials.today_sales_litres)} L sold`];
    if (financials.pending_delivery_count) salesNotes.push(`${rupees(financials.pending_delivery_amount)} (${plural(financials.pending_delivery_count, 'order')}) not delivered yet`);
    if (financials.claims_amount) salesNotes.push(`claims −${rupees(financials.claims_amount)}`);
    if (financials.short_amount) salesNotes.push(`short −${rupees(financials.short_amount)}`);
    setText('metric-sales-sub', salesNotes.join(' • '));
    setText('metric-transport-cost', rupees(financials.transport_cost));
    setText('metric-transport-sub', financials.transport_cost_set
      ? `Day's cost • ${num(financials.transport_litres)} L delivered`
      : 'Not entered yet (Transport tab)');
    setText('metric-cost-per-litre', financials.transport_cost_per_litre == null ? '—'
      : '₹' + Number(financials.transport_cost_per_litre).toFixed(2) + ' / L');
    setText('metric-cost-per-litre-sub', financials.transport_in_progress
      ? 'Shown when all deliveries of the day are done'
      : (financials.transport_cost_per_litre == null ? 'Day cost ÷ litres delivered' : 'Day cost ÷ litres delivered'));
    setText('metric-outstanding', rupees(financials.outstanding_amount));
    setText('metric-outstanding-sub', `${plural(financials.customers_with_dues, 'customer')} with dues` +
      (financials.advance_amount > 0 ? ` • advance held ${rupees(financials.advance_amount)}` : ''));

    renderMilkFlowChart(data);
  } catch (err) {
    console.error('Failed to load dashboard metrics:', err);
    ['metric-procured-sub', 'metric-production-sub', 'metric-dispatched-sub', 'metric-sales-sub', 'metric-outstanding-sub']
      .forEach(id => { document.getElementById(id).innerText = 'Could not load data'; });
  }
}

function renderMilkFlowChart(data) {
  const ctx = document.getElementById('chartMilkFlow');
  if (!ctx) return;

  if (milkFlowChart) milkFlowChart.destroy();

  milkFlowChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Procurement', 'Production', 'Dispatched', 'Wastage', 'Closing Stock'],
      datasets: [{
        label: 'Volume (Litres)',
        data: [
          data.procurement.today_total_litres,
          data.production.today_total_litres,
          data.dispatch.today_dispatched_litres,
          data.wastage.today_wastage_litres,
          data.closing_stock.closing_stock_litres
        ],
        backgroundColor: [
          'rgba(2, 132, 199, 0.8)',
          'rgba(6, 182, 212, 0.8)',
          'rgba(16, 185, 129, 0.8)',
          'rgba(244, 63, 94, 0.8)',
          'rgba(245, 158, 11, 0.8)'
        ],
        borderRadius: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: {
          grid: { color: 'rgba(0, 0, 0, 0.06)' },
          ticks: { color: '#64748b' }
        },
        x: {
          grid: { display: false },
          ticks: { color: '#334155' }
        }
      }
    }
  });
}

// 2. Customers
let driversCache = [];
let routesCache = [];

async function loadCustomerTable() {
  try {
    const [customers, drivers] = await Promise.all([DairyAPI.getCustomers(), DairyAPI.getDrivers()]);
    customersCache = customers;
    driversCache = drivers;
    fillOrderCustomers();
    document.getElementById('nav-customer-count').innerText = customers.filter(c => c.is_active).length;

    const driverFilter = document.getElementById('cust-filter-driver');
    const selected = driverFilter.value;
    driverFilter.innerHTML = '<option value="">All delivery boys</option><option value="none">No delivery boy</option>' +
      drivers.map(d => `<option value="${d.id}">${esc(d.full_name)}</option>`).join('');
    driverFilter.value = selected;

    renderCustomerTable();
  } catch (err) {
    console.error('Failed to load customers:', err);
    document.getElementById('customers-tbody').innerHTML =
      `<tr><td colspan="7" class="text-danger">Could not load customers: ${esc(err.message)}</td></tr>`;
  }
}

function renderCustomerTable() {
  const tbody = document.getElementById('customers-tbody');
  const q = document.getElementById('cust-search').value.trim().toLowerCase();
  const driver = document.getElementById('cust-filter-driver').value;
  const showInactive = document.getElementById('cust-show-inactive').checked;
  const money = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });

  const rows = customersCache.filter(c => {
    if (!showInactive && !c.is_active) return false;
    if (driver === 'none' && c.assigned_driver_id) return false;
    if (driver && driver !== 'none' && String(c.assigned_driver_id) !== driver) return false;
    if (!q) return true;
    return [c.business_name, c.customer_code, c.contact_person, c.phone, c.delivery_address]
      .some(v => (v || '').toLowerCase().includes(q));
  });

  document.getElementById('cust-count').innerText = `${rows.length} of ${customersCache.length} customers`;
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">No customers match.</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map(c => `
    <tr class="${c.is_active ? '' : 'opacity-50'}">
      <td><span class="badge bg-secondary font-monospace">${esc(c.customer_code)}</span>
        ${c.is_active ? '' : '<br><span class="badge bg-light text-muted mt-1">INACTIVE</span>'}</td>
      <td>
        <div class="fw-bold">${esc(c.business_name)}
          ${c.has_login
            ? (c.login_active
              ? '<span class="badge bg-success-subtle text-success ms-1" title="Can log in to the customer app"><i class="bi bi-phone"></i> App</span>'
              : '<span class="badge bg-secondary-subtle text-secondary ms-1" title="App login disabled"><i class="bi bi-phone"></i> Disabled</span>')
            : ''}</div>
        <small class="text-muted">${esc(c.contact_person)} • ${esc(c.phone)}</small>
        <br><small class="text-muted">${esc(c.delivery_address)}</small>
      </td>
      <td>
        <span>${esc(c.route_name)}</span>${c.assigned_route_id ? ` <small class="text-muted">• Stop ${c.route_stop_sequence}</small>` : ''}
        <br>${c.driver_name
          ? `<small class="text-info"><i class="bi bi-person-badge"></i> ${esc(c.driver_name)}</small>`
          : '<small class="text-warning"><i class="bi bi-exclamation-circle"></i> No delivery boy</small>'}
      </td>
      <td class="text-end text-nowrap">
        <div class="fw-bold">${money(c.milk_rate)}</div>${c.rate_product ? `<small class="text-muted">${esc(c.rate_product)}</small>` : ''}
      </td>
      <td class="text-end text-nowrap">${c.credit_limit > 0 ? money(c.credit_limit) : '<span class="text-muted">No limit</span>'}<br><small class="text-muted">${c.credit_days} days</small></td>
      <td class="text-end fw-bold text-nowrap ${c.current_outstanding > 0 ? 'text-danger' : 'text-success'}">
        ${c.current_outstanding < 0 ? `${money(-c.current_outstanding)}<br><small class="fw-normal">advance</small>` : money(c.current_outstanding)}
        ${c.unbilled_amount > 0 ? `<br><small class="fw-normal text-muted" title="Milk delivered but not billed yet; included in the total">incl. ${money(c.unbilled_amount)} not billed</small>` : ''}
        ${c.credit_limit > 0 && c.current_outstanding > c.credit_limit ? '<br><span class="badge bg-danger">Over limit</span>' : ''}
      </td>
      <td class="text-nowrap">
        <button class="btn btn-sm btn-outline-primary" onclick="openCustomerModal(${c.id})" title="Edit customer">
          <i class="bi bi-pencil"></i> Edit
        </button>
        <button class="btn btn-sm ${c.has_login ? (c.login_active ? 'btn-outline-success' : 'btn-outline-secondary') : 'btn-outline-warning'}"
          onclick="openCustomerLogin(${c.id})" title="${c.has_login ? 'App login: reset password / enable / disable' : 'Create app login'}">
          <i class="bi bi-key"></i> ${c.has_login ? 'Login' : 'Set Login'}
        </button>
        <button class="btn btn-sm btn-outline-info" onclick="viewCustomerLedger(${c.id})" title="Ledger">
          <i class="bi bi-journal-text"></i>
        </button>
        <button class="btn btn-sm btn-outline-secondary" onclick="openPricingModal(${c.id})" title="Product prices">
          <i class="bi bi-tag"></i>
        </button>
      </td>
    </tr>
  `).join('');
}

async function ensureRoutes() {
  if (!routesCache.length) routesCache = await DairyAPI.getRoutes();
  return routesCache;
}

window.openCustomerModal = async function(customerId = null) {
  // Always fill the form from fresh data, so it shows exactly what is saved now
  let routesAll = [];
  try {
    const [customers, drivers, routes, products] = await Promise.all([
      DairyAPI.getCustomers(), DairyAPI.getDrivers(), DairyAPI.getRoutes(true), DairyAPI.getAllProducts()]);
    customersCache = customers;
    driversCache = drivers;
    routesAll = routes;
    routesCache = routes.filter(r => r.is_active);
    allProducts = products;
  } catch (err) {
    alert('Could not load the customer: ' + err.message);
    return;
  }
  const c = customerId ? customersCache.find(x => x.id === customerId) : null;
  if (customerId && !c) {
    alert('This customer was not found. Reload the page.');
    return;
  }
  // Active routes, plus the customer's own route even if it was switched off
  const routeList = routesAll.filter(r => r.is_active || (c && c.assigned_route_id === r.id));
  document.getElementById('cust-route').innerHTML =
    (routeList.length ? '<option value="">No route</option>' : '<option value="">No routes yet: add one in Customers &rarr; Routes</option>') +
    routeList.map(r => `<option value="${r.id}">${esc(r.route_name)}${r.driver_name ? ' &bull; ' + esc(r.driver_name) : ''}${r.is_active ? '' : ' (off)'}</option>`).join('');
  document.getElementById('cust-driver').innerHTML = '<option value="">Not assigned</option>' +
    driversCache.filter(d => d.is_active || (c && c.assigned_driver_id === d.id))
      .map(d => `<option value="${d.id}">${esc(d.full_name)} (${esc(d.phone)})${d.is_active ? '' : ' (inactive)'}</option>`).join('');

  // One rate per product on sale (and any product this customer already has an own rate for)
  const own = (c && c.own_rates) || {};
  const rateProducts = allProducts.filter(p => p.is_active || own[p.id] !== undefined);
  document.getElementById('cust-rates').innerHTML = rateProducts.length ? rateProducts.map(p => `
    <tr>
      <td><div class="fw-semibold">${esc(p.product_name)}</div><small class="text-muted">per ${esc(UNIT_LABEL[p.unit] || p.unit)}${p.is_active ? '' : ' • off sale'}</small></td>
      <td class="text-end">${inr(p.standard_b2b_price)}</td>
      <td><input type="number" step="0.01" min="0.01" class="form-control form-control-sm form-dairy-control cust-rate"
        data-product="${p.id}" placeholder="${p.standard_b2b_price}" value="${own[p.id] ?? ''}"></td>
    </tr>`).join('') : '<tr><td colspan="3" class="text-muted small">No products yet: add them in Products.</td></tr>';

  const set = (id, v) => { document.getElementById(id).value = v ?? ''; };
  document.getElementById('cust-modal-title').innerText = c ? `Edit Customer • ${c.customer_code}` : 'Add Customer';
  set('cust-id', c ? c.id : '');
  set('cust-business-name', c?.business_name);
  set('cust-contact-person', c?.contact_person);
  set('cust-phone', c?.phone);
  set('cust-email', c?.email);
  set('cust-type', c ? c.customer_type : 'retailer');
  set('cust-address', c?.delivery_address);
  set('cust-billing-address', c && c.billing_address !== c.delivery_address ? c.billing_address : '');
  set('cust-gstin', c?.gstin);
  set('cust-code', c?.customer_code);
  document.getElementById('cust-code').disabled = !!c;
  set('cust-route', c ? (c.assigned_route_id ?? '') : (routesCache[0]?.id ?? ''));
  set('cust-driver', c ? (c.assigned_driver_id ?? '') : (routesCache[0]?.driver_id ?? ''));
  set('cust-stop', c ? c.route_stop_sequence : 1);
  set('cust-credit-limit', c ? c.credit_limit : 50000);
  set('cust-credit-days', c ? c.credit_days : 7);
  document.getElementById('cust-active').checked = c ? c.is_active : true;
  document.getElementById('cust-save-btn').innerText = c ? 'Save Changes' : 'Add Customer';
  new bootstrap.Modal(document.getElementById('modalCustomer')).show();
};

// Customer app login
window.openCustomerLogin = function(customerId) {
  const c = customersCache.find(x => x.id === customerId);
  if (!c) return;
  const status = document.getElementById('cl-status');
  document.getElementById('cl-customer-id').value = c.id;
  document.getElementById('cl-customer-name').innerText = `${c.business_name} • ${c.customer_code}`;
  document.getElementById('cl-login-id').value = c.phone;
  document.getElementById('cl-password').value = '';
  document.getElementById('cl-active').checked = c.has_login ? c.login_active : true;
  if (!c.has_login) {
    status.className = 'alert alert-warning py-2 small';
    status.innerText = 'This customer has no app login yet. Set a password to create one.';
    document.getElementById('cl-password-label').innerText = 'Password *';
    document.getElementById('cl-password-hint').innerText = 'Share the mobile number and this password with the customer.';
    document.getElementById('cl-save-btn').innerText = 'Create Login';
  } else {
    status.className = `alert ${c.login_active ? 'alert-success' : 'alert-secondary'} py-2 small`;
    status.innerText = c.login_active ? 'Login is active. The customer can use the app.' : 'Login is disabled. The customer cannot log in.';
    document.getElementById('cl-password-label').innerText = 'New Password (optional)';
    document.getElementById('cl-password-hint').innerText = 'Leave blank to keep the current password.';
    document.getElementById('cl-save-btn').innerText = 'Save';
  }
  new bootstrap.Modal(document.getElementById('modalCustomerLogin')).show();
};

window.suggestCustomerPassword = function() {
  // Easy to read out on a phone call: no 0/O or 1/l
  const chars = 'abcdefghjkmnpqrstuvwxyz23456789';
  const arr = new Uint32Array(8);
  crypto.getRandomValues(arr);
  document.getElementById('cl-password').value = Array.from(arr, n => chars[n % chars.length]).join('');
};

// Delivery boys
window.openDriversModal = async function() {
  resetDriverForm();
  await renderDrivers();
  new bootstrap.Modal(document.getElementById('modalDrivers')).show();
};

async function renderDrivers() {
  try {
    driversCache = await DairyAPI.getDrivers();
  } catch (err) {
    document.getElementById('drivers-tbody').innerHTML = `<tr><td colspan="5" class="text-danger">${esc(err.message)}</td></tr>`;
    return;
  }
  document.getElementById('drivers-tbody').innerHTML = driversCache.length ? driversCache.map(d => `
    <tr class="${d.is_active ? '' : 'opacity-50'}">
      <td class="fw-bold">${esc(d.full_name)}</td>
      <td>${esc(d.phone)}</td>
      <td><span class="badge bg-info text-dark">${d.customers_count}</span>
        <small class="text-muted d-block">${esc(d.customers.join(', '))}</small></td>
      <td><span class="badge ${d.is_active ? 'bg-success' : 'bg-secondary'}">${d.is_active ? 'ACTIVE' : 'INACTIVE'}</span></td>
      <td class="text-nowrap">
        <button class="btn btn-sm btn-outline-primary" onclick="editDriver(${d.id})"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-sm btn-outline-${d.is_active ? 'secondary' : 'success'}" onclick="toggleDriver(${d.id})">
          ${d.is_active ? 'Deactivate' : 'Activate'}
        </button>
      </td>
    </tr>`).join('') : '<tr><td colspan="5" class="text-center text-muted py-3">No delivery boys yet.</td></tr>';
}

window.resetDriverForm = function() {
  document.getElementById('driver-id').value = '';
  document.getElementById('driver-name').value = '';
  document.getElementById('driver-phone').value = '';
  document.getElementById('driver-password').value = '';
  document.getElementById('driver-password-label').innerText = 'Password *';
  document.getElementById('driver-save-btn').innerText = 'Add';
  document.getElementById('driver-cancel-btn').classList.add('d-none');
};

window.editDriver = function(driverId) {
  const d = driversCache.find(x => x.id === driverId);
  if (!d) return;
  document.getElementById('driver-id').value = d.id;
  document.getElementById('driver-name').value = d.full_name;
  document.getElementById('driver-phone').value = d.phone;
  document.getElementById('driver-password').value = '';
  document.getElementById('driver-password-label').innerText = 'New Password (optional)';
  document.getElementById('driver-save-btn').innerText = 'Save';
  document.getElementById('driver-cancel-btn').classList.remove('d-none');
};

window.toggleDriver = async function(driverId) {
  const d = driversCache.find(x => x.id === driverId);
  if (!d) return;
  if (d.is_active && d.customers_count &&
      !confirm(`${d.full_name} is assigned to ${d.customers_count} customer(s). Deactivate anyway?`)) return;
  try {
    await DairyAPI.updateDriver(d.id, { full_name: d.full_name, phone: d.phone, is_active: !d.is_active });
    await renderDrivers();
    await loadCustomerTable();
  } catch (err) {
    alert('Could not update delivery boy: ' + err.message);
  }
};

// Delivery routes
let routesAll = [];
window.openRoutesModal = async function() {
  try {
    driversCache = await DairyAPI.getDrivers();
  } catch (err) {
    console.error('Failed to load delivery boys:', err);
  }
  resetRouteForm();
  await renderRoutes();
  new bootstrap.Modal(document.getElementById('modalRoutes')).show();
};

function fillRouteDriverSelect(selectedId) {
  const list = driversCache.filter(d => d.is_active || d.id === selectedId);
  document.getElementById('route-driver').innerHTML = list.length
    ? '<option value="">Choose...</option>' + list.map(d => `<option value="${d.id}">${esc(d.full_name)} (${esc(d.phone)})</option>`).join('')
    : '<option value="">Add a delivery boy first</option>';
  document.getElementById('route-driver').value = selectedId ?? '';
}

async function renderRoutes() {
  const tbody = document.getElementById('routes-tbody');
  try {
    routesAll = await DairyAPI.getRoutes(true);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-danger">${esc(err.message)}</td></tr>`;
    return;
  }
  routesCache = routesAll.filter(r => r.is_active);
  tbody.innerHTML = routesAll.length ? routesAll.map(r => `
    <tr class="${r.is_active ? '' : 'opacity-50'}">
      <td class="fw-bold">${esc(r.route_name)} <small class="text-muted d-block">${esc(r.route_code)}</small></td>
      <td>${r.driver_name ? esc(r.driver_name) : '<span class="text-danger">Not set</span>'}</td>
      <td>${r.vehicle_number ? esc(r.vehicle_number) : '<span class="text-danger">Not set</span>'}
        ${r.vehicle_type ? `<small class="text-muted d-block">${esc(r.vehicle_type)}</small>` : ''}</td>
      <td><span class="badge bg-info text-dark">${r.customers_count}</span></td>
      <td><span class="badge ${!r.is_active ? 'bg-secondary' : r.ready ? 'bg-success' : 'bg-warning text-dark'}">
        ${!r.is_active ? 'OFF' : r.ready ? 'READY' : 'NEEDS ACTIVE DELIVERY BOY'}</span></td>
      <td class="text-nowrap">
        <button class="btn btn-sm btn-outline-primary" onclick="editRoute(${r.id})" title="Edit"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-sm btn-outline-${r.is_active ? 'secondary' : 'success'}" onclick="toggleRoute(${r.id})">
          ${r.is_active ? 'Switch off' : 'Switch on'}
        </button>
      </td>
    </tr>`).join('') : '<tr><td colspan="6" class="text-center text-muted py-3">No routes yet. Add the first route above.</td></tr>';
}

window.resetRouteForm = function() {
  ['route-id', 'route-name', 'route-vehicle', 'route-vehicle-type'].forEach(id => { document.getElementById(id).value = ''; });
  fillRouteDriverSelect(null);
  document.getElementById('route-save-btn').innerText = 'Add';
  document.getElementById('route-cancel-btn').classList.add('d-none');
};

window.editRoute = function(routeId) {
  const r = routesAll.find(x => x.id === routeId);
  if (!r) return;
  document.getElementById('route-id').value = r.id;
  document.getElementById('route-name').value = r.route_name;
  fillRouteDriverSelect(r.driver_id);
  document.getElementById('route-vehicle').value = r.vehicle_number || '';
  document.getElementById('route-vehicle-type').value = r.vehicle_type || '';
  document.getElementById('route-save-btn').innerText = 'Save';
  document.getElementById('route-cancel-btn').classList.remove('d-none');
  document.getElementById('route-name').focus();
};

window.toggleRoute = async function(routeId) {
  const r = routesAll.find(x => x.id === routeId);
  if (!r) return;
  if (!r.is_active && (!r.driver_id || !r.vehicle_number)) {
    editRoute(routeId);
    alert('Set the delivery boy and vehicle, then save.');
    return;
  }
  try {
    await DairyAPI.saveRoute(r.id, {
      route_name: r.route_name, driver_id: r.driver_id, vehicle_number: r.vehicle_number,
      vehicle_type: r.vehicle_type || null, is_active: !r.is_active
    });
    await renderRoutes();
    await loadCustomerTable();
  } catch (err) {
    alert('Could not update route: ' + err.message);
  }
};

// 3. Customer Ledger Modal
window.viewCustomerLedger = async function(customerId) {
  try {
    const res = await DairyAPI.getCustomerLedger(customerId);
    const modalEl = new bootstrap.Modal(document.getElementById('modalLedger'));
    
    document.getElementById('ledger-customer-name').innerText = res.customer.business_name;
    const rs = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
    // A negative balance is money the customer has paid in advance
    const bal = (n) => n < 0 ? `${rs(-n)} advance` : rs(n);
    const types = { opening_balance: ['Opening balance', 'bg-secondary'], sales_invoice: ['Bill', 'bg-primary'],
      payment: ['Payment', 'bg-success'], credit_note: ['Claim credit', 'bg-warning text-dark'], refund: ['Refund', 'bg-warning text-dark'] };
    const out = Number(res.customer.current_outstanding || 0);
    document.getElementById('ledger-credit-limit').innerText = res.customer.credit_limit > 0 ? rs(res.customer.credit_limit) : 'No limit';
    document.getElementById('ledger-outstanding').innerText = bal(out);
    const unbilled = Number(res.customer.unbilled_amount || 0);
    document.getElementById('ledger-outstanding-note').innerText = unbilled > 0
      ? `Bills ${bal(res.customer.billed_outstanding)} + delivered, not billed yet ${rs(unbilled)}` : '';

    const tbody = document.getElementById('ledger-tbody');
    tbody.innerHTML = res.ledger.length ? res.ledger.map(row => {
      const [label, cls] = types[row.type] || [row.type.replace(/_/g, ' '), 'bg-secondary'];
      return `
      <tr>
        <td class="text-nowrap">${new Date(row.date + 'T00:00:00').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</td>
        <td><span class="badge ${cls}">${esc(label)}</span></td>
        <td class="font-monospace small text-nowrap">${esc(row.ref_no || '-')}</td>
        <td>${esc(row.narration || '')}</td>
        <td class="text-danger text-end text-nowrap">${row.debit > 0 ? rs(row.debit) : '-'}</td>
        <td class="text-success text-end text-nowrap">${row.credit > 0 ? rs(row.credit) : '-'}</td>
        <td class="fw-bold text-end text-nowrap">${bal(row.balance)}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="7" class="text-center text-muted py-4">No transactions yet.</td></tr>';

    modalEl.show();
  } catch (err) {
    alert('Failed to load customer ledger: ' + err.message);
  }
};

// 4. Customer Pricing: one row per customer (not per product), filters and pages, so 200 customers
// x 15 products stays readable. A customer's rates for every size are set in one popup.
let pricingCache = [];
let standardPrices = [];
let pricingPage = 1;
let pricingPageSize = 25;

const money2 = (n) => '₹' + Number(n || 0).toFixed(2);
const sizeLabel = (p) => p.variant_name || p.product_name;

// Products with their sizes, in the order of the Products page
function priceGroups(list) {
  const groups = new Map();
  list.forEach(p => {
    const key = p.group_name || p.product_name;
    if (!groups.has(key)) groups.set(key, { name: key, items: [] });
    groups.get(key).items.push(p);
  });
  return [...groups.values()];
}

// Each customer with their rate rows
function pricingCustomers() {
  const map = new Map();
  pricingCache.forEach(r => {
    if (!map.has(r.customer_id)) map.set(r.customer_id, { id: r.customer_id, name: r.customer_name, code: r.customer_code, rows: [] });
    map.get(r.customer_id).rows.push(r);
  });
  return [...map.values()];
}

async function loadPricingTable() {
  const tbody = document.getElementById('pricing-tbody');
  if (!tbody) return;
  try {
    [pricingCache, standardPrices] = await Promise.all([DairyAPI.getCustomPricing(), DairyAPI.getStandardPrices()]);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="text-danger">Could not load prices: ${esc(err.message)}</td></tr>`;
    return;
  }
  const groups = priceGroups(standardPrices);
  const ownCount = (ids) => pricingCache.filter(r => r.is_custom && ids.includes(r.product_id)).length;
  document.getElementById('standard-prices').innerHTML = groups.length ? groups.map((g, i) => {
    const own = ownCount(g.items.map(p => p.id));
    const meta = g.items.length > 1 ? `${g.items.length} sizes` : `${money2(g.items[0].standard_b2b_price)}/${esc(g.items[0].unit)}`;
    return `<button type="button" class="price-group-chip" onclick="openStandardPrices(${i})">
      <i class="bi bi-tag"></i>${esc(g.name)}<span class="chip-meta">${meta}${own ? ` • ${own} own rate${own === 1 ? '' : 's'}` : ''}</span>
    </button>`;
  }).join('') : '<span class="text-muted">No products on sale.</span>';

  const select = document.getElementById('pricing-product');
  const keep = select.value;
  select.innerHTML = '<option value="">All products</option>' +
    groups.map(g => `<option value="${esc(g.name)}">${esc(g.name)}</option>`).join('');
  select.value = groups.some(g => g.name === keep) ? keep : '';
  renderPricingTable();
}

function renderPricingTable() {
  const tbody = document.getElementById('pricing-tbody');
  const term = document.getElementById('pricing-search').value.trim().toLowerCase();
  const group = document.getElementById('pricing-product').value;
  const filter = document.getElementById('pricing-filter').value;
  document.getElementById('pricing-rates-head').innerText = group ? `${group} rates` : 'Own rates';

  const list = pricingCustomers().map(c => {
    const rows = group ? c.rows.filter(r => r.group_name === group) : c.rows;
    return { ...c, rows, own: rows.filter(r => r.is_custom) };
  }).filter(c =>
    (!term || c.name.toLowerCase().includes(term) || (c.code || '').toLowerCase().includes(term)) &&
    (filter !== 'own' || c.own.length) && (filter !== 'standard' || !c.own.length));

  const total = list.length;
  const pages = Math.max(1, Math.ceil(total / pricingPageSize));
  pricingPage = Math.min(Math.max(1, pricingPage), pages);
  const from = (pricingPage - 1) * pricingPageSize;
  const page = list.slice(from, from + pricingPageSize);
  const customers = new Set(pricingCache.map(r => r.customer_id)).size;
  const withOwn = new Set(pricingCache.filter(r => r.is_custom).map(r => r.customer_id)).size;
  document.getElementById('pricing-count').innerText = `${customers} customers • ${withOwn} with their own rate`;

  const rateSince = (iso) => iso ? new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '-';
  const pill = (r, withName) => {
    const diff = r.standard_b2b_price - r.custom_price;
    const note = !r.is_custom ? 'standard' : diff > 0 ? `₹${diff.toFixed(2)} less` : diff < 0 ? `₹${Math.abs(diff).toFixed(2)} more` : 'same as standard';
    return `<span class="rate-pill ${r.is_custom ? 'own' : ''}" title="${esc(r.product_name)}: ${note}">${esc(withName ? r.product_name : sizeLabel(r))} ${money2(r.custom_price)}</span>`;
  };
  const ratesCell = (c) => {
    if (group) return c.rows.map(r => pill(r, false)).join('');
    if (!c.own.length) return '<span class="text-muted small">Standard price for all products</span>';
    const shown = c.own.slice(0, 3).map(r => pill(r, true)).join('');
    return shown + (c.own.length > 3 ? `<span class="small text-muted">+${c.own.length - 3} more</span>` : '');
  };
  const since = (c) => {
    const days = c.own.map(r => r.effective_from).filter(Boolean).sort();
    return days.length ? rateSince(days[days.length - 1]) : '-';
  };

  tbody.innerHTML = page.length ? page.map(c => `
    <tr>
      <td class="fw-bold text-nowrap">${esc(c.name)}<br><small class="text-muted fw-normal">${esc(c.code)}</small></td>
      <td>${ratesCell(c)}</td>
      <td class="text-nowrap small">${since(c)}</td>
      <td class="text-end">
        <button class="btn btn-sm btn-outline-warning text-nowrap" onclick="openPricingModal(${c.id})">
          <i class="bi bi-pencil me-1"></i>${c.own.length ? 'Edit rates' : 'Set rates'}
        </button>
      </td>
    </tr>`).join('') : '<tr><td colspan="4" class="text-center text-muted py-4">No customers match.</td></tr>';

  document.getElementById('pricing-pager').innerHTML = total ? `
    <span class="small text-muted">Showing ${from + 1}–${from + page.length} of ${total}</span>
    <div class="pager-buttons">
      <select class="form-select form-select-sm form-dairy-control" onchange="setPricingPageSize(this.value)" title="Rows per page">
        ${[25, 50, 100].map(n => `<option value="${n}" ${n === pricingPageSize ? 'selected' : ''}>${n} / page</option>`).join('')}
      </select>
      <button class="btn btn-sm btn-outline-secondary" ${pricingPage === 1 ? 'disabled' : ''} onclick="setPricingPage(${pricingPage - 1})" title="Previous page"><i class="bi bi-chevron-left"></i></button>
      <span class="small px-2 text-nowrap">Page ${pricingPage} of ${pages}</span>
      <button class="btn btn-sm btn-outline-secondary" ${pricingPage === pages ? 'disabled' : ''} onclick="setPricingPage(${pricingPage + 1})" title="Next page"><i class="bi bi-chevron-right"></i></button>
    </div>` : '';
}

window.setPricingPage = function(n) {
  pricingPage = n;
  renderPricingTable();
};

window.setPricingPageSize = function(n) {
  pricingPageSize = parseInt(n) || 25;
  pricingPage = 1;
  renderPricingTable();
};

async function afterPriceChange() {
  productsCache = await DairyAPI.getProducts();
  await loadPricingTable();
  await loadCustomerTable();
  await loadProfitabilityTable();
}

// Standard price of one product's sizes
let stdGroup = null;
window.openStandardPrices = function(index) {
  stdGroup = priceGroups(standardPrices)[index];
  if (!stdGroup) return;
  document.getElementById('std-group-name').innerText = stdGroup.name;
  document.getElementById('std-tbody').innerHTML = stdGroup.items.map(p => {
    const own = pricingCache.filter(r => r.product_id === p.id && r.is_custom).length;
    return `<tr>
      <td class="fw-semibold">${esc(sizeLabel(p))}<br><small class="text-muted fw-normal">per ${esc(p.unit)}</small></td>
      <td><input type="number" step="0.01" min="0.01" class="form-control form-dairy-control" data-std="${p.id}" value="${p.standard_b2b_price}" required></td>
      <td class="small text-muted">${own ? `${own} customer${own === 1 ? '' : 's'}` : 'None'}</td>
    </tr>`;
  }).join('');
  bootstrap.Modal.getOrCreateInstance(document.getElementById('modalStandardPrices')).show();
};

async function saveStandardPrices(e) {
  e.preventDefault();
  const changes = [];
  for (const input of document.querySelectorAll('#std-tbody input[data-std]')) {
    const p = stdGroup.items.find(x => x.id === parseInt(input.dataset.std));
    const price = parseFloat(input.value);
    if (!(price > 0)) {
      alert(`Enter a price more than 0 for ${sizeLabel(p)}.`);
      return;
    }
    if (Math.abs(price - p.standard_b2b_price) > 1e-9) changes.push([p, price]);
  }
  if (!changes.length) {
    bootstrap.Modal.getInstance(document.getElementById('modalStandardPrices')).hide();
    return;
  }
  const messages = [];
  try {
    for (const [p, price] of changes) messages.push((await DairyAPI.setStandardPrice(p.id, price)).message);
  } catch (err) {
    alert('Could not change price: ' + err.message + (messages.length ? '\n\nSaved before the error:\n' + messages.join('\n') : ''));
    await afterPriceChange();
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById('modalStandardPrices')).hide();
  alert(messages.join('\n'));
  await afterPriceChange();
}

// One customer's rates for every product size. productId: the size to put the cursor on.
let ratesCustomer = null;
let ratesRows = [];
window.openPricingModal = async function(customerId, productId = null) {
  const customer = customersCache.find(c => c.id === customerId);
  try {
    ratesRows = await DairyAPI.getCustomPricing(customerId);
  } catch (err) {
    alert('Could not load rates: ' + err.message);
    return;
  }
  ratesCustomer = { id: customerId, name: customer ? customer.business_name : (ratesRows[0] || {}).customer_name || '' };
  document.getElementById('rates-customer-name').innerText =
    `${ratesCustomer.name}${customer ? ' • ' + customer.customer_code : ''}`;
  const search = document.getElementById('rates-search');
  search.value = '';
  search.classList.toggle('d-none', ratesRows.length <= 10);
  renderRatesRows();
  bootstrap.Modal.getOrCreateInstance(document.getElementById('modalCustomerRates')).show();
  if (productId) {
    setTimeout(() => document.querySelector(`#rates-tbody input[data-rate="${productId}"]`)?.focus(), 400);
  }
};

function renderRatesRows() {
  const groups = priceGroups(ratesRows);
  document.getElementById('rates-tbody').innerHTML = groups.length ? groups.map(g => {
    const hasSizes = g.items.length > 1 || g.items.some(r => r.variant_name);
    const rows = g.items.map(r => `
      <tr data-name="${esc((g.name + ' ' + r.product_name).toLowerCase())}">
        <td class="${hasSizes ? 'ps-4' : 'fw-semibold'}">${esc(hasSizes ? sizeLabel(r) : r.product_name)}<br><small class="text-muted fw-normal">per ${esc(r.unit)}</small></td>
        <td class="text-end text-muted text-nowrap">${money2(r.standard_b2b_price)}</td>
        <td><input type="number" step="0.01" min="0.01" class="form-control form-control-sm form-dairy-control" data-rate="${r.product_id}"
             value="${r.is_custom ? r.custom_price : ''}" placeholder="${r.standard_b2b_price.toFixed(2)}" oninput="rateInputChanged(this)"></td>
        <td class="small text-nowrap" data-diff="${r.product_id}"></td>
        <td class="text-end">${r.is_custom ? `<button type="button" class="btn btn-sm btn-link text-decoration-none p-0" onclick="clearRate(${r.product_id})" title="Use the standard price">Standard</button>` : ''}</td>
      </tr>`).join('');
    return (hasSizes ? `<tr class="rate-group-row" data-group="${esc(g.name.toLowerCase())}"><td colspan="5">${esc(g.name)}</td></tr>` : '') + rows;
  }).join('') : '<tr><td colspan="5" class="text-center text-muted py-4">No products on sale.</td></tr>';
  document.querySelectorAll('#rates-tbody input[data-rate]').forEach(rateInputChanged);
}

// Live difference from the standard price, and a mark on changed rates
window.rateInputChanged = function(input) {
  const r = ratesRows.find(x => x.product_id === parseInt(input.dataset.rate));
  const value = input.value.trim() === '' ? null : parseFloat(input.value);
  const cell = document.querySelector(`#rates-tbody [data-diff="${r.product_id}"]`);
  if (value === null) cell.innerHTML = '<span class="badge bg-secondary-subtle text-secondary">Standard price</span>';
  else if (!(value > 0)) cell.innerHTML = '<span class="text-danger">Enter more than 0</span>';
  else {
    const diff = r.standard_b2b_price - value;
    cell.innerHTML = diff > 0 ? `<span class="badge bg-success-subtle text-success">₹${diff.toFixed(2)} less</span>`
      : diff < 0 ? `<span class="badge bg-warning-subtle text-warning">₹${Math.abs(diff).toFixed(2)} more</span>`
      : '<span class="badge bg-secondary-subtle text-secondary">Same as standard</span>';
  }
  input.classList.toggle('rate-changed', rateChange(r, value) !== undefined);
  const n = ratesChanges().length;
  document.getElementById('rates-changes').innerText = n ? `${n} change${n === 1 ? '' : 's'} not saved` : '';
};

window.clearRate = function(productId) {
  const input = document.querySelector(`#rates-tbody input[data-rate="${productId}"]`);
  input.value = '';
  rateInputChanged(input);
};

// undefined: no change; null: back to the standard price; a number: the new own rate
function rateChange(r, value) {
  if (value === null) return r.is_custom ? null : undefined;
  if (!(value > 0)) return undefined;
  if (r.is_custom) return Math.abs(value - r.custom_price) > 1e-9 ? value : undefined;
  return Math.abs(value - r.standard_b2b_price) > 1e-9 ? value : undefined;
}

function ratesChanges() {
  const out = [];
  document.querySelectorAll('#rates-tbody input[data-rate]').forEach(input => {
    const r = ratesRows.find(x => x.product_id === parseInt(input.dataset.rate));
    const value = input.value.trim() === '' ? null : parseFloat(input.value);
    const change = rateChange(r, value);
    if (change !== undefined) out.push([r, change]);
  });
  return out;
}

async function saveCustomerRates(e) {
  e.preventDefault();
  const bad = [...document.querySelectorAll('#rates-tbody input[data-rate]')]
    .find(i => i.value.trim() !== '' && !(parseFloat(i.value) > 0));
  if (bad) {
    alert('Enter a rate more than 0, or leave it blank for the standard price.');
    bad.focus();
    return;
  }
  const changes = ratesChanges();
  if (!changes.length) {
    bootstrap.Modal.getInstance(document.getElementById('modalCustomerRates')).hide();
    return;
  }
  const btn = document.getElementById('rates-save');
  btn.disabled = true;
  let repriced = 0;
  let saved = 0;
  try {
    for (const [r, price] of changes) {
      repriced += (await DairyAPI.setCustomerPrice(ratesCustomer.id, r.product_id, price)).orders_repriced || 0;
      saved += 1;
    }
  } catch (err) {
    alert(`Could not save all rates: ${err.message}` + (saved ? `\n${saved} rate(s) were saved before the error.` : ''));
    btn.disabled = false;
    await afterPriceChange();
    return;
  }
  btn.disabled = false;
  bootstrap.Modal.getInstance(document.getElementById('modalCustomerRates')).hide();
  alert(`${ratesCustomer.name}: ${saved} rate${saved === 1 ? '' : 's'} saved.` +
    (repriced ? ` Updated ${repriced} upcoming order(s) that are not dispatched yet.` : '') +
    ' Delivered milk keeps the old rate.');
  await afterPriceChange();
}

// Daily dispatch (Orders page)
function dispatchDate() {
  return document.getElementById('orders-date').value;
}

function prettyDay(iso) {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
}

window.dispatchOrders = async function() {
  const day = dispatchDate();
  const s = ordersSummary;
  let force = false;
  if (s && s.date === day && s.customers_can_order) {
    const until = new Date(s.order_deadline).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
    if (!confirm(`Customers can still order for ${prettyDay(day)} until ${until}.\nIf you dispatch now, their orders are locked.\n\nDispatch anyway?`)) return;
    force = true;
  } else if (!confirm(`Dispatch all confirmed orders for ${prettyDay(day)}?\nNobody can change these orders after dispatch.`)) {
    return;
  }
  const out = document.getElementById('dispatch-result');
  try {
    const res = await DairyAPI.dispatchOrders(day, force);
    const amount = res.orders_dispatched.reduce((sum, o) => sum + (o.amount || 0), 0);
    let html = res.orders_dispatched.length
      ? `<span class="text-success">Dispatched ${res.orders_dispatched.length} orders (${inr(amount)})` +
        (res.trips_created.length ? ` on new trips ${esc(res.trips_created.join(', '))}` : '') + '.</span>'
      : '<span class="text-muted">Nothing new to dispatch for this date.</span>';
    if (res.skipped.length) {
      html += '<br><span class="text-danger">Not dispatched: ' +
        res.skipped.map(x => `${esc(x.customer)} (${esc(x.reason)})`).join(', ') + '</span>';
    }
    out.innerHTML = html;
    await loadOrdersTable();
    await loadTransportTrips();
  } catch (err) {
    out.innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  }
};

window.shiftOrdersDay = function(delta) {
  const input = document.getElementById('orders-date');
  const d = new Date(input.value + 'T00:00:00');
  d.setDate(d.getDate() + delta);
  input.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  onOrdersDayChange();
};

async function onOrdersDayChange() {
  document.getElementById('ao-date').value = dispatchDate();
  document.getElementById('dispatch-result').innerHTML = '';
  await loadOrdersTable();
  showCurrentOrder();
}

function fillOrderCustomers() {
  const select = document.getElementById('ao-customer');
  if (!select) return;
  const keep = select.value;
  select.innerHTML = customersCache.filter(c => c.is_active)
    .map(c => `<option value="${c.id}">${esc(c.business_name)} (${esc(c.customer_code)})</option>`).join('');
  if (keep && [...select.options].some(o => o.value === keep)) select.value = keep;
}

// One quantity box per product on sale (plus any switched-off product already on this order)
const WHOLE_UNITS = ['pcs', 'packet', 'box', 'pouch', 'bottle'];
function renderOrderItemInputs(currentItems = []) {
  const box = document.getElementById('ao-items');
  const current = Object.fromEntries(currentItems.map(i => [i.product_id, i]));
  const list = productsCache.map(p => ({ id: p.id, name: p.product_name, unit: p.unit }));
  currentItems.forEach(i => {
    if (!list.some(p => p.id === i.product_id)) list.push({ id: i.product_id, name: i.product_name + ' (off sale)', unit: i.unit });
  });
  box.innerHTML = list.map(p => {
    const whole = WHOLE_UNITS.includes(p.unit);
    const val = current[p.id] ? current[p.id].quantity : '';
    return `<div class="col-6 col-md-4">
        <label class="form-label text-muted small mb-1" for="ao-p-${p.id}">${esc(p.name)} <span class="text-dim">(${esc(p.unit)})</span></label>
        <input type="number" id="ao-p-${p.id}" data-product-id="${p.id}" class="form-control form-control-sm form-dairy-control ao-qty"
          min="0" step="${whole ? 1 : 'any'}" value="${val}" placeholder="0" inputmode="decimal">
      </div>`;
  }).join('');
}

function orderFormItems() {
  return [...document.querySelectorAll('#ao-items .ao-qty')].map(inp => ({
    product_id: parseInt(inp.dataset.productId), quantity: parseFloat(inp.value) || 0
  }));
}

// Show the chosen customer's current order for the chosen day, and prefill the quantities
async function showCurrentOrder() {
  const out = document.getElementById('ao-current');
  const customerId = parseInt(document.getElementById('ao-customer').value);
  const day = document.getElementById('ao-date').value;
  if (!customerId || !day) {
    out.innerHTML = '';
    renderOrderItemInputs();
    return;
  }
  try {
    const list = await DairyAPI.getOrders({ customer_id: customerId, order_date: day });
    if (document.getElementById('ao-customer').value !== String(customerId) || document.getElementById('ao-date').value !== day) return;
    const o = list[0];
    if (!o || o.status === 'cancelled') {
      out.innerHTML = o ? 'This day\'s order was cancelled. Enter quantities to order again.' : 'No order for this day yet.';
      renderOrderItemInputs();
    } else {
      out.innerHTML = `Current order: <b>${esc(o.what)}</b> • ${inr(o.total_amount)} • ${esc(o.status.replace(/_/g, ' '))}` +
        (['confirmed', 'created'].includes(o.status) ? '' : ' • <span class="text-warning">already dispatched, cannot be changed</span>');
      renderOrderItemInputs(o.items.map(i => ({ product_id: i.product_id, product_name: i.product_name, unit: i.unit, quantity: i.quantity })));
    }
  } catch (err) {
    out.innerHTML = '';
  }
}

// Customer claims
let claimsCache = [];
let currentClaim = null;

async function setupClaimsAndDispatch() {
  const now = new Date();
  const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  document.getElementById('ao-date').value = todayIso;
  fillOrderCustomers();
  document.getElementById('orders-date').addEventListener('change', onOrdersDayChange);
  document.getElementById('ao-customer').addEventListener('change', showCurrentOrder);
  document.getElementById('ao-date').addEventListener('change', showCurrentOrder);
  document.getElementById('orders-search').addEventListener('input', renderOrdersTable);
  document.getElementById('orders-status').addEventListener('change', renderOrdersTable);
  showCurrentOrder();
  // Admin enters / changes / cancels an order (customers who call after the cut-off)
  document.getElementById('form-admin-order').addEventListener('submit', async (e) => {
    e.preventDefault();
    const out = document.getElementById('ao-result');
    const items = orderFormItems();
    if (items.some(i => i.quantity < 0)) {
      out.innerHTML = '<span class="text-danger">Quantities cannot be negative.</span>';
      return;
    }
    if (!items.some(i => i.quantity > 0) && !confirm("All quantities are 0: this cancels the customer's order for that day. Continue?")) return;
    try {
      const res = await DairyAPI.createOrder({
        customer_id: parseInt(document.getElementById('ao-customer').value),
        delivery_date: document.getElementById('ao-date').value,
        items
      });
      out.innerHTML = res.order_status === 'cancelled'
        ? `<span class="text-warning">Order ${esc(res.order_number)} cancelled.</span>`
        : `<span class="text-success">Saved ${esc(res.order_number)}: ${esc(res.what || '')}, ₹${Number(res.total_amount).toLocaleString('en-IN')}.</span>` +
          (res.credit_warning ? `<br><span class="text-danger">${esc(res.credit_warning)}</span>` : '');
      await loadOrdersTable();
      showCurrentOrder();
    } catch (err) {
      out.innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
    }
  });
  document.getElementById('claims-filter').addEventListener('change', loadClaims);
  document.getElementById('claims-search').addEventListener('input', renderClaims);
  await loadClaims();
}

async function updateClaimsBadge() {
  try {
    const { pending } = await DairyAPI.claimsSummary();
    const badge = document.getElementById('nav-claims-count');
    badge.innerText = pending;
    badge.classList.toggle('d-none', !pending);
  } catch (err) {
    console.error('Failed to load claims count:', err);
  }
}

async function loadClaims() {
  const tbody = document.getElementById('claims-tbody');
  updateClaimsBadge();
  try {
    claimsCache = await DairyAPI.getClaims(document.getElementById('claims-filter').value || null);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-danger">Could not load claims: ${esc(err.message)}</td></tr>`;
    return;
  }
  renderClaims();
}

// Admin wording for how an approved claim was settled (settlement_text is worded for the customer)
function claimSettlementAdmin(c) {
  if (c.status !== 'approved') return '';
  const how = { cash: 'cash', upi: 'UPI', bank_transfer: 'bank transfer' }[c.refund_method] || '';
  if (c.settlement === 'refund') return how ? `Refunded by ${how}` : 'Refunded';
  if (c.settlement === 'credit_note' || c.settlement === 'bill') return 'Deducted from bill';
  return 'To be deducted in next bill';
}

function renderClaims() {
  const tbody = document.getElementById('claims-tbody');
  const term = document.getElementById('claims-search').value.trim().toLowerCase();
  const rows = claimsCache.filter(c => !term || c.customer_name.toLowerCase().includes(term) ||
    c.claim_number.toLowerCase().includes(term) || (c.customer_code || '').toLowerCase().includes(term));
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">${claimsCache.length ? 'No claims match.' : 'No claims here.'}</td></tr>`;
    return;
  }
  const money = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  const badge = (c) => c.status === 'pending' ? 'bg-warning text-dark' : (c.status === 'approved' ? 'bg-success' : 'bg-secondary');
  tbody.innerHTML = rows.map(c => `
    <tr>
      <td class="font-monospace small fw-bold text-nowrap">${esc(c.claim_number)}</td>
      <td class="fw-bold">${esc(c.customer_name)}<br><small class="text-muted">${esc(c.customer_code)}</small></td>
      <td class="text-nowrap">${esc(c.issue_date)}<br><small class="text-muted">reported ${esc(new Date(c.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }))}</small></td>
      <td>${esc(c.reason_label)}${c.photo_ids.length ? ` <i class="bi bi-image text-info" title="${c.photo_ids.length} photo(s)"></i>` : ''}</td>
      <td class="text-end text-nowrap">${fmtQty(c.claimed_qty)} ${esc(c.unit)}<br><small class="text-muted">${esc(c.product_name)}</small>${c.status === 'approved' ? `<br><small class="text-success">approved ${fmtQty(c.approved_qty)} ${esc(c.unit)}</small>` : ''}</td>
      <td class="text-end text-nowrap">${c.status === 'approved'
        ? `<b>${money(c.credit_amount)}</b>`
        : c.status === 'pending' ? `<span class="text-muted">≈ ${money(c.claimed_qty * c.rate)}</span>` : '<span class="text-muted">-</span>'}</td>
      <td><span class="badge ${badge(c)}">${c.status.toUpperCase()}</span>
        ${c.status === 'approved' ? `<br><small class="text-muted">${esc(claimSettlementAdmin(c))}</small>` : ''}</td>
      <td><button class="btn btn-sm ${c.status === 'pending' ? 'btn-dairy-primary' : 'btn-outline-secondary'}" onclick="openClaim(${c.id})">
        ${c.status === 'pending' ? 'Review' : 'View'}</button></td>
    </tr>`).join('');
}

function photoThumbs(ids) {
  return ids.map(id => `
    <a href="${DairyAPI.fileUrl(id)}" target="_blank" rel="noopener" title="Open full size">
      <img src="${DairyAPI.fileUrl(id)}" alt="Photo" class="rounded border" style="width: 140px; height: 110px; object-fit: cover;">
    </a>`).join('');
}

window.openClaim = async function(claimId) {
  let c;
  try {
    c = await DairyAPI.getClaim(claimId);
  } catch (err) {
    alert('Could not load claim: ' + err.message);
    return;
  }
  currentClaim = c;
  document.getElementById('claim-title').innerText = `${c.claim_number} • ${c.customer_name}`;
  const when = (iso) => iso ? new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-';
  document.getElementById('claim-subtitle').innerText = `Reported ${when(c.created_at)}`;
  document.getElementById('claim-info').innerHTML = `
    <table class="table table-sm mb-2">
      <tr><th class="text-muted fw-normal">Delivery date</th><td class="fw-bold">${esc(c.issue_date)}</td></tr>
      <tr><th class="text-muted fw-normal">Problem</th><td class="fw-bold">${esc(c.reason_label)}</td></tr>
      <tr><th class="text-muted fw-normal">Product</th><td class="fw-bold">${esc(c.product_name)}</td></tr>
      <tr><th class="text-muted fw-normal">Claimed</th><td class="fw-bold text-danger">${fmtQty(c.claimed_qty)} ${esc(c.unit)}</td></tr>
      <tr><th class="text-muted fw-normal">Customer says</th><td>${esc(c.description)}</td></tr>
    </table>
    ${c.photo_ids.length ? '' : '<div class="text-muted small">No photos attached.</div>'}`;
  document.getElementById('claim-photos').innerHTML = photoThumbs(c.photo_ids);

  const del = c.deliveries || [];
  document.getElementById('claim-delivery').innerHTML = `
    <table class="table table-sm mb-2">
      <tr><th class="text-muted fw-normal">${esc(c.product_name)} ordered that day</th><td class="fw-bold">${fmtQty(c.ordered_qty)} ${esc(c.unit)}</td></tr>
      <tr><th class="text-muted fw-normal">Delivered (per delivery boy)</th><td class="fw-bold">${fmtQty(c.delivered_qty)} ${esc(c.unit)}</td></tr>
      <tr><th class="text-muted fw-normal">Other claims for it that day</th><td>${fmtQty(c.other_claims_qty)} ${esc(c.unit)}</td></tr>
    </table>
    ${(c.day_products || []).length > 1 ? `<div class="small text-muted mb-2">Everything delivered that day: ${c.day_products.map(p =>
      `${esc(p.product_name)} ${fmtQty(p.delivered)} of ${fmtQty(p.ordered)} ${esc(p.unit)}`).join(' • ')}</div>` : ''}
    ${del.length ? del.map(d => `
      <div class="glass-panel-subtle p-2 mb-2 small">
        <div><b>${esc(d.driver_name || 'Delivery boy')}</b> • ${esc(when(d.delivered_at))} • ${esc(d.status.replace(/_/g, ' '))}</div>
        <div>Status: ${esc(d.status.replace(/_/g, ' '))}${d.shortage_reason && d.shortage_reason !== 'none' ? ` • shortage reason at delivery: ${esc(d.shortage_reason.replace(/_/g, ' '))}` : ''}</div>
        <div>Received by: ${esc(d.delivered_to || '-')}</div>
        <div class="d-flex flex-wrap gap-2 mt-2 align-items-start">
          ${photoThumbs(d.photo_ids) || '<span class="text-warning">No delivery photo</span>'}
          ${d.signature ? `<img src="${d.signature}" alt="Customer signature" class="rounded border bg-white" style="height: 110px;">` : '<span class="text-warning">No signature</span>'}
        </div>
      </div>`).join('') : '<div class="text-warning small">No delivery record found for this day.</div>'}`;

  const decision = document.getElementById('claim-decision');
  if (c.status === 'pending') {
    const maxQty = Math.min(c.claimed_qty, Math.max(0, c.delivered_qty - c.other_claims_qty));
    let billNote = c.billed_in
      ? `This day is already billed in <b>${esc(c.billed_in)}</b>. That bill will be reduced now and will show the original and the claimed quantity for ${esc(c.issue_date)}.`
      : 'This day is not billed yet. The amount will be deducted when the bill for this day is generated.';
    if (c.billed_in && c.billed_balance_due === 0) {
      billNote += ' <span class="text-warning">This bill is already fully paid. The amount will be adjusted in the customer&#39;s other unpaid bills (or kept as advance for the next bill). <b>If you have already given or will give this money back to the customer (cash / UPI), choose Refund separately</b>, otherwise it is counted twice.</span>';
    }
    decision.innerHTML = `
      <div class="row g-2 align-items-end">
        <div class="col-md-3">
          <label class="form-label text-muted small mb-1">Approve ${esc(c.unit)} (max ${fmtQty(maxQty)})</label>
          <input type="number" id="claim-approve-qty" class="form-control form-dairy-control" min="0" step="${WHOLE_UNITS.includes(c.unit) ? 1 : 'any'}" max="${maxQty}" value="${maxQty}">
          <small class="text-dim">Rate ₹${c.rate}/L • Credit <b id="claim-credit">₹${(maxQty * c.rate).toFixed(2)}</b></small>
        </div>
        <div class="col-md-9">
          <label class="form-label text-muted small mb-1">How to settle</label>
          <div class="d-flex flex-wrap gap-3">
            <div class="form-check">
              <input class="form-check-input" type="radio" name="claim-mode" id="claim-mode-bill" value="bill" checked>
              <label class="form-check-label fw-bold" for="claim-mode-bill">Deduct from bill</label>
            </div>
            <div class="form-check">
              <input class="form-check-input" type="radio" name="claim-mode" id="claim-mode-refund" value="refund">
              <label class="form-check-label fw-bold" for="claim-mode-refund">Refund separately</label>
            </div>
          </div>
          <small class="text-dim d-block" id="claim-mode-help">${billNote}</small>
        </div>
        <div class="col-12 d-none" id="claim-refund-fields">
          <div class="row g-2">
            <div class="col-md-3">
              <label class="form-label text-muted small mb-1">Refund paid on</label>
              <input type="date" id="claim-refund-date" class="form-control form-dairy-control" min="${esc(c.issue_date)}" max="${isoLocal(new Date())}" value="${isoLocal(new Date())}">
            </div>
            <div class="col-md-3">
              <label class="form-label text-muted small mb-1">Refund paid by</label>
              <select id="claim-refund-method" class="form-select form-dairy-control">
                <option value="">Choose...</option>
                <option value="cash">Cash</option>
                <option value="upi">UPI</option>
                <option value="bank_transfer">Bank transfer</option>
              </select>
            </div>
            <div class="col-md-6">
              <label class="form-label text-muted small mb-1">Reference / UTR (optional)</label>
              <input type="text" id="claim-refund-ref" class="form-control form-dairy-control" maxlength="100">
            </div>
          </div>
        </div>
        <div class="col-md-8">
          <label class="form-label text-muted small mb-1">Note to customer (required when rejecting)</label>
          <input type="text" id="claim-note" class="form-control form-dairy-control" maxlength="300">
        </div>
        <div class="col-md-4 d-flex gap-2">
          <button class="btn btn-success flex-grow-1" onclick="decideClaim('approve')"><i class="bi bi-check-lg"></i> Approve</button>
          <button class="btn btn-outline-danger flex-grow-1" onclick="decideClaim('reject')"><i class="bi bi-x-lg"></i> Reject</button>
        </div>
      </div>`;
    document.getElementById('claim-approve-qty').addEventListener('input', (e) => {
      document.getElementById('claim-credit').innerText = `₹${((parseFloat(e.target.value) || 0) * c.rate).toFixed(2)}`;
    });
    document.querySelectorAll('input[name="claim-mode"]').forEach(r => r.addEventListener('change', () => {
      const refund = document.getElementById('claim-mode-refund').checked;
      document.getElementById('claim-refund-fields').classList.toggle('d-none', !refund);
      document.getElementById('claim-mode-help').innerHTML = refund
        ? 'Pay the money back to the customer yourself. The bill stays unchanged; the claim is shown on it as refunded.'
        : billNote;
    }));
  } else {
    decision.innerHTML = `
      <div class="alert ${c.status === 'approved' ? 'alert-success' : 'alert-secondary'} mb-0">
        <b>${c.status.toUpperCase()}</b>
        ${c.status === 'approved' ? ` • ${fmtQty(c.approved_qty)} ${esc(c.unit)} ${esc(c.product_name)} × ₹${c.rate} = ₹${c.credit_amount.toFixed(2)} • ${esc(claimSettlementAdmin(c))}` : ''}
        ${c.status === 'approved' && c.billed_in && c.settlement !== 'refund' ? `<br>Bill: ${esc(c.billed_in)}` : ''}
        ${c.refund_reference ? `<br>Refund reference: ${esc(c.refund_reference)}` : ''}
        ${c.reviewed_at ? `<br><small>Decided by ${esc(c.reviewed_by_name || 'admin')} on ${esc(when(c.reviewed_at))}</small>` : ''}
        ${c.admin_note ? `<br>Note: ${esc(c.admin_note)}` : ''}
        <div class="mt-2">
          <button class="btn btn-sm btn-outline-danger" onclick="undoClaimDecision()"><i class="bi bi-arrow-counterclockwise me-1"></i>Undo decision</button>
        </div>
      </div>`;
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById('modalClaim')).show();
};

window.undoClaimDecision = async function() {
  const c = currentClaim;
  const amount = `₹${Number(c.credit_amount || 0).toFixed(2)}`;
  let effect;
  if (c.status === 'rejected') {
    effect = 'The claim will be pending again so you can decide it afresh.';
  } else if (c.settlement === 'refund') {
    effect = `The refund of ${amount} will be removed from the records.
IMPORTANT: if you already gave this money to the customer, collect it back yourself.`;
  } else if (c.settlement === 'credit_note' || c.settlement === 'bill') {
    effect = `${amount} will be added back to bill ${c.billed_in || ''} and to the customer's outstanding.`;
  } else {
    effect = `It will no longer be deducted from the next bill (${amount}).`;
  }
  const reason = prompt(`Undo the decision on ${c.claim_number}?

${effect}
The claim becomes pending again.

Why are you undoing it?`);
  if (reason === null) return;
  if (!reason.trim()) {
    alert('Please write a reason.');
    return;
  }
  try {
    await DairyAPI.undoClaim(c.id, reason.trim());
    await openClaim(c.id);
    await loadClaims();
    await loadCustomerTable();
    await loadBills();
  } catch (err) {
    alert('Could not undo: ' + err.message);
  }
};

window.decideClaim = async function(action) {
  const c = currentClaim;
  const note = document.getElementById('claim-note').value.trim();
  try {
    if (action === 'approve') {
      const qty = parseFloat(document.getElementById('claim-approve-qty').value);
      if (!(qty > 0)) {
        alert('Enter the quantity to approve, or reject the claim.');
        return;
      }
      const mode = document.getElementById('claim-mode-refund').checked ? 'refund' : 'bill';
      const method = document.getElementById('claim-refund-method').value;
      const ref = document.getElementById('claim-refund-ref').value.trim();
      const refundDate = document.getElementById('claim-refund-date').value;
      if (mode === 'refund' && !method) {
        alert('Choose how the refund was paid (cash, UPI or bank transfer).');
        return;
      }
      if (mode === 'refund' && !refundDate) {
        alert('Choose the date the refund was paid.');
        return;
      }
      const amount = `₹${(qty * c.rate).toFixed(2)}`;
      const what = mode === 'refund'
        ? `Refund ${amount} to ${c.customer_name} by ${method.replace('_', ' ')} on ${refundDate} (bill will not change)?`
        : `Deduct ${qty} L (${amount}) from ${c.customer_name}'s bill${c.billed_in ? ` ${c.billed_in}` : ''}?`;
      if (!confirm(what)) return;
      await DairyAPI.approveClaim(c.id, qty, note || null, mode, mode === 'refund' ? method : null, ref || null,
        mode === 'refund' ? refundDate : null);
    } else {
      if (!note) {
        alert('Write a reason so the customer knows why the claim was rejected.');
        return;
      }
      if (!confirm(`Reject claim ${c.claim_number}?`)) return;
      await DairyAPI.rejectClaim(c.id, note);
    }
    await openClaim(c.id);
    await loadClaims();
    await loadCustomerTable();
  } catch (err) {
    alert('Could not save decision: ' + err.message);
  }
};

// 6. Orders Table (one delivery day)
let ordersSummary = null;

async function loadOrdersTable() {
  const tbody = document.getElementById('orders-tbody');
  if (!tbody) return;
  const dateInput = document.getElementById('orders-date');
  if (!dateInput.value) {
    const now = new Date();
    dateInput.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }
  const day = dateInput.value;
  try {
    const [orders, summary] = await Promise.all([
      DairyAPI.getOrders({ order_date: day }), DairyAPI.getOrdersDaySummary(day)
    ]);
    if (dateInput.value !== day) return; // user moved to another day meanwhile
    ordersCache = orders;
    ordersSummary = summary;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-danger">Could not load orders: ${esc(err.message)}</td></tr>`;
    return;
  }
  renderOrdersSummary();
  renderOrdersTable();
}

function renderOrdersSummary() {
  const s = ordersSummary;
  const num = (n) => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  const c = s.status_counts;
  const card = (label, value, sub, cls = '') => `
    <div class="col-6 col-lg-3">
      <div class="glass-panel p-3 h-100">
        <div class="text-muted small">${label}</div>
        <div class="h5 fw-bold mb-0 ${cls}">${value}</div>
        <div class="small text-muted">${sub}</div>
      </div>
    </div>`;
  const until = new Date(s.order_deadline).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  document.getElementById('orders-summary').innerHTML =
    card('Customers ordered', `${s.customers_ordered} / ${s.active_customers}`,
      s.cancelled ? `${s.cancelled} cancelled` : 'active customers') +
    card('Milk ordered', `${num(s.total_litres)} L`, `₹${num(s.total_amount)} at order rates (all products)`) +
    card('Delivery', `${c.delivered || 0} delivered`,
      `${c.out_for_delivery || 0} out for delivery • ${s.waiting_dispatch} not dispatched`,
      s.waiting_dispatch ? 'text-warning' : 'text-success') +
    card('Customer ordering', s.customers_can_order ? 'Open' : 'Closed',
      s.customers_can_order ? `until ${until}` : `closed at ${until}`,
      s.customers_can_order ? 'text-success' : 'text-muted') +
    ((s.products || []).length ? `
      <div class="col-12">
        <div class="d-flex flex-wrap gap-2 small">${s.products.map(p => `
          <span class="badge bg-light text-dark border fw-normal py-2 px-3"><b>${esc(p.product_name)}</b>:
            ${num(p.quantity)} ${esc(p.unit)} • ${p.customers} customer(s) • ₹${num(p.amount)}</span>`).join('')}</div>
      </div>` : '') +
    (s.not_ordered.length ? `
      <div class="col-12">
        <div class="small"><span class="text-muted">No order from:</span>
          ${s.not_ordered.map(x => `<span class="badge bg-secondary-subtle text-secondary me-1">${esc(x.name)}</span>`).join('')}</div>
      </div>` : '');

  document.getElementById('dispatch-day-label').innerText = prettyDay(s.date);
  document.getElementById('dispatch-hint').innerHTML = s.waiting_dispatch
    ? `<span class="text-warning">${s.waiting_dispatch} order(s) waiting for dispatch</span>`
    : '<span class="text-muted">No orders waiting for dispatch</span>';
  renderDispatchPanel(s);
}

const clock12 = (iso) => new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' });

function renderDispatchPanel(s) {
  const d = s.dispatch;
  if (!d) return;
  const when = new Date(d.dispatch_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: 'numeric', minute: '2-digit' });
  document.getElementById('disp-time').innerText = clock12(d.dispatch_at);
  let html;
  if (d.on_hold) {
    html = `<div class="alert alert-warning py-2 mb-0"><b><i class="bi bi-pause-circle me-1"></i>Dispatch on hold</b> — ${esc(d.hold_note)}<br>
      <small>${d.customers_told ? 'Customers with orders have been told.' : `Customers will be told at ${esc(when)} if the hold is still on.`}
      Remove the hold to send the milk out${d.time_passed ? ' now' : ''}.</small></div>`;
  } else if (d.dispatched_orders && !d.waiting_orders) {
    html = `<span class="text-success"><i class="bi bi-check-circle me-1"></i>${d.dispatched_orders} order(s) sent to the delivery boys` +
      (d.auto_dispatched_at ? ` automatically at ${esc(clock12(d.auto_dispatched_at))}` : '') + '.</span>';
  } else if (d.time_passed && d.waiting_orders) {
    html = `<span class="text-warning"><i class="bi bi-hourglass-split me-1"></i>${d.waiting_orders} order(s) waiting — they go out within a minute.` +
      ` If they stay here, check the customer's route and delivery boy.</span>`;
  } else {
    html = `<span class="text-info"><i class="bi bi-clock me-1"></i>Automatic dispatch at <b>${esc(when)}</b>` +
      (d.waiting_orders ? ` • ${d.waiting_orders} order(s) will go out` : '') + '.</span>';
  }
  document.getElementById('disp-status').innerHTML = html;

  const box = document.getElementById('disp-hold-box');
  box.classList.toggle('d-none', !d.can_hold);
  const note = document.getElementById('disp-hold-note');
  if (document.activeElement !== note) note.value = d.on_hold ? (d.hold_note || '') : '';
  document.getElementById('disp-hold-btn').innerHTML = d.on_hold
    ? '<i class="bi bi-pencil me-1"></i>Update note' : '<i class="bi bi-pause-circle me-1"></i>Hold dispatch';
  document.getElementById('disp-release-btn').classList.toggle('d-none', !d.on_hold);
  document.getElementById('dispatch-now-btn').disabled = d.on_hold;
}

window.holdDispatch = async function() {
  const day = dispatchDate();
  const note = document.getElementById('disp-hold-note').value.trim();
  if (!note) {
    alert('Write why the milk cannot be dispatched. Customers will see this note.');
    return;
  }
  const onHold = ordersSummary && ordersSummary.dispatch && ordersSummary.dispatch.on_hold;
  if (!onHold && !confirm(`Hold the automatic dispatch for ${prettyDay(day)}?\n\nThe delivery boys will not get these orders until you remove the hold. ` +
      `At dispatch time, customers with orders get this note:\n"${note}"`)) return;
  try {
    await DairyAPI.holdDispatch(day, note);
    document.getElementById('dispatch-result').innerHTML = `<span class="text-warning">Dispatch for ${esc(prettyDay(day))} is on hold.</span>`;
    await loadOrdersTable();
  } catch (err) {
    document.getElementById('dispatch-result').innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  }
};

window.releaseDispatchHold = async function() {
  const day = dispatchDate();
  const d = ordersSummary && ordersSummary.dispatch;
  if (!confirm(d && d.time_passed
    ? `Remove the hold for ${prettyDay(day)}?\nThe dispatch time has passed, so the orders go to the delivery boys right now.`
    : `Remove the hold for ${prettyDay(day)}?\nOrders will go out automatically at the dispatch time.`)) return;
  try {
    const res = await DairyAPI.releaseDispatchHold(day);
    const sent = res.dispatch && res.dispatch.orders_dispatched ? res.dispatch.orders_dispatched.length : 0;
    document.getElementById('dispatch-result').innerHTML = `<span class="text-success">Hold removed.` +
      (sent ? ` ${sent} order(s) sent to the delivery boys.` : '') + '</span>';
    await loadOrdersTable();
  } catch (err) {
    document.getElementById('dispatch-result').innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  }
};

window.setOrdersDayTomorrow = function() {
  const t = new Date();
  t.setDate(t.getDate() + 1);
  document.getElementById('orders-date').value = isoLocal(t);
  onOrdersDayChange();
};

window.downloadOrdersExcel = function() {
  window.location.href = DairyAPI.ordersExcelUrl(dispatchDate());
};

// ---------------- Products ----------------
// A product can have several sizes (500 ML, 1 L): each size is its own product with the same group_name.
let allProducts = [];
let productGroups = [];
const UNIT_LABEL = { L: 'Litre', kg: 'Kg', pcs: 'Piece', packet: 'Packet', box: 'Box', pouch: 'Pouch', bottle: 'Bottle' };
const PACK_UNITS = ['pouch', 'bottle', 'packet'];

async function loadProducts() {
  const tbody = document.getElementById('products-tbody');
  try {
    allProducts = await DairyAPI.getAllProducts();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-danger">${esc(err.message)}</td></tr>`;
    return;
  }
  // Order forms and pricing use the products on sale
  productsCache = allProducts.filter(p => p.is_active);
  document.getElementById('nav-product-count').innerText = productsCache.length;
  renderProducts();
  // The order form shows one box per product on sale: refresh it for the new list
  if (document.getElementById('ao-items')) showCurrentOrder();
}

function groupProducts(list) {
  const groups = new Map();
  list.forEach(p => {
    const key = (p.group_name || p.product_name).toLowerCase();
    if (!groups.has(key)) groups.set(key, { name: p.group_name || p.product_name, items: [] });
    groups.get(key).items.push(p);
  });
  return [...groups.values()].map(g => {
    g.items.sort((a, b) => (a.litres_in_unit || 0) - (b.litres_in_unit || 0) || a.id - b.id);
    g.first = g.items[0];
    g.hasSizes = g.items.some(p => p.variant_name);
    return g;
  });
}

function productRateCell(p) {
  return `${inr(p.standard_b2b_price)}/${esc(p.unit)}
    ${p.gst_rate ? `<br><small class="text-muted fw-normal">GST inside ${inr(p.gst_in_price)}</small>` : ''}`;
}

function productStatusCell(p) {
  return `<span class="badge ${p.is_active ? 'bg-success' : 'bg-secondary'}">${p.is_active ? 'ON SALE' : 'OFF'}</span>
    ${p.open_orders ? `<br><small class="text-muted">${p.open_orders} open order(s)</small>` : ''}`;
}

function productToggleButton(p) {
  return `<button class="btn btn-sm ${p.is_active ? 'btn-outline-danger' : 'btn-outline-success'}" onclick="toggleProduct(${p.id})">
    ${p.is_active ? 'Switch off' : 'Put on sale'}</button>`;
}

function renderProducts() {
  const showOff = document.getElementById('prod-show-off').checked;
  productGroups = groupProducts(allProducts);
  const tbody = document.getElementById('products-tbody');
  const visible = productGroups.map((g, gi) => ({ g, gi, items: g.items.filter(p => showOff || p.is_active) }))
    .filter(x => x.items.length);
  if (!visible.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">No products.</td></tr>';
    return;
  }
  tbody.innerHTML = visible.map(({ g, gi, items }) => {
    const f = g.first;
    if (!g.hasSizes) {
      const p = items[0];
      return `
      <tr class="${p.is_active ? '' : 'opacity-50'}">
        <td><div class="fw-bold">${esc(p.product_name)}</div>
          <small class="text-muted">${esc(p.category)}${p.pack_size ? ' • ' + esc(p.pack_size) : ''} • ${esc(p.sku)}</small></td>
        <td>${esc(UNIT_LABEL[p.unit] || p.unit)}</td>
        <td class="text-end fw-bold">${productRateCell(p)}</td>
        <td class="text-end">${p.gst_rate}%</td>
        <td class="text-end">${p.cost_price ? inr(p.cost_price) : '<span class="text-warning">not set</span>'}</td>
        <td class="text-end">${p.custom_rates}</td>
        <td>${productStatusCell(p)}</td>
        <td class="text-nowrap">
          <button class="btn btn-sm btn-outline-secondary" onclick="openProductModal(${gi})" title="Edit"><i class="bi bi-pencil"></i></button>
          ${productToggleButton(p)}
        </td>
      </tr>`;
    }
    return `
      <tr class="product-group-row">
        <td colspan="2"><div class="fw-bold">${esc(g.name)}</div>
          <small class="text-muted">${esc(f.category)} • ${g.items.length} size(s) • sold per ${esc((UNIT_LABEL[f.unit] || f.unit).toLowerCase())}</small></td>
        <td></td>
        <td class="text-end">${f.gst_rate}%</td>
        <td colspan="3"></td>
        <td class="text-nowrap">
          <button class="btn btn-sm btn-outline-secondary" onclick="openProductModal(${gi})" title="Edit product and sizes"><i class="bi bi-pencil"></i> Edit</button>
          <button class="btn btn-sm btn-outline-primary" onclick="openProductModal(${gi}, true)" title="Add a size"><i class="bi bi-plus-lg"></i> Size</button>
        </td>
      </tr>` + items.map(p => `
      <tr class="product-size-row ${p.is_active ? '' : 'opacity-50'}">
        <td class="ps-4"><span class="badge rounded-pill text-bg-light border me-1">${esc(p.variant_name || '-')}</span>
          <small class="text-muted">${esc(p.sku)}${p.litres_per_unit ? ` • ${qtyText(p.litres_per_unit)} L each` : ''}</small></td>
        <td>${esc(UNIT_LABEL[p.unit] || p.unit)}</td>
        <td class="text-end fw-bold">${productRateCell(p)}</td>
        <td></td>
        <td class="text-end">${p.cost_price ? inr(p.cost_price) : '<span class="text-warning">not set</span>'}</td>
        <td class="text-end">${p.custom_rates}</td>
        <td>${productStatusCell(p)}</td>
        <td class="text-nowrap">${productToggleButton(p)}</td>
      </tr>`).join('');
  }).join('');
}

function qtyText(n) {
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 3 });
}

window.openProductsView = function() {
  const link = document.querySelector('.nav-item-btn[data-target="view-products"]');
  if (link) link.click();
};

let productFormGroup = null;  // the group being edited, null for a new product

function sizeRowHtml(v) {
  const isNew = !v.id;
  return `
    <tr data-id="${v.id || ''}">
      <td><input class="form-control form-control-sm form-dairy-control ps-size" maxlength="50" placeholder="e.g. 500 ML" value="${esc(v.variant_name || '')}"></td>
      <td class="ps-litres-col"><input type="number" min="0" step="0.001" class="form-control form-control-sm form-dairy-control ps-litres" placeholder="e.g. 0.5" value="${v.litres_per_unit ?? ''}"></td>
      <td><input type="number" min="0.01" step="0.01" class="form-control form-control-sm form-dairy-control ps-price" required value="${v.standard_b2b_price ?? ''}"></td>
      <td><input type="number" min="0" step="0.01" class="form-control form-control-sm form-dairy-control ps-cost" value="${v.cost_price || ''}"></td>
      <td><input class="form-control form-control-sm form-dairy-control ps-sku" maxlength="50" placeholder="Auto" value="${esc(v.sku || '')}"></td>
      <td class="text-end">${isNew
        ? '<button type="button" class="btn btn-sm btn-link text-danger p-0" onclick="removeSizeRow(this)" title="Remove this size"><i class="bi bi-x-lg"></i></button>'
        : (v.is_active ? '' : '<span class="badge bg-secondary">OFF</span>')}</td>
    </tr>`;
}

window.addSizeRow = function(v = {}) {
  document.getElementById('prod-sizes').insertAdjacentHTML('beforeend', sizeRowHtml(v));
  updateSizeHints();
};

window.removeSizeRow = function(btn) {
  btn.closest('tr').remove();
  if (!document.querySelectorAll('#prod-sizes tr').length) addSizeRow();
  updateSizeHints();
};

function updateSizeHints() {
  const unit = document.getElementById('prod-unit').value;
  const packs = PACK_UNITS.includes(unit);
  document.querySelectorAll('.ps-litres-col').forEach(el => el.classList.toggle('d-none', !packs));
  const rows = document.querySelectorAll('#prod-sizes tr').length;
  document.getElementById('prod-sizes-note').innerText = rows > 1
    ? 'Customers see these sizes together under one product. Each size has its own rate and code.'
    : 'One size? Leave Size empty. Selling 500 ML and 1 L packs of this product? Add a row for each size.';
  document.getElementById('prod-unit-hint').innerText = packs
    ? `Rate is per ${UNIT_LABEL[unit].toLowerCase()}. Fill "Litres in 1" (0.5 for 500 ML) so milk totals are in litres.`
    : packsToLitres() ? 'Rate is per litre. Old orders, customer rates and claims change to litres; amounts stay the same.' : '';
}

// Editing a pack product (pouch etc.) that is being changed to litres
function packsToLitres() {
  const f = productFormGroup ? productFormGroup.first : null;
  return !!f && PACK_UNITS.includes(f.unit) && document.getElementById('prod-unit').value === 'L';
}

// Pack rates become litre rates (28.75 a 500 ML pouch = 57.50 a litre), and back again
function convertSizeRates() {
  if (!productFormGroup || !PACK_UNITS.includes(productFormGroup.first.unit)) return;
  const litres = packsToLitres();
  document.querySelectorAll('#prod-sizes tr').forEach(tr => {
    const p = allProducts.find(x => x.id === parseInt(tr.dataset.id));
    if (!p || !p.litres_per_unit) return;
    const per = litres ? p.litres_per_unit : 1;
    tr.querySelector('.ps-price').value = +(p.standard_b2b_price / per).toFixed(2);
    tr.querySelector('.ps-cost').value = p.cost_price ? +(p.cost_price / per).toFixed(2) : '';
  });
}

window.openProductModal = function(groupIndex, addSize = false) {
  const g = groupIndex === undefined || groupIndex === null ? null : productGroups[groupIndex];
  productFormGroup = g;
  const f = g ? g.first : null;
  const set = (k, v) => { document.getElementById(k).value = v ?? ''; };
  document.getElementById('prod-modal-title').innerText = g ? `Edit ${g.name}` : 'Add product';
  set('prod-name', g ? g.name : '');
  set('prod-category', f ? f.category : 'Milk');
  set('prod-unit', f ? f.unit : 'L');
  set('prod-gst', f ? String(f.gst_rate) : '0');
  if (f && !['0', '5', '12', '18', '28', '40'].includes(String(f.gst_rate))) {
    const sel = document.getElementById('prod-gst');
    sel.insertAdjacentHTML('beforeend', `<option value="${f.gst_rate}">${f.gst_rate}%</option>`);
    sel.value = String(f.gst_rate);
  }
  set('prod-hsn', f?.hsn_code);
  set('prod-sort', f ? f.sort_order : (productGroups.length + 1));
  set('prod-desc', f?.description);
  // A product already ordered keeps its unit (old bills use it); litres may only be renamed to packs,
  // and packs with their litres known may become litres (quantities and rates are converted)
  const ordered = g && g.items.some(p => p.times_ordered);
  const toLitres = !!ordered && PACK_UNITS.includes(f.unit) && g.items.every(p => p.litres_per_unit);
  const unitSel = document.getElementById('prod-unit');
  [...unitSel.options].forEach(o => {
    o.disabled = !!ordered && o.value !== f.unit && !(f.unit === 'L' && PACK_UNITS.includes(o.value))
      && !(toLitres && o.value === 'L');
  });
  document.getElementById('prod-unit-note').innerText = !ordered ? ''
    : f.unit === 'L' ? 'Already ordered: can only change to pouch / bottle / packet.'
    : toLitres ? 'Already ordered: can only change to Litre.' : 'Already ordered, unit is fixed.';
  document.getElementById('prod-group-names').innerHTML = productGroups.filter(x => x !== g)
    .map(x => `<option value="${esc(x.name)}">`).join('');
  document.getElementById('prod-sizes').innerHTML = '';
  (g ? g.items : [{}]).forEach(v => addSizeRow(v));
  if (addSize) addSizeRow();
  document.getElementById('prod-result').innerHTML = '';
  new bootstrap.Modal(document.getElementById('modalProduct')).show();
};

window.toggleProduct = async function(id) {
  const p = allProducts.find(x => x.id === id);
  if (p.is_active && !confirm(`Switch off ${p.product_name}?\nCustomers will not be able to order it. Orders already placed with it are still delivered and billed.`)) return;
  try {
    const res = await DairyAPI.setProductActive(id, !p.is_active);
    document.getElementById('products-result').innerHTML = `<span class="text-success">${esc(res.message)}</span>`;
    await loadProducts();
  } catch (err) {
    document.getElementById('products-result').innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  }
};

function setupProducts() {
  const nav = document.querySelector('.nav-item-btn[data-target="view-products"]');
  if (!nav) return;
  nav.addEventListener('click', loadProducts);
  document.getElementById('prod-show-off').addEventListener('change', renderProducts);
  document.getElementById('prod-unit').addEventListener('change', () => { convertSizeRates(); updateSizeHints(); });
  loadProducts();
  document.getElementById('form-product').addEventListener('submit', async (e) => {
    e.preventDefault();
    const val = (k) => document.getElementById(k).value.trim();
    const num = (el) => el.value.trim() === '' ? null : parseFloat(el.value);
    const packs = PACK_UNITS.includes(val('prod-unit'));
    const variants = [...document.querySelectorAll('#prod-sizes tr')].map(tr => ({
      id: parseInt(tr.dataset.id) || null,
      variant_name: tr.querySelector('.ps-size').value.trim() || null,
      litres_per_unit: packs ? num(tr.querySelector('.ps-litres')) : null,
      standard_b2b_price: num(tr.querySelector('.ps-price')),
      cost_price: num(tr.querySelector('.ps-cost')) || 0,
      sku: tr.querySelector('.ps-sku').value.trim() || null,
    }));
    const data = {
      product_name: val('prod-name'), category: val('prod-category') || 'Milk', unit: val('prod-unit'),
      gst_rate: parseFloat(val('prod-gst')) || 0, hsn_code: val('prod-hsn') || null,
      sort_order: parseInt(val('prod-sort')) || 0, description: val('prod-desc') || null, variants,
    };
    if (packs && variants.some(v => !v.litres_per_unit) && !confirm(
      'Some sizes have no "Litres in 1" filled in, so their milk is not counted in litre totals. Save anyway?')) return;
    const toLitres = packsToLitres();
    if (toLitres && !confirm(`Sell ${data.product_name} per litre?
` +
      'Old orders, customer rates and claims change to litres (2 pouches of 500 ML = 1 litre). Amounts stay the same. Bills already made do not change.')) return;
    const changed = toLitres ? [] : variants.filter(v => v.id).map(v => ({ v, old: allProducts.find(p => p.id === v.id) }))
      .filter(x => x.old && x.old.standard_b2b_price !== x.v.standard_b2b_price);
    if (changed.length && !confirm(changed.map(x =>
      `Change the rate of ${x.old.product_name} from ${inr(x.old.standard_b2b_price)} to ${inr(x.v.standard_b2b_price)}?`).join('\n') +
      '\nCustomers on the standard rate pay the new rate on orders not dispatched yet. Delivered orders keep the old rate.')) return;
    try {
      const res = await DairyAPI.saveProductGroup(data);
      bootstrap.Modal.getInstance(document.getElementById('modalProduct')).hide();
      document.getElementById('products-result').innerHTML = `<span class="text-success">${esc(data.product_name)}: ${esc(res.message || 'Saved.')}</span>`;
      await loadProducts();
    } catch (err) {
      document.getElementById('prod-result').innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
    }
  });
}
document.addEventListener('DOMContentLoaded', setupProducts);

// ---------------- Email (SMTP) ----------------
const EMAIL_FLAGS = ['send_bills', 'send_payments', 'send_claims', 'send_orders', 'send_delays', 'send_daily_delivery', 'send_admin_alerts'];
const EMAIL_FIELDS = { host: 'smtp_host', port: 'smtp_port', security: 'smtp_security', username: 'smtp_username',
  'from-email': 'from_email', 'from-name': 'from_name', 'reply-to': 'reply_to', 'site-url': 'site_url', 'admin-email': 'admin_email' };
let emailSettings = null;

function renderEmailSettings(s) {
  emailSettings = s;
  document.getElementById('em-enabled').checked = s.enabled;
  Object.entries(EMAIL_FIELDS).forEach(([id, key]) => { document.getElementById(`em-${id}`).value = s[key] ?? ''; });
  EMAIL_FLAGS.forEach(f => { document.getElementById(`em-${f}`).checked = s[f]; });
  document.getElementById('em-password').value = '';
  document.getElementById('em-password-hint').innerHTML = s.password_unreadable
    ? '<span class="text-danger">Saved password cannot be read (server key changed). Enter it again.</span>'
    : (s.has_password ? 'Saved. Leave empty to keep it.' : 'Not saved yet.');
  const state = !s.enabled ? '<span class="badge bg-secondary">Off</span>'
    : s.ready ? '<span class="badge badge-dairy-success">On</span>' : '<span class="badge badge-dairy-warning">Incomplete</span>';
  document.getElementById('em-status').innerHTML = `
    <div class="mb-1">Email: ${state}</div>
    <div class="mb-1">Customers with an email: <b>${s.customers_with_email}</b> of ${s.active_customers}
      ${s.customers_with_email < s.active_customers ? '<span class="text-muted">(add emails in B2B Customers)</span>' : ''}</div>
    <div>Waiting to send: <b>${s.pending}</b> • Failed: <b class="${s.failed ? 'text-danger' : ''}">${s.failed}</b></div>
    ${s.updated_at ? `<div class="text-muted mt-1">Last saved ${esc(new Date(s.updated_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: 'numeric', minute: '2-digit' }))}</div>` : ''}`;
  document.getElementById('nav-email-state').innerText = s.enabled && s.ready ? 'On' : '';
  document.getElementById('em-retry-btn').classList.toggle('d-none', !s.failed);
}

async function loadEmailSettings() {
  try {
    renderEmailSettings(await DairyAPI.getEmailSettings());
    loadEmailLog();
  } catch (err) {
    document.getElementById('em-status').innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  }
}

window.fillHostinger = function() {
  document.getElementById('em-host').value = 'smtp.hostinger.com';
  document.getElementById('em-port').value = 465;
  document.getElementById('em-security').value = 'ssl';
};

const EMAIL_KIND_LABEL = {
  bill_created: 'Bill', bill_cancelled: 'Bill cancelled', payment: 'Payment', claim_approved: 'Claim', claim_rejected: 'Claim',
  claim_reopened: 'Claim', order_confirmed: 'Order', order_placed: 'Order', order_changed: 'Order', order_cancelled: 'Order', dispatch_held: 'On hold',
  delivery_delayed: 'Delay', not_delivered: 'Not delivered', delivered_short: 'Short', delivered: 'Delivered', dispatched: 'Dispatched'
};

window.loadEmailLog = async function() {
  const box = document.getElementById('em-log');
  try {
    const rows = await DairyAPI.getEmailLog(60);
    if (!rows.length) {
      box.innerHTML = '<div class="text-muted py-3 text-center">No emails yet.</div>';
      return;
    }
    const pill = (st) => st === 'sent' ? 'badge-dairy-success' : st === 'failed' ? 'bg-danger' : 'badge-dairy-warning';
    box.innerHTML = rows.map(r => `
      <div class="border-bottom py-2">
        <div class="d-flex justify-content-between gap-2">
          <div class="fw-bold text-truncate">${esc(r.subject)}${r.has_pdf ? ' <i class="bi bi-paperclip"></i>' : ''}</div>
          <span class="badge ${pill(r.status)}">${esc(r.status)}</span>
        </div>
        <div class="text-muted">${esc(r.customer || r.to)}${r.customer ? ` &lt;${esc(r.to)}&gt;` : ''} •
          ${esc(EMAIL_KIND_LABEL[r.kind] || (r.kind.startsWith('claim_new') ? 'Alert' : r.kind))} •
          ${esc(new Date(r.sent_at || r.created_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: 'numeric', minute: '2-digit' }))}</div>
        ${r.error ? `<div class="text-danger">${esc(r.error)}${r.status === 'pending' ? ` (try ${r.attempts} of 3)` : ''}</div>` : ''}
      </div>`).join('');
  } catch (err) {
    box.innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  }
};

window.sendTestEmail = async function() {
  const to = document.getElementById('em-test-to').value.trim();
  const out = document.getElementById('em-test-result');
  if (!to) {
    out.innerHTML = '<span class="text-danger">Enter an email address.</span>';
    return;
  }
  const btn = document.getElementById('em-test-btn');
  btn.disabled = true;
  out.innerHTML = '<span class="text-muted"><span class="spinner-border spinner-border-sm me-1"></span>Sending...</span>';
  try {
    const r = await DairyAPI.sendTestEmail(to);
    out.innerHTML = r.ok
      ? `<span class="text-success"><i class="bi bi-check-circle me-1"></i>Sent. Check the inbox (and spam) of ${esc(to)}.</span>`
      : `<span class="text-danger"><i class="bi bi-x-circle me-1"></i>${esc(r.error)}</span>`;
  } catch (err) {
    out.innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  } finally {
    btn.disabled = false;
  }
};

window.retryFailedEmails = async function() {
  try {
    const r = await DairyAPI.retryFailedEmails();
    document.getElementById('em-result').innerHTML = `<span class="text-success">${r.retrying} email(s) will be sent again.</span>`;
    loadEmailSettings();
  } catch (err) {
    document.getElementById('em-result').innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  }
};

function setupEmailSettings() {
  const nav = document.querySelector('.nav-item-btn[data-target="view-email"]');
  const form = document.getElementById('form-email');
  if (!nav || !form) return;
  nav.addEventListener('click', loadEmailSettings);
  if (location.hash === '#view-email') loadEmailSettings();
  document.getElementById('em-security').addEventListener('change', (e) => {
    const port = document.getElementById('em-port');
    if (!port.value || ['465', '587', '25'].includes(port.value)) port.value = e.target.value === 'ssl' ? 465 : 587;
  });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = { enabled: document.getElementById('em-enabled').checked };
    Object.entries(EMAIL_FIELDS).forEach(([id, key]) => { data[key] = document.getElementById(`em-${id}`).value.trim(); });
    data.smtp_port = parseInt(data.smtp_port) || null;
    EMAIL_FLAGS.forEach(f => { data[f] = document.getElementById(`em-${f}`).checked; });
    const pw = document.getElementById('em-password').value;
    if (pw) data.smtp_password = pw;
    const out = document.getElementById('em-result');
    try {
      renderEmailSettings(await DairyAPI.saveEmailSettings(data));
      out.innerHTML = '<span class="text-success">Saved. Send a test email to check.</span>';
    } catch (err) {
      out.innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
    }
  });
}
document.addEventListener('DOMContentLoaded', setupEmailSettings);

// ---------------- Legal pages editor ----------------
let legalData = null;
let legalSlug = 'privacy';
let legalSaved = '';  // text as last loaded / saved, to warn about unsaved changes

function legalDirty() {
  const box = document.getElementById('legal-text');
  return legalData && box && box.value !== legalSaved;
}

async function loadLegalPages() {
  try {
    legalData = await DairyAPI.getLegalPages();
  } catch (err) {
    document.getElementById('legal-meta').innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
    return;
  }
  document.getElementById('legal-placeholders').innerHTML = Object.entries(legalData.placeholders).map(([key, label]) => {
    const val = legalData.values[key];
    const tip = `${label}${val ? ' — now: ' + val : ''}`;
    return `<button type="button" class="btn btn-sm btn-dairy-secondary py-0 px-2" title="${esc(tip)}" onclick="insertLegalPlaceholder('${key}')">{${esc(key)}}</button>`;
  }).join('');
  showLegalPage(legalSlug);
}

function showLegalPage(slug) {
  const page = legalData.pages.find(p => p.slug === slug);
  if (!page) return;
  legalSlug = slug;
  document.querySelectorAll('#legal-tabs button').forEach(b => b.classList.toggle('active', b.dataset.slug === slug));
  document.getElementById('legal-text').value = page.content;
  legalSaved = page.content;
  document.getElementById('legal-open').href = page.path;
  document.getElementById('legal-reset').disabled = !page.is_custom;
  document.getElementById('legal-result').innerHTML = '';
  const when = new Date(page.updated_at).toLocaleString('en-IN', page.updated_by
    ? { day: '2-digit', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }
    : { day: '2-digit', month: 'short', year: 'numeric' });
  document.getElementById('legal-meta').innerHTML = (page.is_custom
    ? '<span class="badge badge-dairy-warning me-1">Edited</span>'
    : '<span class="badge badge-dairy-info me-1">Default text</span>') +
    `Last updated ${esc(when)}${page.updated_by ? ' by ' + esc(page.updated_by) : ''}`;
  const missing = slug === 'privacy' && !legalData.values.dairy_email
    ? '<br><span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>Add a contact email in Billing &rarr; Dairy Settings; the Play Store needs one.</span>' : '';
  if (missing) document.getElementById('legal-meta').innerHTML += missing;
}

window.insertLegalPlaceholder = function(key) {
  const box = document.getElementById('legal-text');
  const text = `{${key}}`;
  const start = box.selectionStart ?? box.value.length;
  const end = box.selectionEnd ?? start;
  box.value = box.value.slice(0, start) + text + box.value.slice(end);
  box.focus();
  box.selectionStart = box.selectionEnd = start + text.length;
};

window.previewLegalPage = async function() {
  try {
    const page = await DairyAPI.previewLegalPage(legalSlug, document.getElementById('legal-text').value);
    document.getElementById('legal-preview-frame').srcdoc = page;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modalLegalPreview')).show();
  } catch (err) {
    document.getElementById('legal-result').innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  }
};

window.saveLegalPage = async function() {
  const page = legalData.pages.find(p => p.slug === legalSlug);
  if (!confirm(`Publish the changes to "${page.title}"?\nThe live page and its "Last updated" date change now.`)) return;
  const btn = document.getElementById('legal-save');
  btn.disabled = true;
  try {
    const saved = await DairyAPI.saveLegalPage(legalSlug, document.getElementById('legal-text').value);
    legalData.pages = legalData.pages.map(p => p.slug === saved.slug ? saved : p);
    showLegalPage(saved.slug);
    document.getElementById('legal-result').innerHTML = `<span class="text-success">Saved. The live page is updated.</span>`;
  } catch (err) {
    document.getElementById('legal-result').innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  } finally {
    btn.disabled = false;
  }
};

window.resetLegalPage = async function() {
  const page = legalData.pages.find(p => p.slug === legalSlug);
  if (!confirm(`Put "${page.title}" back to the default text?\nYour edited text will be replaced (it stays in the Audit Log).`)) return;
  try {
    const saved = await DairyAPI.resetLegalPage(legalSlug);
    legalData.pages = legalData.pages.map(p => p.slug === saved.slug ? saved : p);
    showLegalPage(saved.slug);
    document.getElementById('legal-result').innerHTML = '<span class="text-success">Default text restored.</span>';
  } catch (err) {
    document.getElementById('legal-result').innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  }
};

function setupLegalEditor() {
  const nav = document.querySelector('.nav-item-btn[data-target="view-legal"]');
  if (!nav) return;
  nav.addEventListener('click', () => { if (!legalData) loadLegalPages(); });
  if (location.hash === '#view-legal') loadLegalPages();
  document.querySelectorAll('#legal-tabs button').forEach(btn => btn.addEventListener('click', () => {
    if (!legalData || btn.dataset.slug === legalSlug) return;
    if (legalDirty() && !confirm('You have unsaved changes on this page. Leave them?')) return;
    showLegalPage(btn.dataset.slug);
  }));
  window.addEventListener('beforeunload', (e) => {
    if (legalDirty()) { e.preventDefault(); e.returnValue = ''; }
  });
}
document.addEventListener('DOMContentLoaded', setupLegalEditor);

// Dashboard strip: tomorrow's total order, ordering window and dispatch
async function loadTomorrowPanel() {
  const box = document.getElementById('dash-tomorrow');
  if (!box) return;
  const t = new Date();
  t.setDate(t.getDate() + 1);
  const day = isoLocal(t);
  try {
    const s = await DairyAPI.getOrdersDaySummary(day);
    const num = (n) => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
    const until = new Date(s.order_deadline).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: 'numeric', minute: '2-digit' });
    const d = s.dispatch || {};
    const dispatchText = d.on_hold
      ? `<span class="text-warning"><i class="bi bi-pause-circle me-1"></i>Dispatch on hold: ${esc(d.hold_note)}</span>`
      : `<i class="bi bi-truck me-1"></i>Auto dispatch ${esc(new Date(d.dispatch_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: 'numeric', minute: '2-digit' }))}`;
    box.innerHTML = `
      <div class="glass-panel p-3 d-flex flex-wrap gap-3 align-items-center justify-content-between">
        <div>
          <div class="text-muted small text-uppercase fw-bold">Tomorrow • ${esc(prettyDay(day))}</div>
          <div class="h4 fw-bold mb-0">${num(s.total_litres)} L <small class="text-muted fs-6">from ${s.customers_ordered} of ${s.active_customers} customers • ₹${num(s.total_amount)}</small></div>
          ${(s.products || []).length > 1 ? `<div class="small text-muted">${s.products.map(p => `${esc(p.product_name)}: <b>${num(p.quantity)} ${esc(p.unit)}</b>`).join(' • ')}</div>` : ''}
          <div class="small mt-1">
            ${s.customers_can_order
              ? `<span class="text-success"><i class="bi bi-unlock me-1"></i>Customers can order until ${esc(until)} — not final yet</span>`
              : `<span class="text-info"><i class="bi bi-lock me-1"></i>Ordering closed at ${esc(until)} — final list</span>`}
            <span class="ms-2">${dispatchText}</span>
          </div>
        </div>
        <div class="d-flex gap-2">
          <button class="btn btn-sm btn-dairy-secondary" onclick="openTomorrowOrders()"><i class="bi bi-list-ul me-1"></i>View orders</button>
          <a class="btn btn-sm btn-success" href="${DairyAPI.ordersExcelUrl(day)}"><i class="bi bi-file-earmark-excel me-1"></i>Excel</a>
        </div>
      </div>`;
  } catch (err) {
    box.innerHTML = '';
  }
}

window.openTomorrowOrders = function() {
  const link = document.querySelector('[data-target="view-orders"], [href="#view-orders"]');
  if (link) link.click();
  setOrdersDayTomorrow();
};

function renderOrdersTable() {
  const tbody = document.getElementById('orders-tbody');
  const term = document.getElementById('orders-search').value.trim().toLowerCase();
  const status = document.getElementById('orders-status').value;
  const rows = ordersCache.filter(o =>
    (!status || o.status === status || (status === 'confirmed' && o.status === 'created')) &&
    (!term || o.customer_name.toLowerCase().includes(term) || (o.customer_code || '').toLowerCase().includes(term)));
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">${ordersCache.length ? 'No orders match.' : 'No orders for this day.'}</td></tr>`;
    return;
  }
  const money = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  const badge = (st) => st === 'delivered' ? 'badge-dairy-success'
    : st === 'out_for_delivery' ? 'badge-dairy-warning'
    : st === 'cancelled' ? 'bg-secondary' : 'badge-dairy-info';
  // Quantities per product ("10 L Cow Milk, 1.5 kg Paneer"); one-product orders keep the short form
  const qtyText = (o, field) => {
    const its = o.items.filter(i => (i[field] ?? 0) > 0);
    if (!its.length) return '-';
    if (o.items.length === 1) return `${fmtQty(its[0][field])} ${esc(its[0].unit)}`;
    return its.map(i => `${fmtQty(i[field])} ${esc(i.unit)} <span class="text-muted fw-normal">${esc(i.product_name)}</span>`).join('<br>');
  };
  tbody.innerHTML = rows.map(o => {
    const short = o.is_short;
    return `
    <tr class="${o.status === 'cancelled' ? 'opacity-50' : ''}">
      <td class="font-monospace small fw-bold text-info text-nowrap">${esc(o.order_number)}</td>
      <td style="min-width: 190px;">
        <div class="fw-bold">${esc(o.customer_name)}</div>
        <small class="text-muted">${esc([o.route_name, o.driver_name].filter(Boolean).join(' • ') || 'No route')}</small>
      </td>
      <td class="text-end fw-bold text-nowrap">${o.status === 'cancelled' ? '-' : qtyText(o, 'quantity')}</td>
      <td class="text-end text-nowrap ${short ? 'text-danger fw-bold' : ''}">${o.delivered_litres === null ? '<span class="text-muted">-</span>' : qtyText(o, 'delivered_quantity')}
        ${short ? `<br><small>short ${esc(o.short_what)}${o.shortage_reason ? ` (${esc(o.shortage_reason.replace(/_/g, ' '))})` : ''}</small>` : ''}</td>
      <td class="text-end text-nowrap">${o.rate !== null ? money(o.rate) : (o.multi_product ? '<span class="text-muted">per product</span>' : 'mixed')}</td>
      <td class="text-end fw-bold text-nowrap">${o.status === 'cancelled' ? '-' : money(o.billed_amount ?? o.total_amount)}
        ${o.billed_amount === null && o.status !== 'cancelled' ? '<br><small class="text-muted fw-normal">if delivered</small>' : ''}</td>
      <td class="text-nowrap"><span class="badge ${badge(o.status)}">${esc(o.status.replace(/_/g, ' ').toUpperCase())}</span>
        ${o.bill_number ? `<br><small class="text-muted">${esc(o.bill_number)}</small>` : (o.status === 'delivered' ? '<br><small class="text-muted">Not billed yet</small>' : '')}</td>
      <td>
        <button class="btn btn-sm btn-outline-secondary" onclick="viewOrderItems(${o.id})" title="Details">
          <i class="bi bi-eye"></i>
        </button>
      </td>
    </tr>`;
  }).join('');
}

window.viewOrderItems = function(orderId) {
  const order = ordersCache.find(o => o.id === orderId);
  if (!order) return;
  document.getElementById('order-items-title').innerText = `${order.order_number} • ${order.customer_name}`;
  document.getElementById('order-items-subtitle').innerText =
    `Delivery: ${order.delivery_date} • Status: ${order.status.replace(/_/g, ' ')}` +
    (order.delivered_what ? ` • Delivered: ${order.delivered_what}` : '') +
    ` • Bill: ${order.bill_number || 'not billed yet'}` +
    (order.notes ? `
${order.notes}` : '');
  const money = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const rows = order.items.map(i => `
    <tr>
      <td>${esc(i.product_name)}</td>
      <td class="text-end">${fmtQty(i.quantity)} ${esc(i.unit)}${i.delivered_quantity !== null && i.delivered_quantity !== i.quantity
        ? `<br><small class="text-danger">delivered ${fmtQty(i.delivered_quantity)} ${esc(i.unit)}</small>` : ''}</td>
      <td class="text-end">${money(i.unit_price)}</td>
      <td class="text-end fw-semibold">${money(i.total_amount)}</td>
    </tr>`).join('');
  const extra = order.transport_charge > 0 ? `
    <tr><td colspan="3" class="text-end text-muted">Transport charge</td><td class="text-end">${money(order.transport_charge)}</td></tr>` : '';
  document.getElementById('order-items-tbody').innerHTML = rows + extra + `
    <tr class="sr-grand-row"><td colspan="3">TOTAL (ORDERED)</td><td class="text-end">${money(order.total_amount)}</td></tr>` +
    (order.billed_amount !== null && order.billed_amount !== order.total_amount ? `
    <tr><td colspan="3" class="text-end text-danger">Billed for what was delivered (${esc(order.delivered_what)})</td><td class="text-end fw-bold text-danger">${money(order.billed_amount)}</td></tr>` : '');
  new bootstrap.Modal(document.getElementById('modalOrderItems')).show();
};

// 7. Transport cost per litre: one total cost per day / milk delivered that day
const rupee2 = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
let transportReady = false;

function setupTransportFilters() {
  if (transportReady) return;
  transportReady = true;
  const today = isoLocal(new Date());
  ['tc-day', 'tc-ref', 'tc-to'].forEach(id => { document.getElementById(id).value = today; });
  document.getElementById('tc-day').max = today;
  document.getElementById('tc-from').value = today.slice(0, 8) + '01';
  const sync = () => {
    const custom = document.getElementById('tc-period').value === 'custom';
    document.getElementById('tc-ref').classList.toggle('d-none', custom);
    document.getElementById('tc-from').classList.toggle('d-none', !custom);
    document.getElementById('tc-to').classList.toggle('d-none', !custom);
  };
  document.getElementById('tc-period').addEventListener('change', () => { sync(); loadTransportReport(); });
  ['tc-ref', 'tc-from', 'tc-to'].forEach(id => document.getElementById(id).addEventListener('change', loadTransportReport));
  document.getElementById('tc-day').addEventListener('change', fillDayCostForm);
  sync();
}

async function loadTransportTrips() {
  setupTransportFilters();
  await loadTransportReport();
  await fillDayCostForm();
}

// Shows the chosen day's saved cost and milk in the entry form
async function fillDayCostForm() {
  const day = document.getElementById('tc-day').value;
  const info = document.getElementById('tc-day-info');
  if (!day) return;
  try {
    const r = await DairyAPI.getTransportDayCosts({ period: 'daily', ref_date: day });
    const d = r.days[0];
    document.getElementById('tc-amount').value = d && d.cost_set ? d.cost : '';
    document.getElementById('tc-note').value = d && d.note ? d.note : '';
    info.innerHTML = !d ? '<span class="text-muted">No milk delivered on this day.</span>'
      : `<div>${fmtQty(d.litres)} L delivered</div>` + (d.in_progress
        ? `<div class="text-warning">${d.pending_orders} order(s) still pending</div>`
        : (d.cost_per_litre !== null ? `<div class="fw-bold text-success">${rupee2(d.cost_per_litre)} / L</div>` : ''));
  } catch (err) {
    info.innerHTML = `<span class="text-danger">${esc(err.message)}</span>`;
  }
}

window.editDayTransportCost = function(day) {
  document.getElementById('tc-day').value = day;
  fillDayCostForm();
  document.getElementById('tc-amount').focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

window.saveDayTransportCost = async function() {
  const day = document.getElementById('tc-day').value;
  const raw = document.getElementById('tc-amount').value;
  const amount = raw === '' ? 0 : parseFloat(raw);
  if (!day) {
    alert('Choose the date.');
    return;
  }
  if (!(amount >= 0)) {
    alert('Enter the transport cost (0 removes it).');
    return;
  }
  if (amount === 0 && !confirm(`Remove the transport cost of ${day}?`)) return;
  try {
    const res = await DairyAPI.setTransportDayCost(day, amount, document.getElementById('tc-note').value.trim());
    alert(res.message);
    await loadTransportReport();
    await fillDayCostForm();
    loadDashboardMetrics();
  } catch (err) {
    alert('Could not save: ' + err.message);
  }
};

async function loadTransportReport() {
  const tbody = document.getElementById('tc-days-tbody');
  const period = document.getElementById('tc-period').value;
  const params = period === 'custom'
    ? { period, start_date: document.getElementById('tc-from').value, end_date: document.getElementById('tc-to').value }
    : { period, ref_date: document.getElementById('tc-ref').value };
  let data;
  try {
    data = await DairyAPI.getTransportDayCosts(params);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-danger">${esc(err.message)}</td></tr>`;
    return;
  }
  const fmtDay = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
  document.getElementById('tc-period-label').innerText = `${data.period.label}`;
  const t = data.total;
  const card = (label, value, sub, cls = '') => `
    <div class="col-sm-4"><div class="glass-panel p-3 h-100">
      <div class="text-muted small fw-bold text-uppercase">${label}</div>
      <div class="fs-4 fw-bold ${cls}">${value}</div><div class="small text-muted">${sub}</div></div></div>`;
  document.getElementById('tc-summary').innerHTML = [
    card('Milk delivered', `${fmtQty(t.litres)} L`, 'all customers, finished days'),
    card('Transport cost', rupee2(t.cost), `${data.days.filter(d => d.cost_set).length} day(s) entered`),
    card('Cost per litre', t.cost_per_litre === null ? '—' : `${rupee2(t.cost_per_litre)} / L`,
      t.cost_per_litre === null ? 'enter the daily cost' : `over ${t.days_counted} day(s) with cost entered`, 'text-success'),
  ].join('');
  const warn = [];
  if (data.days_without_cost.length) warn.push(`No transport cost entered for ${data.days_without_cost.length} day(s) with deliveries: ${data.days_without_cost.map(fmtDay).join(', ')}. These days are left out of the cost per litre.`);
  if (data.days_in_progress.length) warn.push(`Deliveries still pending on ${data.days_in_progress.map(fmtDay).join(', ')}; not counted until done.`);
  document.getElementById('tc-warnings').innerHTML = warn.map(w => `<div><i class="bi bi-exclamation-triangle me-1"></i>${esc(w)}</div>`).join('');

  tbody.innerHTML = data.days.length ? data.days.map(d => `
    <tr>
      <td class="text-nowrap">${fmtDay(d.date)}</td>
      <td class="text-end">${d.customers}</td>
      <td class="text-end">${fmtQty(d.litres)}${d.in_progress ? `<br><small class="text-warning">${d.pending_orders} order(s) pending</small>` : ''}</td>
      <td class="text-end">${d.cost_set ? rupee2(d.cost) : '<span class="text-warning">not entered</span>'}</td>
      <td class="text-end">${d.in_progress ? '<span class="badge bg-warning text-dark">In progress</span>' : (d.cost_per_litre === null ? '<span class="text-muted">-</span>' : `<b>${rupee2(d.cost_per_litre)}/L</b>`)}</td>
      <td class="small text-muted">${esc(d.note || '')}</td>
      <td><button class="btn btn-sm btn-outline-primary" onclick="editDayTransportCost('${d.date}')"><i class="bi bi-pencil"></i></button></td>
    </tr>`).join('') + (data.days.length > 1 ? `
    <tr class="sr-grand-row">
      <td>TOTAL</td><td></td>
      <td class="text-end">${fmtQty(t.litres)}</td>
      <td class="text-end">${rupee2(t.cost)}</td>
      <td class="text-end">${t.cost_per_litre === null ? '-' : rupee2(t.cost_per_litre) + '/L'}</td>
      <td colspan="2"></td>
    </tr>` : '')
    : '<tr><td colspan="7" class="text-center text-muted py-4">No deliveries in this period.</td></tr>';
}

// 8. Milk Procurement Table
async function loadProcurementTable() {
  try {
    const proc = await DairyAPI.getProcurementCollections();
    const tbody = document.getElementById('procurement-tbody');
    if (!tbody) return;

    tbody.innerHTML = proc.map(p => `
      <tr>
        <td class="font-monospace">${p.batch_no}</td>
        <td>${esc(p.vendor_name)} <br><small class="text-muted">${esc(p.village)} • ${esc(p.collection_date || '')}</small></td>
        <td><span class="badge bg-secondary text-uppercase">${p.milk_type}</span></td>
        <td class="fw-bold">${p.quantity_litres} L</td>
        <td>${p.fat_pct}%</td>
        <td>${p.snf_pct}%</td>
        <td class="fw-bold text-info">₹${p.rate_per_litre.toFixed(2)}/L</td>
        <td class="fw-bold text-success">₹${Number(p.total_amount).toLocaleString('en-IN')}</td>
        <td><span class="badge ${p.quality_status === 'accepted' ? 'bg-success' : (p.quality_status === 'rejected' ? 'bg-danger' : 'bg-warning text-dark')}">${esc(p.quality_status.replace(/_/g, ' ').toUpperCase())}</span></td>
      </tr>
    `).join('') || '<tr><td colspan="9" class="text-center text-muted py-4">No milk collections recorded.</td></tr>';
  } catch (err) {
    console.error('Failed to load procurement:', err);
  }
}

// 9. Production Table
async function loadProductionTable() {
  try {
    const prod = await DairyAPI.getProductionBatches();
    const tbody = document.getElementById('production-tbody');
    if (!tbody) return;

    tbody.innerHTML = prod.map(b => `
      <tr>
        <td class="font-monospace">${b.batch_number}</td>
        <td>${b.process_type}</td>
        <td>${b.raw_milk_input_litres} L</td>
        <td class="fw-bold text-success">${b.output_quantity} ${b.output_unit}</td>
        <td class="text-danger">${b.wastage_litres} L</td>
        <td><span class="badge bg-info">${b.yield_percentage}%</span></td>
        <td>${b.expiry_date}</td>
        <td><span class="badge bg-success">${b.status.toUpperCase()}</span></td>
      </tr>
    `).join('') || '<tr><td colspan="8" class="text-center text-muted py-4">No production batches recorded.</td></tr>';
  } catch (err) {
    console.error('Failed to load production batches:', err);
  }
}

// 10. Customer Profitability Table & Chart
let profitabilityReady = false;
let profitMilk = null;

function setupProfitabilityFilters() {
  if (profitabilityReady) return;
  profitabilityReady = true;
  const now = new Date();
  document.getElementById('pf-month').value = isoLocal(now).slice(0, 7);
  document.getElementById('pf-from').value = isoLocal(now).slice(0, 8) + '01';
  document.getElementById('pf-to').value = isoLocal(now);
  const sync = () => {
    const custom = document.getElementById('pf-period').value === 'custom';
    document.getElementById('pf-month').classList.toggle('d-none', custom);
    document.getElementById('pf-from').classList.toggle('d-none', !custom);
    document.getElementById('pf-to').classList.toggle('d-none', !custom);
  };
  document.getElementById('pf-period').addEventListener('change', () => { sync(); loadProfitabilityTable(); });
  ['pf-month', 'pf-from', 'pf-to'].forEach(id => document.getElementById(id).addEventListener('change', loadProfitabilityTable));
  sync();
}

function profitabilityParams() {
  if (document.getElementById('pf-period').value === 'custom') {
    return { period: 'custom', start_date: document.getElementById('pf-from').value, end_date: document.getElementById('pf-to').value };
  }
  return { period: 'monthly', ref_date: `${document.getElementById('pf-month').value}-01` };
}

async function loadProfitabilityTable() {
  setupProfitabilityFilters();
  const tbody = document.getElementById('profitability-tbody');
  const rs = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  const L = (n) => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 }) + ' L';
  try {
    // The dashboard chart always shows this month; the tab uses its own period
    const [res, month] = await Promise.all([
      DairyAPI.getProfitabilityReport(profitabilityParams()),
      DairyAPI.getProfitabilityReport({ period: 'monthly', ref_date: isoLocal(new Date()) }),
    ]);
    renderProfitabilityChart([...month.customers].sort((a, b) => b.revenue - a.revenue));

    const s = res.summary;
    const n = res.notes;
    profitMilk = n.milk_product_id ? { id: n.milk_product_id, name: n.milk_product_name, cost: n.milk_cost_price } : null;
    document.getElementById('pf-cost-price').innerHTML = (n.products || []).map(p =>
      `${esc(p.product_name)} ${p.cost_price ? rs(p.cost_price) : '<span class="text-danger">not set</span>'}/${esc(p.unit)}`).join(' • ') || 'No products';

    const card = (label, value, sub, cls = '') => `
      <div class="col-6 col-lg"><div class="glass-panel p-3 h-100">
        <div class="text-muted small fw-bold text-uppercase">${label}</div>
        <div class="fs-5 fw-bold ${cls}">${value}</div><div class="small text-muted">${sub}</div></div></div>`;
    document.getElementById('pf-summary').innerHTML = [
      card('Revenue', rs(s.total_revenue), `${L(s.sold_litres)} sold • ${esc(res.period.label)}`),
      card('Product cost', rs(s.total_product_cost), `${L(s.delivered_litres)} milk delivered`),
      card('Transport', rs(s.total_transport_cost), 'day cost shared by litres'),
      card('Margin', rs(s.total_net_margin), `${s.overall_margin_percentage}% of revenue`, s.total_net_margin >= 0 ? 'text-success' : 'text-danger'),
    ].join('');

    const notes = [];
    if (n.days_in_progress) notes.push(`${n.days_in_progress} day(s) still have deliveries pending; their transport cost is not counted yet.`);
    if (n.days_without_cost) notes.push(`${n.days_without_cost} day(s) have no transport cost entered (Transport tab).`);
    if (n.products_without_cost_price.length) notes.push(`No cost price for: ${n.products_without_cost_price.join(', ')}.`);
    document.getElementById('pf-notes').innerText = notes.join(' ');

    tbody.innerHTML = res.customers.length ? res.customers.map(c => `
      <tr>
        <td><div class="fw-bold">${esc(c.business_name)}</div><small class="text-muted">${esc(c.customer_code)}${c.avg_rate ? ` • ${rs(c.avg_rate)}/L` : ''}</small></td>
        <td class="text-end text-nowrap">${L(c.sold_litres)}${c.claimed_litres > 0 ? `<br><small class="text-warning">${L(c.claimed_litres)} claimed</small>` : ''}</td>
        <td class="text-end fw-bold text-nowrap">${rs(c.revenue)}</td>
        <td class="text-end text-muted text-nowrap">${rs(c.product_cost)}</td>
        <td class="text-end text-nowrap">${rs(c.transport_cost)}<br><small class="text-muted">${rs(c.transport_per_litre)}/L</small></td>
        <td class="text-end fw-bold text-nowrap ${c.net_contribution_margin >= 0 ? 'text-success' : 'text-danger'}">${rs(c.net_contribution_margin)}</td>
        <td class="text-end text-nowrap">${rs(c.margin_per_litre)}</td>
        <td><span class="badge ${c.margin_percentage >= 15 ? 'bg-success' : (c.margin_percentage > 5 ? 'bg-primary' : 'bg-warning text-dark')}">${c.margin_percentage.toFixed(1)}%</span>
          <br><small class="text-muted">${esc(c.status)}</small></td>
      </tr>`).join('')
      : '<tr><td colspan="8" class="text-center text-muted py-4">No milk delivered in this period.</td></tr>';
  } catch (err) {
    console.error('Failed to load profitability report:', err);
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="text-danger">Could not load: ${esc(err.message)}</td></tr>`;
  }
}

window.editMilkCostPrice = async function() {
  if (!profitMilk) return;
  const value = prompt(`Cost price of ${profitMilk.name} per litre (what it costs the dairy).
Orders not delivered yet take the new cost; delivered orders keep their old cost.`, profitMilk.cost);
  if (value === null) return;
  const price = parseFloat(value);
  if (!(price > 0)) {
    alert('Enter a cost price more than 0.');
    return;
  }
  try {
    const res = await DairyAPI.setCostPrice(profitMilk.id, price);
    alert(res.message);
    await loadProfitabilityTable();
  } catch (err) {
    alert('Could not change the cost price: ' + err.message);
  }
};

function renderProfitabilityChart(customers) {
  const ctx = document.getElementById('chartProfitability');
  if (!ctx) return;

  if (profitabilityChart) profitabilityChart.destroy();

  const labels = customers.slice(0, 5).map(c => c.business_name.split(' ')[0]);
  const revenueData = customers.slice(0, 5).map(c => c.revenue);
  const marginData = customers.slice(0, 5).map(c => c.net_contribution_margin);

  profitabilityChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Revenue (₹)',
          data: revenueData,
          backgroundColor: 'rgba(2, 132, 199, 0.7)',
          borderRadius: 6
        },
        {
          label: 'Net Margin (₹)',
          data: marginData,
          backgroundColor: 'rgba(16, 185, 129, 0.9)',
          borderRadius: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          grid: { color: 'rgba(0, 0, 0, 0.06)' },
          ticks: { color: '#64748b' }
        },
        x: {
          grid: { display: false },
          ticks: { color: '#334155' }
        }
      }
    }
  });
}

// 11. Billing (monthly / 15 days / daily / custom bills with PDF)
let billType = 'monthly';
let billsCache = [];

function isoLocal(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// Dairy Settings: what the cut-off means, in words, for tomorrow's orders
function showCutoffExample() {
  const el = document.getElementById('bs-cutoff-example');
  const v = document.getElementById('bs-order_cutoff_time').value;
  if (!el) return;
  if (!v) { el.innerText = ''; return; }
  const [h, m] = v.split(':').map(Number);
  const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
  const deadline = new Date(tomorrow); deadline.setHours(h, m, 0, 0);
  if (h >= 12) deadline.setDate(deadline.getDate() - 1);
  const fmt = (d, o) => d.toLocaleString('en-IN', o);
  el.innerText = `Example: orders for ${fmt(tomorrow, { day: '2-digit', month: 'short' })} can be changed till `
    + `${fmt(deadline, { hour: 'numeric', minute: '2-digit', hour12: true })} on ${fmt(deadline, { day: '2-digit', month: 'short' })}.`;
}

function billDayLabel(iso) {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

function billMoney(n) {
  return '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function loadInvoicesTable() {
  // Bills are usually made for the month that just ended
  const now = new Date();
  const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  document.getElementById('bill-month').value = isoLocal(lastMonth).slice(0, 7);
  document.getElementById('bills-filter-month').value = isoLocal(lastMonth).slice(0, 7);
  document.getElementById('bill-day').value = isoLocal(now);
  document.getElementById('bill-from').value = isoLocal(lastMonth);
  document.getElementById('bill-to').value = isoLocal(new Date(now.getFullYear(), now.getMonth(), 0));

  document.querySelectorAll('#bill-type-group [data-bill-type]').forEach(btn => {
    btn.addEventListener('click', () => {
      billType = btn.getAttribute('data-bill-type');
      document.querySelectorAll('#bill-type-group [data-bill-type]').forEach(x => x.classList.toggle('active', x === btn));
      updateBillFilterUI();
      document.getElementById('bill-preview-panel').classList.add('d-none');
    });
  });
  ['bills-filter-month', 'bills-filter-type'].forEach(id => {
    document.getElementById(id).addEventListener('change', () => loadBills());
  });

  try {
    const customers = customersCache.length ? customersCache : await DairyAPI.getCustomers();
    document.getElementById('bill-customer').innerHTML = '<option value="">All Customers</option>' +
      customers.map(c => `<option value="${c.id}">${esc(c.business_name)} (${esc(c.customer_code)})</option>`).join('');
  } catch (err) {
    console.error('Failed to load customers for billing:', err);
  }

  // The list opens on the month of the newest bill (a daily bill this month, or last month's bills)
  try {
    const latest = await DairyAPI.getLatestBillMonth();
    if (latest.month) document.getElementById('bills-filter-month').value = latest.month;
  } catch (err) {
    console.error('Could not find the newest bill:', err);
  }

  updateBillFilterUI();
  await loadBills();
}

function updateBillFilterUI() {
  const show = (id, visible) => document.getElementById(id).classList.toggle('d-none', !visible);
  show('bill-month-wrap', billType === 'monthly' || billType === 'fortnightly');
  show('bill-half-wrap', billType === 'fortnightly');
  show('bill-day-wrap', billType === 'daily');
  show('bill-from-wrap', billType === 'custom');
  show('bill-to-wrap', billType === 'custom');
}

function getBillRequest() {
  const req = { bill_type: billType };
  const month = document.getElementById('bill-month').value;
  if (billType === 'monthly') {
    req.ref_date = `${month}-01`;
  } else if (billType === 'fortnightly') {
    req.ref_date = `${month}-${document.getElementById('bill-half').value === '1' ? '01' : '16'}`;
  } else if (billType === 'daily') {
    req.ref_date = document.getElementById('bill-day').value;
  } else {
    req.start_date = document.getElementById('bill-from').value;
    req.end_date = document.getElementById('bill-to').value;
  }
  const customerId = document.getElementById('bill-customer').value;
  if (customerId) req.customer_id = customerId;
  return req;
}

// Quantity column of a bill: "816 L" for one product, one line per product otherwise
function billQtyCell(b) {
  const ps = (b.products || []).filter(p => p.qty > 0);
  if (!ps.length) return fmtQty(b.total_qty);
  if (ps.length === 1) return `${fmtQty(ps[0].qty)} ${esc(ps[0].unit)}`;
  return ps.map(p => `${fmtQty(p.qty)} ${esc(p.unit)} <small class="text-muted">${esc(p.product)}</small>`).join('<br>');
}

function billTotalsByProduct(rows) {
  const t = {};
  rows.forEach(r => (r.products || []).forEach(p => {
    const k = `${p.product}|${p.unit}`;
    t[k] = (t[k] || 0) + p.qty;
  }));
  const keys = Object.keys(t).filter(k => t[k] > 0);
  if (keys.length === 1) return `${fmtQty(t[keys[0]])} ${esc(keys[0].split('|')[1])}`;
  return keys.map(k => `${fmtQty(t[k])} ${esc(k.split('|')[1])} <small>${esc(k.split('|')[0])}</small>`).join('<br>');
}

window.previewBills = async function() {
  let data;
  try {
    data = await DairyAPI.previewBills(getBillRequest());
  } catch (err) {
    alert(err.message);
    return;
  }
  document.getElementById('bill-preview-label').innerText =
    `${data.period.label} (${data.period.start_date} → ${data.period.end_date})`;
  const rows = data.customers;
  // Bill periods are order days; the last day's orders are delivered the next morning
  const notOver = data.period.ready === undefined ? data.period.end_date > isoLocal(new Date()) : !data.period.ready;
  const isReady = (r) => !notOver && !r.already_billed && !r.undelivered_orders && r.delivered_anything;
  const ready = rows.filter(isReady);
  document.getElementById('bill-preview-tbody').innerHTML = rows.map((r, i) => {
    let status = r.already_billed
      ? `<span class="badge bg-secondary">Already billed (${esc(r.already_billed)})</span>`
      : r.undelivered_orders ? `<span class="badge bg-warning text-dark">${r.undelivered_orders} order(s) not delivered yet</span>`
      : !r.delivered_anything ? '<span class="badge bg-light text-muted">Nothing delivered</span>'
      : notOver ? '<span class="badge bg-warning text-dark">Period not over</span>'
      : '<span class="badge bg-success">Ready</span>';
    if (r.partly_billed) status += `<br><small class="text-muted">Days in ${esc(r.partly_billed)} left out</small>`;
    if (r.claims_deducted_amount) status += `<br><small class="text-muted">${billMoney(r.claims_deducted_amount)} claims deducted</small>`;
    if (r.pending_claims && !r.already_billed) status += `<br><small class="text-warning">${r.pending_claims} claim(s) waiting for decision</small>`;
    return `
      <tr class="${isReady(r) ? '' : 'text-muted'}">
        <td class="sr-col-no">${i + 1}</td>
        <td class="fw-semibold">${esc(r.business_name)}</td>
        <td class="text-end">${billQtyCell(r)}</td>
        <td class="text-end">${r.multi_product ? '<small class="text-muted">per product</small>' : billMoney(r.rate) + (r.mixed_rates ? ' <small class="text-muted">(avg)</small>' : '')}</td>
        <td class="text-end fw-semibold">${billMoney(r.amount)}</td>
        <td class="text-end d-none d-md-table-cell">${r.already_billed ? '-' : billMoney(r.previous_balance)}</td>
        <td>${status}</td>
      </tr>`;
  }).join('') + `
    <tr class="sr-grand-row">
      <td></td>
      <td>TOTAL (${ready.length} bills ready)</td>
      <td class="text-end">${billTotalsByProduct(ready)}</td>
      <td></td>
      <td class="text-end">${billMoney(ready.reduce((sum, r) => sum + r.amount, 0))}</td>
      <td class="d-none d-md-table-cell"></td>
      <td></td>
    </tr>`;
  const note = document.getElementById('bill-preview-note');
  const pendingClaims = rows.filter(r => r.pending_claims && !r.already_billed).length;
  const deliveries = data.period.deliveries_from
    ? `<div class="text-muted">Orders of ${esc(billDayLabel(data.period.start_date))} to ${esc(billDayLabel(data.period.end_date))} `
      + `(delivered ${esc(billDayLabel(data.period.deliveries_from))} to ${esc(billDayLabel(data.period.deliveries_to))}). `
      + `Each order is billed on the day it was ordered, the day before its delivery.</div>` : '';
  note.innerHTML = (notOver
    ? `<span class="text-warning">The last orders of this period are delivered on ${esc(billDayLabel(data.period.deliveries_to || data.period.end_date))}. Bills can be made after that delivery.</span>`
    : pendingClaims ? `<span class="text-warning">${pendingClaims} customer(s) have claims waiting for your decision. Decide them first so they are deducted inside the bill.</span>` : '') + deliveries;
  document.getElementById('bill-preview-panel').classList.remove('d-none');
};

window.generateBills = async function() {
  const req = getBillRequest();
  const body = {
    bill_type: req.bill_type,
    ref_date: req.ref_date || null,
    start_date: req.start_date || null,
    end_date: req.end_date || null,
    customer_ids: req.customer_id ? [parseInt(req.customer_id)] : null
  };
  let res;
  try {
    res = await DairyAPI.generateBills(body);
  } catch (err) {
    alert('Could not generate bills: ' + err.message);
    return;
  }
  const total = res.created.reduce((sum, b) => sum + b.amount, 0);
  let msg = `${res.created.length} bills generated for ${res.period.label}` +
    (res.created.length ? ` (total ${billMoney(total)}).` : '.');
  if (res.skipped.length) {
    msg += `\n\nSkipped ${res.skipped.length}:\n` + res.skipped.map(x => `• ${x.business_name}: ${x.reason}`).join('\n');
  }
  alert(msg);

  // Show the period that was just billed in the list
  document.getElementById('bills-filter-month').value = res.period.start_date.slice(0, 7);
  document.getElementById('bills-filter-type').value = '';
  document.getElementById('bill-preview-panel').classList.add('d-none');
  await loadBills();
  await loadCustomerTable();
  await loadDashboardMetrics();
};

function billListFilters() {
  const month = document.getElementById('bills-filter-month').value;
  const params = { bill_type: document.getElementById('bills-filter-type').value };
  if (month) {
    const [y, m] = month.split('-').map(Number);
    params.start_date = `${month}-01`;
    params.end_date = isoLocal(new Date(y, m, 0));
  }
  return params;
}

async function loadBills() {
  const tbody = document.getElementById('bills-tbody');
  try {
    billsCache = await DairyAPI.getBills(billListFilters());
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-danger">Could not load bills: ${esc(err.message)}</td></tr>`;
    return;
  }
  if (!billsCache.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4">No bills for this filter. Use Generate Bills above.</td></tr>';
    return;
  }
  const typeLabel = { monthly: 'Monthly', fortnightly: '15 Days', daily: 'Daily', custom: 'Custom' };
  tbody.innerHTML = billsCache.map(b => `
    <tr>
      <td class="font-monospace small fw-bold text-nowrap">${esc(b.invoice_number)}</td>
      <td class="fw-bold">${esc(b.customer_name)}</td>
      <td>${esc(b.period_label)}<br><small class="text-muted">${typeLabel[b.bill_type] || ''}</small></td>
      <td class="text-end">${billQtyCell(b)}</td>
      <td class="text-end fw-bold">${billMoney(b.amount)}</td>
      <td class="text-end text-success">${billMoney(b.paid_amount)}</td>
      <td class="text-end ${b.balance_due > 0 ? 'text-danger fw-bold' : ''}">${billMoney(b.balance_due)}</td>
      <td><span class="badge ${b.payment_status === 'paid' ? 'bg-success' : (b.payment_status === 'partial' ? 'bg-warning text-dark' : 'bg-danger')}">${b.payment_status.toUpperCase()}</span></td>
      <td class="text-nowrap">
        <a class="btn btn-sm btn-outline-primary" href="${DairyAPI.billPdfUrl(b.id)}" title="Download PDF"><i class="bi bi-file-earmark-pdf"></i> PDF</a>
        ${b.balance_due > 0 ? `<button class="btn btn-sm btn-outline-success" onclick="openBillPayment(${b.id})" title="Record payment"><i class="bi bi-cash-coin"></i></button>` : ''}
        ${b.paid_amount > 0 ? '' : `<button class="btn btn-sm btn-outline-danger" onclick="deleteBill(${b.id})" title="Delete bill"><i class="bi bi-trash"></i></button>`}
      </td>
    </tr>`).join('');
}

window.downloadAllBills = function() {
  if (!billsCache.length) {
    alert('No bills in the list to download.');
    return;
  }
  window.location.href = DairyAPI.billsPdfUrl({ ids: billsCache.map(b => b.id).join(',') });
};

window.deleteBill = async function(billId) {
  const bill = billsCache.find(b => b.id === billId);
  if (!bill || !confirm(`Delete bill ${bill.invoice_number} for ${bill.customer_name} (${billMoney(bill.amount)})?\nThe amount will be removed from the customer's outstanding.\nClaims deducted in it will be deducted again when the bill is made again.`)) return;
  try {
    await DairyAPI.deleteBill(billId);
    await loadBills();
    await loadCustomerTable();
    await loadDashboardMetrics();
  } catch (err) {
    alert('Could not delete bill: ' + err.message);
  }
};

window.openBillPayment = function(billId) {
  const bill = billsCache.find(b => b.id === billId);
  if (!bill) return;
  document.getElementById('pay-bill-id').value = bill.id;
  document.getElementById('pay-bill-info').innerText =
    `${bill.invoice_number} • ${bill.customer_name} • Balance ${billMoney(bill.balance_due)}`;
  document.getElementById('pay-amount').value = bill.balance_due;
  document.getElementById('pay-date').value = isoLocal(new Date());
  document.getElementById('pay-reference').value = '';
  new bootstrap.Modal(document.getElementById('modalBillPayment')).show();
};

const BUSINESS_FIELDS = ['business_name', 'contact_numbers', 'contact_email', 'bank_account_name', 'bank_name', 'bank_account_number',
  'bank_ifsc', 'bank_branch', 'upi_number', 'gstin', 'address', 'order_cutoff_time', 'dispatch_time', 'auto_bill_day'];

window.openBusinessSettings = async function() {
  try {
    const profile = await DairyAPI.getBusinessProfile();
    BUSINESS_FIELDS.forEach(f => { document.getElementById(`bs-${f}`).value = profile[f] || ''; });
    showCutoffExample();
    new bootstrap.Modal(document.getElementById('modalBusinessSettings')).show();
  } catch (err) {
    alert('Could not load dairy details: ' + err.message);
  }
};

window.openChangePassword = function() {
  document.getElementById('form-change-password').reset();
  new bootstrap.Modal(document.getElementById('modalChangePassword')).show();
};

function setupBillingForms() {
  document.getElementById('form-change-password').addEventListener('submit', async (e) => {
    e.preventDefault();
    const current = document.getElementById('cp-current').value;
    const next = document.getElementById('cp-new').value;
    if (next !== document.getElementById('cp-confirm').value) {
      alert('New password and confirmation do not match.');
      return;
    }
    try {
      await DairyAPI.changePassword(current, next);
      bootstrap.Modal.getInstance(document.getElementById('modalChangePassword')).hide();
      alert('Password changed. Use the new password next time you log in.');
    } catch (err) {
      alert('Could not change password: ' + err.message);
    }
  });

  document.getElementById('form-bill-payment').addEventListener('submit', async (e) => {
    e.preventDefault();
    const billId = document.getElementById('pay-bill-id').value;
    const bill = billsCache.find(b => String(b.id) === String(billId));
    const amount = parseFloat(document.getElementById('pay-amount').value);
    if (!(amount > 0)) {
      alert('Enter the amount received.');
      return;
    }
    if (bill && amount > bill.balance_due &&
        !confirm(`${billMoney(amount)} is more than this bill's balance ${billMoney(bill.balance_due)}.
The extra ${billMoney(amount - bill.balance_due)} will go to the customer's other unpaid bills, or stay as advance. Continue?`)) return;
    try {
      const res = await DairyAPI.recordBillPayment(billId, {
        amount: parseFloat(document.getElementById('pay-amount').value),
        payment_date: document.getElementById('pay-date').value || null,
        payment_method: document.getElementById('pay-method').value,
        reference_number: document.getElementById('pay-reference').value.trim() || null
      });
      bootstrap.Modal.getInstance(document.getElementById('modalBillPayment')).hide();
      alert(`Payment ${res.payment_number} saved. Bill balance: ${billMoney(res.bill.balance_due)}`);
      await loadBills();
      await loadCustomerTable();
      await loadDashboardMetrics();
    } catch (err) {
      alert('Could not save payment: ' + err.message);
    }
  });

  document.getElementById('bs-order_cutoff_time').addEventListener('input', showCutoffExample);
  document.getElementById('form-business-settings').addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = {};
    BUSINESS_FIELDS.forEach(f => { data[f] = document.getElementById(`bs-${f}`).value; });
    data.auto_bill_day = data.auto_bill_day ? parseInt(data.auto_bill_day) : null;
    try {
      await DairyAPI.saveBusinessProfile(data);
      bootstrap.Modal.getInstance(document.getElementById('modalBusinessSettings')).hide();
      alert('Dairy settings saved.');
    } catch (err) {
      alert('Could not save details: ' + err.message);
    }
  });
}

// 12. Sales Reports (Daily / Weekly / Monthly / Custom)
let salesReportPeriod = 'monthly';

const fmtINR = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtQty = (n) => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });

// Local YYYY-MM-DD (toISOString would shift the date to UTC)
function toLocalISODate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function parseLocalDate(str) {
  const [y, m, d] = str.split('-').map(Number);
  return new Date(y, m - 1, d || 1);
}

async function setupSalesReport() {
  const today = toLocalISODate(new Date());
  document.getElementById('sr-ref-date').value = today;
  document.getElementById('sr-ref-month').value = today.slice(0, 7);
  document.getElementById('sr-start-date').value = today.slice(0, 8) + '01';
  document.getElementById('sr-end-date').value = today;

  document.querySelectorAll('#sr-period-group [data-period]').forEach(btn => {
    btn.addEventListener('click', () => {
      salesReportPeriod = btn.getAttribute('data-period');
      document.querySelectorAll('#sr-period-group [data-period]').forEach(b => b.classList.toggle('active', b === btn));
      updateSalesReportFilterUI();
      loadSalesReport();
    });
  });
  ['sr-ref-date', 'sr-ref-month', 'sr-start-date', 'sr-end-date', 'sr-product'].forEach(id => {
    document.getElementById(id).addEventListener('change', () => loadSalesReport());
  });

  try {
    const products = await DairyAPI.getProducts();
    document.getElementById('sr-product').innerHTML = '<option value="">All Products</option>' +
      products.map(p => `<option value="${p.id}">${p.product_name} (${p.unit})</option>`).join('');
  } catch (err) {
    console.error('Failed to load products for sales report:', err);
  }

  updateSalesReportFilterUI();
  await loadSalesReport();
}

function updateSalesReportFilterUI() {
  const isCustom = salesReportPeriod === 'custom';
  const isMonthly = salesReportPeriod === 'monthly';
  document.getElementById('sr-ref-wrap').classList.toggle('d-none', isCustom);
  document.getElementById('sr-start-wrap').classList.toggle('d-none', !isCustom);
  document.getElementById('sr-end-wrap').classList.toggle('d-none', !isCustom);
  document.getElementById('sr-ref-date').classList.toggle('d-none', isMonthly);
  document.getElementById('sr-ref-month').classList.toggle('d-none', !isMonthly);
  document.getElementById('sr-ref-label').innerText =
    isMonthly ? 'Month' : (salesReportPeriod === 'weekly' ? 'Any date in week' : 'Date');
}

function getSalesReportParams() {
  const params = {
    period: salesReportPeriod,
    product_id: document.getElementById('sr-product').value
  };
  if (salesReportPeriod === 'custom') {
    params.start_date = document.getElementById('sr-start-date').value;
    params.end_date = document.getElementById('sr-end-date').value;
  } else if (salesReportPeriod === 'monthly') {
    params.ref_date = document.getElementById('sr-ref-month').value + '-01';
  } else {
    params.ref_date = document.getElementById('sr-ref-date').value;
  }
  return params;
}

window.shiftSalesReportPeriod = function(direction) {
  if (salesReportPeriod === 'monthly') {
    const d = parseLocalDate(document.getElementById('sr-ref-month').value + '-01');
    d.setMonth(d.getMonth() + direction);
    document.getElementById('sr-ref-month').value = toLocalISODate(d).slice(0, 7);
  } else if (salesReportPeriod === 'custom') {
    const s = parseLocalDate(document.getElementById('sr-start-date').value);
    const e = parseLocalDate(document.getElementById('sr-end-date').value);
    const spanDays = Math.round((e - s) / 86400000) + 1;
    s.setDate(s.getDate() + direction * spanDays);
    e.setDate(e.getDate() + direction * spanDays);
    document.getElementById('sr-start-date').value = toLocalISODate(s);
    document.getElementById('sr-end-date').value = toLocalISODate(e);
  } else {
    const d = parseLocalDate(document.getElementById('sr-ref-date').value);
    d.setDate(d.getDate() + direction * (salesReportPeriod === 'weekly' ? 7 : 1));
    document.getElementById('sr-ref-date').value = toLocalISODate(d);
  }
  loadSalesReport();
};

window.downloadSalesReportCsv = function() {
  window.location.href = DairyAPI.salesReportCsvUrl(getSalesReportParams());
};

// Step by step: ordered -> not delivered / short / pending -> delivered -> claims -> net sales
function renderSalesRecon(r) {
  const box = document.getElementById('sr-recon');
  if (!r || !r.ordered.count) {
    box.innerHTML = '';
    return;
  }
  const row = (label, item, sign, note, cls = '') => `
    <tr class="${cls}">
      <td>${label}${note ? `<br><small class="text-muted">${note}</small>` : ''}</td>
      <td class="text-end text-nowrap">${sign}${fmtQty(item.quantity)} L</td>
      <td class="text-end text-nowrap">${sign}${fmtINR(item.amount)}</td>
    </tr>`;
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  const rows = [row('Ordered by customers', r.ordered, '', plural(r.ordered.count, 'order'), 'fw-semibold')];
  if (r.pending_delivery.amount) rows.push(row('Not delivered yet (today / out for delivery)', r.pending_delivery, '− ', `${plural(r.pending_delivery.count, 'order')} • counted once delivered`, 'text-muted'));
  if (r.not_delivered.amount) rows.push(row('Not delivered (delivery boy gave nothing)', r.not_delivered, '− ', plural(r.not_delivered.count, 'order'), 'text-danger'));
  if (r.short_delivered.amount) rows.push(row('Short delivered', r.short_delivered, '− ', plural(r.short_delivered.count, 'order'), 'text-danger'));
  rows.push(row('Delivered', r.delivered, '', 'billed at the customer\'s rate', 'fw-semibold'));
  if (r.claims_deducted.amount) rows.push(row('Claims deducted from bills', r.claims_deducted, '− ', plural(r.claims_deducted.count, 'approved claim'), 'text-danger'));
  if (r.claims_refunded.amount) rows.push(row('Total on bills', r.billed, '', 'what the bills charge (or will charge)', 'fw-semibold'));
  if (r.claims_refunded.amount) rows.push(row('Claims refunded separately', r.claims_refunded, '− ', `${plural(r.claims_refunded.count, 'approved claim')} • bill not changed, money paid back`, 'text-danger'));
  rows.push(row('Net sales (this register)', r.net_sales, '', '', 'sr-grand-row'));
  const pendingNote = r.claims_pending.count
    ? `<div class="small text-warning mt-2"><i class="bi bi-exclamation-circle me-1"></i>${plural(r.claims_pending.count, 'claim')} waiting for your decision are not deducted yet.</div>` : '';
  box.innerHTML = `
    <div class="glass-panel p-3 mb-4">
      <h6 class="fw-bold mb-2">How these sales are calculated</h6>
      <div class="table-responsive">
        <table class="table-dairy sr-table mb-0">
          <thead><tr><th>Step</th><th class="text-end">Milk (L)</th><th class="text-end">Amount (all products)</th></tr></thead>
          <tbody>${rows.join('')}</tbody>
        </table>
      </div>
      ${pendingNote}
    </div>`;
}

window.loadSalesReport = async function() {
  let data;
  try {
    data = await DairyAPI.getSalesReport(getSalesReportParams());
  } catch (err) {
    alert(err.message);
    return;
  }
  const s = data.overall_summary;
  const g = data.grand_total;

  document.getElementById('sr-period-label').innerText = data.period.label;
  document.getElementById('sr-period-range').innerText = `${data.period.start_date} → ${data.period.end_date}`;
  document.getElementById('sr-kpi-customers').innerText = s.total_customers;
  document.getElementById('sr-kpi-orders').innerText = `${s.total_orders} orders`;
  document.getElementById('sr-kpi-qty').innerText = fmtQty(s.total_quantity);
  document.getElementById('sr-kpi-products').innerText = `${s.total_products} products`;
  document.getElementById('sr-kpi-amount').innerText = fmtINR(s.total_amount);

  renderSalesRecon(data.reconciliation);

  // One Excel-style register per product: Sr. No | Customer | Rate | Quantity | Total
  const registers = document.getElementById('sr-registers');
  if (!data.product_registers.length) {
    registers.innerHTML = `
      <div class="glass-panel p-4 mb-4 text-center text-muted">No sales found for this period.</div>`;
  } else {
    registers.innerHTML = data.product_registers.map(reg => `
      <div class="glass-panel overflow-hidden mb-4">
        <div class="p-3 border-bottom border-glass d-flex justify-content-between align-items-center flex-wrap gap-2">
          <div>
            <h5 class="fw-bold mb-0">${esc(reg.product_name)}</h5>
            <small class="text-muted">${esc(reg.sku)} • ${reg.rows.length} customers • Unit: ${esc(reg.unit)}</small>
          </div>
          <span class="badge bg-primary fs-6">${fmtINR(reg.total_amount)}</span>
        </div>
        <div class="table-responsive">
          <table class="table-dairy sr-table sr-register">
            <thead>
              <tr>
                <th class="sr-col-no">Sr. No</th>
                <th>Customer</th>
                <th class="text-end">Rate (₹)</th>
                <th class="text-end">Quantity (${reg.unit})</th>
                <th class="text-end">Total (₹)</th>
              </tr>
            </thead>
            <tbody>
              ${reg.rows.map(r => `
                <tr>
                  <td class="sr-col-no">${r.sr_no}</td>
                  <td class="fw-semibold">${esc(r.business_name)}</td>
                  <td class="text-end">${fmtINR(r.unit_price)}</td>
                  <td class="text-end">${fmtQty(r.quantity)}</td>
                  <td class="text-end fw-semibold">${fmtINR(r.total_amount)}</td>
                </tr>`).join('')}
              <tr class="sr-grand-row">
                <td></td>
                <td>TOTAL</td>
                <td></td>
                <td class="text-end">${fmtQty(reg.total_quantity)}</td>
                <td class="text-end">${fmtINR(reg.total_amount)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>`).join('');
  }

  // Product-wise summary across all customers
  document.getElementById('sr-summary-panel').classList.toggle('d-none', !data.grand_product_summary.length);
  document.getElementById('sr-product-tbody').innerHTML = data.grand_product_summary.map((p, i) => `
    <tr>
      <td class="sr-col-no">${i + 1}</td>
      <td class="fw-semibold">${esc(p.product_name)} <small class="text-muted">(${esc(p.unit)})</small></td>
      <td class="text-end d-none d-md-table-cell">${p.customers_count}</td>
      <td class="text-end">${fmtINR(p.avg_unit_price)}</td>
      <td class="text-end">${fmtQty(p.total_quantity)}</td>
      <td class="text-end fw-semibold">${fmtINR(p.total_amount)}</td>
    </tr>`).join('') + `
    <tr class="sr-grand-row">
      <td></td>
      <td>GRAND TOTAL</td>
      <td class="text-end d-none d-md-table-cell">${s.total_customers}</td>
      <td></td>
      <td class="text-end">${fmtQty(g.total_quantity)} L<br><small class="text-muted fw-normal">milk only</small></td>
      <td class="text-end">${fmtINR(g.total_amount)}</td>
    </tr>`;
};

// Form Handlers
function setupModalForms() {
  document.getElementById('form-customer-rates').addEventListener('submit', saveCustomerRates);
  document.getElementById('form-standard-prices').addEventListener('submit', saveStandardPrices);
  document.getElementById('rates-search').addEventListener('input', (e) => {
    const term = e.target.value.trim().toLowerCase();
    document.querySelectorAll('#rates-tbody tr[data-name]').forEach(tr => tr.classList.toggle('d-none', !!term && !tr.dataset.name.includes(term)));
    document.querySelectorAll('#rates-tbody tr[data-group]').forEach(tr => {
      let next = tr.nextElementSibling, any = false;
      while (next && next.dataset.name !== undefined) { any = any || !next.classList.contains('d-none'); next = next.nextElementSibling; }
      tr.classList.toggle('d-none', !any);
    });
  });

  // Customer app login form
  document.getElementById('form-customer-login').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = parseInt(document.getElementById('cl-customer-id').value);
    const c = customersCache.find(x => x.id === id);
    const password = document.getElementById('cl-password').value.trim();
    if ((!c.has_login && !password) || (password && password.length < 6)) {
      alert('Enter a password of at least 6 characters.');
      return;
    }
    try {
      const res = await DairyAPI.setCustomerLogin(id, {
        password: password || null,
        is_active: document.getElementById('cl-active').checked
      });
      bootstrap.Modal.getInstance(document.getElementById('modalCustomerLogin')).hide();
      alert(password
        ? `${res.message}\n\nLogin ID: ${res.login_id}\nGive the customer the password you just set.`
        : res.message);
      await loadCustomerTable();
    } catch (err) {
      alert('Could not save login: ' + err.message);
    }
  });

  // Add / Edit Customer Form
  document.getElementById('form-customer').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('cust-id').value;
    const val = (fid) => document.getElementById(fid).value.trim();
    const payload = {
      customer_code: id ? null : (val('cust-code') || null),
      business_name: val('cust-business-name'),
      contact_person: val('cust-contact-person'),
      phone: val('cust-phone'),
      email: val('cust-email') || null,
      customer_type: val('cust-type'),
      gstin: val('cust-gstin') || null,
      delivery_address: val('cust-address'),
      billing_address: val('cust-billing-address') || null,
      rates: [...document.querySelectorAll('#cust-rates .cust-rate')].map(el => ({
        product_id: parseInt(el.dataset.product), rate: el.value.trim() === '' ? null : parseFloat(el.value),
      })),
      assigned_route_id: parseInt(val('cust-route')) || null,
      assigned_driver_id: parseInt(val('cust-driver')) || null,
      route_stop_sequence: parseInt(val('cust-stop')) || 1,
      credit_limit: parseFloat(val('cust-credit-limit')) || 0,
      credit_days: parseInt(val('cust-credit-days')) || 0,
      is_active: document.getElementById('cust-active').checked
    };
    try {
      const res = id ? await DairyAPI.updateCustomer(id, payload) : await DairyAPI.createCustomer(payload);
      const message = id ? res.message : `Customer added with code ${res.customer_code}.\nClick "Set Login" on the customer to give them app access.`;
      bootstrap.Modal.getInstance(document.getElementById('modalCustomer')).hide();
      alert(message);
      await loadCustomerTable();
      await loadPricingTable();
    } catch (err) {
      alert('Could not save customer: ' + err.message);
    }
  });

  const pricingFirstPage = () => { pricingPage = 1; renderPricingTable(); };
  document.getElementById('pricing-search').addEventListener('input', pricingFirstPage);
  document.getElementById('pricing-product').addEventListener('change', pricingFirstPage);
  document.getElementById('pricing-filter').addEventListener('change', pricingFirstPage);

  ['cust-search', 'cust-filter-driver', 'cust-show-inactive'].forEach(fid => {
    document.getElementById(fid).addEventListener(fid === 'cust-search' ? 'input' : 'change', renderCustomerTable);
  });

  // Route add / edit
  document.getElementById('form-route').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('route-id').value;
    const existing = id ? routesAll.find(r => String(r.id) === id) : null;
    const payload = {
      route_name: document.getElementById('route-name').value.trim(),
      driver_id: parseInt(document.getElementById('route-driver').value) || 0,
      vehicle_number: document.getElementById('route-vehicle').value.trim(),
      vehicle_type: document.getElementById('route-vehicle-type').value.trim() || null,
      is_active: existing ? existing.is_active : true
    };
    if (!payload.driver_id) {
      alert('Choose the delivery boy for this route.');
      return;
    }
    try {
      await DairyAPI.saveRoute(id || null, payload);
      resetRouteForm();
      await renderRoutes();
      await loadCustomerTable();
    } catch (err) {
      alert('Could not save route: ' + err.message);
    }
  });

  // A customer put on a route gets that route's delivery boy (unless a different one was picked by hand)
  let lastRouteDriver = null;
  document.getElementById('cust-route').addEventListener('focus', () => {
    const r = routesCache.find(x => String(x.id) === document.getElementById('cust-route').value);
    lastRouteDriver = r && r.driver_id ? String(r.driver_id) : null;
  });
  document.getElementById('cust-route').addEventListener('change', () => {
    const r = routesCache.find(x => String(x.id) === document.getElementById('cust-route').value);
    const driverSelect = document.getElementById('cust-driver');
    const followsRoute = !driverSelect.value || driverSelect.value === lastRouteDriver;
    if (r && r.driver_id && followsRoute && [...driverSelect.options].some(o => o.value === String(r.driver_id))) {
      driverSelect.value = String(r.driver_id);
    }
    lastRouteDriver = r && r.driver_id ? String(r.driver_id) : null;
  });

  // Delivery boy add / edit
  document.getElementById('form-driver').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('driver-id').value;
    const existing = id ? driversCache.find(d => String(d.id) === id) : null;
    const password = document.getElementById('driver-password').value.trim();
    if ((!id && !password) || (password && password.length < 6)) {
      alert('Set a password of at least 6 characters for the delivery boy login.');
      return;
    }
    const payload = {
      full_name: document.getElementById('driver-name').value.trim(),
      phone: document.getElementById('driver-phone').value.trim(),
      is_active: existing ? existing.is_active : true,
      password: password || null
    };
    try {
      if (id) await DairyAPI.updateDriver(id, payload);
      else await DairyAPI.createDriver(payload);
      if (password) alert(`Login ready for ${payload.full_name}.\nLogin ID: ${payload.phone}\nGive the delivery boy the password you just set.`);
      resetDriverForm();
      await renderDrivers();
      await loadCustomerTable();
    } catch (err) {
      alert('Could not save delivery boy: ' + err.message);
    }
  });

  // Record Milk Collection Form (vendor list loaded when the modal opens)
  const procurementModal = document.getElementById('modalProcurement');
  procurementModal.addEventListener('show.bs.modal', async () => {
    const vendorSelect = document.getElementById('proc-vendor');
    if (vendorSelect.options.length) return;
    try {
      const vendors = await DairyAPI.getVendors();
      vendorSelect.innerHTML = vendors.map(v => `<option value="${v.id}">${esc(v.full_name)} (${esc(v.village)})</option>`).join('');
    } catch (err) {
      console.error('Failed to load vendors:', err);
    }
  });
  document.getElementById('form-procurement').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      vendor_id: parseInt(document.getElementById('proc-vendor').value),
      milk_type: document.getElementById('proc-milk-type').value,
      shift: document.getElementById('proc-shift').value,
      quantity_litres: parseFloat(document.getElementById('proc-qty').value),
      fat_pct: parseFloat(document.getElementById('proc-fat').value),
      snf_pct: parseFloat(document.getElementById('proc-snf').value)
    };
    try {
      const res = await DairyAPI.recordProcurement(payload);
      bootstrap.Modal.getInstance(procurementModal).hide();
      e.target.reset();
      alert(`Saved ${res.batch_no}: ${res.quantity_litres} L @ ₹${res.rate_per_litre}/L = ₹${Number(res.total_amount).toLocaleString('en-IN')} (${res.quality_status}).`);
      await loadProcurementTable();
      await loadDashboardMetrics();
    } catch (err) {
      alert('Failed to record collection: ' + err.message);
    }
  });
}
