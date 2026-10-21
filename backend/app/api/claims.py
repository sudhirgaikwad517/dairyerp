from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.security import require_admin
from backend.app.database import get_db
from backend.app.models.entities import DeliveryClaim, User
from backend.app.services.claims_service import approve_claim, claim_dict, list_claims, reject_claim, reopen_claim

router = APIRouter(prefix="/claims", tags=["Customer Claims"])


class ApproveSchema(BaseModel):
    approved_qty: float
    note: Optional[str] = None
    mode: str = "bill"  # bill = deduct from bill | refund = pay back separately
    refund_method: Optional[str] = None  # cash | upi | bank_transfer (refund only)
    refund_reference: Optional[str] = None
    refund_date: Optional[date] = None  # day the refund was paid (default today)


class RejectSchema(BaseModel):
    note: str


def _get(db: Session, claim_id: int) -> DeliveryClaim:
    claim = db.query(DeliveryClaim).filter(DeliveryClaim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


@router.get("/")
def all_claims(status: Optional[str] = None, customer_id: Optional[int] = None, db: Session = Depends(get_db)):
    return [claim_dict(db, c) for c in list_claims(db, status, customer_id)]


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    return {"pending": db.query(DeliveryClaim).filter(DeliveryClaim.status == "pending").count()}


@router.get("/{claim_id}")
def claim_detail(claim_id: int, db: Session = Depends(get_db)):
    return claim_dict(db, _get(db, claim_id), with_details=True)


@router.post("/{claim_id}/approve")
def approve(claim_id: int, payload: ApproveSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    claim = approve_claim(db, _get(db, claim_id), payload.approved_qty, payload.note, admin,
                          mode=payload.mode, refund_method=payload.refund_method,
                          refund_reference=payload.refund_reference,
                          refund_date=payload.refund_date if payload.mode == "refund" else None)
    return {"status": "success", "claim": claim_dict(db, claim, with_details=True)}


@router.post("/{claim_id}/reject")
def reject(claim_id: int, payload: RejectSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    claim = reject_claim(db, _get(db, claim_id), payload.note, admin)
    return {"status": "success", "claim": claim_dict(db, claim, with_details=True)}


class UndoSchema(BaseModel):
    reason: str


@router.post("/{claim_id}/undo")
def undo(claim_id: int, payload: UndoSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Undo an approval or rejection; bills and ledger are put back and the claim is pending again."""
    claim = reopen_claim(db, _get(db, claim_id), payload.reason, admin)
    return {"status": "success", "claim": claim_dict(db, claim, with_details=True)}
