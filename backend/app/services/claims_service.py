"""Customer claims (spoiled / short / not delivered milk): validation, admin decision and settlement."""
import json
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    AuditLog, Customer, CustomerLedger, Delivery, DeliveryClaim, Invoice, Order, OrderItem, Product, User
)
from backend.app.services import notifications
from backend.app.services.attachments import attachments_for
from backend.app.services.order_lines import order_lines, whole_unit
from backend.app.services.billing_service import (bill_figures, bill_for_delivery_day, line_day, move_excess_to_other_bills,
                                                  recalculate_ledger, refresh_bill, undo_excess_move)

CLAIM_REASONS = {
    "spoiled": "Milk spoiled / bad quality",
    "short_delivered": "Less milk delivered",
    "not_delivered": "Not delivered",
    "leakage": "Leakage / damaged pouch",
    "other": "Other",
}
CLAIM_WINDOW_DAYS = 7  # how far back a customer can report a problem
DELIVERED_STATUSES = ("delivered", "invoiced", "paid")


def day_products(db: Session, customer_id: int, day: date) -> Dict[int, Dict]:
    """Per product the customer got on a day: name, unit, ordered, delivered and the rate."""
    orders = db.query(Order).filter(
        Order.customer_id == customer_id, Order.delivery_date == day, Order.status.in_(DELIVERED_STATUSES)
    ).all()
    out: Dict[int, Dict] = {}
    for rows in order_lines(db, orders).values():
        for r in rows:
            p = out.setdefault(r["product_id"], {"product_id": r["product_id"], "product_name": r["product_name"],
                                                 "unit": r["unit"], "ordered": 0.0, "delivered": 0.0, "amount": 0.0})
            p["ordered"] += r["ordered"]
            p["delivered"] += r["delivered"]
            p["amount"] += r["amount"]
    for p in out.values():
        p["ordered"] = round(p["ordered"], 3)
        p["delivered"] = round(p["delivered"], 3)
        p["rate"] = round(p["amount"] / p["delivered"], 2) if p["delivered"] else 0.0
    return out


def day_delivery(db: Session, customer_id: int, day: date, product_id: Optional[int] = None) -> Dict:
    """
    What the customer received on a day, for one product (or the main product when not given):
    ordered and delivered quantity, rate, and the delivery records.
    """
    orders = db.query(Order).filter(
        Order.customer_id == customer_id, Order.delivery_date == day, Order.status.in_(DELIVERED_STATUSES)
    ).all()
    products = day_products(db, customer_id, day)
    if product_id is None and products:
        product_id = next(iter(products))
    p = products.get(product_id, {"ordered": 0.0, "delivered": 0.0, "rate": 0.0, "unit": "", "product_name": ""})
    deliveries = [d for d in (db.query(Delivery).filter(Delivery.order_id == o.id).first() for o in orders) if d]
    return {"orders": orders, "deliveries": deliveries, "product_id": product_id, "products": products,
            "ordered_qty": p["ordered"], "delivered_qty": p["delivered"], "rate": p["rate"],
            "unit": p["unit"], "product_name": p["product_name"]}


def claimed_so_far(db: Session, customer_id: int, day: date, exclude_id: Optional[int] = None,
                   product_id: Optional[int] = None) -> float:
    q = db.query(DeliveryClaim).filter(
        DeliveryClaim.customer_id == customer_id, DeliveryClaim.issue_date == day,
        DeliveryClaim.status.in_(["pending", "approved"])
    )
    if product_id is not None:
        q = q.filter(DeliveryClaim.product_id == product_id)
    total = 0.0
    for c in q.all():
        if c.id == exclude_id:
            continue
        total += c.claimed_qty if c.status == "pending" else c.approved_qty
    return round(total, 2)


def create_claim(db: Session, customer: Customer, issue_date: date, reason: str, qty: float, description: str,
                 product_id: Optional[int] = None) -> DeliveryClaim:
    today = date.today()
    if reason not in CLAIM_REASONS:
        raise HTTPException(status_code=400, detail="Choose what went wrong")
    if issue_date > today:
        raise HTTPException(status_code=400, detail="The date cannot be in the future")
    if issue_date < today - timedelta(days=CLAIM_WINDOW_DAYS):
        raise HTTPException(status_code=400, detail=f"Problems can be reported within {CLAIM_WINDOW_DAYS} days of delivery")
    if qty is None or qty <= 0:
        raise HTTPException(status_code=400, detail="Enter how many litres were affected")
    if not (description or "").strip():
        raise HTTPException(status_code=400, detail="Please describe what happened")

    got = day_products(db, customer.id, issue_date)
    got = {pid: p for pid, p in got.items() if p["delivered"] > 0}
    if not got:
        raise HTTPException(status_code=400, detail="Nothing was delivered to you on this date")
    if product_id is None:
        if len(got) > 1:
            raise HTTPException(status_code=400, detail="Choose which product the problem is with")
        product_id = next(iter(got))
    if product_id not in got:
        raise HTTPException(status_code=400, detail="That product was not delivered to you on this date")
    info = day_delivery(db, customer.id, issue_date, product_id)
    unit = info["unit"]
    if whole_unit(unit) and abs(qty - round(qty)) > 1e-9:
        raise HTTPException(status_code=400, detail=f"{info['product_name']} is counted per {unit}; enter a whole number")
    available = round(info["delivered_qty"] - claimed_so_far(db, customer.id, issue_date, product_id=product_id), 3)
    if qty > available + 1e-9:
        raise HTTPException(status_code=400, detail=f"You can claim at most {available:g} {unit} of {info['product_name']} "
                                                    f"for this date (delivered {info['delivered_qty']:g} {unit}, "
                                                    f"already claimed the rest)")

    n = db.query(DeliveryClaim).count() + 1
    claim = DeliveryClaim(
        claim_number=f"CLM-{today:%Y%m%d}-{n:04d}", customer_id=customer.id,
        order_id=info["orders"][0].id if info["orders"] else None,
        delivery_id=info["deliveries"][0].id if info["deliveries"] else None,
        product_id=product_id, issue_date=issue_date, reason=reason, claimed_qty=round(qty, 3),
        description=description.strip(), status="pending", rate=info["rate"],
    )
    db.add(claim)
    db.flush()
    notifications.claim_submitted(db, claim, customer, CLAIM_REASONS[reason])
    return claim


SETTLEMENT_MODES = ("bill", "refund")
REFUND_METHODS = ("cash", "upi", "bank_transfer")


def approve_claim(db: Session, claim: DeliveryClaim, approved_qty: float, note: Optional[str], admin: User,
                  mode: str = "bill", refund_method: Optional[str] = None,
                  refund_reference: Optional[str] = None, refund_date: Optional[date] = None) -> DeliveryClaim:
    """
    mode "bill":   deduct from the bill. If that day is already billed, the bill is reduced now
                   (ledger credit note); otherwise it is deducted when the bill is generated.
    mode "refund": pay the customer back separately (cash / UPI / bank). Bills are not changed;
                   the ledger records the claim credit and the refund paid out, which net to zero.
    """
    if mode not in SETTLEMENT_MODES:
        raise HTTPException(status_code=400, detail="Choose: deduct from bill, or refund separately")
    if mode == "refund" and refund_method not in REFUND_METHODS:
        raise HTTPException(status_code=400, detail="Choose how the refund is paid (cash, UPI or bank transfer)")
    if mode == "refund" and refund_date is not None:
        if refund_date > date.today():
            raise HTTPException(status_code=400, detail="Refund date cannot be in the future")
        if refund_date < claim.issue_date:
            raise HTTPException(status_code=400, detail="Refund date cannot be before the day of the claim")
    if claim.status != "pending":
        raise HTTPException(status_code=400, detail="This claim has already been decided")
    if approved_qty is None or approved_qty <= 0:
        raise HTTPException(status_code=400, detail="Approved quantity must be more than 0 (or reject the claim)")
    if approved_qty > claim.claimed_qty:
        raise HTTPException(status_code=400, detail=f"Cannot approve more than the {claim.claimed_qty:g} L claimed")
    info = day_delivery(db, claim.customer_id, claim.issue_date, claim.product_id)
    if whole_unit(info["unit"]) and abs(approved_qty - round(approved_qty)) > 1e-9:
        raise HTTPException(status_code=400, detail=f"{info['product_name']} is counted per {info['unit']}; approve a whole number")
    available = round(info["delivered_qty"] - claimed_so_far(db, claim.customer_id, claim.issue_date, exclude_id=claim.id,
                                                             product_id=claim.product_id), 3)
    if approved_qty > available + 1e-9:
        raise HTTPException(status_code=400, detail=f"Only {available:g} {info['unit']} of that day's "
                                                    f"{info['product_name']} is left to credit")

    claim.status = "approved"
    claim.approved_qty = round(approved_qty, 3)
    claim.rate = info["rate"] or claim.rate
    claim.credit_amount = round(claim.approved_qty * claim.rate, 2)
    claim.admin_note = (note or "").strip() or None
    claim.reviewed_by = admin.id
    claim.reviewed_at = datetime.utcnow()

    customer = db.query(Customer).filter(Customer.id == claim.customer_id).first()
    reason = CLAIM_REASONS[claim.reason]
    if mode == "refund":
        # The day the money was actually given back (it may be recorded later)
        today = refund_date or date.today()
        method_label = {"cash": "cash", "upi": "UPI", "bank_transfer": "bank transfer"}[refund_method]
        ref = (refund_reference or "").strip() or None
        db.add(CustomerLedger(
            customer_id=customer.id, transaction_date=today, transaction_type="credit_note",
            reference_number=claim.claim_number, debit_amount=0.0, credit_amount=claim.credit_amount,
            running_balance=0.0,
            narration=f"Claim credit {claim.approved_qty:g} L ({reason}) on {claim.issue_date:%d %b %Y} - refunded separately"
        ))
        db.add(CustomerLedger(
            customer_id=customer.id, transaction_date=today, transaction_type="refund",
            reference_number=claim.claim_number, debit_amount=claim.credit_amount, credit_amount=0.0,
            running_balance=0.0,
            narration=f"Refund paid by {method_label}" + (f" (ref {ref})" if ref else "") + f" for {claim.claim_number}"
        ))
        claim.settlement = "refund"
        claim.refund_method = refund_method
        claim.refund_reference = ref
        claim.refunded_on = today
        recalculate_ledger(db, customer)
        notifications.claim_approved(db, claim, None)
        db.commit()
        return claim

    # Deduct from the bill. Already billed for that day? Reduce that bill now with a credit note.
    # Otherwise it is deducted automatically when that period's bill is generated.
    bill = bill_for_delivery_day(db, claim.customer_id, claim.issue_date)
    if bill:
        db.add(CustomerLedger(
            customer_id=customer.id, transaction_date=date.today(), transaction_type="credit_note",
            reference_number=claim.claim_number, debit_amount=0.0, credit_amount=claim.credit_amount,
            running_balance=0.0,
            narration=f"Credit for {claim.approved_qty:g} L ({CLAIM_REASONS[claim.reason]}) on {claim.issue_date:%d %b %Y} - billed in {bill.invoice_number}"
        ))
        claim.settlement = "credit_note"
        claim.invoice_id = bill.id
        refresh_bill(db, bill)
        # Bill already paid: the credit pays the customer's other unpaid bills instead
        moves = move_excess_to_other_bills(db, bill)
        claim.excess_moves = json.dumps(moves) if moves else None
        recalculate_ledger(db, customer)
    notifications.claim_approved(db, claim, bill.invoice_number if bill else None)
    db.commit()
    return claim


def reject_claim(db: Session, claim: DeliveryClaim, note: Optional[str], admin: User) -> DeliveryClaim:
    if claim.status != "pending":
        raise HTTPException(status_code=400, detail="This claim has already been decided")
    if not (note or "").strip():
        raise HTTPException(status_code=400, detail="Write a reason so the customer knows why it was rejected")
    claim.status = "rejected"
    claim.admin_note = note.strip()
    claim.reviewed_by = admin.id
    claim.reviewed_at = datetime.utcnow()
    notifications.claim_rejected(db, claim)
    db.commit()
    return claim


def _describe(claim: DeliveryClaim) -> str:
    text = f"{claim.status}"
    if claim.status == "approved":
        text += f" {claim.approved_qty:g} L = Rs {claim.credit_amount:g}, settlement {claim.settlement or 'next bill'}"
        if claim.invoice_id:
            text += f" (bill id {claim.invoice_id})"
        if claim.refund_method:
            text += f", refund {claim.refund_method} {claim.refund_reference or ''}".rstrip()
    if claim.admin_note:
        text += f", note: {claim.admin_note}"
    return text


def reopen_claim(db: Session, claim: DeliveryClaim, reason: Optional[str], admin: User) -> DeliveryClaim:
    """
    Undo the admin's decision and put the claim back to pending so it can be decided again.
    Everything the decision did to bills and the ledger is reversed exactly:
      - rejected / approved but not billed yet: nothing to reverse
      - credit_note (deducted from a bill made earlier): the credit entry is removed, the bill goes back up
      - bill (deducted while the bill was made): the litres and amount go back on that day's line,
        the bill total and its ledger entry go up by the same amount
      - refund (paid back separately): the credit and refund entries are removed (they net to zero);
        money already handed over must be collected back by the dairy
    """
    if claim.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Only an approved or rejected claim can be undone")
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Write why the decision is being undone")

    before = _describe(claim)
    customer = db.query(Customer).filter(Customer.id == claim.customer_id).first()
    ledger_changed = False

    if claim.status == "approved" and claim.settlement == "credit_note":
        bill = db.query(Invoice).filter(Invoice.id == claim.invoice_id).first()
        if bill and bill_figures(db, bill)["excess"] > 0 and claim.reviewed_at:
            # The credit may already have been used as advance to pay a later bill
            later = db.query(Invoice).filter(
                Invoice.customer_id == claim.customer_id, Invoice.id != bill.id,
                Invoice.bill_type.isnot(None), Invoice.advance_applied > 0,
                Invoice.invoice_date >= claim.reviewed_at.date(),
            ).first()
            if later:
                raise HTTPException(status_code=400, detail=(
                    f"This credit was already used as advance in bill {later.invoice_number}. "
                    f"Delete that bill first, then undo this claim and make the bill again."))
        db.query(CustomerLedger).filter(
            CustomerLedger.customer_id == claim.customer_id,
            CustomerLedger.reference_number == claim.claim_number,
            CustomerLedger.transaction_type == "credit_note",
        ).delete()
        claim.settlement = None
        claim.invoice_id = None
        if bill:
            # Money this credit moved to other bills comes back to this bill
            if claim.excess_moves:
                undo_excess_move(db, bill, json.loads(claim.excess_moves))
            refresh_bill(db, bill)
        claim.excess_moves = None
        ledger_changed = True

    elif claim.status == "approved" and claim.settlement == "bill":
        bill = db.query(Invoice).filter(Invoice.id == claim.invoice_id).first()
        if bill:
            qty, amount = claim.approved_qty or 0.0, claim.credit_amount or 0.0
            lines = json.loads(bill.bill_lines) if bill.bill_lines else []
            for line in lines:
                if line["date"] == line_day(bill, claim.issue_date).isoformat() and line.get("product_id") == claim.product_id:
                    line["qty"] = round(line["qty"] + qty, 2)
                    line["amount"] = round(line["amount"] + amount, 2)
                    line["claim_qty"] = round(max(0.0, line.get("claim_qty", 0.0) - qty), 2)
                    line["claim_amount"] = round(max(0.0, line.get("claim_amount", 0.0) - amount), 2)
                    line["rate"] = round(line["amount"] / line["qty"], 2) if line["qty"] else line["rate"]
                    break
            bill.bill_lines = json.dumps(lines)
            line = next((l for l in lines if l.get("product_id") == claim.product_id), None)
            if line:
                lpu = line.get("litres_per_unit", 1.0 if (line.get("unit") or "").upper() == "L" else 0.0)
                bill.total_litres = round((bill.total_litres or 0.0) + qty * lpu, 3)
            bill.subtotal = round((bill.subtotal or 0.0) + amount, 2)
            bill.total_amount = round((bill.total_amount or 0.0) + amount, 2)
            entry = db.query(CustomerLedger).filter(
                CustomerLedger.customer_id == claim.customer_id,
                CustomerLedger.reference_number == bill.invoice_number,
                CustomerLedger.transaction_type == "sales_invoice",
            ).first()
            if entry:
                entry.debit_amount = round((entry.debit_amount or 0.0) + amount, 2)
                entry.narration = f"{entry.narration} (claim {claim.claim_number} undone: +{qty:g} L)"
            refresh_bill(db, bill)
            ledger_changed = True
        claim.settlement = None
        claim.invoice_id = None

    elif claim.status == "approved" and claim.settlement == "refund":
        db.query(CustomerLedger).filter(
            CustomerLedger.customer_id == claim.customer_id,
            CustomerLedger.reference_number == claim.claim_number,
            CustomerLedger.transaction_type.in_(["credit_note", "refund"]),
        ).delete(synchronize_session=False)
        claim.settlement = None
        claim.refund_method = None
        claim.refund_reference = None
        claim.refunded_on = None
        ledger_changed = True

    claim.status = "pending"
    claim.approved_qty = 0.0
    claim.credit_amount = 0.0
    claim.admin_note = None
    claim.reviewed_by = None
    claim.reviewed_at = None
    if ledger_changed and customer:
        recalculate_ledger(db, customer)
    db.add(AuditLog(
        user_id=admin.id, username=admin.username, action="CLAIM_UNDO", entity_name="delivery_claims",
        entity_id=claim.claim_number, old_values=before, new_values=f"pending again. Reason: {reason}",
    ))
    notifications.claim_reopened(db, claim, reason)
    db.commit()
    return claim


def settlement_text(claim: DeliveryClaim) -> str:
    if claim.status != "approved":
        return ""
    if claim.settlement == "credit_note":
        return "Deducted from your bill"
    if claim.settlement == "bill":
        return "Deducted in your bill"
    if claim.settlement == "refund":
        method = {"cash": "cash", "upi": "UPI", "bank_transfer": "bank transfer"}.get(claim.refund_method or "", "")
        return f"Refunded to you by {method}" if method else "Refunded to you"
    return "Will be deducted in your next bill"


def claim_dict(db: Session, claim: DeliveryClaim, with_details: bool = False) -> Dict:
    c = claim.customer
    claim_product = db.query(Product).filter(Product.id == claim.product_id).first() if claim.product_id else None
    data = {
        "id": claim.id,
        "claim_number": claim.claim_number,
        "customer_id": claim.customer_id,
        "customer_name": c.business_name if c else "",
        "customer_code": c.customer_code if c else "",
        "issue_date": claim.issue_date.isoformat(),
        "reason": claim.reason,
        "reason_label": CLAIM_REASONS.get(claim.reason, claim.reason),
        "claimed_qty": claim.claimed_qty,
        "product_id": claim.product_id,
        "product_name": (claim_product.product_name if claim_product else ""),
        "unit": (claim_product.unit if claim_product else "L"),
        "description": claim.description,
        "status": claim.status,
        "approved_qty": claim.approved_qty,
        "rate": claim.rate,
        "credit_amount": claim.credit_amount,
        "admin_note": claim.admin_note,
        "settlement": claim.settlement,
        "settlement_text": settlement_text(claim),
        "refund_method": claim.refund_method,
        "refund_reference": claim.refund_reference,
        # Stored in UTC; the "Z" lets apps show it in the viewer's local time
        "created_at": claim.created_at.isoformat() + "Z" if claim.created_at else None,
        "reviewed_at": claim.reviewed_at.isoformat() + "Z" if claim.reviewed_at else None,
        "reviewed_by_name": (db.query(User.full_name).filter(User.id == claim.reviewed_by).scalar()
                             if claim.reviewed_by else None),
        "photo_ids": [a.id for a in attachments_for(db, "claim", claim.id)],
    }
    if with_details:
        info = day_delivery(db, claim.customer_id, claim.issue_date, claim.product_id)
        deliveries = []
        for d in info["deliveries"]:
            trip = d.trip
            deliveries.append({
                "delivery_id": d.id,
                "status": d.status,
                "ordered_litres": d.total_ordered_litres,
                "delivered_litres": d.total_delivered_litres,
                "shortage_litres": d.total_shortage_litres,
                "shortage_reason": d.shortage_reason,
                "delivered_to": d.delivered_to_person,
                "delivered_at": (d.departure_time or d.arrival_time).isoformat() if (d.departure_time or d.arrival_time) else None,
                "driver_name": trip.driver.full_name if trip and trip.driver else None,
                "has_signature": bool(d.customer_signature_url),
                # Signature is a small PNG data URL captured on the delivery boy's phone
                "signature": d.customer_signature_url if (d.customer_signature_url or "").startswith("data:image/") else None,
                "photo_ids": [a.id for a in attachments_for(db, "delivery", d.id)],
            })
        billed = bill_for_delivery_day(db, claim.customer_id, claim.issue_date)
        data.update({
            "billed_in": billed.invoice_number if billed else None,
            # Is that bill already paid? Then a bill deduction becomes advance for the next bill
            "billed_balance_due": bill_figures(db, billed)["balance"] if billed else None,
            "billed_paid": round((billed.paid_amount or 0.0) + (billed.advance_applied or 0.0), 2) if billed else None,
            "ordered_qty": info["ordered_qty"],
            "delivered_qty": info["delivered_qty"],
            "other_claims_qty": claimed_so_far(db, claim.customer_id, claim.issue_date, exclude_id=claim.id,
                                               product_id=claim.product_id),
            "day_products": list(info["products"].values()),
            "deliveries": deliveries,
        })
    return data


def list_claims(db: Session, status: Optional[str] = None, customer_id: Optional[int] = None) -> List[DeliveryClaim]:
    q = db.query(DeliveryClaim)
    if status:
        q = q.filter(DeliveryClaim.status == status)
    if customer_id:
        q = q.filter(DeliveryClaim.customer_id == customer_id)
    return q.order_by(DeliveryClaim.created_at.desc(), DeliveryClaim.id.desc()).all()
