from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from pydantic import BaseModel
from backend.app.api.auth import phone_taken
from backend.app.core.security import require_admin
from backend.app.database import get_db
from backend.app.services.billing_service import main_product
from backend.app.services.order_pricing import set_customer_price
from backend.app.models.entities import (
    Branch, Customer, CustomerLedger, CustomerPricing, DeliveryRoute, Product, User
)

router = APIRouter(prefix="/customers", tags=["Customers"])


class RateIn(BaseModel):
    product_id: int
    rate: Optional[float] = None  # None = the product's standard rate


class CustomerSchema(BaseModel):
    customer_code: Optional[str] = None  # auto-generated when blank (create only)
    business_name: str
    contact_person: str
    phone: str
    email: Optional[str] = None
    customer_type: str = "retailer"
    gstin: Optional[str] = None
    billing_address: Optional[str] = None  # defaults to delivery address
    delivery_address: str
    credit_limit: float = 50000.0
    credit_days: int = 7
    assigned_route_id: Optional[int] = None
    assigned_driver_id: Optional[int] = None  # delivery boy
    route_stop_sequence: int = 1
    is_active: bool = True
    # The customer's rate for the main product (milk); older screens only
    milk_rate: Optional[float] = None
    # The customer's rate for each product (the customer form); replaces milk_rate when given
    rates: Optional[List[RateIn]] = None
    transport_allocation_method: str = "equal_per_litre"
    negotiated_transport_rate_per_litre: float = 0.0


def _milk_product(db: Session) -> Optional[Product]:
    return db.query(Product).filter(Product.unit == "L", Product.is_active == True).order_by(Product.id).first()


def _milk_rate(db: Session, customer_id: int, milk: Optional[Product]) -> Optional[float]:
    if not milk:
        return None
    cp = db.query(CustomerPricing).filter(
        CustomerPricing.customer_id == customer_id, CustomerPricing.product_id == milk.id
    ).first()
    return cp.custom_price if cp else milk.standard_b2b_price


def _validate(db: Session, payload: CustomerSchema):
    for field in ("business_name", "contact_person", "phone", "delivery_address"):
        if not (getattr(payload, field) or "").strip():
            raise HTTPException(status_code=400, detail=f"{field.replace('_', ' ').title()} is required")
    if payload.assigned_route_id and not db.query(DeliveryRoute).filter(DeliveryRoute.id == payload.assigned_route_id).first():
        raise HTTPException(status_code=400, detail="Selected route does not exist")
    if payload.assigned_driver_id and not db.query(User).filter(
        User.id == payload.assigned_driver_id, User.role == "driver"
    ).first():
        raise HTTPException(status_code=400, detail="Selected delivery boy does not exist")
    if payload.milk_rate is not None and payload.milk_rate <= 0:
        raise HTTPException(status_code=400, detail="Milk rate must be greater than zero")
    for r in payload.rates or []:
        if r.rate is not None and r.rate <= 0:
            raise HTTPException(status_code=400, detail="A rate must be greater than zero (leave it empty for the standard rate)")
        if not db.query(Product).filter(Product.id == r.product_id).first():
            raise HTTPException(status_code=400, detail="One of the products was not found; reload the page")
    if payload.credit_limit < 0 or payload.credit_days < 0:
        raise HTTPException(status_code=400, detail="Credit limit and credit days cannot be negative")


def _apply(customer: Customer, payload: CustomerSchema):
    customer.business_name = payload.business_name.strip()
    customer.contact_person = payload.contact_person.strip()
    customer.phone = payload.phone.strip()
    customer.email = (payload.email or "").strip() or None
    customer.customer_type = payload.customer_type
    customer.gstin = (payload.gstin or "").strip().upper() or None
    customer.delivery_address = payload.delivery_address.strip()
    customer.billing_address = (payload.billing_address or "").strip() or customer.delivery_address
    customer.credit_limit = payload.credit_limit
    customer.credit_days = payload.credit_days
    customer.assigned_route_id = payload.assigned_route_id
    customer.assigned_driver_id = payload.assigned_driver_id
    customer.route_stop_sequence = payload.route_stop_sequence
    customer.is_active = payload.is_active
    customer.transport_allocation_method = payload.transport_allocation_method
    customer.negotiated_transport_rate_per_litre = payload.negotiated_transport_rate_per_litre


def _apply_milk_settings(db: Session, customer: Customer, payload: CustomerSchema, admin: User):
    if payload.rates is not None:
        # One rate per product; empty = standard rate
        for r in payload.rates:
            product = db.query(Product).filter(Product.id == r.product_id).first()
            has_own = db.query(CustomerPricing).filter(
                CustomerPricing.customer_id == customer.id, CustomerPricing.product_id == product.id
            ).first()
            if not has_own and (r.rate is None or round(r.rate, 2) == round(product.standard_b2b_price, 2)):
                continue  # keeps following the standard rate
            set_customer_price(db, customer, product, round(r.rate, 2) if r.rate is not None else None, admin.username)
        return
    # The rate in the customer form is for the customer's usual product (other products: Custom Pricing)
    milk = main_product(db, customer.id) if customer.id else _milk_product(db)
    if milk and payload.milk_rate is not None:
        has_own = db.query(CustomerPricing).filter(
            CustomerPricing.customer_id == customer.id, CustomerPricing.product_id == milk.id
        ).first()
        if not has_own and payload.milk_rate == milk.standard_b2b_price:
            return  # still on the standard price; keep following it
        set_customer_price(db, customer, milk, payload.milk_rate, admin.username)


@router.get("/")
def list_customers(db: Session = Depends(get_db)):
    customers = db.query(Customer).order_by(Customer.customer_code.asc()).all()
    routes = {r.id: r.route_name for r in db.query(DeliveryRoute).all()}
    drivers = {u.id: u.full_name for u in db.query(User).filter(User.role == "driver").all()}
    logins = {u.id: u for u in db.query(User).filter(User.role == "customer").all()}
    own_rates = {}
    for cp in db.query(CustomerPricing).all():
        own_rates.setdefault(cp.customer_id, {})[cp.product_id] = cp.custom_price
    result = []
    for c in customers:
        milk = main_product(db, c.id)
        rate = _milk_rate(db, c.id, milk)
        result.append({
            "id": c.id,
            "customer_code": c.customer_code,
            "business_name": c.business_name,
            "contact_person": c.contact_person,
            "phone": c.phone,
            "email": c.email,
            "customer_type": c.customer_type,
            "gstin": c.gstin,
            "billing_address": c.billing_address,
            "delivery_address": c.delivery_address,
            "assigned_route_id": c.assigned_route_id,
            "route_name": routes.get(c.assigned_route_id, "Unassigned"),
            "assigned_driver_id": c.assigned_driver_id,
            "driver_name": drivers.get(c.assigned_driver_id),
            "route_stop_sequence": c.route_stop_sequence,
            "credit_limit": c.credit_limit,
            "credit_days": c.credit_days,
            "current_outstanding": c.current_outstanding,
            "milk_rate": rate,
            # Own rate per product id (products not listed: standard rate)
            "own_rates": own_rates.get(c.id, {}),
            "rate_product": f"{milk.product_name} (/{milk.unit})" if milk else None,
            "transport_allocation_method": c.transport_allocation_method,
            "negotiated_transport_rate_per_litre": c.negotiated_transport_rate_per_litre,
            "is_active": c.is_active,
            "has_login": c.user_id in logins,
            "login_active": bool(c.user_id in logins and logins[c.user_id].is_active),
        })
    return result


@router.get("/{customer_id}/ledger")
def get_customer_ledger(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    ledger_entries = db.query(CustomerLedger).filter(
        CustomerLedger.customer_id == customer_id
    ).order_by(CustomerLedger.transaction_date.asc(), CustomerLedger.id.asc()).all()

    total_debits = sum(e.debit_amount for e in ledger_entries)
    total_credits = sum(e.credit_amount for e in ledger_entries)

    return {
        "customer": {
            "id": customer.id,
            "customer_code": customer.customer_code,
            "business_name": customer.business_name,
            "credit_limit": customer.credit_limit,
            "credit_days": customer.credit_days,
            "current_outstanding": customer.current_outstanding
        },
        "summary": {
            "total_sales_and_debits": total_debits,
            "total_payments_and_credits": total_credits,
            "closing_outstanding": customer.current_outstanding
        },
        "ledger": [
            {
                "id": entry.id,
                "date": entry.transaction_date.isoformat(),
                "type": entry.transaction_type,
                "ref_no": entry.reference_number,
                "narration": entry.narration,
                "debit": entry.debit_amount,
                "credit": entry.credit_amount,
                "balance": entry.running_balance
            } for entry in ledger_entries
        ]
    }


@router.post("/")
def create_customer(payload: CustomerSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _validate(db, payload)
    code = (payload.customer_code or "").strip().upper()
    if not code:
        n = db.query(Customer).count() + 1
        while db.query(Customer).filter(Customer.customer_code == f"CUST-{n:03d}").first():
            n += 1
        code = f"CUST-{n:03d}"
    if db.query(Customer).filter(Customer.customer_code == code).first():
        raise HTTPException(status_code=400, detail="Customer code already exists")

    branch = db.query(Branch).order_by(Branch.id).first()
    new_cust = Customer(customer_code=code, branch_id=branch.id if branch else None)
    _apply(new_cust, payload)
    db.add(new_cust)
    db.flush()
    _apply_milk_settings(db, new_cust, payload, admin)
    db.commit()
    db.refresh(new_cust)
    return {"status": "success", "customer_id": new_cust.id, "customer_code": new_cust.customer_code}


@router.put("/{customer_id}")
def update_customer(customer_id: int, payload: CustomerSchema, admin: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    _validate(db, payload)
    login = db.query(User).filter(User.id == customer.user_id).first() if customer.user_id else None
    if login and phone_taken(db, payload.phone, exclude_user_id=login.id):
        raise HTTPException(status_code=400, detail="Another login already uses this mobile number")
    _apply(customer, payload)
    _apply_milk_settings(db, customer, payload, admin)
    if login:
        # Customer logs in with this mobile number, so keep the login in step
        login.phone = customer.phone
        login.full_name = customer.business_name
    db.commit()
    return {"status": "success", "message": f"{customer.business_name} updated"}
