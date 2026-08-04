"""Tests voor het transportgedeelte van de MendriX-koppeling.

Het echte netwerkverkeer wordt gemockt; wat hier bewezen wordt is dat de juiste
URL's, headers en TLS-instellingen gebruikt worden.
"""

import ssl
from unittest.mock import MagicMock, patch

import pytest
import requests

from lokalist_weekrapportage import mendrix_client


class TestSessie:
    def test_staat_verouderde_tls_toe(self, monkeypatch):
        """De MendriX-server draait op oude TLS; Python weigert dat standaard."""
        monkeypatch.setenv("MENDRIX_CA_CERT", "")
        gemaakte_context = {}

        echte_maker = mendrix_client.create_urllib3_context

        def volg_context(*args, **kwargs):
            ctx = echte_maker(*args, **kwargs)
            gemaakte_context["ctx"] = ctx
            return ctx

        monkeypatch.setattr(mendrix_client, "create_urllib3_context", volg_context)
        sessie = mendrix_client.sessie()

        assert isinstance(sessie, requests.Session)
        assert gemaakte_context["ctx"].minimum_version == ssl.TLSVersion.TLSv1

    def test_ca_false_schakelt_verificatie_uit(self, monkeypatch):
        monkeypatch.setattr(mendrix_client, "_ca_warning_gelogd", False)
        monkeypatch.setenv("MENDRIX_CA_CERT", "false")

        with patch.object(mendrix_client, "create_urllib3_context") as maker:
            ctx = MagicMock()
            maker.return_value = ctx
            mendrix_client.sessie()

        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_waarschuwing_wordt_maar_een_keer_gelogd(self, monkeypatch, caplog):
        """Anders vervuilt elke SOAP-call het logbestand."""
        monkeypatch.setattr(mendrix_client, "_ca_warning_gelogd", False)
        monkeypatch.setenv("MENDRIX_CA_CERT", "false")

        with caplog.at_level("WARNING"):
            mendrix_client.ca_instelling()
            mendrix_client.ca_instelling()
            mendrix_client.ca_instelling()

        waarschuwingen = [r for r in caplog.records if "TLS-verificatie" in r.message]
        assert len(waarschuwingen) == 1


class TestStuurSoap:
    def _mock_sessie(self, tekst="<respons/>", status_fout=None):
        respons = MagicMock()
        respons.text = tekst
        if status_fout:
            respons.raise_for_status.side_effect = status_fout
        sessie = MagicMock()
        sessie.__enter__.return_value.post.return_value = respons
        return sessie, respons

    def test_verstuurt_naar_de_juiste_url_met_soap_headers(self):
        sessie, _ = self._mock_sessie()

        with patch.object(mendrix_client, "sessie", return_value=sessie):
            resultaat = mendrix_client.stuur_soap("https://soap", "u", "w", "<Req/>")

        assert resultaat == "<respons/>"
        aanroep = sessie.__enter__.return_value.post.call_args
        assert aanroep[0][0] == "https://soap"
        assert aanroep.kwargs["headers"]["Content-Type"] == "text/xml; charset=utf-8"
        assert aanroep.kwargs["timeout"] == 30

    def test_envelope_bevat_de_inloggegevens(self):
        sessie, _ = self._mock_sessie()

        with patch.object(mendrix_client, "sessie", return_value=sessie):
            mendrix_client.stuur_soap("https://soap", "gebruiker", "geheim", "<Req/>")

        verzonden = sessie.__enter__.return_value.post.call_args.kwargs["data"].decode()
        assert '<UserName xsi:type="xsd:string">gebruiker</UserName>' in verzonden
        assert '<Password xsi:type="xsd:string">geheim</Password>' in verzonden

    def test_http_fout_wordt_doorgegeven(self):
        sessie, _ = self._mock_sessie(status_fout=requests.HTTPError("500"))

        with patch.object(mendrix_client, "sessie", return_value=sessie):
            with pytest.raises(requests.HTTPError):
                mendrix_client.stuur_soap("https://soap", "u", "w", "<Req/>")


class TestExtraheerEnFormatXml:
    RESPONS = (
        '<?xml version="1.0"?><Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">'
        "<Body><return>&lt;Order&gt;&lt;Id&gt;1&lt;/Id&gt;&lt;/Order&gt;</return></Body>"
        "</Envelope>"
    )

    def test_geeft_ingesprongen_xml(self):
        xml = mendrix_client.extraheer_en_format_xml(self.RESPONS)

        assert xml.startswith("<?xml")
        assert "<Order>" in xml
        assert "  <Id>1</Id>" in xml
        assert xml.endswith("\n")

    def test_zonder_return_element(self):
        with pytest.raises(ValueError, match="Geen <return>-element"):
            mendrix_client.extraheer_en_format_xml(
                '<?xml version="1.0"?><Envelope><Body/></Envelope>'
            )


class TestHaalOrderXmlOp:
    def test_vraagt_de_juiste_order_op(self):
        with (
            patch.object(mendrix_client, "stuur_soap", return_value="<x/>") as versturen,
            patch.object(mendrix_client, "extraheer_en_format_xml", return_value="<net/>"),
        ):
            resultaat = mendrix_client.haal_order_xml_op("https://soap", "u", "w", 1266289)

        assert resultaat == "<net/>"
        assert "<KeysExplicitAsCsv>1266289</KeysExplicitAsCsv>" in versturen.call_args[0][3]


class TestUploadBestand:
    def test_post_naar_het_dossierpad_met_bearer_token(self, tmp_path):
        bestand = tmp_path / "rapport.pdf"
        bestand.write_bytes(b"%PDF-1.4 inhoud")
        respons = MagicMock()
        sessie = MagicMock()
        sessie.__enter__.return_value.post.return_value = respons

        with patch.object(mendrix_client, "sessie", return_value=sessie):
            mendrix_client.upload_bestand_naar_dossier(
                "https://api/", "jwt-token", 1266400, str(bestand), "rapport.pdf"
            )

        aanroep = sessie.__enter__.return_value.post.call_args
        assert aanroep[0][0] == ("https://api/dossier/dossiers/orders/1266400/contents/rapport.pdf")
        assert aanroep.kwargs["headers"]["Authorization"] == "Bearer jwt-token"
        assert aanroep.kwargs["headers"]["Content-Type"] == "application/octet-stream"
        assert aanroep.kwargs["data"] == b"%PDF-1.4 inhoud"

    def test_dubbele_slash_in_api_url_wordt_opgelost(self, tmp_path):
        bestand = tmp_path / "a.txt"
        bestand.write_bytes(b"x")
        sessie = MagicMock()
        sessie.__enter__.return_value.post.return_value = MagicMock()

        with patch.object(mendrix_client, "sessie", return_value=sessie):
            mendrix_client.upload_bestand_naar_dossier(
                "https://api///", "jwt", 1, str(bestand), "a.txt"
            )

        url = sessie.__enter__.return_value.post.call_args[0][0]
        assert "//dossier" not in url.replace("https://", "")
