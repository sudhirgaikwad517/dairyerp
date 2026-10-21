from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from backend.app.database import get_db
from backend.app.models.entities import Invoice, Customer, Order
from backend.app.services.billing_service import bill_figures, bill_to_dict, get_business_profile

router = APIRouter(prefix="/invoices", tags=["Invoices & Billing"])

@router.get("/")
def list_invoices(customer_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Invoice).order_by(Invoice.id.desc())
    if customer_id:
        query = query.filter(Invoice.customer_id == customer_id)
    invoices = query.all()

    result = []
    for inv in invoices:
        c = inv.customer
        f = bill_figures(db, inv)  # live: later claim credits, advance and payments included
        result.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "customer_id": inv.customer_id,
            "customer_name": c.business_name if c else "Customer",
            "invoice_date": inv.invoice_date.isoformat(),
            "due_date": inv.due_date.isoformat(),
            "total_litres": inv.total_litres,
            "subtotal": inv.subtotal,
            "cgst_amount": inv.cgst_amount,
            "sgst_amount": inv.sgst_amount,
            "total_tax": inv.total_tax,
            "transport_charge": inv.transport_charge,
            "gross_amount": f["gross"],
            "claims_credit": f["credits"],
            "total_amount": f["net"],
            "advance_applied": f["advance"],
            "paid_amount": f["paid"],
            "balance_due": f["balance"],
            "payment_status": inv.payment_status
        })
    return result

@router.get("/{invoice_id}")
def get_invoice_details(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.bill_type:
        # Period bills (daily / 15 days / monthly): the same live figures as the Billing tab and PDF
        return bill_to_dict(inv)

    c = inv.customer
    order = inv.order
    profile = get_business_profile(db)
    items = []
    if order:
        for itm in order.items:
            items.append({
                "product_name": itm.product.product_name if itm.product else "Item",
                "quantity": itm.ordered_quantity,
                "unit": itm.product.unit if itm.product else "L",
                "unit_price": itm.unit_price,
                "gst_rate": itm.gst_rate,
                "tax_amount": itm.tax_amount,
                "total_amount": itm.total_amount
            })

    return {
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date.isoformat(),
        "due_date": inv.due_date.isoformat(),
        "dairy_info": {
            "name": profile.business_name,
            "address": profile.address or "",
            "gstin": profile.gstin or "",
            "phone": profile.contact_numbers or ""
        },
        "customer": {
            "business_name": c.business_name,
            "contact_person": c.contact_person,
            "gstin": c.gstin,
            "billing_address": c.billing_address,
            "delivery_address": c.delivery_address,
            "phone": c.phone
        },
        "items": items,
        "financials": {
            "total_litres": inv.total_litres,
            "subtotal": inv.subtotal,
            "cgst_amount": inv.cgst_amount,
            "sgst_amount": inv.sgst_amount,
            "transport_charge": inv.transport_charge,
            "total_amount": inv.total_amount,
            "paid_amount": inv.paid_amount,
            "balance_due": inv.balance_due,
            "payment_status": inv.payment_status
        }
    }
