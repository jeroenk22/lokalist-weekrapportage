/* ============================================================
   Overzicht laad/los-taken De Lokalist (ClientNo 4787) - HELE WEEK
   Gegroepeerd per dag + per adres, met staffel-tarief (DISFOOD) o.b.v. totaal colli
   ============================================================
   BEVESTIGD:
   - TaskType: 1 = Laden, 2 = Lossen (0 komt ook voor, betekenis onbekend)
   - ClientNo 4787 = De Lokalist (intern klantnummer 4159 is een ander veld)
   - Staffel werkt als "VAN TOT", dus NumberFirst INCLUSIEF, NumberLast EXCLUSIEF
     (1 TOT 4 = colli 1, 2 of 3 -> bij 4 colli geldt de volgende staffel)
   - GoodsToTasks.TaskId komt overeen met ordsubtask.OrdSubTaskNo (getest, klopt)
   - De Lokalist had eerst GEEN eigen regel in clisartsGraduates, viel toen terug
     op de generieke artsGraduates (ArtNo 16 = DISFOOD). Inmiddels heeft De
     Lokalist wel eigen regels in clisartsGraduates, maar die vullen alleen een
     nieuw bedrag (Minimum/Price) in; de van/tot-grenzen worden geleend van de
     generieke staffel via clisartsGraduates.GraduateArticleId -> artsGraduates.
     GraduateId. Het script volgt deze koppeling automatisch (COALESCE).
   - Weeknummer = ISO-weeknummer (maandag t/m zondag), onafhankelijk van DATEFIRST-
     instelling van de sessie, dankzij de handmatige berekening hieronder.
   - Geannuleerde orders (Orders.Cancelled = 1) en verwijderde orders/taken
     (Orders.Deleted of ordsubtask.Deleted = 1) worden uitgesloten.
   - Spoedorders worden door Python bepaald (via lokalist_spoed_overzicht.sql) en
     als NOT IN-lijst geïnjecteerd. Zo staat de detectie-logica op één plek.
   ============================================================ */

SET DATEFIRST 1; -- maandag = dag 1, nodig voor de weekberekening hieronder

DECLARE @ClientNo INT = 4787;
DECLARE @WeekNumber INT = 24;   -- <<< PAS HIER HET GEWENSTE WEEKNUMMER AAN (week 24 = 8-6 t/m 14-6)
DECLARE @Year INT = 2026;       -- <<< PAS HIER HET GEWENSTE JAAR AAN
DECLARE @ArtCode VARCHAR(8) = 'DISFOOD';
DECLARE @ArtNo INT = (SELECT TOP 1 ArtNo FROM dbo.arts WHERE ArtCode = @ArtCode);

-- Bereken maandag en zondag van het opgegeven ISO-weeknummer
DECLARE @JanFourth DATE = DATEFROMPARTS(@Year, 1, 4); -- 4 januari valt altijd in ISO-week 1
DECLARE @MondayWeek1 DATE = DATEADD(DAY, -(DATEPART(WEEKDAY, @JanFourth) - 1), @JanFourth);
DECLARE @WeekStart DATE = DATEADD(WEEK, @WeekNumber - 1, @MondayWeek1);   -- maandag
DECLARE @WeekEnd DATE = DATEADD(DAY, 6, @WeekStart);                      -- zondag

;WITH Staffel AS (
    -- Klant-specifieke staffel (clisartsGraduates). De override vult vaak alleen
    -- een nieuw bedrag (Minimum/Price) in en "leent" de van/tot-grenzen van de
    -- generieke staffel via GraduateArticleId -> artsGraduates.GraduateId.
    SELECT
        COALESCE(cg.NumberFirst, ag_ref.NumberFirst) AS NumberFirst,
        COALESCE(cg.NumberLast,  ag_ref.NumberLast)  AS NumberLast,
        cg.Minimum,
        cg.Price
    FROM dbo.clisartsGraduates cg
    LEFT JOIN dbo.artsGraduates ag_ref ON ag_ref.GraduateId = cg.GraduateArticleId
    WHERE cg.ClientNo = @ClientNo AND cg.ArtNo = @ArtNo

    UNION ALL

    -- Generieke staffel (artsGraduates), alleen als er GEEN klant-specifieke
    -- override bestaat voor deze klant + artikel
    SELECT NumberFirst, NumberLast, Minimum, Price
    FROM dbo.artsGraduates
    WHERE ArtNo = @ArtNo
      AND NOT EXISTS (
          SELECT 1 FROM dbo.clisartsGraduates
          WHERE ClientNo = @ClientNo AND ArtNo = @ArtNo
      )
),
TaskColli AS (
    -- Colli per individuele laad/los-taak van vandaag voor deze klant
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
      AND ost.MomentDone >= @WeekStart
      AND ost.MomentDone <  DATEADD(DAY, 1, @WeekEnd)
      AND 1=1 -- <<SPOED_IDS_FILTER>>
    GROUP BY
        ost.OrdSubTaskNo, ost.OrderId, ost.TaskType,
        ost.LocName, ost.LocStreet, ost.LocZip, ost.LocCity,
        CAST(ost.MomentDone AS DATE)
    HAVING ISNULL(SUM(CASE WHEN g.ColliPacking = 'Colli' THEN g.ColliAmount ELSE 0 END), 0) > 0
),
AdresTotalen AS (
    -- Optellen per adres + type (laden/lossen) + datum, over meerdere orders/taken heen
    SELECT
        Datum,
        TaskType,
        LocName,
        LocStreet,
        LocZip,
        LocCity,
        SUM(ColliPerTaak)              AS TotaalColli,
        COUNT(*)                        AS AantalTaken,
        STRING_AGG(CAST(OrderId AS VARCHAR(20)), ', ') AS OrderNummers
    FROM TaskColli
    GROUP BY Datum, TaskType, LocName, LocStreet, LocZip, LocCity
)
SELECT
    at.Datum,
    DATEPART(ISO_WEEK, at.Datum)        AS Weeknummer,
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
        ELSE CAST(CAST(cg.NumberFirst AS INT) AS VARCHAR(10)) + ' tot ' + CAST(CAST(cg.NumberLast AS INT) AS VARCHAR(10))
    END                                  AS Staffeltrede,
    cg.Minimum                          AS StaffelTarief
FROM AdresTotalen at
LEFT JOIN Staffel cg
    ON at.TotaalColli >= cg.NumberFirst
   AND at.TotaalColli <  cg.NumberLast
ORDER BY at.Datum, at.LocCity, at.TaskType;
