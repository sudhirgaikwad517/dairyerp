"""
Admin: the products the dairy sells (cow milk, buffalo milk, curd, paneer...). Prices include GST.

A product can come in several pack sizes (variants), e.g. Cow Milk Brand Pouch in 500 ML and 1 L.
Each size is its own product row (own rate, code, customer rates, orders) sharing group_name;
its product_name is "<group> - <size>" so every bill and report shows the full name.
"""
import re
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.core.security import require_admin
from backend.app.database import get_db
from backend.app.models.entities import AuditLog, CustomerPricing, DeliveryClaim, Order, OrderItem, Product, User
from backend.app.services.order_lines import UNITS, gst_split, litres_per_unit, whole_unit
from backend.app.services.order_pricing import OPEN_ORDER_STATUSES, reprice_open_orders

router = APIRouter(prefix="/products", tags=["Products"])
MAX_GST = 40.0


class ProductIn(BaseModel):
    product_name: str  # with a size: the product's name without the size ("Cow Milk Brand Pouch")
    variant_name: Optional[str] = None  # pack size, e.g. "500 ML"
    litres_per_unit: Optional[float] = None  # litres of milk in one unit, e.g. 0.5
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


class VariantIn(BaseModel):
    id: Optional[int] = None  # existing size; None = new size
    variant_name: Optional[str] = None
    litres_per_unit: Optional[float] = None
    standard_b2b_price: float
    mrp: Optional[float] = None
    cost_price: Optional[float] = 0.0
    sku: Optional[str] = None
    min_order_quantity: Optional[float] = None


class GroupIn(BaseModel):
    """A product with all its sizes, saved together from the admin's product form."""
    product_name: str
    category: str = "Milk"
    unit: str = "L"
    gst_rate: float = 0.0
    hsn_code: Optional[str] = None
    description: Optional[str] = None
    sort_order: int = 0
    variants: List[VariantIn]


# Units a litre product may be switched to after it was ordered: the same quantities, now named as packs
PACK_UNITS = ("pouch", "bottle", "packet")


def full_name(name: str, variant: Optional[str]) -> str:
    return f"{name} - {variant}" if variant else name


def _used(db: Session, product_id: int) -> int:
    return db.query(func.count(OrderItem.id)).filter(OrderItem.product_id == product_id).scalar() or 0


def _open_orders(db: Session, product_id: int) -> int:
    return (db.query(func.count(func.distinct(Order.id))).join(OrderItem, OrderItem.order_id == Order.id)
            .filter(OrderItem.product_id == product_id, Order.status.in_(OPEN_ORDER_STATUSES),
                    Order.delivery_date >= date.today()).scalar() or 0)


def _out(db: Session, p: Product) -> dict:
    return {
        "id": p.id, "sku": p.sku, "product_name": p.product_name, "category": p.category, "unit": p.unit,
        # Sizes of one product share group_name; a product without sizes is its own group
        "group_name": p.group_name or p.product_name, "variant_name": p.variant_name,
        "litres_per_unit": p.litres_per_unit, "litres_in_unit": litres_per_unit(p),
        "unit_whole": whole_unit(p.unit), "pack_size": p.pack_size, "description": p.description,
        "standard_b2b_price": p.standard_b2b_price, "mrp": p.mrp, "cost_price": p.cost_price,
        "gst_rate": p.gst_rate or 0.0, "hsn_code": p.hsn_code, "sort_order": p.sort_order or 0,
        "min_order_quantity": p.min_order_quantity, "is_active": bool(p.is_active),
        "times_ordered": _used(db, p.id), "open_orders": _open_orders(db, p.id),
        "custom_rates": db.query(func.count(CustomerPricing.id)).filter(CustomerPricing.product_id == p.id).scalar() or 0,
        "gst_in_price": gst_split(p.standard_b2b_price, p.gst_rate or 0.0)["gst"],
    }


def _clean(db: Session, payload: ProductIn, existing: Optional[Product] = None) -> dict:
    group = re.sub(r"\s+", " ", (payload.product_name or "").strip())
    variant = re.sub(r"\s+", " ", (payload.variant_name or "").strip()) or None
    if len(group) < 2:
        raise HTTPException(status_code=400, detail="Enter the product name")
    if variant and len(variant) > 50:
        raise HTTPException(status_code=400, detail="Size is too long (50 letters at most)")
    name = full_name(group, variant)
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Product name is too long")
    clash = db.query(Product).filter(func.lower(Product.product_name) == name.lower())
    if existing:
        clash = clash.filter(Product.id != existing.id)
    if clash.first():
        raise HTTPException(status_code=400, detail=f"A product named '{name}' already exists")
    if payload.unit not in UNITS:
        raise HTTPException(status_code=400, detail=f"Unit must be one of: {', '.join(UNITS)}")
    lpu = payload.litres_per_unit
    if lpu is not None and lpu <= 0:
        lpu = None
    if lpu is not None and lpu > 1000:
        raise HTTPException(status_code=400, detail="Litres in one unit is too large")
    if existing and payload.unit != existing.unit and _used(db, existing.id):
        # A litre product that was really sold as packs may be renamed to packs: quantities stay the same
        to_packs = existing.unit == "L" and payload.unit in PACK_UNITS and lpu
        # Packs with their litres known may become litres: quantities and rates are converted
        to_litres = existing.unit in PACK_UNITS and payload.unit == "L" and existing.litres_per_unit
        if not (to_packs or to_litres):
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
        "product_name": name, "group_name": group if variant else None, "variant_name": variant,
        "litres_per_unit": round(lpu, 4) if lpu else None,
        "category": category[:50], "unit": payload.unit,
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


def _create(db: Session, payload: ProductIn, admin: User) -> Product:
    data = _clean(db, payload)
    p = Product(**{**data, "sku": data["sku"] or f"TMP-{date.today():%Y%m%d%H%M%S}-{id(payload)}"},
                current_stock=0.0, is_active=True)
    db.add(p)
    db.flush()
    if not data["sku"]:
        p.sku = f"P{p.id:03d}"
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="PRODUCT_ADD", entity_name="products",
                    entity_id=str(p.id), new_values=f"{p.product_name}: ₹{p.standard_b2b_price:g}/{p.unit}, GST {p.gst_rate:g}%"))
    db.flush()
    return p


def _refresh_litres(db: Session, p: Product) -> None:
    """Orders with this product get their litres again (after its unit / litres per unit changed)."""
    from backend.app.services.order_lines import litres_per_unit as lpu_of
    order_ids = {i.order_id for i in db.query(OrderItem).filter(OrderItem.product_id == p.id).all()}
    products = {}
    for order in db.query(Order).filter(Order.id.in_(order_ids)).all() if order_ids else []:
        items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        litres = 0.0
        for i in items:
            prod = products.get(i.product_id) or db.query(Product).get(i.product_id)
            products[i.product_id] = prod
            litres += (i.ordered_quantity or 0.0) * lpu_of(prod)
        order.total_litres = round(litres, 3)


def _packs_to_litres(db: Session, p: Product, per_pack: float) -> None:
    """A pack product now sold per litre: its orders, customer rates and claims in litres. Amounts stay the same."""
    for i in db.query(OrderItem).filter(OrderItem.product_id == p.id).all():
        i.ordered_quantity = round(i.ordered_quantity * per_pack, 3)
        if i.delivered_quantity is not None:
            i.delivered_quantity = round(i.delivered_quantity * per_pack, 3)
        i.unit_price = round(i.unit_price / per_pack, 4)
    for cp in db.query(CustomerPricing).filter(CustomerPricing.product_id == p.id).all():
        cp.custom_price = round(cp.custom_price / per_pack, 2)
    for c in db.query(DeliveryClaim).filter(DeliveryClaim.product_id == p.id).all():
        c.claimed_qty = round((c.claimed_qty or 0.0) * per_pack, 3)
        c.approved_qty = round((c.approved_qty or 0.0) * per_pack, 3)
        c.rate = round((c.rate or 0.0) / per_pack, 4)


def _update(db: Session, p: Product, payload: ProductIn, admin: User) -> List[str]:
    """Save changes to one product. Returns notes for the admin; [] with nothing changed."""
    data = _clean(db, payload, p)
    if not data["sku"]:
        data["sku"] = p.sku
    before = {k: getattr(p, k) for k in data}
    changes = [f"{k}: {before[k]} -> {v}" for k, v in data.items() if before[k] != v]
    if not changes:
        return []
    for k, v in data.items():
        setattr(p, k, v)
    db.flush()
    notes = ["Saved"]
    to_litres = before["unit"] in PACK_UNITS and p.unit == "L" and before["litres_per_unit"]
    if to_litres:
        _packs_to_litres(db, p, before["litres_per_unit"])
        notes.append(f"{p.product_name}: orders, customer rates and claims changed to litres")
    if before["unit"] != p.unit or before["litres_per_unit"] != p.litres_per_unit:
        _refresh_litres(db, p)
    # Orders not dispatched yet take the new rate / GST / cost; delivered ones keep theirs
    if before["standard_b2b_price"] != p.standard_b2b_price and not to_litres:
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
    db.flush()
    return notes


@router.post("/")
def create_product(payload: ProductIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = _create(db, payload, admin)
    db.commit()
    return _out(db, p)


@router.put("/group")
def save_group(payload: GroupIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Save a product with all its sizes in one go (all or nothing). Sizes with an id are changed,
    sizes without one are added. A size is never deleted here: switch it off instead.
    """
    if not payload.variants:
        raise HTTPException(status_code=400, detail="Add at least one size with its rate")
    named = [v for v in payload.variants if (v.variant_name or "").strip()]
    if len(payload.variants) > 1 and len(named) < len(payload.variants):
        raise HTTPException(status_code=400, detail="Give every size a name, e.g. 500 ML and 1 L")
    sizes = [re.sub(r"\s+", " ", (v.variant_name or "").strip()).lower() for v in named]
    if len(set(sizes)) < len(sizes):
        raise HTTPException(status_code=400, detail="The same size is listed twice")
    saved, notes = [], []
    for v in payload.variants:
        item = ProductIn(
            product_name=payload.product_name, variant_name=v.variant_name, litres_per_unit=v.litres_per_unit,
            category=payload.category, unit=payload.unit, gst_rate=payload.gst_rate, hsn_code=payload.hsn_code,
            description=payload.description, sort_order=payload.sort_order, standard_b2b_price=v.standard_b2b_price,
            mrp=v.mrp, cost_price=v.cost_price, sku=v.sku, min_order_quantity=v.min_order_quantity,
        )
        if v.id:
            p = db.query(Product).filter(Product.id == v.id).first()
            if not p:
                raise HTTPException(status_code=404, detail="One of the sizes was not found; reload the page")
            done = _update(db, p, item, admin)
            notes += [n for n in done if n != "Saved"]
            if done:
                saved.append(p.product_name)
        else:
            p = _create(db, item, admin)
            saved.append(p.product_name)
    db.commit()
    message = f"Saved {len(saved)} size(s)." if saved else "Nothing changed."
    if notes:
        message += " " + ". ".join(notes) + "."
    return {"status": "success", "message": message}


@router.put("/{product_id}")
def update_product(product_id: int, payload: ProductIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    notes = _update(db, p, payload, admin)
    if not notes:
        return {**_out(db, p), "message": "Nothing changed"}
    db.commit()
    extra = [n for n in notes if n != "Saved"]
    return {**_out(db, p), "message": "Saved. " + ". ".join(extra) if extra else "Saved."}


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
