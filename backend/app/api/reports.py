import io
import csv
import calendar
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.entities import Customer, Delivery, DeliveryClaim, DeliveryRoute, Order, OrderItem, Product
from backend.app.services.order_lines import gst_split, is_litre, order_lines

# Orders whose milk reached the customer (same as billing)
SOLD_STATUSES = ("delivered", "invoiced", "paid")

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])

PERIOD_TYPES = ("daily", "weekly", "monthly", "custom")


def resolve_period(
    period: str,
    ref_date: Optional[date],
    start_date: Optional[date],
    end_date: Optional[date],
) -> Tuple[date, date, str]:
    """Returns (start, end, human label) for the requested reporting period."""
    ref = ref_date or date.today()

    if period == "daily":
        return ref, ref, ref.strftime("%d %b %Y (%A)")

    if period == "weekly":
        # Week runs Monday to Sunday
        start = ref - timedelta(days=ref.weekday())
        end = start + timedelta(days=6)
        return start, end, f"Week {start.strftime('%d %b')} - {end.strftime('%d %b %Y')}"

    if period == "monthly":
        start = ref.replace(day=1)
        end = ref.replace(day=calendar.monthrange(ref.year, ref.month)[1])
        return start, end, f"{calendar.month_name[ref.month]} {ref.year}"

    if period == "custom":
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="start_date and end_date are required for a custom period")
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="start_date must be on or before end_date")
        return start_date, end_date, f"{start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}"

    raise HTTPException(status_code=400, detail=f"period must be one of {', '.join(PERIOD_TYPES)}")


def build_sales_report(
    db: Session,
    start: date,
    end: date,
    period: str,
    label: str,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Excel-style sales register for a date range. Quantities are what was actually sold, same as the bills:
    delivered milk only (short / not delivered litres are not counted, undelivered orders are not sales yet),
    less approved claims (whether deducted in the bill or refunded separately).
    1. Customer-wise: which product, how much quantity, at what rate, and the amount (one row per rate).
    2. Subtotal per customer.
    3. Product-wise grand total across ALL customers (total quantity & total amount).
    4. Customer x Product pivot (quantity & amount) and a date-wise summary.
    """
    orders_query = db.query(Order).filter(
        Order.delivery_date >= start,
        Order.delivery_date <= end,
        Order.status != "cancelled"
    )
    if customer_id:
        orders_query = orders_query.filter(Order.customer_id == customer_id)

    orders = orders_query.all()
    order_map = {o.id: o for o in orders}

    customers = {c.id: c for c in db.query(Customer).all()}
    products = {p.id: p for p in db.query(Product).all()}
    routes = {r.id: r for r in db.query(DeliveryRoute).all()}

    def product_info(p_id: int) -> Dict[str, Any]:
        prod = products.get(p_id)
        return {
            "product_id": p_id,
            "product_name": prod.product_name if prod else f"Product #{p_id}",
            "sku": prod.sku if prod else "",
            "category": prod.category if prod else "General",
            "unit": prod.unit if prod else "Unit",
        }

    # customer_id -> (product_id, unit_price) -> aggregates
    cust_lines: Dict[int, Dict[Tuple[int, float], Dict[str, Any]]] = {}
    cust_orders: Dict[int, set] = {}
    # product_id -> aggregates across all customers
    prod_totals: Dict[int, Dict[str, Any]] = {}
    # date -> aggregates
    date_totals: Dict[date, Dict[str, Any]] = {}

    # How ordered milk turns into sales (same rules as the bills)
    def bucket():
        return {"quantity": 0.0, "amount": 0.0, "count": 0}
    recon = {k: bucket() for k in ("ordered", "pending_delivery", "short_delivered", "not_delivered",
                                    "delivered", "claims_deducted", "claims_refunded", "claims_pending")}

    def add(key, qty, amt, count=0):
        recon[key]["quantity"] += qty
        recon[key]["amount"] += amt
        recon[key]["count"] += count

    litre_ids = {pid for pid, pr in products.items() if is_litre(pr)}

    def book(c_id, p_id, rate, qty, amt, tax, day, order_id=None):
        """Add (or with negative qty/amount, take off) a sale in every view of the register.
        Per product the quantity is in its own unit; day and overall totals count litres of milk only."""
        line = cust_lines.setdefault(c_id, {}).setdefault(
            (p_id, rate), {"quantity": 0.0, "amount": 0.0, "tax": 0.0, "dates": set()}
        )
        line["quantity"] += qty
        line["amount"] += amt
        line["tax"] += tax
        pt = prod_totals.setdefault(p_id, {"quantity": 0.0, "amount": 0.0, "tax": 0.0, "customers": set()})
        pt["quantity"] += qty
        pt["amount"] += amt
        pt["tax"] += tax
        dt = date_totals.setdefault(day, {"quantity": 0.0, "amount": 0.0, "tax": 0.0, "orders": set()})
        dt["quantity"] += qty if p_id in litre_ids else 0.0
        dt["amount"] += amt
        dt["tax"] += tax
        if order_id is not None:
            line["dates"].add(day)
            pt["customers"].add(c_id)
            dt["orders"].add(order_id)
            cust_orders.setdefault(c_id, set()).add(order_id)

    # Same per-product rule as the bills: only what reached the customer is sold
    lines_by_order = order_lines(db, [o for o in orders if o.status != "cancelled"], products)
    lq = lambda r, q: q if r["is_litre"] else 0.0  # reconciliation quantities are litres of milk

    for ord_obj in orders:
        rows = [r for r in lines_by_order.get(ord_obj.id, []) if not product_id or r["product_id"] == product_id]
        if not rows:
            continue
        add("ordered", sum(lq(r, r["ordered"]) for r in rows), sum(r["ordered_amount"] for r in rows), 1)
        if ord_obj.status not in SOLD_STATUSES:
            # not delivered yet: not a sale yet
            add("pending_delivery", sum(lq(r, r["ordered"]) for r in rows), sum(r["ordered_amount"] for r in rows), 1)
            continue
        missing_qty = sum(lq(r, r["ordered"] - r["delivered"]) for r in rows)
        missing_amt = sum(r["ordered_amount"] - r["amount"] for r in rows)
        got_any = any(r["delivered"] > 0 for r in rows)
        if missing_amt > 0.004:
            add("short_delivered" if got_any else "not_delivered", missing_qty, missing_amt, 1)
        for r in rows:
            if r["delivered"] <= 0:
                continue
            # Amount is Qty x Rate; rates include GST, tax is the GST inside it
            tax = gst_split(r["amount"], r["gst_rate"])["gst"]
            book(ord_obj.customer_id, r["product_id"], r["rate"], r["delivered"], r["amount"], tax,
                 ord_obj.delivery_date, ord_obj.id)
            add("delivered", lq(r, r["delivered"]), r["amount"])

    # Approved claims come off the sale of their day (deducted in the bill, or refunded separately)
    claims_q = db.query(DeliveryClaim).filter(
        DeliveryClaim.issue_date >= start, DeliveryClaim.issue_date <= end,
        DeliveryClaim.status.in_(["approved", "pending"]),
    )
    if customer_id:
        claims_q = claims_q.filter(DeliveryClaim.customer_id == customer_id)
    for cl in claims_q.all():
        # The line the claim belongs to: that day's item of the claim's product
        day_orders = [o for o in orders if o.customer_id == cl.customer_id and o.delivery_date == cl.issue_date
                      and o.status in SOLD_STATUSES]
        row = next((r for o in day_orders for r in lines_by_order.get(o.id, []) if r["product_id"] == cl.product_id), None)
        if not row or (product_id and row["product_id"] != product_id):
            continue
        if cl.status == "pending":
            add("claims_pending", lq(row, float(cl.claimed_qty or 0)), 0.0, 1)
            continue
        qty, amt = float(cl.approved_qty or 0), float(cl.credit_amount or 0)
        book(cl.customer_id, row["product_id"], row["rate"], -qty, -amt, -gst_split(amt, row["gst_rate"])["gst"],
             cl.issue_date)
        add("claims_refunded" if cl.settlement == "refund" else "claims_deducted", lq(row, qty), amt, 1)

    report_order_ids = set().union(*cust_orders.values()) if cust_orders else set()
    overall_qty = sum(p["quantity"] for pid, p in prod_totals.items() if pid in litre_ids)
    overall_amt = sum(p["amount"] for p in prod_totals.values())
    overall_tax = sum(p["tax"] for p in prod_totals.values())

    # 1 & 2. Customer-wise detail with subtotals
    customers_report = []
    for c_id in cust_lines:
        cust = customers.get(c_id)
        route_name = "Direct / Unassigned"
        if cust and cust.assigned_route_id in routes:
            route_name = routes[cust.assigned_route_id].route_name

        lines = []
        for (p_id, rate), data in cust_lines[c_id].items():
            lines.append({
                **product_info(p_id),
                "quantity": round(data["quantity"], 2),
                "unit_price": rate,
                "total_amount": round(data["amount"], 2),
                "tax_amount": round(data["tax"], 2),
                "net_amount": round(data["amount"], 2),  # rates include GST
                "delivery_days": len(data["dates"]),
            })
        lines.sort(key=lambda x: (x["product_name"], x["unit_price"]))

        c_amt = sum(l["total_amount"] for l in lines)
        customers_report.append({
            "customer_id": c_id,
            "customer_code": cust.customer_code if cust else f"CUST-{c_id}",
            "business_name": cust.business_name if cust else "Unknown Customer",
            "contact_person": cust.contact_person if cust else "",
            "phone": cust.phone if cust else "",
            "customer_type": cust.customer_type if cust else "b2b",
            "route_name": route_name,
            "total_orders_count": len(cust_orders.get(c_id, ())),
            # Litres of milk; other products are in their own units in "products"
            "customer_total_quantity": round(sum(l["quantity"] for l in lines if l["product_id"] in litre_ids), 2),
            "customer_total_amount": round(c_amt, 2),
            "customer_total_tax": round(sum(l["tax_amount"] for l in lines), 2),
            "customer_net_amount": round(sum(l["net_amount"] for l in lines), 2),
            "share_pct": round(c_amt / overall_amt * 100.0, 1) if overall_amt > 0 else 0.0,
            "products": lines,
        })
    customers_report.sort(key=lambda x: x["business_name"].lower())

    # 3. Product-wise grand total across all customers
    grand_product_summary = []
    for p_id, data in prod_totals.items():
        grand_product_summary.append({
            **product_info(p_id),
            "total_quantity": round(data["quantity"], 2),
            "avg_unit_price": round(data["amount"] / data["quantity"], 2) if data["quantity"] > 0 else 0.0,
            "total_amount": round(data["amount"], 2),
            "total_tax": round(data["tax"], 2),
            "total_net_amount": round(data["amount"], 2),
            "customers_count": len(data["customers"]),
            "revenue_share_pct": round(data["amount"] / overall_amt * 100.0, 1) if overall_amt > 0 else 0.0,
        })
    grand_product_summary.sort(key=lambda x: x["total_amount"], reverse=True)

    # 3b. Product register: one sheet per product listing every customer's rate, quantity and total
    product_registers = []
    for g in grand_product_summary:
        rows = []
        for c in sorted(customers_report, key=lambda x: x["customer_code"]):
            for l in c["products"]:
                if l["product_id"] == g["product_id"]:
                    rows.append({
                        "customer_id": c["customer_id"],
                        "customer_code": c["customer_code"],
                        "business_name": c["business_name"],
                        "unit_price": l["unit_price"],
                        "quantity": l["quantity"],
                        "total_amount": l["total_amount"],
                    })
        for i, r in enumerate(rows, start=1):
            r["sr_no"] = i
        product_registers.append({
            **{k: g[k] for k in ("product_id", "product_name", "sku", "category", "unit")},
            "rows": rows,
            "total_quantity": g["total_quantity"],
            "total_amount": g["total_amount"],
        })

    # 4a. Customer x Product pivot (like an Excel pivot table)
    matrix_products = [
        {k: g[k] for k in ("product_id", "product_name", "unit")} for g in grand_product_summary
    ]
    matrix_rows = []
    for c in customers_report:
        cells: Dict[int, Dict[str, float]] = {}
        for l in c["products"]:
            cell = cells.setdefault(l["product_id"], {"quantity": 0.0, "amount": 0.0})
            cell["quantity"] += l["quantity"]
            cell["amount"] += l["total_amount"]
        matrix_rows.append({
            "customer_id": c["customer_id"],
            "customer_code": c["customer_code"],
            "business_name": c["business_name"],
            "cells": {
                str(p["product_id"]): {
                    "quantity": round(cells.get(p["product_id"], {}).get("quantity", 0.0), 2),
                    "amount": round(cells.get(p["product_id"], {}).get("amount", 0.0), 2),
                }
                for p in matrix_products
            },
            "total_quantity": c["customer_total_quantity"],
            "total_amount": c["customer_total_amount"],
        })

    # 4b. Date-wise summary (every day in range, including days with no sales)
    date_wise_summary = []
    day = start
    while day <= end:
        dt = date_totals.get(day)
        date_wise_summary.append({
            "date": day.isoformat(),
            "day_name": day.strftime("%a"),
            "orders_count": len(dt["orders"]) if dt else 0,
            "total_quantity": round(dt["quantity"], 2) if dt else 0.0,
            "total_amount": round(dt["amount"], 2) if dt else 0.0,
            "total_tax": round(dt["tax"], 2) if dt else 0.0,
            "total_net_amount": round(dt["amount"], 2) if dt else 0.0,
        })
        day += timedelta(days=1)

    reconciliation = {k: {"quantity": round(v["quantity"], 2), "amount": round(v["amount"], 2), "count": v["count"]}
                      for k, v in recon.items()}
    # What the bills charge = delivered - claims deducted; refunded claims were paid back separately
    reconciliation["billed"] = {
        "quantity": round(recon["delivered"]["quantity"] - recon["claims_deducted"]["quantity"], 2),
        "amount": round(recon["delivered"]["amount"] - recon["claims_deducted"]["amount"], 2),
    }
    reconciliation["net_sales"] = {"quantity": round(overall_qty, 2), "amount": round(overall_amt, 2)}

    return {
        "reconciliation": reconciliation,
        "period": {
            "type": period,
            "label": label,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": (end - start).days + 1,
            # Backward-compatible keys used by the old monthly endpoint
            "year": start.year,
            "month": start.month,
            "month_name": label,
        },
        "overall_summary": {
            "total_customers": len(customers_report),
            "total_products": len(grand_product_summary),
            "total_orders": len(report_order_ids),
            "total_quantity": round(overall_qty, 2),
            "total_amount": round(overall_amt, 2),
            "total_tax": round(overall_tax, 2),
            "total_net_amount": round(overall_amt, 2),  # rates include GST
            "average_order_value": round(overall_amt / len(report_order_ids), 2) if report_order_ids else 0.0,
        },
        "customers_report": customers_report,
        "grand_product_summary": grand_product_summary,
        "grand_total": {
            "total_quantity": round(overall_qty, 2),
            "total_amount": round(overall_amt, 2),
            "total_tax": round(overall_tax, 2),
            "total_net_amount": round(overall_amt, 2),  # rates include GST
        },
        "product_registers": product_registers,
        "customer_product_matrix": {
            "products": matrix_products,
            "rows": matrix_rows,
        },
        "date_wise_summary": date_wise_summary,
    }


def sales_report_to_csv(data: Dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    period = data["period"]

    writer.writerow([f"DAIRY ERP - {period['type'].upper()} SALES REGISTER"])
    writer.writerow([f"Period: {period['label']}", f"From: {period['start_date']}", f"To: {period['end_date']}"])
    writer.writerow([f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])

    # One register per product, like the manual Excel sheet
    for reg in data["product_registers"]:
        writer.writerow([f"PRODUCT: {reg['product_name']} ({reg['unit']})"])
        writer.writerow(["Sr. No", "Customer", "Rate (INR)", f"Quantity ({reg['unit']})", "Total (INR)"])
        for r in reg["rows"]:
            writer.writerow([r["sr_no"], r["business_name"], r["unit_price"], r["quantity"], r["total_amount"]])
        writer.writerow(["", "TOTAL", "", reg["total_quantity"], reg["total_amount"]])
        writer.writerow([])

    # Product-wise summary across all customers
    writer.writerow(["PRODUCT-WISE SUMMARY (ALL CUSTOMERS)"])
    writer.writerow(["Sr. No", "Product", "Unit", "Customers", "Total Quantity", "Avg Rate (INR)", "Total (INR)"])
    for i, g in enumerate(data["grand_product_summary"], start=1):
        writer.writerow([i, g["product_name"], g["unit"], g["customers_count"], g["total_quantity"],
                         g["avg_unit_price"], g["total_amount"]])
    writer.writerow(["", "GRAND TOTAL", "", data["overall_summary"]["total_customers"],
                     data["grand_total"]["total_quantity"], "", data["grand_total"]["total_amount"]])

    # UTF-8 BOM so Excel opens customer/product names correctly
    return "﻿" + output.getvalue()


@router.get("/sales")
def get_sales_report(
    period: str = Query(default="monthly", description="daily | weekly | monthly | custom"),
    ref_date: Optional[date] = Query(default=None, description="Any date inside the period (default: today)"),
    start_date: Optional[date] = Query(default=None, description="Start date (custom period only)"),
    end_date: Optional[date] = Query(default=None, description="End date (custom period only)"),
    customer_id: Optional[int] = Query(default=None, description="Optional Customer ID filter"),
    product_id: Optional[int] = Query(default=None, description="Optional Product ID filter"),
    db: Session = Depends(get_db)
):
    """Daily / weekly / monthly customer & product sales report."""
    start, end, label = resolve_period(period, ref_date, start_date, end_date)
    return build_sales_report(db, start, end, period, label, customer_id, product_id)


@router.get("/sales/export-csv")
def export_sales_report_csv(
    period: str = Query(default="monthly"),
    ref_date: Optional[date] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    customer_id: Optional[int] = Query(default=None),
    product_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Exports the sales report as a CSV that opens directly in Excel."""
    start, end, label = resolve_period(period, ref_date, start_date, end_date)
    data = build_sales_report(db, start, end, period, label, customer_id, product_id)

    if start == end:
        suffix = start.isoformat()
    else:
        suffix = f"{start.isoformat()}_to_{end.isoformat()}"
    filename = f"DairyERP_{period.capitalize()}_Sales_{suffix}.csv"
    return StreamingResponse(
        iter([sales_report_to_csv(data)]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ---- Backward-compatible monthly endpoints ----

def _month_ref(year: Optional[int], month: Optional[int]) -> date:
    today = date.today()
    return date(year or today.year, month or today.month, 1)


@router.get("/monthly-sales")
def get_monthly_customer_product_sales(
    year: Optional[int] = Query(default=None, description="Year (e.g. 2026)"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Month (1 to 12)"),
    customer_id: Optional[int] = Query(default=None, description="Optional Customer ID filter"),
    db: Session = Depends(get_db)
):
    return get_sales_report(period="monthly", ref_date=_month_ref(year, month), start_date=None,
                            end_date=None, customer_id=customer_id, product_id=None, db=db)


@router.get("/monthly-sales/export-csv")
def export_monthly_sales_csv(
    year: Optional[int] = Query(default=None),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    customer_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db)
):
    return export_sales_report_csv(period="monthly", ref_date=_month_ref(year, month), start_date=None,
                                   end_date=None, customer_id=customer_id, product_id=None, db=db)
