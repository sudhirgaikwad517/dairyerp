from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import date, timedelta
from backend.app.database import get_db
from backend.app.models.entities import ProductionBatch, Product

router = APIRouter(prefix="/production", tags=["Dairy Processing & Production"])

class ProductionCreateSchema(BaseModel):
    raw_milk_input_litres: float
    process_type: str # Pasteurization, Curd Processing, Paneer Processing
    output_product_id: int
    output_quantity: float
    output_unit: str = "L"
    wastage_litres: float = 0.0
    operator_name: str = "Shift Incharge"

@router.get("/batches")
def list_production_batches(production_date: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(ProductionBatch).order_by(ProductionBatch.id.desc())
    if production_date:
        query = query.filter(ProductionBatch.production_date == date.fromisoformat(production_date))
    batches = query.all()

    result = []
    for b in batches:
        p = b.product
        yield_pct = round((b.output_quantity / b.raw_milk_input_litres * 100.0), 1) if b.raw_milk_input_litres > 0 else 0.0
        result.append({
            "id": b.id,
            "batch_number": b.batch_number,
            "production_date": b.production_date.isoformat(),
            "raw_milk_input_litres": b.raw_milk_input_litres,
            "process_type": b.process_type,
            "output_product": p.product_name if p else "Product",
            "output_quantity": b.output_quantity,
            "output_unit": b.output_unit,
            "wastage_litres": b.wastage_litres,
            "yield_percentage": yield_pct,
            "expiry_date": b.expiry_date.isoformat(),
            "operator_name": b.operator_name,
            "status": b.status
        })
    return result

@router.post("/batch")
def create_production_batch(payload: ProductionCreateSchema, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == payload.output_product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Output product not found")
    if payload.raw_milk_input_litres <= 0 or payload.output_quantity <= 0 or payload.wastage_litres < 0:
        raise HTTPException(status_code=400, detail="Raw milk and output must be more than 0, wastage cannot be negative")
    if payload.output_unit.upper() == "L" and payload.output_quantity + payload.wastage_litres > payload.raw_milk_input_litres:
        raise HTTPException(status_code=400, detail="Output plus wastage cannot be more than the raw milk used")

    batch_no = f"PB-{date.today().strftime('%Y%m%d')}-{db.query(ProductionBatch).count() + 1:02d}"
    shelf_life_days = 2 if product.category.lower() == "milk" else (5 if product.category.lower() == "curd" else 4)

    pb = ProductionBatch(
        batch_number=batch_no,
        production_date=date.today(),
        raw_milk_input_litres=payload.raw_milk_input_litres,
        process_type=payload.process_type,
        output_product_id=product.id,
        output_quantity=payload.output_quantity,
        output_unit=payload.output_unit,
        wastage_litres=payload.wastage_litres,
        expiry_date=date.today() + timedelta(days=shelf_life_days),
        operator_name=payload.operator_name,
        status="completed"
    )
    db.add(pb)

    # Increase stock of finished product
    product.current_stock += payload.output_quantity

    db.commit()
    db.refresh(pb)
    return {
        "status": "success",
        "batch_number": batch_no,
        "output_product": product.product_name,
        "output_quantity": payload.output_quantity,
        "expiry_date": pb.expiry_date.isoformat()
    }
