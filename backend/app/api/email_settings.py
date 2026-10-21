"""Admin: the dairy's SMTP email settings, a test email, and the log of emails sent to customers."""
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.security import require_admin
from backend.app.database import get_db
from backend.app.models.entities import AuditLog, Customer, EmailOutbox, User
from backend.app.services import email_service

router = APIRouter(prefix="/email-settings", tags=["Email settings"])
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
FLAGS = ("send_bills", "send_payments", "send_claims", "send_orders", "send_delays", "send_daily_delivery",
         "send_admin_alerts")


class EmailSettingsIn(BaseModel):
    enabled: bool = False
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 465
    smtp_security: str = "ssl"
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None  # empty = keep the saved password
    clear_password: bool = False
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    site_url: Optional[str] = None
    admin_email: Optional[str] = None
    send_bills: bool = True
    send_payments: bool = True
    send_claims: bool = True
    send_orders: bool = True
    send_delays: bool = True
    send_daily_delivery: bool = True
    send_admin_alerts: bool = True


class TestIn(BaseModel):
    to: str


def _out(db: Session) -> dict:
    s = email_service.get_settings(db)
    with_email = db.query(Customer).filter(Customer.is_active == True, Customer.email.isnot(None), Customer.email != "").count()
    active = db.query(Customer).filter(Customer.is_active == True).count()
    return {
        "enabled": bool(s.enabled), "smtp_host": s.smtp_host, "smtp_port": s.smtp_port, "smtp_security": s.smtp_security,
        "smtp_username": s.smtp_username, "has_password": bool(s.smtp_password_enc),
        "password_unreadable": bool(s.smtp_password_enc) and email_service.decrypt_password(s.smtp_password_enc) is None,
        "from_email": s.from_email, "from_name": s.from_name, "reply_to": s.reply_to, "site_url": s.site_url,
        "admin_email": s.admin_email, **{f: bool(getattr(s, f)) for f in FLAGS},
        "ready": email_service.ready(s),
        "customers_with_email": with_email, "active_customers": active,
        "pending": db.query(EmailOutbox).filter(EmailOutbox.status == "pending").count(),
        "failed": db.query(EmailOutbox).filter(EmailOutbox.status == "failed").count(),
        "updated_at": s.updated_at.isoformat(timespec="minutes") if s.updated_at else None,
    }


def _clean_email(value: Optional[str], label: str) -> Optional[str]:
    value = (value or "").strip()
    if value and not EMAIL_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"{label} is not a valid email address")
    return value or None


@router.get("")
def get_email_settings(db: Session = Depends(get_db)):
    out = _out(db)
    db.commit()  # the settings row is created on first open
    return out


@router.put("")
def save_email_settings(payload: EmailSettingsIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = email_service.get_settings(db)
    if payload.smtp_security not in ("ssl", "starttls", "none"):
        raise HTTPException(status_code=400, detail="Security must be SSL, STARTTLS or None")
    host = (payload.smtp_host or "").strip() or None
    if host and not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        raise HTTPException(status_code=400, detail="SMTP host looks wrong, e.g. smtp.hostinger.com")
    port = payload.smtp_port or (465 if payload.smtp_security == "ssl" else 587)
    if not 1 <= port <= 65535:
        raise HTTPException(status_code=400, detail="SMTP port must be between 1 and 65535")
    site = (payload.site_url or "").strip().rstrip("/") or None
    if site and not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d+)?(/.*)?", site):
        raise HTTPException(status_code=400, detail="Portal address must start with https:// e.g. https://erp.yourdomain.com")
    from_email = _clean_email(payload.from_email, "'From' email")
    username = (payload.smtp_username or "").strip() or None
    if payload.enabled and not (host and from_email and (username or payload.smtp_security == "none")):
        raise HTTPException(status_code=400, detail="To turn email on, fill SMTP host, username and 'From' email")

    s.smtp_host, s.smtp_port, s.smtp_security, s.smtp_username = host, port, payload.smtp_security, username
    s.from_email = from_email
    s.from_name = (payload.from_name or "").strip() or None
    s.reply_to = _clean_email(payload.reply_to, "Reply-to email")
    s.admin_email = _clean_email(payload.admin_email, "Admin alert email")
    s.site_url = site
    if payload.clear_password:
        s.smtp_password_enc = None
    elif payload.smtp_password:
        s.smtp_password_enc = email_service.encrypt_password(payload.smtp_password)
    if payload.enabled and username and not s.smtp_password_enc:
        raise HTTPException(status_code=400, detail="Enter the SMTP password")
    s.enabled = payload.enabled
    for f in FLAGS:
        setattr(s, f, getattr(payload, f))
    s.updated_at = datetime.now()
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="EMAIL_SETTINGS", entity_name="email_settings",
                    entity_id="smtp", new_values=f"enabled={s.enabled} host={host} user={username} from={from_email}"
                                                 + (" password changed" if payload.smtp_password else "")))
    db.commit()
    return _out(db)


@router.post("/test")
def send_test_email(payload: TestIn, db: Session = Depends(get_db)):
    to = _clean_email(payload.to, "Test email")
    if not to:
        raise HTTPException(status_code=400, detail="Enter an email address to send the test to")
    result = email_service.send_test(db, to)
    db.commit()
    return result


@router.get("/log")
def email_log(limit: int = 50, status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(EmailOutbox).order_by(EmailOutbox.id.desc())
    if status:
        q = q.filter(EmailOutbox.status == status)
    names = {c.id: c.business_name for c in db.query(Customer).all()}
    return [{
        "id": r.id, "to": r.to_email, "customer": names.get(r.customer_id), "kind": r.kind, "subject": r.subject,
        "status": r.status, "attempts": r.attempts, "error": r.last_error, "has_pdf": bool(r.invoice_id),
        "created_at": r.created_at.isoformat(timespec="minutes") + "Z" if r.created_at else None,
        "sent_at": r.sent_at.isoformat(timespec="minutes") + "Z" if r.sent_at else None,
    } for r in q.limit(max(1, min(limit, 200))).all()]


@router.post("/retry-failed")
def retry_failed(db: Session = Depends(get_db)):
    n = db.query(EmailOutbox).filter(EmailOutbox.status == "failed").update(
        {EmailOutbox.status: "pending", EmailOutbox.attempts: 0, EmailOutbox.last_error: None}, synchronize_session=False)
    db.commit()
    return {"retrying": n}
