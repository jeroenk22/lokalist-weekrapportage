-- Verzamelorders van De Lokalist voor het webdashboard.
--
-- Een verzamelorder is herkenbaar aan CatchWord = 'Verzamelorder' (in de
-- store-XML het veld <Reference>). Dit is hetzelfde kenmerk waarop
-- lokalist_staffel_overzicht.sql verzamelorders juist UITSLUIT, zodat een
-- verzamelorder nooit in zijn eigen weekrapport terechtkomt.
--
-- Kenmerk komt uit ordsubtask.RefYour en bevat 'Week <nr> <jaar>'.
-- Notities komt uit Orders.Diversen; dat is de kolom achter het <Notes>-element
-- in de order-XML en bevat de HANDMATIG-markering bij hergenereerde rapporten.
--
-- Het strikt filteren en parsen van het kenmerk gebeurt in Python
-- (query.haal_verzamelorders_op), zodat afwijkende kenmerken zoals het
-- jaaroverzicht ('week 1 t/m 24, 2026') buiten de lijst blijven.
--
-- InvKey verwijst naar de factuur waarop deze order staat. Is die gevuld, dan
-- mag de order NIET hergenereerd worden: hergenereren verwijdert de order en
-- maakt een nieuwe met een ander ordernummer aan, waardoor de factuurregel naar
-- een verdwenen order zou wijzen. Waargenomen waarden: InvStatus 2 = nog niet
-- gefactureerd (InvKey leeg), InvStatus 20 = gefactureerd (InvKey gevuld).
--
-- Het factuurnummer dat Miedema zelf hanteert is invoices.InvNo (bijv. 31511432),
-- niet de interne sleutel InvKey. MendriX kent InvNo pas toe zodra de factuur
-- definitief gemaakt is; bij een concept-factuur bestaat de factuurregel wel
-- (InvKey gevuld, Exported = 0) maar is InvNo nog leeg. Beide gevallen blokkeren
-- het hergenereren — ook een conceptrun raakt van slag als de order verdwijnt.

DECLARE @ClientNo INT = 4787;

SELECT
    o.OrderId                                   AS OrderId,
    o.Moment                                    AS Aangemaakt,
    ISNULL(o.Diversen, '')                      AS Notities,
    ISNULL(o.GoodAmount, 0)                     AS TotaalColli,
    ISNULL(o.Amount, 0)                         AS TotaalBedrag,
    o.InvKey                                    AS FactuurSleutel,
    f.InvNo                                     AS FactuurNummer,
    f.InvYearNo                                 AS FactuurJaar,
    ISNULL(o.InvStatus, 0)                      AS FactuurStatus,
    ISNULL(k.Kenmerk, '')                       AS Kenmerk
FROM dbo.Orders o
LEFT JOIN dbo.invoices f
    ON f.InvKey = o.InvKey
OUTER APPLY (
    SELECT TOP 1 ISNULL(t.RefYour, '') AS Kenmerk
    FROM dbo.ordsubtask t
    WHERE t.OrderId = o.OrderId
      AND t.Deleted = 0
    ORDER BY t.OrdSubTaskNo
) k
WHERE o.ClientNo = @ClientNo
  AND ISNULL(o.CatchWord, '') = 'Verzamelorder'
  AND o.Deleted = 0
  AND o.Cancelled = 0
ORDER BY o.Moment DESC;
