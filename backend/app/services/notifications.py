"""In-app notifications shown under the bell icon (customer app and admin app).

Each helper only adds rows to the session; the caller's commit saves them together with
the change they describe, so a notice is never sent for something that was rolled back.
"""
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app.models.entities import AppNotification, Customer, DeliveryClaim, Invoice
from backend.app.services import email_service

KEEP_LATEST = 100  # notices returned per list call
SHORT_REASONS = {
    "leakage": "leakage in transit",
    "damage": "damaged pouch / can",
    "customer_rejection": "customer did not take it",
    "stock_shortage": "not enough milk in the vehicle",
    "delivery_issue": "delivery issue",
}


def money(amount: float) -> str:
    amount = round(amount or 0.0, 2)
    return f"₹{amount:,.0f}" if amount == int(amount) else f"₹{amount:,.2f}"


def litres(qty: float) -> str:
    return f"{round(qty or 0.0, 2):g} L"


def day_text(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def notify_customer(db: Session, customer_id: int, kind: str, title: str, body: str, link: Optional[str] = None,
                    invoice_id: Optional[int] = None) -> None:
    db.add(AppNotification(audience="customer", customer_id=customer_id, kind=kind, title=title, body=body, link=link))
    # Same notice by email when the dairy has email on for this kind (bill emails carry the PDF)
    email_service.queue_customer(db, customer_id, kind, title, body, link, invoice_id)


def notify_admin(db: Session, kind: str, title: str, body: str, link: Optional[str] = None,
                 customer_id: Optional[int] = None) -> None:
    db.add(AppNotification(audience="admin", customer_id=customer_id, kind=kind, title=title, body=body, link=link))
    email_service.queue_admin(db, kind, title, body, link)


# ---- Events -----------------------------------------------------------------

def _qty(q: float, unit: str) -> str:
    return f"{round(q or 0.0, 2):g} {unit}".strip()


def delivery_done(db: Session, customer: Customer, day: date, lines: list,
                  reason: Optional[str], driver_name: Optional[str], edited: bool) -> None:
    """lines: [(product name, unit, ordered, delivered)] for the stop."""
    reason = SHORT_REASONS.get(reason, reason) if reason and reason != "none" else None
    why = f" Reason: {reason}." if reason else ""
    by = f" by {driver_name}" if driver_name else ""
    got = [(n, u, o, d) for n, u, o, d in lines if (d or 0) > 0]
    short = [(n, u, o, d) for n, u, o, d in lines if round((o or 0) - (d or 0), 3) > 0]
    all_text = ", ".join(f"{_qty(o, u)} {n}" for n, u, o, d in lines)
    got_text = ", ".join(f"{_qty(d, u)} {n}" for n, u, o, d in got)
    if not got:
        notify_customer(db, customer.id, "not_delivered", "Order not delivered",
                        f"Your order for {day_text(day)} ({all_text}) was not delivered.{why} "
                        f"You will not be charged for it.", "orders")
        notify_admin(db, "not_delivered", f"Not delivered: {customer.business_name}",
                     f"{all_text} for {day_text(day)} not delivered{by}.{why}", "delivery", customer.id)
        return
    if short:
        short_text = ", ".join(f"{_qty(d, u)} of {_qty(o, u)} {n}" for n, u, o, d in short)
        notify_customer(db, customer.id, "delivered_short", "Delivered (less than ordered)",
                        f"On {day_text(day)} you got {got_text}. Less than ordered: {short_text}.{why} "
                        f"You are charged only for what was delivered.", "orders")
        notify_admin(db, "delivered_short", f"Short delivery: {customer.business_name}",
                     f"{short_text} delivered on {day_text(day)}{by}.{why}", "delivery", customer.id)
        return
    if edited:
        notify_customer(db, customer.id, "delivered", "Delivery updated",
                        f"Delivery for {day_text(day)} corrected: {got_text} delivered.", "orders")
    else:
        notify_customer(db, customer.id, "delivered", "Order delivered",
                        f"{got_text} delivered on {day_text(day)}. "
                        f"If anything is wrong, report a problem within 7 days.", "orders")


def payment_received(db: Session, customer: Customer, amount: float, method: str, on: date,
                     bill_number: Optional[str] = None, collected_by: Optional[str] = None) -> None:
    how = {"cash": "cash", "upi": "UPI", "bank_transfer": "bank transfer", "cheque": "cheque"}.get(method, method)
    where = f" for {bill_number}" if bill_number else ""
    by = " at delivery" if collected_by else ""
    notify_customer(db, customer.id, "payment", "Payment received",
                    f"{money(amount)} received by {how}{by} on {day_text(on)}{where}. Thank you!", "statement")
    if collected_by:
        notify_admin(db, "payment_collected", f"Payment collected: {money(amount)}",
                     f"{collected_by} collected {money(amount)} ({how}) from {customer.business_name}.",
                     "bills", customer.id)


def order_dispatched(db: Session, customer: Customer, day: date, what: str) -> None:
    notify_customer(db, customer.id, "dispatched", "Order sent for delivery",
                    f"Your order for {day_text(day)} ({what}) is with the delivery team. "
                    f"It can no longer be changed.", "orders")


def _until(deadline: datetime) -> str:
    return f"{deadline:%I:%M %p}".lstrip("0") + f" on {day_text(deadline.date())}"


def order_confirmed(db: Session, customer: Customer, day: date, what: str, amount: float, number: str,
                    deadline: datetime) -> None:
    notify_customer(db, customer.id, "order_confirmed", "Order confirmed",
                    f"Order {number} for {day_text(day)}: {what}, {money(amount)}. "
                    f"You can change it in the app till {_until(deadline)}.", "orders")


def order_changed_by_customer(db: Session, customer: Customer, day: date, what: str, previous: str, amount: float,
                              deadline: datetime) -> None:
    notify_customer(db, customer.id, "order_changed", "Order changed",
                    f"Your order for {day_text(day)} is now {what}, {money(amount)} (was {previous}). "
                    f"You can change it till {_until(deadline)}.", "orders")


def order_cancelled_by_customer(db: Session, customer: Customer, day: date, previous: Optional[str],
                                deadline: datetime) -> None:
    notify_customer(db, customer.id, "order_cancelled", "Order cancelled",
                    f"You cancelled your order for {day_text(day)}"
                    f"{f' ({previous})' if previous else ''}. You can order again till {_until(deadline)}.", "orders")


def order_set_by_dairy(db: Session, customer: Customer, day: date, what: Optional[str], previous: Optional[str]) -> None:
    """what None = cancelled; previous None = there was no order before."""
    if what is None:
        notify_customer(db, customer.id, "order_cancelled", "Order cancelled by the dairy",
                        f"Your order for {day_text(day)} was cancelled by the dairy.", "orders")
    elif previous is None:
        notify_customer(db, customer.id, "order_placed", "Order placed by the dairy",
                        f"The dairy placed an order for you for {day_text(day)}: {what}.", "orders")
    elif previous != what:
        notify_customer(db, customer.id, "order_changed", "Order changed by the dairy",
                        f"Your order for {day_text(day)} was changed from {previous} to {what}.", "orders")


def dispatch_held(db: Session, customer: Customer, day: date, what: str, note: str) -> None:
    notify_customer(db, customer.id, "dispatch_held", "Order not sent out yet",
                    f"Your order for {day_text(day)} ({what}) could not be dispatched on time. "
                    f"Reason: {note.strip().rstrip('.')}. "
                    f"The dairy will update you.", "orders")


def dispatch_skipped(db: Session, customer: Customer, day: date, what: str, reason: str) -> None:
    notify_admin(db, "dispatch_skipped", f"Not dispatched: {customer.business_name}",
                 f"{what} for {day_text(day)} could not go to a delivery boy: {reason}. "
                 f"Fix it and press Dispatch.", "orders", customer.id)


ISSUE_REASONS = {
    "vehicle_breakdown": "Vehicle breakdown",
    "traffic": "Heavy traffic / road blocked",
    "weather": "Bad weather",
    "milk_shortage": "Not enough milk in the vehicle",
    "accident": "Accident",
    "other": "Other problem",
}


def delivery_delayed(db: Session, customer: Customer, day: date, reason: str, note: Optional[str]) -> None:
    extra = f" ({note})" if note else ""
    notify_customer(db, customer.id, "delivery_delayed", "Delivery delayed",
                    f"Your milk for {day_text(day)} is running late. Reason: {ISSUE_REASONS.get(reason, reason)}{extra}. "
                    f"Sorry for the trouble.", "orders")


def issue_reported(db: Session, driver_name: str, day: date, reason: str, note: Optional[str], stops: int) -> None:
    extra = f": {note}" if note else ""
    notify_admin(db, "delivery_issue", f"Problem on route: {driver_name}",
                 f"{ISSUE_REASONS.get(reason, reason)}{extra}. {stops} customer(s) still waiting were told "
                 f"their milk is late ({day_text(day)}).", "delivery")


def deletion_requested(db: Session, name: str, phone: Optional[str], source: str, customer_id: Optional[int]) -> None:
    where = "the app" if source == "app" else "the website"
    notify_admin(db, "account_deletion", f"Account deletion request: {name}",
                 f"{name}{f' ({phone})' if phone else ''} asked from {where} to delete their account. "
                 f"Settle any dues, then mark the customer inactive.", "customers", customer_id)


def bill_created(db: Session, inv: Invoice, label: str, advance: float, what: str) -> None:
    paid = f" {money(advance)} paid from your advance." if advance > 0 else ""
    due = f" Please pay by {day_text(inv.due_date)}." if inv.due_date and advance < inv.total_amount else ""
    notify_customer(db, inv.customer_id, "bill_created", f"New bill {inv.invoice_number}",
                    f"Bill for {label}: {what}, {money(inv.total_amount)}.{paid}{due}", "bills",
                    invoice_id=inv.id)


def bill_cancelled(db: Session, inv: Invoice) -> None:
    notify_customer(db, inv.customer_id, "bill_cancelled", f"Bill {inv.invoice_number} cancelled",
                    f"The dairy cancelled bill {inv.invoice_number} ({money(inv.total_amount)}). "
                    f"A corrected bill will be made.", "bills")


def _claim_product(db: Session, claim: DeliveryClaim):
    from backend.app.models.entities import Product
    return db.query(Product).filter(Product.id == claim.product_id).first() if claim.product_id else None


def claim_submitted(db: Session, claim: DeliveryClaim, customer: Customer, reason: str) -> None:
    p = _claim_product(db, claim)
    unit, name = (p.unit, f" {p.product_name}") if p else ("L", "")
    notify_admin(db, "claim_new", f"New claim from {customer.business_name}",
                 f"{claim.claim_number}: {_qty(claim.claimed_qty, unit)}{name} on {day_text(claim.issue_date)} - {reason}.",
                 "claims", customer.id)


def claim_approved(db: Session, claim: DeliveryClaim, bill_number: Optional[str]) -> None:
    p = _claim_product(db, claim)
    unit, name = (p.unit, f" {p.product_name}") if p else ("L", "")
    part = (f"{_qty(claim.approved_qty, unit)} of {_qty(claim.claimed_qty, unit)}{name}"
            if round(claim.approved_qty, 2) < round(claim.claimed_qty, 2) else f"{_qty(claim.approved_qty, unit)}{name}")
    amount = money(claim.credit_amount)
    if claim.settlement == "refund":
        how = {"cash": "cash", "upi": "UPI", "bank_transfer": "bank transfer"}.get(claim.refund_method, claim.refund_method)
        result = f"{amount} paid back to you by {how} on {day_text(claim.refunded_on)}."
    elif claim.settlement == "credit_note" and bill_number:
        result = f"{amount} reduced from bill {bill_number}."
    else:
        result = f"{amount} will be reduced from your next bill."
    note = f" Dairy note: {claim.admin_note}" if claim.admin_note else ""
    notify_customer(db, claim.customer_id, "claim_approved", "Claim approved",
                    f"{claim.claim_number} ({day_text(claim.issue_date)}): {part} approved. {result}{note}", "claims")


def claim_rejected(db: Session, claim: DeliveryClaim) -> None:
    notify_customer(db, claim.customer_id, "claim_rejected", "Claim not approved",
                    f"{claim.claim_number} ({day_text(claim.issue_date)}) was not approved. "
                    f"Reason: {claim.admin_note}", "claims")


def claim_reopened(db: Session, claim: DeliveryClaim, reason: str) -> None:
    notify_customer(db, claim.customer_id, "claim_reopened", "Claim being checked again",
                    f"The dairy is checking {claim.claim_number} ({day_text(claim.issue_date)}) again. "
                    f"Reason: {reason}", "claims")


# ---- Reading ----------------------------------------------------------------

def _scope(db: Session, audience: str, customer_id: Optional[int]):
    q = db.query(AppNotification).filter(AppNotification.audience == audience)
    if audience == "customer":
        q = q.filter(AppNotification.customer_id == customer_id)
    return q


def list_notices(db: Session, audience: str, customer_id: Optional[int] = None) -> List[dict]:
    rows = _scope(db, audience, customer_id).order_by(AppNotification.id.desc()).limit(KEEP_LATEST).all()
    return [{
        "id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
        "created_at": n.created_at.isoformat() + "Z" if n.created_at else None,
        "read": n.read_at is not None,
    } for n in rows]


def unread_count(db: Session, audience: str, customer_id: Optional[int] = None) -> int:
    return _scope(db, audience, customer_id).filter(AppNotification.read_at.is_(None)).count()


def mark_read(db: Session, audience: str, customer_id: Optional[int] = None, notice_id: Optional[int] = None) -> int:
    q = _scope(db, audience, customer_id).filter(AppNotification.read_at.is_(None))
    if notice_id is not None:
        q = q.filter(AppNotification.id == notice_id)
    n = q.update({AppNotification.read_at: datetime.utcnow()}, synchronize_session=False)
    db.commit()
    return n
