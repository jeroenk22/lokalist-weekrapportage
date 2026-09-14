"""Voert de echte periode-query (`lokalist_periode_overzicht.sql`) uit tegen een
draaiende SQL Server LocalDB — geen mock van pyodbc, geen kopie van de querytekst.

Die query voedt `scripts/run_jaaroverzicht.py`, het jaar- en maandoverzicht.
Tot nu toe werd hij nergens uitgevoerd: `tests/unit/test_adres_groepering_drift.py`
vergelijkt alleen de tékst van het gedeelde TaakNamen/AdresTotalen-blok. Deze
test controleert het gedrag, en bewaakt twee dingen:

1. **Dezelfde adresgroepering als het weekrapport.** Een adres met meerdere
   bedrijfsnamen, of met een afwijkende schrijfwijze, hoort ook hier één regel
   met één staffeltarief te zijn.
2. **Verzamelorders tellen niet mee.** De samenvattende order die dit project
   zelf per week in MendriX aanmaakt (`CatchWord = 'Verzamelorder'`) staat op
   het laadadres van De Lokalist met de colli van de HELE week erop. Die stond
   hier eerder als los laadadres in het overzicht, waardoor de weekomzet een
   tweede keer meetelde — en na het groeperen op adres werd hij zelfs met de
   echte taken op dat adres samengevoegd.

De seed komt uit `tests/helpers/mendrix_schema.py`, dezelfde als
`test_adres_groepering_localdb.py` gebruikt. Juist daardoor zegt het iets als
beide queries op identieke data tot hetzelfde antwoord komen.

Vereist een lokale SQL Server LocalDB-instantie van 2017 of nieuwer (marker:
sql_localdb); zie tests/README.md.
"""

import uuid
from datetime import date

import pytest

from lokalist_weekrapportage.query import _parametriseer_periode_sql
from tests.helpers.localdb import connect, master_connectie_of_skip, vereis_string_agg_of_skip
from tests.helpers.mendrix_schema import SCHEMA_SQL, STAFFEL_SQL, taak_sql

pytestmark = pytest.mark.sql_localdb

_JAAR = 2026
_MAANDAG = date.fromisocalendar(_JAAR, 24, 1)
_DINSDAG = date.fromisocalendar(_JAAR, 24, 2)

# De periode loopt bewust ruimer dan de taken zelf, zodat de datumgrenzen niet
# toevallig meebepalen wat er in het resultaat zit.
_PERIODE_START = date.fromisocalendar(_JAAR, 23, 1).isoformat()
_PERIODE_EIND = date.fromisocalendar(_JAAR, 25, 7).isoformat()

# Twee namen op hetzelfde adres, los 3 + 2 colli (beide trede 1-4, EUR 15,39),
# samen 5 colli in trede 4-7 (EUR 19,85). Hetzelfde geval als in het weekrapport.
_HAARLEM = [
    taak_sql(
        order_id=301,
        taak_no=3011,
        tasktype=2,
        naam="Oogst Haarlem B.V.",
        straat="Gierstraat 14",
        postcode="2011GD",
        plaats="Haarlem",
        colli=3,
        datum=_MAANDAG,
    ),
    taak_sql(
        order_id=302,
        taak_no=3021,
        tasktype=2,
        naam="Oogst Haarlem",
        straat="Gierstraat 14",
        postcode="2011GD",
        plaats="Haarlem",
        colli=2,
        datum=_MAANDAG,
    ),
]

# Het echte Laren-geval: een verzamelorder van 23 colli op dezelfde dag en
# hetzelfde adres als een gewone laadtaak van 4 colli (vergelijk order 1246983
# op 24-6-2026). Telt de verzamelorder mee, dan wordt het samen 27 colli --
# boven de staffel, en deze query kent geen fallback, dus dan valt het tarief
# terug op niets.
_LAREN = [
    taak_sql(
        order_id=303,
        taak_no=3031,
        tasktype=1,
        naam="Burgerboerderij de Patrijs",
        straat="Dochterenseweg 13A",
        postcode="7245 NN",
        plaats="Laren",
        colli=4,
        datum=_DINSDAG,
    ),
    taak_sql(
        order_id=304,
        taak_no=3041,
        tasktype=1,
        naam="De Lokalist",
        straat="Dochterenseweg 13A",
        postcode="7245 NN",
        plaats="Laren",
        colli=23,
        datum=_DINSDAG,
        catchword="Verzamelorder",
    ),
]


@pytest.fixture(scope="module")
def periode_db():
    master_conn = master_connectie_of_skip()
    db_naam = f"LokalistPeriode_{uuid.uuid4().hex[:8]}"
    master_conn.execute(f"CREATE DATABASE [{db_naam}]")
    master_conn.close()

    conn = None
    try:
        conn = connect(db_naam)
        vereis_string_agg_of_skip(conn)
        conn.execute(SCHEMA_SQL)
        conn.execute(STAFFEL_SQL)
        for taak in _HAARLEM + _LAREN:
            conn.execute(taak)

        yield conn
    finally:
        if conn is not None:
            conn.close()
        opruim_conn = connect("master")
        opruim_conn.execute(f"ALTER DATABASE [{db_naam}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        opruim_conn.execute(f"DROP DATABASE [{db_naam}]")
        opruim_conn.close()


@pytest.fixture(scope="module")
def resultaat(periode_db) -> list:
    sql = _parametriseer_periode_sql(_PERIODE_START, _PERIODE_EIND)
    return periode_db.execute(sql).fetchall()


def test_zelfde_adres_andere_naam_wordt_ook_hier_een_regel(resultaat):
    rijen = [r for r in resultaat if r.LocCity == "Haarlem"]
    assert len(rijen) == 1
    assert rijen[0].LocName == "Oogst Haarlem, Oogst Haarlem B.V."


def test_samengevoegde_colli_bepalen_ook_hier_de_staffeltrede(resultaat):
    rij = [r for r in resultaat if r.LocCity == "Haarlem"][0]
    assert (int(rij.TotaalColli), int(rij.AantalTaken)) == (5, 2)
    assert rij.Staffeltrede == "4 tot 7"
    assert float(rij.StaffelTarief) == 19.85


def test_verzamelorder_telt_niet_mee(resultaat):
    # De verzamelorder van 23 colli mag het overzicht niet in; hij is een
    # samenvatting van wat er verder al in staat.
    assert all("Verzamelorder" not in (r.LocName or "") for r in resultaat)
    assert all(int(r.TotaalColli) != 23 for r in resultaat)


def test_verzamelorder_wordt_niet_met_het_adres_samengevoegd(resultaat):
    # Dit is de regressie: na het groeperen op adres viel de verzamelorder op
    # dezelfde dag en hetzelfde adres als de echte taak. Samen 27 colli, boven
    # de staffel, en deze query heeft geen fallback -- dus geen tarief meer.
    rijen = [r for r in resultaat if r.LocCity == "Laren"]
    assert len(rijen) == 1
    rij = rijen[0]
    assert rij.LocName == "Burgerboerderij de Patrijs"
    assert (int(rij.TotaalColli), int(rij.AantalTaken)) == (4, 1)
    assert rij.Staffeltrede == "4 tot 7"
    assert float(rij.StaffelTarief) == 19.85


def test_periodegrenzen_worden_echt_toegepast(resultaat, periode_db):
    # Vangt af dat de test groen blijft doordat _parametriseer_periode_sql de
    # DECLARE-regels niet raakt en de query op zijn eigen standaardperiode draait.
    assert resultaat, "binnen de periode horen er rijen te zijn"

    buiten = date.fromisocalendar(_JAAR, 30, 1).isoformat()
    leeg = periode_db.execute(_parametriseer_periode_sql(buiten, buiten)).fetchall()
    assert leeg == [], "buiten de periode mag er niets terugkomen"
