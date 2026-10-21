from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from backend.app.database import get_db
from backend.app.core.security import require_admin
from backend.app.models.entities import AuditLog, DeliveryRoute, DeliveryTrip, TransportDayCost, User
from backend.app.services.day_transport import resolve_transport_period, transport_report

router = APIRouter(prefix="/transport", tags=["Transport & Logistics"])

@router.get("/routes")
def list_routes(db: Session = Depends(get_db)):
    routes = db.query(DeliveryRoute).filter(DeliveryRoute.is_active == True).order_by(DeliveryRoute.route_code).all()
    return [
        {"id": r.id, "route_code": r.route_code, "route_name": r.route_name,
         "approx_distance_km": r.approx_distance_km}
        for r in routes
    ]


class DayCostSchema(BaseModel):
    amount: float
    note: Optional[str] = None


@router.get("/day-costs")
def day_costs(
    period: str = "monthly",
    ref_date: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Day-wise transport cost and cost per litre (day cost / milk delivered to all customers that day)."""
    start, end, label = resolve_transport_period(period, ref_date, start_date, end_date)
    report = transport_report(db, start, end)
    report["period"] = {"type": period, "label": label, "start_date": start.isoformat(), "end_date": end.isoformat()}
    return report


@router.put("/day-costs/{day}")
def set_day_cost(day: date, payload: DayCostSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Enter (or change) the total transport cost of one day. 0 removes it."""
    if day > date.today():
        raise HTTPException(status_code=400, detail="Transport cost can be entered for today or earlier days only")
    if payload.amount is None or payload.amount < 0:
        raise HTTPException(status_code=400, detail="Cost cannot be negative")
    row = db.query(TransportDayCost).filter(TransportDayCost.cost_date == day).first()
    old = f"₹{row.amount:g}" if row else "not set"
    note = (payload.note or "").strip()[:200] or None
    if payload.amount == 0:
        if row:
            db.delete(row)
        new = "removed"
    else:
        if not row:
            row = TransportDayCost(cost_date=day)
            db.add(row)
        row.amount = round(payload.amount, 2)
        row.note = note
        row.updated_by = admin.username
        new = f"₹{row.amount:g}"
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="TRANSPORT_DAY_COST", entity_name="transport_day_costs",
                    entity_id=day.isoformat(), old_values=old, new_values=new))
    db.commit()
    litres = transport_report(db, day, day)["days"]
    day_row = litres[0] if litres else None
    msg = f"Transport cost for {day:%d %b %Y}: {new}."
    if day_row and day_row["cost_per_litre"] is not None:
        msg += f" {day_row['litres']:g} L delivered = ₹{day_row['cost_per_litre']:.2f} per litre."
    return {"status": "success", "message": msg, "day": day_row}


@router.get("/trips")
def list_trips(db: Session = Depends(get_db)):
    trips = db.query(DeliveryTrip).order_by(DeliveryTrip.id.desc()).all()
    result = []
    for t in trips:
        result.append({
            "id": t.id,
            "trip_number": t.trip_number,
            "route_name": t.route.route_name if t.route else "",
            "vehicle_number": t.vehicle.registration_number if t.vehicle else "",
            "driver_name": t.driver.full_name if t.driver else "",
            "trip_date": t.trip_date.isoformat(),
            "opening_km": t.opening_km,
            "closing_km": t.closing_km,
            "total_distance_km": t.total_distance_km,
            "diesel_litres": t.diesel_litres,
            "diesel_cost": t.diesel_cost,
            "driver_cost": t.driver_cost,
            "toll_charges": t.toll_charges,
            "other_expenses": t.other_expenses,
            "total_transport_cost": t.total_transport_cost,
            "total_milk_litres_loaded": t.total_milk_litres_loaded,
            "total_milk_litres_delivered": t.total_milk_litres_delivered,
            "transport_cost_per_litre": t.transport_cost_per_litre,
            "status": t.status
        })
    return result
