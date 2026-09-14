/* ============================================================
   Overzicht laad/los-taken De Lokalist (ClientNo 4787) - PERIODE
   Versie voor jaaroverzicht: accepteert @DateStart/@DateEnd i.p.v. weeknummer.
   Geen spoed-filter; alle afgesloten taken worden meegenomen.

   Groepeert net als het weekrapport op het genormaliseerde ADRES en niet op
   de bedrijfsnaam, zodat het jaartotaal gelijk blijft aan de som van de
   weekrapporten. Zie de header van lokalist_staffel_overzicht.sql voor het
   waarom; het TaakNamen/AdresTotalen-blok hieronder is letterlijk hetzelfde
   en wordt bewaakt door tests/unit/test_adres_groepering_drift.py.
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
        ISNULL(SUM(CASE WHEN g.ColliPacking = 'Colli' THEN g.ColliAmount ELSE 0 END), 0) AS ColliPerTaak,
        -- Genormaliseerd adres: hoofdletters en spaties weg. Hetzelfde adres
        -- staat in MendriX soms net anders gespeld ('3417 MN' naast '3417MN',
        -- 'Dochterenseweg 13 A' naast 'Dochterenseweg 13A'). Dat is een stop,
        -- en mag het rapport niet in twee regels met elk een eigen tarief
        -- splitsen.
        UPPER(REPLACE(ISNULL(ost.LocStreet, ''), ' ', ''))
            + '|' + UPPER(REPLACE(ISNULL(ost.LocZip, ''), ' ', ''))
            + '|' + UPPER(REPLACE(ISNULL(ost.LocCity, ''), ' ', '')) AS AdresSleutel
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
      -- Dezelfde uitsluiting als het weekrapport. De verzamelorders die dit
      -- script zelf per week aanmaakt staan met CatchWord 'Verzamelorder' in
      -- MendriX, op het laadadres van De Lokalist, met de colli van de HELE
      -- week erop. Telden ze mee, dan stond de weekomzet er een tweede keer
      -- in als los 'adres'.
      AND ISNULL(o.CatchWord, '') <> 'Verzamelorder'
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
TaakNamen AS (
    -- Markeert per adres + dag + taaktype de EERSTE taak van elke unieke
    -- bedrijfsnaam. AdresTotalen gebruikt dat om elke naam precies een keer in
    -- de komma-gescheiden naamlijst te zetten; STRING_AGG kent geen DISTINCT.
    SELECT
        tc.*,
        ROW_NUMBER() OVER (
            PARTITION BY tc.Datum, tc.TaskType, tc.AdresSleutel, tc.LocName
            ORDER BY tc.OrdSubTaskNo
        ) AS NaamRang
    FROM TaskColli tc
),
AdresTotalen AS (
    -- Optellen per adres + type (laden/lossen) + datum, over meerdere
    -- orders/taken heen. Bewust NIET op LocName groeperen (zie de header):
    -- hetzelfde adres onder een andere bedrijfsnaam is dezelfde stop. De namen
    -- worden alfabetisch en komma-gescheiden samengevoegd, elk precies een
    -- keer (NaamRang = 1).
    -- Van het adres zelf wordt MIN() genomen: binnen een AdresSleutel
    -- verschillen de varianten alleen in spaties en hoofdletters, dus welke
    -- variant je toont maakt inhoudelijk niet uit -- MIN houdt de keuze in elk
    -- geval stabiel tussen runs.
    SELECT
        Datum,
        TaskType,
        STRING_AGG(CASE WHEN NaamRang = 1 THEN LocName END, ', ')
            WITHIN GROUP (ORDER BY LocName)            AS LocName,
        MIN(LocStreet)                                 AS LocStreet,
        MIN(LocZip)                                    AS LocZip,
        MIN(LocCity)                                   AS LocCity,
        SUM(ColliPerTaak)                              AS TotaalColli,
        COUNT(*)                                       AS AantalTaken,
        STRING_AGG(CAST(OrderId AS VARCHAR(20)), ', ') AS OrderNummers
    FROM TaakNamen
    GROUP BY Datum, TaskType, AdresSleutel
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
