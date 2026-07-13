# Tests

- `fixtures/` — representatieve queryresultaten (lijsten van 11-tuples) en
  voorbeeld-PDF-rijen voor genereer_rapport.py
- `helpers/` — gedeelde hulpfuncties, bijv. een fake pyodbc-cursor
- `unit/` — per module: query.py (mock pyodbc), config.py (mock env vars),
  main.py (mock query + genereer_rapport)
- `integration/` — volledige keten: fixture-rows → genereer_pdf() → PDF-bestand
  bestaat en totals kloppen (geen mocks binnen deze keten zelf)

Run met: `pytest --cov --cov-fail-under=80`

## lokalist_staffel_overzicht.sql: echte T-SQL tegen LocalDB
`test_query.py` mockt `pyodbc` volledig, dus die tests raken de staffel-
join-logica in `lokalist_staffel_overzicht.sql` zelf niet. Om de tie-break
bij overlappende staffeltredes (#18: hoogste tarief wint via
`OUTER APPLY ... ORDER BY Minimum DESC`) toch echt te testen, voert
`integration/test_staffel_overlap_localdb.py` de Staffel-CTE en het
OUTER APPLY-blok — letterlijk geëxtraheerd uit het .sql-bestand via
`helpers/sql_extract.py` — uit tegen een SQL Server LocalDB-instantie met
een minimaal synthetisch schema.

- Marker: `sql_localdb`. Vereist een lokale LocalDB-instantie (`SqlLocalDB.exe`,
  op Windows) en een ODBC-driver voor SQL Server.
- Zonder LocalDB wordt lokaal geskipt; in CI (env var `CI`) faalt de test
  hard i.p.v. stil te skippen — zie `helpers/localdb.py`.
- CI: draait als losse `windows-latest`-job (`sql-localdb-test` in
  `.github/workflows/ci.yml`), naast de hoofd-`test`-job op ubuntu die deze
  marker overslaat (`-m "not sql_localdb"`).
- Deze test dekt alleen de staffel-tie-break zelf (via een synthetische
  `AdresTotalen`-rij), niet de volledige keten met echte Orders/taken.
  Wijzig je iets anders aan deze SQL-file, verifieer dan nog steeds
  handmatig tegen echte MendriX-data (bijv. via 103/105) vóór je merget.
