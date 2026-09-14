"""Voert de echte staffel-query uit tegen een draaiende SQL Server LocalDB —
geen mock van pyodbc, geen kopie van de querytekst.

De query wordt via `_parametriseer_sql()` uit lokalist_staffel_overzicht.sql
geladen, dus dit test de daadwerkelijke productietekst tegen een minimaal,
synthetisch schema.

Beschermt de groepering op ADRES in plaats van op bedrijfsnaam: één fysiek
adres staat in MendriX soms onder meerdere namen — opzettelijk ("Veld 4" naast
"Lenteland cooperatie U.A." op Retsezijstraat 4) of door een schrijfwijze-
verschil ("Oogst Haarlem" naast "Oogst Haarlem B.V."). Ook het adres zelf wordt
niet altijd gelijk gespeld ("7245 NN" naast "7245NN"). Dat is één stop en hoort
dus één rapportregel met één staffeltarief te zijn, met de namen komma-
gescheiden. De seed hieronder gebruikt precies die echte gevallen.

Vereist een lokale SQL Server LocalDB-instantie (marker: sql_localdb). Zonder
LocalDB/ODBC-driver wordt lokaal geskipt; in CI faalt de test hard (zie
tests/helpers/localdb.py).
"""

import uuid
from datetime import date

import pytest

from lokalist_weekrapportage.query import _parametriseer_sql
from tests.helpers.localdb import connect, master_connectie_of_skip, vereis_string_agg_of_skip

pytestmark = pytest.mark.sql_localdb

_CLIENT_NO = 4787  # De Lokalist
_ART_NO = 16  # DISFOOD
_WEEK = 24
_JAAR = 2026

_MAANDAG = date.fromisocalendar(_JAAR, _WEEK, 1)
_DINSDAG = date.fromisocalendar(_JAAR, _WEEK, 2)

_SCHEMA_SQL = """
CREATE TABLE dbo.arts (ArtNo INT NOT NULL, ArtCode VARCHAR(8) NOT NULL);

CREATE TABLE dbo.artsGraduates (
    GraduateId  INT NOT NULL PRIMARY KEY,
    ArtNo       INT NOT NULL,
    NumberFirst INT NOT NULL,
    NumberLast  INT NOT NULL,
    Minimum     DECIMAL(10,2) NOT NULL,
    Price       DECIMAL(10,2) NOT NULL
);

CREATE TABLE dbo.clisartsGraduates (
    ClientNo          INT NOT NULL,
    ArtNo             INT NOT NULL,
    GraduateArticleId INT NULL,
    NumberFirst       INT NULL,
    NumberLast        INT NULL,
    Minimum           DECIMAL(10,2) NOT NULL,
    Price             DECIMAL(10,2) NOT NULL
);

CREATE TABLE dbo.Orders (
    OrderId   INT NOT NULL PRIMARY KEY,
    ClientNo  INT NOT NULL,
    Amount    DECIMAL(18,2) NULL,
    CatchWord VARCHAR(100) NULL,
    Cancelled TINYINT NOT NULL DEFAULT 0,
    Deleted   TINYINT NOT NULL DEFAULT 0
);

CREATE TABLE dbo.ordsubtask (
    OrdSubTaskNo INT NOT NULL PRIMARY KEY,
    OrderId      INT NOT NULL,
    TaskType     INT NOT NULL,
    Deleted      TINYINT NOT NULL DEFAULT 0,
    MomentDone   DATETIME NULL,
    RefYour      VARCHAR(100) NULL,
    LocName      VARCHAR(100) NULL,
    LocStreet    VARCHAR(100) NULL,
    LocZip       VARCHAR(20) NULL,
    LocCity      VARCHAR(100) NULL
);

CREATE TABLE dbo.GoodsToTasks (OrderId INT NOT NULL, TaskId INT NOT NULL, GoodId INT NOT NULL);

CREATE TABLE dbo.Goods (
    GoodId       INT NOT NULL PRIMARY KEY,
    ColliPacking VARCHAR(20) NULL,
    ColliAmount  INT NULL
);
"""

# Staffel zoals in productie: 1-4 (EUR 15,39) en 4-7 (EUR 19,85). Met deze
# grenzen maakt het samenvoegen zichtbaar verschil: 2 + 3 colli los blijven
# allebei in 1-4 hangen, samen (5 colli) komen ze in 4-7 terecht.
_STAFFEL_SQL = f"""
INSERT INTO dbo.arts (ArtNo, ArtCode) VALUES ({_ART_NO}, 'DISFOOD');

INSERT INTO dbo.artsGraduates (GraduateId, ArtNo, NumberFirst, NumberLast, Minimum, Price)
VALUES (1, {_ART_NO}, 1, 4, 99.99, 99.99);

INSERT INTO dbo.clisartsGraduates
    (ClientNo, ArtNo, GraduateArticleId, NumberFirst, NumberLast, Minimum, Price)
VALUES
    ({_CLIENT_NO}, {_ART_NO}, 1,    NULL, NULL, 15.39, 15.39),
    ({_CLIENT_NO}, {_ART_NO}, NULL, 4,    7,    19.85, 19.85);
"""


def _taak_sql(
    *,
    order_id: int,
    taak_no: int,
    tasktype: int,
    naam: str,
    straat: str,
    postcode: str,
    plaats: str,
    colli: int,
    datum: date,
) -> str:
    """Eén order met één laad- of lostaak op het opgegeven adres."""
    good = taak_no
    return f"""
INSERT INTO dbo.Orders (OrderId, ClientNo, Amount, CatchWord, Cancelled, Deleted)
VALUES ({order_id}, {_CLIENT_NO}, 0, NULL, 0, 0);

INSERT INTO dbo.ordsubtask
    (OrdSubTaskNo, OrderId, TaskType, Deleted, MomentDone, RefYour,
     LocName, LocStreet, LocZip, LocCity)
VALUES ({taak_no}, {order_id}, {tasktype}, 0, '{datum.isoformat()}', NULL,
        '{naam}', '{straat}', '{postcode}', '{plaats}');

INSERT INTO dbo.Goods (GoodId, ColliPacking, ColliAmount) VALUES ({good}, 'Colli', {colli});
INSERT INTO dbo.GoodsToTasks (OrderId, TaskId, GoodId) VALUES ({order_id}, {taak_no}, {good});
"""


# Het echte Haarlem-geval (week 36, 2026): twee namen op Gierstraat 14, los
# 2 + 3 colli, elk in trede 1-4 (EUR 15,39) -> samen 5 colli in trede 4-7.
_HAARLEM = [
    _taak_sql(
        order_id=201,
        taak_no=2011,
        tasktype=2,
        naam="Oogst Haarlem B.V.",
        straat="Gierstraat 14",
        postcode="2011GD",
        plaats="Haarlem",
        colli=3,
        datum=_MAANDAG,
    ),
    _taak_sql(
        order_id=202,
        taak_no=2021,
        tasktype=2,
        naam="Oogst Haarlem",
        straat="Gierstraat 14",
        postcode="2011GD",
        plaats="Haarlem",
        colli=2,
        datum=_MAANDAG,
    ),
]

# Het echte Zoelen-geval (week 37, 2026): drie lostaken op Retsezijstraat 4,
# waarvan twee onder dezelfde naam "Veld 4". Bewijst dat een naam die vaker
# voorkomt maar EEN keer in de naamlijst belandt (STRING_AGG kent geen DISTINCT).
_ZOELEN = [
    _taak_sql(
        order_id=203,
        taak_no=2031,
        tasktype=2,
        naam="Veld 4",
        straat="Retsezijstraat 4",
        postcode="4011JP",
        plaats="Zoelen",
        colli=2,
        datum=_DINSDAG,
    ),
    _taak_sql(
        order_id=204,
        taak_no=2041,
        tasktype=2,
        naam="Veld 4",
        straat="Retsezijstraat 4",
        postcode="4011JP",
        plaats="Zoelen",
        colli=1,
        datum=_DINSDAG,
    ),
    _taak_sql(
        order_id=205,
        taak_no=2051,
        tasktype=2,
        naam="Lenteland cooperatie U.A.",
        straat="Retsezijstraat 4",
        postcode="4011JP",
        plaats="Zoelen",
        colli=1,
        datum=_DINSDAG,
    ),
]

# Het echte Laren-geval (week 15, 2026): dezelfde naam op hetzelfde adres,
# maar in MendriX twee keer anders gespeld ("Dochterenseweg 13 A" / "7245 NN"
# naast "Dochterenseweg 13a" / "7245NN"). Dat leverde ook al twee tarieven op
# zonder dat er ueberhaupt een tweede bedrijfsnaam in het spel was.
_LAREN = [
    _taak_sql(
        order_id=209,
        taak_no=2091,
        tasktype=1,
        naam="Burgerboerderij de Patrijs",
        straat="Dochterenseweg 13 A",
        postcode="7245 NN",
        plaats="Laren",
        colli=3,
        datum=_MAANDAG,
    ),
    _taak_sql(
        order_id=210,
        taak_no=2101,
        tasktype=1,
        naam="Burgerboerderij de Patrijs",
        straat="Dochterenseweg 13a",
        postcode="7245NN",
        plaats="Laren",
        colli=2,
        datum=_MAANDAG,
    ),
]

# Controlegevallen die juist NIET samengevoegd mogen worden: hetzelfde bedrijf
# op een ander adres, en hetzelfde adres op een andere dag / met een ander
# taaktype.
_NIET_SAMENVOEGEN = [
    _taak_sql(
        order_id=206,
        taak_no=2061,
        tasktype=2,
        naam="Oogst Haarlem",
        straat="Zijlstraat 99",
        postcode="2011AB",
        plaats="Haarlem",
        colli=2,
        datum=_MAANDAG,
    ),
    _taak_sql(
        order_id=207,
        taak_no=2071,
        tasktype=2,
        naam="Oogst Haarlem B.V.",
        straat="Gierstraat 14",
        postcode="2011GD",
        plaats="Haarlem",
        colli=2,
        datum=_DINSDAG,
    ),
    _taak_sql(
        order_id=208,
        taak_no=2081,
        tasktype=1,
        naam="Oogst Haarlem B.V.",
        straat="Gierstraat 14",
        postcode="2011GD",
        plaats="Haarlem",
        colli=2,
        datum=_MAANDAG,
    ),
    # Zelfde straat, postcode en plaats, ander huisnummer: het normaliseren van
    # spaties mag twee buren niet op een hoop gooien.
    _taak_sql(
        order_id=211,
        taak_no=2111,
        tasktype=2,
        naam="Buurman",
        straat="Gierstraat 16",
        postcode="2011 GD",
        plaats="Haarlem",
        colli=2,
        datum=_MAANDAG,
    ),
]


@pytest.fixture(scope="module")
def adres_db():
    master_conn = master_connectie_of_skip()
    db_naam = f"LokalistAdres_{uuid.uuid4().hex[:8]}"
    master_conn.execute(f"CREATE DATABASE [{db_naam}]")
    master_conn.close()

    # try/finally: een fout in het schema of de seed mag geen database laten
    # staan op de LocalDB-instantie.
    conn = None
    try:
        conn = connect(db_naam)
        vereis_string_agg_of_skip(conn)
        conn.execute(_SCHEMA_SQL)
        conn.execute(_STAFFEL_SQL)
        for taak in _HAARLEM + _ZOELEN + _LAREN + _NIET_SAMENVOEGEN:
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
def resultaat(adres_db) -> list:
    return adres_db.execute(_parametriseer_sql(_WEEK, _JAAR)).fetchall()


def _zoek(rijen, straat: str, datum: date, tasktype_naam: str) -> list:
    return [
        r
        for r in rijen
        if r.LocStreet == straat and r.Datum == datum and r.TaskTypeNaam == tasktype_naam
    ]


def test_zelfde_adres_andere_naam_wordt_een_regel(resultaat):
    rijen = _zoek(resultaat, "Gierstraat 14", _MAANDAG, "Lossen")
    assert len(rijen) == 1, "twee namen op hetzelfde adres horen één rapportregel te zijn"


def test_namen_komma_gescheiden_en_alfabetisch(resultaat):
    rij = _zoek(resultaat, "Gierstraat 14", _MAANDAG, "Lossen")[0]
    assert rij.LocName == "Oogst Haarlem, Oogst Haarlem B.V."


def test_colli_van_beide_namen_tellen_op(resultaat):
    # 3 + 2 colli; AantalTaken telt nog steeds elke taak apart.
    rij = _zoek(resultaat, "Gierstraat 14", _MAANDAG, "Lossen")[0]
    assert (int(rij.TotaalColli), int(rij.AantalTaken)) == (5, 2)


def test_samengevoegde_colli_bepalen_de_staffeltrede(resultaat):
    # Dit is de kern: los waren het 2x trede 1-4 (EUR 15,39 elk), samen is het
    # 5 colli en dus één keer trede 4-7. Zonder deze regel zou het samenvoegen
    # alleen cosmetisch zijn.
    rij = _zoek(resultaat, "Gierstraat 14", _MAANDAG, "Lossen")[0]
    assert rij.Staffeltrede == "4 tot 7"
    assert float(rij.StaffelTarief) == 19.85


def test_ordernummers_van_beide_namen_komen_samen(resultaat):
    rij = _zoek(resultaat, "Gierstraat 14", _MAANDAG, "Lossen")[0]
    assert sorted(rij.OrderNummers.split(", ")) == ["201", "202"]


def test_dezelfde_naam_komt_maar_een_keer_in_de_lijst(resultaat):
    # Drie taken, waarvan twee onder "Veld 4": STRING_AGG kent geen DISTINCT,
    # dus zonder de NaamRang-filter zou hier "Veld 4, Veld 4, ..." staan.
    rij = _zoek(resultaat, "Retsezijstraat 4", _DINSDAG, "Lossen")[0]
    assert rij.LocName == "Lenteland cooperatie U.A., Veld 4"
    assert (int(rij.TotaalColli), int(rij.AantalTaken)) == (4, 3)


def test_adres_met_andere_schrijfwijze_wordt_samengevoegd(resultaat):
    # "Dochterenseweg 13 A"/"7245 NN" en "Dochterenseweg 13a"/"7245NN" zijn
    # hetzelfde adres; los bleven ze allebei in trede 1-4 hangen.
    rijen = [r for r in resultaat if r.LocCity == "Laren"]
    assert len(rijen) == 1
    assert (int(rijen[0].TotaalColli), int(rijen[0].AantalTaken)) == (5, 2)
    assert float(rijen[0].StaffelTarief) == 19.85


def test_naam_komt_ook_bij_schrijfwijzeverschil_maar_een_keer(resultaat):
    rij = [r for r in resultaat if r.LocCity == "Laren"][0]
    assert rij.LocName == "Burgerboerderij de Patrijs"


def test_getoond_adres_is_een_van_de_echte_varianten(resultaat):
    # AdresTotalen toont MIN() van de varianten: een waarde die echt zo in
    # MendriX staat, en stabiel tussen runs. Geen samengeraapte tekst.
    rij = [r for r in resultaat if r.LocCity == "Laren"][0]
    assert (rij.LocStreet, rij.LocZip) == ("Dochterenseweg 13 A", "7245 NN")


def test_ander_huisnummer_blijft_apart(resultaat):
    # Gierstraat 14 en 16 delen straat, postcode en plaats. Het weghalen van
    # spaties mag die niet laten samenvallen.
    rijen = [r for r in resultaat if r.LocStreet == "Gierstraat 16"]
    assert len(rijen) == 1
    assert rijen[0].LocName == "Buurman"


def test_zelfde_naam_ander_adres_blijft_apart(resultaat):
    # "Oogst Haarlem" staat ook op Zijlstraat 99: een andere stop, dus een
    # eigen regel met een eigen tarief.
    rijen = _zoek(resultaat, "Zijlstraat 99", _MAANDAG, "Lossen")
    assert len(rijen) == 1
    assert rijen[0].LocName == "Oogst Haarlem"
    assert int(rijen[0].TotaalColli) == 2


def test_zelfde_adres_andere_dag_blijft_apart(resultaat):
    rijen = _zoek(resultaat, "Gierstraat 14", _DINSDAG, "Lossen")
    assert len(rijen) == 1
    assert int(rijen[0].TotaalColli) == 2


def test_laden_en_lossen_op_hetzelfde_adres_blijven_apart(resultaat):
    # Laden en lossen zijn losse stops en horen in verschillende secties van
    # het rapport; die mogen niet op elkaar gestapeld worden.
    rijen = _zoek(resultaat, "Gierstraat 14", _MAANDAG, "Laden")
    assert len(rijen) == 1
    assert int(rijen[0].TotaalColli) == 2
