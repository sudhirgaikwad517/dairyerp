"""Serves uploaded photos only to people allowed to see them."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.api.driver_api import _driver_deliveries_query
from backend.app.core.security import ADMIN_ROLES, get_current_user
from backend.app.database import get_db
from backend.app.models.entities import Attachment, Customer, Delivery, DeliveryClaim, User
from backend.app.services.attachments import attachment_path

router = APIRouter(prefix="/files", tags=["Files"])


def _can_view(db: Session, user: User, att: Attachment) -> bool:
    if user.role in ADMIN_ROLES:
        return True
    if user.role == "customer":
        customer = db.query(Customer).filter(Customer.user_id == user.id).first()
        if not customer:
            return False
        if att.owner_type == "claim":
            return db.query(DeliveryClaim).filter(
                DeliveryClaim.id == att.owner_id, DeliveryClaim.customer_id == customer.id
            ).first() is not None
        if att.owner_type == "delivery":  # proof of their own delivery
            return db.query(Delivery).filter(
                Delivery.id == att.owner_id, Delivery.customer_id == customer.id
            ).first() is not None
    if user.role == "driver" and att.owner_type == "delivery":
        return att.uploaded_by == user.id or _driver_deliveries_query(db, user.id).filter(
            Delivery.id == att.owner_id
        ).first() is not None
    return False


@router.get("/{attachment_id}")
def get_file(attachment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att or not _can_view(db, user, att):
        raise HTTPException(status_code=404, detail="File not found")
    path = attachment_path(att)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type=att.content_type, headers={"Cache-Control": "private, max-age=3600"})
