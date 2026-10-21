from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.reports import resolve_period
from backend.app.database import get_db
from backend.app.services.profitability_service import calculate_customer_profitability

router = APIRouter(prefix="/profitability", tags=["Customer Profitability"])


@router.get("/")
def get_profitability_report(
    period: str = "monthly",
    ref_date: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    customer_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Customer profitability for a period: Revenue (net sales, as in the Sales Register)
    - Milk cost (delivered litres x cost price) - Transport (route's fixed day cost shared by litres)
    = Contribution margin and margin %.
    """
    start, end, label = resolve_period(period, ref_date, start_date, end_date)
    report = calculate_customer_profitability(db, start, end, customer_id)
    report["period"] = {"type": period, "label": label, "start_date": start.isoformat(), "end_date": end.isoformat()}
    return report
