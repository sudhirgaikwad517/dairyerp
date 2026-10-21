from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import date
from backend.app.database import get_db
from backend.app.models.entities import MilkProcurement, ProcurementVendor

router = APIRouter(prefix="/procurement", tags=["Milk Procurement"])

class ProcurementCreateSchema(BaseModel):
    vendor_id: int
    milk_type: str = "cow"
    quantity_litres: float
    fat_pct: float
    snf_pct: float
    clr_reading: float = 28.5
    temperature_c: float = 4.0
    shift: str = "Morning"

def calculate_milk_rate(fat_pct: float, snf_pct: float, milk_type: str) -> float:
    """
    Standard Indian Dairy Rate Chart formula:
    Cow milk base: ~₹7.5 per Fat unit + ~₹1.2 per SNF unit
    Buffalo milk base: higher fat premium
    """
    if milk_type.lower() == "buffalo":
        base_rate = (fat_pct * 7.8) + (snf_pct * 1.5)
    else:
        base_rate = (fat_pct * 7.4) + (snf_pct * 1.2)
    return round(max(32.0, min(base_rate, 75.0)), 2)

@router.get("/vendors")
def list_vendors(db: Session = Depends(get_db)):
    vendors = db.query(ProcurementVendor).filter(ProcurementVendor.is_active == True).order_by(ProcurementVendor.vendor_code).all()
    return [
        {"id": v.id, "vendor_code": v.vendor_code, "full_name": v.full_name, "village": v.village, "milk_type": v.milk_type}
        for v in vendors
    ]

@router.get("/collections")
def list_collections(collection_date: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(MilkProcurement).order_by(MilkProcurement.id.desc())
    if collection_date:
        query = query.filter(MilkProcurement.collection_date == date.fromisoformat(collection_date))
    records = query.all()
    result = []
    for r in records:
        v = r.vendor
        result.append({
            "id": r.id,
            "batch_no": r.procurement_batch_no,
            "collection_date": r.collection_date.isoformat() if r.collection_date else None,
            "vendor_name": v.full_name if v else "Farmer",
            "village": v.village if v else "",
            "milk_type": r.milk_type,
            "quantity_litres": r.quantity_litres,
            "fat_pct": r.fat_pct,
            "snf_pct": r.snf_pct,
            "clr_reading": r.clr_reading,
            "temperature_c": r.temperature_c,
            "rate_per_litre": r.rate_per_litre,
            "total_amount": r.total_amount,
            "quality_status": r.quality_status,
            "shift": r.collection_shift
        })
    return result

@router.post("/record")
def record_procurement(payload: ProcurementCreateSchema, db: Session = Depends(get_db)):
    vendor = db.query(ProcurementVendor).filter(ProcurementVendor.id == payload.vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Procurement vendor not found")
    if payload.quantity_litres <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be more than 0")
    if not (0 < payload.fat_pct <= 15) or not (0 < payload.snf_pct <= 15):
        raise HTTPException(status_code=400, detail="Fat % and SNF % must be between 0 and 15")
    if payload.milk_type not in ("cow", "buffalo", "mixed") or payload.shift not in ("Morning", "Evening"):
        raise HTTPException(status_code=400, detail="Choose a valid milk type and shift")

    rate = calculate_milk_rate(payload.fat_pct, payload.snf_pct, payload.milk_type)
    total_amt = round(payload.quantity_litres * rate, 2)

    # Simple quality acceptance rule: Normal fat >= 3.2% and SNF >= 8.0%
    quality = "accepted" if (payload.fat_pct >= 3.2 and payload.snf_pct >= 8.0) else "rejected"

    batch_no = f"PROC-{date.today().strftime('%Y%m%d')}-{db.query(MilkProcurement).count() + 1:03d}"
    proc = MilkProcurement(
        procurement_batch_no=batch_no,
        vendor_id=vendor.id,
        collection_date=date.today(),
        collection_shift=payload.shift,
        milk_type=payload.milk_type,
        quantity_litres=payload.quantity_litres,
        fat_pct=payload.fat_pct,
        snf_pct=payload.snf_pct,
        clr_reading=payload.clr_reading,
        temperature_c=payload.temperature_c,
        rate_per_litre=rate,
        total_amount=total_amt,
        quality_status=quality
    )
    db.add(proc)
    db.commit()
    db.refresh(proc)

    return {
        "status": "success",
        "batch_no": batch_no,
        "vendor": vendor.full_name,
        "quantity_litres": payload.quantity_litres,
        "rate_per_litre": rate,
        "total_amount": total_amt,
        "quality_status": quality
    }
