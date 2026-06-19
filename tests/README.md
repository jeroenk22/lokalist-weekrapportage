# Tests

- `fixtures/` — representatieve queryresultaten (lijsten van 11-tuples) en
  voorbeeld-PDF-rijen voor genereer_rapport.py
- `helpers/` — gedeelde hulpfuncties, bijv. een fake pyodbc-cursor
- `unit/` — per module: query.py (mock pyodbc), config.py (mock env vars),
  main.py (mock query + genereer_rapport)
- `integration/` — volledige keten: fixture-rows → genereer_pdf() → PDF-bestand
  bestaat en totals kloppen (geen mocks binnen deze keten zelf)

Run met: `pytest --cov --cov-fail-under=80`
