from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.auth import phone_taken
from backend.app.core.security import hash_password, validate_new_password
from backend.app.database import get_db
from backend.app.models.entities import Branch, Customer, User

router = APIRouter(prefix="/drivers", tags=["Delivery Boys"])


class DriverSchema(BaseModel):
    full_name: str
    phone: str
    is_active: bool = True
    password: Optional[str] = None  # required when adding; blank on edit keeps the current password


def _driver_dict(db: Session, u: User) -> dict:
    customers = db.query(Customer).filter(Customer.assigned_driver_id == u.id).order_by(Customer.customer_code).all()
    return {
        "id": u.id,
        "full_name": u.full_name,
        "phone": u.phone,
        "is_active": u.is_active,
        "customers_count": len(customers),
        "customers": [c.business_name for c in customers],
    }


def _clean(payload: DriverSchema):
    name, phone = payload.full_name.strip(), payload.phone.strip()
    if not name or not phone:
        raise HTTPException(status_code=400, detail="Name and phone are required")
    return name, phone


@router.get("/")
def list_drivers(db: Session = Depends(get_db)):
    drivers = db.query(User).filter(User.role == "driver").order_by(User.full_name).all()
    return [_driver_dict(db, u) for u in drivers]


@router.post("/")
def create_driver(payload: DriverSchema, db: Session = Depends(get_db)):
    name, phone = _clean(payload)
    if phone_taken(db, phone):
        raise HTTPException(status_code=400, detail="A login with this mobile number already exists")
    if not payload.password:
        raise HTTPException(status_code=400, detail="Set a password so the delivery boy can log in")
    validate_new_password(payload.password)
    digits = "".join(ch for ch in phone if ch.isdigit()) or str(db.query(User).count() + 1)
    username = f"driver_{digits}"
    branch = db.query(Branch).order_by(Branch.id).first()
    user = User(
        branch_id=branch.id if branch else None,
        username=username,
        email=f"{username}@drivers.local",  # email is required by the users table; drivers log in by phone
        password_hash=hash_password(payload.password),
        full_name=name,
        phone=phone,
        role="driver",
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"status": "success", "driver": _driver_dict(db, user)}


@router.put("/{driver_id}")
def update_driver(driver_id: int, payload: DriverSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == driver_id, User.role == "driver").first()
    if not user:
        raise HTTPException(status_code=404, detail="Delivery boy not found")
    name, phone = _clean(payload)
    if phone_taken(db, phone, exclude_user_id=user.id):
        raise HTTPException(status_code=400, detail="Another login already uses this mobile number")
    if payload.password:
        validate_new_password(payload.password)
        user.password_hash = hash_password(payload.password)
    user.full_name, user.phone, user.is_active = name, phone, payload.is_active
    db.commit()
    return {"status": "success", "driver": _driver_dict(db, user)}
