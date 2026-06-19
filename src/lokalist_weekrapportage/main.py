"""Orkestreert fase 1: query -> PDF -> lokaal opslaan (DRY_RUN).

Fase 2-4 (SOAP-order, dossier-upload, e-mail) zijn bewust nog niet
aangeroepen — zie CLAUDE.md voor de bouwvolgorde en open beslissingen.
"""

import logging
import os
from datetime import date

from .config import laad_config
from .genereer_rapport import genereer_pdf
from .query import bepaal_week, haal_weekdata_op

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "output")


def _setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    logbestand = os.path.join(LOG_DIR, f"lokalist_{date.today().isoformat()}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(logbestand, encoding="utf-8"), logging.StreamHandler()],
    )


def main() -> None:
    _setup_logging()
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

    rows = haal_weekdata_op(config, week_nummer, jaar)
    log.info("Query uitgevoerd: %d rijen opgehaald", len(rows))

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


if __name__ == "__main__":
    main()
