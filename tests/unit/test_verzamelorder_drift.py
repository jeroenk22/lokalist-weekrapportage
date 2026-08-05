"""Bewaakt dat het dashboard exact dezelfde output produceert als de zondagrun.

Het webdashboard gebruikt src/lokalist_weekrapportage/verzamelorder.py en
mendrix_client.py. De geplande zondagrun gebruikt scripts/run_weekrapportage.py.
Dat zijn bewust twee losse kopieën: de bestaande productiecode mocht niet
gewijzigd worden.

Deze tests vergelijken beide implementaties rechtstreeks. Wijzigt iemand er één,
dan valt deze test om en is de divergentie meteen zichtbaar in plaats van pas in
een afwijkend rapport.
"""

import importlib.util
import os

import pytest

from lokalist_weekrapportage import verzamelorder

_SCRIPT_PAD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "run_weekrapportage.py",
)


@pytest.fixture(scope="module")
def productie_script():
    """Laadt scripts/run_weekrapportage.py als module zonder het te draaien."""
    spec = importlib.util.spec_from_file_location("_run_weekrapportage", _SCRIPT_PAD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_store_xml_zonder_notities_is_identiek(productie_script):
    """Zonder notitie moet de dashboard-XML byte-identiek zijn aan de productie-XML."""
    argumenten = (32, 238.13, "Lokalist week 31 2026 overzicht.", "2026-08-02T23:30:04", 31, 2026)

    verwacht = productie_script._bouw_store_xml(*argumenten)
    resultaat = verzamelorder.bouw_store_xml(*argumenten)

    assert resultaat == verwacht


def test_store_xml_met_notities_voegt_alleen_notes_toe(productie_script):
    """Met notitie verschilt de XML uitsluitend door het extra <Notes>-element."""
    argumenten = (32, 238.13, "Lokalist week 31 2026 overzicht.", "2026-08-02T23:30:04", 31, 2026)

    productie = productie_script._bouw_store_xml(*argumenten)
    met_notitie = verzamelorder.bouw_store_xml(*argumenten, notities="Handmatig gedraaid")

    assert "<Notes>Handmatig gedraaid</Notes>" in met_notitie
    # Verwijder het toegevoegde element en je houdt exact de productie-XML over.
    opgeschoond = met_notitie.replace("\n        <Notes>Handmatig gedraaid</Notes>", "")
    assert opgeschoond == productie


def test_periode_omschrijving_is_identiek(productie_script):
    """De periodetekst in mail en PDF moet exact overeenkomen."""
    for week, jaar in [(1, 2026), (27, 2026), (31, 2026), (44, 2026), (53, 2020)]:
        assert verzamelorder.periode_omschrijving(week, jaar) == (
            productie_script._periode_omschrijving(week, jaar)
        )


def test_totalen_zijn_identiek(productie_script):
    """Colli- en bedragtotalen moeten exact overeenkomen met de productieberekening."""
    rows = [
        ("2026-08-01", "Laden", "A", "S", "Z", "P", 10, 1, "111", "1-20", 25.0),
        ("2026-08-01", "Lossen", "B", "S", "Z", "P", 5, 1, "112", "1-20", 12.5),
        ("2026-08-02", "Laden", "C", "S", "Z", "P", 7, 1, "113", "21-40", 0.0),
    ]
    assert verzamelorder.totaal_laden_colli(rows) == productie_script._totaal_laden_colli(rows)
    assert verzamelorder.totaal_bedrag(rows) == productie_script._totaal_bedrag(rows)


def test_soap_envelope_is_identiek(productie_script):
    """De SOAP-envelope van het dashboard moet identiek zijn aan die van de zondagrun."""
    from lokalist_weekrapportage import mendrix_client

    request_xml = "<Test>waarde &amp; teken</Test>"
    assert mendrix_client.bouw_soap_envelope(request_xml, "gebruiker", "geheim") == (
        productie_script._bouw_soap_envelope(request_xml, "gebruiker", "geheim")
    )


def test_request_order_xml_is_identiek(productie_script):
    """Het ophalen van een order moet dezelfde request-XML gebruiken."""
    from lokalist_weekrapportage import mendrix_client

    assert mendrix_client.bouw_request_order_xml(1266289) == (
        productie_script._bouw_request_order_xml(1266289)
    )


def test_order_id_extractie_is_identiek(productie_script):
    """Order-ID extractie uit de SOAP-respons moet hetzelfde resultaat geven."""
    from lokalist_weekrapportage import mendrix_client

    respons = (
        '<?xml version="1.0"?><Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">'
        "<Body><ExecuteRequestResponse><return>"
        "&lt;EoStoreResultList&gt;&lt;_TEoListBase_Items&gt;"
        "&lt;EoStoreResult&gt;&lt;StoreResult&gt;srInserted&lt;/StoreResult&gt;"
        "&lt;Id&gt;1266289&lt;/Id&gt;&lt;/EoStoreResult&gt;"
        "&lt;/_TEoListBase_Items&gt;&lt;/EoStoreResultList&gt;"
        "</return></ExecuteRequestResponse></Body></Envelope>"
    )
    assert mendrix_client.extraheer_order_id(respons) == 1266289
    assert mendrix_client.extraheer_order_id(respons) == (
        productie_script._extraheer_order_id(respons)
    )
