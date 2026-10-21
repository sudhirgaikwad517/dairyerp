from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.security import (
    ADMIN_ROLES, create_access_token, get_current_user, hash_password, is_hashed, require_admin,
    validate_new_password, verify_password
)
from backend.app.database import get_db
from backend.app.models.entities import Branch, Customer, User

router = APIRouter(prefix="/auth", tags=["Login & Accounts"])

APP_ROLES = {
    "admin": ADMIN_ROLES,
    "driver": {"driver"},
    "customer": {"customer"},
    "mobile": ADMIN_ROLES | {"customer"},  # Flutter app: customers, plus a smaller admin section
}


class LoginSchema(BaseModel):
    username: str  # username or mobile number
    password: str
    app: Optional[str] = None  # admin | driver | customer | mobile: rejects logins meant for another app


class ChangePasswordSchema(BaseModel):
    current_password: str
    new_password: str


class SetLoginSchema(BaseModel):
    password: Optional[str] = None  # required when creating a login; blank keeps the current password
    is_active: bool = True


def digits(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def find_user_by_login(db: Session, identifier: str) -> Optional[User]:
    ident = identifier.strip()
    user = db.query(User).filter(User.username.ilike(ident)).first()
    if user:
        return user
    d = digits(ident)
    if len(d) >= 10:
        last10 = d[-10:]
        for u in db.query(User).all():
            if digits(u.phone)[-10:] == last10:
                return u
    return None


def phone_taken(db: Session, phone: str, exclude_user_id: Optional[int] = None) -> bool:
    last10 = digits(phone)[-10:]
    if len(last10) < 10:
        return False
    return any(
        digits(u.phone)[-10:] == last10 and u.id != exclude_user_id
        for u in db.query(User).all()
    )


def user_info(db: Session, user: User) -> dict:
    info = {"id": user.id, "username": user.username, "full_name": user.full_name,
            "phone": user.phone, "role": user.role}
    if user.role == "customer":
        c = db.query(Customer).filter(Customer.user_id == user.id).first()
        info["customer_id"] = c.id if c else None
        info["customer_name"] = c.business_name if c else None
    return info


@router.post("/login")
def login(payload: LoginSchema, db: Session = Depends(get_db)):
    user = find_user_by_login(db, payload.username)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong mobile number / username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This login is disabled. Please contact the dairy.")
    if payload.app and user.role not in APP_ROLES.get(payload.app, set()):
        raise HTTPException(status_code=403, detail=f"This login cannot be used in the {payload.app} app")
    if user.role == "customer":
        c = db.query(Customer).filter(Customer.user_id == user.id).first()
        if not c or not c.is_active:
            raise HTTPException(status_code=403, detail="This customer account is inactive. Please contact the dairy.")
    if not is_hashed(user.password_hash):
        user.password_hash = hash_password(payload.password)
        db.commit()
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user_info(db, user)}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_info(db, user)


@router.post("/change-password")
def change_password(payload: ChangePasswordSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    validate_new_password(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "success", "message": "Password changed"}


# ---- Admin: manage customer and delivery-boy logins ----

@router.put("/customers/{customer_id}/login", dependencies=[Depends(require_admin)])
def set_customer_login(customer_id: int, payload: SetLoginSchema, db: Session = Depends(get_db)):
    """Create or update the app login for a customer. The customer logs in with their mobile number."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if len(digits(customer.phone)) < 10:
        raise HTTPException(status_code=400, detail="Customer needs a valid 10-digit mobile number to get a login")

    user = db.query(User).filter(User.id == customer.user_id).first() if customer.user_id else None
    if phone_taken(db, customer.phone, exclude_user_id=user.id if user else None):
        raise HTTPException(status_code=400, detail="Another login already uses this mobile number")

    if not user:
        if not payload.password:
            raise HTTPException(status_code=400, detail="Set a password to create the login")
        validate_new_password(payload.password)
        branch = db.query(Branch).order_by(Branch.id).first()
        username = f"cust_{customer.customer_code.lower().replace('-', '')}"
        user = User(
            branch_id=branch.id if branch else None, username=username,
            email=f"{username}@customers.local",  # email is required by the users table; customers log in by mobile
            password_hash=hash_password(payload.password), full_name=customer.business_name,
            phone=customer.phone, role="customer", is_active=payload.is_active,
        )
        db.add(user)
        db.flush()
        customer.user_id = user.id
        message = f"Login created for {customer.business_name}"
    else:
        if payload.password:
            validate_new_password(payload.password)
            user.password_hash = hash_password(payload.password)
        user.phone = customer.phone
        user.full_name = customer.business_name
        user.is_active = payload.is_active
        message = f"Login updated for {customer.business_name}"
    db.commit()
    return {"status": "success", "message": message, "login_id": customer.phone}


@router.put("/drivers/{driver_id}/login", dependencies=[Depends(require_admin)])
def set_driver_login(driver_id: int, payload: SetLoginSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == driver_id, User.role == "driver").first()
    if not user:
        raise HTTPException(status_code=404, detail="Delivery boy not found")
    if not payload.password:
        raise HTTPException(status_code=400, detail="Enter a new password")
    validate_new_password(payload.password)
    user.password_hash = hash_password(payload.password)
    db.commit()
    return {"status": "success", "message": f"Password set for {user.full_name}", "login_id": user.phone}
