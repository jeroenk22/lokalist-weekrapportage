"""
Handmatig uitvoerbaar weekrapportage-script.

Start het script, voer week en jaar in wanneer gevraagd, en het:
  1. Haalt orders op uit MendriX (SQL)
  2. Genereert het PDF-rapport naar output/ (prefix: testscript_)
  3. Maakt een samenvattende order aan in MendriX via SOAP
  4. Haalt de volledige order-XML op via SOAP en slaat deze op als output/testscript_{orderId}.xml
  5. Uploadt het PDF naar het dossier van de nieuwe order (REST)

E-mail wordt NIET verstuurd — dat is fase 4 en wacht nog op SMTP-gegevens.

Gebruik:
    python scripts/run_weekrapportage.py            -- interactief + echte calls
    python scripts/run_weekrapportage.py --dry-run  -- XML bouwen en loggen, niets versturen

Vereist in .env:
    DB_SERVER, DB_DATABASE, DB_AUTH_METHOD
    MENDRIX_SOAP_URL, MENDRIX_SOAP_USER, MENDRIX_SOAP_PASS
    MENDRIX_API_URL, MENDRIX_API_TOKEN
    MENDRIX_CA_CERT  (optioneel — pad naar .pem bij zelfondertekend certificaat)

Let op: maakt een ECHTE order aan in MendriX. Verwijder die achteraf handmatig
als je dit als test gebruikt.
"""

import logging
import os
import ssl
import sys
import xml.etree.ElementTree as stdlib_ET
import xml.sax.saxutils as saxutils
from datetime import date, datetime

import defusedxml.ElementTree as ET
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

from lokalist_weekrapportage.config import laad_config
from lokalist_weekrapportage.genereer_rapport import genereer_pdf
from lokalist_weekrapportage.mendrix_soap import bouw_instructies
from lokalist_weekrapportage.query import haal_weekdata_op

LOKALIST_CLIENT_ID = 4787
LOKALIST_PRODUCT_ID = 19
LOKALIST_ADRES = {
    "Name": "De Lokalist",
    "Street": "Dochterenseweg",
    "Number": "13A",
    "PostalCode": "7245 NN",
    "Place": "Laren",
    "Country": "Nederland",
    "CountryCode": "NL",
}

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def _setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    logbestand = os.path.join(
        LOG_DIR, f"testscript_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(logbestand, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logging.getLogger(__name__).info("Logbestand: %s", logbestand)


_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Invoer
# ---------------------------------------------------------------------------


def _vraag_week_en_jaar() -> tuple[int, int]:
    """Vraagt week en jaar interactief op en valideert de invoer."""
    huidig_jaar = datetime.now().year
    print()
    print("=== Lokalist weekrapportage ===")
    print()

    while True:
        try:
            week = int(input("  Weeknummer (1-53): ").strip())
            if not 1 <= week <= 53:
                raise ValueError
            break
        except ValueError:
            print("  Ongeldige waarde — voer een getal tussen 1 en 53 in.")

    while True:
        invoer = input(f"  Jaar [{huidig_jaar}]: ").strip()
        if not invoer:
            jaar = huidig_jaar
            break
        try:
            jaar = int(invoer)
            if not 2000 <= jaar <= 2100:
                raise ValueError
            break
        except ValueError:
            print("  Ongeldige waarde — voer een viercijferig jaar in.")

    print()
    return week, jaar


# ---------------------------------------------------------------------------
# XML-bouw
# ---------------------------------------------------------------------------


def _totaal_laden_colli(rows: list[tuple]) -> int:
    return sum(int(r[6]) for r in rows if str(r[1]).lower() == "laden")


def _totaal_bedrag(rows: list[tuple]) -> float:
    return sum(float(r[10]) for r in rows if r[10])


DISFOOD_ARTNR = 16  # ArtNo van het DISFOOD-staffelartikel

_MAANDEN_NL = [
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
]


def _periode_omschrijving(weeknummer: int, jaar: int) -> str:
    maandag = date.fromisocalendar(jaar, weeknummer, 1)
    zondag = date.fromisocalendar(jaar, weeknummer, 7)
    if maandag.month == zondag.month:
        return f"{maandag.day} t/m {zondag.day} {_MAANDEN_NL[zondag.month - 1]} {jaar}"
    maand_m = _MAANDEN_NL[maandag.month - 1]
    maand_z = _MAANDEN_NL[zondag.month - 1]
    return f"{maandag.day} {maand_m} t/m {zondag.day} {maand_z} {jaar}"


def _bouw_store_xml(
    colli: int, bedrag: float, instructies: str, moment_str: str, weeknummer: int, jaar: int
) -> str:
    instr_esc = saxutils.escape(instructies)
    kenmerk = f"Week {weeknummer} {jaar}"

    aanmaakdag = date.today().isoformat()
    gewenst_begin = f"{aanmaakdag}T08:00:00"
    gewenst_einde = f"{aanmaakdag}T23:59:59"

    return f"""\
<?xml version="1.0" encoding="windows-1252"?>
<EoCustomLinkStoreOrdersNormal Type="TEoCustomLinkStoreOrdersNormal">
  <Data Type="TEoOrderMxList">
    <_TEoListBase_Items>
      <EoOrderMx Type="TEoOrderMx">
        <OrderId Type="TEoKeyIntInfraMx">
          <Id>-1</Id>
        </OrderId>
        <ClientId Type="TEoKeyIntInfraMx">
          <Id>{LOKALIST_CLIENT_ID}</Id>
        </ClientId>
        <IsActive>False</IsActive>
        <MarkChars></MarkChars>
        <Moment>{moment_str}</Moment>
        <OrderType>400</OrderType>
        <ProductId Type="TEoKeyIntInfraMx">
          <Id>{LOKALIST_PRODUCT_ID}</Id>
        </ProductId>
        <ProductIdAutomaticArticles>False</ProductIdAutomaticArticles>
        <Deleted>False</Deleted>
        <ArticlesSell Type="TEoArticleList">
          <_TEoListBase_Items>
            <EoArticleSell Type="TEoArticleSell">
              <ArticleId Type="TEoKeyIntInfraMx">
                <Id>-1</Id>
              </ArticleId>
              <ArticleIdForeign Type="TEoKeyIntInfraMx">
                <Id>{DISFOOD_ARTNR}</Id>
              </ArticleIdForeign>
              <Deleted>False</Deleted>
              <Number>{colli}.0</Number>
              <NumberRaw>{colli}.0</NumberRaw>
              <NumberManual>True</NumberManual>
              <Minimum>{bedrag}</Minimum>
              <PriceManual>True</PriceManual>
              <SortOrder>0</SortOrder>
              <ShowOnInvoice>True</ShowOnInvoice>
            </EoArticleSell>
          </_TEoListBase_Items>
        </ArticlesSell>
        <Goods Type="TEoGoodMxList">
          <_TEoListBase_Items>
            <EoGoodMx Type="TEoGoodMx">
              <GoodId Type="TEoKeyIntInfraMx">
                <Id>-1</Id>
              </GoodId>
              <Packing Type="TEoPackingMx">
                <Name>Colli</Name>
              </Packing>
              <Comments>Totaal geladen colli</Comments>
              <Parts>{colli}.0</Parts>
              <Weight>1.0</Weight>
              <Volume>0.0</Volume>
              <VolumeWeight>0.0</VolumeWeight>
              <ArticleWeight>0.0</ArticleWeight>
              <Depth>0.0</Depth>
              <Height>0.0</Height>
              <Width>0.0</Width>
            </EoGoodMx>
          </_TEoListBase_Items>
        </Goods>
        <Tasks Type="TEoTaskMxList">
          <WaitGetMinutes>0</WaitGetMinutes>
          <WaitBringMinutes>0</WaitBringMinutes>
          <WaitAllMinutes>0</WaitAllMinutes>
          <_TEoListBase_Items>
            <EoTaskMx Type="TEoTaskMx">
              <TaskId Type="TEoKeyIntInfraMx">
                <Id>-1</Id>
              </TaskId>
              <Address Type="TEoAddress">
                <Name>{LOKALIST_ADRES["Name"]}</Name>
                <Street>{LOKALIST_ADRES["Street"]}</Street>
                <Number>{LOKALIST_ADRES["Number"]}</Number>
                <PostalCode>{LOKALIST_ADRES["PostalCode"]}</PostalCode>
                <Place>{LOKALIST_ADRES["Place"]}</Place>
                <Country>{LOKALIST_ADRES["Country"]}</Country>
                <CountryCode>{LOKALIST_ADRES["CountryCode"]}</CountryCode>
              </Address>
              <Completion Type="TEoCompletion">
                <Actual Type="TEoDateTimeWindow">
                  <DateTimeBegin>{moment_str}</DateTimeBegin>
                  <DateTimeEnd>{moment_str}</DateTimeEnd>
                </Actual>
              </Completion>
              <Instructions>{instr_esc}</Instructions>
              <ReferenceYour>{saxutils.escape(kenmerk)}</ReferenceYour>
              <Requested Type="TEoDateTimeWindow">
                <DateTimeBegin>{gewenst_begin}</DateTimeBegin>
                <DateTimeEnd>{gewenst_einde}</DateTimeEnd>
              </Requested>
              <TaskTypeId Type="TEoKeyIntInfraMx">
                <Id>1</Id>
              </TaskTypeId>
              <TaskStateId Type="TEoKeyIntInfraMx">
                <Id>1800</Id>
              </TaskStateId>
              <TaskProblemId Type="TEoKeyIntInfraMx">
                <Id>0</Id>
              </TaskProblemId>
            </EoTaskMx>
          </_TEoListBase_Items>
        </Tasks>
        <GoodsToTasks Type="TEoGoodToTaskMxList">
          <_TEoListBase_Items>
            <EoGoodToTaskMx Type="TEoGoodToTaskMx">
              <GoodId Type="TEoKeyIntInfraMx">
                <Id>-1</Id>
              </GoodId>
              <TaskId Type="TEoKeyIntInfraMx">
                <Id>-1</Id>
              </TaskId>
            </EoGoodToTaskMx>
          </_TEoListBase_Items>
        </GoodsToTasks>
        <InvoiceStatusId>2</InvoiceStatusId>
        <ExternalDone>True</ExternalDone>
        <ExternalSource>0</ExternalSource>
      </EoOrderMx>
    </_TEoListBase_Items>
  </Data>
</EoCustomLinkStoreOrdersNormal>"""


def _bouw_soap_envelope(request_xml: str, gebruiker: str, wachtwoord: str) -> str:
    request_xml_esc = saxutils.escape(request_xml)
    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
                   xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/">
  <SOAP-ENV:Header SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"
                   xmlns:NS1="urn:UCoSoapDispatcherBase">
    <NS1:TAuthenticationHeader xsi:type="NS1:TAuthenticationHeader">
      <UserName xsi:type="xsd:string">{saxutils.escape(gebruiker)}</UserName>
      <Password xsi:type="xsd:string">{saxutils.escape(wachtwoord)}</Password>
    </NS1:TAuthenticationHeader>
  </SOAP-ENV:Header>
  <SOAP-ENV:Body SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
    <NS2:ExecuteRequest xmlns:NS2="urn:UCoSoapDispatcherCustomLink-ICustomLinkSoap">
      <ARequest xsi:type="xsd:string">{request_xml_esc}</ARequest>
    </NS2:ExecuteRequest>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""


# ---------------------------------------------------------------------------
# SOAP
# ---------------------------------------------------------------------------


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ca() -> str | bool:
    """CA-cert pad uit .env, False om verificatie over te slaan, True voor systeemcerts.

    Relatieve paden worden opgelost vanuit de projectroot.
    """
    waarde = os.getenv("MENDRIX_CA_CERT", "").strip()
    if waarde.lower() == "false":
        _log.warning(
            "MENDRIX_CA_CERT=false — TLS-verificatie uitgeschakeld."
            " Alleen gebruiken op intern netwerk."
        )
        return False
    if waarde:
        pad = waarde if os.path.isabs(waarde) else os.path.join(_PROJECT_ROOT, waarde)
        return pad
    return True


def _sessie() -> requests.Session:
    """Sessie met een permissieve SSL-context voor de MendriX-server.

    De server draait vermoedelijk op TLS 1.0/1.1 of met verouderde cipher suites
    die Python 3.13+ standaard weigert. SECLEVEL=1 staat deze toe.
    Certificaatverificatie wordt volledig in de context geregeld zodat
    check_hostname en verify_mode consistent blijven.
    """
    ca = _ca()
    ctx = create_urllib3_context()
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    ctx.minimum_version = ssl.TLSVersion.TLSv1

    if ca is False:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    elif isinstance(ca, str):
        ctx.load_verify_locations(ca)

    class _LegacyTLSAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["ssl_context"] = ctx
            super().init_poolmanager(*args, **kwargs)

        def proxy_manager_for(self, proxy, **kwargs):
            kwargs["ssl_context"] = ctx
            return super().proxy_manager_for(proxy, **kwargs)

    sessie = requests.Session()
    sessie.mount("https://", _LegacyTLSAdapter())
    return sessie


def _stuur_soap(soap_url: str, gebruiker: str, wachtwoord: str, request_xml: str) -> str:
    envelope = _bouw_soap_envelope(request_xml, gebruiker, wachtwoord)
    with _sessie() as s:
        resp = s.post(
            soap_url,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'},
            timeout=30,
        )
    resp.raise_for_status()
    return resp.text


def _extraheer_order_id(soap_respons: str) -> int:
    """Haalt het nieuwe order-ID uit de EoStoreResultList in de SOAP-respons.

    De SOAP-wrapper gebruikt <return> als elementnaam. De inhoud is
    HTML-escaped XML. Het eerste srInserted-item is de order.
    """
    root = ET.fromstring(soap_respons)
    return_el = root.find(".//{*}return")
    if return_el is None or not return_el.text:
        raise ValueError("Geen <return>-element gevonden in SOAP-respons")

    result_root = ET.fromstring(return_el.text)
    for item in result_root.findall(".//_TEoListBase_Items/EoStoreResult"):
        if item.findtext("StoreResult") == "srInserted":
            order_id_text = item.findtext("Id")
            if order_id_text:
                return int(order_id_text)

    raise ValueError("Geen srInserted-resultaat gevonden in respons:\n" + return_el.text)


def _bouw_request_order_xml(order_id: int) -> str:
    return f"""\
<?xml version="1.0" encoding="windows-1252"?>
<EoCustomLinkRequestOrdersNormal Type="TEoCustomLinkRequestOrdersNormal"
  xsi:noNamespaceSchemaLocation="GdxEoStructures.xsd"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Nested>False</Nested>
  <Filter Type="TEoFilterOrdersNormal">
    <KeysExplicitAsCsv>{order_id}</KeysExplicitAsCsv>
  </Filter>
</EoCustomLinkRequestOrdersNormal>"""


def _extraheer_en_format_xml(soap_respons: str) -> str:
    """Haalt de inner XML uit de SOAP <return> en geeft nette, ingesprongen XML terug."""
    root = ET.fromstring(soap_respons)
    return_el = root.find(".//{*}return")
    if return_el is None or not return_el.text:
        raise ValueError("Geen <return>-element gevonden in SOAP-respons")
    # defusedxml parseert veilig; indent/tostring zijn pure serialisatie (geen XXE-risico)
    inner_root = ET.fromstring(return_el.text)
    stdlib_ET.indent(inner_root, space="  ")
    return stdlib_ET.tostring(inner_root, encoding="unicode", xml_declaration=True) + "\n"


def _haal_order_xml_op(soap_url: str, gebruiker: str, wachtwoord: str, order_id: int) -> str:
    soap_respons = _stuur_soap(soap_url, gebruiker, wachtwoord, _bouw_request_order_xml(order_id))
    return _extraheer_en_format_xml(soap_respons)


def _sla_order_xml_op(output_dir: str, order_id: int, order_xml: str) -> str:
    pad = os.path.join(output_dir, f"testscript_{order_id}.xml")
    with open(pad, "w", encoding="utf-8") as f:
        f.write(order_xml)
    return pad


# ---------------------------------------------------------------------------
# REST dossier-upload
# ---------------------------------------------------------------------------


def _rest_login(api_base: str, api_token: str) -> str:
    """Logt in en geeft een kortstondige JWT terug."""
    url = api_base.rstrip("/") + "/account/login-api-token"
    with _sessie() as s:
        resp = s.post(url, json={"token": api_token}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["data"]["items"][0]["access"]
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Onverwachte login-respons: {data}") from exc


def _upload_pdf_naar_dossier(
    api_base: str, jwt: str, order_id: int, pdf_pad: str, bestandsnaam: str
) -> None:
    """POST het PDF als octet-stream naar het dossier van de order."""
    url = api_base.rstrip("/") + f"/dossier/dossiers/orders/{order_id}/contents/{bestandsnaam}"
    with open(pdf_pad, "rb") as f:
        pdf_bytes = f.read()
    with _sessie() as s:
        resp = s.post(
            url,
            data=pdf_bytes,
            headers={
                "Content-Type": "application/octet-stream",
                "Authorization": f"Bearer {jwt}",
            },
            timeout=60,
        )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Hoofdstroom
# ---------------------------------------------------------------------------


def main(dry_run: bool) -> None:
    load_dotenv()

    soap_url = os.getenv("MENDRIX_SOAP_URL")
    soap_user = os.getenv("MENDRIX_SOAP_USER")
    soap_pass = os.getenv("MENDRIX_SOAP_PASS")
    api_base = os.getenv("MENDRIX_API_URL")
    api_token = os.getenv("MENDRIX_API_TOKEN")

    if not all([soap_url, soap_user, soap_pass]):
        _log.error("MENDRIX_SOAP_URL, MENDRIX_SOAP_USER en MENDRIX_SOAP_PASS zijn vereist in .env")
        sys.exit(1)
    if not dry_run and not all([api_base, api_token]):
        _log.error("MENDRIX_API_URL en MENDRIX_API_TOKEN zijn vereist in .env voor dossier-upload")
        sys.exit(1)

    _setup_logging()
    config = laad_config()
    week_nr, jaar = _vraag_week_en_jaar()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Stap 1: data ophalen ---
    _log.info("=== Stap 1: orders ophalen voor week %d, %d ===", week_nr, jaar)
    rows = haal_weekdata_op(config, week_nr, jaar)
    _log.info("  %d rijen opgehaald", len(rows))
    if not rows:
        _log.warning("Geen orders gevonden voor week %d, %d — gestopt.", week_nr, jaar)
        sys.exit(0)

    # --- Stap 2: PDF genereren ---
    _log.info("=== Stap 2: PDF genereren ===")
    pdf_bestandsnaam = f"testscript_lokalist_week{week_nr}_{jaar}.pdf"
    pdf_pad_str = os.path.join(OUTPUT_DIR, pdf_bestandsnaam)
    pdf_pad, totals = genereer_pdf(
        rows=rows,
        weeknummer=week_nr,
        jaar=jaar,
        periode_omschrijving=_periode_omschrijving(week_nr, jaar),
        output_path=pdf_pad_str,
    )
    _log.info("  PDF: %s", pdf_pad)
    _log.info("  Totalen: %s", totals)

    # --- Stap 3: SOAP-order aanmaken ---
    _log.info(
        "=== Stap 3: samenvattende order %s ===",
        "(DRY RUN)" if dry_run else "aanmaken in MendriX",
    )
    instructies = bouw_instructies(rows, week_nr, jaar)
    colli = _totaal_laden_colli(rows)
    bedrag = _totaal_bedrag(rows)
    moment = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    _log.info("  Laden colli: %d", colli)
    _log.info("  Totaal bedrag (laden+lossen): %.2f", bedrag)
    _log.info("  Instructions:\n%s", instructies)

    store_xml = _bouw_store_xml(colli, bedrag, instructies, moment, week_nr, jaar)
    _log.debug("  Store XML:\n%s", store_xml)

    if dry_run:
        _log.info("  DRY RUN: SOAP-call en dossier-upload overgeslagen.")
        return

    _log.warning("  *** LET OP: er wordt nu een ECHTE order aangemaakt in MendriX! ***")
    try:
        soap_respons = _stuur_soap(soap_url, soap_user, soap_pass, store_xml)
    except requests.HTTPError as exc:
        _log.error(
            "SOAP-call mislukt (HTTP %s):\n%s",
            exc.response.status_code if exc.response is not None else "?",
            exc.response.text if exc.response is not None else "",
        )
        raise

    order_id = _extraheer_order_id(soap_respons)
    _log.info("  Order-ID: %d", order_id)

    _log.info("  Volledige order-XML ophalen voor order %d", order_id)
    order_xml = _haal_order_xml_op(soap_url, soap_user, soap_pass, order_id)
    order_xml_pad = _sla_order_xml_op(OUTPUT_DIR, order_id, order_xml)

    print(f"\n  Order aangemaakt: {order_id}")
    print(f"  Order XML:        {order_xml_pad}")

    _log.info("  Order XML opgeslagen: %s", order_xml_pad)

    # --- Stap 4: PDF uploaden naar dossier ---
    _log.info("=== Stap 4: PDF uploaden naar dossier van order %d ===", order_id)
    try:
        jwt = _rest_login(api_base, api_token)
        _upload_pdf_naar_dossier(api_base, jwt, order_id, pdf_pad, pdf_bestandsnaam)
        print(f"  PDF in dossier:   orders/{order_id}/{pdf_bestandsnaam}")
        _log.info("  PDF geüpload: orders/%d/%s", order_id, pdf_bestandsnaam)
    except requests.HTTPError as exc:
        _log.error(
            "Dossier-upload mislukt (HTTP %s):\n%s",
            exc.response.status_code if exc.response is not None else "?",
            exc.response.text if exc.response is not None else "",
        )
        raise


if __name__ == "__main__":
    _dry = "--dry-run" in sys.argv
    main(dry_run=_dry)
