"""
Public pages the Play Store needs: Privacy Policy, Terms & Conditions and Account Deletion (no login),
plus the admin editor for their text. The dairy's name, address, phone and email come from Dairy Settings,
and the ordering rules (cut-off, dispatch time, claim window) from the live settings, through {placeholders}.
"""
import html
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.security import require_admin
from backend.app.database import get_db
from backend.app.models.entities import AccountDeletionRequest, AuditLog, User
from backend.app.services import notifications
from backend.app.services.legal_content import (DEFAULTS, DELETION_DAYS, DEVELOPER, DEVELOPER_SITE, MAX_LENGTH,
                                                PAGES, PLACEHOLDERS, contact_block_html, get_page,
                                                placeholder_values, render_markdown, save_page)

router = APIRouter(tags=["Legal pages"])
admin_router = APIRouter(prefix="/legal-pages", tags=["Legal pages (admin)"])


def _e(value) -> str:
    return html.escape(str(value or ""))


def _page(title: str, values: dict, updated: datetime, body: str) -> HTMLResponse:
    name = values["dairy_name"]
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)} | {_e(name)}</title>
<link rel="icon" type="image/svg+xml" href="/frontend/assets/logo.svg">
<style>
  :root {{ --ink: #0f172a; --muted: #64748b; --line: #e2e8f0; --brand: #0b2545; --link: #13406b; --bg: #f5f8fa; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--ink); background: var(--bg); line-height: 1.6; }}
  header {{ background: linear-gradient(135deg, #0b2545, #13406b 55%, #0e7fb5); color: #fff; padding: 22px 16px 26px; }}
  .wrap {{ max-width: 820px; margin: 0 auto; }}
  .brand {{ display: flex; align-items: center; gap: 12px; }}
  .brand img {{ width: 44px; height: 44px; border-radius: 12px; background: #fff; }}
  .brand b {{ font-size: 1.1rem; }}
  h1 {{ margin: 16px 0 2px; font-size: 1.6rem; }}
  header small {{ color: rgba(255,255,255,.8); }}
  main {{ background: #fff; border: 1px solid var(--line); border-radius: 16px; margin: -14px auto 24px; padding: 22px 20px; overflow-wrap: anywhere; }}
  h2 {{ font-size: 1.12rem; margin: 26px 0 6px; color: var(--brand); }}
  h3 {{ font-size: 1rem; margin: 18px 0 4px; }}
  main > :first-child {{ margin-top: 0; }}
  ul {{ padding-left: 20px; }}
  li {{ margin: 3px 0; }}
  a {{ color: var(--link); }}
  .box {{ background: #f8fafc; border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; margin: 8px 0; }}
  label {{ display: block; font-weight: 600; margin: 12px 0 4px; }}
  input, textarea {{ width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 10px; font: inherit; }}
  button {{ margin-top: 16px; background: #be123c; color: #fff; border: 0; border-radius: 10px; padding: 11px 18px; font: inherit; font-weight: 700; cursor: pointer; }}
  .ok {{ background: #ecfdf5; border-color: #a7f3d0; }}
  .err {{ background: #fff1f2; border-color: #fecdd3; }}
  footer {{ text-align: center; color: var(--muted); font-size: .8rem; padding: 0 16px 28px; }}
  footer a {{ color: var(--muted); }}
  nav a {{ margin: 0 6px; }}
  @media (max-width: 600px) {{ main {{ border-radius: 0; border-left: 0; border-right: 0; }} }}
</style>
</head>
<body>
<header><div class="wrap">
  <div class="brand"><img src="/frontend/assets/logo.svg" alt=""><b>{_e(name)}</b></div>
  <h1>{_e(title)}</h1>
  <small>Last updated: {updated.day} {updated:%B %Y}</small>
</div></header>
<main class="wrap">{body}</main>
<footer>
  <nav><a href="/privacy">Privacy Policy</a> · <a href="/terms">Terms &amp; Conditions</a> · <a href="/delete-account">Delete account</a></nav>
  <p>App published by {DEVELOPER} for {_e(name)}.<br>
  <a href="{DEVELOPER_SITE}" target="_blank" rel="noopener">Design Developed By {DEVELOPER}</a></p>
</footer>
</body>
</html>""")


def _render(db: Session, slug: str, content: Optional[str] = None, extra: str = "") -> HTMLResponse:
    page = get_page(db, slug)
    values = placeholder_values(db)
    body = render_markdown(page["content"] if content is None else content, values) + extra
    return _page(page["title"], values, page["updated_at"] if content is None else datetime.now(), body)


@router.get("/privacy", response_class=HTMLResponse)
def privacy_policy(db: Session = Depends(get_db)):
    return _render(db, "privacy")


@router.get("/terms", response_class=HTMLResponse)
def terms(db: Session = Depends(get_db)):
    return _render(db, "terms")


def _deletion_extra(values: dict, message: str = "", ok: bool = False, name: str = "", phone: str = "", reason: str = "") -> str:
    notice = f'<div class="box {"ok" if ok else "err"}">{message}</div>' if message else ""
    form = "" if ok else f"""
<form method="post" action="/delete-account">
  <label for="name">Your name / business name</label>
  <input id="name" name="name" required maxlength="150" value="{_e(name)}">
  <label for="phone">Registered mobile number</label>
  <input id="phone" name="phone" required maxlength="15" inputmode="tel" value="{_e(phone)}">
  <label for="reason">Reason (optional)</label>
  <textarea id="reason" name="reason" rows="3" maxlength="500">{_e(reason)}</textarea>
  <button type="submit">Request account deletion</button>
</form>"""
    return f"""
<h2>Send a request</h2>
{notice}
{form}
<h2>Need help?</h2>
{contact_block_html(values)}"""


@router.get("/delete-account", response_class=HTMLResponse)
def deletion_page(db: Session = Depends(get_db)):
    return _render(db, "delete_account", extra=_deletion_extra(placeholder_values(db)))


@router.post("/delete-account", response_class=HTMLResponse)
def deletion_request(name: str = Form(""), phone: str = Form(""), reason: str = Form(""), db: Session = Depends(get_db)):
    values = placeholder_values(db)
    name, reason = name.strip()[:150], reason.strip()[:500]
    digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
    if not name or len(digits) < 10:
        return _render(db, "delete_account", extra=_deletion_extra(
            values, "Enter your name and your 10-digit registered mobile number.", False, name, phone, reason))
    # One open request per number per day is enough
    recent = db.query(AccountDeletionRequest).filter(
        AccountDeletionRequest.phone == digits, AccountDeletionRequest.status == "open",
        AccountDeletionRequest.created_at >= datetime.utcnow() - timedelta(days=1),
    ).first()
    if not recent:
        db.add(AccountDeletionRequest(name=name, phone=digits, reason=reason or None, source="web"))
        notifications.deletion_requested(db, name, digits, "web", None)
        db.commit()
    return _render(db, "delete_account", extra=_deletion_extra(
        values, f"Request received. {_e(values['dairy_name'])} will contact you on {_e(digits)} and close the account "
                f"within {DELETION_DAYS} days.", True))


# ---------------- Admin editor ----------------

PUBLIC_PATH = {"privacy": "/privacy", "terms": "/terms", "delete_account": "/delete-account"}


class PageText(BaseModel):
    content: str


def _slug(slug: str) -> str:
    if slug not in PAGES:
        raise HTTPException(status_code=404, detail="Unknown page")
    return slug


def _page_dict(db: Session, slug: str) -> dict:
    p = get_page(db, slug)
    return {**p, "updated_at": p["updated_at"].isoformat(timespec="minutes"), "path": PUBLIC_PATH[slug],
            "default_content": DEFAULTS[slug]}


@admin_router.get("")
def list_pages(db: Session = Depends(get_db)):
    return {"pages": [_page_dict(db, s) for s in PAGES], "placeholders": PLACEHOLDERS,
            "values": placeholder_values(db)}


@admin_router.post("/{slug}/preview", response_class=HTMLResponse)
def preview(slug: str, payload: PageText, db: Session = Depends(get_db)):
    """How the page will look with this text (nothing is saved)."""
    slug = _slug(slug)
    extra = _deletion_extra(placeholder_values(db)) if slug == "delete_account" else ""
    return _render(db, slug, content=payload.content[:MAX_LENGTH], extra=extra)


@admin_router.put("/{slug}")
def save(slug: str, payload: PageText, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    slug = _slug(slug)
    text = (payload.content or "").replace("\r\n", "\n").strip()
    if len(text) < 50:
        raise HTTPException(status_code=400, detail="The page text is too short")
    if len(text) > MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"The page text is too long (max {MAX_LENGTH:,} characters)")
    before = get_page(db, slug)
    if text == before["content"].strip():
        raise HTTPException(status_code=400, detail="Nothing changed")
    save_page(db, slug, None if text == DEFAULTS[slug].strip() else text, admin)
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="LEGAL_PAGE_EDIT", entity_name="legal_pages",
                    entity_id=slug, old_values=before["content"], new_values=text))
    db.commit()
    return _page_dict(db, slug)


@admin_router.post("/{slug}/reset")
def reset(slug: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    slug = _slug(slug)
    before = get_page(db, slug)
    if not before["is_custom"]:
        raise HTTPException(status_code=400, detail="This page already uses the default text")
    save_page(db, slug, None, admin)
    db.add(AuditLog(user_id=admin.id, username=admin.username, action="LEGAL_PAGE_RESET", entity_name="legal_pages",
                    entity_id=slug, old_values=before["content"], new_values="default text"))
    db.commit()
    return _page_dict(db, slug)
