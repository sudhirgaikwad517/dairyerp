import re
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.entities import Invoice
from backend.app.services.bill_pdf import render_bills_pdf
from backend.app.services.billing_service import (
    bill_to_dict, delete_bill, generate_bills, get_business_profile, period_label,
    delivery_range, preview_bills, record_bill_payment, resolve_bill_period
)

router = APIRouter(tags=["Billing"])


class GenerateBillsSchema(BaseModel):
    bill_type: str  # daily | fortnightly | monthly | custom
    ref_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    customer_ids: Optional[List[int]] = None  # empty / null = all active customers


class BillPaymentSchema(BaseModel):
    amount: float
    payment_date: Optional[date] = None
    payment_method: str = "upi"
    reference_number: Optional[str] = None


class BusinessProfileSchema(BaseModel):
    business_name: str
    contact_numbers: Optional[str] = None
    contact_email: Optional[str] = None  # public contact for customers (privacy policy, terms)
    address: Optional[str] = None
    gstin: Optional[str] = None
    bank_account_name: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_branch: Optional[str] = None
    upi_number: Optional[str] = None
    # Customers' last time (HH:MM) to place / change / cancel: before noon = on the delivery day (01:00),
    # from noon = the evening before (21:00). See daily_orders.order_deadline.
    order_cutoff_time: Optional[str] = "21:00"
    dispatch_time: Optional[str] = "04:00"  # each day's orders go to the delivery boys at this time (HH:MM)
    auto_bill_day: Optional[int] = None  # day of the month (1-28) when last month's bills are made by themselves


def _period_response(bill_type: str, start: date, end: date):
    first, last = delivery_range(start, end)
    return {"bill_type": bill_type, "start_date": start.isoformat(), "end_date": end.isoformat(),
            "label": period_label(bill_type, start, end),
            # The period is in order days; its milk is delivered one day later
            "deliveries_from": first.isoformat(), "deliveries_to": last.isoformat(),
            "ready": last <= date.today()}


@router.get("/billing/preview")
def preview(
    bill_type: str = Query(default="monthly"),
    ref_date: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    customer_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """What a bill run would produce, without saving anything."""
    start, end = resolve_bill_period(bill_type, ref_date, start_date, end_date)
    rows = preview_bills(db, bill_type, start, end, [customer_id] if customer_id else None)
    return {"period": _period_response(bill_type, start, end), "customers": rows}


@router.post("/billing/generate")
def generate(payload: GenerateBillsSchema, db: Session = Depends(get_db)):
    start, end = resolve_bill_period(payload.bill_type, payload.ref_date, payload.start_date, payload.end_date)
    result = generate_bills(db, payload.bill_type, start, end, payload.customer_ids or None)
    return {"period": _period_response(payload.bill_type, start, end), **result}


def _bills_query(db: Session, start: Optional[date], end: Optional[date], customer_id: Optional[int], bill_type: Optional[str]):
    q = db.query(Invoice).filter(Invoice.bill_type.isnot(None))
    if start:
        q = q.filter(Invoice.period_end >= start)
    if end:
        q = q.filter(Invoice.period_start <= end)
    if customer_id:
        q = q.filter(Invoice.customer_id == customer_id)
    if bill_type:
        q = q.filter(Invoice.bill_type == bill_type)
    return q.order_by(Invoice.period_start.desc(), Invoice.invoice_number.asc())


@router.get("/billing/bills")
def list_bills(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    customer_id: Optional[int] = None,
    bill_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    bills = [bill_to_dict(b) for b in _bills_query(db, start_date, end_date, customer_id, bill_type).all()]
    for b in bills:
        b.pop("lines")
    return bills


@router.get("/billing/latest-bill-month")
def latest_bill_month(db: Session = Depends(get_db)):
    """Month (YYYY-MM) of the bill made last, so the Bills list opens where the newest bills are."""
    inv = db.query(Invoice).filter(Invoice.bill_type.isnot(None)).order_by(Invoice.id.desc()).first()
    return {"month": inv.period_start.strftime("%Y-%m") if inv and inv.period_start else None}


@router.get("/billing/bills/{bill_id}")
def get_bill(bill_id: int, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == bill_id, Invoice.bill_type.isnot(None)).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill_to_dict(inv)


def _pdf_response(bills, profile, filename: str) -> Response:
    pdf = render_bills_pdf(bills, profile)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/billing/bills/{bill_id}/pdf")
def bill_pdf(bill_id: int, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == bill_id, Invoice.bill_type.isnot(None)).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Bill not found")
    bill = bill_to_dict(inv)
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in bill["customer_name"]).strip("_")
    return _pdf_response([bill], get_business_profile(db), f"{bill['invoice_number']}_{safe_name}.pdf")


@router.get("/billing/pdf")
def bills_pdf(
    ids: Optional[str] = Query(default=None, description="Comma-separated bill ids; otherwise filters apply"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    customer_id: Optional[int] = None,
    bill_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """All matching bills in one PDF, one page per bill."""
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        invoices = db.query(Invoice).filter(Invoice.id.in_(id_list), Invoice.bill_type.isnot(None)).order_by(Invoice.invoice_number).all()
    else:
        invoices = _bills_query(db, start_date, end_date, customer_id, bill_type).all()
    if not invoices:
        raise HTTPException(status_code=404, detail="No bills found to download")
    bills = sorted((bill_to_dict(i) for i in invoices), key=lambda b: (b["period_start"], b["customer_code"]))
    return _pdf_response(bills, get_business_profile(db), f"Milk_Bills_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf")


@router.delete("/billing/bills/{bill_id}")
def remove_bill(bill_id: int, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == bill_id, Invoice.bill_type.isnot(None)).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Bill not found")
    number = inv.invoice_number
    delete_bill(db, inv)
    return {"status": "success", "message": f"Bill {number} deleted"}


@router.post("/billing/bills/{bill_id}/payment")
def add_bill_payment(bill_id: int, payload: BillPaymentSchema, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == bill_id, Invoice.bill_type.isnot(None)).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Bill not found")
    payment = record_bill_payment(db, inv, payload.amount, payload.payment_date or date.today(),
                                  payload.payment_method, payload.reference_number)
    return {"status": "success", "payment_number": payment.payment_number, "bill": bill_to_dict(inv)}


def _hhmm(value: str, error: str) -> str:
    try:
        hh, mm = value.strip().split(":")
        assert 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59 and len(mm) == 2
    except (ValueError, AssertionError):
        raise HTTPException(status_code=400, detail=error)
    return f"{int(hh):02d}:{mm}"


@router.get("/settings/business")
def get_profile(db: Session = Depends(get_db)):
    p = get_business_profile(db)
    return {k: getattr(p, k) for k in BusinessProfileSchema.model_fields}


@router.put("/settings/business")
def update_profile(payload: BusinessProfileSchema, db: Session = Depends(get_db)):
    if not payload.business_name.strip():
        raise HTTPException(status_code=400, detail="Business name is required")
    payload.order_cutoff_time = _hhmm(payload.order_cutoff_time or "21:00", "Order cut-off time must be like 21:00")
    payload.dispatch_time = _hhmm(payload.dispatch_time or "04:00", "Dispatch time must be like 04:00")
    if payload.order_cutoff_time < "12:00" and payload.order_cutoff_time >= payload.dispatch_time:
        raise HTTPException(status_code=400, detail=(
            f"The order cut-off ({payload.order_cutoff_time}) must be before the dispatch time "
            f"({payload.dispatch_time}), so orders are locked before they go to the delivery boys."))
    if payload.auto_bill_day is not None and not 1 <= payload.auto_bill_day <= 28:
        raise HTTPException(status_code=400, detail="Automatic monthly bill day must be from 1 to 28")
    email = (payload.contact_email or "").strip()
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="Enter a valid contact email, like info@yourdairy.com")
    payload.contact_email = email or None
    p = get_business_profile(db)
    if payload.auto_bill_day != p.auto_bill_day:
        # Turned on or moved: last month is still billed this month if it has not been yet
        p.auto_bill_done_for = None
    for k, v in payload.model_dump().items():
        setattr(p, k, v.strip() if isinstance(v, str) else v)
    p.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "success", "message": "Business details saved"}
