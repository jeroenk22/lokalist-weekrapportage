"""Bouwt het 'Jaaroverzicht De Lokalist' PDF.

Gegroepeerd per week (met weeknummer + datumperiode), binnen elke week
per dag. Per week een subtotaal Laden/Lossen; onderaan een eindtotaal.

Gebruik:
    from genereer_jaaroverzicht_pdf import genereer_jaaroverzicht
    pdf_path, totals = genereer_jaaroverzicht(
        rows=rows,
        periode_omschrijving="week 1 t/m 24, 2026",
        output_path="/pad/naar/jaaroverzicht.pdf",
    )

Rij-vorm: zelfde 11 velden als genereer_rapport.genereer_pdf.
"""

import os
from collections import defaultdict
from datetime import date, datetime, timedelta

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as RLImage,
)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(_SCRIPT_DIR, "..", "src", "lokalist_weekrapportage")
LOGO_MIEDEMA = os.path.join(ASSET_DIR, "logo_miedema.png")
LOGO_LOKALIST = os.path.join(ASSET_DIR, "logo_lokalist.png")

MIEDEMA_ASPECT = 1985 / 457
LOKALIST_ASPECT = 713 / 116

DAGNAMEN_NL = {
    0: "Maandag",
    1: "Dinsdag",
    2: "Woensdag",
    3: "Donderdag",
    4: "Vrijdag",
    5: "Zaterdag",
    6: "Zondag",
}
MAANDNAMEN_NL = {
    1: "januari",
    2: "februari",
    3: "maart",
    4: "april",
    5: "mei",
    6: "juni",
    7: "juli",
    8: "augustus",
    9: "september",
    10: "oktober",
    11: "november",
    12: "december",
}

MIEDEMA_GROEN = colors.HexColor("#004530")
MIEDEMA_GEEL = colors.HexColor("#FADC01")
INKT = colors.HexColor("#1c2630")
GRIJS_TEKST = colors.HexColor("#5b6470")
GRIJS_LIJN = colors.HexColor("#dcdfe3")
GRIJS_BAND = colors.HexColor("#f3f4f6")
LADEN_KLEUR = colors.HexColor("#B8860B")
LOSSEN_KLEUR = MIEDEMA_GROEN
WEEK_KLEUR = colors.HexColor("#2c3e50")

PAGE_WIDTH_MM = 180
COL_WIDTHS_MM = [40.5, 23.5, 47, 13.5, 21.5, 34]

styles = getSampleStyleSheet()
title_style = ParagraphStyle(
    "TitleCustom",
    parent=styles["Title"],
    fontName="Helvetica-Bold",
    fontSize=20,
    leading=24,
    textColor=INKT,
    spaceAfter=3,
    alignment=TA_LEFT,
)
subtitle_style = ParagraphStyle(
    "SubtitleCustom",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=9.5,
    leading=13,
    textColor=GRIJS_TEKST,
    spaceAfter=0,
)
section_style = ParagraphStyle(
    "SectionHeader",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=12.5,
    leading=14,
    textColor=colors.white,
    spaceAfter=0,
    spaceBefore=0,
)
week_section_style = ParagraphStyle(
    "WeekHeader",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=13,
    textColor=colors.white,
    spaceAfter=0,
    spaceBefore=0,
)
cell_style = ParagraphStyle(
    "Cell",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=8.3,
    leading=10.4,
    textColor=INKT,
)
cell_style_lo = ParagraphStyle(
    "CellLo", parent=cell_style, fontSize=7, textColor=GRIJS_TEKST, leading=8.6
)
cell_style_r = ParagraphStyle("CellR", parent=cell_style, alignment=TA_RIGHT)
cell_style_c = ParagraphStyle("CellC", parent=cell_style, alignment=TA_CENTER)
header_cell_style = ParagraphStyle(
    "HeaderCell",
    parent=cell_style,
    fontName="Helvetica-Bold",
    fontSize=8,
    textColor=colors.white,
)


def fmt_eur(value: float) -> str:
    return "€ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dag_label(datum_str: str) -> str:
    d = datetime.strptime(datum_str, "%Y-%m-%d").date()
    return f"{DAGNAMEN_NL[d.weekday()]} {d.day} {MAANDNAMEN_NL[d.month]}"


def _week_datums(week: int, jaar: int) -> tuple[date, date]:
    jan4 = date(jaar, 1, 4)
    monday_week1 = jan4 - timedelta(days=jan4.weekday())
    week_start = monday_week1 + timedelta(weeks=week - 1)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _week_header_tekst(week: int, jaar: int) -> str:
    start, end = _week_datums(week, jaar)
    start_str = f"{start.day} {MAANDNAMEN_NL[start.month]}"
    if start.year != end.year:
        start_str += f" {start.year}"
    end_str = f"{end.day} {MAANDNAMEN_NL[end.month]} {end.year}"
    return f"Week {week} — {start_str} t/m {end_str}"


def build_header_row(accent_color):
    header = ["Klant/adres", "Plaats", "Ordernummers", "Colli", "Trede", "Tarief"]
    t = Table(
        [[Paragraph(h, header_cell_style) for h in header]],
        colWidths=[w * mm for w in COL_WIDTHS_MM],
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent_color),
                ("TOPPADDING", (0, 0), (-1, -1), 6.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def build_day_block(day_label, day_rows, accent_color):
    data = []
    style_commands = [
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRIJS_LIJN),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    data.append(
        [
            Paragraph(
                day_label.upper(),
                ParagraphStyle(
                    "DayLbl",
                    parent=cell_style,
                    fontName="Helvetica-Bold",
                    fontSize=7.6,
                    textColor=GRIJS_TEKST,
                ),
            ),
            "",
            "",
            "",
            "",
            "",
        ]
    )
    style_commands += [
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), GRIJS_BAND),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
    ]

    day_total = 0.0
    for r in day_rows:
        (_, _, locname, straat, postcode, plaats, colli, taken, orders, trede, tarief) = r
        day_total += tarief
        adres = (
            f"<font face='Helvetica-Bold'>{locname}</font>"
            f"<br/><font size=7 color='#8a93a0'>{straat}</font>"
        )
        data.append(
            [
                Paragraph(adres, cell_style),
                Paragraph(plaats, cell_style),
                Paragraph(str(orders), cell_style_lo),
                Paragraph(str(colli), cell_style_c),
                Paragraph(trede or "", cell_style_c),
                Paragraph(f"<font face='Helvetica-Bold'>{fmt_eur(tarief)}</font>", cell_style_r),
            ]
        )

    table = Table(data, colWidths=[w * mm for w in COL_WIDTHS_MM])
    table.setStyle(TableStyle(style_commands))
    return table, day_total


def section_header_bar(text, color, total_width_mm=PAGE_WIDTH_MM, style=None):
    t = Table(
        [[Paragraph(text, style or section_style)]],
        colWidths=[total_width_mm * mm],
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("TOPPADDING", (0, 0), (-1, -1), 7.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return t


def build_dag_blokken(section_rows, accent_color):
    """Dag-blokken voor één sectie (laden of lossen), zonder totaalbalk."""
    by_day = defaultdict(list)
    for r in section_rows:
        by_day[r[0]].append(r)

    flowables = []
    section_total = 0.0
    for day in sorted(by_day.keys()):
        day_table, day_total = build_day_block(_dag_label(day), by_day[day], accent_color)
        section_total += day_total
        flowables.append(day_table)
    return flowables, section_total


def build_week_subtotaal(week_nr, laden_total, lossen_total, toon_laden=True, toon_lossen=True):
    bedrag = lossen_total if not toon_laden else laden_total
    lbl = ParagraphStyle(
        "WkSubLbl",
        parent=cell_style,
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=colors.white,
    )
    lbl_r = ParagraphStyle("WkSubR", parent=lbl, alignment=TA_RIGHT)
    t = Table(
        [
            [
                Paragraph(f"Subtotaal week {week_nr}", lbl),
                Paragraph(f"<b>{fmt_eur(bedrag)}</b>", lbl_r),
            ]
        ],
        colWidths=[(PAGE_WIDTH_MM - 34) * mm, 34 * mm],
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WEEK_KLEUR),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return t


def _build_sectie_totaal(label: str, bedrag: float, kleur):
    lbl = ParagraphStyle(
        "SecTotLbl",
        parent=cell_style,
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.white,
    )
    lbl_r = ParagraphStyle("SecTotR", parent=lbl, alignment=TA_RIGHT, fontSize=10.5)
    t = Table(
        [[Paragraph(label, lbl), Paragraph(f"<b>{fmt_eur(bedrag)}</b>", lbl_r)]],
        colWidths=[(PAGE_WIDTH_MM - 34) * mm, 34 * mm],
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), INKT),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return t


def _draw_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(GRIJS_LIJN)
    canvas.setLineWidth(0.5)
    y = 14 * mm
    canvas.line(15 * mm, y, (15 + PAGE_WIDTH_MM) * mm, y)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GRIJS_TEKST)
    canvas.drawString(15 * mm, y - 9, "Miedema Ophaaldienst B.V. · intern overzicht")
    canvas.drawRightString((15 + PAGE_WIDTH_MM) * mm, y - 9, f"Pagina {doc.page}")
    canvas.restoreState()


def genereer_jaaroverzicht(rows, periode_omschrijving: str, output_path: str):
    """
    Bouwt het jaaroverzicht PDF. Gegroepeerd per week, per dag.

    Parameters
    ----------
    rows : list[tuple]
        11 velden per rij (zelfde formaat als genereer_rapport.genereer_pdf).
    periode_omschrijving : str
        Bijv. "week 1 t/m 24, 2026".
    output_path : str
        Volledig pad incl. bestandsnaam.pdf.

    Returns
    -------
    (output_path, totals_dict)
    totals_dict = {"laden": .., "lossen": .., "totaal": ..}
    """
    if not os.path.isfile(LOGO_MIEDEMA) or not os.path.isfile(LOGO_LOKALIST):
        raise FileNotFoundError(f"Logo-bestanden niet gevonden in {ASSET_DIR}.")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=15 * mm,
        bottomMargin=20 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
    )
    story = []

    # --- Header met logo's ---
    miedema_h_mm, lokalist_h_mm = 9.5, 8.5
    miedema_w_mm = miedema_h_mm * MIEDEMA_ASPECT
    lokalist_w_mm = lokalist_h_mm * LOKALIST_ASPECT
    mid_col_mm = PAGE_WIDTH_MM - miedema_w_mm - lokalist_w_mm
    header_table = Table(
        [
            [
                RLImage(LOGO_MIEDEMA, width=miedema_w_mm * mm, height=miedema_h_mm * mm),
                "",
                RLImage(LOGO_LOKALIST, width=lokalist_w_mm * mm, height=lokalist_h_mm * mm),
            ]
        ],
        colWidths=[miedema_w_mm * mm, mid_col_mm * mm, lokalist_w_mm * mm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 14))

    gold_line = Table([[""]], colWidths=[PAGE_WIDTH_MM * mm], rowHeights=[1.4])
    gold_line.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), MIEDEMA_GEEL)]))
    story.append(gold_line)
    story.append(Spacer(1, 12))

    # --- Titel ---
    story.append(Paragraph("Orderoverzicht De Lokalist", title_style))
    nu = datetime.now()
    story.append(
        Paragraph(
            f"{periode_omschrijving} · "
            f"Gegenereerd op {nu.strftime('%d-%m-%Y')} om {nu.strftime('%H:%M')}",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.6, color=GRIJS_LIJN))
    story.append(Spacer(1, 14))

    # --- Groepeer per (iso_jaar, iso_week) ---
    by_week: dict[tuple[int, int], list] = defaultdict(list)
    for r in rows:
        d = datetime.strptime(r[0], "%Y-%m-%d").date()
        iso = d.isocalendar()
        by_week[(iso[0], iso[1])].append(r)

    laden_grand = 0.0
    lossen_grand = 0.0
    weken = sorted(by_week.keys())

    # --- Sectie LADEN ---
    story.append(
        KeepTogether(
            [
                section_header_bar("LADEN", LADEN_KLEUR),
                build_header_row(LADEN_KLEUR),
            ]
        )
    )

    for jaar, week in weken:
        laden_rows = [r for r in by_week[(jaar, week)] if r[1] == "Laden"]
        if not laden_rows:
            continue
        week_tekst = _week_header_tekst(week, jaar)
        story.append(
            KeepTogether(
                [
                    section_header_bar(week_tekst, WEEK_KLEUR, style=week_section_style),
                    build_header_row(LADEN_KLEUR),
                ]
            )
        )
        dag_flowables, laden_week = build_dag_blokken(laden_rows, LADEN_KLEUR)
        story.extend(dag_flowables)
        story.append(KeepTogether(build_week_subtotaal(week, laden_week, 0.0, toon_lossen=False)))
        story.append(Spacer(1, 8))
        laden_grand += laden_week

    story.append(Spacer(1, 6))
    story.append(KeepTogether(_build_sectie_totaal("Totaal Laden", laden_grand, LADEN_KLEUR)))
    story.append(Spacer(1, 20))

    # --- Sectie LOSSEN ---
    story.append(
        KeepTogether(
            [
                section_header_bar("LOSSEN", LOSSEN_KLEUR),
                build_header_row(LOSSEN_KLEUR),
            ]
        )
    )

    for jaar, week in weken:
        lossen_rows = [r for r in by_week[(jaar, week)] if r[1] == "Lossen"]
        if not lossen_rows:
            continue
        week_tekst = _week_header_tekst(week, jaar)
        story.append(
            KeepTogether(
                [
                    section_header_bar(week_tekst, WEEK_KLEUR, style=week_section_style),
                    build_header_row(LOSSEN_KLEUR),
                ]
            )
        )
        dag_flowables, lossen_week = build_dag_blokken(lossen_rows, LOSSEN_KLEUR)
        story.extend(dag_flowables)
        story.append(KeepTogether(build_week_subtotaal(week, 0.0, lossen_week, toon_laden=False)))
        story.append(Spacer(1, 8))
        lossen_grand += lossen_week

    story.append(Spacer(1, 6))
    story.append(KeepTogether(_build_sectie_totaal("Totaal Lossen", lossen_grand, LOSSEN_KLEUR)))
    story.append(Spacer(1, 20))

    # --- Eindtotaal ---
    story.append(HRFlowable(width="100%", thickness=1.1, color=MIEDEMA_GROEN))
    story.append(Spacer(1, 6))
    grand_total = laden_grand + lossen_grand
    totals_data = [
        [Paragraph("Totaal Laden", cell_style), Paragraph(fmt_eur(laden_grand), cell_style_r)],
        [Paragraph("Totaal Lossen", cell_style), Paragraph(fmt_eur(lossen_grand), cell_style_r)],
        [
            Paragraph(
                f"<b>Eindtotaal {periode_omschrijving}</b>",
                ParagraphStyle("GTL", parent=cell_style, fontSize=11.5, textColor=MIEDEMA_GROEN),
            ),
            Paragraph(
                f"<b>{fmt_eur(grand_total)}</b>",
                ParagraphStyle("GTV", parent=cell_style_r, fontSize=11.5, textColor=MIEDEMA_GROEN),
            ),
        ],
    ]
    totals_table = Table(totals_data, colWidths=[135 * mm, 45 * mm])
    totals_table.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, 1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, 1), 4),
                ("LINEABOVE", (0, 2), (-1, 2), 1.1, MIEDEMA_GROEN),
                ("TOPPADDING", (0, 2), (-1, 2), 9),
            ]
        )
    )
    story.append(KeepTogether(totals_table))

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)

    return output_path, {
        "laden": laden_grand,
        "lossen": lossen_grand,
        "totaal": grand_total,
    }
