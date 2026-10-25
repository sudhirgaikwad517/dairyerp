"""
One place for "what did the customer actually get" per product, used by bills, reports, claims,
transport cost and profitability, so every screen counts the same way.

Each order item records what the delivery boy handed over (OrderItem.delivered_quantity).
Older deliveries only recorded the total litres for the whole stop; for those the shortage is
spread over the items in proportion (that is how they were billed), see legacy_factor.
"""
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from backend.app.models.entities import Delivery, Order, OrderItem, Product

SOLD_STATUSES = ("delivered", "invoiced", "paid")
DONE_DELIVERY = ("delivered", "partially_delivered")

# Units a product can be sold in. Whole units cannot be ordered in fractions.
UNITS = {
    "L": {"label": "Litre", "whole": False},
    "pouch": {"label": "Pouch", "whole": True},
    "bottle": {"label": "Bottle", "whole": True},
    "kg": {"label": "Kg", "whole": False},
    "pcs": {"label": "Piece", "whole": True},
    "packet": {"label": "Packet", "whole": True},
    "box": {"label": "Box", "whole": True},
}


def litres_per_unit(product: Optional[Product]) -> float:
    """Litres of milk in one unit: the product's own figure (0.5 for a 500 ML pouch), 1 for litres, else 0."""
    if not product:
        return 0.0
    if product.litres_per_unit:
        return float(product.litres_per_unit)
    return 1.0 if (product.unit or "").strip().upper() == "L" else 0.0


def is_litre(product: Optional[Product]) -> bool:
    """Counts as milk in litre totals (sold per litre, or packs with litres per unit)."""
    return litres_per_unit(product) > 0


def whole_unit(unit: Optional[str]) -> bool:
    return UNITS.get(unit or "", {}).get("whole", False)


def qty_text(qty: float, unit: Optional[str]) -> str:
    q = round(qty or 0.0, 2)
    return f"{q:g} {'Liter' if unit == 'L' else (unit or '')}".strip()


def describe(pairs: Iterable) -> str:
    """[(qty, product)] -> '20 L Cow Milk, 2 kg Paneer'."""
    parts = [f"{qty_text(q, p.unit if p else '')} {p.product_name if p else 'Product'}" for q, p in pairs if q and q > 0]
    return ", ".join(parts) if parts else "nothing"


def order_what(db: Session, order: Order) -> str:
    """'20 L Cow Milk, 2 kg Paneer' for an order's items."""
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).order_by(OrderItem.id).all()
    return describe((i.ordered_quantity, db.query(Product).get(i.product_id)) for i in items)


def legacy_factor(order_items: List[OrderItem], delivery: Optional[Delivery], litre_ids: set) -> float:
    """Share of an old order that was delivered when only the stop's total litres were recorded."""
    if not delivery or delivery.status not in DONE_DELIVERY:
        return 1.0
    ordered = sum(i.ordered_quantity or 0.0 for i in order_items if i.product_id in litre_ids)
    if ordered <= 0:
        return 1.0
    return max(0.0, min(delivery.total_delivered_litres or 0.0, ordered)) / ordered


def item_delivered(item: OrderItem, order: Order, factor: float) -> float:
    """Quantity of this item that reached the customer (0 if the order is not delivered)."""
    if order.status not in SOLD_STATUSES:
        return 0.0
    ordered = item.ordered_quantity or 0.0
    if item.delivered_quantity is not None:
        return round(max(0.0, min(item.delivered_quantity, ordered)), 3)
    return round(ordered * factor, 3)


def order_lines(db: Session, orders: List[Order], products: Optional[Dict[int, Product]] = None) -> Dict[int, List[Dict]]:
    """
    order id -> one dict per item: product, ordered, delivered, rate, delivered amount and GST rate.
    Amount = delivered x rate (rates include GST).
    """
    if not orders:
        return {}
    products = products or {p.id: p for p in db.query(Product).all()}
    litre_ids = {pid for pid, p in products.items() if is_litre(p)}
    ids = [o.id for o in orders]
    items_by_order: Dict[int, List[OrderItem]] = {}
    for i in db.query(OrderItem).filter(OrderItem.order_id.in_(ids)).order_by(OrderItem.id).all():
        items_by_order.setdefault(i.order_id, []).append(i)
    deliveries = {d.order_id: d for d in db.query(Delivery).filter(Delivery.order_id.in_(ids)).all()}
    out: Dict[int, List[Dict]] = {}
    for o in orders:
        items = items_by_order.get(o.id, [])
        factor = legacy_factor(items, deliveries.get(o.id), litre_ids)
        rows = []
        for i in items:
            p = products.get(i.product_id)
            delivered = item_delivered(i, o, factor)
            rate = round(i.unit_price or 0.0, 2)
            lpu = litres_per_unit(p)
            rows.append({
                "item": i, "product": p, "product_id": i.product_id,
                "product_name": p.product_name if p else f"Product #{i.product_id}",
                "unit": p.unit if p else "",
                "is_litre": i.product_id in litre_ids,
                "litres_per_unit": lpu,
                "ordered": round(i.ordered_quantity or 0.0, 3),
                "delivered": delivered,
                # Litres of milk (pouches x litres per pouch); 0 for products that are not milk
                "ordered_litres": round((i.ordered_quantity or 0.0) * lpu, 3),
                "delivered_litres": round(delivered * lpu, 3),
                "rate": rate,
                "ordered_amount": round((i.ordered_quantity or 0.0) * rate, 2),
                "amount": round(delivered * rate, 2),
                "gst_rate": i.gst_rate or 0.0,
                "cost_price": i.product_cost_price or 0.0,
            })
        out[o.id] = rows
    return out


def gst_split(amount: float, gst_rate: float) -> Dict[str, float]:
    """Rates include GST: taxable value and the GST inside an amount."""
    if not gst_rate or gst_rate <= 0:
        return {"taxable": round(amount, 2), "gst": 0.0}
    taxable = round(amount * 100.0 / (100.0 + gst_rate), 2)
    return {"taxable": taxable, "gst": round(amount - taxable, 2)}


def backfill(db: Session) -> Dict[str, int]:
    """
    Bring older records up to the per-product format (safe to run at every start):
    - delivered items get their delivered quantity (from the stop's total litres, as they were billed)
    - claims get the product they were about (that day's milk)
    - saved bill lines get their product
    """
    import json
    from backend.app.models.entities import DeliveryClaim, Invoice
    products = {p.id: p for p in db.query(Product).all()}
    litre_ids = {pid for pid, p in products.items() if is_litre(p)}
    counts = {"items": 0, "claims": 0, "bills": 0}

    todo = (db.query(OrderItem).join(Order, Order.id == OrderItem.order_id)
            .filter(OrderItem.delivered_quantity.is_(None), Order.status.in_(SOLD_STATUSES)).all())
    by_order: Dict[int, List[OrderItem]] = {}
    for i in todo:
        by_order.setdefault(i.order_id, []).append(i)
    for order_id, items in by_order.items():
        order = db.query(Order).get(order_id)
        all_items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
        d = db.query(Delivery).filter(Delivery.order_id == order_id).first()
        factor = legacy_factor(all_items, d, litre_ids)
        for i in items:
            i.delivered_quantity = item_delivered(i, order, factor)
            counts["items"] += 1

    def main_product_on(customer_id, day) -> Optional[int]:
        o = db.query(Order).filter(Order.customer_id == customer_id, Order.delivery_date == day,
                                   Order.status.in_(SOLD_STATUSES)).first()
        if o:
            items = db.query(OrderItem).filter(OrderItem.order_id == o.id).order_by(OrderItem.id).all()
            pick = next((i for i in items if i.product_id in litre_ids), items[0] if items else None)
            if pick:
                return pick.product_id
        return min(litre_ids) if litre_ids else None

    for c in db.query(DeliveryClaim).filter(DeliveryClaim.product_id.is_(None)).all():
        c.product_id = main_product_on(c.customer_id, c.issue_date)
        counts["claims"] += 1

    for inv in db.query(Invoice).filter(Invoice.bill_lines.isnot(None)).all():
        lines = json.loads(inv.bill_lines)
        changed = False
        for l in lines:
            if l.get("product_id") is None:
                from datetime import date as _d
                pid = main_product_on(inv.customer_id, _d.fromisoformat(l["date"]))
                p = products.get(pid)
                l["product_id"] = pid
                l["product"] = p.product_name if p else "Milk"
                l["unit"] = p.unit if p else "L"
                l.setdefault("gst_rate", 0.0)
                changed = True
        if changed:
            inv.bill_lines = json.dumps(lines)
            counts["bills"] += 1
    db.commit()
    return counts
