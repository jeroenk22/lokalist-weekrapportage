# lokalist-weekrapportage

## Wat deze app doet
Wekelijks automatiseringsscript dat elke zondag 23:30 op machine 192.168.4.105
de laad/los-taken van De Lokalist (ClientNo 4787) uit MendriX (SQL Server
192.168.4.102, database MENDRIXDB01) ophaalt, het PDF "Orderoverzicht De
Lokalist" genereert (vaste opmaak met Miedema/Lokalist-logo's, goud/groen
secties Laden/Lossen), een samenvattende order aanmaakt in MendriX via SOAP,
het PDF in het dossier van die order zet via REST, en het rapport per e-mail
verstuurt naar de geconfigureerde ontvangers.

## Stack
- Python 3.13
- pyodbc (SQL Server-koppeling)
- reportlab (PDF-generatie, al geïmplementeerd in genereer_rapport.py)
- python-dotenv (.env inladen)
- requests (REST dossier-upload én SOAP; zeep staat in de dependencies maar de
  SOAP-envelopes worden handmatig gebouwd, zie `mendrix_client.py`)
- defusedxml (veilig XML parsen; stdlib `ElementTree` alleen voor serialisatie)
- Ruff 0.15.18 (lint + format)
- pytest 9.0.3 + pytest-cov (testen)

Webdashboard (`web/`):
- Node 22 + TypeScript, Express 5, Zod (validatie)
- React 19, Vite 6, TanStack Query, Tailwind CSS 4
- Vitest + Testing Library

## Bouwvolgorde — ALLE FASES ZIJN GEBOUWD EN DRAAIEN IN PRODUCTIE
Dit project is in fases gebouwd volgens de oorspronkelijke briefing
(`briefing_lokalist_automatisering.md`, niet in deze repo opgenomen i.v.m.
interne netwerkdetails — bewaar dit document apart). Alle fases zijn af:

1. **Fase 1 — data + PDF.** query.py + genereer_rapport.py.
2. **Fase 2 — order aanmaken via SOAP.** Gebouwd, draait in productie.
3. **Fase 3 — PDF + ordernummers.txt in het dossier via REST.** Gebouwd.
4. **Fase 4 — e-mail versturen.** Gebouwd (`mailer.py`, SMTP én Graph).
5. **Fase 5 — Task Scheduler.** Draait elke zondag 23:30 op de 105
   (`scripts/install_taskscheduler.ps1`) en maakt echte orders aan.
6. **Fase 6 — webdashboard.** Zie `web/README.md`.

**Let op — de productieroute is `scripts/run_weekrapportage.py`, niet `main.py`.**
Dat script bevat de volledige keten (SQL → PDF → SOAP → REST → mail) en leest
`--dry-run` uit `sys.argv`, niet uit `DRY_RUN` in `.env`. De `DRY_RUN`-variabele
raakt daardoor alleen `main.py`, dat in productie niet gebruikt wordt; `DRY_RUN=true`
in `.env` betekent dus *niet* dat de zondagrun droog draait.

`mendrix_dossier.py` en `mendrix_soap.maak_order_aan()` zijn nog steeds ongebruikte
stubs met `NotImplementedError` — de werkende implementatie staat in
`run_weekrapportage.py` en `mendrix_client.py`. `mendrix_soap.bouw_instructies()`
en `bouw_ordernummers_txt()` zijn wél in gebruik.

## Webdashboard (fase 6)
`web/` bevat een React + Express-dashboard waarmee collega's zonder Python een
bestaand weekrapport opnieuw kunnen genereren. Het bouwt het rapport **niet na**:
het start dezelfde Python-engine via `scripts/web_runner.py` (JSON in, NDJSON uit).
Volledige uitleg staat in `web/README.md`. Kernpunten:

- `scripts/run_weekrapportage.py` mag **niet** gewijzigd worden. De gedeelde
  onderdelen zijn gekopieerd naar `mendrix_client.py` en `verzamelorder.py`;
  `tests/unit/test_verzamelorder_drift.py` bewaakt dat beide kopieën byte-identieke
  XML blijven produceren.
- Volgorde bij hergenereren is bewust **eerst nieuw aanmaken, dan pas de oude
  verwijderen**, met rollback van de nieuwe order als stap 4/5/6 faalt.
- Gefactureerde verzamelorders (`Orders.InvKey` gevuld) worden geweigerd —
  server-side in `web_runner.py`, niet alleen in de UI.
- Er zit **bewust geen authenticatie** op (interne netwerk, akkoord van Jeroen).

## Expliciet NIET opnieuw te beslissen (al vastgesteld)
- De volledige visuele opmaak van het PDF (`genereer_rapport.py`) — ongewijzigd
  laten, niet "verbeteren" of herschrijven.
- TaskType: 1 = Laden, 2 = Lossen.
- Staffel-logica: COALESCE via `GraduateArticleId`, VAN-inclusief/TOT-exclusief.
- Orders met laad- en lostaak in verschillende weken mogen gesplitst over twee
  rapportages verschijnen — bewuste keuze, niet "fixen".
- `StaffelPrijsPerStuk`/`Price` wordt niet getoond in het rapport.

### MendriX-veldmapping (empirisch vastgesteld, niet aannemen maar hergebruiken)
- XML `<Reference>` ↔ DB `Orders.CatchWord`. Verzamelorders hebben hier
  `Verzamelorder`; `lokalist_staffel_overzicht.sql` sluit ze daarop uit.
- XML `<Notes>` ↔ DB `Orders.Diversen`. Hier staat de
  `[HANDMATIG HERGENEREERD]`-markering van het dashboard in.
- Taak-`<ReferenceYour>` ↔ DB `ordsubtask.RefYour`, met `Week <nr> <jaar>`.
- `Orders.Deleted` is een tinyint die MendriX zelf gebruikt; verwijderen gaat via
  order ophalen → `<Deleted>True</Deleted>` → terugsturen als
  `EoCustomLinkStoreOrdersNormal` (bevestigd op testorder 1267594, 4-8-2026).
- `Orders.InvStatus` 2 = niet gefactureerd (`InvKey` leeg), 20 = gefactureerd
  (`InvKey` gevuld).

## Beslissingen (alle 1-4 zijn vastgesteld; 5 is geleverd)
1. ~~Database-authenticatie~~ → **vastgesteld: Windows Integrated Auth**
   (`DB_AUTH_METHOD=windows`, geen SQL-login nodig)
2. ~~"Afgelopen week"~~ → **vastgesteld: `WEEK_OFFSET=0`**. Rapport draait
   elke zondag 23:30 en moet dan alles van maandag t/m zaterdag ervoor
   meenemen. Omdat zondag zelf al de laatste dag van die ISO-week is, komt
   de lopende ISO-week (`WEEK_OFFSET=0`) op dat moment overeen met "de
   afgelopen week" (maandag t/m zaterdag) — `WEEK_OFFSET=1` zou juist één
   week te vroeg rapporteren. Bevestigd door Jeroen aan de hand van een
   concreet voorbeeld: run op zondag 12-7-2026 moet week 28 opleveren, wat
   met offset 0 klopt (offset 1 geeft ten onrechte week 27).
3. ~~SOAP create-call: `ClientId` of `ClientNumber`?~~ → **vastgesteld: `ClientId`**
   met waarde 4787, zie `_bouw_store_xml` in `run_weekrapportage.py`.
4. ~~Colli-totaal/bedrag op de samenvattende order~~ → **vastgesteld:** colli telt
   **alleen Laden** (`totaal_laden_colli`), het bedrag telt **Laden + Lossen**
   (`totaal_bedrag`), beide plus de spoedregels.
5. ~~Documentatie aanleveren~~ → **geleverd**: `docs/examples/` bevat de
   SOAP-voorbeeld-XML's en `GdxEoStructures.xsd`, `docs/db-structure/` het
   DB-schema. SMTP-gegevens staan in `.env`.

## Commando's
```bash
# Installeer dependencies
python -m venv .venv
source .venv/Scripts/activate   # Git Bash op Windows
pip install -e ".[dev]"

# Productie-keten handmatig draaien (SQL → PDF → SOAP → REST → mail)
python scripts/run_weekrapportage.py --test      # vraagt week/jaar
python scripts/run_weekrapportage.py --dry-run   # niets versturen

# Run tests
pytest --cov --cov-fail-under=80

# Lint + format
ruff check .
ruff format .

# Webdashboard (zie web/README.md)
cd web && npm install
npm run dev       # ontwikkelen
npm run build && npm start   # productie op de 105, http://<ip>:3000
npm test          # vitest
```

## Projectstructuur
- `src/lokalist_weekrapportage/` — applicatiecode
  - `genereer_rapport.py` — PDF-module (kant-en-klaar, niet wijzigen)
  - `logo_miedema.png`, `logo_lokalist.png` — logo-assets (niet wijzigen)
  - `lokalist_staffel_overzicht.sql` — basis-SQL (niet wijzigen, query.py
    parametriseert week/jaar dynamisch zonder de queryskelet aan te passen)
  - `query.py` — database-koppeling, dynamische week/jaar-parametrisering
  - `config.py` — .env inladen + validatie (fail fast)
  - `mailer.py` — e-mail via SMTP of Microsoft Graph (in gebruik)
  - `main.py` — oude fase 1-orkestratie; **niet de productieroute**
  - `mendrix_soap.py` — `bouw_instructies` + `bouw_ordernummers_txt` (in gebruik);
    `maak_order_aan()` is een ongebruikte stub
  - `mendrix_dossier.py` — ongebruikte stub
  - `mendrix_client.py` — SOAP/REST-koppeling + `verwijder_order` (dashboard)
  - `verzamelorder.py` — store-XML, NL datumopmaak, handmatig-markering (dashboard)
  - `verzamelorder_query.py` + `lokalist_verzamelorders.sql` — dashboardlijst
- `scripts/` — uitvoerbare scripts
  - `run_weekrapportage.py` — **de productieketen** (Task Scheduler, zondag 23:30)
  - `web_runner.py` — JSON/NDJSON-entrypoint voor het webdashboard
- `web/` — React + Express dashboard, zie `web/README.md`
- `docs/` — externe API-documentatie (handmatig aangeleverd)
  - `examples/` — XML-voorbeeldberichten + `GdxEoStructures.xsd`
  - `db-structure/` — DB-schema van MENDRIXDB01 (UTF-16!)
- `tests/` — unit- en integratietests, zie Teststrategie hieronder
- `logs/` — logbestanden (gitignored, alleen `.gitkeep` gecommit)
- `output/` — lokaal gegenereerde PDF's (gitignored)

## Conventies
- Branch strategie: main (protected) → develop → feature/xxx, fix/xxx, chore/xxx
- Commits: Conventional Commits (feat:, fix:, chore:, docs:, test:)
- PR: nooit direct naar main, altijd via PR met passing tests
- Package manager: pip + venv

## Logging

### Setup
Elk entrypoint roept één keer zijn eigen `_setup_logging()` aan met
`logging.basicConfig` (file-handler + StreamHandler). Nooit opnieuw aanroepen
vanuit andere modules.

| Entrypoint | Logbestand |
|------------|------------|
| `scripts/run_weekrapportage.py` (productie) | `logs/testscript_YYYY-MM-DD_HHMMSS.log` |
| `scripts/web_runner.py` (dashboard) | `logs/dashboard_YYYY-MM-DD_HHMMSS.log` |
| `main.py` (niet in productie) | `logs/lokalist_YYYY-MM-DD.log` |

In `web_runner.py` gaat de StreamHandler expliciet naar **stderr**: stdout is daar
gereserveerd voor het NDJSON-protocol richting de Node-backend. Een `print()` in
die keten breekt het dashboard.

### Logger declaratie
Elke module declareert een module-level logger:
```python
_log = logging.getLogger(__name__)
```
`__name__` levert automatisch de juiste hiërarchische naam op
(`lokalist_weekrapportage.query`, `lokalist_weekrapportage.main`, enz.).

### Niveaus
| Niveau    | Gebruik                                                       |
|-----------|---------------------------------------------------------------|
| `debug`   | Gedetailleerde tussenstappen (SQL-params, regel-voor-regel)  |
| `info`    | Mijlpalen: run gestart, query klaar, PDF opgeslagen          |
| `warning` | Herstelbare fout of verwacht afwijkend gedrag                |
| `error`   | Fatale stap — verwerking kan niet doorgaan                   |

### Externe aanroepen
SQL Server (pyodbc), SOAP (zeep) en REST (requests) altijd in try/except:
```python
try:
    rows = conn.execute(sql).fetchall()
except Exception:
    _log.warning("DB-query mislukt", exc_info=True)
    raise
```

### Verboden
- Nooit `print()` voor diagnostische output — altijd `_log`
- Nooit `logging.basicConfig` aanroepen buiten `_setup_logging()`

## Pre-commit kwaliteitscheck
Vóór elke commit wordt automatisch `ruff check .` en `ruff format --check .`
uitgevoerd via een hook in `.claude/settings.json`. Als een van beide faalt,
wordt de commit geblokkeerd. Fix ruff-fouten altijd vóór het committen.

## Wat Claude NIET mag doen
- Nooit direct committen naar main
- Nooit .env bestanden aanmaken met echte secrets
- Nooit dependencies toevoegen zonder expliciete vraag
- Nooit bestaande tests verwijderen
- Nooit `genereer_rapport.py`, de logo's of de SQL-skelet-structuur wijzigen
  zonder expliciete vraag van Jeroen
- Nooit `scripts/run_weekrapportage.py` wijzigen — dat is de draaiende
  productieketen. Gedeelde logica hoort in een nieuwe module, met een drift-test
  die bewijst dat beide kopieën identieke uitvoer geven
- Nooit MendriX-veldnamen of -gedrag op aannames baseren. Verifieer tegen de
  database of met een read-only SOAP-call, zoals bij de veldmapping hierboven
- Nooit een gefactureerde order (`Orders.InvKey` gevuld) verwijderen of
  hergenereren — er verwijst een factuurregel naar
- Nooit `Co-Authored-By: Claude` of enige vermelding van "gegenereerd door Claude"
  opnemen in commit-berichten, PR-beschrijvingen of code-commentaar

---

## Teststrategie

### Aanpak
- **Unit tests** voor alle pure functies en componenten — één eenheid, alles gemocked
- **Integratietests** voor de volledige keten (query → rows → PDF) — geen mocks
  voor de transformatielogica, wel voor de externe SQL-verbinding zelf
- Geen E2E/browser tests (geen UI in dit project)

### Structuur
```
tests/
  fixtures/            → representatieve queryresultaten en testdata
  helpers/              → gedeelde hulpfuncties en seed-data
  unit/                → unit tests per module
  integration/          → integratietests per keten
```

### Regels
- Fixtures aanmaken **voordat** de productiecode geschreven wordt
- Minimaal 80% coverage afgedwongen in CI
- Externe diensten (SQL Server, SOAP, REST, SMTP) altijd mocken in unit tests
- Elke bugfix krijgt eerst een falende test, dan de fix

---

## Karpathy Gedragsregels

Behavioral guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding
Before implementing: state assumptions explicitly, ask if uncertain, present
multiple interpretations instead of picking silently, push back if a simpler
approach exists, stop and ask if something is unclear.

### 2. Simplicity First
Minimum code that solves the problem. No speculative features, no
abstractions for single-use code, no unrequested flexibility/configurability,
no error handling for impossible scenarios.

### 3. Surgical Changes
Touch only what you must. Don't "improve" adjacent code. Don't refactor
working code. Match existing style. Remove only imports/variables your own
changes made unused — never pre-existing dead code unless asked.

### 4. Goal-Driven Execution
Transform tasks into verifiable goals ("Fix the bug" → "Write a test that
reproduces it, then make it pass"). For multi-step tasks, state a brief plan
with a verify-step per item.

---

## Security
- Claude Code security-guidance plugin is actief:
  /plugin install security-guidance@claude-plugins-official
  Karpathy skills: /plugin install andrej-karpathy-skills@karpathy-skills
- Nooit API keys, wachtwoorden of secrets in code of commits
- Gebruik altijd .env.example voor configuratie voorbeelden
- Alle dependencies worden gescand via de security plugin
- Database-login krijgt alleen SELECT-rechten (zie open beslissing 1)

## Evaluatie & Kwaliteit
- **Code coverage:** minimaal 80% (afgedwongen in CI)
- **Linting:** Ruff — zero errors verplicht in CI

## Na elke wijziging verplicht uitvoeren
Na **elke** code-wijziging — hoe klein ook — altijd in deze volgorde:

1. `ruff check . && ruff format --check .` — fix eventuele fouten direct
2. `pytest --cov --cov-fail-under=80` — controleer of alle tests slagen en coverage ≥ 80%
3. Als coverage gedaald is of een test faalt: schrijf eerst de ontbrekende test(s),
   daarna pas afronden. Lever nooit werk op waarbij tests rood zijn of coverage onder 80% zakt.
