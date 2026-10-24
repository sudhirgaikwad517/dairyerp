import calendar
import json
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session, object_session

from backend.app.models.entities import (
    BusinessProfile, Customer, CustomerLedger, DeliveryClaim, CustomerPricing, Delivery, Invoice, Order, OrderItem, Payment, Product
)
from backend.app.services import notifications
from backend.app.services.order_lines import gst_split, litres_per_unit, order_lines

BILL_TYPES = ("daily", "fortnightly", "monthly", "custom")

# Bills count an order on the day it was ordered: milk delivered on the morning of the 24th is
# ordered on the 23rd (the cut-off may run past midnight, but it is still the 23rd's order), so it
# is billed on the 23rd. Bill periods and bill lines are in order days; deliveries stay as they are.
ORDER_TO_DELIVERY = timedelta(days=1)


def bill_day(delivery_day: date) -> date:
    """The day an order is billed on: the day before its delivery."""
    return delivery_day - ORDER_TO_DELIVERY


def delivery_range(start: date, end: date) -> Tuple[date, date]:
    """Delivery days whose orders fall in the bill period start..end."""
    return start + ORDER_TO_DELIVERY, end + ORDER_TO_DELIVERY


def order_days(inv: Optional[Invoice]) -> bool:
    """Is this bill in order days? Bills made before that rule are in delivery days."""
    return inv is None or inv.day_basis == "order"


def line_day(inv: Optional[Invoice], delivery_day: date) -> date:
    """The bill line (day) that holds a delivery day's milk in this bill."""
    return bill_day(delivery_day) if order_days(inv) else delivery_day

DEFAULT_PROFILE = {
    "business_name": "AKASH DAIRY FARM",
    "contact_numbers": "8329202372/9975541428",
    "address": "",
    "gstin": "",
    "bank_account_name": "AKASH DAIRY FARM",
    "bank_name": "HDFC BANK",
    "bank_account_number": "50200065045342",
    "bank_ifsc": "HDFC000825",
    "bank_branch": "HINGNE KHURD PUNE",
    "upi_number": "9975541428",
    "order_cutoff_time": "21:00",
    "dispatch_time": "04:00",
}


def get_business_profile(db: Session) -> BusinessProfile:
    profile = db.query(BusinessProfile).first()
    if not profile:
        profile = BusinessProfile(**DEFAULT_PROFILE)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    elif not profile.order_cutoff_time or not profile.dispatch_time:  # saved before these options existed
        profile.order_cutoff_time = profile.order_cutoff_time or DEFAULT_PROFILE["order_cutoff_time"]
        profile.dispatch_time = profile.dispatch_time or "04:00"
        db.commit()
    return profile


def resolve_bill_period(
    bill_type: str,
    ref_date: Optional[date],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Tuple[date, date]:
    """
    daily       -> the given day
    fortnightly -> 1st-15th or 16th-month end, whichever half contains the date
    monthly     -> the whole month containing the date
    custom      -> start_date..end_date
    """
    ref = ref_date or date.today()
    if bill_type == "daily":
        return ref, ref
    if bill_type == "fortnightly":
        if ref.day <= 15:
            return ref.replace(day=1), ref.replace(day=15)
        return ref.replace(day=16), ref.replace(day=calendar.monthrange(ref.year, ref.month)[1])
    if bill_type == "monthly":
        return ref.replace(day=1), ref.replace(day=calendar.monthrange(ref.year, ref.month)[1])
    if bill_type == "custom":
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="From and To dates are required for a custom bill")
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="From date must be on or before To date")
        if (end_date - start_date).days > 61:
            raise HTTPException(status_code=400, detail="A custom bill can cover at most 62 days")
        return start_date, end_date
    raise HTTPException(status_code=400, detail=f"Bill type must be one of {', '.join(BILL_TYPES)}")


def period_label(bill_type: str, start: date, end: date) -> str:
    """Label printed on the bill, e.g. 'SEP 2026', '01-15 SEP 2026', '30 SEP 2026'."""
    if bill_type == "monthly":
        return start.strftime("%b %Y").upper()
    if start == end:
        return start.strftime("%d %b %Y").upper()
    if start.year == end.year and start.month == end.month:
        return f"{start.day:02d}-{end.day:02d} {start.strftime('%b %Y').upper()}"
    if start.year == end.year:
        return f"{start:%d %b} - {end:%d %b %Y}".upper()
    return f"{start:%d %b %Y} - {end:%d %b %Y}".upper()


def main_product(db: Session, customer_id: int) -> Optional[Product]:
    """The customer's usual product: the one on their latest order, else the first active litre product."""
    item = (db.query(OrderItem).join(Order, Order.id == OrderItem.order_id)
            .filter(Order.customer_id == customer_id, Order.status != "cancelled")
            .order_by(Order.delivery_date.desc(), OrderItem.id.asc()).first())
    if item:
        p = db.query(Product).filter(Product.id == item.product_id).first()
        if p:
            return p
    return (db.query(Product).filter(Product.unit == "L", Product.is_active == True).order_by(Product.id).first()
            or db.query(Product).filter(Product.is_active == True).order_by(Product.id).first())


def customer_rate(db: Session, customer_id: int, product: Optional[Product] = None) -> float:
    """Customer's current rate for a product (their usual product when not given)."""
    product = product or main_product(db, customer_id)
    if not product:
        return 0.0
    cp = db.query(CustomerPricing).filter(
        CustomerPricing.customer_id == customer_id, CustomerPricing.product_id == product.id).first()
    return cp.custom_price if cp else product.standard_b2b_price


def claims_to_deduct(db: Session, customer_id: int, start: date, end: date, invoice_id: Optional[int] = None,
                     all_approved: bool = False):
    """
    Approved claims that reduce this period's bill: those not yet settled anywhere, plus (when
    re-reading an existing bill) the ones already deducted in that bill.
    """
    first, last = delivery_range(start, end)  # claims are about a delivery day
    q = db.query(DeliveryClaim).filter(
        DeliveryClaim.customer_id == customer_id,
        DeliveryClaim.status == "approved",
        DeliveryClaim.issue_date >= first,
        DeliveryClaim.issue_date <= last,
    )
    claims = [c for c in q.all() if c.settlement != "refund"]  # refunded separately: never deducted
    if all_approved:
        return claims
    return [c for c in claims if c.settlement is None or (invoice_id and c.settlement == "bill" and c.invoice_id == invoice_id)]


def compute_bill_lines(db: Session, customer: Customer, start: date, end: date, invoice_id: Optional[int] = None,
                       all_approved_claims: bool = False, skip_days: Optional[set] = None) -> List[Dict]:
    """
    Day-wise lines for the period: for each order day, one line per product delivered (quantity,
    rate, amount). An order is on the day before its delivery (bill_day). A day with nothing
    delivered gets one empty line for the customer's usual product, so the bill reads like the
    dairy's register. Only what was actually delivered is billed, per product. Approved claims
    (spoiled / short / not delivered) are deducted from their order's day and product.
    Rates include GST. Days in skip_days (already in another bill) get no lines.
    """
    skip_days = skip_days or set()
    first, last = delivery_range(start, end)
    orders = db.query(Order).filter(
        Order.customer_id == customer.id,
        Order.delivery_date >= first,
        Order.delivery_date <= last,
        Order.status.in_(["delivered", "invoiced", "paid"])
    ).all()
    products = {p.id: p for p in db.query(Product).all()}
    per_order = order_lines(db, orders, products)

    by_day: Dict[date, Dict[int, Dict]] = {}
    for o in orders:
        for r in per_order.get(o.id, []):
            if r["delivered"] <= 0:
                continue
            slot = by_day.setdefault(bill_day(o.delivery_date), {}).setdefault(
                r["product_id"], {"qty": 0.0, "amount": 0.0, "gst_rate": r["gst_rate"]})
            slot["qty"] += r["delivered"]
            slot["amount"] += r["amount"]

    claim_by: Dict[tuple, Dict[str, float]] = {}
    for c in claims_to_deduct(db, customer.id, start, end, invoice_id, all_approved=all_approved_claims):
        cd = claim_by.setdefault((bill_day(c.issue_date), c.product_id), {"qty": 0.0, "amount": 0.0})
        cd["qty"] += c.approved_qty or 0.0
        cd["amount"] += c.credit_amount or 0.0

    usual = main_product(db, customer.id)
    order_key = lambda pid: (products[pid].sort_order or 0, pid) if pid in products else (0, pid)
    lines = []
    day = start
    while day <= end:
        if day in skip_days:
            day += timedelta(days=1)
            continue
        todays = dict(by_day.get(day, {}))
        for (cday, pid) in claim_by:
            if cday == day and pid not in todays:
                todays[pid] = {"qty": 0.0, "amount": 0.0, "gst_rate": 0.0}  # claim on a day with no sale (should not happen)
        if not todays and usual:
            todays = {usual.id: {"qty": 0.0, "amount": 0.0, "gst_rate": usual.gst_rate or 0.0}}
        for pid in sorted(todays, key=order_key):
            d = todays[pid]
            p = products.get(pid)
            claim = claim_by.get((day, pid), {"qty": 0.0, "amount": 0.0})
            qty = round(max(0.0, d["qty"] - claim["qty"]), 3)
            amount = round(max(0.0, d["amount"] - claim["amount"]), 2)
            if qty > 0:
                rate = round(amount / qty, 2)
            elif d["qty"] > 0:
                rate = round(d["amount"] / d["qty"], 2)
            else:
                rate = round(customer_rate(db, customer.id, p) if p else 0.0, 2)
            lines.append({"date": day.isoformat(), "product_id": pid, "product": p.product_name if p else "Product",
                          "unit": p.unit if p else "", "litres_per_unit": litres_per_unit(p),
                          "qty": qty, "rate": rate, "amount": amount,
                          "gst_rate": d["gst_rate"] or 0.0,
                          "claim_qty": round(claim["qty"], 3), "claim_amount": round(claim["amount"], 2)})
        day += timedelta(days=1)
    return lines


def _lpu(line: Dict) -> float:
    """Litres in one unit of a bill line (lines saved before pack sizes existed: 1 for litres)."""
    if line.get("litres_per_unit") is not None:
        return line["litres_per_unit"]
    return 1.0 if (line.get("unit") or "").upper() == "L" else 0.0


def product_summary(lines: List[Dict]) -> List[Dict]:
    """Per product: quantity, amount and rate (average if the rate changed in the period)."""
    out: Dict[int, Dict] = {}
    for l in lines:
        p = out.setdefault(l.get("product_id"), {"product_id": l.get("product_id"), "product": l.get("product", "Milk"),
                                                  "unit": l.get("unit", "L"), "litres_per_unit": _lpu(l),
                                                  "qty": 0.0, "amount": 0.0, "rates": set(),
                                                  "claim_qty": 0.0, "claim_amount": 0.0})
        p["qty"] += l["qty"]
        p["amount"] += l["amount"]
        p["claim_qty"] += l.get("claim_qty", 0.0)
        p["claim_amount"] += l.get("claim_amount", 0.0)
        if l["qty"] > 0:
            p["rates"].add(l["rate"])
    result = []
    for p in out.values():
        if p["qty"] <= 0 and p["claim_qty"] <= 0 and len(out) > 1:
            continue  # an empty filler line for a product not bought in the period
        rates = p.pop("rates")
        p["qty"] = round(p["qty"], 3)
        p["amount"] = round(p["amount"], 2)
        p["claim_qty"] = round(p["claim_qty"], 3)
        p["claim_amount"] = round(p["claim_amount"], 2)
        p["mixed_rates"] = len(rates) > 1
        p["rate"] = next(iter(rates)) if len(rates) == 1 else (round(p["amount"] / p["qty"], 2) if p["qty"] else 0.0)
        result.append(p)
    return result


def what_text(summary: List[Dict]) -> str:
    """'300 L Cow Milk, 12 kg Paneer' for a bill or statement."""
    parts = [f"{round(p['qty'], 3):g} {p['unit']} {p['product']}".strip() for p in summary if p["qty"] > 0]
    return ", ".join(parts) if parts else "nothing delivered"


def gst_summary(db: Session, lines: List[Dict]) -> List[Dict]:
    """GST inside the bill, per rate (only when the dairy has a GSTIN; rates include GST)."""
    profile = get_business_profile(db)
    if not (profile.gstin or "").strip():
        return []
    groups: Dict[float, Dict] = {}
    for l in lines:
        r = l.get("gst_rate") or 0.0
        if r <= 0 or l["amount"] <= 0:
            continue
        g = groups.setdefault(r, {"gst_rate": r, "amount": 0.0})
        g["amount"] += l["amount"]
    out = []
    for r, g in sorted(groups.items()):
        split = gst_split(g["amount"], r)
        half = round(split["gst"] / 2, 2)
        out.append({"gst_rate": r, "amount": round(g["amount"], 2), "taxable": split["taxable"],
                    "cgst": half, "sgst": round(split["gst"] - half, 2), "gst": split["gst"]})
    return out


def summarize_lines(lines: List[Dict]) -> Dict:
    """
    Bill totals. With one product, total_qty / rate are that product's (as before). With several
    products, total_qty is the litres of milk only and rate is None; see product_summary.
    """
    summary = product_summary(lines)
    total_amount = round(sum(l["amount"] for l in lines), 2)
    if len(summary) <= 1:
        p = summary[0] if summary else {"qty": 0.0, "rate": lines[0]["rate"] if lines else 0.0, "mixed_rates": False}
        return {"total_qty": p["qty"], "total_amount": total_amount, "rate": p["rate"], "mixed_rates": p["mixed_rates"],
                "products": summary, "multi_product": False}
    litres = round(sum(p["qty"] * p["litres_per_unit"] for p in summary), 3)
    return {"total_qty": litres, "total_amount": total_amount, "rate": None, "mixed_rates": True,
            "products": summary, "multi_product": True}


def recalculate_ledger(db: Session, customer: Customer) -> None:
    """Recompute running balances in date order and set the customer's outstanding to the closing balance."""
    db.flush()
    entries = db.query(CustomerLedger).filter(CustomerLedger.customer_id == customer.id).order_by(
        CustomerLedger.transaction_date.asc(), CustomerLedger.id.asc()
    ).all()
    balance = 0.0
    for e in entries:
        balance = round(balance + (e.debit_amount or 0.0) - (e.credit_amount or 0.0), 2)
        e.running_balance = balance
    customer.current_outstanding = balance


def covered_days(inv: Invoice) -> set:
    """Order days this bill holds: its saved day lines (older bills are in delivery days)."""
    try:
        days = {date.fromisoformat(l["date"]) for l in json.loads(inv.bill_lines or "[]")}
    except (ValueError, KeyError, TypeError):
        days = set()
    if not days and inv.period_start and inv.period_end:
        days = {inv.period_start + timedelta(days=i) for i in range((inv.period_end - inv.period_start).days + 1)}
    return days if order_days(inv) else {bill_day(d) for d in days}


def bills_holding_days(db: Session, customer_id: int, start: date, end: date) -> Dict[Invoice, set]:
    """Bills that already hold some order days of start..end, with those days."""
    candidates = db.query(Invoice).filter(
        Invoice.customer_id == customer_id,
        Invoice.bill_type.isnot(None),
        Invoice.period_start <= end + ORDER_TO_DELIVERY,  # older bills are in delivery days
        Invoice.period_end >= start
    ).order_by(Invoice.period_start).all()
    out = {}
    for inv in candidates:
        days = {d for d in covered_days(inv) if start <= d <= end}
        if days:
            out[inv] = days
    return out


def bill_for_delivery_day(db: Session, customer_id: int, delivery_day: date) -> Optional[Invoice]:
    """The bill that holds the order delivered on this day (billed on the day before; older bills on the day)."""
    day = bill_day(delivery_day)
    return next(iter(bills_holding_days(db, customer_id, day, day)), None)


def unbilled_amounts(db: Session, customer_ids: Optional[List[int]] = None) -> Dict[int, float]:
    """
    customer id -> amount for milk already delivered that no bill holds yet (less approved claims
    waiting for that bill). Dues count it at once; making the bill only moves it into the ledger.
    """
    q = db.query(Order).filter(Order.status.in_(["delivered", "invoiced", "paid"]))
    bq = db.query(Invoice).filter(Invoice.bill_type.isnot(None), Invoice.period_start.isnot(None))
    cq = db.query(DeliveryClaim).filter(DeliveryClaim.status == "approved", DeliveryClaim.settlement.is_(None))
    if customer_ids is not None:
        q = q.filter(Order.customer_id.in_(customer_ids))
        bq = bq.filter(Invoice.customer_id.in_(customer_ids))
        cq = cq.filter(DeliveryClaim.customer_id.in_(customer_ids))
    billed_days: Dict[int, set] = {}
    for inv in bq.all():
        billed_days.setdefault(inv.customer_id, set()).update(covered_days(inv))

    def billed(cid: int, delivery_day: date) -> bool:
        return bill_day(delivery_day) in billed_days.get(cid, set())

    orders = [o for o in q.all() if not billed(o.customer_id, o.delivery_date)]
    lines = order_lines(db, orders)
    out: Dict[int, float] = {}
    for o in orders:
        out[o.customer_id] = out.get(o.customer_id, 0.0) + sum(r["amount"] for r in lines.get(o.id, []))
    for c in cq.all():
        if c.customer_id in out and not billed(c.customer_id, c.issue_date):
            out[c.customer_id] -= c.credit_amount or 0.0
    return {cid: round(max(0.0, v), 2) for cid, v in out.items() if round(v, 2) > 0}


def outstanding_parts(db: Session, customer: Customer, unbilled: Optional[float] = None) -> Dict[str, float]:
    """Billed balance (ledger), delivered-not-billed amount and the total the customer owes now."""
    billed = round(customer.current_outstanding or 0.0, 2)
    if unbilled is None:
        unbilled = unbilled_amounts(db, [customer.id]).get(customer.id, 0.0)
    return {"billed_outstanding": billed, "unbilled_amount": unbilled, "current_outstanding": round(billed + unbilled, 2)}


def preview_bills(db: Session, bill_type: str, start: date, end: date, customer_ids: Optional[List[int]] = None) -> List[Dict]:
    query = db.query(Customer)
    if customer_ids:
        query = query.filter(Customer.id.in_(customer_ids))
    result = []
    period_days = {start + timedelta(days=i) for i in range((end - start).days + 1)}
    for c in query.order_by(Customer.customer_code).all():
        # Days already in another bill (say a daily bill inside this month) are left out of this one
        held = bills_holding_days(db, c.id, start, end)
        skip = set().union(*held.values()) if held else set()
        lines = compute_bill_lines(db, c, start, end, skip_days=skip)
        s = summarize_lines(lines)
        delivered_anything = any(l["qty"] > 0 for l in lines)
        # Inactive customers still get billed for milk delivered before they were deactivated
        if not c.is_active and not delivered_anything and not customer_ids:
            continue
        held_numbers = ", ".join(inv.invoice_number for inv in held)
        prev = round(c.current_outstanding or 0.0, 2)
        first, last = delivery_range(start, end)
        # Orders in the period that are not delivered yet: billing now would leave them out for good
        undelivered = sum(1 for o in db.query(Order).filter(
            Order.customer_id == c.id, Order.delivery_date >= first, Order.delivery_date <= last,
            Order.status.notin_(["delivered", "invoiced", "paid", "cancelled"]), Order.total_amount > 0,
        ).all() if bill_day(o.delivery_date) not in skip)
        pending_claims = sum(1 for cl in db.query(DeliveryClaim).filter(
            DeliveryClaim.customer_id == c.id, DeliveryClaim.status == "pending",
            DeliveryClaim.issue_date >= first, DeliveryClaim.issue_date <= last
        ).all() if bill_day(cl.issue_date) not in skip)
        result.append({
            "customer_id": c.id,
            "customer_code": c.customer_code,
            "business_name": c.business_name,
            "total_qty": s["total_qty"],
            "rate": s["rate"],
            "mixed_rates": s["mixed_rates"],
            "multi_product": s["multi_product"],
            "products": s["products"],
            "what": what_text(s["products"]),
            "delivered_anything": delivered_anything,
            "amount": s["total_amount"],
            "previous_balance": prev,
            "total_payable": round(s["total_amount"] + prev, 2),
            "already_billed": held_numbers if period_days <= skip else None,
            # Some days are in other bills: this bill holds only the rest
            "partly_billed": held_numbers if skip and not period_days <= skip else None,
            "skip_days": sorted(d.isoformat() for d in skip),
            "claims_deducted_qty": round(sum(l["claim_qty"] for l in lines), 3),
            "claims_deducted_amount": round(sum(l["claim_amount"] for l in lines), 2),
            "pending_claims": pending_claims,
            "undelivered_orders": undelivered,
        })
    return result


def generate_bills(db: Session, bill_type: str, start: date, end: date, customer_ids: Optional[List[int]] = None) -> Dict:
    created, skipped = [], []
    today = date.today()
    if delivery_range(start, end)[1] > today:
        # Orders of the last day are delivered the next morning, and a billed period cannot be billed again
        last = delivery_range(start, end)[1]
        raise HTTPException(status_code=400, detail=(
            f"This period runs till {end:%d %b %Y}; its last orders are delivered on {last:%d %b %Y}. "
            f"Make the bill after that delivery, or choose a custom period up to "
            f"{today - ORDER_TO_DELIVERY:%d %b %Y}."))
    for row in preview_bills(db, bill_type, start, end, customer_ids):
        if row["already_billed"]:
            skipped.append({**row, "reason": f"Already billed in {row['already_billed']}"})
            continue
        if row["undelivered_orders"]:
            skipped.append({**row, "reason": f"{row['undelivered_orders']} order(s) in this period not delivered yet"})
            continue
        if not row["delivered_anything"]:
            skipped.append({**row, "reason": "Nothing delivered in this period"})
            continue

        customer = db.query(Customer).filter(Customer.id == row["customer_id"]).first()
        skip = {date.fromisoformat(d) for d in row["skip_days"]}
        lines = compute_bill_lines(db, customer, start, end, skip_days=skip)
        prefix = {"daily": "D", "fortnightly": "F", "monthly": "M", "custom": "C"}[bill_type]
        number = f"BILL-{start.strftime('%Y%m%d')}-{customer.customer_code[-3:]}-{prefix}"
        amount = row["amount"]
        prev = row["previous_balance"]
        # An advance already in the customer's account pays (part of) this bill straight away
        advance = round(min(max(0.0, -prev), amount), 2)

        inv = Invoice(
            invoice_number=number, customer_id=customer.id, branch_id=customer.branch_id,
            invoice_date=today, due_date=today + timedelta(days=customer.credit_days or 0),
            total_litres=round(sum(p["qty"] * p["litres_per_unit"] for p in row["products"]), 3),
            subtotal=amount, total_tax=0.0, transport_charge=0.0,
            total_amount=amount, paid_amount=0.0, balance_due=amount, payment_status="pending",
            bill_type=bill_type, period_start=start, period_end=end, previous_balance=prev,
            advance_applied=advance, bill_lines=json.dumps(lines), day_basis="order"
        )
        db.add(inv)
        db.add(CustomerLedger(
            customer_id=customer.id, transaction_date=today, transaction_type="sales_invoice",
            reference_number=number, debit_amount=amount, credit_amount=0.0, running_balance=0.0,
            narration=f"Bill {period_label(bill_type, start, end)} ({row['what']})"
                      + (f"; days in {row['partly_billed']} left out" if row["partly_billed"] else "")
        ))
        recalculate_ledger(db, customer)
        db.flush()
        # Claims deducted in this bill are now settled by it
        for claim in claims_to_deduct(db, customer.id, start, end):
            if bill_day(claim.issue_date) in skip:
                continue
            claim.settlement = "bill"
            claim.invoice_id = inv.id
        gst = gst_summary(db, lines)
        inv.cgst_amount = round(sum(g["cgst"] for g in gst), 2)
        inv.sgst_amount = round(sum(g["sgst"] for g in gst), 2)
        inv.total_tax = round(inv.cgst_amount + inv.sgst_amount, 2)
        refresh_bill(db, inv)
        notifications.bill_created(db, inv, period_label(bill_type, start, end), advance, row["what"])
        created.append({**row, "bill_id": inv.id, "invoice_number": number})

    db.commit()
    return {"created": created, "skipped": skipped}


def delete_bill(db: Session, invoice: Invoice) -> None:
    if (invoice.paid_amount or 0) > 0:
        moved_in = db.query(DeliveryClaim).filter(DeliveryClaim.excess_moves.like(f'%"{invoice.id}"%')).first()
        if moved_in:
            raise HTTPException(status_code=400, detail=(
                f"Part of this bill is paid by claim {moved_in.claim_number} (credit from another bill that was "
                f"already paid). Undo that claim first, then delete this bill."))
        raise HTTPException(status_code=400, detail="This bill has payments recorded against it and cannot be deleted")
    customer = invoice.customer
    # Claims deducted in this bill (at creation or later by credit note) go back to
    # "to be deducted in the next bill", so making the bill again deducts them inside it.
    for claim in db.query(DeliveryClaim).filter(DeliveryClaim.invoice_id == invoice.id).all():
        if claim.settlement == "credit_note":
            # Its credit entry goes too; the claim is deducted inside the bill when it is made again
            db.query(CustomerLedger).filter(
                CustomerLedger.customer_id == invoice.customer_id,
                CustomerLedger.reference_number == claim.claim_number,
                CustomerLedger.transaction_type == "credit_note",
            ).delete()
        claim.settlement = None
        claim.invoice_id = None
    db.query(CustomerLedger).filter(
        CustomerLedger.customer_id == invoice.customer_id,
        CustomerLedger.reference_number == invoice.invoice_number
    ).delete()
    notifications.bill_cancelled(db, invoice)
    db.delete(invoice)
    recalculate_ledger(db, customer)
    db.commit()


def credit_claims(db: Session, inv: Invoice) -> List[DeliveryClaim]:
    """Claims approved after this bill was made, paid back by a credit note against it."""
    return db.query(DeliveryClaim).filter(
        DeliveryClaim.invoice_id == inv.id, DeliveryClaim.settlement == "credit_note"
    ).all()


def bill_figures(db: Session, inv: Invoice) -> Dict[str, float]:
    gross = round(inv.total_amount or 0.0, 2)
    credits = round(sum(c.credit_amount or 0.0 for c in credit_claims(db, inv)), 2)
    net = round(gross - credits, 2)
    advance = round(inv.advance_applied or 0.0, 2)
    paid = round(inv.paid_amount or 0.0, 2)
    return {"gross": gross, "credits": credits, "net": net, "advance": advance, "paid": paid,
            "balance": round(max(0.0, net - advance - paid), 2),
            # Paid more than the bill now asks for (e.g. a claim credited after full payment);
            # it stays in the ledger as advance for the next bill
            "excess": round(max(0.0, advance + paid - net), 2)}


def refresh_bill(db: Session, inv: Invoice) -> None:
    """Keep the bill's balance and status in step with later claim credits and payments."""
    db.flush()
    f = bill_figures(db, inv)
    inv.balance_due = f["balance"]
    if f["balance"] <= 0:
        inv.payment_status = "paid"
    elif f["paid"] + f["advance"] > 0:
        inv.payment_status = "partial"
    else:
        inv.payment_status = "pending"


def apply_payment_to_bills(db: Session, customer_id: int, amount: float, first: Optional[Invoice] = None) -> Optional[int]:
    """
    Spread a payment over the customer's unpaid bills: the given bill first, then oldest first.
    Anything left over stays in the ledger as advance. Returns the first bill it was applied to.
    """
    remaining = round(amount, 2)
    bills = db.query(Invoice).filter(
        Invoice.customer_id == customer_id, Invoice.bill_type.isnot(None), Invoice.balance_due > 0
    ).order_by(Invoice.period_start.asc(), Invoice.id.asc()).all()
    if first is not None:
        bills = [first] + [b for b in bills if b.id != first.id]
    first_id = None
    for bill in bills:
        if remaining <= 0:
            break
        due = bill_figures(db, bill)["balance"]
        if due <= 0:
            continue
        part = round(min(due, remaining), 2)
        bill.paid_amount = round((bill.paid_amount or 0.0) + part, 2)
        refresh_bill(db, bill)
        remaining = round(remaining - part, 2)
        first_id = first_id or bill.id
    return first_id


def move_excess_to_other_bills(db: Session, inv: Invoice) -> Dict[str, float]:
    """
    A claim credited after a bill was paid leaves that bill over-paid. The extra money belongs to the
    customer, so it pays their other unpaid bills (oldest first) right away; only what is left after
    that stays on this bill as advance. Without this, the bills would still show the old dues while
    the ledger already counts the credit. Returns what was moved, {"advance": x, "<bill id>": amount},
    so that undoing the claim can put every rupee back where it was (undo_excess_move).
    """
    f = bill_figures(db, inv)
    excess = f["excess"]
    if excess <= 0:
        return {}
    others = db.query(Invoice).filter(
        Invoice.customer_id == inv.customer_id, Invoice.bill_type.isnot(None),
        Invoice.id != inv.id, Invoice.balance_due > 0,
    ).order_by(Invoice.period_start.asc(), Invoice.id.asc()).all()
    room = round(sum(bill_figures(db, b)["balance"] for b in others), 2)
    move = round(min(excess, room), 2)
    if move <= 0:
        return {}
    # Take the extra off this bill: unused advance first, then money paid
    from_advance = round(min(move, f["advance"]), 2)
    inv.advance_applied = round((inv.advance_applied or 0.0) - from_advance, 2)
    inv.paid_amount = round((inv.paid_amount or 0.0) - (move - from_advance), 2)
    refresh_bill(db, inv)
    moves: Dict[str, float] = {"advance": from_advance}
    left = move
    for bill in others:
        if left <= 0:
            break
        due = bill_figures(db, bill)["balance"]
        part = round(min(due, left), 2)
        if part <= 0:
            continue
        bill.paid_amount = round((bill.paid_amount or 0.0) + part, 2)
        refresh_bill(db, bill)
        moves[str(bill.id)] = part
        left = round(left - part, 2)
    return moves


def undo_excess_move(db: Session, inv: Invoice, moves: Dict[str, float]) -> None:
    """Reverse move_excess_to_other_bills: the money goes back from the other bills to this bill."""
    total = 0.0
    for key, amount in moves.items():
        if key == "advance":
            continue
        other = db.query(Invoice).filter(Invoice.id == int(key)).first()
        if other:
            other.paid_amount = round(max(0.0, (other.paid_amount or 0.0) - amount), 2)
            refresh_bill(db, other)
        total = round(total + amount, 2)
    from_advance = round(moves.get("advance", 0.0), 2)
    inv.advance_applied = round((inv.advance_applied or 0.0) + from_advance, 2)
    inv.paid_amount = round((inv.paid_amount or 0.0) + total - from_advance, 2)
    refresh_bill(db, inv)


def record_bill_payment(db: Session, invoice: Invoice, amount: float, pay_date: date, method: str, reference: Optional[str]) -> Payment:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")
    customer = invoice.customer
    number = f"PAY-{pay_date.strftime('%Y%m%d')}-{db.query(Payment).count() + 1:04d}"
    payment = Payment(
        payment_number=number, customer_id=customer.id, invoice_id=invoice.id, payment_date=pay_date,
        amount=amount, payment_method=method, reference_number=reference,
        remarks=f"Against {invoice.invoice_number}"
    )
    db.add(payment)
    db.add(CustomerLedger(
        customer_id=customer.id, transaction_date=pay_date, transaction_type="payment",
        reference_number=number, debit_amount=0.0, credit_amount=amount, running_balance=0.0,
        narration=f"Payment received ({method}) against {invoice.invoice_number}"
    ))
    apply_payment_to_bills(db, customer.id, amount, first=invoice)
    recalculate_ledger(db, customer)
    notifications.payment_received(db, customer, amount, method, pay_date, bill_number=invoice.invoice_number)
    db.commit()
    return payment


def claim_adjustments(db: Session, customer_id: int, start: date, end: date, lines: List[Dict],
                      deducted: List[DeliveryClaim], inv: Optional[Invoice] = None) -> List[Dict]:
    """
    One row per approved claim in the period for the bill's "Claim Adjustments" table:
    the day's original quantity, the claim, and what was billed. Refunded claims are listed too
    (marked as refunded) so the bill is a complete record, but they do not change any amount.
    """
    by_key = {(l["date"], l.get("product_id")): l for l in lines}
    first, last = delivery_range(start, end) if order_days(inv) else (start, end)
    refunded = db.query(DeliveryClaim).filter(
        DeliveryClaim.customer_id == customer_id, DeliveryClaim.status == "approved",
        DeliveryClaim.settlement == "refund",
        DeliveryClaim.issue_date >= first, DeliveryClaim.issue_date <= last,
    ).all()
    rows = []
    for c in sorted(deducted + refunded, key=lambda x: (x.issue_date, x.id)):
        day = line_day(inv, c.issue_date).isoformat()  # the bill line of that delivery's order
        line = by_key.get((day, c.product_id), {})
        original = round(line.get("qty", 0.0) + line.get("claim_qty", 0.0), 3)
        rows.append({
            "date": day,
            "delivery_date": c.issue_date.isoformat(),
            "product": line.get("product", ""),
            "unit": line.get("unit", ""),
            "claim_number": c.claim_number,
            "reason": c.reason,
            "original_qty": original,
            "claim_qty": c.approved_qty,
            "final_qty": line.get("qty", original),
            "rate": c.rate,
            "amount": c.credit_amount,
            "mode": "refunded" if c.settlement == "refund" else "deducted",
        })
    return rows


def bill_to_dict(inv: Invoice) -> Dict:
    """
    A bill as it stands now: the lines saved when it was made, minus claims credited afterwards,
    with payments received so far and the customer's current total outstanding.
    """
    db = object_session(inv)
    c = inv.customer
    lines = [dict(l) for l in (json.loads(inv.bill_lines) if inv.bill_lines else [])]
    for l in lines:
        l.setdefault("claim_qty", 0.0)
        l.setdefault("claim_amount", 0.0)
        l.setdefault("gst_rate", 0.0)
    by_key = {(l["date"], l.get("product_id")): l for l in lines}
    for claim in credit_claims(db, inv):
        line = by_key.get((line_day(inv, claim.issue_date).isoformat(), claim.product_id))
        if not line:
            continue
        line["qty"] = round(max(0.0, line["qty"] - (claim.approved_qty or 0.0)), 2)
        line["amount"] = round(max(0.0, line["amount"] - (claim.credit_amount or 0.0)), 2)
        line["claim_qty"] = round(line["claim_qty"] + (claim.approved_qty or 0.0), 2)
        line["claim_amount"] = round(line["claim_amount"] + (claim.credit_amount or 0.0), 2)
    for l in lines:
        l["original_qty"] = round(l["qty"] + l["claim_qty"], 3)
    s = summarize_lines(lines) if lines else {"rate": 0.0, "mixed_rates": False, "total_qty": inv.total_litres,
                                              "products": [], "multi_product": False}
    f = bill_figures(db, inv)
    prev = inv.previous_balance or 0.0
    parts = outstanding_parts(db, c) if c else {"current_outstanding": 0.0, "unbilled_amount": 0.0}
    current = parts["current_outstanding"]
    deducted_claims = db.query(DeliveryClaim).filter(
        DeliveryClaim.invoice_id == inv.id, DeliveryClaim.settlement.in_(["bill", "credit_note"])
    ).all()
    claims_amount = round(sum(l["claim_amount"] for l in lines), 2)
    claims_qty = round(sum(l["claim_qty"] for l in lines), 3)
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "bill_type": inv.bill_type,
        "period_start": inv.period_start.isoformat() if inv.period_start else None,
        "period_end": inv.period_end.isoformat() if inv.period_end else None,
        "period_label": period_label(inv.bill_type, inv.period_start, inv.period_end) if inv.period_start else "",
        "invoice_date": inv.invoice_date.isoformat(),
        "due_date": inv.due_date.isoformat(),
        "customer_id": inv.customer_id,
        "customer_code": c.customer_code if c else "",
        "customer_name": c.business_name if c else "",
        "customer_phone": c.phone if c else "",
        "customer_address": c.delivery_address if c else "",
        "total_qty": s["total_qty"],
        "original_qty": round(s["total_qty"] + claims_qty, 3) if not s["multi_product"] else None,
        "claims_qty": claims_qty,
        "rate": s["rate"],
        "mixed_rates": s["mixed_rates"],
        "multi_product": s["multi_product"],
        "products": s["products"],
        "what": what_text(s["products"]),
        "gst": gst_summary(db, lines),
        # Amount for the milk as delivered, before claims; claims deducted; amount billed
        "original_amount": round(f["net"] + claims_amount, 2),
        "claims_amount": claims_amount,
        "gross_amount": f["gross"],
        "claims_credit": f["credits"],
        "amount": f["net"],
        "advance": f["advance"],
        "billing_amount": round(f["net"] - f["advance"], 2),
        "outstanding": round(max(0.0, prev), 2),
        "outstanding_label": "PREVIOUS OUTSTANDING",
        "paid_amount": f["paid"],
        "balance_due": f["balance"],
        "excess_paid": f["excess"],
        "payment_status": inv.payment_status,
        "current_outstanding": current,
        "unbilled_amount": parts["unbilled_amount"],
        "current_outstanding_label": f"TOTAL OUTSTANDING (AS ON {date.today():%d %b %Y})".upper(),
        "total_payable": round(max(0.0, prev) + f["net"] - f["advance"] - f["paid"], 2),
        "adjustments": claim_adjustments(db, inv.customer_id, inv.period_start, inv.period_end, lines, deducted_claims, inv)
        if inv.period_start else [],
        "lines": lines,
    }


def build_statement(db: Session, customer: Customer, bill_type: str, start: date, end: date) -> Dict:
    """
    A customer's own milk statement for any period, in the bill format. It is not a bill: nothing is
    saved and the ledger is not touched. Claims deducted from bills are deducted here too; refunded
    claims are listed but not deducted. The outstanding shown is the account balance as on today.
    """
    lines = compute_bill_lines(db, customer, start, end, all_approved_claims=True)
    for l in lines:
        l["original_qty"] = round(l["qty"] + l.get("claim_qty", 0.0), 3)
    s = summarize_lines(lines)
    parts = outstanding_parts(db, customer)
    balance = parts["current_outstanding"]  # includes milk delivered but not billed yet
    deducted = claims_to_deduct(db, customer.id, start, end, all_approved=True)
    claims_amount = round(sum(l.get("claim_amount", 0.0) for l in lines), 2)
    claims_qty = round(sum(l.get("claim_qty", 0.0) for l in lines), 3)
    return {
        "is_statement": True,
        "invoice_number": f"STATEMENT-{start:%Y%m%d}",
        "bill_type": bill_type,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "period_label": period_label(bill_type, start, end),
        "customer_name": customer.business_name,
        "customer_phone": customer.phone,
        "customer_address": customer.delivery_address,
        "customer_code": customer.customer_code,
        "total_qty": s["total_qty"],
        "rate": s["rate"],
        "mixed_rates": s["mixed_rates"],
        "multi_product": s["multi_product"],
        "products": s["products"],
        "what": what_text(s["products"]),
        "gst": gst_summary(db, lines),
        "amount": s["total_amount"],
        "advance": round(max(0.0, -balance), 2),
        "billing_amount": s["total_amount"],
        "outstanding": round(max(0.0, balance), 2),
        "outstanding_label": f"OUTSTANDING (AS ON {date.today():%d %b %Y})".upper(),
        "unbilled_amount": parts["unbilled_amount"],
        "total_payable": 0.0,
        "original_qty": round(s["total_qty"] + claims_qty, 3) if not s["multi_product"] else None,
        "claims_qty": claims_qty,
        "original_amount": round(s["total_amount"] + claims_amount, 2),
        "claims_amount": claims_amount,
        "adjustments": claim_adjustments(db, customer.id, start, end, lines, deducted),
        "lines": lines,
    }
