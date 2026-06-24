"""Haalt de XML van een bestaande MendriX-order op via SOAP en slaat die op in scripts/output/."""

import os
import re
import ssl
import sys
import xml.etree.ElementTree as stdlib_ET
from pathlib import Path

import defusedxml.ElementTree as ET
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

load_dotenv()

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


soap_url = os.getenv("MENDRIX_SOAP_URL")
soap_user = os.getenv("MENDRIX_SOAP_USER")
soap_pass = os.getenv("MENDRIX_SOAP_PASS")

if not all([soap_url, soap_user, soap_pass]):
    sys.exit("MENDRIX_SOAP_URL, MENDRIX_SOAP_USER of MENDRIX_SOAP_PASS ontbreekt in .env")


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


order_id = input("Order ID: ").strip()
if not order_id.isdigit():
    sys.exit("Ongeldig Order ID")

custom_link_xml = (
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
            <ARequest xsi:type="xsd:string">{xml_escape(custom_link_xml)}</ARequest>
        </urn:ExecuteRequest>
    </soap-env:Body>
</soap-env:Envelope>"""

print(f"\nSOAP URL:  {soap_url}")
print(f"Order ID:  {order_id}")
print("Versturen...\n")

try:
    with _sessie() as session:
        response = session.post(
            soap_url,
            data=envelope.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": '"urn:UCoSoapDispatcherCustomLink-ICustomLinkSoap#ExecuteRequest"',
            },
            timeout=30,
        )
    response.raise_for_status()
    raw = response.text
except requests.RequestException as e:
    sys.exit(f"SOAP-fout: {e}")

cl_response = raw
for tag in ("return", "ExecuteRequestResult", "AResult"):
    m = re.search(rf"<[^>]*{tag}[^>]*>(.*?)</[^>]*{tag}>", raw, re.DOTALL)
    if m:
        cl_response = xml_unescape(m.group(1))
        break

try:
    root = ET.fromstring(cl_response)
    stdlib_ET.indent(root, space="  ")
    cl_response = stdlib_ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"
except ET.ParseError:
    pass  # geen geldige XML, schrijf ruwe response

output_dir = Path("scripts") / "output"
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / f"{order_id}.xml"
output_path.write_text(cl_response, encoding="utf-8")
print(f"Opgeslagen in: {output_path}")
