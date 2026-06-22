/* ============================================================
   Spoedorders De Lokalist (ClientNo 4787) - HELE WEEK
   Detectie: een order is spoed als aan EEN van de volgende voorwaarden wordt voldaan:
     1. CatchWord LIKE '%spoed%' EN Orders.Amount wijkt af van staffeltarief
     2. Laden EN lossen in dezelfde order op dezelfde dag (IsSameDag) EN Amount wijkt af

   Retourneert per spoedorder:
     Datum, OrderId, VanNaam, VanAdres, NaarNaam, NaarAdres,
     LadenColli (alleen geladen colli), SpoedTarief
   ============================================================ */

SET DATEFIRST 1;

DECLARE @ClientNo    INT = 4787;
DECLARE @WeekNumber  INT = 24;   -- <<< dynamisch ingevuld door Python
DECLARE @Year        INT = 2026; -- <<< dynamisch ingevuld door Python
DECLARE @ArtCode     VARCHAR(8) = 'DISFOOD';
DECLARE @ArtNo       INT = (SELECT TOP 1 ArtNo FROM dbo.arts WHERE ArtCode = @ArtCode);

-- ISO-weekgrenzen (zelfde berekening als hoofd-query)
DECLARE @JanFourth   DATE = DATEFROMPARTS(@Year, 1, 4);
DECLARE @MondayWeek1 DATE = DATEADD(DAY, -(DATEPART(WEEKDAY, @JanFourth) - 1), @JanFourth);
DECLARE @WeekStart   DATE = DATEADD(WEEK, @WeekNumber - 1, @MondayWeek1);
DECLARE @WeekEnd     DATE = DATEADD(DAY, 6, @WeekStart);

;WITH Staffel AS (
    -- Zelfde staffel-CTE als hoofd-query (COALESCE voor client-override)
    SELECT
        COALESCE(cg.NumberFirst, ag.NumberFirst) AS NumberFirst,
        COALESCE(cg.NumberLast,  ag.NumberLast)  AS NumberLast,
        COALESCE(cg.Minimum,     ag.Minimum)     AS Minimum
    FROM dbo.clisartsGraduates cg
    LEFT JOIN dbo.artsGraduates ag ON ag.GraduateId = cg.GraduateArticleId
    WHERE cg.ClientNo = @ClientNo AND cg.ArtNo = @ArtNo

    UNION ALL

    SELECT NumberFirst, NumberLast, Minimum
    FROM dbo.artsGraduates
    WHERE ArtNo = @ArtNo
      AND NOT EXISTS (
          SELECT 1 FROM dbo.clisartsGraduates
          WHERE ClientNo = @ClientNo AND ArtNo = @ArtNo
      )
),
OrderColli AS (
    -- Colli per order + spoed-indicatoren:
    -- LadenColli: alleen geladen colli (voor staffelvergelijking en weergave)
    -- IsSameDag: 1 als laden EN lossen binnen dezelfde order op dezelfde dag
    SELECT
        o.OrderId,
        o.Amount   AS SpoedTarief,
        o.CatchWord,
        ISNULL(SUM(CASE WHEN ost.TaskType = 1 THEN g.ColliAmount ELSE 0 END), 0) AS LadenColli,
        MIN(CAST(ost.MomentDone AS DATE)) AS Datum,
        CASE
            WHEN MIN(CAST(ost.MomentDone AS DATE)) = MAX(CAST(ost.MomentDone AS DATE))
             AND SUM(CASE WHEN ost.TaskType = 1 THEN 1 ELSE 0 END) > 0
             AND SUM(CASE WHEN ost.TaskType = 2 THEN 1 ELSE 0 END) > 0
            THEN 1
            ELSE 0
        END AS IsSameDag
    FROM dbo.Orders o
    INNER JOIN dbo.ordsubtask ost
        ON ost.OrderId = o.OrderId AND ost.Deleted = 0
    LEFT JOIN dbo.GoodsToTasks gtt
        ON gtt.OrderId = o.OrderId AND gtt.TaskId = ost.OrdSubTaskNo
    LEFT JOIN dbo.Goods g
        ON g.GoodId = gtt.GoodId
    WHERE o.ClientNo  = @ClientNo
      AND o.Cancelled = 0
      AND o.Deleted   = 0
      AND ost.MomentDone IS NOT NULL
      AND CAST(ost.MomentDone AS DATE) >= @WeekStart
      AND CAST(ost.MomentDone AS DATE) <= @WeekEnd
    GROUP BY o.OrderId, o.Amount, o.CatchWord
),
VanAdres AS (
    -- Eerste laden-taak per order = vertrekadres
    SELECT
        ost.OrderId,
        ost.LocName   AS VanNaam,
        ISNULL(ost.LocStreet, '') + ', ' + ISNULL(ost.LocZip, '') + ' ' + ISNULL(ost.LocCity, '') AS VanAdres,
        ROW_NUMBER() OVER (PARTITION BY ost.OrderId ORDER BY ost.OrdSubTaskNo) AS rn
    FROM dbo.ordsubtask ost
    WHERE ost.TaskType = 1 AND ost.Deleted = 0
),
NaarAdres AS (
    -- Eerste lossen-taak per order = bestemmingsadres
    SELECT
        ost.OrderId,
        ost.LocName   AS NaarNaam,
        ISNULL(ost.LocStreet, '') + ', ' + ISNULL(ost.LocZip, '') + ' ' + ISNULL(ost.LocCity, '') AS NaarAdres,
        ROW_NUMBER() OVER (PARTITION BY ost.OrderId ORDER BY ost.OrdSubTaskNo) AS rn
    FROM dbo.ordsubtask ost
    WHERE ost.TaskType = 2 AND ost.Deleted = 0
)
SELECT
    oc.Datum,
    oc.OrderId,
    ISNULL(va.VanNaam, '')  AS VanNaam,
    ISNULL(va.VanAdres, '') AS VanAdres,
    ISNULL(na.NaarNaam, '')  AS NaarNaam,
    ISNULL(na.NaarAdres, '') AS NaarAdres,
    oc.LadenColli           AS TotaalColli,
    oc.SpoedTarief
FROM OrderColli oc
LEFT JOIN VanAdres  va ON va.OrderId = oc.OrderId AND va.rn = 1
LEFT JOIN NaarAdres na ON na.OrderId = oc.OrderId AND na.rn = 1
LEFT JOIN Staffel    s ON oc.LadenColli >= s.NumberFirst
                       AND oc.LadenColli <  s.NumberLast
WHERE oc.SpoedTarief IS NOT NULL
  AND (s.Minimum IS NULL OR ABS(oc.SpoedTarief - s.Minimum) > 0.001)
  AND (oc.CatchWord LIKE '%spoed%' OR oc.IsSameDag = 1)
ORDER BY oc.Datum, oc.OrderId;
