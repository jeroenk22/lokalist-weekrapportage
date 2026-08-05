/* ============================================================
   Spoedorders De Lokalist (ClientNo 4787) - HELE WEEK

   Detectie: de markering is altijd verplicht -
     CatchWord LIKE '%spoed%' OF RefYour LIKE '%spoed%' op een laad- of
     lostaak (TaskType 1/2). Zonder markering is het geen spoedorder.

   Plus minimaal een van:
     1. Laden EN lossen zitten in dezelfde order op dezelfde dag (IsSameDay)
     2. Orders.Amount wijkt af van het staffeltarief voor dit colli-aantal -
        een spoedorder krijgt een eigen tarief van de planning, vaak op
        km-basis, en dat wijkt per definitie af van de staffel

   Vervallen criterium "colli buiten de staffelrange": sinds #27 kent het
   staffeltarief een fallback boven de hoogste trede, en die geldt hier nu ook.
   Buiten de staffel vallen maakt een order geen spoedorder. Zie issue #28.

   Gevolg dat je moet kennen: bij LadenColli = 0 matcht geen enkele trede en
   grijpt de fallback niet (die werkt alleen naar boven), dus s.Minimum blijft
   NULL en criterium 2 kan niet afgaan. Dat treedt op bij een order waarvan de
   laadtaak in een andere week valt dan de lostaak - dan zit er in deze week
   geen laadtaak en dus geen colli. Zo'n order is bewust GEEN spoedorder: laden
   en lossen vielen niet op dezelfde dag, dus criterium 1 gaat ook niet af, en
   dan is het per definitie geen spoed. Het oude criterium "buiten
   staffelrange" haalde die order er wel uit, met 0 colli in de spoedsectie.
   Dat orders over twee rapportages gesplitst mogen worden is een vastgestelde
   keuze (zie CLAUDE.md).

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
    -- IsSameDay: 1 als laden EN lossen binnen dezelfde order op dezelfde dag
    SELECT
        o.OrderId,
        o.Amount   AS SpoedTarief,
        o.CatchWord,
        ISNULL(SUM(CASE WHEN ost.TaskType = 1 AND g.ColliPacking = 'Colli' THEN g.ColliAmount ELSE 0 END), 0) AS LadenColli,
        MIN(CAST(ost.MomentDone AS DATE)) AS Datum,
        CASE
            WHEN MIN(CAST(ost.MomentDone AS DATE)) = MAX(CAST(ost.MomentDone AS DATE))
             AND SUM(CASE WHEN ost.TaskType = 1 THEN 1 ELSE 0 END) > 0
             AND SUM(CASE WHEN ost.TaskType = 2 THEN 1 ELSE 0 END) > 0
            THEN 1
            ELSE 0
        END AS IsSameDay
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
      AND (
          o.CatchWord LIKE '%spoed%'
          OR EXISTS (
              SELECT 1 FROM dbo.ordsubtask ost2
              WHERE ost2.OrderId = o.OrderId
                AND ost2.Deleted = 0
                AND ost2.TaskType IN (1, 2)
                AND ost2.RefYour LIKE '%spoed%'
          )
      )
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
OUTER APPLY (
    -- Zelfde tie-break en fallback als het hoofdrapport (zie het OUTER APPLY
    -- in lokalist_staffel_overzicht.sql). Bij overlappende tredes wint de
    -- hoogste Minimum; matcht er geen enkele trede, dan tellen alle tredes
    -- die volledig onder het aantal liggen mee en wint daarvan opnieuw het
    -- hoogste tarief. tests/unit/test_staffel_apply_drift.py bewaakt dat dit
    -- blok gelijk blijft aan dat van het hoofdrapport.
    --
    -- LET OP: alleen dit blok is gelijk, de Staffel-CTE erboven nog niet.
    -- Die gebruikt hier COALESCE(cg.Minimum, ag.Minimum) en in het
    -- hoofdrapport kaal cg.Minimum. Bij een geleende trede zonder eigen
    -- bedrag (clisartsGraduates.Minimum is nullable en komt leeg voor)
    -- berekenen de twee queries dus een verschillend tarief. Niet het geval
    -- bij De Lokalist/DISFOOD, wel een openstaand verschil.
    --
    -- Bewust TOP (1) en geen gewone join: De Lokalist heeft voor DISFOOD
    -- zowel 10-14 als 10-15, dus bij 10 t/m 14 colli matchen er twee tredes.
    -- Een gewone join gaf daar twee identieke rijen, en die telden dubbel mee
    -- in het colli- en bedragtotaal van de verzamelorder. Zie issue #28.
    SELECT TOP (1) s.Minimum
    FROM Staffel s
    WHERE (oc.LadenColli >= s.NumberFirst AND oc.LadenColli < s.NumberLast)
       OR (NOT EXISTS (
               SELECT 1 FROM Staffel s2
               WHERE oc.LadenColli >= s2.NumberFirst
                 AND oc.LadenColli <  s2.NumberLast
           )
           AND oc.LadenColli >= s.NumberLast)
    ORDER BY s.Minimum DESC
) s
WHERE oc.SpoedTarief IS NOT NULL
  AND (
      oc.IsSameDay = 1                                    -- zelfde dag laden+lossen
      OR ABS(oc.SpoedTarief - s.Minimum) > 0.001          -- tarief wijkt af van de staffel
  )
ORDER BY oc.Datum, oc.OrderId;
