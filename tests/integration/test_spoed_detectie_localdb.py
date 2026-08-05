"""Voert de echte spoed-query uit tegen een draaiende SQL Server LocalDB —
geen mock van pyodbc, geen kopie van de querytekst.

De query wordt via `_parametriseer_spoed_sql()` uit
lokalist_spoed_overzicht.sql geladen, dus dit test de daadwerkelijke
productietekst tegen een minimaal, synthetisch schema.

Beschermt tegen twee regressies (zie issue #28):

1. **Dubbele rijen.** De Lokalist heeft voor DISFOOD bewust zowel 10-14 als
   10-15, dus bij 10 t/m 14 colli matchen er twee staffeltredes. Met een gewone
   `LEFT JOIN` kwam één spoedorder twee keer in het resultaat, en telde die
   dubbel mee in het colli- en bedragtotaal van de verzamelorder.
2. **Buiten de staffelrange als spoedcriterium.** Sinds #27 geldt boven de
   hoogste trede het tarief van díé trede. Er is dus altijd een tarief om mee
   te vergelijken, en een order boven de staffel is niet vanzelf spoed.

Plus de basisregel: zonder markering ("spoed" in CatchWord of in RefYour van
een laad-/lostaak) is een order nooit een spoedorder.

Vereist een lokale SQL Server LocalDB-instantie (marker: sql_localdb). Zonder
LocalDB/ODBC-driver wordt lokaal geskipt; in CI faalt de test hard (zie
tests/helpers/localdb.py).
"""

import uuid
from datetime import date

import pytest

from lokalist_weekrapportage.query import _parametriseer_spoed_sql
from tests.helpers.localdb import connect, master_connectie_of_skip

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
    Minimum     DECIMAL(10,2) NOT NULL
);

CREATE TABLE dbo.clisartsGraduates (
    ClientNo          INT NOT NULL,
    ArtNo             INT NOT NULL,
    GraduateArticleId INT NULL,
    NumberFirst       INT NULL,
    NumberLast        INT NULL,
    Minimum           DECIMAL(10,2) NOT NULL
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

# Dezelfde staffelopzet als in productie: de artikeltrede 10-15 wordt door de
# klant geleend via GraduateArticleId (eigen tarief EUR 30,00) en overlapt met
# de eigen tredes 10-14 en 14-17. Effectief:
#   10-15 -> 30,00   10-14 -> 30,77   14-17 -> 40,75   17-20 -> 47,13
# Bij 12 colli matchen 10-15 en 10-14; bij 14 colli matchen 10-15 en 14-17.
_STAFFEL_SQL = f"""
INSERT INTO dbo.arts (ArtNo, ArtCode) VALUES ({_ART_NO}, 'DISFOOD');

INSERT INTO dbo.artsGraduates (GraduateId, ArtNo, NumberFirst, NumberLast, Minimum)
VALUES (1, {_ART_NO}, 10, 15, 99.99);

INSERT INTO dbo.clisartsGraduates
    (ClientNo, ArtNo, GraduateArticleId, NumberFirst, NumberLast, Minimum)
VALUES
    ({_CLIENT_NO}, {_ART_NO}, 1,    NULL, NULL, 30.00),
    ({_CLIENT_NO}, {_ART_NO}, NULL, 10,   14,   30.77),
    ({_CLIENT_NO}, {_ART_NO}, NULL, 14,   17,   40.75),
    ({_CLIENT_NO}, {_ART_NO}, NULL, 17,   20,   47.13);
"""


def _order_sql(
    order_id: int,
    colli: int,
    bedrag: float,
    zelfde_dag: bool,
    catchword: str | None,
    taak_ref: str | None = None,
) -> str:
    """Bouwt één order met een laad- en een lostaak, en colli op de laadtaak."""
    laad_taak = order_id * 10 + 1
    los_taak = order_id * 10 + 2
    good = order_id
    los_datum = _MAANDAG if zelfde_dag else _DINSDAG
    cw = "NULL" if catchword is None else f"'{catchword}'"
    ref = "NULL" if taak_ref is None else f"'{taak_ref}'"

    return f"""
INSERT INTO dbo.Orders (OrderId, ClientNo, Amount, CatchWord, Cancelled, Deleted)
VALUES ({order_id}, {_CLIENT_NO}, {bedrag}, {cw}, 0, 0);

INSERT INTO dbo.ordsubtask
    (OrdSubTaskNo, OrderId, TaskType, Deleted, MomentDone, RefYour,
     LocName, LocStreet, LocZip, LocCity)
VALUES
    ({laad_taak}, {order_id}, 1, 0, '{_MAANDAG.isoformat()}', {ref},
     'Van BV', 'Straat 1', '1234AB', 'Enschede'),
    ({los_taak}, {order_id}, 2, 0, '{los_datum.isoformat()}', NULL,
     'Naar BV', 'Weg 2', '5678CD', 'Hengelo');

INSERT INTO dbo.Goods (GoodId, ColliPacking, ColliAmount) VALUES ({good}, 'Colli', {colli});
INSERT INTO dbo.GoodsToTasks (OrderId, TaskId, GoodId) VALUES ({order_id}, {laad_taak}, {good});
"""


# Elke order dekt één geval. Het verwachte aantal rijen staat in de tests zelf.
_ORDERS = [
    # tag + afwijkend tarief + zelfde dag, 12 colli: het overlapgeval
    _order_sql(101, colli=12, bedrag=99.99, zelfde_dag=True, catchword="Spoed test"),
    # tag + exact het staffeltarief (30,77 bij 12 colli) + niet zelfde dag
    _order_sql(102, colli=12, bedrag=30.77, zelfde_dag=False, catchword="Spoed test"),
    # geen tag, verder alles wat op spoed lijkt
    _order_sql(103, colli=12, bedrag=99.99, zelfde_dag=True, catchword="Gewone rit"),
    # tag via de taak + 25 colli (boven de staffel) + exact het fallback-tarief
    _order_sql(104, colli=25, bedrag=47.13, zelfde_dag=False, catchword=None, taak_ref="Spoed"),
    # tag + afwijkend tarief + niet zelfde dag, 14 colli: het tweede overlapgeval
    _order_sql(105, colli=14, bedrag=99.99, zelfde_dag=False, catchword="Spoed test"),
    # tag + exact het staffeltarief, maar wél zelfde dag
    _order_sql(106, colli=12, bedrag=30.77, zelfde_dag=True, catchword="Spoed test"),
]


@pytest.fixture(scope="module")
def spoed_db():
    master_conn = master_connectie_of_skip()
    db_naam = f"LokalistSpoed_{uuid.uuid4().hex[:8]}"
    master_conn.execute(f"CREATE DATABASE [{db_naam}]")
    master_conn.close()

    conn = connect(db_naam)
    conn.execute(_SCHEMA_SQL)
    conn.execute(_STAFFEL_SQL)
    for order in _ORDERS:
        conn.execute(order)

    yield conn

    conn.close()
    opruim_conn = connect("master")
    opruim_conn.execute(f"ALTER DATABASE [{db_naam}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
    opruim_conn.execute(f"DROP DATABASE [{db_naam}]")
    opruim_conn.close()


@pytest.fixture(scope="module")
def resultaat(spoed_db) -> list:
    sql = _parametriseer_spoed_sql(_WEEK, _JAAR)
    return spoed_db.execute(sql).fetchall()


def _order_ids(rijen) -> list[int]:
    return [int(r.OrderId) for r in rijen]


def test_overlappende_tredes_geven_geen_dubbele_rij(resultaat):
    # 12 colli valt in zowel 10-15 als 10-14. Met de oude LEFT JOIN kwam deze
    # order twee keer terug en telde hij dubbel in colli en bedrag.
    assert _order_ids(resultaat).count(101) == 1


def test_tweede_overlapgeval_geeft_ook_maar_een_rij(resultaat):
    # 14 colli valt in zowel 10-15 als 14-17.
    assert _order_ids(resultaat).count(105) == 1


def test_zonder_markering_geen_spoedorder(resultaat):
    # Order 103 is zelfde dag met een sterk afwijkend bedrag, maar mist de tag.
    assert 103 not in _order_ids(resultaat)


def test_boven_de_staffel_is_niet_vanzelf_spoed(resultaat):
    # Order 104 zit met 25 colli boven de hoogste trede en betaalt exact het
    # fallback-tarief (47,13). Vóór #28 maakte `Minimum IS NULL` hier een
    # spoedorder van.
    assert 104 not in _order_ids(resultaat)


def test_staffeltarief_zonder_zelfde_dag_is_geen_spoed(resultaat):
    # Order 102 heeft de tag, maar betaalt gewoon het staffeltarief en reed
    # over twee dagen. Geen van beide criteria gaat af.
    assert 102 not in _order_ids(resultaat)


def test_zelfde_dag_alleen_is_al_genoeg(resultaat):
    # Order 106 betaalt exact het staffeltarief, maar laadt en lost op dezelfde
    # dag. Dat criterium staat los van het tarief.
    assert _order_ids(resultaat).count(106) == 1


def test_alleen_de_verwachte_orders_komen_terug(resultaat):
    assert sorted(_order_ids(resultaat)) == [101, 105, 106]
