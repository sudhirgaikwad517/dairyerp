"""Renders milk bills as PDF in the dairy's bill format (one page per bill)."""
import calendar
import io
from datetime import date
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, SimpleDocTemplate, Table, TableStyle

BLUE = colors.HexColor("#BDD7EE")
GRID = colors.black

# DATE | QTY/LTR | RATE | DATE | QTY/LTR | RATE
COL_WIDTHS = [32 * mm, 30 * mm, 26 * mm, 32 * mm, 30 * mm, 26 * mm]


def fmt_num(value) -> str:
    """78083.0 -> '78083', 314987.5 -> '314987.5' (no currency symbol or commas, as on the bill)."""
    if value is None or value == "":
        return ""
    v = round(float(value), 2)
    return str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0").rstrip(".")


def _day_label(day_iso: str, single_month: bool) -> str:
    d = date.fromisoformat(day_iso)
    return str(d.day) if single_month else d.strftime("%d/%m")


UNIT_WORD = {"L": "LTR", "kg": "KG", "pcs": "PCS", "packet": "PKT", "box": "BOX"}


def _bill_table(bill: Dict, profile) -> Table:
    lines: List[Dict] = bill["lines"]
    start = date.fromisoformat(bill["period_start"])
    end = date.fromisoformat(bill["period_end"])
    single_month = start.year == end.year and start.month == end.month
    multi = bool(bill.get("multi_product"))
    products = bill.get("products") or []
    only = products[0] if len(products) == 1 else None
    unit = (only or {}).get("unit") or (lines[0].get("unit") if lines else "L") or "L"
    unit_word = UNIT_WORD.get(unit, unit.upper())

    if multi:
        # Several products: one row per day and product that had a delivery (or a claim)
        left = right = []
    elif single_month:
        # Always print the whole month like the paper bill (1-15 | 16-month end);
        # only the days inside the bill period are filled, the rest stay blank.
        by_date = {l["date"]: l for l in lines}
        last_day = calendar.monthrange(start.year, start.month)[1]
        month_days = [date(start.year, start.month, d).isoformat() for d in range(1, last_day + 1)]
        left = [(d, by_date.get(d)) for d in month_days[:15]]
        right = [(d, by_date.get(d)) for d in month_days[15:]]
    else:
        # Period crosses months: list the period's days in two halves with dd/mm dates
        n = len(lines)
        left_count = 1 if n == 1 else (n + 1) // 2
        left = [(l["date"], l) for l in lines[:left_count]]
        right = [(l["date"], l) for l in lines[left_count:]]
    day_rows = max(len(left), len(right))

    def cells(entry):
        if not entry:
            return ["", "", ""]
        day_iso, line = entry
        label = _day_label(day_iso, single_month)
        if line is None:
            return [label, "", ""]  # outside the bill period
        qty = fmt_num(line["qty"]) if line["qty"] > 0 else "-"
        if line.get("claim_qty"):
            qty += " *"  # quantity after an approved claim; details in "Claim Adjustments"
        return [label, qty, fmt_num(line["rate"])]

    period_title = "Month" if bill["bill_type"] == "monthly" else ("Date" if start == end else "Period")
    statement = bill.get("is_statement", False)
    adjustments: List[Dict] = bill.get("adjustments", [])
    claims_qty = bill.get("claims_qty", round(sum(l.get("claim_qty", 0) for l in lines), 2))
    claims_amount = bill.get("claims_amount", 0.0)
    milk_word = "MILK" if unit == "L" else ((only or {}).get("product") or "QTY").upper()
    total_milk_label = f"TOTAL {milk_word}" + (f" (AFTER {fmt_num(claims_qty)} {unit_word} CLAIM)" if claims_qty and not multi else "")
    gstin = (profile.gstin or "").strip()
    contact = f"CONTACT: {profile.contact_numbers or ''}" + (f"   |   GSTIN: {gstin}" if gstin else "")
    data = [
        [profile.business_name.upper(), "", "", "", "", ""],
        [contact + ("   |   STATEMENT" if statement else ""), "", "", "", "", ""],
        [f"NAME :   {bill['customer_name'].upper()}", "", "", "", f"MOBILE:  {bill['customer_phone'] or ''}", ""],
        [f"Address :  {bill['customer_address'] or ''}", "", "", "", f"{period_title} :  {bill['period_label']}", ""],
        ["", "", "", "", "", ""],
    ]
    header_row = 5
    if multi:
        data.append(["DATE", "PRODUCT", "QTY", "UNIT", "RATE", "AMOUNT"])
        rows = [l for l in lines if l["qty"] > 0 or l.get("claim_qty")]
        for l in rows:
            qty = fmt_num(l["qty"]) if l["qty"] > 0 else "-"
            if l.get("claim_qty"):
                qty += " *"
            data.append([date.fromisoformat(l["date"]).strftime("%d/%m/%Y"), l.get("product", ""), qty,
                         UNIT_WORD.get(l.get("unit", ""), (l.get("unit") or "").upper()), fmt_num(l["rate"]),
                         fmt_num(l["amount"])])
        if not rows:
            data.append(["", "Nothing delivered in this period", "", "", "", ""])
        day_rows = max(1, len(rows))
    else:
        data.append(["DATE", f"QTY/{unit_word}", "RATE", "DATE", f"QTY/{unit_word}", "RATE"])
        for i in range(day_rows):
            data.append(cells(left[i] if i < len(left) else None) + cells(right[i] if i < len(right) else None))
    first_day, last_day = header_row + 1, header_row + day_rows

    # Several products: what each came to over the period
    prod_title = prod_head = None
    if multi and products:
        prod_title = len(data)
        data.append(["PRODUCT TOTALS", "", "", "", "", ""])
        prod_head = len(data)
        data.append(["PRODUCT", "", "QTY", "UNIT", "RATE", "AMOUNT"])
        for p in products:
            data.append([p["product"], "", fmt_num(p["qty"]), UNIT_WORD.get(p["unit"], (p["unit"] or "").upper()),
                         fmt_num(p["rate"]) + (" (avg)" if p.get("mixed_rates") else ""), fmt_num(p["amount"])])
    prod_end = len(data) - 1

    # Claim adjustments: original quantity, claim and final quantity for each claim day
    adj_title = adj_head = None
    if adjustments:
        adj_title = len(data)
        data.append(["CLAIM ADJUSTMENTS (* marked days above)", "", "", "", "", ""])
        adj_head = len(data)
        data.append(["DATE", "ORIGINAL QTY", "CLAIM QTY", "FINAL QTY", "RATE", "DEDUCTED"])
        for adj in adjustments:
            refunded = adj["mode"] == "refunded"
            data.append([
                date.fromisoformat(adj["date"]).strftime("%d/%m/%Y") + (f" {adj.get('product', '')}" if multi else ""),
                fmt_num(adj["original_qty"]),
                fmt_num(adj["claim_qty"]),
                fmt_num(adj["final_qty"]) + (" (unchanged)" if refunded else ""),
                fmt_num(adj["rate"]),
                f"REFUNDED {fmt_num(adj['amount'])}" if refunded else fmt_num(adj["amount"]),
            ])

    # GST inside the rates (only when the dairy has a GSTIN)
    gst_title = gst_head = None
    gst_rows = bill.get("gst") or []
    if gst_rows:
        gst_title = len(data)
        data.append(["GST SUMMARY (INCLUDED IN THE RATES)", "", "", "", "", ""])
        gst_head = len(data)
        data.append(["GST RATE", "TAXABLE VALUE", "CGST", "SGST", "TOTAL GST", "AMOUNT"])
        for g in gst_rows:
            data.append([f"{fmt_num(g['gst_rate'])}%", fmt_num(g["taxable"]), fmt_num(g["cgst"]), fmt_num(g["sgst"]),
                         fmt_num(g["gst"]), fmt_num(g["amount"])])

    rate_text = (fmt_num(bill["rate"]) + (" (avg)" if bill.get("mixed_rates") else "")) if bill.get("rate") is not None else ""
    pay_start = len(data)
    left_details = [
        "PAYMENT DETAILS",
        profile.bank_account_name or profile.business_name,
        profile.bank_name or "",
        f"A/C NO: {profile.bank_account_number or ''}",
        f"IFSC CODE: {profile.bank_ifsc or ''}",
        f"BRANCH : {profile.bank_branch or ''}",
        f"GOOGLE PAY/ PHONE PAY : {profile.upi_number or ''}",
    ]
    if multi:
        right_rows = [("TOTAL MILK (LTR)", fmt_num(bill["total_qty"])), ("PRODUCTS", str(len(products)))]
    else:
        right_rows = [(total_milk_label, fmt_num(bill["total_qty"])), ("RATE", rate_text)]
    if claims_amount:
        # Amount for the milk as delivered, then the claims taken off it
        right_rows += [
            (f"AMOUNT ({fmt_num(bill.get('original_qty', 0))} {unit_word})" if not multi else "AMOUNT",
             fmt_num(bill.get("original_amount", bill["amount"]))),
            ("LESS: CLAIMS" + (f" ({fmt_num(claims_qty)} {unit_word})" if not multi else ""), "- " + fmt_num(claims_amount)),
            ("NET AMOUNT", fmt_num(bill["amount"])),
        ]
    else:
        right_rows.append(("AMOUNT", fmt_num(bill["amount"])))
    right_rows += [
        ("ADVANCE", fmt_num(bill["advance"]) if bill["advance"] else ""),
        (f"BILLING AMOUNT({bill['period_label']})", fmt_num(bill["billing_amount"])),
        (bill.get("outstanding_label", "OUTSTANDING"), fmt_num(bill["outstanding"])),
    ]
    if not statement:
        # A bill always shows where it stands today: later payments and the account balance
        right_rows += [
            ("PAID", fmt_num(bill.get("paid_amount", 0.0))),
            ("BALANCE DUE (THIS BILL)", fmt_num(bill.get("balance_due", 0.0))),
        ]
        if bill.get("excess_paid"):
            right_rows.append(("EXCESS PAID (KEPT AS ADVANCE)", fmt_num(bill["excess_paid"])))
        current = bill.get("current_outstanding", 0.0)
        label = bill.get("current_outstanding_label", "TOTAL OUTSTANDING")
        if current < 0:
            # Customer has paid more than all bills: show it as advance, not a minus outstanding
            label = label.replace("TOTAL OUTSTANDING", "ADVANCE BALANCE")
        right_rows.append((label, fmt_num(abs(current))))
    for i in range(max(len(left_details), len(right_rows))):
        left_text = left_details[i] if i < len(left_details) else ""
        label, value = right_rows[i] if i < len(right_rows) else ("", "")
        data.append([left_text, "", "", label, "", value])

    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 1.2, GRID),
        # Title block
        ("SPAN", (0, 0), (-1, 0)), ("SPAN", (0, 1), (-1, 1)),
        ("BACKGROUND", (0, 0), (-1, 1), BLUE),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, 0), 18),
        ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
        ("LINEBELOW", (0, 1), (-1, 1), 1, GRID),
        # Customer block
        ("SPAN", (0, 2), (3, 2)), ("SPAN", (4, 2), (5, 2)),
        ("SPAN", (0, 3), (3, 3)), ("SPAN", (4, 3), (5, 3)),
        ("SPAN", (0, 4), (-1, 4)),
        ("ROWBACKGROUNDS", (0, 4), (-1, 4), [colors.white]),
        # Day table
        ("GRID", (0, header_row), (-1, last_day), 0.6, GRID),
        ("BACKGROUND", (0, header_row), (-1, header_row), BLUE),
        ("BACKGROUND", (0, first_day), (0, last_day), BLUE),
        ("ALIGN", (0, first_day), (-1, last_day), "CENTER"),
        # Payment block
        ("GRID", (0, pay_start), (-1, -1), 0.6, GRID),
        ("ALIGN", (3, pay_start), (4, -1), "CENTER"),
        ("ALIGN", (5, pay_start), (5, -1), "CENTER"),
    ]
    if not multi:
        style.append(("BACKGROUND", (3, first_day), (3, last_day), BLUE))
    else:
        style.append(("FONTSIZE", (0, first_day), (-1, last_day), 8))
    if prod_title is not None:
        style += [
            ("SPAN", (0, prod_title), (-1, prod_title)),
            ("BACKGROUND", (0, prod_title), (-1, prod_head), BLUE),
            ("GRID", (0, prod_title), (-1, prod_end), 0.6, GRID),
            ("ALIGN", (2, prod_head), (-1, prod_end), "CENTER"),
            ("FONTSIZE", (0, prod_head), (-1, prod_end), 8),
        ] + [("SPAN", (0, r), (1, r)) for r in range(prod_head, prod_end + 1)]
    if gst_title is not None:
        style += [
            ("SPAN", (0, gst_title), (-1, gst_title)),
            ("BACKGROUND", (0, gst_title), (-1, gst_head), BLUE),
            ("GRID", (0, gst_title), (-1, pay_start - 1), 0.6, GRID),
            ("ALIGN", (0, gst_head), (-1, pay_start - 1), "CENTER"),
            ("FONTSIZE", (0, gst_head), (-1, pay_start - 1), 8),
        ]
    if adjustments:
        adj_end = (gst_title - 1) if gst_title is not None else (pay_start - 1)
        style += [
            ("SPAN", (0, adj_title), (-1, adj_title)),
            ("BACKGROUND", (0, adj_title), (-1, adj_head), BLUE),
            ("GRID", (0, adj_title), (-1, adj_end), 0.6, GRID),
            ("ALIGN", (0, adj_head), (-1, adj_end), "CENTER"),
            ("FONTSIZE", (0, adj_head), (-1, adj_end), 8),
        ]
    # Long labels get a smaller font so they stay inside their cells
    for r in range(pay_start, len(data)):
        if len(data[r][3]) > 26:
            style.append(("FONTSIZE", (3, r), (4, r), 7.5))
    if len(bill["period_label"]) > 14:
        style.append(("FONTSIZE", (4, 3), (5, 3), 8))
    for r in range(pay_start, len(data)):
        style += [("SPAN", (0, r), (2, r)), ("SPAN", (3, r), (4, r)), ("BACKGROUND", (0, r), (2, r), BLUE)]
    style += [("BACKGROUND", (3, pay_start), (4, -1), BLUE)]

    table = Table(data, colWidths=COL_WIDTHS, rowHeights=[None, None, None, None, 6] + [None] * (len(data) - 5))
    table.setStyle(TableStyle(style))
    return table


def render_bills_pdf(bills: List[Dict], profile) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"{profile.business_name} - Milk Bills", author=profile.business_name
    )
    story = []
    for i, bill in enumerate(bills):
        if i:
            story.append(PageBreak())
        story.append(_bill_table(bill, profile))
    doc.build(story)
    return buffer.getvalue()
