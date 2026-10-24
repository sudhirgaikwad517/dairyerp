from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from backend.app.database import get_db
from backend.app.api.reports import build_sales_report
from backend.app.services.day_transport import transport_report
from backend.app.services.billing_service import unbilled_amounts
from backend.app.models.entities import (
    Customer, Order, MilkProcurement, ProductionBatch, DeliveryTrip, Delivery, Vehicle, User
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/overview")
def get_dashboard_overview(
    on: Optional[date] = Query(default=None, description="Day to show (default: today)"),
    db: Session = Depends(get_db)
):
    """
    Live overview for one day (default today), computed entirely from the database:
    Milk Procurement, Production, Dispatched, Wastage, Closing Stock,
    Today's Sales, Transport Cost, Outstanding, Orders, Active Drivers/Vehicles.
    """
    today = on or date.today()

    # Milk Procurement (today)
    procurements = db.query(MilkProcurement).filter(MilkProcurement.collection_date == today).all()
    procured_litres = sum(p.quantity_litres for p in procurements)
    accepted_litres = sum(p.quantity_litres for p in procurements if p.quality_status == "accepted")
    avg_fat = (
        sum(p.fat_pct * p.quantity_litres for p in procurements) / procured_litres
        if procured_litres > 0 else 0.0
    )

    # Production (today) - liquid milk in litres, solid products (curd, paneer) in KG kept separate
    batches = db.query(ProductionBatch).filter(ProductionBatch.production_date == today).all()
    production_litres = sum(b.output_quantity for b in batches if (b.output_unit or "L").upper() == "L")
    production_kg = sum(b.output_quantity for b in batches if (b.output_unit or "L").upper() != "L")
    raw_milk_used = sum(b.raw_milk_input_litres for b in batches)
    wastage_litres = sum(b.wastage_litres for b in batches)

    # Dispatch (today's trips) - delivered milk litres
    todays_trips = db.query(DeliveryTrip).filter(DeliveryTrip.trip_date == today).all()
    trip_ids = [t.id for t in todays_trips]
    dispatched_litres = 0.0
    if trip_ids:
        dispatched_litres = db.query(func.coalesce(func.sum(Delivery.total_delivered_litres), 0.0)).filter(
            Delivery.trip_id.in_(trip_ids)
        ).scalar()

    # Closing stock:
    #   packed milk  = milk packed today - milk dispatched today
    #   raw milk     = milk procured today - raw milk used in production today
    closing_stock_litres = max(0.0, production_litres - dispatched_litres)
    raw_milk_balance = max(0.0, procured_litres - raw_milk_used)

    # Orders & Sales: the same figures as the Sales Register for this day. Sales = milk actually
    # delivered less approved claims; orders not delivered yet are shown separately, not as sales.
    todays_orders = db.query(Order).filter(Order.delivery_date == today, Order.status != "cancelled").all()
    delivered_statuses = {"delivered", "invoiced", "paid"}
    delivered_orders_today = sum(1 for o in todays_orders if o.status in delivered_statuses)
    recon = build_sales_report(db, today, today, "daily", today.isoformat())["reconciliation"]

    # Transport: the day's total cost / milk delivered to all customers (same as the Transport tab).
    # Cost per litre only once every delivery of the day is done; part-way it would look far too high.
    tday = transport_report(db, today, today)["days"]
    tday = tday[0] if tday else None
    transport_cost = tday["cost"] if tday else 0.0
    transport_in_progress = bool(tday and tday["in_progress"])
    cost_per_litre = tday["cost_per_litre"] if tday else None

    # Outstanding: money customers owe (advances paid by others are shown separately, not netted off)
    # Bills not yet paid plus milk delivered but not billed yet
    unbilled = unbilled_amounts(db)
    balances = [(c.current_outstanding or 0.0) + unbilled.get(c.id, 0.0) for c in db.query(Customer).all()]
    total_dues = round(sum(b for b in balances if b > 0), 2)
    total_advance = round(-sum(b for b in balances if b < 0), 2)
    customers_with_dues = sum(1 for b in balances if b > 0)

    # Operations
    total_orders = db.query(Order).count()
    pending_orders = db.query(Order).filter(
        Order.status.in_(["created", "confirmed", "packed", "assigned", "out_for_delivery"])).count()
    delivered_orders = db.query(Order).filter(Order.status.in_(list(delivered_statuses))).count()
    total_customers = db.query(Customer).filter(Customer.is_active == True).count()
    active_vehicles = db.query(Vehicle).filter(Vehicle.is_active == True).count()
    active_drivers = db.query(User).filter(User.role == "driver", User.is_active == True).count()

    return {
        "date": today.isoformat(),
        "procurement": {
            "today_total_litres": round(procured_litres, 2),
            "collections_count": len(procurements),
            "accepted_pct": round(accepted_litres / procured_litres * 100.0, 1) if procured_litres > 0 else 0.0,
            "avg_fat_pct": round(avg_fat, 2),
            "unit": "L"
        },
        "production": {
            "today_total_litres": round(production_litres, 2),
            "today_total_kg": round(production_kg, 2),
            "raw_milk_used_litres": round(raw_milk_used, 2),
            "batches_count": len(batches),
            "unit": "L"
        },
        "dispatch": {
            "today_dispatched_litres": round(dispatched_litres, 2),
            "trips_count": len(todays_trips),
            "unit": "L"
        },
        "wastage": {
            "today_wastage_litres": round(wastage_litres, 2),
            "wastage_pct": round(wastage_litres / raw_milk_used * 100.0, 2) if raw_milk_used > 0 else 0.0,
            "unit": "L"
        },
        "closing_stock": {
            "closing_stock_litres": round(closing_stock_litres, 2),
            "raw_milk_balance_litres": round(raw_milk_balance, 2),
            "unit": "L"
        },
        "financials": {
            "today_sales": recon["net_sales"]["amount"],
            "today_sales_litres": recon["net_sales"]["quantity"],
            "orders_value": recon["ordered"]["amount"],
            "pending_delivery_amount": recon["pending_delivery"]["amount"],
            "pending_delivery_count": recon["pending_delivery"]["count"],
            "claims_amount": round(recon["claims_deducted"]["amount"] + recon["claims_refunded"]["amount"], 2),
            "short_amount": round(recon["short_delivered"]["amount"] + recon["not_delivered"]["amount"], 2),
            "today_orders_count": len(todays_orders),
            "transport_cost": transport_cost,
            "transport_cost_set": bool(tday and tday["cost_set"]),
            "transport_litres": tday["litres"] if tday else 0.0,
            "transport_in_progress": transport_in_progress,
            "outstanding_amount": total_dues,
            "advance_amount": total_advance,
            "net_outstanding": round(total_dues - total_advance, 2),
            "customers_with_dues": customers_with_dues,
            "transport_cost_per_litre": cost_per_litre
        },
        "operations": {
            "total_customers": total_customers,
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "delivered_orders": delivered_orders,
            "delivered_orders_today": delivered_orders_today,
            "active_vehicles": active_vehicles,
            "active_drivers": active_drivers
        }
    }
