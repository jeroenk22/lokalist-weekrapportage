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
   - Overlappende staffeltredes komen bewust voor (bevestigd door Jeroen,
     13-07-2026): De Lokalist heeft voor DISFOOD zowel de standaardtrede
     10-15 als een eigen trede 10-14, met opzet een lager tarief op 10-15
     zodat MendriX die bij het bepalen van de orderprijs negeert. MendriX
     kiest in zo'n geval altijd de trede met het HOOGSTE tarief (Minimum).
     Dit rapport volgt dezelfde regel via OUTER APPLY ... ORDER BY Minimum
     DESC ... TOP (1), zodat een adres niet dubbel met verschillende tredes
     in het rapport verschijnt.
   - Een fysiek adres staat in MendriX soms onder meerdere bedrijfsnamen:
     opzettelijk (een locatie die twee handelsnamen voert, zoals "Veld 4" en
     "Lenteland cooperatie U.A." op Retsezijstraat 4) of onbedoeld door een
     schrijfwijzeverschil ("Oogst Haarlem" naast "Oogst Haarlem B.V."). Ook het
     adres zelf wordt niet altijd gelijk gespeld ('3417 MN' naast '3417MN').
     Het blijft een stop, dus het rapport groepeert op het genormaliseerde
     ADRES en niet op de naam; de namen komen komma-gescheiden in een regel te
     staan. Gevolg: de colli van die namen tellen op tot een staffeltrede en
     dus een tarief, waar dat eerder twee losse regels met elk een eigen
     tarief waren.
   - Boven de hoogste trede geldt het tarief van die hoogste trede (fallback,
     bevestigd door Jeroen 4-8-2026). MendriX zelf heeft daar GEEN vangnet:
     arts.Price van DISFOOD is 0, arts.Minimum en de clisarts-regel van 4787
     zijn leeg, dus een order boven de staffel komt in MendriX op 0 uit en
     wordt met de hand bijgeprijsd (zie order 1175375, 19 colli, handmatig
     EUR 81,50 met AnyValueManual = 1). Het rapport mag daar niet op 0
     springen; de fallback maakt zichtbaar dat de staffel in MendriX
     opgerekt moet worden i.p.v. een regel stilletjes op nul te zetten.
     Zit er ooit een gat MIDDEN in de staffel, dan pakt dezelfde fallback
     de hoogste trede die er volledig onder ligt. Dat is nu niet aan de
     orde (de staffel is aaneengesloten) en levert nog altijd een beter
     antwoord dan 0.
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
      AND ISNULL(o.CatchWord, '') <> 'Verzamelorder'
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
    -- Van het adres zelf wordt een van de echte varianten getoond, nooit
    -- samengeraapte tekst. Binnen een AdresSleutel verschillen die alleen in
    -- spaties en hoofdletters, dus de netste wint: geen dubbele spatie en geen
    -- spatie aan de kop, want dat zie je terug in de PDF. Zo wint
    -- 'Lichtschip 31' van 'Lichtschip  31'. Zijn alle varianten even net, dan
    -- beslist MIN() -- die pakt de alfabetisch eerste en levert bij postcodes
    -- vanzelf de geschreven vorm op ('7245 NN' voor '7245NN'). Is er geen
    -- enkele nette variant, dan valt COALESCE terug op MIN() over alles. In
    -- alle gevallen ligt de keuze vast, dus twee runs geven hetzelfde adres.
    SELECT
        Datum,
        TaskType,
        STRING_AGG(CASE WHEN NaamRang = 1 THEN LocName END, ', ')
            WITHIN GROUP (ORDER BY LocName)            AS LocName,
        COALESCE(MIN(CASE WHEN LocStreet NOT LIKE '%  %'
                           AND LocStreet NOT LIKE ' %' THEN LocStreet END),
                 MIN(LocStreet))                       AS LocStreet,
        COALESCE(MIN(CASE WHEN LocZip NOT LIKE '%  %'
                           AND LocZip NOT LIKE ' %' THEN LocZip END),
                 MIN(LocZip))                          AS LocZip,
        COALESCE(MIN(CASE WHEN LocCity NOT LIKE '%  %'
                           AND LocCity NOT LIKE ' %' THEN LocCity END),
                 MIN(LocCity))                         AS LocCity,
        SUM(ColliPerTaak)                              AS TotaalColli,
        COUNT(*)                                       AS AantalTaken,
        STRING_AGG(CAST(OrderId AS VARCHAR(20)), ', ') AS OrderNummers
    FROM TaakNamen
    GROUP BY Datum, TaskType, AdresSleutel
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
OUTER APPLY (
    -- Bij overlappende tredes wint de hoogste Minimum (tarief), zelfde
    -- tie-break als MendriX zelf toepast (zie header hierboven).
    -- Matcht geen enkele trede, dan tellen alle tredes die volledig onder
    -- het aantal liggen mee en wint daarvan opnieuw het hoogste tarief
    -- (fallback, zie header). Bewust niet "de trede met de grootste
    -- NumberLast": een bredere trede heeft bij deze klant juist vaak een
    -- lager tarief (10-15 naast 10-14), dus dat zou het goedkoopste tarief
    -- opleveren i.p.v. het hoogste.
    SELECT TOP (1) s.NumberFirst, s.NumberLast, s.Minimum, s.Price
    FROM Staffel s
    WHERE (at.TotaalColli >= s.NumberFirst AND at.TotaalColli < s.NumberLast)
       OR (NOT EXISTS (
               SELECT 1 FROM Staffel s2
               WHERE at.TotaalColli >= s2.NumberFirst
                 AND at.TotaalColli <  s2.NumberLast
           )
           AND at.TotaalColli >= s.NumberLast)
    ORDER BY s.Minimum DESC
) cg
ORDER BY at.Datum, at.LocCity, at.TaskType;
