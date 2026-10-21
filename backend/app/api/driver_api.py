from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from backend.app.core.security import ADMIN_ROLES, require_driver
from backend.app.services.attachments import attachments_for, save_photo
from backend.app.services.billing_service import apply_payment_to_bills, find_overlapping_bill, recalculate_ledger
from backend.app.services import notifications
from backend.app.services.dispatch_control import dispatch_status
from backend.app.database import get_db
from backend.app.models.entities import (
    DeliveryTrip, Delivery, Order, OrderItem, Product, Customer, Payment, CustomerLedger, User, DeliveryIssue
)
from backend.app.services.order_lines import is_litre, whole_unit

router = APIRouter(prefix="/driver", tags=["Driver Web Portal"])

class ProblemSchema(BaseModel):
    reason: str  # vehicle_breakdown, traffic, weather, milk_shortage, accident, other
    note: Optional[str] = None


DONE_STATUSES = ("delivered", "partially_delivered")
LOCKED_MESSAGE = "This delivery is already confirmed and cannot be changed. Please call the dairy office."


class ItemDelivered(BaseModel):
    item_id: int
    delivered_quantity: float


class DeliveryCompletionSchema(BaseModel):
    delivery_id: int
    # What was handed over, per product (order item). Older apps send only delivered_litres,
    # which is accepted when the order has a single product.
    items: Optional[List[ItemDelivered]] = None
    delivered_litres: Optional[float] = None
    shortage_reason: str = "none" # leakage, damage, customer_rejection, stock_shortage, delivery_issue
    shortage_notes: Optional[str] = None
    recipient_name: Optional[str] = None
    signature_data_url: Optional[str] = None
    collected_amount: float = 0.0
    payment_method: Optional[str] = None # cash, upi

def _driver_deliveries_query(db: Session, driver_id: int):
    """
    A delivery boy's stops: customers assigned to him, plus customers with no delivery boy
    on trips he drives.
    """
    return db.query(Delivery).join(Customer, Customer.id == Delivery.customer_id).join(
        DeliveryTrip, DeliveryTrip.id == Delivery.trip_id
    ).filter(or_(
        Customer.assigned_driver_id == driver_id,
        and_(Customer.assigned_driver_id.is_(None), DeliveryTrip.driver_id == driver_id)
    ))


def _resolve_driver_id(user: User, driver_id: Optional[int]) -> int:
    # Delivery boys always see their own stops; the admin may look at anyone's
    if user.role in ADMIN_ROLES and driver_id:
        return driver_id
    return user.id


@router.get("/my-trips")
def get_driver_assigned_trips(
    driver_id: Optional[int] = None,
    user: User = Depends(require_driver),
    db: Session = Depends(get_db)
):
    """
    Returns the delivery boy's stops for today, or for his most recent delivery day if none today.
    """
    driver_id = _resolve_driver_id(user, driver_id)
    query = _driver_deliveries_query(db, driver_id)
    today = date.today()
    day = today
    # Today's automatic dispatch (time, or the dairy's hold note), shown on the delivery app
    dispatch = dispatch_status(db, today)
    issues = [{"reason": i.reason, "note": i.note, "stops_affected": i.stops_affected,
               "created_at": i.created_at.isoformat(timespec="minutes")}
              for i in db.query(DeliveryIssue).filter(DeliveryIssue.day == today, DeliveryIssue.driver_id == driver_id)
              .order_by(DeliveryIssue.id.desc()).all()]
    if not query.filter(DeliveryTrip.trip_date == day).first():
        latest = query.order_by(DeliveryTrip.trip_date.desc()).first()
        if not latest:
            return {"active_trip": None, "stops": [], "dispatch": dispatch, "issues": issues}
        day = latest.trip.trip_date

    deliveries = query.filter(DeliveryTrip.trip_date == day).order_by(
        DeliveryTrip.route_id.asc(), Delivery.delivery_sequence.asc()
    ).all()

    products = {p.id: p for p in db.query(Product).all()}
    stops = []
    for d in deliveries:
        c = d.customer
        o = d.order
        o_items = db.query(OrderItem).filter(OrderItem.order_id == o.id).order_by(OrderItem.id).all() if o else []
        items = [{
            "item_id": i.id, "product_id": i.product_id,
            "product_name": products[i.product_id].product_name if i.product_id in products else "Product",
            "unit": products[i.product_id].unit if i.product_id in products else "",
            "whole": whole_unit(products[i.product_id].unit) if i.product_id in products else False,
            "ordered": i.ordered_quantity,
            "delivered": i.delivered_quantity,
            "rate": i.unit_price,
        } for i in o_items]
        stops.append({
            "delivery_id": d.id,
            "sequence": len(stops) + 1,
            "status": d.status,
            "customer_id": c.id,
            "business_name": c.business_name,
            "contact_person": c.contact_person,
            "phone": c.phone,
            "delivery_address": c.delivery_address,
            "order_number": o.order_number if o else "",
            "ordered_litres": d.total_ordered_litres,
            "delivered_litres": d.total_delivered_litres,
            "shortage_litres": d.total_shortage_litres,
            "shortage_reason": d.shortage_reason,
            "shortage_notes": d.shortage_notes,
            "collected_amount": d.collected_amount,
            "collected_payment_method": d.collected_payment_method,
            "photo_ids": [a.id for a in attachments_for(db, "delivery", d.id)],
            "has_signature": bool(d.customer_signature_url),
            "items": items,
            "order_amount": o.total_amount if o else 0.0,
            # A delivery boy confirms a stop once; after that only the office can correct it
            "locked": d.status in DONE_STATUSES and user.role not in ADMIN_ROLES,
        })

    trips = {d.trip_id: d.trip for d in deliveries}
    first_trip = deliveries[0].trip
    route_names = sorted({t.route.route_name for t in trips.values() if t.route})
    return {
        "active_trip": {
            "trip_id": first_trip.id,
            "trip_number": ", ".join(sorted(t.trip_number for t in trips.values())),
            "trip_date": day.isoformat(),
            "is_today": day == date.today(),
            "route_name": " + ".join(route_names) if route_names else "Route",
            "vehicle_number": ", ".join(sorted({t.vehicle.registration_number for t in trips.values() if t.vehicle})),
            "opening_km": first_trip.opening_km,
            "closing_km": first_trip.closing_km,
            "status": first_trip.status,
            "total_loaded_litres": sum(d.total_ordered_litres for d in deliveries)
        },
        "stops": stops,
        "dispatch": dispatch,
        "issues": issues,
    }


@router.post("/report-problem")
def report_problem(payload: ProblemSchema, user: User = Depends(require_driver), db: Session = Depends(get_db)):
    """
    Delivery boy reports a problem on the way (vehicle breakdown, traffic...). Every customer of his
    still waiting for today's milk is told it is late; the admin is told too.
    """
    if payload.reason not in notifications.ISSUE_REASONS:
        raise HTTPException(status_code=400, detail="Choose what the problem is")
    note = (payload.note or "").strip() or None
    if payload.reason == "other" and not note:
        raise HTTPException(status_code=400, detail="Write what the problem is")
    today = date.today()
    waiting = _driver_deliveries_query(db, user.id).filter(
        DeliveryTrip.trip_date == today, Delivery.status.notin_(DONE_STATUSES)
    ).all()
    if not waiting:
        raise HTTPException(status_code=400, detail="No customers are waiting for milk from you today")
    for d in waiting:
        notifications.delivery_delayed(db, d.customer, today, payload.reason, note)
    db.add(DeliveryIssue(day=today, driver_id=user.id, reason=payload.reason, note=note, stops_affected=len(waiting)))
    notifications.issue_reported(db, user.full_name or user.username, today, payload.reason, note, len(waiting))
    db.commit()
    return {"status": "success", "customers_told": len(waiting)}

@router.post("/complete-delivery")
def complete_delivery_stop(
    payload: DeliveryCompletionSchema,
    user: User = Depends(require_driver),
    db: Session = Depends(get_db)
):
    """
    Driver submits delivered quantity, shortage quantity & reason,
    customer signature, and collected cash/UPI payment.
    """
    delivery = db.query(Delivery).filter(Delivery.id == payload.delivery_id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if user.role not in ADMIN_ROLES and not _driver_deliveries_query(db, user.id).filter(Delivery.id == delivery.id).first():
        raise HTTPException(status_code=403, detail="This delivery is not assigned to you")
    if delivery.order:
        billed = find_overlapping_bill(db, delivery.customer_id, delivery.order.delivery_date, delivery.order.delivery_date)
        if billed:
            raise HTTPException(status_code=400, detail=f"This day is already billed in {billed.invoice_number}; "
                                                        f"ask the dairy office to correct it")
    if user.role not in ADMIN_ROLES and delivery.status in DONE_STATUSES:
        raise HTTPException(status_code=400, detail=LOCKED_MESSAGE)
    if not attachments_for(db, "delivery", delivery.id):
        raise HTTPException(status_code=400, detail="Take a photo of the delivery first")

    # What was handed over for each product on the order
    o_items = db.query(OrderItem).filter(OrderItem.order_id == delivery.order_id).order_by(OrderItem.id).all()
    if not o_items:
        raise HTTPException(status_code=400, detail="This order has no products")
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_([i.product_id for i in o_items])).all()}
    if payload.items is not None:
        given = {}
        for it in payload.items:
            if it.item_id in given:
                raise HTTPException(status_code=400, detail="A product is listed twice")
            given[it.item_id] = it.delivered_quantity
        if set(given) != {i.id for i in o_items}:
            raise HTTPException(status_code=400, detail="Enter the delivered quantity for every product on the order")
    elif payload.delivered_litres is not None and len(o_items) == 1:
        given = {o_items[0].id: payload.delivered_litres}
    else:
        raise HTTPException(status_code=400, detail="Enter the delivered quantity for every product on the order")
    for i in o_items:
        q, p = given[i.id], products.get(i.product_id)
        name = p.product_name if p else "a product"
        if q is None or q < 0:
            raise HTTPException(status_code=400, detail=f"Delivered quantity of {name} cannot be negative")
        if q > (i.ordered_quantity or 0) + 1e-9:
            raise HTTPException(status_code=400, detail=f"Delivered {name} cannot be more than ordered ({i.ordered_quantity:g})")
        if p and whole_unit(p.unit) and abs(q - round(q)) > 1e-9:
            raise HTTPException(status_code=400, detail=f"{name} is counted per {p.unit}; enter a whole number")
    any_short = any(round((i.ordered_quantity or 0) - given[i.id], 3) > 0 for i in o_items)
    if any_short and (payload.shortage_reason or "none") == "none":
        raise HTTPException(status_code=400, detail="Select why less was delivered")

    edited = delivery.status in ("delivered", "partially_delivered")
    for i in o_items:
        i.delivered_quantity = round(given[i.id], 3)
    litre_items = [i for i in o_items if is_litre(products.get(i.product_id))]
    delivery.total_ordered_litres = round(sum(i.ordered_quantity or 0 for i in litre_items), 3)
    delivery.total_delivered_litres = round(sum(i.delivered_quantity for i in litre_items), 3)
    delivery.total_shortage_litres = round(max(0.0, delivery.total_ordered_litres - delivery.total_delivered_litres), 3)
    delivery.shortage_reason = payload.shortage_reason if any_short else "none"
    delivery.shortage_notes = payload.shortage_notes
    delivery.delivered_to_person = payload.recipient_name
    if payload.signature_data_url:
        if not payload.signature_data_url.startswith("data:image/png;base64,") or len(payload.signature_data_url) > 300_000:
            raise HTTPException(status_code=400, detail="Invalid signature image")
        delivery.customer_signature_url = payload.signature_data_url  # keep the earlier signature when not re-signed
    delivery.status = "partially_delivered" if any_short else "delivered"
    delivery.departure_time = datetime.now()  # local time, same as trip departure/return times

    # Payment Collection by Driver
    if payload.collected_amount > 0:
        # Editing a delivery later only adds the new money; earlier collections stay recorded
        delivery.collected_amount = round((delivery.collected_amount or 0.0) + payload.collected_amount, 2)
        delivery.collected_payment_method = payload.payment_method or "cash"

        # Record payment
        pay = Payment(
            payment_number=f"PAY-DRV-{delivery.id}-{int(datetime.utcnow().timestamp())}",
            customer_id=delivery.customer_id,
            amount=payload.collected_amount,
            reference_number=f"DELIVERY-{delivery.id}",
            payment_method=delivery.collected_payment_method,
            remarks=f"Collected by driver for delivery #{delivery.id}"
        )
        db.add(pay)

        # Update customer ledger
        cust = db.query(Customer).filter(Customer.id == delivery.customer_id).first()
        if cust:
            # A negative balance is an advance payment; clamping at zero would lose the money
            pay.invoice_id = apply_payment_to_bills(db, cust.id, payload.collected_amount)
            ledger_entry = CustomerLedger(
                customer_id=cust.id,
                transaction_date=date.today(),
                transaction_type="payment",
                reference_number=pay.payment_number,
                debit_amount=0.0,
                credit_amount=payload.collected_amount,
                running_balance=0.0,
                narration=f"Payment received by Driver ({payload.payment_method}) at delivery"
            )
            db.add(ledger_entry)
            recalculate_ledger(db, cust)

    # Update associated order status
    if delivery.order:
        delivery.order.status = "delivered"

    day = delivery.order.delivery_date if delivery.order else (delivery.trip.trip_date if delivery.trip else date.today())
    lines = [(products[i.product_id].product_name if i.product_id in products else "Product",
              products[i.product_id].unit if i.product_id in products else "",
              i.ordered_quantity or 0.0, i.delivered_quantity or 0.0) for i in o_items]
    notifications.delivery_done(db, delivery.customer, day, lines,
                                (payload.shortage_reason or "").strip() or None if any_short else None,
                                user.full_name or user.username, edited)
    if payload.collected_amount > 0:
        notifications.payment_received(db, delivery.customer, payload.collected_amount, delivery.collected_payment_method,
                                       date.today(), collected_by=user.full_name or user.username)

    # Trip totals: delivered litres and the route's fixed cost spread per litre
    trip = delivery.trip
    if trip:
        db.flush()
        delivered = sum(d.total_delivered_litres or 0.0 for d in trip.deliveries)
        trip.total_milk_litres_delivered = delivered
        trip.transport_cost_per_litre = round((trip.total_transport_cost or 0.0) / delivered, 3) if delivered else 0.0

    db.commit()
    return {
        "status": "success",
        "message": f"Delivery #{delivery.id} confirmed for {delivery.customer.business_name}",
        "delivered_litres": delivery.total_delivered_litres,
        "shortage_litres": delivery.total_shortage_litres,
        "items": [{"item_id": i.id, "ordered": i.ordered_quantity, "delivered": i.delivered_quantity} for i in o_items],
        "collected_amount": delivery.collected_amount
    }


@router.post("/deliveries/{delivery_id}/photo")
async def upload_delivery_photo(
    delivery_id: int,
    photo: UploadFile = File(...),
    user: User = Depends(require_driver),
    db: Session = Depends(get_db)
):
    """Proof of delivery: photo taken by the delivery boy at the customer's place."""
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if user.role not in ADMIN_ROLES and not _driver_deliveries_query(db, user.id).filter(Delivery.id == delivery.id).first():
        raise HTTPException(status_code=403, detail="This delivery is not assigned to you")
    if user.role not in ADMIN_ROLES and delivery.status in DONE_STATUSES:
        raise HTTPException(status_code=400, detail=LOCKED_MESSAGE)
    att = await save_photo(db, photo, "delivery", delivery.id, user.id)
    db.commit()
    return {"status": "success", "photo_id": att.id}
