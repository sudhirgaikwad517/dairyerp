"""
Transport cost per litre, the simple way the dairy works: one total transport cost per day
(all vehicles, drivers and fuel together). For a day:  cost per litre = that day's cost / milk delivered
to all customers that day.  15-day and monthly figures add up the days.
"""
import calendar
from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.services.order_lines import order_lines
from backend.app.models.entities import Delivery, Order, OrderItem, Product, TransportDayCost

SOLD_STATUSES = ("delivered", "invoiced", "paid")
PERIODS = ("daily", "fortnightly", "monthly", "custom")


def resolve_transport_period(period: str, ref_date: Optional[date], start_date: Optional[date],
                             end_date: Optional[date]) -> Tuple[date, date, str]:
    ref = ref_date or date.today()
    if period == "daily":
        return ref, ref, ref.strftime("%d %b %Y")
    if period == "fortnightly":
        last = calendar.monthrange(ref.year, ref.month)[1]
        if ref.day <= 15:
            return ref.replace(day=1), ref.replace(day=15), f"1 - 15 {ref:%b %Y}"
        return ref.replace(day=16), ref.replace(day=last), f"16 - {last} {ref:%b %Y}"
    if period == "monthly":
        last = calendar.monthrange(ref.year, ref.month)[1]
        return ref.replace(day=1), ref.replace(day=last), ref.strftime("%B %Y")
    if period == "custom":
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="Choose the from and to dates")
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="From date must be on or before the to date")
        return start_date, end_date, f"{start_date:%d %b %Y} - {end_date:%d %b %Y}"
    raise HTTPException(status_code=400, detail="Period must be day, 15 days, month or custom")


def delivered_by_day(db: Session, start: date, end: date) -> Dict[date, Dict[str, Any]]:
    """
    Milk delivered to all customers on each day (litres actually handed over: a short delivery counts
    only what was given), and how many orders of that day are still not delivered.
    """
    orders = db.query(Order).filter(Order.delivery_date >= start, Order.delivery_date <= end,
                                    Order.status != "cancelled").all()
    lines = order_lines(db, orders)

    days: Dict[date, Dict[str, Any]] = {}
    for o in orders:
        milk = [r for r in lines.get(o.id, []) if r["is_litre"]]
        if not milk or sum(r["ordered"] for r in milk) <= 0:
            continue
        day = days.setdefault(o.delivery_date, {"litres": 0.0, "pending": 0, "customers": set(), "by_customer": {}})
        if o.status not in SOLD_STATUSES:
            day["pending"] += 1
            continue
        got = sum(r["delivered"] for r in milk)  # litres actually handed over, same as the bills
        if got > 0:
            day["litres"] += got
            day["customers"].add(o.customer_id)
            day["by_customer"][o.customer_id] = day["by_customer"].get(o.customer_id, 0.0) + got
    return days


def transport_report(db: Session, start: date, end: date) -> Dict[str, Any]:
    """Day-wise milk, cost and cost per litre, with totals for the period."""
    today = date.today()
    delivered = delivered_by_day(db, start, end)
    costs = {c.cost_date: c for c in db.query(TransportDayCost).filter(
        TransportDayCost.cost_date >= start, TransportDayCost.cost_date <= end).all()}

    rows = []
    day = start
    while day <= min(end, today):
        dv = delivered.get(day)
        c = costs.get(day)
        cost = round(c.amount, 2) if c else 0.0
        if dv or c:
            litres = round(dv["litres"], 2) if dv else 0.0
            pending = dv["pending"] if dv else 0
            in_progress = pending > 0
            rows.append({
                "date": day.isoformat(),
                "litres": litres,
                "customers": len(dv["customers"]) if dv else 0,
                "pending_orders": pending,
                "in_progress": in_progress,
                "cost": cost,
                "cost_set": c is not None,
                "note": c.note if c else None,
                # Only for a finished day; part-way through the day it would look far too high
                "cost_per_litre": round(cost / litres, 2) if cost and litres and not in_progress else None,
            })
        day += timedelta(days=1)

    done = [r for r in rows if not r["in_progress"]]
    with_cost = [r for r in done if r["cost_set"] and r["cost"] > 0 and r["litres"] > 0]
    cost_total = round(sum(r["cost"] for r in done), 2)
    litres_with_cost = round(sum(r["litres"] for r in with_cost), 2)
    cost_with_litres = round(sum(r["cost"] for r in with_cost), 2)
    return {
        "days": rows,
        "total": {
            "litres": round(sum(r["litres"] for r in done), 2),
            "cost": cost_total,
            # Days without a cost entered are left out, so they do not pull the average down
            "cost_per_litre": round(cost_with_litres / litres_with_cost, 2) if litres_with_cost else None,
            "days_counted": len(with_cost),
        },
        "days_without_cost": [r["date"] for r in done if r["litres"] > 0 and not (r["cost_set"] and r["cost"] > 0)],
        "days_in_progress": [r["date"] for r in rows if r["in_progress"]],
    }


def customer_transport_share(db: Session, start: date, end: date, customer_id: Optional[int] = None) -> Dict[int, float]:
    """Each finished day's cost shared by the litres each customer got that day (for profitability)."""
    delivered = delivered_by_day(db, start, end)
    costs = {c.cost_date: c.amount or 0.0 for c in db.query(TransportDayCost).filter(
        TransportDayCost.cost_date >= start, TransportDayCost.cost_date <= end).all()}
    share: Dict[int, float] = {}
    for day, dv in delivered.items():
        cost = costs.get(day, 0.0)
        if dv["pending"] or not cost or dv["litres"] <= 0:
            continue
        for c_id, got in dv["by_customer"].items():
            if customer_id and c_id != customer_id:
                continue
            share[c_id] = share.get(c_id, 0.0) + cost * got / dv["litres"]
    return share
