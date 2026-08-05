"""Tests voor de gedeelde MendriX-koppeling."""

from unittest.mock import MagicMock, patch

import pytest

from lokalist_weekrapportage import mendrix_client

ORDER_XML = """<?xml version='1.0' encoding='utf-8'?>
<EoCustomLinkResponseOrdersNormal Type="TEoCustomLinkResponseOrdersNormal">
  <Data Type="TEoOrderMxList">
    <_TEoListBase_Items>
      <EoOrderMx Type="TEoOrderMx">
        <OrderId Type="TEoKeyIntInfraMx"><Id>1266289</Id></OrderId>
        <Deleted>False</Deleted>
        <Notes>iets</Notes>
        <Tasks Type="TEoTaskMxList">
          <_TEoListBase_Items>
            <EoTaskMx Type="TEoTaskMx"><Deleted>False</Deleted></EoTaskMx>
          </_TEoListBase_Items>
        </Tasks>
      </EoOrderMx>
    </_TEoListBase_Items>
  </Data>
</EoCustomLinkResponseOrdersNormal>
"""


class TestBouwVerwijderXml:
    def test_zet_order_op_verwijderd(self):
        xml = mendrix_client.bouw_verwijder_xml(ORDER_XML)
        assert "<Deleted>True</Deleted>" in xml

    def test_hernoemt_naar_store_request(self):
        xml = mendrix_client.bouw_verwijder_xml(ORDER_XML)
        assert "<EoCustomLinkStoreOrdersNormal" in xml
        assert "EoCustomLinkResponseOrdersNormal" not in xml
        assert 'Type="TEoCustomLinkStoreOrdersNormal"' in xml

    def test_laat_onderliggende_taken_ongemoeid(self):
        """Alleen de order zelf wordt verwijderd, niet losse taken."""
        xml = mendrix_client.bouw_verwijder_xml(ORDER_XML)
        assert xml.count("<Deleted>True</Deleted>") == 1
        assert "<Deleted>False</Deleted>" in xml

    def test_behoudt_het_order_id(self):
        assert "<Id>1266289</Id>" in mendrix_client.bouw_verwijder_xml(ORDER_XML)

    def test_zonder_order_element_volgt_een_duidelijke_fout(self):
        leeg = (
            '<?xml version="1.0"?>'
            "<EoCustomLinkResponseOrdersNormal></EoCustomLinkResponseOrdersNormal>"
        )
        with pytest.raises(ValueError, match="Geen <EoOrderMx> gevonden"):
            mendrix_client.bouw_verwijder_xml(leeg)


class TestExtraheerOrderId:
    RESPONS = (
        '<?xml version="1.0"?><Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">'
        "<Body><ExecuteRequestResponse><return>"
        "&lt;EoStoreResultList&gt;&lt;_TEoListBase_Items&gt;"
        "&lt;EoStoreResult&gt;&lt;StoreResult&gt;srInserted&lt;/StoreResult&gt;"
        "&lt;Id&gt;1266400&lt;/Id&gt;&lt;/EoStoreResult&gt;"
        "&lt;/_TEoListBase_Items&gt;&lt;/EoStoreResultList&gt;"
        "</return></ExecuteRequestResponse></Body></Envelope>"
    )

    def test_haalt_het_nieuwe_id_eruit(self):
        assert mendrix_client.extraheer_order_id(self.RESPONS) == 1266400

    def test_zonder_return_element(self):
        respons = '<?xml version="1.0"?><Envelope><Body></Body></Envelope>'
        with pytest.raises(ValueError, match="Geen <return>-element"):
            mendrix_client.extraheer_order_id(respons)

    def test_zonder_srinserted(self):
        respons = (
            '<?xml version="1.0"?><Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">'
            "<Body><return>&lt;EoStoreResultList&gt;&lt;_TEoListBase_Items&gt;"
            "&lt;EoStoreResult&gt;&lt;StoreResult&gt;srFailed&lt;/StoreResult&gt;"
            "&lt;/EoStoreResult&gt;&lt;/_TEoListBase_Items&gt;&lt;/EoStoreResultList&gt;"
            "</return></Body></Envelope>"
        )
        with pytest.raises(ValueError, match="Geen srInserted-resultaat"):
            mendrix_client.extraheer_order_id(respons)


class TestCaInstelling:
    def test_false_schakelt_verificatie_uit(self, monkeypatch):
        monkeypatch.setattr(mendrix_client, "_ca_warning_gelogd", False)
        monkeypatch.setenv("MENDRIX_CA_CERT", "false")
        assert mendrix_client.ca_instelling() is False

    def test_leeg_gebruikt_systeemcertificaten(self, monkeypatch):
        monkeypatch.setenv("MENDRIX_CA_CERT", "")
        assert mendrix_client.ca_instelling() is True

    def test_relatief_pad_wordt_absoluut(self, monkeypatch):
        monkeypatch.setenv("MENDRIX_CA_CERT", "cert/chain.pem")
        resultaat = mendrix_client.ca_instelling()
        assert isinstance(resultaat, str)
        assert resultaat.endswith("chain.pem")
        assert mendrix_client._PROJECT_ROOT in resultaat


class TestVerwijderOrder:
    def test_haalt_op_en_stuurt_verwijderverzoek(self):
        with (
            patch.object(mendrix_client, "haal_order_xml_op", return_value=ORDER_XML) as ophalen,
            patch.object(mendrix_client, "stuur_soap", return_value="<ok/>") as versturen,
        ):
            mendrix_client.verwijder_order("https://soap", "u", "w", 1266289)

        ophalen.assert_called_once_with("https://soap", "u", "w", 1266289)
        verzonden_xml = versturen.call_args[0][3]
        assert "<Deleted>True</Deleted>" in verzonden_xml
        assert "EoCustomLinkStoreOrdersNormal" in verzonden_xml


class TestRestLogin:
    def test_haalt_het_token_uit_de_respons(self):
        respons = MagicMock()
        respons.json.return_value = {"data": {"items": [{"access": "jwt-token"}]}}
        sessie = MagicMock()
        sessie.__enter__.return_value.post.return_value = respons

        with patch.object(mendrix_client, "sessie", return_value=sessie):
            assert mendrix_client.rest_login("https://api/", "token") == "jwt-token"

    def test_onverwachte_respons_geeft_duidelijke_fout(self):
        respons = MagicMock()
        respons.json.return_value = {"onzin": True}
        sessie = MagicMock()
        sessie.__enter__.return_value.post.return_value = respons

        with patch.object(mendrix_client, "sessie", return_value=sessie):
            with pytest.raises(ValueError, match="Onverwachte login-respons"):
                mendrix_client.rest_login("https://api/", "token")
