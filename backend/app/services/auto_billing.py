"""Monthly bills made by themselves on the day of the month the admin chose in Dairy Settings."""
import logging
import threading
import time as clock
from datetime import date, datetime, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session

from backend.app.services import notifications
from backend.app.services.billing_service import generate_bills, get_business_profile, period_label, resolve_bill_period

logger = logging.getLogger(__name__)

CHECK_EVERY_SECONDS = 600
# The last orders of a month are delivered on the 1st morning; by noon those deliveries are done
RUN_FROM_HOUR = 12
LOCK = threading.Lock()


def run_auto_bills(db: Session, now: Optional[datetime] = None) -> Optional[Dict]:
    """Make last month's monthly bills once, on or after the chosen day. Returns the result when it ran."""
    now = now or datetime.now()
    profile = get_business_profile(db)
    day = profile.auto_bill_day
    if not day or now.day < day or now.hour < RUN_FROM_HOUR:
        return None
    last_month = (now.date().replace(day=1) - timedelta(days=1)).replace(day=1)
    key = last_month.strftime("%Y-%m")
    if profile.auto_bill_done_for == key:
        return None
    with LOCK:
        start, end = resolve_bill_period("monthly", last_month)
        result = generate_bills(db, "monthly", start, end)
        profile = get_business_profile(db)
        profile.auto_bill_done_for = key
        label = period_label("monthly", start, end)
        made = result["created"]
        # Customers with nothing delivered are not worth a line; the rest need the admin
        problems = [s for s in result["skipped"] if s["reason"] != "Nothing delivered in this period"
                    and not s["reason"].startswith("Already billed")]
        body = f"{len(made)} monthly bill(s) for {label} were made automatically"
        if made:
            body += f", total {notifications.money(sum(b['amount'] for b in made))}"
        body += "."
        if problems:
            body += f" Not made for {len(problems)}: " + "; ".join(
                f"{s['business_name']} ({s['reason']})" for s in problems[:10])
            if len(problems) > 10:
                body += f" and {len(problems) - 10} more"
            body += ". Make those from Milk Bills after fixing them."
        notifications.notify_admin(db, "auto_bills", f"Monthly bills made: {label}", body, "invoices")
        db.commit()
        return result


def start_auto_biller(session_factory) -> threading.Thread:
    """Background loop in the server process: checks every 10 minutes."""
    def loop():
        while True:
            try:
                with session_factory() as db:
                    run_auto_bills(db)
            except Exception:  # never let one bad check stop the loop
                logger.exception("Automatic monthly bills failed")
            clock.sleep(CHECK_EVERY_SECONDS)

    t = threading.Thread(target=loop, name="auto-bills", daemon=True)
    t.start()
    return t
