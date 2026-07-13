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
- requests (REST dossier-upload)
- zeep (SOAP-client voor MendriX CustomLink-API)
- Ruff 0.15.18 (lint + format)
- pytest 9.0.3 + pytest-cov (testen)

## BELANGRIJK — Gefaseerde bouwvolgorde (NIET afwijken zonder Jeroen)
Dit project wordt in fases gebouwd, exact zoals vastgelegd in de oorspronkelijke
briefing (`briefing_lokalist_automatisering.md`, niet in deze repo opgenomen
i.v.m. interne netwerkdetails — bewaar dit document apart):

1. **Fase 1 (NU GEBOUWD):** query.py + genereer_rapport.py + main.py met
   `DRY_RUN=true` als enige werkende modus. Haalt data op, bouwt het PDF,
   logt alles, slaat lokaal op in `output/`. Dit is volledig testbaar.
2. **Fase 2 (NOG NIET GEBOUWD):** order aanmaken in MendriX via SOAP.
   Documentatie komt in `docs/soap/` (Markdown) en `docs/examples/` (XML).
   Wacht op: voorbeeld-XML van een CreateOrder SOAP-request, WSDL/methode-
   documentatie, en bevestiging of `ClientId` of `ClientNumber` gebruikt
   wordt. Bouw dit NIET zelf een contract voor — wacht op aangeleverde
   documentatie van Jeroen.
3. **Fase 3 (NOG NIET GEBOUWD):** PDF in dossier zetten via REST API.
   Documentatie komt in `docs/rest/` (Swagger/OpenAPI JSON).
   Wacht op: exact endpoint-pad, upload-formaat (multipart/base64/anders),
   authenticatiemethode, verplichte documenttype/categorie-velden.
4. **Fase 4 (NOG NIET GEBOUWD):** e-mail versturen. Wacht op SMTP-gegevens.
5. **Fase 5 (Task Scheduler-taak actief sinds 24-6-2026):** Windows Task
   Scheduler-taak op de 105 draait elke zondag 23:30 (`scripts/install_taskscheduler.ps1`).
   `DRY_RUN=true` staat nog aan, dus dit voert momenteel alleen fase 1 uit
   (PDF lokaal wegschrijven) — fases 2-4 zijn nog niet gebouwd.

`src/lokalist_weekrapportage/mendrix_soap.py`, `mendrix_dossier.py` en
`mailer.py` bevatten daarom bewust alleen functie-signatures met
`raise NotImplementedError(...)` en een verwijzing naar wat er nog moet
worden aangeleverd. **Vul deze niet zelf in op aannames — vraag het na bij
Jeroen of wacht op de documentatie.**

## Expliciet NIET opnieuw te beslissen (al vastgesteld)
- De volledige visuele opmaak van het PDF (`genereer_rapport.py`) — ongewijzigd
  laten, niet "verbeteren" of herschrijven.
- TaskType: 1 = Laden, 2 = Lossen.
- Staffel-logica: COALESCE via `GraduateArticleId`, VAN-inclusief/TOT-exclusief.
- Orders met laad- en lostaak in verschillende weken mogen gesplitst over twee
  rapportages verschijnen — bewuste keuze, niet "fixen".
- `StaffelPrijsPerStuk`/`Price` wordt niet getoond in het rapport.

## Open beslissingen (door Jeroen te bevestigen voordat fase 2+ gebouwd wordt)
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
3. SOAP create-call: `ClientId` of `ClientNumber`?
4. Colli-totaal/bedrag op de samenvattende order: alleen Laden, of Laden+Lossen?
5. Documentatie aanleveren in:
   - `docs/soap/` — WSDL + methode-beschrijvingen (Markdown)
   - `docs/examples/` — voorbeeld-XML van CreateOrder SOAP-request
   - `docs/rest/` — Swagger/OpenAPI JSON voor dossier-upload
   - SMTP-gegevens voor fase 4

## Commando's
```bash
# Installeer dependencies
python -m venv .venv
source .venv/Scripts/activate   # Git Bash op Windows
pip install -e ".[dev]"

# Start (fase 1, dry-run)
python -m lokalist_weekrapportage.main

# Run tests
pytest --cov --cov-fail-under=80

# Lint + format
ruff check .
ruff format .
```

## Projectstructuur
- `src/lokalist_weekrapportage/` — applicatiecode
  - `genereer_rapport.py` — PDF-module (kant-en-klaar, niet wijzigen)
  - `logo_miedema.png`, `logo_lokalist.png` — logo-assets (niet wijzigen)
  - `lokalist_staffel_overzicht.sql` — basis-SQL (niet wijzigen, query.py
    parametriseert week/jaar dynamisch zonder de queryskelet aan te passen)
  - `query.py` — database-koppeling, dynamische week/jaar-parametrisering
  - `config.py` — .env inladen + validatie (fail fast)
  - `main.py` — orkestreert fase 1 (query → PDF → lokaal opslaan, dry-run)
  - `mendrix_soap.py`, `mendrix_dossier.py`, `mailer.py` — stubs voor fase 2-4
- `docs/` — externe API-documentatie (niet gegenereerd, handmatig aangeleverd)
  - `soap/` — Markdown bestanden: WSDL-beschrijving, methode-documentatie fase 2
  - `rest/` — Swagger/OpenAPI JSON voor de dossier-upload API fase 3
  - `examples/` — XML voorbeeldberichten van SOAP-calls (CreateOrder e.d.)
- `tests/` — unit- en integratietests, zie Teststrategie hieronder
- `logs/` — logbestanden (gitignored, alleen `.gitkeep` gecommit)
- `output/` — lokaal gegenereerde PDF's bij DRY_RUN (gitignored)

## Conventies
- Branch strategie: main (protected) → develop → feature/xxx, fix/xxx, chore/xxx
- Commits: Conventional Commits (feat:, fix:, chore:, docs:, test:)
- PR: nooit direct naar main, altijd via PR met passing tests
- Package manager: pip + venv

## Logging

### Setup
`_setup_logging()` in `main.py` configureert één keer `logging.basicConfig` met
file-handler (`logs/lokalist_YYYY-MM-DD.log`) én StreamHandler. Nooit opnieuw
aanroepen vanuit andere modules.

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
- Nooit fase 2/3/4 (SOAP, REST, e-mail) implementeren op basis van aannames —
  altijd wachten op aangeleverde documentatie of expliciet navragen
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
