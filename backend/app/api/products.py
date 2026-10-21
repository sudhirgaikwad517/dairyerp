"""Admin: the products the dairy sells (cow milk, buffalo milk, curd, paneer...). Prices include GST."""
import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.core.security import require_admin
from backend.app.database import get_db
from backend.app.models.entities import AuditLog, CustomerPricing, Order, OrderItem, Product, User
from backend.app.services.order_lines import UNITS, gst_split, whole_unit
from backend.app.services.order_pricing import OPEN_ORDER_STATUSES, reprice_open_orders

router = APIRouter(prefix="/products", tags=["Products"])
MAX_GST = 40.0


class ProductIn(BaseModel):
    product_name: str
    category: str = "Milk"
    unit: str = "L"
    pack_size: Optional[str] = None
    standard_b2b_price: float
    mrp: Optional[float] = None
    cost_price: Optional[float] = 0.0
    gst_rate: float = 0.0
    hsn_code: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    sort_order: int = 0
    min_order_quantity: Optional[float] = None


class ActiveIn(BaseModel):
    is_active: bool


def _used(db: Session, product_id: int) -> int:
    return db.query(func.count(OrderItem.id)).filter(OrderItem.product_id == product_id).scalar() or 0


def _open_orders(db: Session, product_id: int) -> int:
    return (db.query(func.count(func.distinct(Order.id))).join(OrderItem, OrderItem.order_id == Order.id)
            .filter(OrderItem.product_id == product_id, Order.status.in_(OPEN_ORDER_STATUSES),
                    Order.delivery_date >= date.today()).scalar() or 0)


def _out(db: Session, p: Product) -> dict:
    return {
        "id": p.id, "sku": p.sku, "product_name": p.product_name, "category": p.category, "unit": p.unit,
        "unit_whole": whole_unit(p.unit), "pack_size": p.pack_size, "description": p.description,
        "standard_b2b_price": p.standard_b2b_price, "mrp": p.mrp, "cost_price": p.cost_price,
        "gst_rate": p.gst_rate or 0.0, "hsn_code": p.hsn_code, "sort_order": p.sort_order or 0,
        "min_order_quantity": p.min_order_quantity, "is_active": bool(p.is_active),
        "times_ordered": _used(db, p.id), "open_orders": _open_orders(db, p.id),
        "custom_rates": db.query(func.count(CustomerPricing.id)).filter(CustomerPricing.product_id == p.id).scalar() or 0,
        "gst_in_price": gst_split(p.standard_b2b_price, p.gst_rate or 0.0)["gst"],
    }


def _clean(db: Session, payload: ProductIn, existing: Optional[Product] = None) -> dict:
    name = re.sub(r"\s+", " ", (payload.product_name or "").strip())
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Enter the product name")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Product name is too long")
    clash = db.query(Product).filter(func.lower(Product.product_name) == name.lower())
    if existing:
        clash = clash.filter(Product.id != existing.id)
    if clash.first():
        raise HTTPException(status_code=400, detail=f"A product named '{name}' already exists")
    if payload.unit not in UNITS:
        raise HTTPException(status_code=400, detail=f"Unit must be one of: {', '.join(UNITS)}")
    if existing and payload.unit != existing.unit and _used(db, existing.id):
        raise HTTPException(status_code=400, detail=(
            f"{existing.product_name} has been ordered before, so its unit ({existing.unit}) cannot change. "
            f"Add a new product with the new unit and switch this one off."))
    if payload.standard_b2b_price is None or payload.standard_b2b_price <= 0:
        raise HTTPException(status_code=400, detail="Rate must be more than 0")
    if payload.standard_b2b_price > 1_000_000:
        raise HTTPException(status_code=400, detail="Rate is too large")
    if payload.mrp is not None and payload.mrp < 0:
        raise HTTPException(status_code=400, detail="MRP cannot be negative")
    if payload.cost_price is not None and payload.cost_price < 0:
        raise HTTPException(status_code=400, detail="Cost price cannot be negative")
    if payload.gst_rate is None or not 0 <= payload.gst_rate <= MAX_GST:
        raise HTTPException(status_code=400, detail=f"GST must be between 0 and {MAX_GST:g}%")
    if payload.min_order_quantity is not None and payload.min_order_quantity < 0:
        raise HTTPException(status_code=400, detail="Minimum order cannot be negative")
    category = re.sub(r"\s+", " ", (payload.category or "").strip()) or "Milk"
    sku = (payload.sku or "").strip().upper() or None
    if sku:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,49}", sku):
            raise HTTPException(status_code=400, detail="Code may use letters, numbers, - and _ only")
        dup = db.query(Product).filter(Product.sku == sku)
        if existing:
            dup = dup.filter(Product.id != existing.id)
        if dup.first():
            raise HTTPException(status_code=400, detail=f"Code {sku} is already used by another product")
    hsn = (payload.hsn_code or "").strip() or None
    if hsn and not re.fullmatch(r"\d{4,8}", hsn):
        raise HTTPException(status_code=400, detail="HSN code must be 4 to 8 digits")
    return {
        "product_name": name, "category": category[:50], "unit": payload.unit,
        "pack_size": ((payload.pack_size or "").strip() or None), "description": ((payload.description or "").strip()[:200] or None),
        "standard_b2b_price": round(payload.standard_b2b_price, 2),
        "mrp": round(payload.mrp if payload.mrp is not None else payload.standard_b2b_price, 2),
        "cost_price": round(payload.cost_price or 0.0, 2), "gst_rate": round(payload.gst_rate, 2),
        "hsn_code": hsn, "sku": sku, "sort_order": payload.sort_order or 0,
        "min_order_quantity": payload.min_order_quantity if payload.min_order_quantity is not None else 0.0,
    }


@router.get("/")
def list_products(include_inactive: bool = False, category: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Product)
    if not include_inactive:
        q = q.filter(Product.is_active == True)
    if category:
        q = q.filter(Product.category.ilike(f"%{category}%"))
    return [_out(db, p) for p in q.order_by(Product.is_active.desc(), Product.sort_order, Product.id).all()]


@router.get("/units")
def units():
    return [{"unit": u, **info} for u, info in UNITS.items()]


@router.post("/")
def create_product(payload: ProductIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    data = _clean(db, payload)
    p = Product(**{**data, "sku": data["sku"] or f"TMP-{date.today():%Y%m%d%H%M%S}"}, current_stock=0.0, is_active=True)
    db.add(p)
    db.flush()
    if not data["sku"]:
        p.sku = f"P{p.id:03d}"
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="PRODUCT_ADD", entity_name="products",
                    entity_id=str(p.id), new_values=f"{p.product_name}: ₹{p.standard_b2b_price:g}/{p.unit}, GST {p.gst_rate:g}%"))
    db.commit()
    return _out(db, p)


@router.put("/{product_id}")
def update_product(product_id: int, payload: ProductIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    data = _clean(db, payload, p)
    if not data["sku"]:
        data["sku"] = p.sku
    before = {k: getattr(p, k) for k in data}
    changes = [f"{k}: {before[k]} -> {v}" for k, v in data.items() if before[k] != v]
    if not changes:
        return {**_out(db, p), "message": "Nothing changed"}
    for k, v in data.items():
        setattr(p, k, v)
    db.flush()
    notes = []
    # Orders not dispatched yet take the new rate / GST / cost; delivered ones keep theirs
    if before["standard_b2b_price"] != p.standard_b2b_price:
        n = reprice_open_orders(db, p)
        if n:
            notes.append(f"{n} upcoming order(s) of customers on the standard rate updated")
    open_items = db.query(OrderItem).join(Order, Order.id == OrderItem.order_id).filter(
        OrderItem.product_id == p.id, Order.status.in_(OPEN_ORDER_STATUSES), Order.delivery_date >= date.today()).all()
    if before["gst_rate"] != p.gst_rate or before["cost_price"] != p.cost_price:
        for i in open_items:
            i.gst_rate = p.gst_rate
            i.tax_amount = gst_split(i.total_amount or 0.0, p.gst_rate or 0.0)["gst"]
            i.product_cost_price = p.cost_price
        for o in {i.order_id for i in open_items}:
            order = db.query(Order).get(o)
            order.tax_amount = round(sum(x.tax_amount or 0.0 for x in db.query(OrderItem).filter(OrderItem.order_id == o).all()), 2)
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="PRODUCT_EDIT", entity_name="products",
                    entity_id=str(p.id), old_values=p.product_name, new_values="; ".join(changes)[:2000]))
    db.commit()
    return {**_out(db, p), "message": "Saved. " + ". ".join(notes) if notes else "Saved."}


@router.put("/{product_id}/active")
def set_active(product_id: int, payload: ActiveIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    if not payload.is_active and p.is_active:
        others = db.query(Product).filter(Product.is_active == True, Product.id != p.id).count()
        if not others:
            raise HTTPException(status_code=400, detail="At least one product must stay on sale")
    p.is_active = payload.is_active
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="PRODUCT_ON" if payload.is_active else "PRODUCT_OFF",
                    entity_name="products", entity_id=str(p.id), new_values=p.product_name))
    db.commit()
    open_n = _open_orders(db, p.id)
    msg = f"{p.product_name} is {'on sale again' if p.is_active else 'switched off: customers cannot order it'}."
    if not p.is_active and open_n:
        msg += f" {open_n} order(s) already placed with it will still be delivered and billed."
    return {**_out(db, p), "message": msg}
