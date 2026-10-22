from datetime import date
from typing import Iterable, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.app.models.entities import AuditLog, Customer, CustomerPricing, Order, OrderItem, Product
from backend.app.services.order_lines import gst_split, litres_per_unit


def customer_unit_price(db: Session, customer_id: int, product: Product) -> float:
    """Negotiated customer price if one exists, otherwise the product's standard B2B price."""
    cp = db.query(CustomerPricing).filter(
        CustomerPricing.customer_id == customer_id,
        CustomerPricing.product_id == product.id
    ).first()
    return cp.custom_price if cp else product.standard_b2b_price


def fill_order_items(db: Session, order: Order, customer: Customer, items: Iterable[Tuple[int, float]]) -> None:
    """
    Adds priced items to an order and sets its totals.
    Used for every order (customer app and admin) so all are billed the same way:
    Amount = Qty x Rate. Rates include GST; tax_amount is only the GST inside the amount (for the bill's
    GST summary). A transport charge is added only when the customer has a negotiated ₹/L rate.
    """
    subtotal = tax_total = total_litres = 0.0

    for product_id, quantity in items:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product or quantity <= 0:
            continue

        unit_price = customer_unit_price(db, customer.id, product)
        item_total = round(quantity * unit_price, 2)
        item_tax = gst_split(item_total, product.gst_rate or 0.0)["gst"]

        db.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            ordered_quantity=quantity,
            unit_price=unit_price,
            gst_rate=product.gst_rate,
            tax_amount=item_tax,
            total_amount=item_total,
            product_cost_price=product.cost_price
        ))

        subtotal += item_total
        tax_total += item_tax
        total_litres += quantity * litres_per_unit(product)

    transport_charge = 0.0
    if customer.transport_allocation_method == "customer_specific" and customer.negotiated_transport_rate_per_litre > 0:
        transport_charge = round(total_litres * customer.negotiated_transport_rate_per_litre, 2)

    order.subtotal = round(subtotal, 2)
    order.tax_amount = round(tax_total, 2)
    order.transport_charge = transport_charge
    order.total_amount = round(subtotal + transport_charge, 2)  # GST is already inside the rates
    order.total_litres = round(total_litres, 3)


# Orders that are placed but not yet dispatched still take the latest rate.
OPEN_ORDER_STATUSES = ("created", "confirmed")


def reprice_open_orders(db: Session, product: Product, customer_id: Optional[int] = None) -> int:
    """
    Apply the current rate to orders from today onwards that are not dispatched yet.
    Delivered / out-for-delivery orders keep the rate they were sent at.
    customer_id None = every customer who pays the standard price for this product.
    Returns how many orders changed.
    """
    custom = {cp.customer_id: cp.custom_price for cp in
              db.query(CustomerPricing).filter(CustomerPricing.product_id == product.id).all()}
    q = (db.query(Order).join(OrderItem, OrderItem.order_id == Order.id)
         .filter(OrderItem.product_id == product.id,
                 Order.delivery_date >= date.today(),
                 Order.status.in_(OPEN_ORDER_STATUSES)))
    if customer_id is not None:
        q = q.filter(Order.customer_id == customer_id)
    changed = 0
    for order in q.distinct().all():
        if customer_id is None and order.customer_id in custom:
            continue  # has its own negotiated price
        price = custom.get(order.customer_id, product.standard_b2b_price)
        items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        touched = False
        for item in items:
            if item.product_id == product.id and item.unit_price != price:
                item.unit_price = price
                item.total_amount = round(item.ordered_quantity * price, 2)
                item.tax_amount = gst_split(item.total_amount, item.gst_rate or 0.0)["gst"]
                touched = True
        if touched:
            order.subtotal = round(sum(i.total_amount for i in items), 2)
            order.tax_amount = round(sum(i.tax_amount for i in items), 2)
            order.total_amount = round(order.subtotal + (order.transport_charge or 0.0), 2)
            changed += 1
    return changed


def set_customer_price(db: Session, customer: Customer, product: Product, price: Optional[float], username: str) -> int:
    """
    Set (or with price None, remove) a customer's negotiated rate for a product, log it, and
    apply it to their not-yet-dispatched orders. Returns how many open orders were repriced.
    """
    if price is not None and price <= 0:
        raise HTTPException(status_code=400, detail="Price must be more than 0")
    cp = db.query(CustomerPricing).filter(
        CustomerPricing.customer_id == customer.id, CustomerPricing.product_id == product.id
    ).first()
    old = cp.custom_price if cp else product.standard_b2b_price
    new = price if price is not None else product.standard_b2b_price
    if price is None:
        if cp:
            db.delete(cp)
    elif cp:
        if cp.custom_price != price:
            cp.custom_price = price
            cp.effective_from = date.today()
    else:
        db.add(CustomerPricing(customer_id=customer.id, product_id=product.id,
                               custom_price=price, effective_from=date.today()))
    db.flush()
    if old != new or (price is None and cp):
        db.add(AuditLog(
            username=username, action="PRICE_CHANGE", entity_name="customer_pricing",
            entity_id=f"{customer.id}-{product.id}", old_values=f"Price: ₹{old}",
            new_values=f"Price: ₹{new} for {customer.business_name} - {product.product_name}"
                       + (" (standard price)" if price is None else ""),
        ))
    return reprice_open_orders(db, product, customer.id)
