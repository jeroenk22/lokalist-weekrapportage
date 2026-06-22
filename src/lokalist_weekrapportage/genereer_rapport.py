#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
genereer_rapport.py
--------------------
Bouwt het 'Orderoverzicht De Lokalist' PDF-rapport, exact in de opmaak die
samen met Jeroen is vastgesteld (Miedema + Lokalist logo's, goud/groen
secties Laden/Lossen, dag-subtotalen, eindtotaal).

Dit bestand is een HERBRUIKBARE MODULE: het bevat geen hardcoded data meer.
Andere scripts (bijv. het wekelijkse automatiseringsscript) roepen
`genereer_pdf(...)` aan met de queryresultaten en krijgen het pad naar het
gegenereerde PDF-bestand terug.

Vereiste assets (zelfde map als dit script, of pas ASSET_DIR hieronder aan):
    logo_miedema.png   (transparante achtergrond, gecropt op de inhoud)
    logo_lokalist.png  (transparante achtergrond, gecropt op de inhoud)

Vereiste rij-vorm per item in `rows` (lijst van tuples), exact deze 11 velden:
    (datum:str 'YYYY-MM-DD', task_type:'Laden'|'Lossen', locname:str,
     straat:str, postcode:str, plaats:str, colli:int, aantal_taken:int,
     ordernummers:str (komma-gescheiden), staffeltrede:str ('1 tot 4'),
     tarief:float)

Gebruik:
    from genereer_rapport import genereer_pdf
    pdf_path, totals = genereer_pdf(
        rows=rows,
        weeknummer=25,
        jaar=2026,
        periode_omschrijving="16 t/m 22 juni 2026",
        output_path="/pad/naar/output.pdf",
    )
    # totals = {"laden": 210.68, "lossen": 183.59, "totaal": 394.27}
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
    Image as RLImage, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from datetime import datetime, date
from collections import defaultdict

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_MIEDEMA = os.path.join(ASSET_DIR, "logo_miedema.png")
LOGO_LOKALIST = os.path.join(ASSET_DIR, "logo_lokalist.png")

# Vaste pixelverhoudingen van de aangeleverde, voorgecropte logo's.
# Als de logo-bestanden ooit vervangen worden, deze waarden updaten
# (breedte/hoogte in pixels van het nieuwe bestand) zodat de aspect ratio
# correct blijft.
MIEDEMA_ASPECT = 1985 / 457
LOKALIST_ASPECT = 713 / 116

DAGNAMEN_NL = {
    0: "Maandag", 1: "Dinsdag", 2: "Woensdag", 3: "Donderdag",
    4: "Vrijdag", 5: "Zaterdag", 6: "Zondag",
}
MAANDNAMEN_NL = {
    1: "januari", 2: "februari", 3: "maart", 4: "april", 5: "mei", 6: "juni",
    7: "juli", 8: "augustus", 9: "september", 10: "oktober", 11: "november",
    12: "december",
}


def _dag_label(datum_str: str) -> str:
    d = datetime.strptime(datum_str, "%Y-%m-%d").date()
    return f"{DAGNAMEN_NL[d.weekday()]} {d.day} {MAANDNAMEN_NL[d.month]}"


# ------------------------------------------------------------------
# Merkkleuren + opmaak-constanten
# ------------------------------------------------------------------
MIEDEMA_GROEN = colors.HexColor("#004530")
MIEDEMA_GEEL  = colors.HexColor("#FADC01")
INKT          = colors.HexColor("#1c2630")
GRIJS_TEKST   = colors.HexColor("#5b6470")
GRIJS_LIJN    = colors.HexColor("#dcdfe3")
GRIJS_BAND    = colors.HexColor("#f3f4f6")

LADEN_KLEUR   = colors.HexColor("#B8860B")   # donker goud, uit het Miedema-logo
LOSSEN_KLEUR  = MIEDEMA_GROEN                # het donkergroen uit beide logo's
SPOED_KLEUR   = colors.HexColor("#C0392B")   # rood voor spoedorders

PAGE_WIDTH_MM = 180  # A4 (210mm) - 2x15mm marge
COL_WIDTHS_MM = [40.5, 23.5, 47, 13.5, 21.5, 34]        # som = 180mm
SPOED_COL_WIDTHS_MM = [22, 40, 40, 18, 14, 46]           # som = 180mm

styles = getSampleStyleSheet()
title_style = ParagraphStyle(
    "TitleCustom", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=20, leading=24, textColor=INKT, spaceAfter=3, alignment=TA_LEFT,
)
subtitle_style = ParagraphStyle(
    "SubtitleCustom", parent=styles["Normal"], fontName="Helvetica",
    fontSize=9.5, leading=13, textColor=GRIJS_TEKST, spaceAfter=0,
)
section_style = ParagraphStyle(
    "SectionHeader", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=12.5, leading=14, textColor=colors.white, spaceAfter=0, spaceBefore=0,
)
cell_style    = ParagraphStyle("Cell", parent=styles["Normal"], fontName="Helvetica", fontSize=8.3, leading=10.4, textColor=INKT)
cell_style_lo = ParagraphStyle("CellLo", parent=cell_style, fontSize=7, textColor=GRIJS_TEKST, leading=8.6)
cell_style_r  = ParagraphStyle("CellR", parent=cell_style, alignment=TA_RIGHT)
cell_style_c  = ParagraphStyle("CellC", parent=cell_style, alignment=TA_CENTER)
header_cell_style = ParagraphStyle(
    "HeaderCell", parent=cell_style, fontName="Helvetica-Bold", fontSize=8, textColor=colors.white,
)


def fmt_eur(value: float) -> str:
    return "\u20ac " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_spoed_header_row():
    header = ["Datum", "Van adres", "Naar adres", "Order", "Colli", "Tarief"]
    t = Table(
        [[Paragraph(h, header_cell_style) for h in header]],
        colWidths=[w * mm for w in SPOED_COL_WIDTHS_MM],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SPOED_KLEUR),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def build_spoed_block(spoed_rows):
    """Bouwt de spoed-tabel (per order, geen dag-groepering)."""
    data = []
    style_commands = [
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRIJS_LIJN),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    spoed_total = 0.0
    for r in sorted(spoed_rows, key=lambda x: (x[0], x[1])):
        datum, order_id, van_naam, van_adres, naar_naam, naar_adres, colli, tarief = r
        spoed_total += tarief
        van_tekst = (
            f"<font face='Helvetica-Bold'>{van_naam}</font>"
            f"<br/><font size=7 color='#8a93a0'>{van_adres}</font>"
        )
        naar_tekst = (
            f"<font face='Helvetica-Bold'>{naar_naam}</font>"
            f"<br/><font size=7 color='#8a93a0'>{naar_adres}</font>"
        )
        data.append([
            Paragraph(_dag_label(datum), cell_style),
            Paragraph(van_tekst, cell_style),
            Paragraph(naar_tekst, cell_style),
            Paragraph(str(order_id), cell_style_c),
            Paragraph(str(colli), cell_style_c),
            Paragraph(f"<font face='Helvetica-Bold'>{fmt_eur(tarief)}</font>", cell_style_r),
        ])
    table = Table(data, colWidths=[w * mm for w in SPOED_COL_WIDTHS_MM])
    table.setStyle(TableStyle(style_commands))
    return table, spoed_total


def build_header_row(accent_color):
    header = ["Klant/adres", "Plaats", "Ordernummers", "Colli", "Trede", "Tarief"]
    t = Table([[Paragraph(h, header_cell_style) for h in header]],
              colWidths=[w * mm for w in COL_WIDTHS_MM])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent_color),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
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
    data.append([Paragraph(day_label.upper(), ParagraphStyle(
        "DayLbl", parent=cell_style, fontName="Helvetica-Bold", fontSize=7.6, textColor=GRIJS_TEKST,
    )), "", "", "", "", ""])
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
        adres = f"<font face='Helvetica-Bold'>{locname}</font><br/><font size=7 color='#8a93a0'>{straat}</font>"
        data.append([
            Paragraph(adres, cell_style),
            Paragraph(plaats, cell_style),
            Paragraph(str(orders), cell_style_lo),
            Paragraph(str(colli), cell_style_c),
            Paragraph(trede, cell_style_c),
            Paragraph(f"<font face='Helvetica-Bold'>{fmt_eur(tarief)}</font>", cell_style_r),
        ])

    sub_idx = len(data)
    data.append([
        Paragraph(f"Subtotaal &ndash; {day_label.lower()}", ParagraphStyle(
            "SubLbl", parent=cell_style, fontName="Helvetica-Oblique", fontSize=7.8, textColor=GRIJS_TEKST,
        )),
        "", "", "", "",
        Paragraph(f"<b>{fmt_eur(day_total)}</b>", cell_style_r),
    ])
    style_commands += [
        ("SPAN", (0, sub_idx), (4, sub_idx)),
        ("LINEABOVE", (0, sub_idx), (-1, sub_idx), 0.6, GRIJS_LIJN),
        ("LINEBELOW", (0, sub_idx), (-1, sub_idx), 0, colors.white),
        ("TOPPADDING", (0, sub_idx), (-1, sub_idx), 4),
        ("BOTTOMPADDING", (0, sub_idx), (-1, sub_idx), 4),
    ]

    table = Table(data, colWidths=[w * mm for w in COL_WIDTHS_MM])
    table.setStyle(TableStyle(style_commands))
    return table, day_total


def build_totaal_bar(section_total):
    t = Table(
        [[Paragraph("TOTAAL SECTIE", ParagraphStyle(
            "TotLbl", parent=cell_style, fontName="Helvetica-Bold", fontSize=9, textColor=colors.white,
        )), Paragraph(f"<b>{fmt_eur(section_total)}</b>", ParagraphStyle(
            "TotVal", parent=cell_style_r, fontSize=10.5, textColor=colors.white,
        ))]],
        colWidths=[(180 - 34) * mm, 34 * mm],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INKT),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t


def build_section_flowables(section_rows, accent_color):
    by_day = defaultdict(list)
    for r in section_rows:
        by_day[r[0]].append(r)

    flowables = [build_header_row(accent_color)]
    section_total = 0.0
    for day in sorted(by_day.keys()):
        day_label = _dag_label(day)
        day_table, day_total = build_day_block(day_label, by_day[day], accent_color)
        section_total += day_total
        flowables.append(day_table)
    flowables.append(Spacer(1, 6))
    flowables.append(KeepTogether(build_totaal_bar(section_total)))
    return flowables, section_total


def section_header_bar(text, color, total_width_mm=PAGE_WIDTH_MM):
    t = Table([[Paragraph(text, section_style)]], colWidths=[total_width_mm * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("TOPPADDING", (0, 0), (-1, -1), 7.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t


def _draw_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(GRIJS_LIJN)
    canvas.setLineWidth(0.5)
    y = 14 * mm
    canvas.line(15 * mm, y, (15 + PAGE_WIDTH_MM) * mm, y)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GRIJS_TEKST)
    canvas.drawString(15 * mm, y - 9, "Miedema Ophaaldienst B.V. \u00b7 intern overzicht")
    canvas.drawRightString((15 + PAGE_WIDTH_MM) * mm, y - 9, f"Pagina {doc.page}")
    canvas.restoreState()


def genereer_pdf(
    rows,
    weeknummer: int,
    jaar: int,
    periode_omschrijving: str,
    output_path: str,
    spoed_rows=None,
):
    """
    Bouwt het PDF-rapport en schrijft het naar output_path.

    Parameters
    ----------
    rows : list[tuple]
        Normale queryresultaten (11 velden per rij, zie module-docstring).
    weeknummer, jaar : int
        Voor de titelregel.
    periode_omschrijving : str
        Bijv. "16 t/m 22 juni 2026".
    output_path : str
        Volledig pad (incl. bestandsnaam.pdf).
    spoed_rows : list[tuple] | None
        Optioneel, 8 velden: (datum, order_id, van_naam, van_adres,
        naar_naam, naar_adres, colli, tarief). Sectie wordt alleen getoond
        als er rijen zijn.

    Returns
    -------
    (output_path, totals_dict)
    totals_dict = {"laden": .., "lossen": .., "spoed": .., "totaal": ..}
    """
    if not os.path.isfile(LOGO_MIEDEMA) or not os.path.isfile(LOGO_LOKALIST):
        raise FileNotFoundError(
            f"Logo-bestanden niet gevonden in {ASSET_DIR}. "
            f"Verwacht: logo_miedema.png en logo_lokalist.png naast dit script."
        )

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=15*mm, bottomMargin=20*mm, leftMargin=15*mm, rightMargin=15*mm,
    )
    story = []

    # --- Header met logo's ---
    miedema_h_mm, lokalist_h_mm = 9.5, 8.5
    miedema_w_mm = miedema_h_mm * MIEDEMA_ASPECT
    lokalist_w_mm = lokalist_h_mm * LOKALIST_ASPECT
    miedema_img = RLImage(LOGO_MIEDEMA, width=miedema_w_mm * mm, height=miedema_h_mm * mm)
    lokalist_img = RLImage(LOGO_LOKALIST, width=lokalist_w_mm * mm, height=lokalist_h_mm * mm)
    mid_col_mm = PAGE_WIDTH_MM - miedema_w_mm - lokalist_w_mm
    header_table = Table(
        [[miedema_img, "", lokalist_img]],
        colWidths=[miedema_w_mm * mm, mid_col_mm * mm, lokalist_w_mm * mm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 14))

    gold_line = Table([[""]], colWidths=[PAGE_WIDTH_MM * mm], rowHeights=[1.4])
    gold_line.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), MIEDEMA_GEEL)]))
    story.append(gold_line)
    story.append(Spacer(1, 12))

    # --- Titel + subtitel ---
    story.append(Paragraph("Orderoverzicht De Lokalist", title_style))
    nu = datetime.now()
    story.append(Paragraph(
        f"Week {weeknummer} &middot; {periode_omschrijving} &middot; "
        f"Gegenereerd op {nu.strftime('%d-%m-%Y')} om {nu.strftime('%H:%M')}",
        subtitle_style,
    ))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.6, color=GRIJS_LIJN))
    story.append(Spacer(1, 14))

    # --- Sectie Laden ---
    laden_rows = [r for r in rows if r[1] == "Laden"]
    story.append(KeepTogether([section_header_bar("LADEN", LADEN_KLEUR), build_header_row(LADEN_KLEUR)]))
    laden_flowables, laden_total = build_section_flowables(laden_rows, LADEN_KLEUR)
    story.extend(laden_flowables[1:])
    story.append(Spacer(1, 20))

    # --- Sectie Lossen ---
    lossen_rows = [r for r in rows if r[1] == "Lossen"]
    story.append(KeepTogether([section_header_bar("LOSSEN", LOSSEN_KLEUR), build_header_row(LOSSEN_KLEUR)]))
    lossen_flowables, lossen_total = build_section_flowables(lossen_rows, LOSSEN_KLEUR)
    story.extend(lossen_flowables[1:])
    story.append(Spacer(1, 18))

    # --- Sectie Spoed (alleen als er spoedorders zijn) ---
    spoed_total = 0.0
    if spoed_rows:
        story.append(KeepTogether([section_header_bar("SPOED", SPOED_KLEUR), build_spoed_header_row()]))
        spoed_table, spoed_total = build_spoed_block(spoed_rows)
        story.append(spoed_table)
        story.append(Spacer(1, 6))
        story.append(KeepTogether(build_totaal_bar(spoed_total)))
        story.append(Spacer(1, 18))

    # --- Eindtotaal ---
    grand_total = laden_total + lossen_total + spoed_total
    totals_data = [
        [Paragraph("Totaal Laden", cell_style), Paragraph(fmt_eur(laden_total), cell_style_r)],
        [Paragraph("Totaal Lossen", cell_style), Paragraph(fmt_eur(lossen_total), cell_style_r)],
    ]
    if spoed_rows:
        totals_data.append(
            [Paragraph("Totaal Spoed", cell_style), Paragraph(fmt_eur(spoed_total), cell_style_r)]
        )
    eindtotaal_idx = len(totals_data)
    totals_data.append([
        Paragraph(
            f"<b>Eindtotaal week {weeknummer}</b>",
            ParagraphStyle("GTL", parent=cell_style, fontSize=11.5, textColor=MIEDEMA_GROEN),
        ),
        Paragraph(
            f"<b>{fmt_eur(grand_total)}</b>",
            ParagraphStyle("GTV", parent=cell_style_r, fontSize=11.5, textColor=MIEDEMA_GROEN),
        ),
    ])
    totals_table = Table(totals_data, colWidths=[135 * mm, 45 * mm])
    totals_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, eindtotaal_idx - 1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, eindtotaal_idx - 1), 4),
        ("LINEABOVE", (0, eindtotaal_idx), (-1, eindtotaal_idx), 1.1, MIEDEMA_GROEN),
        ("TOPPADDING", (0, eindtotaal_idx), (-1, eindtotaal_idx), 9),
    ]))
    story.append(KeepTogether(totals_table))

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)

    return output_path, {
        "laden": laden_total,
        "lossen": lossen_total,
        "spoed": spoed_total,
        "totaal": grand_total,
    }


if __name__ == "__main__":
    # Kleine zelftest met de bekende week-24 data, puur om te verifiëren dat
    # de module zelfstandig correct draait (handig bij het opzetten op de
    # nieuwe machine, los van de SQL-koppeling).
    test_rows = [
        ("2026-06-08", "Lossen", "Squarewise Oost B.V.", "Oude Kraan 72", "6811LL", "Arnhem", 3, 1, "1235223", "1 tot 4", 15.39),
        ("2026-06-08", "Laden", "Burgerboerderij de Patrijs", "Dochterenseweg 13A", "7245NN", "Laren", 6, 1, "1236833", "4 tot 7", 19.85),
    ]
    path, totals = genereer_pdf(
        rows=test_rows, weeknummer=24, jaar=2026,
        periode_omschrijving="8 t/m 14 juni 2026 (zelftest)",
        output_path=os.path.join(ASSET_DIR, "zelftest_rapport.pdf"),
    )
    print(f"Zelftest geslaagd: {path}")
    print(totals)
