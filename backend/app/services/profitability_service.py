from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.models.entities import Customer, Delivery, Order, OrderItem, Product
from backend.app.services.day_transport import customer_transport_share, transport_report
from backend.app.services.order_lines import order_lines

SOLD_STATUSES = ("delivered", "invoiced", "paid")


def calculate_customer_profitability(db: Session, start: date, end: date,
                                     customer_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Customer profitability for a period, built only from recorded figures:
      Revenue        = net sales, exactly as the Sales Register (delivered milk less approved claims)
      Milk cost      = litres delivered x the cost price saved on each order (Products: cost price)
      Transport cost = the day's total transport cost, shared by the litres each customer got that day
                       (same days as the Transport tab: finished days only)
      Margin         = Revenue - Milk cost - Transport cost
    Spoiled / short milk that was claimed still cost the dairy, so claims lower the margin.
    """
    # Late import: reports imports this module's siblings
    from backend.app.api.reports import build_sales_report

    sales = build_sales_report(db, start, end, "custom", "", customer_id=customer_id)
    revenue = {c["customer_id"]: c for c in sales["customers_report"]}

    # Milk cost of what was delivered (short deliveries reduce the litres)
    q = db.query(Order).filter(Order.delivery_date >= start, Order.delivery_date <= end,
                               Order.status.in_(SOLD_STATUSES))
    if customer_id:
        q = q.filter(Order.customer_id == customer_id)
    orders = q.all()
    products = {p.id: p for p in db.query(Product).all()}
    lines = order_lines(db, orders, products)

    cost: Dict[int, float] = {}
    litres: Dict[int, float] = {}
    no_cost_price = set()
    for o in orders:
        for r in lines.get(o.id, []):
            # Cost of what was handed over (same quantities as the bill), at the cost saved on the order
            price = r["cost_price"] or (r["product"].cost_price if r["product"] else 0.0) or 0.0
            if not price and r["delivered"] > 0:
                no_cost_price.add(r["product_name"])
            cost[o.customer_id] = cost.get(o.customer_id, 0.0) + r["delivered"] * price
            if r["is_litre"]:
                litres[o.customer_id] = litres.get(o.customer_id, 0.0) + r["delivered"]

    # Transport: each finished day's total cost shared by the litres each customer got that day
    transport = customer_transport_share(db, start, end, customer_id)
    treport = transport_report(db, start, end)
    days_in_progress = len(treport["days_in_progress"])
    days_without_cost = len(treport["days_without_cost"])

    customers = db.query(Customer)
    if customer_id:
        customers = customers.filter(Customer.id == customer_id)
    rows = []
    for c in customers.order_by(Customer.customer_code).all():
        sale = revenue.get(c.id)
        rev = sale["customer_total_amount"] if sale else 0.0
        sold = sale["customer_total_quantity"] if sale else 0.0
        if not sale and not cost.get(c.id):
            continue  # nothing delivered in this period
        mc = round(cost.get(c.id, 0.0), 2)
        tc = round(transport.get(c.id, 0.0), 2)
        margin = round(rev - mc - tc, 2)
        pct = round(margin / rev * 100.0, 2) if rev > 0 else 0.0
        delivered = round(litres.get(c.id, 0.0), 2)
        rows.append({
            "customer_id": c.id,
            "customer_code": c.customer_code,
            "business_name": c.business_name,
            "customer_type": c.customer_type,
            "delivered_litres": delivered,
            "sold_litres": sold,
            "claimed_litres": round(max(0.0, delivered - sold), 2),
            "revenue": round(rev, 2),
            "avg_rate": round(rev / sold, 2) if sold else 0.0,
            "product_cost": mc,
            "transport_cost": tc,
            "transport_per_litre": round(tc / delivered, 2) if delivered else 0.0,
            "net_contribution_margin": margin,
            "margin_per_litre": round(margin / sold, 2) if sold else 0.0,
            "margin_percentage": pct,
            "status": "Highly Profitable" if pct >= 15 else ("Profitable" if pct > 5 else "Review Pricing"),
        })

    tot = lambda k: round(sum(r[k] for r in rows), 2)  # noqa: E731
    total_rev, total_margin = tot("revenue"), tot("net_contribution_margin")
    milk = next((p for p in products.values() if p.unit == "L" and p.is_active), None)
    return {
        "summary": {
            "total_revenue": total_rev,
            "total_product_cost": tot("product_cost"),
            "total_transport_cost": tot("transport_cost"),
            "total_net_margin": total_margin,
            "overall_margin_percentage": round(total_margin / total_rev * 100.0, 2) if total_rev > 0 else 0.0,
            "delivered_litres": tot("delivered_litres"),
            "sold_litres": tot("sold_litres"),
        },
        "notes": {
            "days_in_progress": days_in_progress,
            "days_without_cost": days_without_cost,
            "products_without_cost_price": sorted(no_cost_price),
            "milk_product_id": milk.id if milk else None,
            "milk_cost_price": milk.cost_price if milk else None,
            "milk_product_name": milk.product_name if milk else None,
            "products": [{"id": p.id, "product_name": p.product_name, "unit": p.unit, "cost_price": p.cost_price}
                         for p in sorted(products.values(), key=lambda p: (p.sort_order or 0, p.id)) if p.is_active],
        },
        "customers": rows,
    }
