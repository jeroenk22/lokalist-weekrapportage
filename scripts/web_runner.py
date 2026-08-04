"""JSON-entrypoint voor het webdashboard.

Leest één JSON-opdracht van stdin en schrijft NDJSON-gebeurtenissen naar stdout.
De Node-backend start dit script en streamt de voortgang door naar de browser.

BELANGRIJK — stdout is een datakanaal: daar komt uitsluitend NDJSON op. Alle
logging gaat naar het logbestand én naar stderr, nooit naar stdout.

Opdrachten
----------
  {"command": "lijst"}
      → alle actieve verzamelorders + de standaard e-mailinstellingen

  {"command": "regenereer",
   "orderId": 1266289,
   "email": {"to": [...], "cc": [...], "bcc": [...]},
   "dryRun": false}
      → genereert het rapport van de week van die order opnieuw

Volgorde bij regenereren (bewust: eerst nieuw, dan oud weg)
-----------------------------------------------------------
  1. orders ophalen uit de database
  2. PDF genereren
  3. nieuwe verzamelorder aanmaken in MendriX
  4. order-XML ophalen en wegschrijven
  5. PDF + ordernummers.txt in het dossier zetten
  6. rapport e-mailen
  7. pas nu de oude verzamelorder verwijderen

Faalt stap 4, 5 of 6, dan wordt de zojuist aangemaakte order weer verwijderd en
blijft de oorspronkelijke verzamelorder ongemoeid. Er gaat dus nooit een order
verloren door een halverwege mislukte run.
"""

import dataclasses
import json
import logging
import os
import sys
import traceback
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from dotenv import load_dotenv

from lokalist_weekrapportage.config import laad_config
from lokalist_weekrapportage.email_allowlist import (
    geweigerde_adressen,
    lees_allowlist,
    omschrijf,
)
from lokalist_weekrapportage.genereer_rapport import genereer_pdf
from lokalist_weekrapportage.mailer import verstuur_rapport
from lokalist_weekrapportage.mendrix_client import (
    extraheer_order_id,
    haal_order_xml_op,
    rest_login,
    stuur_soap,
    upload_bestand_naar_dossier,
    verwijder_order,
)
from lokalist_weekrapportage.mendrix_soap import bouw_instructies, bouw_ordernummers_txt
from lokalist_weekrapportage.query import haal_spoeddata_op, haal_weekdata_op
from lokalist_weekrapportage.verzamelorder import (
    NAAM_MAXLENGTE,
    bouw_handmatige_notitie,
    bouw_store_xml,
    periode_omschrijving,
    totaal_bedrag,
    totaal_laden_colli,
)
from lokalist_weekrapportage.verzamelorder_query import haal_verzamelorders_op

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")
OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "output")

TOTAAL_STAPPEN = 7

_log = logging.getLogger("dashboard")
_logbestand = ""


# ---------------------------------------------------------------------------
# Uitvoer naar de Node-backend
# ---------------------------------------------------------------------------


def _emit(gebeurtenis: dict) -> None:
    """Schrijft één NDJSON-regel naar stdout en flusht direct."""
    sys.stdout.write(json.dumps(gebeurtenis, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _stap(nummer: int, bericht: str) -> None:
    _log.info("=== Stap %d/%d: %s ===", nummer, TOTAAL_STAPPEN, bericht)
    _emit({"type": "stap", "nummer": nummer, "totaal": TOTAAL_STAPPEN, "bericht": bericht})


def _melding(bericht: str, niveau: str = "info") -> None:
    getattr(_log, niveau)(bericht)
    _emit({"type": "log", "niveau": niveau, "bericht": bericht})


# ---------------------------------------------------------------------------
# Logging — zelfde opzet als de geplande zondagrun
# ---------------------------------------------------------------------------


# Alleen een handmatige hergeneratie krijgt een eigen logbestand. Het ophalen
# van de lijst gebeurt bij élke pagina-verversing; daar een bestand voor
# aanmaken levert alleen ruis op tussen de runs die er wél toe doen.
LOGBESTAND_PREFIX = {"regenereer": "handmatig"}


def _setup_logging(opdrachtnaam: str | None) -> str:
    """Zet logging op. Geeft het pad van het logbestand terug, of "" als er geen
    bestand wordt geschreven (dan gaat alles alleen naar stderr).
    """
    global _logbestand
    prefix = LOGBESTAND_PREFIX.get(opdrachtnaam or "")

    # stderr altijd: stdout is gereserveerd voor het NDJSON-protocol.
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    if prefix:
        os.makedirs(LOG_DIR, exist_ok=True)
        _logbestand = os.path.join(
            LOG_DIR, f"{prefix}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
        )
        handlers.insert(0, logging.FileHandler(_logbestand, encoding="utf-8"))
    else:
        _logbestand = ""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )
    if _logbestand:
        _log.info("Logbestand: %s", _logbestand)
    return _logbestand


def _ruim_oude_logs_op(dagen: int = 60) -> None:
    """Verwijdert logbestanden ouder dan `dagen`, net als de zondagrun.

    Alleen `.log`: in logs/ staat ook `.gitkeep`, en die houdt de map in Git.
    Zonder deze filter ruimt de eerste hergeneratie na 60 dagen dat bestand op.
    """
    grens = datetime.now().timestamp() - dagen * 86400
    verwijderd = 0
    for bestand in os.listdir(LOG_DIR):
        if not bestand.endswith(".log"):
            continue
        pad = os.path.join(LOG_DIR, bestand)
        try:
            if os.path.isfile(pad) and os.path.getmtime(pad) < grens:
                os.remove(pad)
                verwijderd += 1
        except OSError:
            _log.warning("Kon oud logbestand niet verwijderen: %s", pad)
    if verwijderd:
        _log.info("Oude logbestanden opgeruimd: %d bestand(en).", verwijderd)


# ---------------------------------------------------------------------------
# Opdracht: lijst
# ---------------------------------------------------------------------------


def _standaard_uitgevinkt() -> list[str]:
    """Adressen die in de modal zichtbaar zijn maar niet vooraf aangevinkt.

    Bedoeld voor ontvangers die het wekelijkse rapport wél automatisch krijgen,
    maar bij een handmatige hergeneratie meestal niet nodig zijn. De gebruiker
    kan ze in de modal alsnog aanvinken.

    Alleen voor het dashboard: config.py en daarmee de zondagrun blijven
    ongemoeid, dus de automatische mailing verandert hier niet door.
    """
    ruw = os.getenv("DASHBOARD_EMAIL_UITGEVINKT", "")
    return [adres.strip() for adres in ruw.split(",") if adres.strip()]


def _vaste_ontvangers(config) -> list[str]:
    """Alle adressen die al uit .env komen.

    Die zijn per definitie toegestaan, ook als hun domein niet in de allowlist
    staat: ze horen bij de wekelijkse mailing en zijn dus al goedgekeurd.
    """
    return [
        *config.email_ontvangers,
        *config.email_cc,
        *config.email_bcc,
        *_standaard_uitgevinkt(),
    ]


def _opdracht_lijst(config) -> dict:
    orders = haal_verzamelorders_op(config)
    uitgevinkt = _standaard_uitgevinkt()
    allowlist = lees_allowlist()
    if uitgevinkt:
        _log.info("Standaard uitgevinkt in de modal: %s", ", ".join(uitgevinkt))
    if allowlist:
        _log.info("Toegestane ontvangers: %s", omschrijf(allowlist))
    return {
        "verzamelorders": [vo.as_dict() for vo in orders],
        "email": {
            "to": list(config.email_ontvangers),
            "cc": list(config.email_cc),
            "bcc": list(config.email_bcc),
            "uitgevinkt": uitgevinkt,
            # Alleen ter informatie voor de UI; de echte grendel staat in
            # _controleer_ontvangers hieronder.
            "allowlist": allowlist,
            "afzender": config.afzender_email,
            "provider": config.email_provider,
        },
    }


# ---------------------------------------------------------------------------
# Opdracht: regenereer
# ---------------------------------------------------------------------------


def _soap_gegevens() -> tuple[str, str, str]:
    url = os.getenv("MENDRIX_SOAP_URL")
    user = os.getenv("MENDRIX_SOAP_USER")
    wachtwoord = os.getenv("MENDRIX_SOAP_PASS")
    if not all([url, user, wachtwoord]):
        raise RuntimeError(
            "MENDRIX_SOAP_URL, MENDRIX_SOAP_USER en MENDRIX_SOAP_PASS zijn vereist in .env"
        )
    return url, user, wachtwoord


def _rest_gegevens() -> tuple[str, str]:
    api_base = os.getenv("MENDRIX_API_URL")
    api_token = os.getenv("MENDRIX_API_TOKEN")
    if not all([api_base, api_token]):
        raise RuntimeError(
            "MENDRIX_API_URL en MENDRIX_API_TOKEN zijn vereist in .env voor de dossier-upload"
        )
    return api_base, api_token


def _config_met_email(config, email: dict):
    """Config-kopie met de e-mailadressen uit het dashboard.

    De gebruiker kan in de modal adressen uitvinken of toevoegen en het
    Aan-adres aanpassen. mailer.py blijft hierdoor ongewijzigd bruikbaar.
    """
    return dataclasses.replace(
        config,
        email_ontvangers=[a.strip() for a in email.get("to", []) if a and a.strip()],
        email_cc=[a.strip() for a in email.get("cc", []) if a and a.strip()],
        email_bcc=[a.strip() for a in email.get("bcc", []) if a and a.strip()],
    )


def _controleer_ontvangers(config, email: dict) -> None:
    """Weigert ontvangers buiten de allowlist.

    Het rapport bevat klantgegevens; in de modal kan iemand het Aan-adres
    aanpassen of adressen toevoegen. Zonder deze controle gaat het naar elk
    ingetypt adres. Staat DASHBOARD_EMAIL_DOMEINEN leeg, dan is er geen grens.

    Deze controle staat bewust hier en niet alleen in de UI — de browser is
    geen beveiliging.
    """
    allowlist = lees_allowlist()
    if not allowlist:
        return

    adressen = [adres for veld in ("to", "cc", "bcc") for adres in (email.get(veld) or [])]
    geweigerd = geweigerde_adressen(adressen, allowlist, _vaste_ontvangers(config))
    if not geweigerd:
        return

    _log.warning("Ontvangers buiten de allowlist geweigerd: %s", ", ".join(geweigerd))
    raise ValueError(
        f"Deze ontvanger(s) zijn niet toegestaan: {', '.join(geweigerd)}. Het rapport bevat "
        f"klantgegevens en mag alleen naar {omschrijf(allowlist)}. Hoort dit adres er wel "
        f"bij, vul het dan aan in DASHBOARD_EMAIL_DOMEINEN in .env."
    )


def _zoek_verzamelorder(config, order_id: int):
    for vo in haal_verzamelorders_op(config):
        if vo.order_id == order_id:
            return vo
    raise ValueError(
        f"Verzamelorder {order_id} niet gevonden. "
        f"Mogelijk is deze al verwijderd — ververs het dashboard."
    )


def _opdracht_regenereer(config, opdracht: dict) -> dict:
    order_id = int(opdracht["orderId"])
    dry_run = bool(opdracht.get("dryRun", False))
    email_instellingen = opdracht.get("email") or {}

    # Wie het doet leggen we vast in de order; zonder naam beginnen we niet.
    naam = " ".join(str(opdracht.get("naam") or "").split())
    if not naam:
        raise ValueError(
            "Vul in wie het rapport opnieuw genereert — die naam wordt in de order vastgelegd."
        )
    # Spiegelt de maxLength van het naamveld in de modal. Zonder deze controle
    # zou bouw_handmatige_notitie een te lange naam stilzwijgend inkorten om
    # binnen de 250 tekens van Diversen te blijven.
    if len(naam) > NAAM_MAXLENGTE:
        raise ValueError(
            f"De naam mag maximaal {NAAM_MAXLENGTE} tekens zijn; deze is {len(naam)} tekens."
        )

    _controleer_ontvangers(config, email_instellingen)

    soap_url, soap_user, soap_pass = _soap_gegevens()
    if not dry_run:
        api_base, api_token = _rest_gegevens()

    oude = _zoek_verzamelorder(config, order_id)

    # Harde grendel: een gefactureerde order mag nooit verdwijnen. Hergenereren
    # verwijdert hem en maakt een nieuwe met een ander ordernummer aan, waardoor
    # de factuurregel naar een niet meer bestaande order zou wijzen. Deze controle
    # staat bewust hier en niet alleen in de UI — de browser is geen beveiliging.
    if oude.gefactureerd:
        raise ValueError(
            f"Verzamelorder {order_id} staat op een {oude.factuur_omschrijving} en kan niet "
            f"opnieuw gegenereerd worden. Hergenereren zou de order verwijderen, waardoor "
            f"de factuurregel naar een verdwenen order verwijst. Neem contact op met de "
            f"administratie als dit rapport toch aangepast moet worden."
        )

    week_nr, jaar = oude.weeknummer, oude.jaar

    # Kop in het logbestand: in één oogopslag zichtbaar wat dit was en van wie.
    _log.info("=" * 70)
    _log.info("HANDMATIGE HERGENERATIE%s", " (DRY RUN)" if dry_run else "")
    _log.info("  Aangevraagd door : %s", naam)
    _log.info("  Verzamelorder    : %d (week %d %d)", order_id, week_nr, jaar)
    _log.info("  Oorspronkelijk   : %s", oude.label)
    _log.info("=" * 70)

    _melding(f"Verzamelorder {order_id} gevonden — week {week_nr} {jaar}, aangemaakt {oude.label}.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    periode = periode_omschrijving(week_nr, jaar)

    # --- Stap 1: data ophalen ---
    _stap(1, f"orders ophalen voor week {week_nr}, {jaar}")
    try:
        spoed_rows = haal_spoeddata_op(config, week_nr, jaar)
        spoed_ids = [int(r[1]) for r in spoed_rows]
        rows = haal_weekdata_op(config, week_nr, jaar, spoed_order_ids=spoed_ids)
    except Exception:
        _log.error("Stap 1 mislukt: data ophalen uit database.", exc_info=True)
        raise
    _melding(f"{len(rows)} normale rijen en {len(spoed_rows)} spoedorder(s) opgehaald.")
    if not rows and not spoed_rows:
        raise ValueError(
            f"Geen orders gevonden voor week {week_nr} {jaar}. De verzamelorder is niet aangepast."
        )

    # --- Stap 2: PDF genereren ---
    _stap(2, "PDF genereren")
    pdf_bestandsnaam = f"lokalist_week{week_nr}_{jaar}.pdf"
    pdf_pad_str = os.path.join(OUTPUT_DIR, pdf_bestandsnaam)
    try:
        pdf_pad, totals = genereer_pdf(
            rows=rows,
            weeknummer=week_nr,
            jaar=jaar,
            periode_omschrijving=periode,
            output_path=pdf_pad_str,
            spoed_rows=spoed_rows or None,
        )
    except Exception:
        _log.error("Stap 2 mislukt: PDF genereren naar %s.", pdf_pad_str, exc_info=True)
        raise
    _melding(f"PDF gegenereerd: {os.path.basename(pdf_pad)} — totalen: {totals}")

    instructies = bouw_instructies(rows, week_nr, jaar, spoed_rows=spoed_rows)
    colli = totaal_laden_colli(rows) + sum(int(r[6]) for r in (spoed_rows or []))
    bedrag = totaal_bedrag(rows) + sum(float(r[7]) for r in (spoed_rows or []))
    nu = datetime.now()
    moment = nu.strftime("%Y-%m-%dT%H:%M:%S")
    notitie = bouw_handmatige_notitie(week_nr, jaar, order_id, naam)
    store_xml = bouw_store_xml(colli, bedrag, instructies, moment, week_nr, jaar, notities=notitie)

    if dry_run:
        _melding("DRY RUN — er wordt niets aangemaakt, verwijderd of verstuurd.", niveau="warning")
        return {
            "dryRun": True,
            "oudeOrderId": order_id,
            "weeknummer": week_nr,
            "jaar": jaar,
            "pdf": pdf_pad,
            "colli": colli,
            "bedrag": bedrag,
            "notitie": notitie,
            "naam": naam,
        }

    # --- Stap 3: nieuwe verzamelorder aanmaken ---
    _stap(3, "nieuwe verzamelorder aanmaken in MendriX")
    _log.info("Laden colli: %d | totaalbedrag: %.2f", colli, bedrag)
    try:
        soap_respons = stuur_soap(soap_url, soap_user, soap_pass, store_xml)
        nieuw_order_id = extraheer_order_id(soap_respons)
    except Exception:
        _log.error("Stap 3 mislukt: nieuwe order aanmaken.", exc_info=True)
        raise
    _melding(f"Nieuwe verzamelorder aangemaakt: {nieuw_order_id}")

    # Vanaf hier draaien we alles binnen een vangnet: gaat er iets mis, dan
    # ruimen we de zojuist aangemaakte order op en blijft de oude bestaan.
    try:
        # --- Stap 4: order-XML ophalen ---
        _stap(4, f"order-XML van {nieuw_order_id} ophalen")
        order_xml = haal_order_xml_op(soap_url, soap_user, soap_pass, nieuw_order_id)
        xml_pad = os.path.join(OUTPUT_DIR, f"dashboard_{nieuw_order_id}.xml")
        with open(xml_pad, "w", encoding="utf-8") as f:
            f.write(order_xml)
        _melding(f"Order-XML opgeslagen: {os.path.basename(xml_pad)}")

        # --- Stap 5: dossier vullen ---
        _stap(5, "PDF en ordernummers.txt in het dossier zetten")
        txt_bestandsnaam = f"lokalist_week{week_nr}_{jaar}_ordernummers.txt"
        txt_pad = os.path.join(OUTPUT_DIR, txt_bestandsnaam)
        with open(txt_pad, "w", encoding="utf-8") as f:
            f.write(bouw_ordernummers_txt(rows, week_nr, jaar, spoed_rows=spoed_rows))

        jwt = rest_login(api_base, api_token)
        # Let op: niet 'naam' als lusvariabele — dat is hierboven de gebruikersnaam.
        for bestand, bestandsnaam in [(pdf_pad, pdf_bestandsnaam), (txt_pad, txt_bestandsnaam)]:
            upload_bestand_naar_dossier(api_base, jwt, nieuw_order_id, bestand, bestandsnaam)
            _melding(f"Geüpload naar dossier: orders/{nieuw_order_id}/{bestandsnaam}")

        # --- Stap 6: e-mail versturen ---
        _stap(6, "rapport e-mailen")
        mail_config = _config_met_email(config, email_instellingen)
        if not mail_config.email_ontvangers:
            raise ValueError(
                "Geen enkel Aan-adres opgegeven — het rapport kan niet verstuurd worden."
            )
        verstuur_rapport(
            config=mail_config,
            pdf_pad=pdf_pad,
            weeknummer=week_nr,
            jaar=jaar,
            periode_omschrijving=periode,
            extra_bijlagen=[txt_pad],
        )
        _melding(
            "Rapport verstuurd — Aan: "
            + ", ".join(mail_config.email_ontvangers)
            + (f" | CC: {', '.join(mail_config.email_cc)}" if mail_config.email_cc else "")
            + (f" | BCC: {', '.join(mail_config.email_bcc)}" if mail_config.email_bcc else "")
        )

    except Exception:
        _log.error(
            "Fout na het aanmaken van order %d — nieuwe order wordt teruggedraaid.",
            nieuw_order_id,
            exc_info=True,
        )
        _melding(
            f"Fout opgetreden. Nieuwe order {nieuw_order_id} wordt verwijderd; "
            f"de oorspronkelijke verzamelorder {order_id} blijft bestaan.",
            niveau="warning",
        )
        try:
            verwijder_order(soap_url, soap_user, soap_pass, nieuw_order_id)
            _melding(f"Terugdraaien geslaagd — order {nieuw_order_id} verwijderd.")
        except Exception:
            _log.error("Terugdraaien mislukt voor order %d.", nieuw_order_id, exc_info=True)
            _melding(
                f"LET OP: terugdraaien mislukt. Order {nieuw_order_id} staat mogelijk nog "
                f"in MendriX en moet handmatig gecontroleerd worden.",
                niveau="error",
            )
        raise

    # --- Stap 7: oude verzamelorder verwijderen ---
    _stap(7, f"oude verzamelorder {order_id} verwijderen")
    try:
        verwijder_order(soap_url, soap_user, soap_pass, order_id)
    except Exception:
        _log.error("Stap 7 mislukt: oude order %d verwijderen.", order_id, exc_info=True)
        _melding(
            f"Het nieuwe rapport is volledig verwerkt, maar de oude verzamelorder "
            f"{order_id} kon niet verwijderd worden. Verwijder deze handmatig in MendriX.",
            niveau="error",
        )
        raise
    _melding(f"Oude verzamelorder {order_id} verwijderd.")

    return {
        "dryRun": False,
        "oudeOrderId": order_id,
        "nieuweOrderId": nieuw_order_id,
        "weeknummer": week_nr,
        "jaar": jaar,
        "pdf": pdf_pad,
        "colli": colli,
        "bedrag": bedrag,
        "notitie": notitie,
        "naam": naam,
    }


# ---------------------------------------------------------------------------
# Hoofdstroom
# ---------------------------------------------------------------------------

_OPDRACHTEN = {
    "lijst": lambda config, opdracht: _opdracht_lijst(config),
    "regenereer": _opdracht_regenereer,
}


def main() -> int:
    load_dotenv()

    # Eerst de opdracht lezen: die bepaalt of er een logbestand komt en hoe het heet.
    try:
        ruwe_invoer = sys.stdin.read()
        opdracht = json.loads(ruwe_invoer) if ruwe_invoer.strip() else {}
    except json.JSONDecodeError as exc:
        _setup_logging(None)
        _log.error("Ongeldige JSON-opdracht ontvangen: %s", exc)
        _emit({"type": "fout", "bericht": f"Ongeldige JSON-opdracht: {exc}", "logbestand": ""})
        return 2

    naam = opdracht.get("command")
    logbestand = _setup_logging(naam)
    if logbestand:
        _ruim_oude_logs_op()

    handler = _OPDRACHTEN.get(naam)
    if handler is None:
        _emit(
            {
                "type": "fout",
                "bericht": f"Onbekende opdracht: {naam!r}. "
                f"Geldig: {', '.join(sorted(_OPDRACHTEN))}.",
                "logbestand": logbestand,
            }
        )
        return 2

    _log.info("Opdracht '%s' gestart.", naam)
    try:
        config = laad_config()
        resultaat = handler(config, opdracht)
    except Exception as exc:
        _log.error("Opdracht '%s' afgebroken.", naam, exc_info=True)
        _emit(
            {
                "type": "fout",
                "bericht": str(exc) or exc.__class__.__name__,
                "details": traceback.format_exc(),
                "logbestand": logbestand,
            }
        )
        return 1

    _log.info("Opdracht '%s' voltooid.", naam)
    _emit({"type": "klaar", "data": resultaat, "logbestand": logbestand})
    return 0


if __name__ == "__main__":
    sys.exit(main())
