# Python best practices — lokalist-weekrapportage

- Gebruik `data_only=True`-equivalent denken: bij externe data (SQL-resultaten)
  nooit aannemen dat een veld gevuld is — expliciet `None`-checks.
- Type hints overal in nieuwe functies (`def f(x: int) -> str:`).
- Geen brede `except Exception:` — vang specifieke exceptions (pyodbc.Error,
  requests.RequestException, zeep.exceptions.Fault) apart af, zie CLAUDE.md
  §Logging voor de foutafhandelingsstrategie per pipelinestap.
- Logging via de standaard `logging`-module naar `logs/lokalist_YYYY-MM-DD.log`,
  nooit alleen naar console (geplande taak heeft geen zichtbare console).
- `genereer_rapport.py` is een bevroren module — wijzigingen hierin alleen na
  expliciete vraag van Jeroen.
- Secrets altijd via `.env` + `python-dotenv`, nooit hardcoded.
