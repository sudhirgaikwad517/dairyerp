"""
Automatic dispatch: at the dispatch time the admin sets (e.g. 04:00), each delivery day's confirmed
orders go onto the delivery boys' trips by themselves. Before that time the admin can put the day
on hold with a note (no milk, vehicle problem...); at dispatch time the waiting customers are told
why, instead of the milk going out. Releasing the hold dispatches straight away if the time has passed.
"""
import json
import logging
import threading
import time as clock
from datetime import date, datetime, time
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models.entities import AuditLog, BusinessProfile, DispatchDay, Order, User
from backend.app.services import notifications
from backend.app.services.daily_orders import EDITABLE_STATUSES, dispatch_day
from backend.app.services.order_lines import order_what

logger = logging.getLogger(__name__)
DEFAULT_DISPATCH = "04:00"
CHECK_EVERY_SECONDS = 30
DISPATCH_LOCK = threading.Lock()  # the background dispatcher and the admin's Dispatch button never run together


def dispatch_time(db: Session) -> time:
    profile = db.query(BusinessProfile).first()
    value = (profile.dispatch_time if profile else None) or DEFAULT_DISPATCH
    try:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return time(4, 0)


def dispatch_at(db: Session, day: date) -> datetime:
    return datetime.combine(day, dispatch_time(db))


def _record(db: Session, day: date, create: bool = False) -> Optional[DispatchDay]:
    rec = db.query(DispatchDay).filter(DispatchDay.day == day).first()
    if not rec and create:
        rec = DispatchDay(day=day, on_hold=False)
        db.add(rec)
        db.flush()
    return rec


def _waiting_orders(db: Session, day: date) -> List[Order]:
    """Confirmed orders for the day that are not on a delivery trip yet."""
    return db.query(Order).filter(
        Order.delivery_date == day, Order.status.in_(EDITABLE_STATUSES), Order.total_amount > 0
    ).order_by(Order.id).all()


def dispatch_status(db: Session, day: date, now: Optional[datetime] = None) -> Dict:
    now = now or datetime.now()
    at = dispatch_at(db, day)
    rec = _record(db, day)
    sent = db.query(Order).filter(
        Order.delivery_date == day, Order.status.in_(["out_for_delivery", "delivered", "invoiced", "paid"])
    ).count()
    return {
        "date": day.isoformat(),
        "dispatch_time": f"{at:%H:%M}",
        "dispatch_at": at.isoformat(timespec="minutes"),
        "time_passed": now >= at,
        "on_hold": bool(rec and rec.on_hold),
        "hold_note": rec.hold_note if rec and rec.on_hold else None,
        "hold_set_at": rec.hold_set_at.isoformat(timespec="minutes") if rec and rec.on_hold and rec.hold_set_at else None,
        "customers_told": bool(rec and rec.on_hold and rec.hold_notified_ids),
        "waiting_orders": len(_waiting_orders(db, day)),
        "dispatched_orders": sent,
        "auto_dispatched_at": rec.auto_dispatched_at.isoformat(timespec="minutes") if rec and rec.auto_dispatched_at else None,
        # The hold can be set or changed until the milk has gone out
        "can_hold": day >= now.date() and (now < at or bool(rec and rec.on_hold)) and not (sent and now >= at),
    }


def set_hold(db: Session, day: date, note: str, admin: User, now: Optional[datetime] = None) -> Dict:
    now = now or datetime.now()
    note = (note or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="Write why the milk cannot be dispatched; customers will see this note")
    if day < now.date():
        raise HTTPException(status_code=400, detail="This day is over")
    rec = _record(db, day, create=True)
    at = dispatch_at(db, day)
    if now >= at and not rec.on_hold:
        raise HTTPException(status_code=400, detail=(
            f"Dispatch time {at:%I:%M %p} has passed and the orders have gone to the delivery boys. "
            f"Cancel single orders instead."))
    was_on_hold = rec.on_hold
    rec.on_hold = True
    rec.hold_note = note
    rec.hold_by = admin.id
    rec.hold_set_at = now
    rec.updated_at = datetime.utcnow()
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="DISPATCH_HOLD", entity_name="dispatch_days",
                    entity_id=day.isoformat(), new_values=("note changed: " if was_on_hold else "") + note))
    db.commit()
    if now >= at:
        # Already past the time (note changed during a hold): tell anyone not told yet
        run_dispatch(db, now)
    return dispatch_status(db, day, now)


def release_hold(db: Session, day: date, admin: User, now: Optional[datetime] = None) -> Dict:
    now = now or datetime.now()
    rec = _record(db, day)
    if not rec or not rec.on_hold:
        raise HTTPException(status_code=400, detail="Dispatch for this day is not on hold")
    rec.on_hold = False
    rec.updated_at = datetime.utcnow()
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="DISPATCH_RELEASE", entity_name="dispatch_days",
                    entity_id=day.isoformat(), old_values=rec.hold_note, new_values="hold removed"))
    db.commit()
    result = dispatch_status(db, day, now)
    if day == now.date() and now >= dispatch_at(db, day):
        result["dispatch"] = run_dispatch(db, now)  # time already passed: send the milk out now
        result.update({k: v for k, v in dispatch_status(db, day, now).items()})
    return result


def check_manual_dispatch(db: Session, day: date) -> None:
    rec = _record(db, day)
    if rec and rec.on_hold:
        raise HTTPException(status_code=400, detail=f"Dispatch for {day:%d %b} is on hold ({rec.hold_note}). Remove the hold first.")


def run_dispatch(db: Session, now: Optional[datetime] = None) -> Optional[Dict]:
    """
    One check of the automatic dispatcher for today. Safe to call any number of times:
    only orders still waiting are touched, and every notice is sent once.
    """
    now = now or datetime.now()
    day = now.date()
    if now < dispatch_at(db, day):
        return None
    with DISPATCH_LOCK:
        return _run_dispatch_locked(db, day)


def _run_dispatch_locked(db: Session, day: date) -> Optional[Dict]:
    waiting = _waiting_orders(db, day)
    rec = _record(db, day)
    if rec and rec.on_hold:
        told = set(json.loads(rec.hold_notified_ids or "[]"))
        new = [o for o in waiting if o.id not in told]
        for o in new:
            notifications.dispatch_held(db, o.customer, day, order_what(db, o), rec.hold_note)
        if new:
            rec.hold_notified_ids = json.dumps(sorted(told | {o.id for o in new}))
            db.commit()
        return {"held": True, "customers_told": len(new)}
    if not waiting:
        return None
    result = dispatch_day(db, day)
    rec = _record(db, day, create=True)
    if result["orders_dispatched"] and not rec.auto_dispatched_at:
        rec.auto_dispatched_at = datetime.now()
    # Orders that could not go (no route / no delivery boy): tell the admin once per order
    told = set(json.loads(rec.skipped_notified_ids or "[]"))
    still = {o.id: o for o in _waiting_orders(db, day)}
    for s in result["skipped"]:
        order = next((o for o in still.values() if o.customer.business_name == s["customer"] and o.id not in told), None)
        if order:
            notifications.dispatch_skipped(db, order.customer, day, order_what(db, order), s["reason"])
            told.add(order.id)
    rec.skipped_notified_ids = json.dumps(sorted(told)) if told else None
    db.commit()
    return result


def start_auto_dispatcher(session_factory) -> threading.Thread:
    """Background loop in the server process: checks every 30 seconds."""
    def loop():
        while True:
            try:
                with session_factory() as db:
                    run_dispatch(db)
            except Exception:  # never let one bad check stop the dispatcher
                logger.exception("Automatic dispatch check failed")
            clock.sleep(CHECK_EVERY_SECONDS)

    t = threading.Thread(target=loop, name="auto-dispatch", daemon=True)
    t.start()
    return t
