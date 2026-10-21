from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.security import require_admin
from backend.app.database import get_db
from backend.app.models.entities import AuditLog, Customer, CustomerPricing, Order, OrderItem, Product, User
from backend.app.services.order_pricing import OPEN_ORDER_STATUSES, reprice_open_orders, set_customer_price

router = APIRouter(prefix="/pricing", tags=["Customer Pricing"])


class SetPricingSchema(BaseModel):
    customer_id: int
    product_id: int
    custom_price: Optional[float] = None  # None = go back to the standard price


class StandardPriceSchema(BaseModel):
    standard_b2b_price: float


def _row(customer: Customer, product: Product, cp: Optional[CustomerPricing]) -> dict:
    price = cp.custom_price if cp else product.standard_b2b_price
    return {
        "id": cp.id if cp else None,
        "customer_id": customer.id,
        "customer_code": customer.customer_code,
        "customer_name": customer.business_name,
        "customer_active": bool(customer.is_active),
        "product_id": product.id,
        "product_name": product.product_name,
        "unit": product.unit,
        "standard_b2b_price": product.standard_b2b_price,
        "custom_price": price,
        "is_custom": cp is not None,
        "discount_per_unit": round(product.standard_b2b_price - price, 2),
        "effective_from": cp.effective_from.isoformat() if cp and cp.effective_from else None,
    }


@router.get("/")
def get_all_custom_pricing(customer_id: Optional[int] = None, include_inactive: bool = False,
                           db: Session = Depends(get_db)):
    """Rate of every customer for every product: negotiated rate if set, otherwise the standard price."""
    customers = db.query(Customer).order_by(Customer.customer_code.asc())
    if customer_id:
        customers = customers.filter(Customer.id == customer_id)
    elif not include_inactive:
        customers = customers.filter(Customer.is_active == True)
    products = db.query(Product).filter(Product.is_active == True).order_by(Product.id).all()
    custom = {(cp.customer_id, cp.product_id): cp for cp in db.query(CustomerPricing).all()}
    return [_row(c, p, custom.get((c.id, p.id))) for c in customers.all() for p in products]


@router.get("/products")
def standard_prices(db: Session = Depends(get_db)):
    return [{"id": p.id, "product_name": p.product_name, "unit": p.unit, "standard_b2b_price": p.standard_b2b_price}
            for p in db.query(Product).filter(Product.is_active == True).order_by(Product.id).all()]


@router.post("/set")
def set_customer_pricing(payload: SetPricingSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Set a customer's negotiated rate (or reset it to standard). Applies to orders not yet dispatched."""
    cust = db.query(Customer).filter(Customer.id == payload.customer_id).first()
    prod = db.query(Product).filter(Product.id == payload.product_id).first()
    if not cust or not prod:
        raise HTTPException(status_code=404, detail="Customer or Product not found")
    repriced = set_customer_price(db, cust, prod, payload.custom_price, admin.username)
    db.commit()
    price = payload.custom_price if payload.custom_price is not None else prod.standard_b2b_price
    msg = (f"{cust.business_name}: {prod.product_name} is now ₹{price:g}/{prod.unit}"
           + (" (standard price)" if payload.custom_price is None else "") + ".")
    if repriced:
        msg += f" Updated {repriced} upcoming order(s) that are not dispatched yet."
    msg += " Delivered milk keeps the old rate."
    return {"status": "success", "message": msg, "orders_repriced": repriced}


class CostPriceSchema(BaseModel):
    cost_price: float


@router.put("/products/{product_id}/cost")
def set_cost_price(product_id: int, payload: CostPriceSchema, admin: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    """
    What one unit costs the dairy (used for profit only, never on bills). Orders from today that are
    not delivered yet take the new cost; delivered orders keep the cost of their day.
    """
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    if payload.cost_price <= 0:
        raise HTTPException(status_code=400, detail="Cost price must be more than 0")
    old = prod.cost_price
    prod.cost_price = payload.cost_price
    open_items = db.query(OrderItem).join(Order, Order.id == OrderItem.order_id).filter(
        OrderItem.product_id == prod.id, Order.delivery_date >= date.today(),
        Order.status.in_(OPEN_ORDER_STATUSES),
    ).all()
    for item in open_items:
        item.product_cost_price = payload.cost_price
    db.add(AuditLog(username=admin.username, action="COST_PRICE_CHANGE", entity_name="products",
                    entity_id=str(prod.id), old_values=f"Cost price: ₹{old}",
                    new_values=f"Cost price: ₹{payload.cost_price} for {prod.product_name}"))
    db.commit()
    return {"status": "success",
            "message": f"Cost price of {prod.product_name} is now ₹{payload.cost_price:g}/{prod.unit}.",
            "orders_updated": len(open_items)}


@router.put("/products/{product_id}")
def set_standard_price(product_id: int, payload: StandardPriceSchema, admin: User = Depends(require_admin),
                       db: Session = Depends(get_db)):
    """Change the standard B2B price. Customers with their own rate are not affected."""
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    if payload.standard_b2b_price <= 0:
        raise HTTPException(status_code=400, detail="Price must be more than 0")
    old = prod.standard_b2b_price
    prod.standard_b2b_price = payload.standard_b2b_price
    db.add(AuditLog(username=admin.username, action="PRICE_CHANGE", entity_name="products",
                    entity_id=str(prod.id), old_values=f"Standard price: ₹{old}",
                    new_values=f"Standard price: ₹{payload.standard_b2b_price} for {prod.product_name}"))
    db.flush()
    repriced = reprice_open_orders(db, prod)
    db.commit()
    msg = f"Standard price of {prod.product_name} is now ₹{payload.standard_b2b_price:g}/{prod.unit}."
    if repriced:
        msg += f" Updated {repriced} upcoming order(s) of customers on the standard price."
    return {"status": "success", "message": msg, "orders_repriced": repriced}
