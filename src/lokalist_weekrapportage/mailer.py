"""E-mail utilities.

verstuur_admin_melding — admin-notificaties bij lege runs en fouten (geïmplementeerd).
verstuur_rapport       — fase 4, rapport naar ontvangers (NOG NIET GEBOUWD).

Ontbreekt voor verstuur_rapport: SMTP-gegevens (zie CLAUDE.md §6 / .env.example).
"""

import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import Config

_log = logging.getLogger(__name__)


def verstuur_admin_melding(
    config: Config,
    onderwerp: str,
    bericht: str,
    logbestand: str | None = None,
) -> None:
    """Verstuurt een notificatiemail naar alle ADMIN_EMAIL_ONTVANGERS.

    Legt alleen een warning vast als SMTP of ontvangers niet geconfigureerd zijn
    — gooit geen exception zodat de hoofdfout niet verdronken wordt.
    """
    if not config.admin_email_ontvangers:
        _log.warning(
            "Geen ADMIN_EMAIL_ONTVANGERS ingesteld — admin-melding '%s' niet verstuurd.",
            onderwerp,
        )
        return
    if not config.smtp_host or not config.afzender_email:
        _log.warning(
            "SMTP niet geconfigureerd (SMTP_HOST of AFZENDER_EMAIL ontbreekt) — "
            "admin-melding '%s' niet verstuurd.",
            onderwerp,
        )
        return

    msg = MIMEMultipart()
    msg["From"] = config.afzender_email
    msg["To"] = ", ".join(config.admin_email_ontvangers)
    msg["Subject"] = onderwerp
    msg.attach(MIMEText(bericht, "plain", "utf-8"))

    if logbestand and os.path.isfile(logbestand):
        with open(logbestand, "rb") as f:
            bijlage = MIMEApplication(f.read(), Name=os.path.basename(logbestand))
        bijlage["Content-Disposition"] = f'attachment; filename="{os.path.basename(logbestand)}"'
        msg.attach(bijlage)
    elif logbestand:
        _log.warning("Logbestand niet gevonden voor bijlage: %s", logbestand)

    try:
        poort = config.smtp_poort or 587
        with smtplib.SMTP(config.smtp_host, poort) as server:
            if config.smtp_gebruik_tls:
                server.starttls()
            if config.smtp_gebruiker and config.smtp_wachtwoord:
                server.login(config.smtp_gebruiker, config.smtp_wachtwoord)
            server.sendmail(
                config.afzender_email,
                config.admin_email_ontvangers,
                msg.as_bytes(),
            )
        _log.info("Admin-melding verstuurd naar: %s", ", ".join(config.admin_email_ontvangers))
    except Exception:
        _log.error("Fout bij verzenden admin-melding '%s'", onderwerp, exc_info=True)


def verstuur_rapport(*args, **kwargs):
    raise NotImplementedError(
        "Fase 4 (e-mail) is nog niet geïmplementeerd — wacht op SMTP-gegevens."
    )
