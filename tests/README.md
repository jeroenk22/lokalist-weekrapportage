# Tests

- `fixtures/` — representatieve queryresultaten (lijsten van 11-tuples) en
  voorbeeld-PDF-rijen voor genereer_rapport.py
- `helpers/` — gedeelde hulpfuncties, bijv. een fake pyodbc-cursor
- `unit/` — per module: query.py (mock pyodbc), config.py (mock env vars),
  main.py (mock query + genereer_rapport)
- `integration/` — volledige keten: fixture-rows → genereer_pdf() → PDF-bestand
  bestaat en totals kloppen (geen mocks binnen deze keten zelf)

Run met: `pytest --cov --cov-fail-under=80`

## Bekende blinde vlek: lokalist_staffel_overzicht.sql
Geen enkele test hierboven voert de echte T-SQL uit — `test_query.py` mockt
`pyodbc` volledig, dus de staffel-join-logica in
`lokalist_staffel_overzicht.sql` zelf wordt niet automatisch getest (geen
lokale/CI SQL Server beschikbaar). Wijzig je dit bestand (bijv. de
staffel-resolutie bij overlappende tredes), verifieer dan altijd handmatig
tegen echte MendriX-data — bijv. via de 103 of 105 — vóór je merget.
