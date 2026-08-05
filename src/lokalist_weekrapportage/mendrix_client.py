"""Gedeelde MendriX-koppeling: SOAP-transport en REST dossier-upload.

Deze module bevat de plumbing die eerder in scripts/run_weekrapportage.py stond.
Zowel de geplande zondagrun als het webdashboard gebruiken deze code, zodat er
maar één implementatie bestaat en beide routes gegarandeerd identiek werken.

De functies zijn ongewijzigd overgenomen uit run_weekrapportage.py; alleen de
naamgeving is publiek gemaakt en er is een verwijder_order()-functie bijgekomen.
"""

import logging
import os
import ssl
import xml.etree.ElementTree as stdlib_ET

import defusedxml.ElementTree as ET
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

_log = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

_ca_warning_gelogd = False


def ca_instelling() -> str | bool:
    """CA-cert pad uit .env, False om verificatie over te slaan, True voor systeemcerts.

    Relatieve paden worden opgelost vanuit de projectroot.
    """
    global _ca_warning_gelogd
    waarde = os.getenv("MENDRIX_CA_CERT", "").strip()
    if waarde.lower() == "false":
        if not _ca_warning_gelogd:
            _log.warning(
                "MENDRIX_CA_CERT=false — TLS-verificatie uitgeschakeld."
                " Alleen gebruiken op intern netwerk."
            )
            _ca_warning_gelogd = True
        return False
    if waarde:
        pad = waarde if os.path.isabs(waarde) else os.path.join(_PROJECT_ROOT, waarde)
        return pad
    return True


def sessie() -> requests.Session:
    """Sessie met een permissieve SSL-context voor de MendriX-server.

    De server draait vermoedelijk op TLS 1.0/1.1 of met verouderde cipher suites
    die Python 3.13+ standaard weigert. SECLEVEL=1 staat deze toe.
    Certificaatverificatie wordt volledig in de context geregeld zodat
    check_hostname en verify_mode consistent blijven.
    """
    ca = ca_instelling()
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

    s = requests.Session()
    s.mount("https://", _LegacyTLSAdapter())
    return s


# ---------------------------------------------------------------------------
# SOAP
# ---------------------------------------------------------------------------


def bouw_soap_envelope(request_xml: str, gebruiker: str, wachtwoord: str) -> str:
    import xml.sax.saxutils as saxutils

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


def stuur_soap(soap_url: str, gebruiker: str, wachtwoord: str, request_xml: str) -> str:
    envelope = bouw_soap_envelope(request_xml, gebruiker, wachtwoord)
    with sessie() as s:
        resp = s.post(
            soap_url,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'},
            timeout=30,
        )
    resp.raise_for_status()
    return resp.text


def extraheer_order_id(soap_respons: str) -> int:
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


def bouw_request_order_xml(order_id: int) -> str:
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


def extraheer_en_format_xml(soap_respons: str) -> str:
    """Haalt de inner XML uit de SOAP <return> en geeft nette, ingesprongen XML terug."""
    root = ET.fromstring(soap_respons)
    return_el = root.find(".//{*}return")
    if return_el is None or not return_el.text:
        raise ValueError("Geen <return>-element gevonden in SOAP-respons")
    # defusedxml parseert veilig; indent/tostring zijn pure serialisatie (geen XXE-risico)
    inner_root = ET.fromstring(return_el.text)
    stdlib_ET.indent(inner_root, space="  ")
    return stdlib_ET.tostring(inner_root, encoding="unicode", xml_declaration=True) + "\n"


def haal_order_xml_op(soap_url: str, gebruiker: str, wachtwoord: str, order_id: int) -> str:
    soap_respons = stuur_soap(soap_url, gebruiker, wachtwoord, bouw_request_order_xml(order_id))
    return extraheer_en_format_xml(soap_respons)


# ---------------------------------------------------------------------------
# Order verwijderen
# ---------------------------------------------------------------------------


def bouw_verwijder_xml(order_xml: str) -> str:
    """Zet een opgehaalde order-XML om naar een Store-request die de order verwijdert.

    Zelfde round-trip als scripts/update_order_colli.py: de opgehaalde
    EoCustomLinkResponseOrdersNormal wordt hernoemd naar
    EoCustomLinkStoreOrdersNormal en het order-niveau <Deleted> wordt op True
    gezet. dbo.Orders.Deleted is een tinyint die MendriX zelf ook gebruikt om
    verwijderde orders te markeren.

    Alleen het <Deleted>-element direct onder EoOrderMx wordt aangepast; de
    Deleted-vlaggen van onderliggende taken/goods blijven ongemoeid.
    """
    root = ET.fromstring(order_xml)

    order_el = root.find(".//EoOrderMx")
    if order_el is None:
        raise ValueError("Geen <EoOrderMx> gevonden in order-XML — order bestaat niet?")

    deleted_el = order_el.find("Deleted")
    if deleted_el is None:
        deleted_el = stdlib_ET.SubElement(order_el, "Deleted")
    deleted_el.text = "True"

    root.tag = "EoCustomLinkStoreOrdersNormal"
    root.set("Type", "TEoCustomLinkStoreOrdersNormal")
    root.set("xsi:noNamespaceSchemaLocation", "GdxEoStructures.xsd")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

    stdlib_ET.indent(root, space="  ")
    return stdlib_ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def verwijder_order(soap_url: str, gebruiker: str, wachtwoord: str, order_id: int) -> str:
    """Verwijdert een order in MendriX via de fetch → Deleted=True → store round-trip.

    Retourneert de ruwe SOAP-respons zodat de aanroeper deze kan loggen.
    """
    _log.info("Order %d ophalen om te verwijderen...", order_id)
    order_xml = haal_order_xml_op(soap_url, gebruiker, wachtwoord, order_id)
    verwijder_xml = bouw_verwijder_xml(order_xml)
    _log.debug("Verwijder-XML voor order %d:\n%s", order_id, verwijder_xml)
    respons = stuur_soap(soap_url, gebruiker, wachtwoord, verwijder_xml)
    _log.info("Order %d verwijderd in MendriX.", order_id)
    return respons


# ---------------------------------------------------------------------------
# REST dossier-upload
# ---------------------------------------------------------------------------


def rest_login(api_base: str, api_token: str) -> str:
    """Logt in en geeft een kortstondige JWT terug."""
    url = api_base.rstrip("/") + "/account/login-api-token"
    with sessie() as s:
        resp = s.post(url, json={"token": api_token}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["data"]["items"][0]["access"]
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Onverwachte login-respons: {data}") from exc


def upload_bestand_naar_dossier(
    api_base: str, jwt: str, order_id: int, bestand_pad: str, bestandsnaam: str
) -> None:
    """POST een bestand als octet-stream naar het dossier van de order."""
    url = api_base.rstrip("/") + f"/dossier/dossiers/orders/{order_id}/contents/{bestandsnaam}"
    with open(bestand_pad, "rb") as f:
        inhoud = f.read()
    with sessie() as s:
        resp = s.post(
            url,
            data=inhoud,
            headers={
                "Content-Type": "application/octet-stream",
                "Authorization": f"Bearer {jwt}",
            },
            timeout=60,
        )
    resp.raise_for_status()
