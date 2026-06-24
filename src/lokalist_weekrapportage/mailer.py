"""E-mail utilities.

verstuur_admin_melding — admin-notificaties bij lege runs en fouten.
verstuur_rapport       — weekrapport als HTML-mail met PDF-bijlage naar EMAIL_ONTVANGERS.

Ondersteunde providers (EMAIL_PROVIDER in .env):
  smtp  — elke SMTP-server: Gmail (smtp.gmail.com:587) of Office 365 legacy
           (smtp.office365.com:587). Configureer SMTP_HOST/POORT/GEBRUIKER/WACHTWOORD.
  graph — Microsoft Graph API via OAuth2 client-credentials. Vereist
           MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET en MS_SENDER_EMAIL.
"""

import base64
import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from .config import Config

_log = logging.getLogger(__name__)

_PKG_DIR = os.path.dirname(__file__)
_LOGO_MIEDEMA_PAD = os.path.join(_PKG_DIR, "logo_miedema.png")
_LOGO_LOKALIST_PAD = os.path.join(_PKG_DIR, "logo_lokalist.png")
_ICON_TELEFOON_PAD = os.path.join(_PKG_DIR, "icon_telefoon.png")
_ICON_GLOBE_PAD = os.path.join(_PKG_DIR, "icon_globe.png")
_TEMPLATE_PAD = os.path.join(_PKG_DIR, "template_mail.html")

# Inline afbeeldingen voor het weekrapport: (content-id, bestandspad)
_RAPPORT_AFBEELDINGEN = [
    ("logo_lokalist", _LOGO_LOKALIST_PAD),
    ("logo_miedema", _LOGO_MIEDEMA_PAD),
    ("icon_telefoon", _ICON_TELEFOON_PAD),
    ("icon_globe", _ICON_GLOBE_PAD),
]


def _laad_html_template() -> str:
    try:
        with open(_TEMPLATE_PAD, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"E-mail template niet gevonden: {_TEMPLATE_PAD}") from None


# ---------------------------------------------------------------------------
# SMTP-transport (Gmail + Office 365 legacy)
# ---------------------------------------------------------------------------


def _smtp_verstuur(config: Config, msg: MIMEMultipart, ontvangers: list[str]) -> None:
    poort = config.smtp_poort or 587
    with smtplib.SMTP(config.smtp_host, poort) as server:
        if config.smtp_gebruik_tls:
            server.starttls()
        if config.smtp_gebruiker and config.smtp_wachtwoord:
            server.login(config.smtp_gebruiker, config.smtp_wachtwoord)
        server.sendmail(config.afzender_email, ontvangers, msg.as_bytes())


def _smtp_beschikbaar(config: Config) -> bool:
    return bool(config.smtp_host and config.afzender_email)


# ---------------------------------------------------------------------------
# Graph API-transport (Microsoft 365 OAuth2)
# ---------------------------------------------------------------------------


def _graph_token(config: Config) -> str:
    """Haalt een OAuth2 access-token op via client-credentials flow."""
    url = f"https://login.microsoftonline.com/{config.ms_tenant_id}/oauth2/v2.0/token"
    try:
        resp = requests.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": config.ms_client_id,
                "client_secret": config.ms_client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30,
        )
        resp.raise_for_status()
    except Exception:
        _log.warning("Graph API token-aanvraag mislukt", exc_info=True)
        raise
    return resp.json()["access_token"]


def _graph_verstuur(
    config: Config,
    onderwerp: str,
    body: str,
    body_type: str,
    ontvangers: list[str],
    bijlagen: list[tuple[str, str | None, bool]] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> None:
    """Verstuurt een e-mail via Microsoft Graph API.

    bijlagen: lijst van (bestandspad, content_id, is_inline)
      content_id=None, is_inline=False → gewone bijlage
      content_id=<id>, is_inline=True  → inline afbeelding (cid:<id> in HTML)
    """
    token = _graph_token(config)
    afzender = config.ms_sender_email or config.afzender_email

    graph_bijlagen = []
    for pad, content_id, is_inline in bijlagen or []:
        if not os.path.isfile(pad):
            _log.warning("Bijlage niet gevonden, wordt overgeslagen: %s", pad)
            continue
        with open(pad, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        entry: dict = {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": os.path.basename(pad),
            "contentBytes": data,
            "isInline": is_inline,
        }
        if content_id:
            entry["contentId"] = content_id
        graph_bijlagen.append(entry)

    bericht: dict = {
        "message": {
            "subject": onderwerp,
            "body": {"contentType": body_type, "content": body},
            "toRecipients": [{"emailAddress": {"address": a}} for a in ontvangers],
            "from": {"emailAddress": {"address": afzender}},
        }
    }
    if cc:
        bericht["message"]["ccRecipients"] = [{"emailAddress": {"address": a}} for a in cc]
    if bcc:
        bericht["message"]["bccRecipients"] = [{"emailAddress": {"address": a}} for a in bcc]
    if graph_bijlagen:
        bericht["message"]["attachments"] = graph_bijlagen

    try:
        resp = requests.post(
            f"https://graph.microsoft.com/v1.0/users/{afzender}/sendMail",
            json=bericht,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        resp.raise_for_status()
    except Exception:
        _log.warning("Graph API e-mailverzending mislukt", exc_info=True)
        raise


def _graph_beschikbaar(config: Config) -> bool:
    return bool(config.ms_tenant_id and config.ms_client_id and config.ms_client_secret)


# ---------------------------------------------------------------------------
# Publieke functies
# ---------------------------------------------------------------------------


def verstuur_admin_melding(
    config: Config,
    onderwerp: str,
    bericht: str,
    logbestand: str | None = None,
) -> None:
    """Verstuurt een notificatiemail naar alle ADMIN_EMAIL_ONTVANGERS.

    Legt alleen een warning vast als de provider niet geconfigureerd is —
    gooit geen exception zodat de hoofdfout niet verdronken wordt.
    """
    if not config.admin_email_ontvangers:
        _log.warning(
            "Geen ADMIN_EMAIL_ONTVANGERS ingesteld — admin-melding '%s' niet verstuurd.",
            onderwerp,
        )
        return

    ontvangers = config.admin_email_ontvangers

    try:
        if config.email_provider == "graph":
            if not _graph_beschikbaar(config):
                _log.warning(
                    "Graph API niet geconfigureerd (MS_TENANT_ID/CLIENT_ID/CLIENT_SECRET) — "
                    "admin-melding '%s' niet verstuurd.",
                    onderwerp,
                )
                return
            bijlagen = []
            if logbestand and os.path.isfile(logbestand):
                bijlagen.append((logbestand, None, False))
            elif logbestand:
                _log.warning("Logbestand niet gevonden voor bijlage: %s", logbestand)
            _graph_verstuur(config, onderwerp, bericht, "Text", ontvangers, bijlagen)
        else:
            if not _smtp_beschikbaar(config):
                _log.warning(
                    "SMTP niet geconfigureerd (SMTP_HOST of AFZENDER_EMAIL ontbreekt) — "
                    "admin-melding '%s' niet verstuurd.",
                    onderwerp,
                )
                return
            msg = MIMEMultipart()
            msg["From"] = config.afzender_email
            msg["To"] = ", ".join(ontvangers)
            msg["Subject"] = onderwerp
            msg.attach(MIMEText(bericht, "plain", "utf-8"))
            if logbestand and os.path.isfile(logbestand):
                with open(logbestand, "rb") as f:
                    b = MIMEApplication(f.read(), Name=os.path.basename(logbestand))
                b["Content-Disposition"] = f'attachment; filename="{os.path.basename(logbestand)}"'
                msg.attach(b)
            elif logbestand:
                _log.warning("Logbestand niet gevonden voor bijlage: %s", logbestand)
            _smtp_verstuur(config, msg, ontvangers)

        _log.info("Admin-melding verstuurd naar: %s", ", ".join(ontvangers))
    except Exception:
        _log.error("Fout bij verzenden admin-melding '%s'", onderwerp, exc_info=True)


def verstuur_rapport(
    config: Config,
    pdf_pad: str,
    weeknummer: int,
    jaar: int,
    periode_omschrijving: str,
    extra_ontvangers: list[str] | None = None,
    extra_bijlagen: list[str] | None = None,
) -> None:
    """Verstuurt het weekrapport als HTML-mail met PDF-bijlage naar EMAIL_ONTVANGERS.

    extra_bijlagen: optionele lijst van bestandspaden die als gewone bijlage worden meegestuurd.
    """
    to_lijst = list(config.email_ontvangers) + (extra_ontvangers or [])
    cc_lijst = list(config.email_cc)
    bcc_lijst = list(config.email_bcc)
    if not to_lijst:
        _log.warning("Geen EMAIL_ONTVANGERS ingesteld — rapport niet verstuurd.")
        return

    onderwerp = f"Weekoverzicht De Lokalist — week {weeknummer}, {jaar}"
    html = _laad_html_template().format(
        weeknummer=weeknummer,
        jaar=jaar,
        periode=periode_omschrijving,
    )

    try:
        if config.email_provider == "graph":
            if not _graph_beschikbaar(config):
                _log.warning("Graph API niet geconfigureerd — rapport niet verstuurd.")
                return
            bijlagen = (
                [(pad, cid, True) for cid, pad in _RAPPORT_AFBEELDINGEN]
                + [(pdf_pad, None, False)]
                + [(pad, None, False) for pad in (extra_bijlagen or [])]
            )
            _graph_verstuur(
                config,
                onderwerp,
                html,
                "HTML",
                to_lijst,
                bijlagen,
                cc=cc_lijst or None,
                bcc=bcc_lijst or None,
            )
        else:
            if not _smtp_beschikbaar(config):
                _log.warning("SMTP niet geconfigureerd — rapport niet verstuurd.")
                return
            msg = MIMEMultipart("related")
            msg["From"] = f"Miedema Ophaaldienst <{config.afzender_email}>"
            msg["To"] = ", ".join(to_lijst)
            if cc_lijst:
                msg["Cc"] = ", ".join(cc_lijst)
            msg["Subject"] = onderwerp
            alternatief = MIMEMultipart("alternative")
            alternatief.attach(MIMEText(html, "html", "utf-8"))
            msg.attach(alternatief)
            for cid, pad in _RAPPORT_AFBEELDINGEN:
                if os.path.isfile(pad):
                    with open(pad, "rb") as f:
                        afb = MIMEImage(f.read())
                    afb.add_header("Content-ID", f"<{cid}>")
                    afb.add_header("Content-Disposition", "inline", filename=os.path.basename(pad))
                    msg.attach(afb)
                else:
                    _log.warning("Inline afbeelding niet gevonden, wordt overgeslagen: %s", pad)
            for bijlage_pad in [pdf_pad] + (extra_bijlagen or []):
                bestandsnaam = os.path.basename(bijlage_pad)
                with open(bijlage_pad, "rb") as f:
                    bijlage = MIMEApplication(f.read(), Name=bestandsnaam)
                bijlage["Content-Disposition"] = f'attachment; filename="{bestandsnaam}"'
                msg.attach(bijlage)
            alle_ontvangers = to_lijst + cc_lijst + bcc_lijst
            _smtp_verstuur(config, msg, alle_ontvangers)

        alle_log = to_lijst + cc_lijst + bcc_lijst
        _log.info("Rapport verstuurd naar: %s", ", ".join(alle_log))
    except Exception:
        _log.error("Fout bij verzenden rapport", exc_info=True)
        raise
