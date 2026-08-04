"""Ophalen van bestaande verzamelorders voor het webdashboard.

Aparte module zodat query.py — die de productie-weekrapportage voedt —
ongewijzigd blijft. De connectiestring wordt hergebruikt uit query.py, zodat
authenticatie en driverkeuze op één plek geregeld blijven.
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime

import pyodbc

from .config import Config
from .query import _bouw_connectiestring
from .verzamelorder import (
    dagnaam,
    formatteer_aanmaakmoment,
    is_handmatig,
    maandnaam,
    parse_naam,
)

_log = logging.getLogger(__name__)

SQL_BESTAND = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "lokalist_verzamelorders.sql"
)

# Alleen kenmerken die exact 'Week <nr> <jaar>' zijn horen bij een weekrapport.
# Het jaaroverzicht gebruikt bijvoorbeeld 'week 1 t/m 24, 2026' en valt hier
# bewust buiten: dat rapport kan niet via dit dashboard hergenereerd worden.
_KENMERK_PATROON = re.compile(r"^Week\s+(\d{1,2})\s+(\d{4})$", re.IGNORECASE)


@dataclass(frozen=True)
class Verzamelorder:
    order_id: int
    aangemaakt: datetime
    weeknummer: int
    jaar: int
    handmatig: bool
    notities: str
    totaal_colli: int
    totaal_bedrag: float
    # Interne sleutel (Orders.InvKey) — bepaalt of er een factuur aan hangt en is
    # het enige waarop je een voorlopige factuur in MendriX kunt terugvinden
    # (Snelkiezen facturen, CTRL+SHIFT+K, vinkje "Kies op sleutel").
    factuur_sleutel: int | None = None
    # Het factuurnummer dat Miedema hanteert (invoices.InvNo). Blijft leeg zolang
    # de factuur voorlopig is; MendriX kent het nummer pas toe bij definitief maken.
    factuur_nummer: int | None = None

    @property
    def label(self) -> str:
        """'zondag 02 augustus 2026 (automatisch)' — zoals in het dashboard."""
        return formatteer_aanmaakmoment(self.aangemaakt, self.handmatig)

    @property
    def hergenereerd_door(self) -> str | None:
        """Naam uit de notitie; None bij automatische of oudere handmatige runs."""
        return parse_naam(self.notities) if self.handmatig else None

    @property
    def herkomst_tekst(self) -> str | None:
        """Tooltip bij de handmatig-badge.

        'Op dinsdag 04 augustus 12:07 hergenereerd door Jeroen'. Datum en tijd
        komen uit Orders.Moment — het aanmaakmoment van deze order is precies
        het moment waarop hij hergenereerd is.
        """
        if not self.handmatig:
            return None
        moment = (
            f"Op {dagnaam(self.aangemaakt)} {self.aangemaakt.day:02d} "
            f"{maandnaam(self.aangemaakt.month)} "
            f"{self.aangemaakt.hour:02d}:{self.aangemaakt.minute:02d} hergenereerd"
        )
        naam = self.hergenereerd_door
        return f"{moment} door {naam}" if naam else f"{moment} (naam niet vastgelegd)"

    @property
    def gefactureerd(self) -> bool:
        """True als er een factuur naar deze order verwijst.

        Zo'n order mag niet hergenereerd worden: hergenereren verwijdert hem en
        maakt een nieuwe aan met een ander ordernummer, waardoor de factuurregel
        naar een niet meer bestaande order zou wijzen. Geldt ook voor een
        voorlopige factuur — die raakt net zo goed van slag.
        """
        return self.factuur_sleutel is not None

    @property
    def factuur_voorlopig(self) -> bool:
        """True als de factuur bestaat maar nog geen definitief nummer heeft."""
        return self.gefactureerd and self.factuur_nummer is None

    @property
    def factuur_kopieerwaarde(self) -> int | None:
        """Het nummer waarmee je deze factuur in MendriX terugvindt.

        Definitief: het factuurnummer (InvNo). Voorlopig: de sleutel (InvKey),
        want een nummer is er dan nog niet — zoeken gaat dan via Snelkiezen
        facturen met "Kies op sleutel".
        """
        if not self.gefactureerd:
            return None
        return self.factuur_nummer if self.factuur_nummer is not None else self.factuur_sleutel

    @property
    def factuur_omschrijving(self) -> str | None:
        """Tekst voor het dashboard: het echte nummer, of 'voorlopige factuur'."""
        if not self.gefactureerd:
            return None
        if self.factuur_nummer is None:
            return f"voorlopige factuur {self.factuur_sleutel}"
        return f"factuur {self.factuur_nummer}"

    def as_dict(self) -> dict:
        return {
            "orderId": self.order_id,
            "aangemaakt": self.aangemaakt.isoformat(),
            "weeknummer": self.weeknummer,
            "jaar": self.jaar,
            "handmatig": self.handmatig,
            "notities": self.notities,
            "totaalColli": self.totaal_colli,
            "totaalBedrag": self.totaal_bedrag,
            "label": self.label,
            "hergenereerdDoor": self.hergenereerd_door,
            "herkomstTekst": self.herkomst_tekst,
            "gefactureerd": self.gefactureerd,
            "factuurNummer": self.factuur_nummer,
            "factuurSleutel": self.factuur_sleutel,
            "factuurVoorlopig": self.factuur_voorlopig,
            "factuurKopieerwaarde": self.factuur_kopieerwaarde,
            "factuurOmschrijving": self.factuur_omschrijving,
        }


def parse_kenmerk(kenmerk: str) -> tuple[int, int] | None:
    """Haalt (weeknummer, jaar) uit een kenmerk als 'Week 31 2026'.

    Geeft None terug bij een kenmerk dat niet bij een weekrapport hoort.
    """
    match = _KENMERK_PATROON.match((kenmerk or "").strip())
    if not match:
        return None
    week, jaar = int(match.group(1)), int(match.group(2))
    if not 1 <= week <= 53:
        return None
    return week, jaar


def _rij_naar_verzamelorder(rij) -> Verzamelorder | None:
    geparsed = parse_kenmerk(rij.Kenmerk)
    if geparsed is None:
        _log.debug(
            "Order %s overgeslagen — kenmerk %r hoort niet bij een weekrapport.",
            rij.OrderId,
            rij.Kenmerk,
        )
        return None
    week, jaar = geparsed
    notities = rij.Notities or ""
    return Verzamelorder(
        order_id=int(rij.OrderId),
        aangemaakt=rij.Aangemaakt,
        weeknummer=week,
        jaar=jaar,
        handmatig=is_handmatig(notities),
        notities=notities,
        totaal_colli=int(rij.TotaalColli or 0),
        totaal_bedrag=float(rij.TotaalBedrag or 0.0),
        factuur_sleutel=int(rij.FactuurSleutel) if rij.FactuurSleutel else None,
        factuur_nummer=int(rij.FactuurNummer) if rij.FactuurNummer else None,
    )


def haal_verzamelorders_op(config: Config) -> list[Verzamelorder]:
    """Haalt alle actieve verzamelorders op, nieuwste eerst.

    Verwijderde, geannuleerde en niet-weekgebonden orders blijven buiten de lijst.
    """
    with open(SQL_BESTAND, encoding="utf-8") as f:
        sql_tekst = f.read()

    conn = pyodbc.connect(_bouw_connectiestring(config))
    try:
        cursor = conn.cursor()
        cursor.execute(sql_tekst)
        ruwe_rijen = cursor.fetchall()
    except Exception:
        _log.warning("Verzamelorder-query mislukt", exc_info=True)
        raise
    finally:
        conn.close()

    orders = [vo for rij in ruwe_rijen if (vo := _rij_naar_verzamelorder(rij)) is not None]
    _log.info(
        "%d verzamelorder(s) opgehaald (%d rij(en) uit de database).", len(orders), len(ruwe_rijen)
    )
    return orders
