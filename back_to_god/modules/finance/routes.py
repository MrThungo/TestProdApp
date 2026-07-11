from __future__ import annotations

import csv
import html
import zipfile
from io import BytesIO, StringIO
from urllib.parse import urlparse

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

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


def _pdf_response(filename: str, lines: list[str]) -> Response:
    text_lines = lines[:42]
    content_lines = ["BT", "/F1 11 Tf", "50 790 Td", "14 TL"]
    for line in text_lines:
        safe = str(line).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"({safe[:96]}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
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
            "Uploaded by",
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
        "Visible now", "Visible from", "Visible until", "Uploaded by", "Approved/revoked by",
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
    slips, offerings = _finance_report_rows()
    lines = [
        "Back to God AOG City Centre - Finance Report",
        f"Generated: {today_date()}",
        f"Deposit slips: {summary['slip_count']} | Deposits: {summary['total_money']}",
        f"Offerings captured: {summary['offering_count']} | Offerings: {summary['offering_money']}",
        "",
        "Recent offerings",
    ]
    for row in offerings[1:16]:
        lines.append(f"{row[0]} | {row[1]} | {row[2]} | Slip: {row[3]}")
    lines.append("")
    lines.append("Recent deposit slips")
    for row in slips[1:16]:
        lines.append(f"{row[4]} | {row[0]} | {row[3]} | {row[5]}")
    log_event("finance_pdf_downloaded", g.user["id"], "report", None, f"{len(slips) - 1}/{len(offerings) - 1}")
    return _pdf_response("back-to-god-finance-report.pdf", lines)


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
