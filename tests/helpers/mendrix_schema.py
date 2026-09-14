"""Minimaal, synthetisch MendriX-schema plus seed-helpers voor LocalDB-tests.

Gedeeld door de tests die de echte querytekst uitvoeren
(`test_adres_groepering_localdb.py` en `test_periode_groepering_localdb.py`).
Juist omdát beide tests op dezelfde tabellen en dezelfde taken draaien, zegt het
iets als het weekrapport en het jaar-/maandoverzicht tot hetzelfde antwoord
komen — dat is wat `tests/unit/test_adres_groepering_drift.py` op tekstniveau
bewaakt en hier op gedrag.

Alleen de kolommen die de queries aanraken staan erin; MendriX zelf heeft er
veel meer.
"""

CLIENT_NO = 4787  # De Lokalist
ART_NO = 16  # DISFOOD

SCHEMA_SQL = """
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

# De staffel zoals De Lokalist hem voor DISFOOD heeft: 1-4 (EUR 15,39) en
# 4-7 (EUR 19,85). Met die grenzen maakt samenvoegen zichtbaar verschil --
# 2 + 3 colli blijven los allebei in 1-4 hangen, samen komen ze in 4-7.
# De artikeltrede wordt geleend via GraduateArticleId, net als in productie.
STAFFEL_SQL = f"""
INSERT INTO dbo.arts (ArtNo, ArtCode) VALUES ({ART_NO}, 'DISFOOD');

INSERT INTO dbo.artsGraduates (GraduateId, ArtNo, NumberFirst, NumberLast, Minimum, Price)
VALUES (1, {ART_NO}, 1, 4, 99.99, 99.99);

INSERT INTO dbo.clisartsGraduates
    (ClientNo, ArtNo, GraduateArticleId, NumberFirst, NumberLast, Minimum, Price)
VALUES
    ({CLIENT_NO}, {ART_NO}, 1,    NULL, NULL, 15.39, 15.39),
    ({CLIENT_NO}, {ART_NO}, NULL, 4,    7,    19.85, 19.85);
"""


def taak_sql(
    *,
    order_id: int,
    taak_no: int,
    tasktype: int,
    naam: str,
    straat: str,
    postcode: str,
    plaats: str,
    colli: int,
    datum,
    catchword: str | None = None,
) -> str:
    """Eén order met één laad- of lostaak op het opgegeven adres.

    `catchword` vult `Orders.CatchWord`; met 'Verzamelorder' bouw je de
    samenvattende order die dit project zelf per week in MendriX aanmaakt.
    """
    good = taak_no
    cw = "NULL" if catchword is None else f"'{catchword}'"
    return f"""
INSERT INTO dbo.Orders (OrderId, ClientNo, Amount, CatchWord, Cancelled, Deleted)
VALUES ({order_id}, {CLIENT_NO}, 0, {cw}, 0, 0);

INSERT INTO dbo.ordsubtask
    (OrdSubTaskNo, OrderId, TaskType, Deleted, MomentDone, RefYour,
     LocName, LocStreet, LocZip, LocCity)
VALUES ({taak_no}, {order_id}, {tasktype}, 0, '{datum.isoformat()}', NULL,
        '{naam}', '{straat}', '{postcode}', '{plaats}');

INSERT INTO dbo.Goods (GoodId, ColliPacking, ColliAmount) VALUES ({good}, 'Colli', {colli});
INSERT INTO dbo.GoodsToTasks (OrderId, TaskId, GoodId) VALUES ({order_id}, {taak_no}, {good});
"""
