"""PDF (ReportLab) and HTML report generation.

Both formats are produced from the same computed section payloads, so the PDF
and the HTML always contain identical numbers. Charts are rendered with
matplotlib from the real aggregated data.
"""
from __future__ import annotations

import html
import io
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless rendering inside the server process
import matplotlib.pyplot as plt  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0B1224")
BLUE = colors.HexColor("#3B82F6")
VIOLET = colors.HexColor("#8B5CF6")
INK = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#6B7280")
LIGHT = colors.HexColor("#F3F4F6")
BORDER = colors.HexColor("#E5E7EB")

PALETTE = ["#3B82F6", "#8B5CF6", "#06B6D4", "#F59E0B", "#10B981",
           "#EF4444", "#EC4899", "#6366F1"]


# ---------------------------------------------------------------------------
# Chart image rendering
# ---------------------------------------------------------------------------
def render_chart_png(chart: dict[str, Any], width: float = 7.0,
                     height: float = 3.2, dpi: int = 150) -> bytes | None:
    """Render a chart spec (from the EDA service) into PNG bytes."""
    try:
        chart_type = chart.get("chart_type")
        figure, axis = plt.subplots(figsize=(width, height), dpi=dpi)
        figure.patch.set_facecolor("white")
        axis.set_facecolor("white")

        if chart_type in ("histogram", "bar", "grouped_aggregate", "value_counts"):
            data = chart.get("data", [])
            labels = [str(item.get("label", "")) for item in data]
            values = [float(item.get("value") or 0) for item in data]
            if not values:
                plt.close(figure)
                return None
            positions = range(len(values))
            axis.bar(positions, values, color=PALETTE[0], edgecolor="white")
            axis.set_xticks(list(positions))
            axis.set_xticklabels(labels, rotation=45 if len(labels) > 6 else 0,
                                 ha="right" if len(labels) > 6 else "center",
                                 fontsize=7)
            axis.set_ylabel(chart.get("y_label", "Value"), fontsize=8)
            axis.set_xlabel(chart.get("x_label", ""), fontsize=8)
        elif chart_type == "pie":
            data = chart.get("data", [])
            labels = [str(item.get("label", "")) for item in data]
            values = [float(item.get("value") or 0) for item in data]
            if not values or sum(values) == 0:
                plt.close(figure)
                return None
            axis.pie(values, labels=labels, autopct="%1.1f%%",
                     colors=PALETTE, textprops={"fontsize": 7})
            axis.axis("equal")
        elif chart_type == "scatter":
            data = chart.get("data", [])
            xs = [float(item["x"]) for item in data if item.get("x") is not None]
            ys = [float(item["y"]) for item in data if item.get("y") is not None]
            if not xs:
                plt.close(figure)
                return None
            axis.scatter(xs, ys, s=10, alpha=0.55, color=PALETTE[0])
            axis.set_xlabel(chart.get("x_label", ""), fontsize=8)
            axis.set_ylabel(chart.get("y_label", ""), fontsize=8)
        elif chart_type == "line":
            data = chart.get("data", [])
            labels = [str(item.get("label", "")) for item in data]
            values = [float(item.get("value") or 0) for item in data]
            if not values:
                plt.close(figure)
                return None
            axis.plot(range(len(values)), values, marker="o", linewidth=1.8,
                      color=VIOLET if False else PALETTE[1])
            step = max(1, len(labels) // 8)
            axis.set_xticks(list(range(0, len(labels), step)))
            axis.set_xticklabels(labels[::step], rotation=45, ha="right", fontsize=7)
            axis.set_ylabel(chart.get("y_label", "Value"), fontsize=8)
        elif chart_type == "box":
            series = chart.get("series", [])
            if not series:
                plt.close(figure)
                return None
            labels, positions = [], []
            for index, item in enumerate(series[:12]):
                stats = [
                    item.get("min"), item.get("q1"), item.get("median"),
                    item.get("q3"), item.get("max"),
                ]
                if any(v is None for v in stats):
                    continue
                bxp = {
                    "label": str(item.get("label", index)),
                    "whislo": float(stats[0]), "q1": float(stats[1]),
                    "med": float(stats[2]), "q3": float(stats[3]),
                    "whishi": float(stats[4]), "fliers": [],
                }
                labels.append(item.get("label", index))
                positions.append(bxp)
            if not positions:
                plt.close(figure)
                return None
            axis.bxp(positions, showfliers=False, patch_artist=True,
                     boxprops={"facecolor": "#DBEAFE", "edgecolor": PALETTE[0]},
                     medianprops={"color": PALETTE[1], "linewidth": 2})
            axis.set_xticklabels([str(l) for l in labels], rotation=45, ha="right", fontsize=7)
        elif chart_type == "correlation_heatmap":
            columns = chart.get("columns", [])
            matrix = chart.get("matrix", {})
            if not columns:
                plt.close(figure)
                return None
            grid = [[float(matrix.get(r, {}).get(c, 0) or 0) for c in columns] for r in columns]
            image = axis.imshow(grid, cmap="RdBu_r", vmin=-1, vmax=1)
            axis.set_xticks(range(len(columns)))
            axis.set_yticks(range(len(columns)))
            axis.set_xticklabels(columns, rotation=45, ha="right", fontsize=7)
            axis.set_yticklabels(columns, fontsize=7)
            figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
        else:
            plt.close(figure)
            return None

        axis.set_title(chart.get("title", ""), fontsize=9, color="#111827", pad=8)
        axis.tick_params(labelsize=7)
        for spine in ("top", "right"):
            axis.spines[spine].set_visible(False)
        figure.tight_layout()

        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
        plt.close(figure)
        return buffer.getvalue()
    except (ValueError, TypeError, KeyError, RuntimeError):
        plt.close("all")
        return None


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DPTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=22, leading=26, textColor=NAVY, alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "DPSubtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, leading=13, textColor=MUTED, spaceAfter=12,
        ),
        "h1": ParagraphStyle(
            "DPH1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=13.5, leading=17, textColor=NAVY, spaceBefore=14,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "DPH2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=10.5, leading=14, textColor=BLUE, spaceBefore=8, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "DPBody", parent=base["Normal"], fontName="Helvetica", fontSize=8.8,
            leading=12.5, textColor=INK, spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "DPSmall", parent=base["Normal"], fontName="Helvetica", fontSize=7.6,
            leading=10.5, textColor=MUTED,
        ),
        "bullet": ParagraphStyle(
            "DPBullet", parent=base["Normal"], fontName="Helvetica", fontSize=8.8,
            leading=12.5, textColor=INK, leftIndent=10, bulletIndent=2, spaceAfter=2,
        ),
        "mono": ParagraphStyle(
            "DPMono", parent=base["Normal"], fontName="Courier", fontSize=7.6,
            leading=10, textColor=INK,
        ),
    }


def _table(rows: list[list[str]], widths: list[float] | None = None,
           header: bool = True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.4),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
        for row_index in range(1, len(rows)):
            if row_index % 2 == 0:
                style.append(("BACKGROUND", (0, row_index), (-1, row_index), LIGHT))
    table.setStyle(TableStyle(style))
    return table


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return f"{int(value):,}"
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return str(value)


def build_pdf(sections: dict[str, Any], output_path: str | Path) -> Path:
    """Render the report sections into a PDF file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()

    document = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=sections.get("title", "DataPilot Report"),
        author="DataPilot",
    )
    story: list[Any] = []

    # --- Cover header ---
    story.append(Paragraph(sections.get("title", "DataPilot Analysis Report"), styles["title"]))
    meta_bits = [
        f"Dataset: <b>{html.escape(str(sections.get('dataset_name', 'n/a')))}</b>",
        f"Project: {html.escape(str(sections.get('project_name', 'n/a')))}",
        f"Generated: {sections.get('generated_at', datetime.utcnow().isoformat())}",
        f"Row count: {_fmt(sections.get('overview', {}).get('rows'))}",
    ]
    story.append(Paragraph(" &nbsp;•&nbsp; ".join(meta_bits), styles["subtitle"]))

    # --- Quality summary strip ---
    quality = sections.get("quality") or {}
    if quality:
        components = quality.get("components", {})
        strip = [[
            Paragraph("<b>Quality score</b>", styles["small"]),
            Paragraph("<b>Grade</b>", styles["small"]),
            Paragraph("<b>Completeness</b>", styles["small"]),
            Paragraph("<b>Uniqueness</b>", styles["small"]),
            Paragraph("<b>Validity</b>", styles["small"]),
            Paragraph("<b>Outlier health</b>", styles["small"]),
        ], [
            Paragraph(f"<b>{_fmt(quality.get('score'))}/100</b>", styles["body"]),
            Paragraph(f"<b>{quality.get('grade', '—')}</b>", styles["body"]),
            Paragraph(_fmt(components.get("completeness")), styles["body"]),
            Paragraph(_fmt(components.get("uniqueness")), styles["body"]),
            Paragraph(_fmt(components.get("validity")), styles["body"]),
            Paragraph(_fmt(components.get("outlier_health")), styles["body"]),
        ]]
        summary_table = Table(strip, colWidths=[30 * mm] * 6)
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "Scoring methodology: " + html.escape(str(quality.get("methodology", ""))),
            styles["small"],
        ))

    # --- Overview ---
    overview = sections.get("overview") or {}
    if overview:
        story.append(Paragraph("1. Dataset Overview", styles["h1"]))
        rows = [
            ["Metric", "Value"],
            ["Rows", _fmt(overview.get("rows"))],
            ["Columns", _fmt(overview.get("columns"))],
            ["Source format", _fmt(overview.get("source_format"))],
            ["Original filename", _fmt(overview.get("original_filename"))],
            ["File size", _fmt(overview.get("file_size_human"))],
            ["Current version", _fmt(overview.get("version_label"))],
            ["Numeric columns", _fmt(overview.get("numeric_count"))],
            ["Categorical columns", _fmt(overview.get("categorical_count"))],
            ["Datetime columns", _fmt(overview.get("datetime_count"))],
            ["Missing cells", _fmt(overview.get("missing_cells"))],
            ["Duplicate rows", _fmt(overview.get("duplicate_rows"))],
        ]
        story.append(_table(rows, widths=[60 * mm, 110 * mm]))

    # --- Key findings ---
    findings = sections.get("findings") or []
    if findings:
        story.append(Paragraph("2. Key Findings", styles["h1"]))
        for finding in findings:
            story.append(Paragraph(
                f"•&nbsp;{html.escape(str(finding))}", styles["bullet"]
            ))

    # --- Column profile ---
    profile_rows = sections.get("column_profile") or []
    if profile_rows:
        story.append(Paragraph("3. Column Profile", styles["h1"]))
        rows = [["Column", "Type", "Non-null", "Missing", "Missing %", "Unique"]]
        for column in profile_rows[:60]:
            rows.append([
                str(column.get("name")),
                str(column.get("kind")),
                _fmt(column.get("non_null")),
                _fmt(column.get("missing")),
                f"{_fmt(column.get('missing_pct'))}%",
                _fmt(column.get("unique")),
            ])
        story.append(_table(rows, widths=[42 * mm, 24 * mm, 24 * mm, 22 * mm, 26 * mm, 26 * mm]))

    # --- Descriptive statistics ---
    stats_rows = sections.get("descriptive_statistics") or []
    if stats_rows:
        story.append(Paragraph("4. Descriptive Statistics", styles["h1"]))
        rows = [["Column", "N", "Mean", "Median", "Std Dev", "Min", "Max", "Skew"]]
        for row in stats_rows:
            rows.append([
                str(row.get("column")),
                _fmt(row.get("n")),
                _fmt(row.get("mean")),
                _fmt(row.get("median")),
                _fmt(row.get("std")),
                _fmt(row.get("min")),
                _fmt(row.get("max")),
                _fmt(row.get("skewness")),
            ])
        story.append(_table(rows, widths=[34 * mm, 14 * mm, 22 * mm, 22 * mm, 22 * mm, 20 * mm, 20 * mm, 20 * mm]))
        story.append(Paragraph(
            "Standard deviation uses the sample estimator (ddof=1). "
            "Skewness of 0 indicates symmetry; |skew| > 1 indicates strong asymmetry.",
            styles["small"],
        ))

    # --- Cleaning history ---
    cleaning = sections.get("cleaning_history") or []
    if cleaning:
        story.append(Paragraph("5. Cleaning History", styles["h1"]))
        rows = [["Operation", "Column", "Affected", "Summary"]]
        for action in cleaning:
            rows.append([
                str(action.get("operation")),
                str(action.get("column") or "—"),
                _fmt(action.get("affected")),
                Paragraph(html.escape(str(action.get("detail", ""))[:220]), styles["small"]),
            ])
        story.append(_table(rows, widths=[30 * mm, 24 * mm, 18 * mm, 98 * mm]))
        before = sections.get("cleaning_before") or {}
        after = sections.get("cleaning_after") or {}
        if before and after:
            story.append(Spacer(1, 4))
            rows = [
                ["Metric", "Before cleaning", "After cleaning"],
                ["Rows", _fmt(before.get("rows")), _fmt(after.get("rows"))],
                ["Columns", _fmt(before.get("columns")), _fmt(after.get("columns"))],
                ["Missing cells", _fmt(before.get("missing_cells")), _fmt(after.get("missing_cells"))],
                ["Duplicate rows", _fmt(before.get("duplicate_rows")), _fmt(after.get("duplicate_rows"))],
                ["Quality score", _fmt(before.get("quality_score")), _fmt(after.get("quality_score"))],
            ]
            story.append(_table(rows, widths=[60 * mm, 55 * mm, 55 * mm]))

    # --- Statistical analysis ---
    analyses = sections.get("statistical_analyses") or []
    if analyses:
        story.append(PageBreak())
        story.append(Paragraph("6. Statistical Analysis", styles["h1"]))
        for analysis in analyses:
            block: list[Any] = [
                Paragraph(html.escape(str(analysis.get("label", "Analysis"))), styles["h2"]),
                Paragraph(html.escape(str(analysis.get("interpretation", ""))), styles["body"]),
            ]
            details = analysis.get("details") or []
            if details:
                rows = [["Measure", "Value"]] + [
                    [str(k), _fmt(v)] for k, v in details
                ]
                block.append(_table(rows, widths=[70 * mm, 100 * mm]))
            assumptions = analysis.get("assumptions") or []
            if assumptions:
                block.append(Paragraph("<b>Assumptions</b>", styles["small"]))
                for item in assumptions:
                    block.append(Paragraph(f"•&nbsp;{html.escape(str(item))}", styles["bullet"]))
            limitations = analysis.get("limitations") or []
            if limitations:
                block.append(Paragraph("<b>Limitations</b>", styles["small"]))
                for item in limitations:
                    block.append(Paragraph(f"•&nbsp;{html.escape(str(item))}", styles["bullet"]))
            block.append(Spacer(1, 6))
            story.append(KeepTogether(block))

    # --- Charts ---
    charts = sections.get("charts") or []
    if charts:
        story.append(PageBreak())
        story.append(Paragraph("7. Visual Analysis", styles["h1"]))
        for index, chart in enumerate(charts):
            png = render_chart_png(chart)
            if not png:
                continue
            story.append(Paragraph(html.escape(str(chart.get("title", "Chart"))), styles["h2"]))
            story.append(Image(io.BytesIO(png), width=165 * mm, height=76 * mm))
            note = chart.get("note")
            if note:
                story.append(Paragraph(html.escape(str(note)), styles["small"]))
            story.append(Spacer(1, 6))

    # --- NL conversation ---
    conversation = sections.get("conversation") or []
    if conversation:
        story.append(PageBreak())
        story.append(Paragraph("8. Natural Language Analysis", styles["h1"]))
        story.append(Paragraph(
            "Questions answered by the analytics engine. Each answer states which "
            "engine produced it; all numbers were computed from the dataset.",
            styles["small"],
        ))
        story.append(Spacer(1, 4))
        for message in conversation:
            role = message.get("role")
            if role == "user":
                story.append(Paragraph(
                    f"<b>Q:</b> {html.escape(str(message.get('content', '')))}",
                    styles["body"],
                ))
            else:
                engine = message.get("engine_label") or message.get("engine", "")
                story.append(Paragraph(
                    f"<b>A</b> <font color='#6B7280' size='7'>[{html.escape(str(engine))}]</font>: "
                    + html.escape(str(message.get("content", ""))),
                    styles["body"],
                ))
            story.append(Spacer(1, 3))

    # --- Limitations ---
    story.append(Paragraph("9. Limitations", styles["h1"]))
    default_limitations = [
        "Results describe the uploaded sample only and do not establish causation.",
        "Statistical tests assume independent observations; repeated measurements "
        "violate this and require different methods.",
        "Automated type detection is heuristic. Verify column types before relying "
        "on aggregate figures.",
        "Missing values were excluded or imputed according to the recorded cleaning "
        "plan; different handling can change the results.",
        "Charts display sampled points where datasets are very large, so visual "
        "density near the edges may be approximate.",
    ]
    for item in (sections.get("limitations") or default_limitations):
        story.append(Paragraph(f"•&nbsp;{html.escape(str(item))}", styles["bullet"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Report generated by DataPilot v{sections.get('app_version', '1.0.0')} on "
        f"{sections.get('generated_at', '')}. All statistics computed with "
        "pandas/NumPy/SciPy from the uploaded dataset.",
        styles["small"],
    ))

    document.build(story)
    return output_path


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
_HTML_CSS = """
:root{--navy:#0B1224;--blue:#3B82F6;--violet:#8B5CF6;--ink:#1F2937;
--muted:#6B7280;--line:#E5E7EB;--bg:#F8FAFC;}
*{box-sizing:border-box;}
body{margin:0;padding:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
font-size:14px;line-height:1.6;}
.wrap{max-width:1000px;margin:0 auto;padding:40px 28px 80px;}
header{background:linear-gradient(135deg,var(--navy) 0%,#16213E 60%,#1E2A4A 100%);
color:#fff;padding:36px 40px;border-radius:16px;margin-bottom:32px;}
header h1{margin:0 0 8px;font-size:27px;letter-spacing:-.5px;}
header .meta{color:#94A3B8;font-size:12.5px;}
header .meta b{color:#E2E8F0;font-weight:600;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:14px;margin-bottom:8px;}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;
padding:16px 18px;}
.card .k{font-size:11px;text-transform:uppercase;letter-spacing:.6px;
color:var(--muted);font-weight:600;}
.card .v{font-size:24px;font-weight:700;color:var(--navy);margin-top:4px;
font-variant-numeric:tabular-nums;}
.card .s{font-size:11.5px;color:var(--muted);}
section{background:#fff;border:1px solid var(--line);border-radius:14px;
padding:26px 28px;margin-bottom:22px;}
section>h2{margin:0 0 16px;font-size:16px;color:var(--navy);
letter-spacing:-.2px;padding-bottom:10px;border-bottom:2px solid var(--line);}
h3{font-size:13.5px;color:var(--blue);margin:20px 0 8px;}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0;}
th{background:var(--navy);color:#fff;text-align:left;padding:9px 11px;
font-weight:600;font-size:11.5px;letter-spacing:.3px;}
td{padding:8px 11px;border-bottom:1px solid var(--line);
font-variant-numeric:tabular-nums;}
tr:nth-child(even) td{background:#FAFBFC;}
ul{margin:8px 0;padding-left:20px;}
li{margin-bottom:6px;}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;
font-weight:600;}
.pill.llm{background:#EDE9FE;color:#6D28D9;}
.pill.rule{background:#DBEAFE;color:#1D4ED8;}
.q{background:#F1F5F9;border-left:3px solid var(--blue);padding:10px 14px;
border-radius:0 8px 8px 0;margin:12px 0 6px;font-weight:600;}
.a{margin:0 0 14px;padding-left:14px;color:#334155;}
.note{font-size:12px;color:var(--muted);font-style:italic;margin-top:6px;}
.chart{margin:18px 0;}
.chart img{max-width:100%;border:1px solid var(--line);border-radius:10px;}
.quality-bar{display:flex;height:10px;border-radius:999px;overflow:hidden;
margin:10px 0 6px;background:var(--line);}
.quality-bar span{display:block;height:100%;}
footer{text-align:center;color:var(--muted);font-size:11.5px;padding:24px 0;}
"""


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _hfmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return f"{int(value):,}"
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return _e(value)


def build_html(sections: dict[str, Any]) -> str:
    """Render the report sections into a standalone HTML document."""
    quality = sections.get("quality") or {}
    overview = sections.get("overview") or {}
    parts: list[str] = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>{_e(sections.get('title', 'DataPilot Report'))}</title>",
        f"<style>{_HTML_CSS}</style></head><body><div class='wrap'>",
    ]

    parts.append(
        "<header>"
        f"<h1>{_e(sections.get('title', 'DataPilot Analysis Report'))}</h1>"
        f"<div class='meta'>Dataset: <b>{_e(sections.get('dataset_name', 'n/a'))}</b>"
        f" &nbsp;•&nbsp; Project: {_e(sections.get('project_name', 'n/a'))}"
        f" &nbsp;•&nbsp; Rows: <b>{_hfmt(overview.get('rows'))}</b>"
        f" &nbsp;•&nbsp; Columns: <b>{_hfmt(overview.get('columns'))}</b>"
        f" &nbsp;•&nbsp; Generated: {_e(sections.get('generated_at', ''))}"
        "</div></header>"
    )

    # KPI cards
    cards = [
        ("Quality score", f"{_hfmt(quality.get('score'))}/100",
         f"Grade {quality.get('grade', '—')}"),
        ("Rows", _hfmt(overview.get("rows")), "current version"),
        ("Columns", _hfmt(overview.get("columns")),
         f"{_hfmt(overview.get('numeric_count'))} numeric"),
        ("Missing cells", _hfmt(overview.get("missing_cells")),
         f"{_hfmt(quality.get('counts', {}).get('missing_cells'))} detected"),
        ("Duplicate rows", _hfmt(overview.get("duplicate_rows")), "exact duplicates"),
    ]
    parts.append("<div class='grid'>")
    for label, value, sub in cards:
        parts.append(
            f"<div class='card'><div class='k'>{_e(label)}</div>"
            f"<div class='v'>{value}</div><div class='s'>{_e(sub)}</div></div>"
        )
    parts.append("</div>")

    # Findings
    findings = sections.get("findings") or []
    if findings:
        parts.append("<section><h2>Key Findings</h2><ul>")
        for finding in findings:
            parts.append(f"<li>{_e(finding)}</li>")
        parts.append("</ul></section>")

    # Quality components
    if quality:
        components = quality.get("components", {})
        weights = quality.get("weights", {})
        parts.append("<section><h2>Data Quality Breakdown</h2><table>")
        parts.append("<tr><th>Component</th><th>Score</th><th>Weight</th></tr>")
        for name, score in components.items():
            parts.append(
                f"<tr><td>{_e(name.replace('_', ' ').title())}</td>"
                f"<td>{_hfmt(score)}</td>"
                f"<td>{_hfmt(round(weights.get(name, 0) * 100, 1))}%</td></tr>"
            )
        parts.append("</tbody></table>")
        parts.append(f"<p class='note'>{_e(quality.get('methodology', ''))}</p>")
        issues = quality.get("issues") or []
        if issues:
            parts.append("<h3>Detected issues</h3><ul>")
            for issue in issues:
                parts.append(f"<li>{_e(issue)}</li>")
            parts.append("</ul>")
        parts.append("</section>")

    # Column profile
    profile_rows = sections.get("column_profile") or []
    if profile_rows:
        parts.append("<section><h2>Column Profile</h2><table>")
        parts.append("<tr><th>Column</th><th>Type</th><th>Non-null</th>"
                     "<th>Missing</th><th>Missing %</th><th>Unique</th></tr>")
        for column in profile_rows:
            parts.append(
                f"<tr><td>{_e(column.get('name'))}</td>"
                f"<td>{_e(column.get('kind'))}</td>"
                f"<td>{_hfmt(column.get('non_null'))}</td>"
                f"<td>{_hfmt(column.get('missing'))}</td>"
                f"<td>{_hfmt(column.get('missing_pct'))}%</td>"
                f"<td>{_hfmt(column.get('unique'))}</td></tr>"
            )
        parts.append("</table></section>")

    # Descriptive stats
    stats_rows = sections.get("descriptive_statistics") or []
    if stats_rows:
        parts.append("<section><h2>Descriptive Statistics</h2><table>")
        parts.append("<tr><th>Column</th><th>N</th><th>Mean</th><th>Median</th>"
                     "<th>Std Dev</th><th>Min</th><th>Max</th><th>Skew</th></tr>")
        for row in stats_rows:
            parts.append(
                f"<tr><td>{_e(row.get('column'))}</td>"
                f"<td>{_hfmt(row.get('n'))}</td>"
                f"<td>{_hfmt(row.get('mean'))}</td>"
                f"<td>{_hfmt(row.get('median'))}</td>"
                f"<td>{_hfmt(row.get('std'))}</td>"
                f"<td>{_hfmt(row.get('min'))}</td>"
                f"<td>{_hfmt(row.get('max'))}</td>"
                f"<td>{_hfmt(row.get('skewness'))}</td></tr>"
            )
        parts.append("</table><p class='note'>Standard deviation uses the sample "
                     "estimator (ddof=1).</p></section>")

    # Cleaning
    cleaning = sections.get("cleaning_history") or []
    if cleaning:
        parts.append("<section><h2>Cleaning History</h2><table>")
        parts.append("<tr><th>Operation</th><th>Column</th><th>Affected</th><th>Detail</th></tr>")
        for action in cleaning:
            parts.append(
                f"<tr><td>{_e(action.get('operation'))}</td>"
                f"<td>{_e(action.get('column') or '—')}</td>"
                f"<td>{_hfmt(action.get('affected'))}</td>"
                f"<td>{_e(action.get('detail'))}</td></tr>"
            )
        parts.append("</table>")
        before, after = sections.get("cleaning_before"), sections.get("cleaning_after")
        if before and after:
            parts.append("<h3>Before vs after</h3><table>")
            parts.append("<tr><th>Metric</th><th>Before</th><th>After</th></tr>")
            for key, label in (("rows", "Rows"), ("columns", "Columns"),
                               ("missing_cells", "Missing cells"),
                               ("duplicate_rows", "Duplicate rows"),
                               ("quality_score", "Quality score")):
                parts.append(
                    f"<tr><td>{label}</td><td>{_hfmt(before.get(key))}</td>"
                    f"<td>{_hfmt(after.get(key))}</td></tr>"
                )
            parts.append("</table>")
        parts.append("</section>")

    # Statistical analyses
    analyses = sections.get("statistical_analyses") or []
    if analyses:
        parts.append("<section><h2>Statistical Analysis</h2>")
        for analysis in analyses:
            parts.append(f"<h3>{_e(analysis.get('label', 'Analysis'))}</h3>")
            parts.append(f"<p>{_e(analysis.get('interpretation', ''))}</p>")
            details = analysis.get("details") or []
            if details:
                parts.append("<table><tr><th>Measure</th><th>Value</th></tr>")
                for key, value in details:
                    parts.append(f"<tr><td>{_e(key)}</td><td>{_hfmt(value)}</td></tr>")
                parts.append("</table>")
            for heading, key in (("Assumptions", "assumptions"),
                                 ("Limitations", "limitations")):
                items = analysis.get(key) or []
                if items:
                    parts.append(f"<h3>{heading}</h3><ul>")
                    for item in items:
                        parts.append(f"<li>{_e(item)}</li>")
                    parts.append("</ul>")
        parts.append("</section>")

    # Charts
    charts = sections.get("charts") or []
    if charts:
        parts.append("<section><h2>Visual Analysis</h2>")
        for chart in charts:
            png = render_chart_png(chart)
            if not png:
                continue
            import base64

            encoded = base64.b64encode(png).decode("ascii")
            parts.append(f"<div class='chart'><h3>{_e(chart.get('title', 'Chart'))}</h3>")
            parts.append(
                f"<img alt='{_e(chart.get('title', 'chart'))}' "
                f"src='data:image/png;base64,{encoded}'>"
            )
            if chart.get("note"):
                parts.append(f"<p class='note'>{_e(chart['note'])}</p>")
            parts.append("</div>")
        parts.append("</section>")

    # Conversation
    conversation = sections.get("conversation") or []
    if conversation:
        parts.append("<section><h2>Natural Language Analysis</h2>")
        for message in conversation:
            if message.get("role") == "user":
                parts.append(f"<div class='q'>Q: {_e(message.get('content', ''))}</div>")
            else:
                engine = str(message.get("engine", "rule_based"))
                css = "llm" if engine == "llm" else "rule"
                label = _e(message.get("engine_label", engine))
                parts.append(
                    f"<div class='a'><span class='pill {css}'>{label}</span> "
                    f"{_e(message.get('content', ''))}</div>"
                )
        parts.append("</section>")

    # Limitations
    limitations = sections.get("limitations") or [
        "Results describe the uploaded sample only and do not establish causation.",
        "Statistical tests assume independent observations.",
        "Automated type detection is heuristic; verify column types.",
        "Missing values were handled per the recorded cleaning plan.",
    ]
    parts.append("<section><h2>Limitations</h2><ul>")
    for item in limitations:
        parts.append(f"<li>{_e(item)}</li>")
    parts.append("</ul></section>")

    parts.append(
        f"<footer>Generated by DataPilot v{_e(sections.get('app_version', '1.0.0'))} "
        f"on {_e(sections.get('generated_at', ''))} &nbsp;•&nbsp; "
        "All statistics computed with pandas / NumPy / SciPy from the uploaded dataset."
        "</footer></div></body></html>"
    )
    return "".join(parts)
