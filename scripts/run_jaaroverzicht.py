"""Genereert het jaaroverzicht PDF voor De Lokalist, week 1 t/m 24 van 2026,
maakt een samenvattende order aan in MendriX via SOAP en plaatst de PDF
in het dossier van die order via REST.

Gebruik:
    python scripts/run_jaaroverzicht.py           # dry-run: PDF genereren, geen SOAP/REST
    python scripts/run_jaaroverzicht.py --send    # ook order aanmaken + PDF uploaden

Uitvoer: output/lokalist_jaaroverzicht_2026_w01-w24.pdf
"""

import os
import re
import ssl
import sys
import xml.sax.saxutils as saxutils
from datetime import datetime
from pathlib import Path

import defusedxml.ElementTree as ET
import pyodbc
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from genereer_jaaroverzicht_pdf import genereer_jaaroverzicht  # noqa: E402
from lokalist_weekrapportage.config import laad_config  # noqa: E402

DATE_START    = "2026-01-01"
DATE_END      = "2026-06-14"   # einde week 24, 2026
PERIODE_LABEL = "week 1 t/m 24, 2026"
LOKALIST_CLIENT_NO  = 4787
LOKALIST_PRODUCT_ID = 19
DISFOOD_ARTNR       = 16
LOKALIST_ADRES = {
    "Name": "De Lokalist", "Street": "Dochterenseweg", "Number": "13A",
    "PostalCode": "7245 NN", "Place": "Laren", "Country": "Nederland", "CountryCode": "NL",
}

SQL_BESTAND = Path(__file__).resolve().parent.parent / "src" / "lokalist_weekrapportage" / "lokalist_periode_overzicht.sql"
OUTPUT_DIR  = Path(__file__).resolve().parent.parent / "output"
OUTPUT_PAD  = OUTPUT_DIR / "lokalist_jaaroverzicht_2026_w01-w24.pdf"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _ca():
    waarde = os.getenv("MENDRIX_CA_CERT", "").strip()
    if waarde.lower() == "false":
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


def _stuur_soap(request_xml: str) -> str:
    soap_url  = os.getenv("MENDRIX_SOAP_URL", "")
    soap_user = os.getenv("MENDRIX_SOAP_USER", "")
    soap_pass = os.getenv("MENDRIX_SOAP_PASS", "")
    envelope = f"""\
<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
                   xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/">
  <SOAP-ENV:Header SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"
                   xmlns:NS1="urn:UCoSoapDispatcherBase">
    <NS1:TAuthenticationHeader xsi:type="NS1:TAuthenticationHeader">
      <UserName xsi:type="xsd:string">{saxutils.escape(soap_user)}</UserName>
      <Password xsi:type="xsd:string">{saxutils.escape(soap_pass)}</Password>
    </NS1:TAuthenticationHeader>
  </SOAP-ENV:Header>
  <SOAP-ENV:Body SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
    <NS2:ExecuteRequest xmlns:NS2="urn:UCoSoapDispatcherCustomLink-ICustomLinkSoap">
      <ARequest xsi:type="xsd:string">{saxutils.escape(request_xml)}</ARequest>
    </NS2:ExecuteRequest>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
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
    root = ET.fromstring(soap_respons)
    return_el = root.find(".//{*}return")
    if return_el is None or not return_el.text:
        raise ValueError("Geen <return>-element in SOAP-respons")
    result_root = ET.fromstring(return_el.text)
    for item in result_root.findall(".//_TEoListBase_Items/EoStoreResult"):
        if item.findtext("StoreResult") == "srInserted":
            return int(item.findtext("Id"))
    raise ValueError(f"Geen srInserted in respons:\n{return_el.text}")


def _bouw_instructies(rows: list[tuple]) -> str:
    alle_orders: set[int] = set()
    for r in rows:
        for nr in r[8].split(","):
            nr = nr.strip()
            if nr:
                alle_orders.add(int(nr))
    gesorteerd = sorted(alle_orders)
    header = f"Lokalist {PERIODE_LABEL} overzicht. Ordernummers:"
    nummers = ", ".join(str(nr) for nr in gesorteerd)
    tekst = f"{header} {nummers}"
    if len(tekst) > 250:
        tekst = f"{header} zie PDF in dossier ({len(gesorteerd)} orders)"
    return tekst


def _bouw_ordernummers_txt(rows: list[tuple]) -> str:
    alle_orders: set[int] = set()
    for r in rows:
        for nr in r[8].split(","):
            nr = nr.strip()
            if nr:
                alle_orders.add(int(nr))
    regels = [f"Lokalist {PERIODE_LABEL} overzicht. Ordernummers:"]
    regels.extend(str(nr) for nr in sorted(alle_orders))
    return "\n".join(regels)


def _bouw_store_xml(colli: int, bedrag: float, moment_str: str, instructies: str) -> str:
    adr = LOKALIST_ADRES
    kenmerk = saxutils.escape(PERIODE_LABEL)
    aanmaakdag = DATE_END
    return f"""\
<?xml version="1.0" encoding="windows-1252"?>
<EoCustomLinkStoreOrdersNormal Type="TEoCustomLinkStoreOrdersNormal">
  <Data Type="TEoOrderMxList">
    <_TEoListBase_Items>
      <EoOrderMx Type="TEoOrderMx">
        <OrderId Type="TEoKeyIntInfraMx"><Id>-1</Id></OrderId>
        <ClientId Type="TEoKeyIntInfraMx"><Id>{LOKALIST_CLIENT_NO}</Id></ClientId>
        <IsActive>False</IsActive>
        <MarkChars></MarkChars>
        <Moment>{moment_str}</Moment>
        <OrderType>400</OrderType>
        <ProductId Type="TEoKeyIntInfraMx"><Id>{LOKALIST_PRODUCT_ID}</Id></ProductId>
        <ProductIdAutomaticArticles>False</ProductIdAutomaticArticles>
        <Deleted>False</Deleted>
        <ArticlesSell Type="TEoArticleList">
          <_TEoListBase_Items>
            <EoArticleSell Type="TEoArticleSell">
              <ArticleId Type="TEoKeyIntInfraMx"><Id>-1</Id></ArticleId>
              <ArticleIdForeign Type="TEoKeyIntInfraMx"><Id>{DISFOOD_ARTNR}</Id></ArticleIdForeign>
              <Deleted>False</Deleted>
              <Number>{colli}.0</Number>
              <NumberRaw>{colli}.0</NumberRaw>
              <NumberManual>True</NumberManual>
              <Minimum>{bedrag:.2f}</Minimum>
              <PriceManual>True</PriceManual>
              <SortOrder>0</SortOrder>
              <ShowOnInvoice>True</ShowOnInvoice>
            </EoArticleSell>
          </_TEoListBase_Items>
        </ArticlesSell>
        <Goods Type="TEoGoodMxList">
          <_TEoListBase_Items>
            <EoGoodMx Type="TEoGoodMx">
              <GoodId Type="TEoKeyIntInfraMx"><Id>-1</Id></GoodId>
              <Packing Type="TEoPackingMx"><Name>Colli</Name></Packing>
              <Comments>Totaal geladen colli</Comments>
              <Parts>{colli}.0</Parts>
              <Weight>1.0</Weight>
              <Volume>0.0</Volume><VolumeWeight>0.0</VolumeWeight>
              <ArticleWeight>0.0</ArticleWeight>
              <Depth>0.0</Depth><Height>0.0</Height><Width>0.0</Width>
            </EoGoodMx>
          </_TEoListBase_Items>
        </Goods>
        <Tasks Type="TEoTaskMxList">
          <WaitGetMinutes>0</WaitGetMinutes>
          <WaitBringMinutes>0</WaitBringMinutes>
          <WaitAllMinutes>0</WaitAllMinutes>
          <_TEoListBase_Items>
            <EoTaskMx Type="TEoTaskMx">
              <TaskId Type="TEoKeyIntInfraMx"><Id>-1</Id></TaskId>
              <Address Type="TEoAddress">
                <Name>{adr["Name"]}</Name>
                <Street>{adr["Street"]}</Street>
                <Number>{adr["Number"]}</Number>
                <PostalCode>{adr["PostalCode"]}</PostalCode>
                <Place>{adr["Place"]}</Place>
                <Country>{adr["Country"]}</Country>
                <CountryCode>{adr["CountryCode"]}</CountryCode>
              </Address>
              <Completion Type="TEoCompletion">
                <Actual Type="TEoDateTimeWindow">
                  <DateTimeBegin>{moment_str}</DateTimeBegin>
                  <DateTimeEnd>{moment_str}</DateTimeEnd>
                </Actual>
              </Completion>
              <Instructions>{saxutils.escape(instructies)}</Instructions>
              <ReferenceYour>{kenmerk}</ReferenceYour>
              <Requested Type="TEoDateTimeWindow">
                <DateTimeBegin>{aanmaakdag}T08:00:00</DateTimeBegin>
                <DateTimeEnd>{aanmaakdag}T23:59:59</DateTimeEnd>
              </Requested>
              <TaskTypeId Type="TEoKeyIntInfraMx"><Id>1</Id></TaskTypeId>
              <TaskStateId Type="TEoKeyIntInfraMx"><Id>1800</Id></TaskStateId>
              <TaskProblemId Type="TEoKeyIntInfraMx"><Id>0</Id></TaskProblemId>
            </EoTaskMx>
          </_TEoListBase_Items>
        </Tasks>
        <GoodsToTasks Type="TEoGoodToTaskMxList">
          <_TEoListBase_Items>
            <EoGoodToTaskMx Type="TEoGoodToTaskMx">
              <GoodId Type="TEoKeyIntInfraMx"><Id>-1</Id></GoodId>
              <TaskId Type="TEoKeyIntInfraMx"><Id>-1</Id></TaskId>
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


def maak_samenvattende_order(totaal_bedrag: float, totaal_colli: int, rows: list[tuple]) -> int:
    moment = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    instructies = _bouw_instructies(rows)
    store_xml = _bouw_store_xml(totaal_colli, totaal_bedrag, moment, instructies)
    soap_respons = _stuur_soap(store_xml)
    return _extraheer_order_id(soap_respons)


def _rest_login() -> str:
    api_base  = os.getenv("MENDRIX_API_URL", "").rstrip("/")
    api_token = os.getenv("MENDRIX_API_TOKEN", "")
    with _sessie() as s:
        login = s.post(f"{api_base}/account/login-api-token", json={"token": api_token}, timeout=15)
    login.raise_for_status()
    return login.json()["data"]["items"][0]["access"]


def _upload_bestand(order_id: int, bestandsnaam: str, inhoud: bytes, jwt: str) -> None:
    api_base = os.getenv("MENDRIX_API_URL", "").rstrip("/")
    url = f"{api_base}/dossier/dossiers/orders/{order_id}/contents/{bestandsnaam}"
    with _sessie() as s:
        resp = s.post(
            url,
            data=inhoud,
            headers={"Content-Type": "application/octet-stream", "Authorization": f"Bearer {jwt}"},
            timeout=60,
        )
    resp.raise_for_status()


def upload_pdf_naar_dossier(order_id: int, pdf_path: Path, rows: list[tuple]) -> None:
    jwt = _rest_login()
    _upload_bestand(order_id, pdf_path.name, pdf_path.read_bytes(), jwt)
    txt_inhoud = _bouw_ordernummers_txt(rows).encode("utf-8")
    _upload_bestand(order_id, "ordernummers.txt", txt_inhoud, jwt)


def _bouw_connectiestring(config) -> str:
    if config.db_auth_method == "windows":
        return (
            f"DRIVER={{{config.db_driver}}};"
            f"SERVER={config.db_server};DATABASE={config.db_database};"
            f"Trusted_Connection=yes;TrustServerCertificate=yes;"
        )
    return (
        f"DRIVER={{{config.db_driver}}};"
        f"SERVER={config.db_server};DATABASE={config.db_database};"
        f"UID={config.db_user};PWD={config.db_password};"
        f"TrustServerCertificate=yes;"
    )


def haal_periodedata_op(config) -> list[tuple]:
    sql = SQL_BESTAND.read_text(encoding="utf-8")
    sql = re.sub(r"DECLARE @DateStart DATE = '[^']*';", f"DECLARE @DateStart DATE = '{DATE_START}';", sql)
    sql = re.sub(r"DECLARE @DateEnd\s+DATE = '[^']*';", f"DECLARE @DateEnd   DATE = '{DATE_END}';", sql)

    conn = pyodbc.connect(_bouw_connectiestring(config))
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        ruwe_rijen = cursor.fetchall()
    finally:
        conn.close()

    rows = []
    for r in ruwe_rijen:
        datum_str = r.Datum.strftime("%Y-%m-%d") if hasattr(r.Datum, "strftime") else str(r.Datum)
        rows.append((
            datum_str,
            r.TaskTypeNaam,
            r.LocName or "",
            r.LocStreet or "",
            r.LocZip or "",
            r.LocCity or "",
            int(r.TotaalColli or 0),
            int(r.AantalTaken or 0),
            r.OrderNummers or "",
            r.Staffeltrede or "",
            float(r.StaffelTarief or 0.0),
        ))
    return rows


def main():
    send_mode = "--send" in sys.argv
    config = laad_config()

    print(f"Data ophalen: {DATE_START} t/m {DATE_END} ...")
    rows = haal_periodedata_op(config)
    print(f"{len(rows)} rijen opgehaald.")
    if not rows:
        sys.exit("Geen orders gevonden voor de opgegeven periode.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"PDF genereren: {OUTPUT_PAD} ...")
    pdf_path, totals = genereer_jaaroverzicht(
        rows=rows,
        periode_omschrijving=PERIODE_LABEL,
        output_path=str(OUTPUT_PAD),
    )
    print(f"PDF klaar: {pdf_path}")
    print(f"  Laden:  {totals['laden']:>10.2f}")
    print(f"  Lossen: {totals['lossen']:>10.2f}")
    print(f"  Totaal: {totals['totaal']:>10.2f}")

    if not send_mode:
        print("\nDry-run — voeg --send toe om order aan te maken en PDF te uploaden.")
        return

    totaal_colli = sum(r[6] for r in rows if r[1] == "Laden")
    print(f"\nOrder aanmaken (totaal {totaal_colli} colli, € {totals['totaal']:.2f}) ...")
    order_id = maak_samenvattende_order(totals["totaal"], totaal_colli, rows)
    print(f"Order aangemaakt: OrderId = {order_id}")

    print(f"PDF uploaden naar dossier van order {order_id} ...")
    upload_pdf_naar_dossier(order_id, OUTPUT_PAD, rows)
    print("PDF geplaatst in dossier.")


if __name__ == "__main__":
    main()
