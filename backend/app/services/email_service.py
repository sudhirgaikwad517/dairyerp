"""
Email through the dairy's own SMTP account (e.g. Hostinger: smtp.hostinger.com, port 465 SSL).

Every in-app notice can also go by email. notify_* only add a row to the email outbox inside the same
database transaction, so an email is never sent for a change that was rolled back. A background worker
sends the outbox every 20 seconds and retries a failed email up to 3 times. The SMTP password is stored
encrypted with the server's secret key and is never sent back to the browser.
"""
import base64
import hashlib
import html
import logging
import smtplib
import ssl
import threading
import time as clock
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from backend.app.models.entities import Customer, EmailOutbox, EmailSettings, Invoice

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=5)
SEND_EVERY_SECONDS = 20
BATCH = 25
SMTP_TIMEOUT = 25

# Which setting allows which notice kind
CATEGORY = {
    "bill_created": "send_bills", "bill_cancelled": "send_bills",
    "payment": "send_payments",
    "claim_approved": "send_claims", "claim_rejected": "send_claims", "claim_reopened": "send_claims",
    "order_confirmed": "send_orders", "order_placed": "send_orders", "order_changed": "send_orders",
    "order_cancelled": "send_orders",
    "delivered": "send_daily_delivery", "delivered_short": "send_daily_delivery", "not_delivered": "send_daily_delivery",
    "dispatch_held": "send_delays", "delivery_delayed": "send_delays",
    # "dispatched" (sent for delivery, every day) stays in the app only
}
LINK_PATH = {"orders": "/customer", "bills": "/customer", "claims": "/customer", "statement": "/customer",
             "delivery": "/#view-orders", "customers": "/#view-customers"}
_send_lock = threading.Lock()


# ---------------- settings ----------------

def _fernet() -> Fernet:
    from backend.app.core.security import SECRET_KEY
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("email:" + SECRET_KEY).encode()).digest()))


def encrypt_password(password: str) -> str:
    return _fernet().encrypt(password.encode()).decode()


def decrypt_password(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:  # secret key changed: the password must be entered again
        return None


def get_settings(db: Session) -> EmailSettings:
    s = db.query(EmailSettings).first()
    if not s:
        s = EmailSettings(enabled=False, smtp_port=465, smtp_security="ssl", send_bills=True, send_payments=True,
                          send_claims=True, send_orders=True, send_delays=True, send_daily_delivery=True,
                          send_admin_alerts=True)
        db.add(s)
        db.flush()
    return s


def ready(s: EmailSettings) -> bool:
    return bool(s.enabled and s.smtp_host and s.from_email and (s.smtp_username or s.smtp_security == "none"))


# ---------------- queueing (called from notifications) ----------------

def _settings_if_on(db: Session) -> Optional[EmailSettings]:
    s = db.query(EmailSettings).first()
    return s if s and ready(s) else None


def queue_customer(db: Session, customer_id: int, kind: str, title: str, body: str, link: Optional[str],
                   invoice_id: Optional[int] = None) -> None:
    s = _settings_if_on(db)
    flag = CATEGORY.get(kind)
    if not s or not flag or not getattr(s, flag):
        return
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    to = (customer.email or "").strip() if customer else ""
    if not to or "@" not in to or not customer.is_active:
        return
    db.add(EmailOutbox(to_email=to, customer_id=customer_id, kind=kind, subject=title, body=body, link=link,
                       invoice_id=invoice_id, status="pending"))


def queue_admin(db: Session, kind: str, title: str, body: str, link: Optional[str]) -> None:
    s = _settings_if_on(db)
    if not s or not s.send_admin_alerts or not (s.admin_email or "").strip():
        return
    db.add(EmailOutbox(to_email=s.admin_email.strip(), kind=kind, subject=f"[Dairy alert] {title}", body=body,
                       link=link, status="pending"))


# ---------------- building and sending ----------------

def _profile(db: Session):
    from backend.app.services.billing_service import get_business_profile
    return get_business_profile(db)


def build_message(db: Session, s: EmailSettings, to: str, subject: str, body: str, link: Optional[str],
                  invoice_id: Optional[int] = None) -> EmailMessage:
    p = _profile(db)
    dairy = p.business_name or "Dairy"
    site = (s.site_url or "").rstrip("/")
    url = site + LINK_PATH.get(link or "", "/customer") if site else ""
    contact = " · ".join(x for x in [p.contact_numbers, p.contact_email] if x)
    e = html.escape

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((s.from_name or dairy, s.from_email))
    msg["To"] = to
    if s.reply_to:
        msg["Reply-To"] = s.reply_to
    msg["Message-ID"] = make_msgid(domain=(s.from_email or "dairy.local").split("@")[-1])
    text = f"{subject}\n\n{body}\n"
    if url:
        text += f"\nOpen: {url}\n"
    text += f"\n--\n{dairy}\n{contact}\n"
    if site:
        text += f"Privacy Policy: {site}/privacy\n"
    msg.set_content(text)

    button = (f'<p style="margin:22px 0 4px"><a href="{e(url)}" style="background:#13406b;color:#fff;text-decoration:none;'
              f'padding:10px 18px;border-radius:8px;font-weight:600;display:inline-block">Open in the app</a></p>') if url else ""
    legal = (f' · <a href="{e(site)}/privacy" style="color:#64748b">Privacy Policy</a>'
             f' · <a href="{e(site)}/terms" style="color:#64748b">Terms</a>') if site else ""
    body_html = "<br>".join(e(line) for line in body.split("\n"))
    msg.add_alternative(f"""<!DOCTYPE html><html><body style="margin:0;background:#f1f5f9;font-family:Segoe UI,Roboto,Arial,sans-serif;color:#0f172a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border-radius:14px;overflow:hidden;border:1px solid #e2e8f0">
<tr><td style="background:#0b2545;color:#fff;padding:18px 22px;font-size:18px;font-weight:700">{e(dairy)}</td></tr>
<tr><td style="padding:22px">
<h2 style="margin:0 0 10px;font-size:18px;color:#0b2545">{e(subject)}</h2>
<p style="margin:0;font-size:15px;line-height:1.6">{body_html}</p>
{button}
</td></tr>
<tr><td style="padding:14px 22px;background:#f8fafc;color:#64748b;font-size:12px;line-height:1.6">
{e(dairy)}{(' · ' + e(contact)) if contact else ''}<br>
You get this email because you are a customer of {e(dairy)}.{legal}<br>
<a href="https://www.prowexa.com" style="color:#94a3b8">Design Developed By Prowexa Technologies Pvt. Ltd</a>
</td></tr></table></td></tr></table></body></html>""", subtype="html")

    if invoice_id:
        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if inv and inv.bill_type:
            from backend.app.services.bill_pdf import render_bills_pdf
            from backend.app.services.billing_service import bill_to_dict
            pdf = render_bills_pdf([bill_to_dict(inv)], p)
            msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=f"{inv.invoice_number}.pdf")
    return msg


def smtp_send(s: EmailSettings, msg: EmailMessage, password: Optional[str]) -> None:
    host, port = s.smtp_host.strip(), int(s.smtp_port or (465 if s.smtp_security == "ssl" else 587))
    context = ssl.create_default_context()
    if s.smtp_security == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
    try:
        server.ehlo()
        if s.smtp_security == "starttls":
            server.starttls(context=context)
            server.ehlo()
        if s.smtp_username:
            server.login(s.smtp_username.strip(), password or "")
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def friendly_error(err: Exception) -> str:
    if isinstance(err, smtplib.SMTPAuthenticationError):
        return "Login failed: check the SMTP username (full email address) and password"
    if isinstance(err, smtplib.SMTPRecipientsRefused):
        return "The receiver's email address was refused"
    if isinstance(err, smtplib.SMTPSenderRefused):
        return "The 'From' email was refused: it must be the same mailbox as the SMTP username (or allowed by it)"
    if isinstance(err, (TimeoutError, ConnectionRefusedError, OSError)) and not isinstance(err, smtplib.SMTPException):
        return f"Cannot connect to the SMTP server ({err}). Check host, port and security (465 = SSL, 587 = STARTTLS)"
    return str(err) or err.__class__.__name__


def send_test(db: Session, to: str) -> Dict:
    s = get_settings(db)
    if not (s.smtp_host and s.from_email):
        return {"ok": False, "error": "Fill the SMTP host and 'From' email first, then save"}
    try:
        p = _profile(db)
        msg = build_message(db, s, to, f"Test email from {p.business_name}",
                            "Email is set up correctly. Customers will now get their bills and updates by email.",
                            None)
        with _send_lock:
            smtp_send(s, msg, decrypt_password(s.smtp_password_enc))
        return {"ok": True}
    except Exception as err:  # report any SMTP / network problem to the admin
        return {"ok": False, "error": friendly_error(err)}


def process_outbox(db: Session, now: Optional[datetime] = None) -> Dict[str, int]:
    """Send waiting emails. Returns counts; safe to call often."""
    now = now or datetime.utcnow()
    s = db.query(EmailSettings).first()
    if not s or not ready(s):
        return {"sent": 0, "failed": 0}
    rows = db.query(EmailOutbox).filter(EmailOutbox.status == "pending").order_by(EmailOutbox.id).limit(BATCH).all()
    password = decrypt_password(s.smtp_password_enc)
    sent = failed = 0
    with _send_lock:
        for row in rows:
            if row.attempts and row.sent_at is None and row.created_at and \
                    now < (row.created_at + RETRY_AFTER * row.attempts):
                continue  # wait before retrying
            try:
                msg = build_message(db, s, row.to_email, row.subject, row.body, row.link, row.invoice_id)
                smtp_send(s, msg, password)
                row.status, row.sent_at, row.last_error = "sent", datetime.utcnow(), None
                sent += 1
            except Exception as err:  # keep the error for the admin's email log
                row.attempts = (row.attempts or 0) + 1
                row.last_error = friendly_error(err)[:500]
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = "failed"
                    failed += 1
            db.commit()
    return {"sent": sent, "failed": failed}


def start_email_worker(session_factory) -> threading.Thread:
    def loop():
        while True:
            try:
                with session_factory() as db:
                    process_outbox(db)
            except Exception:  # never let one bad round stop the worker
                logger.exception("Email worker round failed")
            clock.sleep(SEND_EVERY_SECONDS)

    t = threading.Thread(target=loop, name="email-worker", daemon=True)
    t.start()
    return t
