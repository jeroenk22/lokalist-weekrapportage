/* ============================================================
   Overzicht laad/los-taken De Lokalist (ClientNo 4787) - PERIODE
   Versie voor jaaroverzicht: accepteert @DateStart/@DateEnd i.p.v. weeknummer.
   Geen spoed-filter; alle afgesloten taken worden meegenomen.
   ============================================================ */

SET DATEFIRST 1;

DECLARE @ClientNo INT = 4787;
DECLARE @DateStart DATE = '2026-01-01';   -- <<< AANPASSEN via Python
DECLARE @DateEnd   DATE = '2026-06-14';   -- <<< AANPASSEN via Python (t/m week 24 = 14 jun)
DECLARE @ArtCode VARCHAR(8) = 'DISFOOD';
DECLARE @ArtNo INT = (SELECT TOP 1 ArtNo FROM dbo.arts WHERE ArtCode = @ArtCode);

;WITH Staffel AS (
    SELECT
        COALESCE(cg.NumberFirst, ag_ref.NumberFirst) AS NumberFirst,
        COALESCE(cg.NumberLast,  ag_ref.NumberLast)  AS NumberLast,
        cg.Minimum,
        cg.Price
    FROM dbo.clisartsGraduates cg
    LEFT JOIN dbo.artsGraduates ag_ref ON ag_ref.GraduateId = cg.GraduateArticleId
    WHERE cg.ClientNo = @ClientNo AND cg.ArtNo = @ArtNo

    UNION ALL

    SELECT NumberFirst, NumberLast, Minimum, Price
    FROM dbo.artsGraduates
    WHERE ArtNo = @ArtNo
      AND NOT EXISTS (
          SELECT 1 FROM dbo.clisartsGraduates
          WHERE ClientNo = @ClientNo AND ArtNo = @ArtNo
      )
),
TaskColli AS (
    SELECT
        ost.OrdSubTaskNo,
        ost.OrderId,
        ost.TaskType,
        ost.LocName,
        ost.LocStreet,
        ost.LocZip,
        ost.LocCity,
        CAST(ost.MomentDone AS DATE) AS Datum,
        ISNULL(SUM(CASE WHEN g.ColliPacking = 'Colli' THEN g.ColliAmount ELSE 0 END), 0) AS ColliPerTaak
    FROM dbo.ordsubtask ost
    INNER JOIN dbo.Orders o
        ON o.OrderId = ost.OrderId
    LEFT JOIN dbo.GoodsToTasks gtt
        ON gtt.TaskId = ost.OrdSubTaskNo
       AND gtt.OrderId = ost.OrderId
    LEFT JOIN dbo.Goods g
        ON g.GoodId = gtt.GoodId
    WHERE o.ClientNo = @ClientNo
      AND o.Cancelled = 0
      AND o.Deleted = 0
      AND ost.Deleted = 0
      AND ost.MomentDone IS NOT NULL
      AND ost.MomentDone >= @DateStart
      AND ost.MomentDone <  DATEADD(DAY, 1, @DateEnd)
    GROUP BY
        ost.OrdSubTaskNo, ost.OrderId, ost.TaskType,
        ost.LocName, ost.LocStreet, ost.LocZip, ost.LocCity,
        CAST(ost.MomentDone AS DATE)
    HAVING ISNULL(SUM(CASE WHEN g.ColliPacking = 'Colli' THEN g.ColliAmount ELSE 0 END), 0) > 0
),
AdresTotalen AS (
    SELECT
        Datum,
        TaskType,
        LocName,
        LocStreet,
        LocZip,
        LocCity,
        SUM(ColliPerTaak)                                              AS TotaalColli,
        COUNT(*)                                                        AS AantalTaken,
        STRING_AGG(CAST(OrderId AS VARCHAR(20)), ', ')                 AS OrderNummers
    FROM TaskColli
    GROUP BY Datum, TaskType, LocName, LocStreet, LocZip, LocCity
)
SELECT
    at.Datum,
    at.TaskType,
    CASE at.TaskType
        WHEN 1 THEN 'Laden'
        WHEN 2 THEN 'Lossen'
        ELSE 'Onbekend (' + CAST(at.TaskType AS VARCHAR(10)) + ')'
    END                                  AS TaskTypeNaam,
    at.LocName,
    at.LocStreet,
    at.LocZip,
    at.LocCity,
    at.TotaalColli,
    at.AantalTaken,
    at.OrderNummers,
    CASE
        WHEN cg.NumberFirst IS NULL THEN NULL
        ELSE CAST(CAST(cg.NumberFirst AS INT) AS VARCHAR(10))
             + ' tot '
             + CAST(CAST(cg.NumberLast AS INT) AS VARCHAR(10))
    END                                  AS Staffeltrede,
    cg.Minimum                           AS StaffelTarief
FROM AdresTotalen at
LEFT JOIN Staffel cg
    ON at.TotaalColli >= cg.NumberFirst
   AND at.TotaalColli <  cg.NumberLast
ORDER BY at.Datum, at.LocCity, at.TaskType;
