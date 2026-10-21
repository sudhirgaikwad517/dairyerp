"""Bell icon notifications. A customer sees only their own; the admin sees the dairy's (new claims, short deliveries...)."""
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.core.security import ADMIN_ROLES, get_current_customer, get_current_user
from backend.app.database import get_db
from backend.app.models.entities import User
from backend.app.services.notifications import list_notices, mark_read, unread_count

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _audience(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Tuple[str, Optional[int]]:
    if user.role in ADMIN_ROLES:
        return "admin", None
    if user.role == "customer":
        return "customer", get_current_customer(user, db).id
    raise HTTPException(status_code=403, detail="Notifications are for customers and the dairy admin")


@router.get("")
def my_notifications(who=Depends(_audience), db: Session = Depends(get_db)):
    audience, customer_id = who
    return {"unread": unread_count(db, audience, customer_id), "items": list_notices(db, audience, customer_id)}


@router.get("/unread-count")
def my_unread_count(who=Depends(_audience), db: Session = Depends(get_db)):
    audience, customer_id = who
    return {"unread": unread_count(db, audience, customer_id)}


@router.post("/read-all")
def read_all(who=Depends(_audience), db: Session = Depends(get_db)):
    audience, customer_id = who
    return {"marked": mark_read(db, audience, customer_id)}


@router.post("/{notice_id}/read")
def read_one(notice_id: int, who=Depends(_audience), db: Session = Depends(get_db)):
    audience, customer_id = who
    return {"marked": mark_read(db, audience, customer_id, notice_id)}
