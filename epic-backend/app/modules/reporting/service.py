"""Aggregation queries for dashboards and management reporting, plus Excel/PDF export."""
import io
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..tickets.models import Ticket, PRIORITIES
from ...core.sla import SLA_HOURS_BY_PRIORITY, AT_RISK_THRESHOLD

OPEN_STATES = ("OPEN", "ASSIGNED", "IN_PROGRESS", "PENDING_USER")
TREND_DAYS = 14


def _sla_breakdown(db: Session, now: datetime | None = None):
    """Single pass over (priority, created_at, resolved_at, closed_at, sla_due_at) to derive
    SLA compliance, breach, and at-risk counts without pulling full Ticket rows."""
    now = now or datetime.utcnow()
    rows = db.query(
        Ticket.priority, Ticket.created_at, Ticket.resolved_at, Ticket.closed_at, Ticket.sla_due_at
    ).all()

    met = breached = at_risk = on_track = no_sla = 0
    resolved_count = 0
    total_resolution_seconds = 0.0
    by_priority_resolution = {p: {"count": 0, "seconds": 0.0} for p in PRIORITIES}

    for priority, created_at, resolved_at, closed_at, sla_due_at in rows:
        end = resolved_at or closed_at
        if end is not None:
            resolved_count += 1
            seconds = (end - created_at).total_seconds()
            total_resolution_seconds += seconds
            if priority in by_priority_resolution:
                by_priority_resolution[priority]["count"] += 1
                by_priority_resolution[priority]["seconds"] += seconds

        if sla_due_at is None:
            no_sla += 1
            continue
        if end is not None:
            if end <= sla_due_at:
                met += 1
            else:
                breached += 1
            continue
        if now > sla_due_at:
            breached += 1
            continue
        window = (sla_due_at - created_at).total_seconds()
        remaining = (sla_due_at - now).total_seconds()
        if window > 0 and (remaining / window) <= AT_RISK_THRESHOLD:
            at_risk += 1
        else:
            on_track += 1

    evaluated = met + breached
    compliance_rate = round((met / evaluated) * 100, 1) if evaluated else None
    avg_resolution_hours = (
        round((total_resolution_seconds / resolved_count) / 3600, 1) if resolved_count else None
    )
    avg_resolution_by_priority = {
        p: (round((v["seconds"] / v["count"]) / 3600, 1) if v["count"] else None)
        for p, v in by_priority_resolution.items()
    }

    return {
        "compliance_rate": compliance_rate,
        "met": met,
        "breached": breached,
        "at_risk": at_risk,
        "on_track": on_track,
        "no_sla_target": no_sla,
        "avg_resolution_hours": avg_resolution_hours,
        "avg_resolution_hours_by_priority": avg_resolution_by_priority,
        "target_hours_by_priority": SLA_HOURS_BY_PRIORITY,
    }


def _trend(db: Session, days: int = TREND_DAYS, now: datetime | None = None):
    now = now or datetime.utcnow()
    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(func.date(Ticket.created_at), func.count(Ticket.id))
        .filter(Ticket.created_at >= since)
        .group_by(func.date(Ticket.created_at))
        .all()
    )
    counts = {str(d): c for d, c in rows}
    out = []
    for i in range(days):
        day = (since + timedelta(days=i)).date()
        out.append({"date": day.isoformat(), "count": counts.get(day.isoformat(), 0)})
    return out


def overview(db: Session):
    by_status = dict(db.query(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status).all())
    by_ticket_type = dict(db.query(Ticket.ticket_type, func.count(Ticket.id)).group_by(Ticket.ticket_type).all())
    by_category = dict(db.query(Ticket.category, func.count(Ticket.id)).group_by(Ticket.category).all())
    by_priority = dict(db.query(Ticket.priority, func.count(Ticket.id)).group_by(Ticket.priority).all())
    total = db.query(func.count(Ticket.id)).scalar() or 0
    open_total = db.query(func.count(Ticket.id)).filter(Ticket.status.in_(OPEN_STATES)).scalar() or 0
    return {
        "total_tickets": total,
        "open_tickets": open_total,
        "by_status": by_status,
        "by_ticket_type": by_ticket_type,
        "by_category": by_category,
        "by_priority": by_priority,
        "sla": _sla_breakdown(db),
        "trend": _trend(db),
    }


def engineer_workload(db: Session, engineer_id: str):
    rows = (db.query(Ticket.status, func.count(Ticket.id))
              .filter(Ticket.assignee_id == engineer_id)
              .group_by(Ticket.status).all())
    return {
        "engineer_id": engineer_id,
        "by_status": dict(rows),
        "active": sum(c for s, c in rows if s in ("ASSIGNED", "IN_PROGRESS", "PENDING_USER")),
    }


def report_group(db: Session, group_by: str, from_dt=None, to_dt=None):
    col_map = {"status": Ticket.status, "ticket_type": Ticket.ticket_type, "category": Ticket.category, "priority": Ticket.priority}
    col = col_map.get(group_by)
    if col is None:
        raise ValueError(f"group_by must be one of {list(col_map)}")
    q = db.query(col, func.count(Ticket.id)).group_by(col)
    if from_dt:
        q = q.filter(Ticket.created_at >= from_dt)
    if to_dt:
        q = q.filter(Ticket.created_at <= to_dt)
    return [{"key": k, "count": v} for k, v in q.all()]


# ---------- Export ----------

def _label(key: str) -> str:
    return str(key).replace("_", " ").title()


def build_excel_export(db: Session) -> bytes:
    """Builds an .xlsx workbook (Summary / By Status / By Priority / By Category /
    By Type / SLA / Trend sheets) from the same overview() data the dashboard shows."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    data = overview(db)
    wb = Workbook()

    header_fill = PatternFill(start_color="0067B8", end_color="0067B8", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    title_font = Font(size=14, bold=True, color="0067B8")

    def style_header_row(ws, row_idx=1, ncols=2):
        for col in range(1, ncols + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="left")

    def autosize(ws, widths):
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w

    # --- Summary ---
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "EPIC Admin Dashboard — Summary"
    ws["A1"].font = title_font
    ws["A2"] = f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
    ws["A2"].font = Font(italic=True, color="57606A")

    ws.append([])
    ws.append(["Metric", "Value"])
    style_header_row(ws, row_idx=4)
    sla = data["sla"]
    summary_rows = [
        ("Total tickets", data["total_tickets"]),
        ("Open tickets", data["open_tickets"]),
        ("SLA compliance rate (%)", sla["compliance_rate"]),
        ("SLA breached", sla["breached"]),
        ("SLA at risk", sla["at_risk"]),
        ("SLA on track", sla["on_track"]),
        ("Avg. resolution time (hours)", sla["avg_resolution_hours"]),
    ]
    for label, value in summary_rows:
        ws.append([label, value])
    autosize(ws, [32, 18])

    # --- Generic breakdown sheet helper ---
    def add_breakdown_sheet(name, mapping):
        s = wb.create_sheet(name)
        s.append([name.replace("By ", ""), "Count"])
        style_header_row(s)
        for k, v in mapping.items():
            s.append([_label(k), v])
        autosize(s, [26, 12])

    add_breakdown_sheet("By Status", data["by_status"])
    add_breakdown_sheet("By Priority", data["by_priority"])
    add_breakdown_sheet("By Category", data["by_category"])
    add_breakdown_sheet("By Type", data["by_ticket_type"])

    # --- SLA sheet ---
    sla_ws = wb.create_sheet("SLA")
    sla_ws.append(["SLA metric", "Value"])
    style_header_row(sla_ws)
    for label, value in [
        ("Compliance rate (%)", sla["compliance_rate"]),
        ("Met", sla["met"]),
        ("Breached", sla["breached"]),
        ("At risk", sla["at_risk"]),
        ("On track", sla["on_track"]),
        ("No SLA target", sla["no_sla_target"]),
        ("Avg. resolution (hours)", sla["avg_resolution_hours"]),
    ]:
        sla_ws.append([label, value])
    sla_ws.append([])
    sla_ws.append(["Target (hours) by priority", ""])
    for p, h in sla["target_hours_by_priority"].items():
        sla_ws.append([_label(p), h])
    sla_ws.append([])
    sla_ws.append(["Avg. resolution (hours) by priority", ""])
    for p, h in sla["avg_resolution_hours_by_priority"].items():
        sla_ws.append([_label(p), h])
    autosize(sla_ws, [32, 14])

    # --- Trend sheet ---
    trend_ws = wb.create_sheet("Ticket Trend")
    trend_ws.append(["Date", "Tickets created"])
    style_header_row(trend_ws)
    for point in data["trend"]:
        trend_ws.append([point["date"], point["count"]])
    autosize(trend_ws, [16, 16])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_pdf_export(db: Session) -> bytes:
    """Builds a print-friendly PDF summary of the dashboard (KPIs, SLA, breakdown tables)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    data = overview(db)
    sla = data["sla"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    brand = colors.HexColor("#0067B8")
    muted = colors.HexColor("#57606A")

    title_style = ParagraphStyle("TitleBrand", parent=styles["Title"], textColor=brand, fontSize=20)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], textColor=brand, spaceBefore=14, spaceAfter=6)
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], textColor=muted)

    story = [
        Paragraph("EPIC Admin Dashboard Report", title_style),
        Paragraph(f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC", meta_style),
        Spacer(1, 12),
    ]

    def make_table(rows, col_widths=(3 * inch, 2 * inch)):
        t = Table(rows, colWidths=list(col_widths))
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), brand),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F6F8")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E1E4E8")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    story.append(Paragraph("Key metrics", section_style))
    story.append(make_table([
        ["Metric", "Value"],
        ["Total tickets", str(data["total_tickets"])],
        ["Open tickets", str(data["open_tickets"])],
        ["SLA compliance rate", f"{sla['compliance_rate']}%" if sla["compliance_rate"] is not None else "—"],
        ["Avg. resolution time", f"{sla['avg_resolution_hours']} hrs" if sla["avg_resolution_hours"] is not None else "—"],
    ]))

    story.append(Paragraph("SLA status", section_style))
    story.append(make_table([
        ["SLA status", "Tickets"],
        ["Met", str(sla["met"])],
        ["Breached", str(sla["breached"])],
        ["At risk", str(sla["at_risk"])],
        ["On track", str(sla["on_track"])],
        ["No SLA target", str(sla["no_sla_target"])],
    ]))

    for title, mapping in [
        ("Tickets by status", data["by_status"]),
        ("Tickets by priority", data["by_priority"]),
        ("Tickets by category", data["by_category"]),
        ("Tickets by type", data["by_ticket_type"]),
    ]:
        story.append(Paragraph(title, section_style))
        rows = [["Value", "Count"]] + [[_label(k), str(v)] for k, v in mapping.items()]
        story.append(make_table(rows))

    doc.build(story)
    return buf.getvalue()