"""
Text of the public legal pages (Privacy Policy, Terms, Account deletion), editable by the admin.

Pages are written in a small, safe Markdown:
  ## Heading            ### Smaller heading
  - list item           (a block where every line starts with "- ")
  **bold**              [link text](https://... or /privacy or mailto:...)
  blank line = new paragraph; a single line break stays a line break
and {placeholders} that are filled from Dairy Settings, e.g. {dairy_name}, {cutoff_time}.
Everything the admin types is HTML-escaped, so a page can never run scripts.
"""
import html
import re
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from backend.app.models.entities import LegalPage, User

DEVELOPER = "Prowexa Technologies Private Limited"
DEVELOPER_SITE = "https://www.prowexa.com"
DEFAULT_UPDATED = datetime(2026, 10, 24)
DELETION_DAYS = 30
RECORD_YEARS = 8
MAX_LENGTH = 50_000

PAGES = {
    "privacy": "Privacy Policy",
    "terms": "Terms & Conditions",
    "delete_account": "Delete your account",
}

# What each {placeholder} means (shown in the editor)
PLACEHOLDERS = {
    "dairy_name": "Dairy name (Dairy Settings)",
    "dairy_address": "Dairy address",
    "dairy_phone": "Dairy phone numbers",
    "dairy_email": "Dairy contact email",
    "dairy_contact_block": "Box with name, address, phone and email (put it on its own line)",
    "cutoff_time": "Order cut-off time, e.g. 1:00 AM",
    "cutoff_rule": "When orders lock, e.g. 1:00 AM on the delivery day",
    "dispatch_time": "Automatic dispatch time, e.g. 4:00 AM",
    "claim_days": "Days a customer has to report a problem",
    "deletion_days": "Days to close an account after a request",
    "record_years": "Years bills are kept for tax law",
    "developer": "App developer / publisher",
    "developer_site": "Developer website",
}

DEFAULTS = {
"privacy": """This policy explains what information the **{dairy_name}** mobile app and web portal (the "App") collect, why, and how it is protected. The App is used by registered customers, delivery staff and the office staff of {dairy_name} (the "Dairy") to order milk, record deliveries and see bills. The App is developed and published on Google Play by **{developer}** ("Prowexa") on behalf of the Dairy.

## 1. Who is responsible

The Dairy decides what customer information is kept and is responsible for it. Prowexa builds and maintains the App and handles the information only to run the App for the Dairy. Contact for any privacy question:

{dairy_contact_block}

## 2. Information we collect

- **Account details** given to the Dairy when your account is created: business / customer name, contact person, mobile number, email address (if given), delivery address, GSTIN (if any), login username and password (stored only in encrypted, hashed form).
- **Orders and deliveries**: milk quantities ordered per day, delivered quantity, shortages and reasons, delivery time, the photo taken by the delivery person at delivery and the customer's signature.
- **Bills and payments**: bills, rates, amounts paid, payment method (cash / UPI / bank) and reference numbers entered by the Dairy. The App does **not** collect card, UPI PIN or bank login details and does not process payments.
- **Problems / claims** you report: date, quantity, description and the photos you attach.
- **Notifications** sent to you inside the App (deliveries, bills, payments, claims).
- **Technical data**: a login token stored securely on your phone so you stay logged in.

We do **not** collect your location, contacts, call logs, SMS, or any advertising ID. The App has no ads and no third-party analytics or tracking.

## 3. Phone permissions

- **Camera / photos**: used only when you choose to take or pick a photo for a problem report. Only the photos you select are uploaded.
- **Phone dialer**: the "Call Dairy" button opens your phone's dialer; the App does not make calls itself.
- **Internet**: to talk to the Dairy's server.

## 4. How the information is used

- To take and deliver your milk orders and to show you your orders, deliveries, bills and account statement.
- To check and settle problems you report (spoiled, short or missed milk).
- To send you notices about your orders, deliveries, bills, payments and claims.
- To keep the accounts and tax records the Dairy is required to keep by law.

## 5. Sharing

Your information is **not sold or rented** to anyone. It is seen only by the Dairy's staff who need it (office staff, and your delivery person for your name, address, phone and order). It is stored on secure servers rented by the Dairy / Prowexa from a hosting provider, who cannot use it for anything else. Information may be disclosed if required by law, a court or a government authority.

## 6. Security

Information travels between the App and the server over an encrypted (HTTPS) connection. Passwords are stored hashed, each user sees only what their role allows (a customer sees only their own account), and photos are shown only to the customer concerned and the Dairy.

## 7. How long it is kept

Account, order and delivery information is kept while you are a customer of the Dairy. Bills, payments and the account statement are kept for up to {record_years} years as required by Indian tax and accounting laws (GST and Income Tax), even after an account is closed. Other information is deleted or anonymised after that.

## 8. Your rights and deleting your account

Under India's Digital Personal Data Protection Act, 2023 you can ask to see, correct or erase your personal information, and withdraw consent. To delete your account, use **Menu → Delete my account** in the App or the [account deletion page](/delete-account). The Dairy closes the account within {deletion_days} days after any unpaid dues are settled; records that the law requires are kept as explained above.

## 9. Children

The App is meant for businesses and adults who buy milk from the Dairy. It is not meant for children under 18.

## 10. Changes

If this policy changes, the new version is posted on this page with a new "Last updated" date.

## 11. Grievance contact

For complaints about your information, contact the Dairy (details above). If the issue is with the App itself, you can also write to {developer} via [{developer_site}]({developer_site}).
""",

"terms": """These terms apply to the use of the **{dairy_name}** app and web portal (the "App") by customers of {dairy_name} (the "Dairy"). By logging in and using the App you agree to them. The App is developed by {developer} for the Dairy.

## 1. Accounts

- Accounts are created by the Dairy for its registered customers. There is no public sign-up.
- Keep your password secret. Orders placed from your login are treated as placed by you.
- Tell the Dairy if your mobile number or address changes, or if you think someone else used your login.

## 2. Ordering milk

- Order for a day before **{cutoff_rule}**. Till then you can change the quantities or cancel the order in the App.
- **After that time the order is locked** and you can only view it. Please call the Dairy for any change; the Dairy can change it only before it is sent for delivery.
- One order per day. Your bill shows each order on the day it was ordered for: milk delivered on the morning of the 24th is billed on the 23rd.
- Orders are sent to the delivery team automatically at **{dispatch_time}** on the delivery day. If the Dairy cannot send milk for a reason beyond its control, you will get a notice with the reason.

## 3. Delivery

- The delivery person records the quantity delivered, a photo and your signature. You are charged only for the milk actually delivered.
- Delivery times can be affected by vehicle problems, traffic or weather. You will get a notice in the App if delivery is delayed.

## 4. Problems with milk (claims)

- Report spoiled, short or missed milk from the App within **{claim_days} days** of delivery, with a clear description and photos (photos are not needed when milk was not delivered at all).
- The Dairy checks every claim. An approved claim is either reduced from your bill or paid back to you separately (cash / UPI / bank), never both. The Dairy's decision and note are shown in the App.

## 5. Prices, bills and payment

- Milk is charged at the rate agreed with the Dairy for your account. Rates may change with notice from the Dairy.
- Bills are made for the period agreed with the Dairy (daily, 15 days or monthly). Pay by the due date shown on the bill.
- Payments made to the Dairy or its delivery person are recorded in your account statement. Money paid in excess is kept as advance and used for your next bills.
- The Dairy may stop deliveries if dues remain unpaid beyond the agreed credit limit or period.

## 6. Fair use

Do not misuse the App: no false claims or photos, no attempts to access other customers' information, and no attempts to disturb the service. The Dairy may suspend an account that is misused.

## 7. Availability and liability

The App is provided to make ordering and billing easier. It may sometimes be unavailable for maintenance or because of internet problems; you can always place or confirm orders by calling the Dairy. The figures in the Dairy's books are final if there is any difference. Neither the Dairy nor {developer} is liable for indirect losses from using or not being able to use the App.

## 8. Closing your account

You may ask to close your account at any time from **Menu → Delete my account** or the [account deletion page](/delete-account). Unpaid dues must be settled first. See the [Privacy Policy](/privacy) for what is kept.

## 9. Law

These terms are governed by the laws of India. Disputes are subject to the courts having jurisdiction over the Dairy's place of business.

## 10. Contact

{dairy_contact_block}
""",

"delete_account": """Customers of **{dairy_name}** can ask for their App account to be deleted here, or from the App: **Menu → Delete my account**.

## What happens

- The Dairy confirms the request on your registered mobile number and settles any unpaid dues or advance with you.
- Your login is closed and your personal details (contact person, address, photos, signatures, claim photos) are deleted within {deletion_days} days.
- Bills, payments and the account statement are kept for up to {record_years} years because Indian tax laws require it; they are not used for anything else.
""",
}


def _clock(t) -> str:
    return datetime.combine(datetime.today(), t).strftime("%I:%M %p").lstrip("0")


def placeholder_values(db: Session) -> Dict[str, str]:
    from backend.app.services.billing_service import get_business_profile
    from backend.app.services.claims_service import CLAIM_WINDOW_DAYS
    from backend.app.services.daily_orders import cutoff_text, cutoff_time
    from backend.app.services.dispatch_control import dispatch_time
    p = get_business_profile(db)
    return {
        "dairy_name": p.business_name or "the dairy",
        "dairy_address": p.address or "",
        "dairy_phone": p.contact_numbers or "",
        "dairy_email": p.contact_email or "",
        "cutoff_time": _clock(cutoff_time(db)),
        "cutoff_rule": cutoff_text(cutoff_time(db)),
        "dispatch_time": _clock(dispatch_time(db)),
        "claim_days": str(CLAIM_WINDOW_DAYS),
        "deletion_days": str(DELETION_DAYS),
        "record_years": str(RECORD_YEARS),
        "developer": DEVELOPER,
        "developer_site": DEVELOPER_SITE,
    }


def contact_block_html(v: Dict[str, str]) -> str:
    e = html.escape
    rows = [f"<b>{e(v['dairy_name'])}</b>"]
    if v["dairy_address"]:
        rows.append(e(v["dairy_address"]))
    if v["dairy_phone"]:
        rows.append(f"Phone: {e(v['dairy_phone'])}")
    if v["dairy_email"]:
        rows.append(f'Email: <a href="mailto:{e(v["dairy_email"])}">{e(v["dairy_email"])}</a>')
    return '<div class="box">' + "<br>".join(rows) + "</div>"


_SAFE_LINK = re.compile(r"^(https?://|/|mailto:|tel:)", re.I)


def _fill(text: str, values: Dict[str, str]) -> str:
    """Replace {placeholders} in raw text; unknown ones stay as typed."""
    return re.sub(r"\{([a-z_]+)\}", lambda m: values.get(m.group(1), m.group(0)) if m.group(1) != "dairy_contact_block" else m.group(0), text)


def _inline(raw: str) -> str:
    out = html.escape(raw, quote=True)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2)).strip()
        if not _SAFE_LINK.match(url):
            return m.group(0)
        ext = url.lower().startswith("http")
        return f'<a href="{html.escape(url, quote=True)}"' + (' target="_blank" rel="noopener"' if ext else "") + f">{label}</a>"
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, out)


def render_markdown(text: str, values: Dict[str, str]) -> str:
    text = _fill((text or "").replace("\r\n", "\n"), values)
    blocks = re.split(r"\n\s*\n", text.strip())
    parts = []
    for block in blocks:
        lines = [ln.rstrip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        if len(lines) == 1 and lines[0].strip() == "{dairy_contact_block}":
            parts.append(contact_block_html(values))
        elif all(ln.lstrip().startswith("- ") for ln in lines):
            parts.append("<ul>" + "".join(f"<li>{_inline(ln.lstrip()[2:])}</li>" for ln in lines) + "</ul>")
        elif lines[0].startswith("### "):
            parts.append(f"<h3>{_inline(lines[0][4:])}</h3>")
            if lines[1:]:
                parts.append("<p>" + "<br>".join(_inline(ln) for ln in lines[1:]) + "</p>")
        elif lines[0].startswith("## "):
            parts.append(f"<h2>{_inline(lines[0][3:])}</h2>")
            if lines[1:]:
                parts.append("<p>" + "<br>".join(_inline(ln) for ln in lines[1:]) + "</p>")
        else:
            parts.append("<p>" + "<br>".join(
                contact_block_html(values) if ln.strip() == "{dairy_contact_block}" else _inline(ln) for ln in lines) + "</p>")
    return "\n".join(parts)


def get_page(db: Session, slug: str) -> Dict:
    row = db.query(LegalPage).filter(LegalPage.slug == slug).first()
    custom = bool(row and row.content)
    # A reset back to the default text is also a change, so it keeps its own date
    updated = row.updated_at if row and row.updated_at else DEFAULT_UPDATED
    by = None
    if custom and row.updated_by:
        u = db.query(User).filter(User.id == row.updated_by).first()
        by = u.full_name or u.username if u else None
    return {
        "slug": slug,
        "title": PAGES[slug],
        "content": row.content if custom else DEFAULTS[slug],
        "is_custom": custom,
        "updated_at": updated,
        "updated_by": by,
    }


def save_page(db: Session, slug: str, content: Optional[str], admin: User) -> None:
    """content None = back to the default text."""
    row = db.query(LegalPage).filter(LegalPage.slug == slug).first()
    if not row:
        row = LegalPage(slug=slug)
        db.add(row)
    row.content = content
    row.updated_at = datetime.now()
    row.updated_by = admin.id
