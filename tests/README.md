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

## Groeperen op adres i.p.v. op bedrijfsnaam
`integration/test_adres_groepering_localdb.py` voert de **volledige**
`lokalist_staffel_overzicht.sql` (via `_parametriseer_sql()`) uit tegen LocalDB
met een synthetisch schema en echte Orders/taken. Het bewaakt dat één adres met
meerdere bedrijfsnamen — "Oogst Haarlem" naast "Oogst Haarlem B.V.", "Veld 4"
naast "Lenteland cooperatie U.A." — één rapportregel wordt met de namen
komma-gescheiden, en dat de colli daardoor optellen tot één staffeltrede.
Hetzelfde geldt voor een adres dat alleen anders gespeld is ("7245 NN" naast
"7245NN"); een ander huisnummer mag juist níét samenvallen.

`integration/test_periode_groepering_localdb.py` doet hetzelfde voor
`lokalist_periode_overzicht.sql` — de query achter `scripts/run_jaaroverzicht.py`
(jaar- én maandoverzicht). Die draait op dezelfde seed uit
`helpers/mendrix_schema.py`, zodat "beide queries geven hetzelfde antwoord" ook
echt getest is en niet alleen op tekstniveau vergeleken. Daarnaast bewaakt die
test dat verzamelorders (`CatchWord = 'Verzamelorder'`) er niet in meetellen.

`unit/test_adres_groepering_drift.py` vergelijkt daarbovenop de tékst van het
gedeelde TaakNamen/AdresTotalen-blok in beide .sql-bestanden, zodat ze niet
stilletjes uiteenlopen.

- Let op: deze test heeft **SQL Server 2017 of hoger** nodig, want de query
  gebruikt `STRING_AGG`. De `windows-latest`-runner voldoet; een oudere lokale
  LocalDB (bijv. 2014) skipt via `vereis_string_agg_of_skip()` in
  `helpers/localdb.py`, en faalt hard zodra `CI` gezet is.
