"""Renders milk bills as PDF in the dairy's bill format (one page per bill)."""
import calendar
import io
import os
from datetime import date
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (CondPageBreak, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

BLUE = colors.HexColor("#BDD7EE")
LOGO = os.path.join(os.path.dirname(__file__), "bill_logo.png")
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


UNIT_WORD = {"L": "LTR", "kg": "KG", "pcs": "PCS", "packet": "PKT", "box": "BOX", "pouch": "POUCH", "bottle": "BTL"}


def _bank_details(profile) -> List[str]:
    return [
        "PAYMENT DETAILS",
        profile.bank_account_name or profile.business_name,
        profile.bank_name or "",
        f"A/C NO: {profile.bank_account_number or ''}",
        f"IFSC CODE: {profile.bank_ifsc or ''}",
        f"BRANCH : {profile.bank_branch or ''}",
        f"GOOGLE PAY/ PHONE PAY : {profile.upi_number or ''}",
    ]


def _amount_rows(bill: Dict, amount_note: str = "", claim_note: str = "", hide_empty_advance: bool = True) -> List[tuple]:
    """AMOUNT -> claims -> advance -> billing amount -> outstanding -> paid / balance, as (label, value)."""
    rows = []
    claims_amount = bill.get("claims_amount", 0.0)
    if claims_amount:
        # Amount for the milk as delivered, then the claims taken off it
        rows += [
            ("AMOUNT" + amount_note, fmt_num(bill.get("original_amount", bill["amount"]))),
            ("LESS: CLAIMS" + claim_note, "- " + fmt_num(claims_amount)),
            ("NET AMOUNT", fmt_num(bill["amount"])),
        ]
    else:
        rows.append(("AMOUNT", fmt_num(bill["amount"])))
    if bill["advance"] or not hide_empty_advance:
        rows += [
            ("ADVANCE", fmt_num(bill["advance"]) if bill["advance"] else ""),
            (f"BILLING AMOUNT({bill['period_label']})", fmt_num(bill["billing_amount"])),
        ]
    rows.append((bill.get("outstanding_label", "OUTSTANDING"), fmt_num(bill["outstanding"])))
    if not bill.get("is_statement", False):
        # A bill always shows where it stands today: later payments and the account balance
        rows += [
            ("PAID", fmt_num(bill.get("paid_amount", 0.0))),
            ("BALANCE DUE (THIS BILL)", fmt_num(bill.get("balance_due", 0.0))),
        ]
        if bill.get("excess_paid"):
            rows.append(("EXCESS PAID (KEPT AS ADVANCE)", fmt_num(bill["excess_paid"])))
        current = bill.get("current_outstanding", 0.0)
        label = bill.get("current_outstanding_label", "TOTAL OUTSTANDING")
        if current < 0:
            # Customer has paid more than all bills: show it as advance, not a minus outstanding
            label = label.replace("TOTAL OUTSTANDING", "ADVANCE BALANCE")
        rows.append((label, fmt_num(abs(current))))
    return rows


PAGE_W = sum(COL_WIDTHS)
LIGHT = colors.HexColor("#EEF5FB")
CELL = ParagraphStyle("cell", fontName="Helvetica-Bold", fontSize=7.5, leading=9, alignment=TA_CENTER)
CELL_LEFT = ParagraphStyle("cell_left", parent=CELL, alignment=TA_LEFT)
MAX_PRODUCT_COLS = 6


def _split_name(name: str):
    """'Cow Milk Brand Pouch - 1 L' -> ('Cow Milk Brand Pouch', '1 L')."""
    head, sep, tail = (name or "").rpartition(" - ")
    return (head, tail) if sep else (name or "", "")


def _section(title: str, header: List, rows: List[List], widths: List[float], left_cols: int = 1,
             total_row: bool = False, repeat: bool = False):
    """A titled grid: blue title and header rows, light bands, numbers centred."""
    n = len(widths)
    data = [[title] + [""] * (n - 1), header] + rows
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("SPAN", (0, 0), (-1, 0)),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 0), (-1, 1), BLUE),
        ("GRID", (0, 0), (-1, -1), 0.6, GRID),
        ("BOX", (0, 0), (-1, -1), 1.2, GRID),
        ("ALIGN", (left_cols, 1), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 2), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 2), (-1, -1), 1.6),
    ]
    body_end = len(data) - (2 if total_row else 1)
    for r in range(2, body_end + 1):
        if r % 2:
            style.append(("BACKGROUND", (0, r), (-1, r), LIGHT))
    if total_row:
        style += [("BACKGROUND", (0, -1), (-1, -1), BLUE), ("FONTSIZE", (0, -1), (-1, -1), 9)]
    table = Table(data, colWidths=widths, repeatRows=2 if repeat else 0)
    table.setStyle(TableStyle(style))
    return table if repeat else KeepTogether(table)


def _multi_bill(bill: Dict, profile) -> List:
    """Bill with several products: a day x product register, product totals, then payment."""
    lines: List[Dict] = bill["lines"]
    products = bill.get("products") or []
    start = date.fromisoformat(bill["period_start"])
    end = date.fromisoformat(bill["period_end"])
    statement = bill.get("is_statement", False)
    period_title = "Month" if bill["bill_type"] == "monthly" else ("Date" if start == end else "Period")
    gstin = (profile.gstin or "").strip()
    contact = f"CONTACT: {profile.contact_numbers or ''}" + (f"   |   GSTIN: {gstin}" if gstin else "")
    w_left, w_right = PAGE_W * 0.62, PAGE_W * 0.38
    head = Table([
        [profile.business_name.upper(), ""],
        [contact + ("   |   STATEMENT" if statement else ""), ""],
        [f"NAME :   {bill['customer_name'].upper()}", f"MOBILE:  {bill['customer_phone'] or ''}"],
        [Paragraph(f"Address :  {bill['customer_address'] or ''}", CELL_LEFT), f"{period_title} :  {bill['period_label']}"],
    ], colWidths=[w_left, w_right])
    head.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 1.2, GRID),
        ("SPAN", (0, 0), (-1, 0)), ("SPAN", (0, 1), (-1, 1)),
        ("BACKGROUND", (0, 0), (-1, 1), BLUE),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, 0), 18),
        ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
        ("LINEBELOW", (0, 1), (-1, 1), 1, GRID),
        ("FONTSIZE", (1, 3), (1, 3), 8 if len(bill["period_label"]) > 14 else 9),
    ]))
    story = [head, Spacer(1, 3 * mm)]

    # Day x product register: only the quantity per day, rates and amounts are in the totals below
    pids = [p["product_id"] for p in products]
    days: Dict[str, Dict] = {}
    for l in lines:
        if l["qty"] > 0 or l.get("claim_qty"):
            days.setdefault(l["date"], {})[l.get("product_id")] = l
    day_keys = sorted(days)
    single_month = start.year == end.year and start.month == end.month
    date_w, amount_w = 20 * mm, 24 * mm
    # Many products: split the columns into equal parts (8 -> 4 + 4), each part with its own dates
    parts = max(1, -(-len(pids) // MAX_PRODUCT_COLS))
    size = max(1, -(-len(pids) // parts))
    chunks = [pids[i:i + size] for i in range(0, len(pids), size)] or [[]]
    with_amount = len(chunks) == 1  # with many products the day amount needs every column; skip it
    if len(day_keys) <= 1:
        chunks = []  # one day: the product totals below already show it
    names = {p["product_id"]: p["product"] for p in products}
    for n, chunk in enumerate(chunks):
        prod_w = (PAGE_W - date_w - (amount_w if with_amount else 0)) / max(1, len(chunk))
        header = ["DATE"]
        for pid in chunk:
            group, size = _split_name(names[pid])
            header.append(Paragraph(f"{group}<br/>{size}" if size else group, CELL))
        rows = []
        for d in day_keys:
            dd = date.fromisoformat(d)
            row = [dd.strftime("%d %a") if single_month else dd.strftime("%d/%m")]
            for pid in chunk:
                l = days[d].get(pid)
                if not l:
                    row.append("")
                    continue
                qty = fmt_num(l["qty"]) if l["qty"] > 0 else "-"
                row.append(qty + (" *" if l.get("claim_qty") else ""))
            if with_amount:
                row.append(fmt_num(sum(l["amount"] for l in days[d].values())))
            rows.append(row)
        if with_amount:
            header.append("AMOUNT")
        if not rows:
            rows = [["", "Nothing delivered in this period"] + [""] * (len(header) - 2)]
        title = "DAILY DELIVERY (QUANTITY)" + (f" - PART {n + 1} OF {len(chunks)}" if len(chunks) > 1 else "")
        widths = [date_w] + [prod_w] * len(chunk) + ([amount_w] if with_amount else [])
        if n:
            story.append(CondPageBreak(70 * mm))  # start a part on a new page rather than with a few rows
        story += [_section(title, header, rows, widths, repeat=True), Spacer(1, 3 * mm)]

    # One line per product: total quantity, litres, rate and amount
    rows = []
    for p in products:
        litres = p["qty"] * p.get("litres_per_unit", 0)
        rows.append([Paragraph(p["product"], CELL_LEFT), fmt_num(p["qty"]),
                     UNIT_WORD.get(p["unit"], (p["unit"] or "").upper()), fmt_num(round(litres, 3)) if litres else "-",
                     fmt_num(p["rate"]) + (" (avg)" if p.get("mixed_rates") else ""), fmt_num(p["amount"])])
    rows.append(["TOTAL", "", "", fmt_num(bill["total_qty"]), "",
                 fmt_num(bill.get("original_amount", bill["amount"]) if bill.get("claims_amount") else bill["amount"])])
    widths = [66 * mm, 22 * mm, 20 * mm, 24 * mm, 24 * mm]
    widths.append(PAGE_W - sum(widths))
    story += [_section("PRODUCT TOTALS" if chunks else "PRODUCTS", ["PRODUCT", "QTY", "UNIT", "MILK (LTR)", "RATE", "AMOUNT"], rows, widths,
                       total_row=True), Spacer(1, 3 * mm)]

    adjustments: List[Dict] = bill.get("adjustments", [])
    if adjustments:
        rows = []
        for adj in adjustments:
            refunded = adj["mode"] == "refunded"
            rows.append([date.fromisoformat(adj["date"]).strftime("%d/%m/%Y"), Paragraph(adj.get("product", ""), CELL_LEFT),
                         fmt_num(adj["original_qty"]), fmt_num(adj["claim_qty"]),
                         fmt_num(adj["final_qty"]) + (" (same)" if refunded else ""), fmt_num(adj["rate"]),
                         f"REFUNDED {fmt_num(adj['amount'])}" if refunded else fmt_num(adj["amount"])])
        widths = [22 * mm, 52 * mm, 20 * mm, 20 * mm, 22 * mm, 18 * mm]
        widths.append(PAGE_W - sum(widths))
        story += [_section("CLAIM ADJUSTMENTS (* marked days above)",
                           ["DATE", "PRODUCT", "ORIGINAL", "CLAIM", "FINAL", "RATE", "DEDUCTED"], rows, widths, left_cols=2),
                  Spacer(1, 3 * mm)]

    gst_rows = bill.get("gst") or []
    if gst_rows:
        rows = [[f"{fmt_num(g['gst_rate'])}%", fmt_num(g["taxable"]), fmt_num(g["cgst"]), fmt_num(g["sgst"]),
                 fmt_num(g["gst"]), fmt_num(g["amount"])] for g in gst_rows]
        story += [_section("GST SUMMARY (INCLUDED IN THE RATES)",
                           ["GST RATE", "TAXABLE VALUE", "CGST", "SGST", "TOTAL GST", "AMOUNT"], rows, [PAGE_W / 6] * 6,
                           left_cols=0), Spacer(1, 3 * mm)]

    left_details = _bank_details(profile)
    right_rows = _amount_rows(bill)
    data = []
    for i in range(max(len(left_details), len(right_rows))):
        label, value = right_rows[i] if i < len(right_rows) else ("", "")
        data.append([left_details[i] if i < len(left_details) else "", label, value])
    pay = Table(data, colWidths=[PAGE_W * 0.46, PAGE_W * 0.36, PAGE_W * 0.18])
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.6, GRID),
        ("BOX", (0, 0), (-1, -1), 1.2, GRID),
        ("BACKGROUND", (0, 0), (1, -1), BLUE),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]
    for r, (label, _) in enumerate(right_rows):
        if len(label) > 28:
            style.append(("FONTSIZE", (1, r), (1, r), 7.5))
        if label.startswith(("BALANCE DUE", "TOTAL OUTSTANDING")) or (statement and r == len(right_rows) - 1):
            style += [("FONTSIZE", (2, r), (2, r), 10), ("BACKGROUND", (2, r), (2, r), LIGHT)]
    pay.setStyle(TableStyle(style))
    story.append(KeepTogether(pay))
    return story


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
    left_details = _bank_details(profile)
    right_rows = [(total_milk_label, fmt_num(bill["total_qty"])), ("RATE", rate_text)]
    right_rows += _amount_rows(bill, f" ({fmt_num(bill.get('original_qty', 0))} {unit_word})",
                               f" ({fmt_num(claims_qty)} {unit_word})", hide_empty_advance=False)
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
        if os.path.exists(LOGO):
            story += [Image(LOGO, width=22 * mm, height=22 * mm), Spacer(1, 2 * mm)]
        if bill.get("multi_product"):
            story += _multi_bill(bill, profile)
        else:
            story.append(_bill_table(bill, profile))
    doc.build(story)
    return buffer.getvalue()
