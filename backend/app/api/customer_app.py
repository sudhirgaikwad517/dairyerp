"""Endpoints for the logged-in customer (Flutter app and customer web portal). Always scoped to that customer."""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.security import get_current_customer, get_current_user
from backend.app.database import get_db
from backend.app.models.entities import (
    AccountDeletionRequest, Customer, CustomerComplaint, CustomerLedger, Invoice, Order, OrderItem, Product, User
)
from backend.app.services.bill_pdf import render_bills_pdf
from backend.app.services import notifications
from backend.app.services.attachments import save_photos
from backend.app.services.billing_service import (bill_to_dict, build_statement, get_business_profile, main_product,
                                                  outstanding_parts,
                                                  resolve_bill_period)
from backend.app.services.claims_service import (
    CLAIM_REASONS, CLAIM_WINDOW_DAYS, claim_dict, claimed_so_far, create_claim, day_delivery, day_products, list_claims
)
from backend.app.services.order_lines import litres_per_unit, whole_unit
from backend.app.services.daily_orders import customer_days, cutoff_same_day, cutoff_text, cutoff_time, set_day_quantity
from backend.app.services.order_pricing import customer_unit_price, fill_order_items

router = APIRouter(prefix="/me", tags=["Customer App"])

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
COMPLAINT_CATEGORIES = {"short_quantity", "leakage", "product_quality", "late_delivery", "billing_issue", "wrong_product", "other"}


class OrderItemIn(BaseModel):
    product_id: int
    quantity: float


class PlaceOrderSchema(BaseModel):
    delivery_date: Optional[date] = None
    items: List[OrderItemIn]
    notes: Optional[str] = None


class DayOrderSchema(BaseModel):
    items: List[OrderItemIn]


class DeletionSchema(BaseModel):
    reason: Optional[str] = None


class ComplaintSchema(BaseModel):
    category: str
    description: str
    subject: Optional[str] = None


def _order_dict(db: Session, o: Order) -> dict:
    items = []
    for i in db.query(OrderItem).filter(OrderItem.order_id == o.id).all():
        p = db.query(Product).filter(Product.id == i.product_id).first()
        items.append({"product_id": i.product_id, "product_name": p.product_name if p else "Product",
                      "unit": p.unit if p else "L", "quantity": i.ordered_quantity,
                      "unit_price": i.unit_price, "total_amount": i.total_amount,
                      # What reached the customer, once delivered
                      "delivered_quantity": i.delivered_quantity if o.status in ("delivered", "invoiced", "paid") else None})
    return {"id": o.id, "order_number": o.order_number, "delivery_date": o.delivery_date.isoformat(),
            "status": o.status, "total_litres": o.total_litres, "total_amount": o.total_amount,
            "payment_status": o.payment_status, "is_standing_order": o.is_standing_order, "items": items}


@router.get("/profile")
def profile(customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    milk = main_product(db, customer.id)
    dairy = get_business_profile(db)
    active = db.query(Product).filter(Product.is_active == True).order_by(Product.sort_order, Product.id).all()
    return {
        "id": customer.id,
        "customer_code": customer.customer_code,
        "business_name": customer.business_name,
        "contact_person": customer.contact_person,
        "phone": customer.phone,
        "email": customer.email,
        "customer_type": customer.customer_type,
        "delivery_address": customer.delivery_address,
        "credit_limit": customer.credit_limit,
        "credit_days": customer.credit_days,
        # Total owed now: bills not yet paid plus milk delivered but not billed yet
        **outstanding_parts(db, customer),
        # Rate of the customer's usual product, and their rate for every product on sale
        "milk_rate": customer_unit_price(db, customer.id, milk) if milk else None,
        "main_product": {"id": milk.id, "name": milk.product_name, "unit": milk.unit} if milk else None,
        "rates": [{"product_id": p.id, "product_name": p.product_name, "unit": p.unit,
                   "rate": customer_unit_price(db, customer.id, p)} for p in active],
        "dairy_name": dairy.business_name,
        "dairy_contact": dairy.contact_numbers,
        "dairy_email": dairy.contact_email,
        "upi_number": dairy.upi_number,
        # Where to pay: shown on the app's home screen
        "bank_account_name": dairy.bank_account_name,
        "bank_name": dairy.bank_name,
        "bank_account_number": dairy.bank_account_number,
        "bank_ifsc": dairy.bank_ifsc,
        "bank_branch": dairy.bank_branch,
        "order_cutoff_time": dairy.order_cutoff_time or "21:00",
        # 'Order or change by 1:00 AM on the delivery day' for the app's banner
        "order_cutoff_text": cutoff_text(cutoff_time(db)),
        "order_cutoff_same_day": cutoff_same_day(cutoff_time(db)),
    }


@router.get("/products")
def products(customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    result = []
    for p in db.query(Product).filter(Product.is_active == True).order_by(Product.sort_order, Product.id).all():
        price = customer_unit_price(db, customer.id, p)
        result.append({"id": p.id, "sku": p.sku, "product_name": p.product_name, "category": p.category,
                       # Sizes of one product (500 ML, 1 L) share group_name; shown together in the order form
                       "group_name": p.group_name or p.product_name, "variant_name": p.variant_name,
                       "litres_per_unit": litres_per_unit(p),
                       "unit": p.unit, "whole": whole_unit(p.unit), "pack_size": p.pack_size, "mrp": p.mrp,
                       "description": p.description, "gst_rate": p.gst_rate or 0.0,
                       "standard_b2b_price": p.standard_b2b_price, "custom_price": price,
                       "min_order_quantity": p.min_order_quantity})
    # Products in the dairy's order; the sizes of a product together, smallest first
    first_seen = {}
    for i, r in enumerate(result):
        first_seen.setdefault(r["group_name"].lower(), i)
    result.sort(key=lambda r: (first_seen[r["group_name"].lower()], r["litres_per_unit"] or 0, r["id"]))
    return result


@router.get("/orders")
def orders(limit: int = 30, customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    rows = db.query(Order).filter(Order.customer_id == customer.id).order_by(
        Order.delivery_date.desc(), Order.id.desc()
    ).limit(max(1, min(limit, 200))).all()
    return [_order_dict(db, o) for o in rows]


@router.post("/orders")
def place_order(payload: PlaceOrderSchema, customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    """Set the quantity for one day (one order per day: placing again changes that day's order)."""
    deliv = payload.delivery_date or date.today()
    items = [(i.product_id, i.quantity) for i in payload.items]
    if not any(q > 0 for _, q in items):
        raise HTTPException(status_code=400, detail="Add at least one product quantity")
    order = set_day_quantity(db, customer, deliv, items, placed_by="customer app")
    warning = None
    # Credit limit 0 means no limit has been set for this customer
    over = outstanding_parts(db, customer)["current_outstanding"] + order.total_amount > (customer.credit_limit or 0)
    if customer.credit_limit and customer.credit_limit > 0 and over:
        warning = "Your outstanding is above your credit limit. Please clear dues soon."
    return {"status": "success", "order": _order_dict(db, order), "credit_warning": warning}


@router.get("/days")
def my_days(start: Optional[date] = None, days: int = 7,
            customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    """Milk for each day: own order, skipped, or from the fixed schedule, and whether it can still be changed."""
    return customer_days(db, customer, start or date.today(), max(1, min(days, 31)))


@router.put("/days/{day}")
def set_my_day(day: date, payload: DayOrderSchema,
               customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    """Set how much milk is needed on a day. All quantities 0 = no milk that day."""
    set_day_quantity(db, customer, day, [(i.product_id, i.quantity) for i in payload.items], placed_by="customer app")
    return customer_days(db, customer, day, 1)[0]


@router.post("/account-deletion")
def request_account_deletion(payload: DeletionSchema, customer: Customer = Depends(get_current_customer),
                             db: Session = Depends(get_db)):
    """Customer asks the dairy to close the account (Play Store rule). The admin is told and closes it."""
    open_request = db.query(AccountDeletionRequest).filter(
        AccountDeletionRequest.customer_id == customer.id, AccountDeletionRequest.status == "open").first()
    if not open_request:
        db.add(AccountDeletionRequest(customer_id=customer.id, name=customer.business_name, phone=customer.phone,
                                      reason=(payload.reason or "").strip()[:500] or None, source="app"))
        notifications.deletion_requested(db, customer.business_name, customer.phone, "app", customer.id)
        db.commit()
    return {"status": "success", "already_requested": bool(open_request),
            "message": "Request sent. The dairy will contact you, settle any dues and close your account within 30 days."}


@router.get("/ledger")
def ledger(customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    entries = db.query(CustomerLedger).filter(CustomerLedger.customer_id == customer.id).order_by(
        CustomerLedger.transaction_date.asc(), CustomerLedger.id.asc()
    ).all()
    return {
        **outstanding_parts(db, customer),
        "credit_limit": customer.credit_limit,
        "ledger": [{"id": e.id, "date": e.transaction_date.isoformat(), "type": e.transaction_type,
                    "ref_no": e.reference_number, "narration": e.narration, "debit": e.debit_amount,
                    "credit": e.credit_amount, "balance": e.running_balance} for e in entries],
    }


@router.post("/complaints")
def complaint(payload: ComplaintSchema, customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    if payload.category not in COMPLAINT_CATEGORIES:
        raise HTTPException(status_code=400, detail="Choose a valid issue type")
    if not payload.description.strip():
        raise HTTPException(status_code=400, detail="Please describe the issue")
    ticket_no = f"TKT-{date.today().strftime('%Y%m%d')}-{db.query(CustomerComplaint).count() + 1:03d}"
    db.add(CustomerComplaint(
        ticket_number=ticket_no, customer_id=customer.id, category=payload.category,
        subject=(payload.subject or payload.category.replace("_", " ").title())[:150],
        description=payload.description.strip(), status="open"
    ))
    db.commit()
    return {"status": "success", "ticket_number": ticket_no}


@router.get("/bills")
def bills(customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    rows = db.query(Invoice).filter(Invoice.customer_id == customer.id, Invoice.bill_type.isnot(None)).order_by(
        Invoice.period_start.desc()
    ).all()
    result = [bill_to_dict(b) for b in rows]
    for b in result:
        b.pop("lines")
    return result


@router.get("/bills/{bill_id}/pdf")
def bill_pdf(bill_id: int, customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(
        Invoice.id == bill_id, Invoice.customer_id == customer.id, Invoice.bill_type.isnot(None)
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Bill not found")
    pdf = render_bills_pdf([bill_to_dict(inv)], get_business_profile(db))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{inv.invoice_number}.pdf"'})


# ---- Claims: spoiled / short / not delivered milk ----

@router.get("/claimable-days")
def claimable_days(customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    """Recent days with delivered milk that a problem can still be reported for."""
    today = date.today()
    result = []
    for n in range(CLAIM_WINDOW_DAYS + 1):
        day = today - timedelta(days=n)
        products = []
        for p in day_products(db, customer.id, day).values():
            if p["delivered"] <= 0:
                continue
            products.append({**p, "whole": whole_unit(p["unit"]),
                             "available_qty": round(p["delivered"] - claimed_so_far(db, customer.id, day,
                                                                                    product_id=p["product_id"]), 3)})
        if not products:
            continue
        first = products[0]
        # Top-level fields describe the first product (older app versions read only these)
        result.append({"date": day.isoformat(), "ordered_qty": first["ordered"], "delivered_qty": first["delivered"],
                       "rate": first["rate"], "unit": first["unit"], "available_qty": first["available_qty"],
                       "products": products})
    return {"reasons": CLAIM_REASONS, "days": result}


@router.get("/claims")
def my_claims(customer: Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    return [claim_dict(db, c) for c in list_claims(db, customer_id=customer.id)]


@router.post("/claims")
async def submit_claim(
    issue_date: date = Form(...),
    reason: str = Form(...),
    quantity: float = Form(...),
    description: str = Form(...),
    product_id: Optional[int] = Form(None),
    photos: List[UploadFile] = File(default=[]),
    customer: Customer = Depends(get_current_customer),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    real_photos = [p for p in (photos or []) if p and p.filename]
    if not real_photos and reason != "not_delivered":
        raise HTTPException(status_code=400, detail="Add at least one photo of the problem")
    claim = create_claim(db, customer, issue_date, reason, quantity, description, product_id)
    await save_photos(db, real_photos, "claim", claim.id, user.id)
    db.commit()
    return {"status": "success", "claim": claim_dict(db, claim)}


@router.get("/statement/pdf")
def statement_pdf(
    bill_type: str = "monthly",
    ref_date: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """Customer's own milk statement in the bill format, for a month, 15 days, one day or custom dates."""
    start, end = resolve_bill_period(bill_type, ref_date, start_date, end_date)
    data = build_statement(db, customer, bill_type, start, end)
    pdf = render_bills_pdf([data], get_business_profile(db))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Milk_Statement_{start:%Y%m%d}_{end:%Y%m%d}.pdf"'})
