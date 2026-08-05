"""Orkestreert fase 1: query -> PDF -> lokaal opslaan (DRY_RUN).

Fase 2-4 (SOAP-order, dossier-upload, e-mail) zijn bewust nog niet
aangeroepen — zie CLAUDE.md voor de bouwvolgorde en open beslissingen.
"""

import logging
import os
from datetime import date

from .config import laad_config
from .genereer_rapport import genereer_pdf
from .mailer import verstuur_admin_melding
from .query import bepaal_week, haal_spoeddata_op, haal_weekdata_op

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(_BASE, "logs")
OUTPUT_DIR = os.path.join(_BASE, "output")


def _setup_logging() -> str:
    """Configureert logging en geeft het pad van het logbestand terug."""
    os.makedirs(LOG_DIR, exist_ok=True)
    logbestand = os.path.join(LOG_DIR, f"lokalist_{date.today().isoformat()}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(logbestand, encoding="utf-8"), logging.StreamHandler()],
    )
    return logbestand


def _flush_logs() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def main() -> None:
    logbestand = _setup_logging()
    log = logging.getLogger(__name__)

    config = laad_config()
    if not config.dry_run:
        log.warning(
            "DRY_RUN=false maar fase 2-4 (SOAP/REST/e-mail) zijn nog niet "
            "geïmplementeerd. Forceer DRY_RUN gedrag."
        )

    vandaag = date.today()
    week_nummer, jaar = bepaal_week(vandaag, config.week_offset)
    log.info("Run gestart voor week %s, jaar %s (run_datum=%s)", week_nummer, jaar, vandaag)

    try:
        spoed_rows = haal_spoeddata_op(config, week_nummer, jaar)
        spoed_ids = [int(r[1]) for r in spoed_rows]
        rows = haal_weekdata_op(config, week_nummer, jaar, spoed_order_ids=spoed_ids)
        log.info("Query uitgevoerd: %d rijen, %d spoedorder(s)", len(rows), len(spoed_rows))

        if not rows:
            log.warning("Geen orders gevonden voor week %s, %s — run gestopt.", week_nummer, jaar)
            _flush_logs()
            verstuur_admin_melding(
                config,
                onderwerp=f"[Lokalist] Geen orders week {week_nummer}/{jaar}",
                bericht=(
                    f"Er zijn geen orders van De Lokalist gevonden voor week"
                    f" {week_nummer}, {jaar}.\n\n"
                    f"Er is geen PDF gegenereerd, geen order aangemaakt"
                    f" en geen rapport verstuurd.\n\n"
                    f"Het logbestand is bijgevoegd."
                ),
                logbestand=logbestand,
            )
            return

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, f"lokalist_week{week_nummer}_{jaar}.pdf")
        pdf_path, totals = genereer_pdf(
            rows=rows,
            weeknummer=week_nummer,
            jaar=jaar,
            periode_omschrijving=f"week {week_nummer}, {jaar}",
            output_path=output_path,
        )
        log.info("PDF gegenereerd: %s — totalen: %s", pdf_path, totals)
        log.info(
            "DRY_RUN actief: stap 3 (SOAP order), stap 4 (dossier-upload) en "
            "stap 5 (e-mail) worden overgeslagen. Zie CLAUDE.md voor de status."
        )

    except Exception:
        log.error("Fout opgetreden — run afgebroken.", exc_info=True)
        _flush_logs()
        verstuur_admin_melding(
            config,
            onderwerp=f"[Lokalist] FOUT tijdens run week {week_nummer}/{jaar}",
            bericht=(
                f"Het weekrapportage-process is gestopt door een onverwachte fout "
                f"(week {week_nummer}, {jaar}).\n\n"
                f"Zie het bijgevoegde logbestand voor de volledige foutmelding en stacktrace."
            ),
            logbestand=logbestand,
        )
        raise


if __name__ == "__main__":
    main()
