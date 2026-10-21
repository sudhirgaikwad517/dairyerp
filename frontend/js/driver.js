/**
 * Delivery App (mobile-first): today's stops, delivery entry with photo + signature, payment collection
 */

let activeTripData = null;
let currentDelivery = null;
let stopFilter = 'pending';
let signatureCanvas = null;
let signatureCtx = null;
let isDrawing = false;
let hasSignature = false;

const money = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const litres = (n) => `${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })} L`;
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, ch => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
));

const SHORT_REASONS = {
  leakage: 'Leakage',
  damage: 'Damaged',
  customer_rejection: 'Customer rejected',
  stock_shortage: 'Not enough milk',
  delivery_issue: 'Delivery issue'
};

document.addEventListener('DOMContentLoaded', async () => {
  // Delivery boy app needs a delivery boy login
  if (!Auth.require()) return;
  const user = Auth.user();
  const hour = new Date().getHours();
  const greet = hour < 12 ? 'Good morning' : (hour < 17 ? 'Good afternoon' : 'Good evening');
  document.getElementById('driver-greeting').innerText = user && user.full_name ? `${greet}, ${user.full_name}` : greet;

  document.querySelectorAll('#stop-filter button').forEach(btn => btn.addEventListener('click', () => {
    stopFilter = btn.dataset.filter;
    document.querySelectorAll('#stop-filter button').forEach(b => b.classList.toggle('active', b === btn));
    renderStops();
  }));

  initSignaturePad();
  await loadDriverDeliveries();
});

window.driverLogout = function() {
  if (confirm('Log out of the delivery app?')) Auth.logout();
};

function showToast(message, type = 'success') {
  const box = document.getElementById('app-toast');
  const icon = type === 'success' ? 'check-circle-fill' : 'exclamation-triangle-fill';
  box.innerHTML = `<div class="alert alert-${type} shadow d-flex align-items-start gap-2 mb-0 py-2" role="alert">
    <i class="bi bi-${icon} mt-1"></i><div class="small fw-semibold">${esc(message)}</div></div>`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { box.innerHTML = ''; }, type === 'success' ? 3500 : 6000);
}

// Canvas Signature Pad Initialization
function initSignaturePad() {
  signatureCanvas = document.getElementById('signaturePad');
  if (!signatureCanvas) return;
  signatureCtx = signatureCanvas.getContext('2d');
  signatureCtx.lineWidth = 2.5;
  signatureCtx.lineCap = 'round';
  signatureCtx.strokeStyle = '#0b2545';

  function getPos(e) {
    const rect = signatureCanvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    // Canvas may be scaled down by CSS on small screens; map back to canvas pixels
    return {
      x: (clientX - rect.left) * (signatureCanvas.width / rect.width),
      y: (clientY - rect.top) * (signatureCanvas.height / rect.height)
    };
  }

  function start(e) {
    e.preventDefault();
    isDrawing = true;
    const pos = getPos(e);
    signatureCtx.beginPath();
    signatureCtx.moveTo(pos.x, pos.y);
  }

  function draw(e) {
    if (!isDrawing) return;
    e.preventDefault();
    const pos = getPos(e);
    signatureCtx.lineTo(pos.x, pos.y);
    signatureCtx.stroke();
    hasSignature = true;
  }

  function stop() {
    isDrawing = false;
  }

  signatureCanvas.addEventListener('mousedown', start);
  signatureCanvas.addEventListener('mousemove', draw);
  window.addEventListener('mouseup', stop);

  signatureCanvas.addEventListener('touchstart', start, { passive: false });
  signatureCanvas.addEventListener('touchmove', draw, { passive: false });
  signatureCanvas.addEventListener('touchend', stop);
}

window.clearSignature = function() {
  if (signatureCtx && signatureCanvas) {
    signatureCtx.clearRect(0, 0, signatureCanvas.width, signatureCanvas.height);
    hasSignature = false;
  }
};

const isDone = (stop) => stop.status === 'delivered' || stop.status === 'partially_delivered';

// What happened at a stop, for the badge and card colour
const qtyU = (n, unit) => `${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 3 })} ${unit || ''}`.trim();
const WHOLE = ['pcs', 'packet', 'box'];
const isShort = (stop) => (stop.items || []).some(i => i.delivered !== null && i.delivered < i.ordered);
const nothingGiven = (stop) => (stop.items || []).length > 0 && stop.items.every(i => (i.delivered || 0) <= 0);

function stopState(stop) {
  if (!isDone(stop)) return { key: 'pending', label: 'Pending', pill: 'pill-blue' };
  if (nothingGiven(stop)) return { key: 'missed', label: 'Not delivered', pill: 'pill-red' };
  if (isShort(stop)) return { key: 'short', label: 'Short', pill: 'pill-amber' };
  return { key: 'done', label: 'Delivered', pill: 'pill-green' };
}

// Load Assigned Deliveries
async function loadDriverDeliveries(manual = false) {
  const icon = document.getElementById('refresh-icon');
  icon.classList.add('spin');
  try {
    const data = await DairyAPI.getDriverTrips();
    activeTripData = data;
    const trip = data.active_trip;

    if (trip) {
      document.getElementById('route-name').innerText = trip.route_name;
      const dateText = new Date(trip.trip_date + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' });
      document.getElementById('trip-date-badge').innerText = trip.is_today ? `Today, ${dateText}` : dateText;
      const meta = [trip.trip_number, trip.vehicle_number].filter(Boolean).join(' • ');
      document.getElementById('trip-badge-info').innerText = meta;
      document.getElementById('trip-badge-wrap').classList.toggle('d-none', !meta);
    } else {
      document.getElementById('route-name').innerText = 'No trip assigned yet';
      document.getElementById('trip-date-badge').innerText = 'Today';
      document.getElementById('trip-badge-wrap').classList.add('d-none');
    }

    renderDispatchBanner();
    renderIssues();
    renderProgress();
    renderStops();
    if (manual) showToast('Deliveries updated');
  } catch (err) {
    console.error('Failed to load driver trips:', err);
    document.getElementById('driver-stops-list').innerHTML = `
      <div class="glass-panel p-4 text-center">
        <i class="bi bi-wifi-off fs-2 text-danger"></i>
        <div class="fw-bold mt-2">Could not load deliveries</div>
        <div class="text-muted small mb-3">${esc(err.message)}</div>
        <button class="btn btn-dairy-primary btn-sm" onclick="loadDriverDeliveries(true)">Try again</button>
      </div>`;
  } finally {
    icon.classList.remove('spin');
  }
}
window.loadDriverDeliveries = loadDriverDeliveries;

const ISSUE_REASONS = {
  vehicle_breakdown: 'Vehicle breakdown',
  traffic: 'Heavy traffic / road blocked',
  weather: 'Bad weather',
  milk_shortage: 'Not enough milk in the vehicle',
  accident: 'Accident',
  other: 'Other problem'
};
const timeText = (iso) => new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' });
const hasTodayStops = () => !!(activeTripData && activeTripData.active_trip && activeTripData.active_trip.is_today);

// Today's dispatch: when the orders come, or the dairy's hold note
function renderDispatchBanner() {
  const box = document.getElementById('dispatch-banner');
  const d = activeTripData && activeTripData.dispatch;
  if (!d || hasTodayStops() && !d.on_hold) {
    box.innerHTML = '';
    return;
  }
  let html;
  if (d.on_hold) {
    html = `<div class="alert alert-warning d-flex gap-2 align-items-start mb-3" style="border-radius: 14px;">
      <i class="bi bi-pause-circle-fill fs-5"></i><div><b>Today's dispatch is on hold</b><br>
      <span class="small">${esc(String(d.hold_note || "").replace(/\.+$/, ""))}. Wait for the dairy office.</span></div></div>`;
  } else if (!d.time_passed) {
    html = `<div class="alert alert-info d-flex gap-2 align-items-start mb-3" style="border-radius: 14px;">
      <i class="bi bi-clock-fill fs-5"></i><div><b>Today's orders come at ${esc(timeText(d.dispatch_at))}</b><br>
      <span class="small">They are sent to you automatically. Tap refresh after that time.</span></div></div>`;
  } else {
    html = `<div class="alert alert-secondary d-flex gap-2 align-items-start mb-3" style="border-radius: 14px;">
      <i class="bi bi-inbox fs-5"></i><div><b>No orders for you today yet</b><br>
      <span class="small">Orders were sent at ${esc(timeText(d.dispatch_at))}. Call the dairy office if you expected deliveries.</span></div></div>`;
  }
  box.innerHTML = html;
}

function renderIssues() {
  const stops = (activeTripData && activeTripData.stops) || [];
  const waiting = hasTodayStops() ? stops.filter(s => !isDone(s)).length : 0;
  const issues = (activeTripData && activeTripData.issues) || [];
  document.getElementById('issue-box').classList.toggle('d-none', !waiting && !issues.length);
  document.querySelector('#issue-box button').classList.toggle('d-none', !waiting);
  document.getElementById('issue-list').innerHTML = issues.map(i =>
    `<div class="text-danger-emphasis"><i class="bi bi-check2 me-1"></i>Reported at ${esc(timeText(i.created_at))}: ` +
    `${esc(ISSUE_REASONS[i.reason] || i.reason)}${i.note ? ' — ' + esc(i.note) : ''} (${i.stops_affected} customer(s) told)</div>`).join('');
}

window.openProblemModal = function() {
  const waiting = ((activeTripData && activeTripData.stops) || []).filter(s => !isDone(s)).length;
  document.getElementById('problem-reason').value = '';
  document.getElementById('problem-note').value = '';
  document.getElementById('problem-count').innerText = `${waiting} customer(s) still waiting will get this message.`;
  new bootstrap.Modal(document.getElementById('modalProblem')).show();
};

window.sendProblem = async function() {
  const reason = document.getElementById('problem-reason').value;
  const note = document.getElementById('problem-note').value.trim();
  if (!reason) {
    showToast('Select what the problem is.', 'danger');
    return;
  }
  if (reason === 'other' && !note) {
    showToast('Write what the problem is.', 'danger');
    return;
  }
  const btn = document.getElementById('problem-send');
  btn.disabled = true;
  try {
    const res = await DairyAPI.reportDeliveryProblem(reason, note);
    bootstrap.Modal.getInstance(document.getElementById('modalProblem')).hide();
    showToast(`Sent. ${res.customers_told} customer(s) and the dairy office were told.`);
    await loadDriverDeliveries();
  } catch (err) {
    showToast('Could not send: ' + err.message, 'danger');
  } finally {
    btn.disabled = false;
  }
};

function renderProgress() {
  const stops = (activeTripData && activeTripData.stops) || [];
  const done = stops.filter(isDone).length;
  const pct = stops.length ? Math.round(done * 100 / stops.length) : 0;
  document.getElementById('pg-done').innerText = done;
  document.getElementById('pg-total').innerText = stops.length;
  document.getElementById('pg-percent').innerText = `${pct}%`;
  document.getElementById('pg-percent').className = `pill ${pct === 100 && stops.length ? 'pill-green' : 'pill-blue'}`;
  document.getElementById('pg-bar').style.width = `${pct}%`;
  document.getElementById('pg-loaded').innerText = litres(stops.reduce((s, x) => s + (x.ordered_litres || 0), 0));
  document.getElementById('pg-delivered').innerText = litres(stops.filter(isDone).reduce((s, x) => s + (x.delivered_litres || 0), 0));
  document.getElementById('pg-collected').innerText = money(stops.reduce((s, x) => s + (x.collected_amount || 0), 0));
  document.getElementById('cnt-pending').innerText = stops.length - done;
  document.getElementById('cnt-done').innerText = done;
  document.getElementById('cnt-all').innerText = stops.length;
}

function renderStops() {
  const container = document.getElementById('driver-stops-list');
  const stops = (activeTripData && activeTripData.stops) || [];

  if (!stops.length) {
    container.innerHTML = `
      <div class="glass-panel p-4 text-center">
        <i class="bi bi-inbox fs-2 text-muted"></i>
        <div class="fw-bold mt-2">No deliveries assigned</div>
        <div class="text-muted small">Today's orders show here after the dispatch time. Tap refresh at the top.</div>
      </div>`;
    return;
  }

  const shown = stops.filter(s => stopFilter === 'all' || (stopFilter === 'done' ? isDone(s) : !isDone(s)));
  if (!shown.length) {
    container.innerHTML = stopFilter === 'pending'
      ? `<div class="glass-panel p-4 text-center">
           <i class="bi bi-check2-circle fs-1 text-success"></i>
           <div class="fw-bold mt-2">All deliveries done</div>
           <div class="text-muted small">Great work! Every stop on this route is updated.</div>
         </div>`
      : '<div class="glass-panel p-4 text-center text-muted">No deliveries done yet.</div>';
    return;
  }

  container.innerHTML = shown.map(stop => {
    const st = stopState(stop);
    const done = isDone(stop);
    const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(stop.delivery_address || stop.business_name)}`;
    const reason = isShort(stop) && SHORT_REASONS[stop.shortage_reason] ? ` • ${SHORT_REASONS[stop.shortage_reason]}` : '';
    return `
      <div class="stop-card ${st.key !== 'pending' ? 'done ' + st.key : ''}">
        <div class="d-flex gap-3 align-items-start">
          <div class="stop-no">${stop.sequence}</div>
          <div class="flex-grow-1" style="min-width: 0;">
            <div class="d-flex justify-content-between gap-2 align-items-start">
              <div class="stop-name">${esc(stop.business_name)}</div>
              <span class="pill ${st.pill}">${esc(st.label)}</span>
            </div>
            ${stop.contact_person ? `<div class="stop-addr"><i class="bi bi-person me-1"></i>${esc(stop.contact_person)}</div>` : ''}
            ${stop.delivery_address ? `<div class="stop-addr"><i class="bi bi-geo-alt me-1"></i>${esc(stop.delivery_address)}</div>` : ''}
          </div>
        </div>

        ${(stop.items || []).length > 1 ? `
        <div class="item-lines">${stop.items.map(i => `
          <div><span>${esc(i.product_name)}</span><span class="fw-bold">${done
            ? `<span class="${i.delivered < i.ordered ? 'text-warning' : 'text-success'}">${qtyU(i.delivered, i.unit)}</span> / ${qtyU(i.ordered, i.unit)}`
            : qtyU(i.ordered, i.unit)}</span></div>`).join('')}
          ${stop.collected_amount > 0 ? `<div><span>Collected</span><span class="fw-bold">${money(stop.collected_amount)}</span></div>` : ''}
        </div>` : `
        <div class="qty-row">
          <div class="qty-box"><div class="ql">Ordered${stop.items && stop.items[0] ? ' • ' + esc(stop.items[0].product_name) : ''}</div>
            <div class="qv">${stop.items && stop.items[0] ? qtyU(stop.items[0].ordered, stop.items[0].unit) : litres(stop.ordered_litres)}</div></div>
          <div class="qty-box"><div class="ql">Delivered</div>
            <div class="qv ${done ? (isShort(stop) ? 'text-warning' : 'text-success') : 'text-muted'}">${done
              ? (stop.items && stop.items[0] ? qtyU(stop.items[0].delivered, stop.items[0].unit) : litres(stop.delivered_litres)) : '—'}</div></div>
          ${stop.collected_amount > 0 ? `<div class="qty-box"><div class="ql">Collected</div><div class="qv">${money(stop.collected_amount)}</div></div>` : ''}
        </div>`}
        ${reason || stop.shortage_notes ? `<div class="small text-warning-emphasis mb-2"><i class="bi bi-info-circle me-1"></i>${esc((reason ? reason.slice(3) : '') + (stop.shortage_notes ? (reason ? ' — ' : '') + stop.shortage_notes : ''))}</div>` : ''}

        <div class="stop-actions">
          <a href="tel:${esc(stop.phone)}" class="btn btn-outline-success btn-icon-only" title="Call" aria-label="Call ${esc(stop.business_name)}"><i class="bi bi-telephone-fill"></i></a>
          <a href="${mapUrl}" target="_blank" rel="noopener" class="btn btn-outline-primary btn-icon-only" title="Open map" aria-label="Open map"><i class="bi bi-geo-alt-fill"></i></a>
          ${done && stop.locked
            ? `<span class="btn btn-light flex-grow-1 disabled text-success fw-bold" aria-disabled="true"><i class="bi bi-lock-fill me-1"></i>Confirmed</span>`
            : `<button class="btn ${done ? 'btn-outline-secondary' : 'btn-dairy-primary'} flex-grow-1" onclick="openDeliveryExecutionModal(${stop.delivery_id})">
            <i class="bi bi-${done ? 'pencil-square' : 'check-circle-fill'} me-1"></i>${done ? 'Correct Delivery' : 'Deliver'}
          </button>`}
        </div>
      </div>`;
  }).join('');
}

// Quantity per product in the delivery form
function renderExecItems(stop, done) {
  document.getElementById('exec-items').innerHTML = (stop.items || []).map(i => {
    const step = WHOLE.includes(i.unit) ? 1 : 0.5;
    const value = done && i.delivered !== null ? i.delivered : i.ordered;
    return `<div class="item-row" id="exec-row-${i.item_id}">
        <div class="d-flex justify-content-between align-items-baseline mb-1">
          <span class="item-name">${esc(i.product_name)}</span>
          <span class="item-ordered">ordered ${esc(qtyU(i.ordered, i.unit))}</span>
        </div>
        <div class="input-group qty-stepper">
          <button type="button" class="btn btn-outline-secondary" onclick="stepItem(${i.item_id}, -${step})" aria-label="Less">−</button>
          <input type="number" step="${WHOLE.includes(i.unit) ? 1 : 'any'}" min="0" max="${i.ordered}" value="${value}"
            class="form-control form-dairy-control exec-item-qty" data-item-id="${i.item_id}" data-ordered="${i.ordered}"
            data-unit="${esc(i.unit)}" data-name="${esc(i.product_name)}" inputmode="decimal" aria-label="${esc(i.product_name)} delivered">
          <span class="input-group-text">${esc(i.unit)}</span>
          <button type="button" class="btn btn-outline-secondary" onclick="stepItem(${i.item_id}, ${step})" aria-label="More">+</button>
        </div>
      </div>`;
  }).join('');
  document.querySelectorAll('.exec-item-qty').forEach(inp => inp.addEventListener('input', syncShortBox));
}

function execItems() {
  return [...document.querySelectorAll('.exec-item-qty')].map(inp => ({
    item_id: parseInt(inp.dataset.itemId), qty: parseFloat(inp.value), ordered: parseFloat(inp.dataset.ordered),
    unit: inp.dataset.unit, name: inp.dataset.name,
  }));
}

window.stepItem = function(itemId, delta) {
  const inp = document.querySelector(`.exec-item-qty[data-item-id="${itemId}"]`);
  const ordered = parseFloat(inp.dataset.ordered);
  inp.value = Math.round(Math.min(ordered, Math.max(0, (parseFloat(inp.value) || 0) + delta)) * 1000) / 1000;
  syncShortBox();
};
window.setQtyFull = function() {
  document.querySelectorAll('.exec-item-qty').forEach(inp => { inp.value = inp.dataset.ordered; });
  syncShortBox();
};
window.setQtyZero = function() {
  document.querySelectorAll('.exec-item-qty').forEach(inp => { inp.value = 0; });
  syncShortBox();
};

function syncShortBox() {
  const items = execItems();
  const shortItems = items.filter(i => !isNaN(i.qty) && i.qty < i.ordered);
  items.forEach(i => document.getElementById(`exec-row-${i.item_id}`).classList.toggle('short', !isNaN(i.qty) && i.qty < i.ordered));
  const short = shortItems.length > 0;
  const nothing = items.length > 0 && items.every(i => !isNaN(i.qty) && i.qty <= 0);
  document.getElementById('exec-short-box').classList.toggle('d-none', !short);
  if (short) {
    document.getElementById('exec-short-label').innerText = nothing
      ? 'Nothing delivered — why?'
      : `Less: ${shortItems.map(i => `${qtyU(i.ordered - i.qty, i.unit)} ${i.name}`).join(', ')} — why?`;
  }
  // Nothing handed over: nobody signs for it
  const noMilk = nothing;
  const signed = currentDelivery && currentDelivery.has_signature;
  document.getElementById('exec-sign-star').classList.toggle('d-none', noMilk || signed);
  document.getElementById('exec-sign-hint').innerText = noMilk
    ? 'Not needed when no milk was delivered.'
    : (signed ? 'Signature already saved. Sign again only if needed.' : 'Customer signs here with a finger.');
}

window.openDeliveryExecutionModal = function(deliveryId) {
  const stop = activeTripData.stops.find(s => s.delivery_id === deliveryId);
  if (!stop) return;
  const done = isDone(stop);
  if (done && stop.locked) {
    showToast('This delivery is already confirmed and cannot be changed. Please call the dairy office.', 'danger');
    return;
  }

  currentDelivery = stop;
  document.getElementById('exec-delivery-id').value = stop.delivery_id;
  document.getElementById('exec-stop-label').innerText = `Stop ${stop.sequence}${done ? ' • editing saved delivery' : ''}`;
  document.getElementById('exec-customer-name').innerText = stop.business_name;
  document.getElementById('exec-ordered-litres').innerText = (stop.items || []).map(i => `${qtyU(i.ordered, i.unit)} ${i.product_name}`).join(', ');
  renderExecItems(stop, done);
  document.getElementById('exec-shortage-reason').value = done && stop.shortage_reason && SHORT_REASONS[stop.shortage_reason] ? stop.shortage_reason : 'none';
  document.getElementById('exec-shortage-notes').value = done ? (stop.shortage_notes || '') : '';
  document.getElementById('exec-recipient-name').value = '';
  document.getElementById('exec-collected-amount').value = '';
  // A payment saved earlier is already in the customer's account; entering it again would count it twice
  document.getElementById('exec-collected-amount').placeholder = stop.collected_amount > 0
    ? `Already got ${money(stop.collected_amount)} — enter only new money` : '0';

  clearSignature();
  const photoInput = document.getElementById('exec-photo');
  photoInput.value = '';
  document.getElementById('exec-photo-preview').classList.add('d-none');
  const existingPhotos = (stop.photo_ids || []).length;
  document.getElementById('exec-photo-hint').innerText = existingPhotos
    ? `${existingPhotos} photo already saved. Take another only if needed.`
    : "Take a photo of the milk handed over at the customer's place.";
  syncShortBox();
  new bootstrap.Modal(document.getElementById('modalDeliveryExec')).show();
};

// Handle Delivery Confirmation Form Submission
const execForm = document.getElementById('form-delivery-exec');
if (execForm) {

  execForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const items = execItems();
    let shortageReason = document.getElementById('exec-shortage-reason').value;
    const shortageNotes = document.getElementById('exec-shortage-notes').value.trim();
    const recipientName = document.getElementById('exec-recipient-name').value.trim();
    const collectedAmount = parseFloat(document.getElementById('exec-collected-amount').value || 0);
    const paymentMethod = document.getElementById('exec-payment-method').value;

    for (const i of items) {
      if (isNaN(i.qty) || i.qty < 0) {
        showToast(`Enter how much ${i.name} was delivered.`, 'danger');
        return;
      }
      if (i.qty > i.ordered) {
        showToast(`${i.name}: cannot deliver more than ordered (${qtyU(i.ordered, i.unit)}).`, 'danger');
        return;
      }
      if (WHOLE.includes(i.unit) && !Number.isInteger(i.qty)) {
        showToast(`${i.name} is counted per ${i.unit}; enter a whole number.`, 'danger');
        return;
      }
    }
    const anyShort = items.some(i => i.qty < i.ordered);
    const nothing = items.every(i => i.qty <= 0);
    if (anyShort && shortageReason === 'none') {
      showToast('Select why less was delivered.', 'danger');
      return;
    }
    if (!anyShort) shortageReason = 'none';
    if (collectedAmount < 0) {
      showToast('Payment cannot be negative.', 'danger');
      return;
    }

    const deliveryId = parseInt(document.getElementById('exec-delivery-id').value);
    const photo = document.getElementById('exec-photo').files[0];
    const existingPhotos = (currentDelivery && currentDelivery.photo_ids || []).length;
    if (!photo && !existingPhotos) {
      showToast('Please take a delivery photo first.', 'danger');
      return;
    }
    if (!nothing && !hasSignature && !(currentDelivery && currentDelivery.has_signature)) {
      showToast("Please take the customer's signature.", 'danger');
      return;
    }
    const who = currentDelivery ? currentDelivery.business_name : 'this customer';
    const summary = nothing
      ? `NOTHING delivered to ${who}`
      : `Delivered to ${who}: ${items.filter(i => i.qty > 0).map(i => `${qtyU(i.qty, i.unit)} ${i.name}`).join(', ')}` +
        (anyShort ? ` (less than ordered)` : '');
    if (!confirm(`Confirm: ${summary}` + (collectedAmount > 0 ? `, ${money(collectedAmount)} collected` : '') +
        `?\n\nOnce confirmed you cannot change it.`)) return;

    // Only send a signature that was actually drawn (a blank canvas is not a signature)
    const signatureData = hasSignature && signatureCanvas ? signatureCanvas.toDataURL('image/png') : null;

    const payload = {
      delivery_id: deliveryId,
      items: items.map(i => ({ item_id: i.item_id, delivered_quantity: i.qty })),
      shortage_reason: shortageReason,
      shortage_notes: shortageNotes,
      recipient_name: recipientName,
      signature_data_url: signatureData,
      collected_amount: collectedAmount,
      payment_method: paymentMethod
    };

    const submitBtn = document.getElementById('exec-submit');
    const btnHtml = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Saving...';
    try {
      if (photo) await DairyAPI.uploadDeliveryPhoto(deliveryId, photo);
      await DairyAPI.completeDelivery(payload);
      bootstrap.Modal.getInstance(document.getElementById('modalDeliveryExec')).hide();
      const name = currentDelivery ? currentDelivery.business_name : 'customer';
      showToast(!nothing
        ? `Saved: delivered to ${name}${collectedAmount > 0 ? `, ${money(collectedAmount)} collected` : ''}.`
        : `Saved: nothing delivered to ${name}.`);
      await loadDriverDeliveries();
    } catch (err) {
      showToast('Could not save delivery: ' + err.message, 'danger');
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = btnHtml;
    }
  });

  document.getElementById('exec-photo').addEventListener('change', (e) => {
    const file = e.target.files[0];
    const preview = document.getElementById('exec-photo-preview');
    if (!file) {
      preview.classList.add('d-none');
      return;
    }
    preview.src = URL.createObjectURL(file);
    preview.classList.remove('d-none');
  });
}
