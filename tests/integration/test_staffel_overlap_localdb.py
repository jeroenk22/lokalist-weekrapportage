"""Voert de echte staffel-tie-break-SQL uit tegen een draaiende SQL Server
LocalDB-instantie — geen mock van pyodbc, geen kopie van de queryskelet-tekst.

Beschermt tegen regressie op de fix uit #18: bij overlappende staffeltredes
(De Lokalist/DISFOOD heeft bewust zowel 10-14 als 10-15) moet de trede met
het HOOGSTE tarief winnen, via `OUTER APPLY ... ORDER BY Minimum DESC`.

De Staffel-CTE en het OUTER APPLY-blok worden letterlijk uit
lokalist_staffel_overzicht.sql geëxtraheerd (tests/helpers/sql_extract.py) en
tegen een minimaal, synthetisch schema uitgevoerd — zo test dit de
daadwerkelijke queryskelet-tekst, niet een losse kopie.

Vereist een lokale SQL Server LocalDB-instantie (marker: sql_localdb). Zonder
LocalDB/ODBC-driver wordt lokaal geskipt; in CI faalt de test hard (zie
tests/helpers/localdb.py).
"""

import uuid

import pytest

from tests.helpers.localdb import connect, master_connectie_of_skip
from tests.helpers.sql_extract import haal_outer_apply_blok, haal_staffel_cte_body

pytestmark = pytest.mark.sql_localdb

_CLIENT_NO = 4787  # De Lokalist
_ART_NO = 16  # DISFOOD

_SCHEMA_SQL = """
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
"""

# De echte, bevestigde situatie (zie #18): standaardtrede 10-15 (bewust laag
# tarief, geleend bereik via GraduateArticleId) overlapt met De Lokalists
# eigen trede 10-14 (hoger tarief, eigen bereik). MendriX -en dus ook dit
# rapport- kiest het hoogste tarief.
_SEED_SQL = f"""
INSERT INTO dbo.artsGraduates (GraduateId, ArtNo, NumberFirst, NumberLast, Minimum, Price)
VALUES (1, {_ART_NO}, 10, 15, 99.99, 99.99);

INSERT INTO dbo.clisartsGraduates
    (ClientNo, ArtNo, GraduateArticleId, NumberFirst, NumberLast, Minimum, Price)
VALUES
    ({_CLIENT_NO}, {_ART_NO}, 1,    NULL, NULL, 30.00, 30.00),
    ({_CLIENT_NO}, {_ART_NO}, NULL, 10,   14,   30.77, 30.77);
"""


def _bouw_test_query(staffel_cte_body: str, outer_apply_blok: str) -> str:
    return f"""
DECLARE @ClientNo INT = {_CLIENT_NO};
DECLARE @ArtNo INT = {_ART_NO};

;WITH Staffel AS (
{staffel_cte_body}
),
AdresTotalen AS (
    SELECT CAST(? AS INT) AS TotaalColli
)
SELECT cg.NumberFirst, cg.NumberLast, cg.Minimum, cg.Price
FROM AdresTotalen at
{outer_apply_blok}
;
"""


@pytest.fixture(scope="module")
def staffel_db():
    master_conn = master_connectie_of_skip()
    db_naam = f"LokalistTest_{uuid.uuid4().hex[:8]}"
    master_conn.execute(f"CREATE DATABASE [{db_naam}]")
    master_conn.close()

    conn = connect(db_naam)
    conn.execute(_SCHEMA_SQL)
    conn.execute(_SEED_SQL)

    yield conn

    conn.close()
    opruim_conn = connect("master")
    opruim_conn.execute(f"ALTER DATABASE [{db_naam}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
    opruim_conn.execute(f"DROP DATABASE [{db_naam}]")
    opruim_conn.close()


@pytest.fixture(scope="module")
def test_query() -> str:
    return _bouw_test_query(haal_staffel_cte_body(), haal_outer_apply_blok())


def _voer_uit(staffel_db, test_query: str, totaal_colli: int):
    cursor = staffel_db.execute(test_query, [totaal_colli])
    rijen = cursor.fetchall()
    assert len(rijen) == 1, "OUTER APPLY moet de buitenste rij altijd behouden (precies 1 rij)"
    return rijen[0]


def test_overlappende_tredes_kiezen_hoogste_tarief(staffel_db, test_query):
    # TotaalColli=12 valt in zowel 10-15 (€30,00) als 10-14 (€30,77).
    rij = _voer_uit(staffel_db, test_query, 12)
    assert (rij.NumberFirst, rij.NumberLast, float(rij.Minimum)) == (10, 14, 30.77)


def test_geen_overlap_gebruikt_enige_match(staffel_db, test_query):
    # TotaalColli=14 valt NIET meer in 10-14 (TOT-exclusief), wel nog in 10-15.
    rij = _voer_uit(staffel_db, test_query, 14)
    assert (rij.NumberFirst, rij.NumberLast, float(rij.Minimum)) == (10, 15, 30.00)


def test_geen_match_behoudt_adres_met_lege_staffel(staffel_db, test_query):
    # Buiten elke trede: OUTER APPLY (i.p.v. CROSS APPLY) mag het adres niet
    # laten verdwijnen uit het rapport.
    rij = _voer_uit(staffel_db, test_query, 999)
    assert rij.NumberFirst is None
    assert rij.Minimum is None
