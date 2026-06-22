"""Laadt en valideert configuratie uit .env. Faalt direct bij een ontbrekende
verplichte variabele in plaats van halverwege de pipeline vast te lopen."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Variabelen die nodig zijn voor fase 1 (query + PDF + dry-run).
# SOAP/REST/SMTP-variabelen worden pas verplicht zodra fase 2-4 gebouwd worden.
VERPLICHT_FASE_1 = ["DB_SERVER", "DB_DATABASE", "DB_AUTH_METHOD"]
DB_DRIVER_DEFAULT = "ODBC Driver 18 for SQL Server"


@dataclass(frozen=True)
class Config:
    db_server: str
    db_database: str
    db_auth_method: str
    db_driver: str
    db_user: str | None
    db_password: str | None
    week_offset: int
    dry_run: bool
    smtp_host: str | None
    smtp_poort: int | None
    smtp_gebruiker: str | None
    smtp_wachtwoord: str | None
    smtp_gebruik_tls: bool
    afzender_email: str | None
    admin_email_ontvangers: list[str]


def laad_config() -> Config:
    load_dotenv()

    ontbrekend = [naam for naam in VERPLICHT_FASE_1 if not os.getenv(naam)]
    if ontbrekend:
        raise RuntimeError(
            f"Verplichte .env-variabelen ontbreken: {', '.join(ontbrekend)}. "
            f"Kopieer .env.example naar .env en vul ze in."
        )

    db_auth_method = os.environ["DB_AUTH_METHOD"]
    if db_auth_method == "sql" and not (os.getenv("DB_USER") and os.getenv("DB_PASSWORD")):
        raise RuntimeError(
            "DB_AUTH_METHOD=sql vereist DB_USER en DB_PASSWORD in .env."
        )

    smtp_poort_str = os.getenv("SMTP_POORT")
    admin_raw = os.getenv("ADMIN_EMAIL_ONTVANGERS", "")

    return Config(
        db_server=os.environ["DB_SERVER"],
        db_database=os.environ["DB_DATABASE"],
        db_auth_method=db_auth_method,
        db_driver=os.getenv("DB_DRIVER", DB_DRIVER_DEFAULT),
        db_user=os.getenv("DB_USER"),
        db_password=os.getenv("DB_PASSWORD"),
        week_offset=int(os.getenv("WEEK_OFFSET", "0")),
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
        smtp_host=os.getenv("SMTP_HOST") or None,
        smtp_poort=int(smtp_poort_str) if smtp_poort_str else None,
        smtp_gebruiker=os.getenv("SMTP_GEBRUIKER") or None,
        smtp_wachtwoord=os.getenv("SMTP_WACHTWOORD") or None,
        smtp_gebruik_tls=os.getenv("SMTP_GEBRUIK_TLS", "true").lower() == "true",
        afzender_email=os.getenv("AFZENDER_EMAIL") or None,
        admin_email_ontvangers=[e.strip() for e in admin_raw.split(",") if e.strip()],
    )
