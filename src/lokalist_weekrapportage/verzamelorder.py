"""Verzamelorder-logica voor het webdashboard.

Bevat de XML-opbouw van de samenvattende order, de Nederlandse datumopmaak voor
het dashboard en de markering die een handmatig hergenereerd rapport herkenbaar
maakt.

De store-XML is een exacte kopie van _bouw_store_xml uit
scripts/run_weekrapportage.py, met één toevoeging: een optioneel <Notes>-element.
Wordt er geen notitie meegegeven, dan is de output byte-identiek aan die van de
geplande zondagrun. tests/unit/test_verzamelorder_drift.py bewaakt dat.
"""

import re
import xml.sax.saxutils as saxutils
from datetime import date, datetime

LOKALIST_CLIENT_ID = 4787
LOKALIST_PRODUCT_ID = 19
LOKALIST_ADRES = {
    "Name": "De Lokalist",
    "Street": "Dochterenseweg",
    "Number": "13A",
    "PostalCode": "7245 NN",
    "Place": "Laren",
    "Country": "Nederland",
    "CountryCode": "NL",
}

DISFOOD_ARTNR = 16  # ArtNo van het DISFOOD-staffelartikel

# Machine-leesbare markering in het Notes-veld (dbo.Orders.Diversen). Hiermee
# herkent het dashboard of een verzamelorder handmatig opnieuw is gegenereerd.
#
# Twee vormen komen voor:
#   [HANDMATIG HERGENEREERD]                 — oude runs, zonder naam
#   [HANDMATIG HERGENEREERD | door Jeroen]   — met de naam van wie het deed
# Herkenning gaat daarom op de PREFIX, zodat beide blijven werken.
HANDMATIG_PREFIX = "[HANDMATIG HERGENEREERD"

# Blijft bestaan voor de oude vorm; nieuwe notities gebruiken bouw_handmatige_notitie.
HANDMATIG_MARKER = "[HANDMATIG HERGENEREERD]"

# dbo.Orders.Diversen is varchar(250). De notitie moet daar met naam en al in
# passen; anders kapt SQL Server hem af en raken we de naam kwijt.
NOTITIE_MAXLENGTE = 250

# 'door' is optioneel bij het uitlezen, zodat een met de hand aangepaste notitie
# zonder dat woord nog steeds gelezen kan worden.
_NAAM_PATROON = re.compile(
    r"^\[HANDMATIG HERGENEREERD(?:\s*\|\s*(?:door\s+)?([^\]]*))?\]", re.IGNORECASE
)

_MAANDEN_NL = [
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
]

_DAGEN_NL = [
    "maandag",
    "dinsdag",
    "woensdag",
    "donderdag",
    "vrijdag",
    "zaterdag",
    "zondag",
]


def maandnaam(maand: int) -> str:
    """Nederlandse maandnaam voor maand 1-12."""
    if not 1 <= maand <= 12:
        raise ValueError(f"Ongeldige maand: {maand}")
    return _MAANDEN_NL[maand - 1]


def dagnaam(d: date) -> str:
    """Nederlandse dagnaam (maandag..zondag)."""
    return _DAGEN_NL[d.weekday()]


def formatteer_aanmaakmoment(moment: datetime, handmatig: bool) -> str:
    """Geeft 'dagnaam dd maandnaam jaar (automatisch|handmatig)'.

    Bijvoorbeeld: 'zondag 02 augustus 2026 (automatisch)'.
    """
    herkomst = "handmatig" if handmatig else "automatisch"
    return (
        f"{dagnaam(moment)} {moment.day:02d} {maandnaam(moment.month)} {moment.year} ({herkomst})"
    )


def bouw_handmatige_notitie(weeknummer: int, jaar: int, oude_order_id: int, naam: str) -> str:
    """Tekst voor het Notes-veld van een handmatig hergenereerde verzamelorder.

    Bevat de naam van wie het gedaan heeft en het vervangen ordernummer. Datum
    en tijd staan er bewust NIET in: dbo.Orders.Moment is het aanmaakmoment van
    deze order en dus precies het hergeneratiemoment. Dat scheelt ruimte in een
    veld van maar 250 tekens.

    Past de notitie er niet in, dan wordt de naam ingekort — nooit de rest, want
    dan zou het ordernummer of de markering sneuvelen.
    """
    schone_naam = " ".join(naam.split())
    if not schone_naam:
        raise ValueError("Naam is verplicht voor een handmatige hergeneratie.")

    def opbouw(gebruikte_naam: str) -> str:
        return (
            f"[HANDMATIG HERGENEREERD | door {gebruikte_naam}] Week {weeknummer} {jaar} "
            f"opnieuw gegenereerd via het dashboard. "
            f"Vorige verzamelorder {oude_order_id} verwijderd."
        )

    notitie = opbouw(schone_naam)
    if len(notitie) > NOTITIE_MAXLENGTE:
        teveel = len(notitie) - NOTITIE_MAXLENGTE
        notitie = opbouw(schone_naam[: max(1, len(schone_naam) - teveel)])
    return notitie


def is_handmatig(notities: str | None) -> bool:
    """Herkent aan het Notes-veld of de verzamelorder handmatig is hergenereerd.

    Werkt op zowel de oude vorm (zonder naam) als de nieuwe (met naam).
    """
    return (notities or "").lstrip().startswith(HANDMATIG_PREFIX)


def parse_naam(notities: str | None) -> str | None:
    """Haalt de naam uit het Notes-veld, of None als die er niet in staat.

    Orders die vóór de naaminvoer zijn hergenereerd hebben geen naam; die geven
    dus None terug.
    """
    match = _NAAM_PATROON.match((notities or "").lstrip())
    if not match:
        return None
    naam = (match.group(1) or "").strip()
    return naam or None


def periode_omschrijving(weeknummer: int, jaar: int) -> str:
    """Omschrijving van de week, bijv. '27 juli t/m 2 augustus 2026'."""
    maandag = date.fromisocalendar(jaar, weeknummer, 1)
    zondag = date.fromisocalendar(jaar, weeknummer, 7)
    if maandag.month == zondag.month:
        return f"{maandag.day} t/m {zondag.day} {_MAANDEN_NL[zondag.month - 1]} {jaar}"
    maand_m = _MAANDEN_NL[maandag.month - 1]
    maand_z = _MAANDEN_NL[zondag.month - 1]
    return f"{maandag.day} {maand_m} t/m {zondag.day} {maand_z} {jaar}"


def totaal_laden_colli(rows: list[tuple]) -> int:
    return sum(int(r[6]) for r in rows if str(r[1]).lower() == "laden")


def totaal_bedrag(rows: list[tuple]) -> float:
    return sum(float(r[10]) for r in rows if r[10])


def bouw_store_xml(
    colli: int,
    bedrag: float,
    instructies: str,
    moment_str: str,
    weeknummer: int,
    jaar: int,
    notities: str = "",
) -> str:
    """Bouwt de EoCustomLinkStoreOrdersNormal-XML voor een nieuwe verzamelorder.

    notities: optionele tekst voor het <Notes>-element (dbo.Orders.Diversen).
    Blijft dit leeg, dan is de XML identiek aan die van run_weekrapportage.py.
    """
    instr_esc = saxutils.escape(instructies)
    kenmerk = f"Week {weeknummer} {jaar}"

    aanmaakdag = date.today().isoformat()
    gewenst_begin = f"{aanmaakdag}T08:00:00"
    gewenst_einde = f"{aanmaakdag}T23:59:59"

    notes_regel = f"\n        <Notes>{saxutils.escape(notities)}</Notes>" if notities else ""

    return f"""\
<?xml version="1.0" encoding="windows-1252"?>
<EoCustomLinkStoreOrdersNormal Type="TEoCustomLinkStoreOrdersNormal">
  <Data Type="TEoOrderMxList">
    <_TEoListBase_Items>
      <EoOrderMx Type="TEoOrderMx">
        <OrderId Type="TEoKeyIntInfraMx">
          <Id>-1</Id>
        </OrderId>
        <ClientId Type="TEoKeyIntInfraMx">
          <Id>{LOKALIST_CLIENT_ID}</Id>
        </ClientId>
        <IsActive>False</IsActive>
        <MarkChars></MarkChars>
        <Reference>Verzamelorder</Reference>
        <Moment>{moment_str}</Moment>{notes_regel}
        <OrderType>400</OrderType>
        <ProductId Type="TEoKeyIntInfraMx">
          <Id>{LOKALIST_PRODUCT_ID}</Id>
        </ProductId>
        <ProductIdAutomaticArticles>False</ProductIdAutomaticArticles>
        <Deleted>False</Deleted>
        <ArticlesSell Type="TEoArticleList">
          <_TEoListBase_Items>
            <EoArticleSell Type="TEoArticleSell">
              <ArticleId Type="TEoKeyIntInfraMx">
                <Id>-1</Id>
              </ArticleId>
              <ArticleIdForeign Type="TEoKeyIntInfraMx">
                <Id>{DISFOOD_ARTNR}</Id>
              </ArticleIdForeign>
              <Deleted>False</Deleted>
              <Number>{colli}.0</Number>
              <NumberRaw>{colli}.0</NumberRaw>
              <NumberManual>True</NumberManual>
              <Minimum>{bedrag}</Minimum>
              <PriceManual>True</PriceManual>
              <SortOrder>0</SortOrder>
              <ShowOnInvoice>True</ShowOnInvoice>
            </EoArticleSell>
          </_TEoListBase_Items>
        </ArticlesSell>
        <Goods Type="TEoGoodMxList">
          <_TEoListBase_Items>
            <EoGoodMx Type="TEoGoodMx">
              <GoodId Type="TEoKeyIntInfraMx">
                <Id>-1</Id>
              </GoodId>
              <Packing Type="TEoPackingMx">
                <Name>Colli</Name>
              </Packing>
              <Comments>Totaal geladen colli</Comments>
              <Parts>{colli}.0</Parts>
              <Weight>1.0</Weight>
              <Volume>0.0</Volume>
              <VolumeWeight>0.0</VolumeWeight>
              <ArticleWeight>0.0</ArticleWeight>
              <Depth>0.0</Depth>
              <Height>0.0</Height>
              <Width>0.0</Width>
            </EoGoodMx>
          </_TEoListBase_Items>
        </Goods>
        <Tasks Type="TEoTaskMxList">
          <WaitGetMinutes>0</WaitGetMinutes>
          <WaitBringMinutes>0</WaitBringMinutes>
          <WaitAllMinutes>0</WaitAllMinutes>
          <_TEoListBase_Items>
            <EoTaskMx Type="TEoTaskMx">
              <TaskId Type="TEoKeyIntInfraMx">
                <Id>-1</Id>
              </TaskId>
              <Address Type="TEoAddress">
                <Name>{LOKALIST_ADRES["Name"]}</Name>
                <Street>{LOKALIST_ADRES["Street"]}</Street>
                <Number>{LOKALIST_ADRES["Number"]}</Number>
                <PostalCode>{LOKALIST_ADRES["PostalCode"]}</PostalCode>
                <Place>{LOKALIST_ADRES["Place"]}</Place>
                <Country>{LOKALIST_ADRES["Country"]}</Country>
                <CountryCode>{LOKALIST_ADRES["CountryCode"]}</CountryCode>
              </Address>
              <Completion Type="TEoCompletion">
                <Actual Type="TEoDateTimeWindow">
                  <DateTimeBegin>{moment_str}</DateTimeBegin>
                  <DateTimeEnd>{moment_str}</DateTimeEnd>
                </Actual>
              </Completion>
              <Instructions>{instr_esc}</Instructions>
              <ReferenceYour>{saxutils.escape(kenmerk)}</ReferenceYour>
              <Requested Type="TEoDateTimeWindow">
                <DateTimeBegin>{gewenst_begin}</DateTimeBegin>
                <DateTimeEnd>{gewenst_einde}</DateTimeEnd>
              </Requested>
              <TaskTypeId Type="TEoKeyIntInfraMx">
                <Id>1</Id>
              </TaskTypeId>
              <TaskStateId Type="TEoKeyIntInfraMx">
                <Id>1800</Id>
              </TaskStateId>
              <TaskProblemId Type="TEoKeyIntInfraMx">
                <Id>0</Id>
              </TaskProblemId>
            </EoTaskMx>
          </_TEoListBase_Items>
        </Tasks>
        <GoodsToTasks Type="TEoGoodToTaskMxList">
          <_TEoListBase_Items>
            <EoGoodToTaskMx Type="TEoGoodToTaskMx">
              <GoodId Type="TEoKeyIntInfraMx">
                <Id>-1</Id>
              </GoodId>
              <TaskId Type="TEoKeyIntInfraMx">
                <Id>-1</Id>
              </TaskId>
            </EoGoodToTaskMx>
          </_TEoListBase_Items>
        </GoodsToTasks>
        <InvoiceStatusId>2</InvoiceStatusId>
        <ExternalDone>True</ExternalDone>
        <ExternalSource>0</ExternalSource>
      </EoOrderMx>
    </_TEoListBase_Items>
  </Data>
</EoCustomLinkStoreOrdersNormal>"""
