"""Consolideert goods-regels van een bestaande order: telt Parts op en zet Packing op 'Colli'.

Gebruik:
    python scripts/update_order_colli.py           # dry-run: toont Store-XML, stuurt niet
    python scripts/update_order_colli.py --send    # stuurt daadwerkelijk naar MendriX

Haalt de order live op via SOAP — geen lokale XML vereist.
"""

import os
import re
import ssl
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import defusedxml.ElementTree as defused_ET
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

load_dotenv()

soap_url = os.getenv("MENDRIX_SOAP_URL")
soap_user = os.getenv("MENDRIX_SOAP_USER")
soap_pass = os.getenv("MENDRIX_SOAP_PASS")

if not all([soap_url, soap_user, soap_pass]):
    sys.exit("MENDRIX_SOAP_URL, MENDRIX_SOAP_USER of MENDRIX_SOAP_PASS ontbreekt in .env")

send_mode = "--send" in sys.argv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _ca() -> str | bool:
    waarde = os.getenv("MENDRIX_CA_CERT", "").strip()
    if waarde.lower() == "false":
        print("LET OP: MENDRIX_CA_CERT=false — TLS-verificatie uitgeschakeld.")
        return False
    if waarde:
        return waarde if os.path.isabs(waarde) else str(_PROJECT_ROOT / waarde)
    return True


def _sessie() -> requests.Session:
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

    s = requests.Session()
    s.mount("https://", _LegacyTLSAdapter())
    return s


def xml_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def xml_unescape(value: str) -> str:
    return (
        value.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )


def soap_request(body_xml: str) -> str:
    """Stuurt een SOAP-verzoek en geeft de CustomLink-payload terug."""
    envelope = f"""<?xml version="1.0"?>
<soap-env:Envelope
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:urn="urn:UCoSoapDispatcherCustomLink-ICustomLinkSoap">
    <soap-env:Header xmlns:NS-1="urn:UCoSoapDispatcherBase">
        <NS-1:TAuthenticationHeader xsi:type="urn:TAuthenticationHeader"
            xmlns:urn="urn:UCoSoapDispatcherBase">
            <UserName xsi:type="xsd:string">{xml_escape(soap_user)}</UserName>
            <Password xsi:type="xsd:string">{xml_escape(soap_pass)}</Password>
        </NS-1:TAuthenticationHeader>
    </soap-env:Header>
    <soap-env:Body>
        <urn:ExecuteRequest soap-env:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
            <ARequest xsi:type="xsd:string">{xml_escape(body_xml)}</ARequest>
        </urn:ExecuteRequest>
    </soap-env:Body>
</soap-env:Envelope>"""

    try:
        with _sessie() as session:
            resp = session.post(
                soap_url,
                data=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": (
                        '"urn:UCoSoapDispatcherCustomLink-ICustomLinkSoap#ExecuteRequest"'
                    ),
                },
                timeout=30,
            )
        resp.raise_for_status()
    except requests.RequestException as e:
        sys.exit(f"SOAP-fout: {e}")

    raw = resp.text
    for tag in ("return", "ExecuteRequestResult", "AResult"):
        m = re.search(rf"<[^>]*{tag}[^>]*>(.*?)</[^>]*{tag}>", raw, re.DOTALL)
        if m:
            return xml_unescape(m.group(1))
    return raw


# --- Order IDs inlezen ---
raw_input = input("Order ID('s): ").strip()
# Splits op komma's, puntkomma's, spaties en enters
order_ids = [tok for tok in re.split(r"[\s,;]+", raw_input) if tok]
ongeldig = [o for o in order_ids if not o.isdigit()]
if ongeldig:
    sys.exit(f"Ongeldige Order ID('s): {', '.join(ongeldig)}")
if not order_ids:
    sys.exit("Geen Order ID opgegeven.")

fouten = []

for order_id in order_ids:
    print(f"\n{'=' * 50}")
    print(f"Order {order_id} ophalen...")

    fetch_xml = (
        '<?xml version="1.0" encoding="windows-1252"?>'
        '<EoCustomLinkRequestOrdersNormal Type="TEoCustomLinkRequestOrdersNormal" '
        'xsi:noNamespaceSchemaLocation="GdxEoStructures.xsd" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<Nested>False</Nested>"
        '<Filter Type="TEoFilterOrdersNormal">'
        f"<KeysExplicitAsCsv>{order_id}</KeysExplicitAsCsv>"
        "</Filter>"
        "</EoCustomLinkRequestOrdersNormal>"
    )

    try:
        response_xml = soap_request(fetch_xml)
        root = defused_ET.fromstring(response_xml)
    except Exception as e:
        print(f"  FOUT bij ophalen: {e}")
        fouten.append(order_id)
        continue

    order_el = root.find(".//EoOrderMx")
    if order_el is None:
        print(f"  FOUT: order {order_id} niet gevonden in respons.")
        fouten.append(order_id)
        continue

    # --- Goods consolideren ---
    goods_el = order_el.find("Goods")
    if goods_el is None:
        print("  FOUT: geen <Goods>-element gevonden.")
        fouten.append(order_id)
        continue

    items_el = goods_el.find("_TEoListBase_Items")
    goods_regels = items_el.findall("EoGoodMx") if items_el is not None else []

    if not goods_regels:
        print("  FOUT: geen EoGoodMx-regels gevonden.")
        fouten.append(order_id)
        continue

    totaal_parts = sum(float(g.findtext("Parts", "0")) for g in goods_regels)
    eerste_good = goods_regels[0]
    eerste_good_id = eerste_good.findtext("GoodId/Id")

    print(f"  Goods-regels: {len(goods_regels)}")
    for g in goods_regels:
        print(
            f"    GoodId={g.findtext('GoodId/Id')}  "
            f"Parts={g.findtext('Parts')}  "
            f"Packing={g.findtext('Packing/Name')}"
        )
    print(f"  Totaal: {int(totaal_parts)} Colli")

    # Parts en Packing op eerste Good aanpassen
    parts_el = eerste_good.find("Parts")
    if parts_el is None:
        parts_el = ET.SubElement(eerste_good, "Parts")
    parts_el.text = str(totaal_parts)

    packing_el = eerste_good.find("Packing")
    if packing_el is None:
        packing_el = ET.SubElement(eerste_good, "Packing")
        packing_el.set("Type", "TEoPackingMx")
    name_el = packing_el.find("Name")
    if name_el is None:
        name_el = ET.SubElement(packing_el, "Name")
    name_el.text = "Colli"

    for g in goods_regels[1:]:
        items_el.remove(g)

    for tag, waarde in [("GoodCount", "1"), ("Parts", str(totaal_parts))]:
        el = goods_el.find(tag)
        if el is not None:
            el.text = waarde

    gtt_el = order_el.find("GoodsToTasks/_TEoListBase_Items")
    if gtt_el is not None:
        for gtt in list(gtt_el.findall("EoGoodToTaskMx")):
            if gtt.findtext("GoodId/Id") != eerste_good_id:
                gtt_el.remove(gtt)

    # --- Store-XML bouwen ---
    root.tag = "EoCustomLinkStoreOrdersNormal"
    root.set("Type", "TEoCustomLinkStoreOrdersNormal")
    root.set("xsi:noNamespaceSchemaLocation", "GdxEoStructures.xsd")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

    ET.indent(root, space="  ")
    store_xml = ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"

    if not send_mode:
        print("  Dry-run — wordt niet verstuurd.")
        continue

    try:
        result = soap_request(store_xml)
        print(f"  Verstuurd. Respons: {result[:200]}")
    except Exception as e:
        print(f"  FOUT bij versturen: {e}")
        fouten.append(order_id)

print(f"\n{'=' * 50}")
if not send_mode:
    print(f"Dry-run klaar ({len(order_ids)} order(s)). Voeg --send toe om te versturen.")
elif fouten:
    print(f"Klaar met fouten bij: {', '.join(fouten)}")
else:
    print(f"Klaar — {len(order_ids)} order(s) bijgewerkt.")
