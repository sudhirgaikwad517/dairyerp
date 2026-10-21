/**
 * Dairy ERP Central API Client
 */
const API_BASE = '/api/v1';

// Each page says which app it is (admin / driver / customer) before loading this file.
// Every app keeps its own login, so the admin and a delivery boy can be logged in on one computer.
const DAIRY_APP = window.DAIRY_APP || 'admin';
const AUTH_KEY = `dairy_auth_${DAIRY_APP}`;

const Auth = {
  get() {
    try {
      return JSON.parse(localStorage.getItem(AUTH_KEY) || 'null');
    } catch (e) {
      return null;
    }
  },
  token() {
    const a = Auth.get();
    return a ? a.access_token : null;
  },
  user() {
    const a = Auth.get();
    return a ? a.user : null;
  },
  save(data) {
    localStorage.setItem(AUTH_KEY, JSON.stringify(data));
  },
  logout() {
    localStorage.removeItem(AUTH_KEY);
    window.location.href = `/login?app=${DAIRY_APP}`;
  },
  // Call at page start: sends the visitor to the login page when not logged in
  require() {
    if (!Auth.token()) {
      Auth.logout();
      return false;
    }
    return true;
  },
  // Plain links (PDF / CSV downloads) cannot send headers, so the token goes in the URL
  url(url) {
    const t = Auth.token();
    return t ? `${url}${url.includes('?') ? '&' : '?'}access_token=${encodeURIComponent(t)}` : url;
  }
};

// Every call goes through here so a failed request throws instead of silently returning an error body
async function apiRequest(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = Auth.token();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401 && !path.startsWith('/auth/login')) {
    Auth.logout();
    throw new Error('Session expired. Please log in again.');
  }
  let body = null;
  try {
    body = await res.json();
  } catch (e) {
    body = null;
  }
  if (!res.ok) {
    const detail = body && body.detail;
    const message = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map(d => d.msg).join(', ')
      : `Request failed (${res.status})`;
    throw new Error(message);
  }
  return body;
}

function postJSON(path, data, method = 'POST') {
  return apiRequest(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data)
  });
}

function toQuery(params) {
  const qs = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '') qs.append(k, v);
  });
  const s = qs.toString();
  return s ? `?${s}` : '';
}

const DairyAPI = {
  // 0. Login & accounts
  login(username, password) {
    return postJSON('/auth/login', { username, password, app: DAIRY_APP });
  },

  me() {
    return apiRequest('/auth/me');
  },

  changePassword(currentPassword, newPassword) {
    return postJSON('/auth/change-password', { current_password: currentPassword, new_password: newPassword });
  },

  setCustomerLogin(customerId, data) {
    return postJSON(`/auth/customers/${customerId}/login`, data, 'PUT');
  },

  setDriverPassword(driverId, password) {
    return postJSON(`/auth/drivers/${driverId}/login`, { password }, 'PUT');
  },

  // Customer app (logged-in customer only)
  myProfile() {
    return apiRequest('/me/profile');
  },

  myOrders(limit = 30) {
    return apiRequest(`/me/orders?limit=${limit}`);
  },

  myProducts() {
    return apiRequest('/me/products');
  },

  placeMyOrder(data) {
    return postJSON('/me/orders', data);
  },

  myLedger() {
    return apiRequest('/me/ledger');
  },

  myDays(days = 7) {
    return apiRequest(`/me/days?days=${days}`);
  },

  setMyDay(day, items) {
    return postJSON(`/me/days/${day}`, { items }, 'PUT');
  },

  myBills() {
    return apiRequest('/me/bills');
  },

  myBillPdfUrl(billId) {
    return Auth.url(`${API_BASE}/me/bills/${billId}/pdf`);
  },

  submitMyComplaint(data) {
    return postJSON('/me/complaints', data);
  },

  // 1. Dashboard Live Overview
  getDashboardOverview(onDate = null) {
    return apiRequest(`/dashboard/overview${toQuery({ on: onDate })}`);
  },

  // 2. Customers
  getCustomers() {
    return apiRequest('/customers/');
  },

  getCustomerLedger(customerId) {
    return apiRequest(`/customers/${customerId}/ledger`);
  },

  createCustomer(data) {
    return postJSON('/customers/', data);
  },

  updateCustomer(customerId, data) {
    return postJSON(`/customers/${customerId}`, data, 'PUT');
  },

  // 2b. Delivery Boys
  getDrivers() {
    return apiRequest('/drivers/');
  },

  createDriver(data) {
    return postJSON('/drivers/', data);
  },

  updateDriver(driverId, data) {
    return postJSON(`/drivers/${driverId}`, data, 'PUT');
  },

  // 3. Products
  getProducts() {
    return apiRequest('/products/');
  },

  // 4. Customer Pricing
  getCustomPricing(customerId = null) {
    return apiRequest(`/pricing/${toQuery({ customer_id: customerId })}`);
  },

  // price null = back to the standard price
  setCustomerPrice(customerId, productId, price) {
    return postJSON('/pricing/set', {
      customer_id: customerId,
      product_id: productId,
      custom_price: price
    });
  },

  getStandardPrices() {
    return apiRequest('/pricing/products');
  },

  setStandardPrice(productId, price) {
    return postJSON(`/pricing/products/${productId}`, { standard_b2b_price: price }, 'PUT');
  },

  // 5. Dispatch
  // force: dispatch even though customers can still order for that day
  dispatchOrders(day, force = false) {
    return postJSON(`/orders/dispatch${toQuery({ day, force: force || null })}`);
  },

  // Customer claims (admin)
  getClaims(status = null) {
    return apiRequest(`/claims/${toQuery({ status })}`);
  },

  getClaim(claimId) {
    return apiRequest(`/claims/${claimId}`);
  },

  claimsSummary() {
    return apiRequest('/claims/summary');
  },

  // mode: 'bill' (deduct from bill) or 'refund' (pay back separately; needs refundMethod)
  approveClaim(claimId, approvedQty, note, mode = 'bill', refundMethod = null, refundReference = null, refundDate = null) {
    return postJSON(`/claims/${claimId}/approve`, {
      approved_qty: approvedQty, note, mode,
      refund_method: refundMethod, refund_reference: refundReference, refund_date: refundDate,
    });
  },

  rejectClaim(claimId, note) {
    return postJSON(`/claims/${claimId}/reject`, { note });
  },

  // Undo an approval / rejection: bill and ledger are put back, claim is pending again
  undoClaim(claimId, reason) {
    return postJSON(`/claims/${claimId}/undo`, { reason });
  },

  // Uploaded photos (only shown to people allowed to see them)
  fileUrl(fileId) {
    return Auth.url(`${API_BASE}/files/${fileId}`);
  },

  // 6. Orders
  getOrders(params = {}) {
    return apiRequest(`/orders/${toQuery(params)}`);
  },

  createOrder(data) {
    return postJSON('/orders/', data);
  },

  getOrdersDaySummary(day) {
    return apiRequest(`/orders/day-summary${toQuery({ day })}`);
  },

  // Automatic dispatch: hold a day with a note, or remove the hold
  holdDispatch(day, note) {
    return postJSON('/orders/dispatch-hold', { day, note }, 'PUT');
  },

  releaseDispatchHold(day) {
    return apiRequest(`/orders/dispatch-hold${toQuery({ day })}`, { method: 'DELETE' });
  },

  // Products (admin)
  getAllProducts() {
    return apiRequest('/products/?include_inactive=true');
  },

  saveProduct(id, data) {
    return id ? postJSON(`/products/${id}`, data, 'PUT') : postJSON('/products/', data);
  },

  setProductActive(id, isActive) {
    return postJSON(`/products/${id}/active`, { is_active: isActive }, 'PUT');
  },

  // Email (SMTP)
  getEmailSettings() {
    return apiRequest('/email-settings');
  },

  saveEmailSettings(data) {
    return postJSON('/email-settings', data, 'PUT');
  },

  sendTestEmail(to) {
    return postJSON('/email-settings/test', { to });
  },

  getEmailLog(limit = 50) {
    return apiRequest(`/email-settings/log${toQuery({ limit })}`);
  },

  retryFailedEmails() {
    return postJSON('/email-settings/retry-failed');
  },

  // Legal pages editor (admin)
  getLegalPages() {
    return apiRequest('/legal-pages');
  },

  saveLegalPage(slug, content) {
    return postJSON(`/legal-pages/${slug}`, { content }, 'PUT');
  },

  resetLegalPage(slug) {
    return postJSON(`/legal-pages/${slug}/reset`);
  },

  // Returns the page HTML (not JSON)
  async previewLegalPage(slug, content) {
    const res = await fetch(`${API_BASE}/legal-pages/${slug}/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${Auth.token()}` },
      body: JSON.stringify({ content })
    });
    if (!res.ok) throw new Error(`Preview failed (${res.status})`);
    return res.text();
  },

  ordersExcelUrl(day) {
    return Auth.url(`${API_BASE}/orders/export${toQuery({ day })}`);
  },

  // 7. Driver & Deliveries
  getDriverTrips() {
    return apiRequest('/driver/my-trips');
  },

  reportDeliveryProblem(reason, note) {
    return postJSON('/driver/report-problem', { reason, note });
  },

  uploadDeliveryPhoto(deliveryId, file) {
    const form = new FormData();
    form.append('photo', file);
    return apiRequest(`/driver/deliveries/${deliveryId}/photo`, { method: 'POST', body: form });
  },

  completeDelivery(payload) {
    return postJSON('/driver/complete-delivery', payload);
  },

  // 8. Transport Trips, Routes & Allocation
  getTransportTrips() {
    return apiRequest('/transport/trips');
  },

  getRoutes(includeInactive = false) {
    return apiRequest(`/transport/routes${includeInactive ? '?include_inactive=true' : ''}`);
  },

  saveRoute(id, data) {
    return id ? postJSON(`/transport/routes/${id}`, data, 'PUT') : postJSON('/transport/routes', data);
  },

  getTransportDayCosts(params) {
    return apiRequest(`/transport/day-costs${toQuery(params)}`);
  },

  setTransportDayCost(day, amount, note) {
    return postJSON(`/transport/day-costs/${day}`, { amount, note: note || null }, 'PUT');
  },


  // 9. Milk Procurement
  getProcurementCollections() {
    return apiRequest('/procurement/collections');
  },

  getVendors() {
    return apiRequest('/procurement/vendors');
  },

  recordProcurement(data) {
    return postJSON('/procurement/record', data);
  },

  // 10. Production Batches
  getProductionBatches() {
    return apiRequest('/production/batches');
  },

  createProductionBatch(data) {
    return postJSON('/production/batch', data);
  },

  // 11. Customer Profitability
  getProfitabilityReport(params = {}) {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
    return apiRequest(`/profitability/${qs ? '?' + qs : ''}`);
  },

  setCostPrice(productId, costPrice) {
    return postJSON(`/pricing/products/${productId}/cost`, { cost_price: costPrice }, 'PUT');
  },

  // 11b. Sales Reports (daily / weekly / monthly / custom)
  getSalesReport(params) {
    return apiRequest(`/reports/sales${toQuery(params)}`);
  },

  salesReportCsvUrl(params) {
    return Auth.url(`${API_BASE}/reports/sales/export-csv${toQuery(params)}`);
  },

  // 12. Invoices
  getInvoices(customerId = null) {
    return apiRequest(`/invoices/${toQuery({ customer_id: customerId })}`);
  },

  getInvoiceDetails(invoiceId) {
    return apiRequest(`/invoices/${invoiceId}`);
  },

  // 12b. Period Bills (daily / 15 days / monthly / custom) & PDF
  previewBills(params) {
    return apiRequest(`/billing/preview${toQuery(params)}`);
  },

  generateBills(data) {
    return postJSON('/billing/generate', data);
  },

  getBills(params = {}) {
    return apiRequest(`/billing/bills${toQuery(params)}`);
  },

  deleteBill(billId) {
    return apiRequest(`/billing/bills/${billId}`, { method: 'DELETE' });
  },

  recordBillPayment(billId, data) {
    return postJSON(`/billing/bills/${billId}/payment`, data);
  },

  billPdfUrl(billId) {
    return Auth.url(`${API_BASE}/billing/bills/${billId}/pdf`);
  },

  billsPdfUrl(params) {
    return Auth.url(`${API_BASE}/billing/pdf${toQuery(params)}`);
  },

  getBusinessProfile() {
    return apiRequest('/settings/business');
  },

  saveBusinessProfile(data) {
    return postJSON('/settings/business', data, 'PUT');
  },

  // 13. Complaints
  getComplaints() {
    return apiRequest('/complaints/');
  },

  submitComplaint(data) {
    return postJSON('/complaints/', data);
  }
};
