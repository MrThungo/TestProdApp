from __future__ import annotations

import csv
import html
import zipfile
from io import BytesIO, StringIO
from urllib.parse import urlparse

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from back_to_god.core.formatting import bits_size, chat_timestamp, pretty_date
from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import (
    can_approve_finance,
    can_manage_finance,
    can_upload_finance,
    login_required,
    role_required,
)
from back_to_god.core.security import today_date, validate_csrf
from back_to_god.services.audit import log_event
from back_to_god.services.finance import (
    approve_deposit_slip,
    can_view_slip,
    cents_to_money,
    create_deposit_slip,
    create_offering,
    deleted_deposit_slip_count,
    deposit_slip_count,
    finance_summary,
    get_deposit_slip,
    list_deposit_slip_options,
    list_deleted_deposit_slips,
    list_deposit_slips_for_report,
    list_deposit_slips,
    list_offerings,
    list_offerings_for_slip,
    list_offerings_for_report,
    list_visible_deposit_slips,
    link_offering_to_slip,
    offering_count,
    reject_deposit_slip,
    restore_deposit_slip,
    revoke_deposit_slip_visibility,
    soft_delete_deposit_slip,
    update_deposit_slip,
    visible_deposit_slip_count,
)


bp = Blueprint("finance", __name__, url_prefix="/finance")


def _xml(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _excel_column(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _sheet_xml(rows: list[list[object]]) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
    parts.append('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>')
    for row_index, row in enumerate(rows, start=1):
        parts.append(f'<row r="{row_index}">')
        for column_index, value in enumerate(row, start=1):
            cell = f"{_excel_column(column_index)}{row_index}"
            parts.append(f'<c r="{cell}" t="inlineStr"><is><t>{_xml(value)}</t></is></c>')
        parts.append("</row>")
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


def _xlsx_response(filename: str, sheets: dict[str, list[list[object]]]) -> Response:
    output = BytesIO()
    sheet_names = list(sheets)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
""" + "".join(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for index in range(1, len(sheet_names) + 1)
            ) + "</Types>",
        )
        workbook.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        workbook.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>"""
            + "".join(
                f'<sheet name="{_xml(name[:31])}" sheetId="{index}" r:id="rId{index}"/>'
                for index, name in enumerate(sheet_names, start=1)
            )
            + "</sheets></workbook>",
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">"""
            + "".join(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
                for index in range(1, len(sheet_names) + 1)
            )
            + "</Relationships>",
        )
        for index, name in enumerate(sheet_names, start=1):
            workbook.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(sheets[name]))
    response = Response(
        output.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _pdf_escape(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _pdf_cell(value: object, width: int) -> str:
    clean = "" if value is None else " ".join(str(value).split())
    if len(clean) > width:
        clean = clean[: max(0, width - 3)] + "..."
    return clean.ljust(width)


def _pdf_table_line(values: list[object], widths: list[int]) -> str:
    return " | ".join(_pdf_cell(value, width) for value, width in zip(values, widths))


def _pdf_table_rule(widths: list[int]) -> str:
    return "-+-".join("-" * width for width in widths)


def _pdf_report_response(
    filename: str,
    title: str,
    summary_items: list[tuple[str, object]],
    tables: list[dict[str, object]],
    note: str = "",
) -> Response:
    page_width = 842
    page_height = 595
    margin = 32
    pages: list[bytes] = []
    commands: list[str] = []
    y = page_height - margin
    page_number = 0

    def draw_text(text: object, font: str = "F3", size: float = 7.0, x_offset: float = 0) -> None:
        nonlocal y
        safe = _pdf_escape(text)
        commands.append(f"BT /{font} {size:.2f} Tf {margin + x_offset:.2f} {y:.2f} Td ({safe}) Tj ET")

    def add_line(text: object, font: str = "F3", size: float = 7.0, height: float = 9.0, x_offset: float = 0) -> None:
        nonlocal y
        ensure_space(height)
        draw_text(text, font, size, x_offset)
        y -= height

    def finish_page() -> None:
        if commands:
            pages.append("\n".join(commands).encode("latin-1", "replace"))

    def begin_page() -> None:
        nonlocal commands, y, page_number
        commands = []
        y = page_height - margin
        page_number += 1
        draw_text(title, "F2", 13.5)
        y -= 15
        draw_text(f"Generated: {today_date()} | Page {page_number}", "F1", 8)
        y -= 10
        commands.append(f"0.35 w {margin} {y:.2f} m {page_width - margin} {y:.2f} l S")
        y -= 14

    def ensure_space(required_height: float) -> None:
        nonlocal commands
        if y - required_height >= margin:
            return
        finish_page()
        begin_page()

    def add_section(title_text: str, description: str = "") -> None:
        nonlocal y
        ensure_space(24)
        y -= 3
        draw_text(title_text, "F2", 9.5)
        y -= 10
        if description:
            draw_text(description, "F1", 7.5)
            y -= 10

    def add_table(table: dict[str, object]) -> None:
        nonlocal y
        title_text = str(table["title"])
        description = str(table.get("description") or "")
        headers = list(table["headers"])  # type: ignore[arg-type]
        widths = list(table["widths"])  # type: ignore[arg-type]
        rows = list(table["rows"])  # type: ignore[arg-type]
        font_size = float(table.get("font_size") or 6.4)
        line_height = float(table.get("line_height") or 8.0)

        add_section(title_text, description)
        ensure_space(line_height * 3)
        add_line(_pdf_table_line(headers, widths), "F4", font_size, line_height)
        add_line(_pdf_table_rule(widths), "F3", font_size, line_height)
        if rows:
            for row in rows:
                add_line(_pdf_table_line(list(row), widths), "F3", font_size, line_height)
        else:
            empty = ["No records"] + [""] * (len(widths) - 1)
            add_line(_pdf_table_line(empty, widths), "F3", font_size, line_height)
        ensure_space(7)
        y -= 7

    begin_page()
    if note:
        add_line(note, "F1", 7.5, 10)
        add_line("", "F1", 4, 5)

    summary_rows = []
    for index in range(0, len(summary_items), 3):
        chunk = summary_items[index : index + 3]
        row: list[object] = []
        for label, value in chunk:
            row.extend([label, value])
        while len(row) < 6:
            row.extend(["", ""])
        summary_rows.append(row)
    add_table(
        {
            "title": "Executive Summary",
            "description": "High-level finance totals for this report.",
            "headers": ["Metric", "Value", "Metric", "Value", "Metric", "Value"],
            "widths": [24, 18, 24, 18, 24, 18],
            "rows": summary_rows,
            "font_size": 7.0,
            "line_height": 8.5,
        }
    )

    for table in tables:
        add_table(table)

    finish_page()

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>",
    ]
    page_ids: list[int] = []
    for stream in pages:
        page_id = len(objects) + 1
        stream_id = page_id + 1
        page_ids.append(page_id)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R >> >> "
            f"/Contents {stream_id} 0 R >>".encode()
        )
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(page_ids)} >>".encode()

    pdf = BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(pdf.tell())
        pdf.write(f"{index} 0 obj\n".encode())
        pdf.write(obj)
        pdf.write(b"\nendobj\n")
    xref_at = pdf.tell()
    pdf.write(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.write(f"{offset:010d} 00000 n \n".encode())
    pdf.write(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode())
    response = Response(pdf.getvalue(), mimetype="application/pdf")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _safe_back_url() -> str:
    fallback = url_for("finance.index")
    referrer = request.referrer
    if not referrer:
        return fallback
    referrer_url = urlparse(referrer)
    host_url = urlparse(request.host_url)
    if referrer_url.netloc and referrer_url.netloc != host_url.netloc:
        return fallback
    return referrer


@bp.get("/")
@login_required
def index():
    can_manage = can_manage_finance()
    total = deposit_slip_count() if can_manage else visible_deposit_slip_count()
    pagination = build_pagination(total, current_page(), 10)
    slips = (
        list_deposit_slips(pagination["per_page"], pagination["offset"])
        if can_manage
        else list_visible_deposit_slips(pagination["per_page"], pagination["offset"])
    )
    return render_template(
        "finance/index.html",
        slips=slips,
        offerings=list_offerings(8, 0) if can_manage else [],
        report_slips=list_deposit_slips_for_report() if can_manage else [],
        report_offerings=list_offerings_for_report() if can_manage else [],
        offering_total=offering_count() if can_manage else 0,
        slip_options=list_deposit_slip_options() if can_upload_finance() else [],
        summary=finance_summary() if can_manage else None,
        can_manage_finance=can_manage,
        can_upload_finance=can_upload_finance(),
        can_approve_finance=can_approve_finance(),
        today=today_date(),
        cents_to_money=cents_to_money,
        pagination=pagination,
        deleted_slips=deleted_deposit_slip_count() if g.user["role"] == "super_admin" else 0,
    )


@bp.post("/offerings")
@role_required("super_admin", "treasurer")
def create_offering_entry():
    validate_csrf()
    try:
        offering_id = create_offering(request.form, g.user["id"])
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("finance.index"))
    log_event("offering_created", g.user["id"], "finance_offering", offering_id, request.form.get("offering_type", ""))
    flash("Offering captured.", "success")
    return redirect(url_for("finance.index"))


@bp.post("/offerings/<int:offering_id>/link-slip")
@role_required("super_admin", "treasurer")
def link_offering_slip(offering_id: int):
    validate_csrf()
    slip_id = request.form.get("deposit_slip_id", "").strip()
    if not slip_id.isdigit():
        flash("Choose a deposit slip to link.", "error")
        return redirect(url_for("finance.index"))
    try:
        link_offering_to_slip(offering_id, int(slip_id))
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("finance.index"))
    log_event("offering_linked_to_slip", g.user["id"], "finance_offering", offering_id, slip_id)
    flash("Offering linked to deposit slip.", "success")
    return redirect(url_for("finance.index"))


@bp.post("/deposit-slips")
@role_required("super_admin", "treasurer")
def create_slip():
    validate_csrf()
    try:
        slip_id = create_deposit_slip(request.form, request.files.get("deposit_slip"), g.user["id"])
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("finance.index"))

    log_event("deposit_slip_created", g.user["id"], "deposit_slip", slip_id, request.form.get("title", ""))
    flash("Deposit slip uploaded.", "success")
    return redirect(url_for("finance.index"))


@bp.post("/deposit-slips/<int:slip_id>/edit")
@role_required("super_admin", "treasurer")
def edit_slip(slip_id: int):
    validate_csrf()
    slip = get_deposit_slip(slip_id)
    if slip is None:
        abort(404)
    update_deposit_slip(slip_id, request.form)
    log_event("deposit_slip_updated", g.user["id"], "deposit_slip", slip_id, slip["title"])
    flash("Deposit slip updated. Visibility will need approval again if requested.", "success")
    return redirect(url_for("finance.index"))


@bp.post("/deposit-slips/<int:slip_id>/approve")
@role_required("super_admin", "admin", "pastor")
def approve_slip(slip_id: int):
    validate_csrf()
    slip = get_deposit_slip(slip_id)
    if slip is None:
        abort(404)
    approve_deposit_slip(slip_id, g.user["id"])
    log_event("deposit_slip_approved", g.user["id"], "deposit_slip", slip_id, slip["title"])
    flash("Deposit slip approved and visible during its time window.", "success")
    return redirect(url_for("finance.index"))


@bp.post("/deposit-slips/<int:slip_id>/reject")
@role_required("super_admin", "admin", "pastor")
def reject_slip(slip_id: int):
    validate_csrf()
    slip = get_deposit_slip(slip_id)
    if slip is None:
        abort(404)
    reject_deposit_slip(slip_id, g.user["id"])
    log_event("deposit_slip_rejected", g.user["id"], "deposit_slip", slip_id, slip["title"])
    flash("Deposit slip visibility request rejected.", "success")
    return redirect(url_for("finance.index"))


@bp.post("/deposit-slips/<int:slip_id>/revoke")
@role_required("super_admin", "admin", "pastor", "treasurer")
def revoke_slip(slip_id: int):
    validate_csrf()
    slip = get_deposit_slip(slip_id)
    if slip is None:
        abort(404)
    revoke_deposit_slip_visibility(slip_id, g.user["id"])
    log_event("deposit_slip_visibility_revoked", g.user["id"], "deposit_slip", slip_id, slip["title"])
    flash("Deposit slip visibility revoked.", "success")
    return redirect(url_for("finance.index"))


@bp.post("/deposit-slips/<int:slip_id>/delete")
@role_required("super_admin")
def delete_slip(slip_id: int):
    validate_csrf()
    slip = get_deposit_slip(slip_id)
    if slip is None:
        abort(404)
    soft_delete_deposit_slip(slip_id, g.user["id"])
    log_event("deposit_slip_deleted", g.user["id"], "deposit_slip", slip_id, slip["title"])
    flash("Deposit slip moved to the recycle bin.", "success")
    return redirect(url_for("finance.index"))


@bp.get("/recycle-bin")
@role_required("super_admin")
def recycle_bin():
    total = deleted_deposit_slip_count()
    pagination = build_pagination(total, current_page(), 10)
    return render_template(
        "finance/recycle_bin.html",
        slips=list_deleted_deposit_slips(pagination["per_page"], pagination["offset"]),
        pagination=pagination,
        cents_to_money=cents_to_money,
    )


@bp.post("/deposit-slips/<int:slip_id>/restore")
@role_required("super_admin")
def restore_slip(slip_id: int):
    validate_csrf()
    slip = get_deposit_slip(slip_id, include_deleted=True)
    if slip is None or not slip["deleted_at"]:
        abort(404)
    restore_deposit_slip(slip_id, g.user["id"])
    log_event("deposit_slip_restored", g.user["id"], "deposit_slip", slip_id, slip["title"])
    flash("Deposit slip restored.", "success")
    return redirect(url_for("finance.recycle_bin"))


@bp.get("/reports/deposit-slips.csv")
@role_required("super_admin", "admin", "pastor", "treasurer")
def deposit_slips_report():
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Title",
            "Bank",
            "Reference",
            "Amount",
            "Deposit date",
            "Status",
            "Visible now",
            "Visible from",
            "Visible until",
            "Deposited by / uploaded by",
            "Approved/revoked by",
            "Approved/revoked at",
            "File",
            "Mime type",
            "Size bytes",
            "Created",
            "Updated",
        ]
    )
    rows = list_deposit_slips_for_report()
    for slip in rows:
        writer.writerow(
            [
                slip["title"],
                slip["bank_name"] or "",
                slip["reference"] or "",
                cents_to_money(slip["amount_cents"]),
                slip["deposit_date"] or "",
                slip["approval_status"],
                "Yes" if slip["is_visible"] else "No",
                slip["visible_from"] or "",
                slip["visible_until"] or "",
                slip["created_by_name"] or "",
                slip["approved_by_name"] or "",
                slip["approved_at"] or "",
                slip["original_name"] or "",
                slip["mime_type"] or "",
                slip["size_bytes"] or 0,
                slip["created_at"] or "",
                slip["updated_at"] or "",
            ]
        )
    log_event("finance_report_downloaded", g.user["id"], "report", None, str(len(rows)))
    response = Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="back-to-god-finance-deposit-slips.csv"'
    return response


def _finance_report_rows() -> tuple[list[list[object]], list[list[object]]]:
    slips = [[
        "Title", "Bank", "Reference", "Amount", "Deposit date", "Status",
        "Visible now", "Visible from", "Visible until", "Deposited by / uploaded by", "Approved/revoked by",
        "Approved/revoked at", "File", "Mime type", "Size bytes", "Created", "Updated",
    ]]
    for slip in list_deposit_slips_for_report():
        slips.append([
            slip["title"], slip["bank_name"] or "", slip["reference"] or "",
            cents_to_money(slip["amount_cents"]), slip["deposit_date"] or "",
            slip["approval_status"], "Yes" if slip["is_visible"] else "No",
            slip["visible_from"] or "", slip["visible_until"] or "",
            slip["created_by_name"] or "", slip["approved_by_name"] or "",
            slip["approved_at"] or "", slip["original_name"] or "",
            slip["mime_type"] or "", slip["size_bytes"] or 0,
            slip["created_at"] or "", slip["updated_at"] or "",
        ])

    offerings = [["Date", "Type", "Amount", "Linked slip", "Reference", "Captured by", "Note", "Created"]]
    for offering in list_offerings_for_report():
        offerings.append([
            offering["offering_date"], offering["offering_type"],
            cents_to_money(offering["amount_cents"]),
            offering["deposit_slip_title"] or "Not linked",
            offering["deposit_reference"] or "",
            offering["captured_by_name"] or "",
            offering["note"] or "",
            offering["created_at"] or "",
        ])
    return slips, offerings


@bp.get("/reports/finance.xlsx")
@role_required("super_admin", "admin", "pastor", "treasurer")
def finance_excel_report():
    slips, offerings = _finance_report_rows()
    log_event("finance_excel_downloaded", g.user["id"], "report", None, f"{len(slips) - 1}/{len(offerings) - 1}")
    return _xlsx_response(
        "back-to-god-finance-report.xlsx",
        {"Deposit slips": slips, "Offerings": offerings},
    )


@bp.get("/reports/finance.pdf")
@role_required("super_admin", "admin", "pastor", "treasurer")
def finance_pdf_report():
    summary = finance_summary()
    slips = list_deposit_slips_for_report()
    offerings = list_offerings_for_report()

    def timestamp(value: str | None, fallback: str = "") -> str:
        return chat_timestamp(value) if value else fallback

    def visibility_label(slip) -> str:
        if slip["is_visible"] and slip["visible_until"]:
            return f"Visible until {timestamp(slip['visible_until'])}"
        if slip["approval_status"] == "approved" and slip["visible_until"]:
            return "Expired or revoked"
        return "Not visible"

    summary_items = [
        ("Deposit slips", summary["slip_count"]),
        ("Total captured", summary["total_money"]),
        ("Offerings", summary["offering_money"]),
        ("Offering records", summary["offering_count"]),
        ("Visible now", summary["visible_count"]),
        ("Pending approval", summary["pending_count"]),
        ("Approved", summary["approved_count"]),
        ("Draft", summary["draft_count"]),
        ("Rejected", summary["rejected_count"]),
        ("Expired windows", summary["expired_count"]),
        ("Report slips", len(slips)),
        ("Report offerings", len(offerings)),
    ]

    tables = [
        {
            "title": "Monthly Deposits",
            "description": "Captured deposit values by month.",
            "headers": ["Month", "Amount"],
            "widths": [16, 16],
            "rows": [[month["month"], cents_to_money(month["cents"])] for month in summary["monthly"]],
            "font_size": 7.0,
        },
        {
            "title": "Bank Totals",
            "description": "Captured totals grouped by bank.",
            "headers": ["Bank", "Amount"],
            "widths": [34, 18],
            "rows": [[bank["label"], cents_to_money(bank["cents"])] for bank in summary["by_bank"]],
            "font_size": 7.0,
        },
        {
            "title": "Status Summary",
            "description": "Approval and visibility state of deposit slips.",
            "headers": ["Status", "Count"],
            "widths": [24, 10],
            "rows": [[item["label"], item["count"]] for item in summary["status_breakdown"]],
            "font_size": 7.0,
        },
        {
            "title": "Offering Type Summary",
            "description": "Giving categories and captured values.",
            "headers": ["Offering type", "Amount"],
            "widths": [34, 18],
            "rows": [[item["label"], cents_to_money(item["cents"])] for item in summary["offering_types"]],
            "font_size": 7.0,
        },
        {
            "title": "Offering Register",
            "description": "Captured offerings with linked deposit slip references.",
            "headers": ["Date", "Type", "Amount", "Captured by", "Linked slip", "Reference", "Note", "Captured at"],
            "widths": [11, 18, 12, 21, 22, 16, 24, 16],
            "rows": [
                [
                    pretty_date(offering["offering_date"]),
                    offering["offering_type"],
                    cents_to_money(offering["amount_cents"]),
                    offering["captured_by_name"] or "Unknown",
                    offering["deposit_slip_title"] or "Not linked",
                    offering["deposit_reference"] or "Not linked",
                    offering["note"] or "None",
                    timestamp(offering["created_at"], "Not recorded"),
                ]
                for offering in offerings
            ],
            "font_size": 5.9,
            "line_height": 7.2,
        },
        {
            "title": "Deposit Accountability Register",
            "description": "Every deposit slip with the person who deposited/uploaded the money.",
            "headers": ["Date", "Slip title", "Bank", "Reference", "Amount", "Deposited/uploaded by", "Uploaded at", "Status", "Visibility"],
            "widths": [11, 22, 14, 15, 13, 24, 16, 10, 24],
            "rows": [
                [
                    pretty_date(slip["deposit_date"]),
                    slip["title"],
                    slip["bank_name"] or "Bank",
                    slip["reference"] or "Not added",
                    cents_to_money(slip["amount_cents"]),
                    slip["created_by_name"] or "Unknown",
                    timestamp(slip["created_at"], "Not recorded"),
                    slip["approval_status"],
                    visibility_label(slip),
                ]
                for slip in slips
            ],
            "font_size": 5.9,
            "line_height": 7.2,
        },
        {
            "title": "Approval & Visibility Audit",
            "description": "Who approved or revoked visibility and the active visibility window.",
            "headers": ["Slip title", "Visible", "Visible from", "Visible until", "Approved/revoked by", "Approved/revoked at", "Updated at"],
            "widths": [24, 8, 17, 17, 24, 17, 17],
            "rows": [
                [
                    slip["title"],
                    "Yes" if slip["is_visible"] else "No",
                    timestamp(slip["visible_from"], "Not visible"),
                    timestamp(slip["visible_until"], "Not set"),
                    slip["approved_by_name"] or "Not approved",
                    timestamp(slip["approved_at"], "Not approved"),
                    timestamp(slip["updated_at"], "Not recorded"),
                ]
                for slip in slips
            ],
            "font_size": 6.1,
            "line_height": 7.4,
        },
        {
            "title": "File Evidence Register",
            "description": "File evidence attached to each deposit slip.",
            "headers": ["Slip title", "File name", "File type", "File size", "Deposited/uploaded by", "Uploaded at"],
            "widths": [24, 30, 18, 14, 24, 17],
            "rows": [
                [
                    slip["title"],
                    slip["original_name"] or "Unknown file",
                    slip["mime_type"] or "Unknown",
                    bits_size(slip["size_bytes"]),
                    slip["created_by_name"] or "Unknown",
                    timestamp(slip["created_at"], "Not recorded"),
                ]
                for slip in slips
            ],
            "font_size": 6.1,
            "line_height": 7.4,
        },
    ]

    log_event("finance_pdf_downloaded", g.user["id"], "report", None, f"{len(slips)}/{len(offerings)}")
    return _pdf_report_response(
        "back-to-god-finance-report.pdf",
        "Back to God AOG City Centre - Finance Report",
        summary_items,
        tables,
        "Deposited by / uploaded by is the user account that uploaded the deposit slip.",
    )


@bp.get("/deposit-slips/<int:slip_id>")
@login_required
def view_slip(slip_id: int):
    slip = get_deposit_slip(slip_id)
    if slip is None:
        abort(404)
    if not can_view_slip(slip, can_manage_finance()):
        abort(404)

    linked_offerings = list_offerings_for_slip(slip_id)
    linked_total_cents = sum(int(item["amount_cents"]) for item in linked_offerings)
    return render_template(
        "finance/slip_view.html",
        slip=slip,
        back_url=_safe_back_url(),
        linked_offerings=linked_offerings,
        linked_total=cents_to_money(linked_total_cents),
        cents_to_money=cents_to_money,
    )


@bp.get("/deposit-slips/<int:slip_id>/file")
@login_required
def slip_file(slip_id: int):
    slip = get_deposit_slip(slip_id)
    if slip is None:
        abort(404)
    if not can_view_slip(slip, can_manage_finance()):
        abort(404)

    headers = {
        "Cache-Control": "no-store, private",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Length": str(slip["size_bytes"]),
        "Content-Disposition": f"inline; filename=\"{slip['original_name']}\"",
    }
    return Response(slip["data"], mimetype=slip["mime_type"], headers=headers)
