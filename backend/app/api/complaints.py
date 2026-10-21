from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.app.database import get_db
from backend.app.models.entities import CustomerComplaint, Customer

router = APIRouter(prefix="/complaints", tags=["Complaints & Support"])

class ComplaintCreateSchema(BaseModel):
    customer_id: int
    category: str # product_quality, short_quantity, late_delivery, wrong_product, billing_issue, other
    subject: str
    description: str

@router.get("/")
def list_complaints(customer_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(CustomerComplaint).order_by(CustomerComplaint.id.desc())
    if customer_id:
        query = query.filter(CustomerComplaint.customer_id == customer_id)
    complaints = query.all()

    result = []
    for c in complaints:
        cust = c.customer
        result.append({
            "id": c.id,
            "ticket_number": c.ticket_number,
            "customer_name": cust.business_name if cust else "Customer",
            "category": c.category,
            "subject": c.subject,
            "description": c.description,
            "status": c.status,
            "resolution_notes": c.resolution_notes,
            "created_at": c.created_at.isoformat()
        })
    return result

@router.post("/")
def submit_complaint(payload: ComplaintCreateSchema, db: Session = Depends(get_db)):
    cust = db.query(Customer).filter(Customer.id == payload.customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    ticket_no = f"TKT-{datetime.utcnow().strftime('%Y%m%d')}-{db.query(CustomerComplaint).count() + 1:03d}"
    complaint = CustomerComplaint(
        ticket_number=ticket_no,
        customer_id=payload.customer_id,
        category=payload.category,
        subject=payload.subject,
        description=payload.description,
        status="open"
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)

    return {
        "status": "success",
        "ticket_number": ticket_no,
        "message": "Complaint registered successfully. Quality team notified."
    }
