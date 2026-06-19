# lokalist-weekrapportage

Wekelijks automatiseringsscript voor het Orderoverzicht De Lokalist
(Miedema Ophaaldienst B.V.). Zie `CLAUDE.md` voor de volledige context,
bouwvolgorde en open beslissingen.

## Status
**Fase 1** — query + PDF-generatie + dry-run. SOAP-order, dossier-upload en
e-mail volgen zodra de benodigde documentatie is aangeleverd (zie CLAUDE.md).

## Snel starten
```bash
python -m venv .venv
source .venv/Scripts/activate   # Git Bash op Windows
pip install -e ".[dev]"
cp .env.example .env            # vul daarna in
python -m lokalist_weekrapportage.main
```
