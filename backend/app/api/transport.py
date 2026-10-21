from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from backend.app.database import get_db
from backend.app.core.security import require_admin
from backend.app.models.entities import AuditLog, Customer, DeliveryRoute, DeliveryTrip, TransportDayCost, User, Vehicle
from backend.app.services.day_transport import resolve_transport_period, transport_report

router = APIRouter(prefix="/transport", tags=["Transport & Logistics"])

def _route_dict(db: Session, r: DeliveryRoute) -> dict:
    driver = db.query(User).filter(User.id == r.default_driver_id).first() if r.default_driver_id else None
    vehicle = db.query(Vehicle).filter(Vehicle.id == r.default_vehicle_id).first() if r.default_vehicle_id else None
    customers = db.query(Customer).filter(Customer.assigned_route_id == r.id, Customer.is_active == True).count()
    return {
        "id": r.id, "route_code": r.route_code, "route_name": r.route_name,
        "approx_distance_km": r.approx_distance_km, "is_active": bool(r.is_active),
        "driver_id": r.default_driver_id, "driver_name": driver.full_name if driver else None,
        "vehicle_number": vehicle.registration_number if vehicle else None,
        "vehicle_type": vehicle.vehicle_type if vehicle else None,
        "customers_count": customers,
        # Orders on this route can be dispatched only with a delivery boy and a vehicle
        "ready": bool(driver and driver.is_active and vehicle),
    }


@router.get("/routes")
def list_routes(include_inactive: bool = False, db: Session = Depends(get_db)):
    q = db.query(DeliveryRoute)
    if not include_inactive:
        q = q.filter(DeliveryRoute.is_active == True)
    return [_route_dict(db, r) for r in q.order_by(DeliveryRoute.route_code).all()]


class RouteSchema(BaseModel):
    route_name: str
    driver_id: int
    vehicle_number: str
    vehicle_type: Optional[str] = None
    approx_distance_km: Optional[float] = None
    is_active: bool = True


def _vehicle_for(db: Session, number: str, vehicle_type: Optional[str], driver_id: int) -> Vehicle:
    """The vehicle with this number, added the first time it is used."""
    vehicle = db.query(Vehicle).filter(Vehicle.registration_number == number).first()
    if not vehicle:
        vehicle = Vehicle(registration_number=number, vehicle_type=vehicle_type or "Milk Van", capacity_litres=0.0)
        db.add(vehicle)
    elif vehicle_type:
        vehicle.vehicle_type = vehicle_type
    vehicle.is_active = True
    vehicle.default_driver_id = driver_id
    db.flush()
    return vehicle


def _save_route(db: Session, admin: User, route: Optional[DeliveryRoute], payload: RouteSchema) -> dict:
    name = " ".join(payload.route_name.split())
    if not name:
        raise HTTPException(status_code=400, detail="Enter the route name")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Route name is too long")
    same = db.query(DeliveryRoute).filter(DeliveryRoute.route_name.ilike(name))
    if route:
        same = same.filter(DeliveryRoute.id != route.id)
    if same.first():
        raise HTTPException(status_code=400, detail="A route with this name already exists")
    driver = db.query(User).filter(User.id == payload.driver_id, User.role == "driver").first()
    if not driver:
        raise HTTPException(status_code=400, detail="Choose the delivery boy for this route")
    if not driver.is_active and payload.is_active:
        raise HTTPException(status_code=400, detail=f"{driver.full_name} is deactivated. Choose an active delivery boy")
    number = "".join(payload.vehicle_number.split()).upper()
    if not (4 <= len(number) <= 15) or not number.isalnum():
        raise HTTPException(status_code=400, detail="Enter the vehicle number, e.g. MH12AB1234")
    if payload.approx_distance_km is not None and payload.approx_distance_km < 0:
        raise HTTPException(status_code=400, detail="Distance cannot be negative")
    vehicle_type = " ".join((payload.vehicle_type or "").split())[:50] or None

    if route and route.is_active and not payload.is_active:
        n = db.query(Customer).filter(Customer.assigned_route_id == route.id, Customer.is_active == True).count()
        if n:
            raise HTTPException(status_code=400,
                                detail=f"{n} active customer(s) are on this route. Move them to another route first")
    old = _route_dict(db, route) if route else None
    vehicle = _vehicle_for(db, number, vehicle_type, driver.id)
    if not route:
        n = db.query(DeliveryRoute).count() + 1
        while db.query(DeliveryRoute).filter(DeliveryRoute.route_code == f"RT-{n:02d}").first():
            n += 1
        route = DeliveryRoute(route_code=f"RT-{n:02d}", route_name=name, branch_id=driver.branch_id,
                              start_location="Dairy", end_location="Dairy")
        db.add(route)
    route.route_name = name
    route.default_driver_id = driver.id
    route.default_vehicle_id = vehicle.id
    if payload.approx_distance_km is not None:
        route.approx_distance_km = round(payload.approx_distance_km, 1)
    route.is_active = payload.is_active
    db.flush()
    new = _route_dict(db, route)
    describe = lambda d: f"{d['route_name']} | {d['driver_name']} | {d['vehicle_number']} | {'active' if d['is_active'] else 'off'}"
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="ROUTE_EDIT" if old else "ROUTE_ADD",
                    entity_name="delivery_routes", entity_id=str(route.id),
                    old_values=describe(old) if old else None, new_values=describe(new)))
    db.commit()
    return _route_dict(db, route)


@router.post("/routes")
def add_route(payload: RouteSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _save_route(db, admin, None, payload)


@router.put("/routes/{route_id}")
def edit_route(route_id: int, payload: RouteSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    route = db.query(DeliveryRoute).filter(DeliveryRoute.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return _save_route(db, admin, route, payload)


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
