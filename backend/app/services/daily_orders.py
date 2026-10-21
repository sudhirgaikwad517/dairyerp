"""
Day-by-day ordering (one order per customer per day) and dispatch (turning a day's orders into delivery trips).

Only real orders exist: a customer gets milk on a day only if they (or the admin) ordered for that day.
Customers can place a day's order until the cut-off time on the evening before (set by the admin,
default 21:00). Once placed, a customer cannot change or cancel it; only the admin can.
"""
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    BusinessProfile, Customer, Delivery, DeliveryRoute, DeliveryTrip, Order, OrderItem, Product, Vehicle
)
from backend.app.services import notifications
from backend.app.services.order_lines import order_what, whole_unit
from backend.app.services.order_pricing import fill_order_items

EDITABLE_STATUSES = ("created", "confirmed")
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
MAX_DAYS_AHEAD = 30
DEFAULT_CUTOFF = "21:00"


def cutoff_time(db: Session) -> time:
    profile = db.query(BusinessProfile).first()
    value = (profile.order_cutoff_time if profile else None) or DEFAULT_CUTOFF
    try:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return time(21, 0)


def order_deadline(db: Session, day: date, cutoff: Optional[time] = None) -> datetime:
    """Last moment a customer can place / change the order for `day`: cut-off time on the previous day."""
    return datetime.combine(day - timedelta(days=1), cutoff or cutoff_time(db))


def _db_weekday(day: date) -> int:
    return day.isoweekday() % 7  # 0=Sunday .. 6=Saturday


def order_for_day(db: Session, customer_id: int, day: date) -> Optional[Order]:
    """The customer's order for a day. Newest wins if old data has several."""
    return db.query(Order).filter(Order.customer_id == customer_id, Order.delivery_date == day).order_by(
        Order.id.desc()
    ).first()


def _order_items(db: Session, order: Order) -> List[Dict]:
    out = []
    for i in db.query(OrderItem).filter(OrderItem.order_id == order.id).order_by(OrderItem.id).all():
        p = db.query(Product).filter(Product.id == i.product_id).first()
        out.append({"product_id": i.product_id, "product_name": p.product_name if p else "Product",
                    "unit": p.unit if p else "L", "quantity": i.ordered_quantity, "rate": i.unit_price,
                    "amount": i.total_amount, "delivered_quantity": i.delivered_quantity})
    return out


def customer_days(db: Session, customer: Customer, start: date, days: int) -> List[Dict]:
    now = datetime.now()
    cutoff = cutoff_time(db)
    result = []
    for n in range(days):
        day = start + timedelta(days=n)
        order = order_for_day(db, customer.id, day)
        if order and order.status == "cancelled":
            order_active = False
        else:
            order_active = order is not None
        deadline = order_deadline(db, day, cutoff)
        open_for_orders = now <= deadline
        # One order per day, placed once: after that only the dairy can change it
        editable = open_for_orders and not order_active
        items = _order_items(db, order) if order_active else []
        delivery = None
        if order_active:
            d = db.query(Delivery).filter(Delivery.order_id == order.id).first()
            if d:
                delivery = {"status": d.status, "delivered_litres": d.total_delivered_litres,
                            "shortage_litres": d.total_shortage_litres}
        if order_active:
            status = order.status
        elif order and order.status == "cancelled":
            status = "cancelled"
        else:
            status = "no_order"
        result.append({
            "date": day.isoformat(),
            "day_name": DAY_NAMES[_db_weekday(day)],
            "items": items,
            "total_qty": round(sum(i["quantity"] for i in items), 2),
            "total_amount": round(sum(i["amount"] for i in items), 2),
            "source": "order" if order_active else "none",
            "status": status,
            "order_number": order.order_number if order_active else None,
            "editable": editable,
            "can_cancel": False,  # customers cannot cancel; only the admin can
            "order_deadline": deadline.isoformat(timespec="minutes"),
            "orders_closed": not open_for_orders,
            "delivery": delivery,
        })
    return result


def set_day_quantity(db: Session, customer: Customer, day: date, items: List[Tuple[int, float]],
                     placed_by: str, is_admin: bool = False) -> Order:
    """
    Create or change the customer's order for one day.
    Customers: place it once, until the cut-off time the evening before; they cannot change or cancel it.
    Admin: any time before dispatch; all quantities 0 cancels the order.
    """
    now = datetime.now()
    today = now.date()
    if day < today:
        raise HTTPException(status_code=400, detail="You cannot change a past day")
    if day > today + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(status_code=400, detail=f"Orders can be placed up to {MAX_DAYS_AHEAD} days ahead")
    if not is_admin:
        deadline = order_deadline(db, day)
        if now > deadline:
            raise HTTPException(
                status_code=400,
                detail=f"Orders for {day:%d %b} closed at {deadline:%I:%M %p} on {deadline:%d %b}. Please call the dairy."
            )
    from backend.app.services.billing_service import find_overlapping_bill  # avoid import cycle
    billed = find_overlapping_bill(db, customer.id, day, day)
    if billed:
        raise HTTPException(status_code=400, detail=f"{day:%d %b} is already billed in {billed.invoice_number}. "
                                                    f"Delete that bill first to change this day.")
    order = order_for_day(db, customer.id, day)
    products = {p.id: p for p in db.query(Product).all()}
    # Products already on this day's order may stay on it even if they were switched off since
    already = {i.product_id for i in db.query(OrderItem).filter(OrderItem.order_id == order.id).all()} if order else set()
    seen = set()
    for pid, qty in items:
        p = products.get(pid)
        if pid in seen:
            raise HTTPException(status_code=400, detail="The same product is listed twice")
        seen.add(pid)
        if qty is None or qty < 0:
            raise HTTPException(status_code=400, detail="Quantity cannot be negative")
        if not p or (not p.is_active and not (is_admin and pid in already) and qty > 0):
            raise HTTPException(status_code=400, detail="One of the products is not available")
        if qty > 0 and whole_unit(p.unit) and abs(qty - round(qty)) > 1e-9:
            raise HTTPException(status_code=400, detail=f"{p.product_name} is sold per {p.unit}; enter a whole number")
        if qty > 100000:
            raise HTTPException(status_code=400, detail=f"Quantity for {p.product_name} is too large")
    wanted = [(pid, round(qty, 3)) for pid, qty in items if qty and qty > 0]
    if not wanted and not is_admin:
        raise HTTPException(status_code=400, detail="Add a quantity for at least one product.")

    if not is_admin and order and order.status != "cancelled":
        raise HTTPException(status_code=400, detail=(
            f"You have already ordered {order_what(db, order)} for {day:%d %b}. An order cannot be changed "
            f"once placed. Please call the dairy."))
    if order and order.status not in EDITABLE_STATUSES and order.status != "cancelled":
        raise HTTPException(status_code=400, detail="This day's milk is already out for delivery and cannot be changed")
    if not wanted and (order is None or order.status == "cancelled"):
        raise HTTPException(status_code=400, detail="There is no order for this day to cancel")

    previous_what = order_what(db, order) if order and order.status != "cancelled" else None
    if not order:
        order = Order(
            order_number=f"ORD-{day:%Y%m%d}-{customer.customer_code[-3:]}-{db.query(Order).count() + 1}",
            customer_id=customer.id, branch_id=customer.branch_id, order_date=today, delivery_date=day,
            status="confirmed",
        )
        db.add(order)
        db.flush()
    else:
        db.query(OrderItem).filter(OrderItem.order_id == order.id).delete()

    order.is_standing_order = False
    order.order_date = today
    stamp = now.strftime("%d %b %H:%M")
    if wanted:
        order.status = "confirmed"
        order.notes = f"Set by {placed_by} on {stamp}"
        fill_order_items(db, order, customer, wanted)
    else:
        order.status = "cancelled"
        order.notes = f"Cancelled by {placed_by} on {stamp}"
        order.subtotal = order.tax_amount = order.transport_charge = order.total_amount = order.total_litres = 0.0
    db.flush()
    what = order_what(db, order) if wanted else None
    if is_admin:
        notifications.order_set_by_dairy(db, customer, day, what, previous_what)
    else:
        notifications.order_confirmed(db, customer, day, what, order.total_amount or 0.0, order.order_number)
    db.commit()
    db.refresh(order)
    return order


def dispatch_day(db: Session, day: date) -> Dict:
    """
    Put every confirmed order for the day onto its route's delivery trip (one trip per route per day),
    so delivery boys see the stops. Orders already on a trip are left alone. Dispatched orders
    become 'out_for_delivery' and can no longer be changed by the customer.
    """
    orders = db.query(Order).filter(
        Order.delivery_date == day, Order.status.in_(EDITABLE_STATUSES), Order.total_amount > 0
    ).all()
    routes = {r.id: r for r in db.query(DeliveryRoute).all()}
    created_trips, added, skipped = [], [], []
    trips: Dict[int, DeliveryTrip] = {}

    for order in sorted(orders, key=lambda o: (o.customer.assigned_route_id or 0, o.customer.route_stop_sequence or 0)):
        customer = order.customer
        if db.query(Delivery).filter(Delivery.order_id == order.id).first():
            continue
        route = routes.get(customer.assigned_route_id)
        if not route:
            skipped.append({"customer": customer.business_name, "reason": "No route assigned"})
            continue
        if not route.default_driver_id or not route.default_vehicle_id:
            skipped.append({"customer": customer.business_name, "reason": f"{route.route_name} has no default driver/vehicle"})
            continue

        trip = trips.get(route.id)
        if not trip:
            trip = db.query(DeliveryTrip).filter(
                DeliveryTrip.route_id == route.id, DeliveryTrip.trip_date == day,
                DeliveryTrip.status.in_(["scheduled", "in_transit"])
            ).first()
        if not trip:
            vehicle = db.query(Vehicle).filter(Vehicle.id == route.default_vehicle_id).first()
            n = db.query(DeliveryTrip).filter(DeliveryTrip.route_id == route.id, DeliveryTrip.trip_date == day).count() + 1
            trip = DeliveryTrip(
                trip_number=f"TRIP-{day:%Y%m%d}-{route.id:02d}" + (f"-{n}" if n > 1 else ""),
                route_id=route.id, vehicle_id=route.default_vehicle_id, driver_id=route.default_driver_id,
                trip_date=day, departure_time=datetime.now(), opening_km=vehicle.current_odometer_km if vehicle else 0.0,
                status="in_transit", total_milk_litres_loaded=0.0,
                total_transport_cost=route.fixed_daily_cost or 0.0,  # fixed per route per day
            )
            db.add(trip)
            db.flush()
            created_trips.append(trip.trip_number)
        trips[route.id] = trip

        seq = db.query(Delivery).filter(Delivery.trip_id == trip.id).count() + 1
        db.add(Delivery(
            trip_id=trip.id, order_id=order.id, customer_id=customer.id, delivery_sequence=seq,
            status="pending", total_ordered_litres=order.total_litres, total_delivered_litres=0.0,
        ))
        trip.total_milk_litres_loaded = (trip.total_milk_litres_loaded or 0.0) + order.total_litres
        order.status = "out_for_delivery"
        what = order_what(db, order)
        notifications.order_dispatched(db, customer, day, what)
        added.append({"customer": customer.business_name, "litres": order.total_litres, "what": what,
                      "amount": order.total_amount, "trip": trip.trip_number})

    db.commit()
    return {"date": day.isoformat(), "trips_created": created_trips, "orders_dispatched": added, "skipped": skipped}
