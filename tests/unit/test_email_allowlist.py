"""Tests voor de domein-allowlist van het dashboard.

Het rapport bevat klantgegevens; de allowlist bepaalt naar welke domeinen het
verstuurd mag worden als iemand in de modal een adres aanpast of toevoegt.
"""

import os
from unittest.mock import patch

import pytest

from lokalist_weekrapportage.email_allowlist import (
    domein_van,
    geweigerde_adressen,
    is_toegestaan,
    lees_toegestane_domeinen,
)

DOMEINEN = ["lokalist.nl", "ophaaldienstmiedema.nl"]


class TestLeesToegestaneDomeinen:
    def test_leeg_betekent_geen_begrenzing(self):
        assert lees_toegestane_domeinen("") == []

    def test_splitst_op_komma_en_ruimt_witruimte_op(self):
        assert lees_toegestane_domeinen(" lokalist.nl , ophaaldienstmiedema.nl ") == DOMEINEN

    def test_slaat_lege_delen_over(self):
        assert lees_toegestane_domeinen("a.nl,,  ,b.nl") == ["a.nl", "b.nl"]

    def test_leidende_apenstaart_mag(self):
        assert lees_toegestane_domeinen("@lokalist.nl") == ["lokalist.nl"]

    def test_normaliseert_naar_kleine_letters(self):
        assert lees_toegestane_domeinen("Lokalist.NL") == ["lokalist.nl"]

    def test_leest_uit_de_omgeving_zonder_argument(self):
        with patch.dict(os.environ, {"DASHBOARD_EMAIL_DOMEINEN": "lokalist.nl"}):
            assert lees_toegestane_domeinen() == ["lokalist.nl"]

    def test_ontbrekende_variabele_geeft_lege_lijst(self):
        with patch.dict(os.environ, {}, clear=True):
            assert lees_toegestane_domeinen() == []


class TestDomeinVan:
    @pytest.mark.parametrize(
        ("adres", "verwacht"),
        [
            ("info@lokalist.nl", "lokalist.nl"),
            ("  Info@Lokalist.NL  ", "lokalist.nl"),
            ("jan+tag@sub.lokalist.nl", "sub.lokalist.nl"),
        ],
    )
    def test_haalt_het_domein_eruit(self, adres, verwacht):
        assert domein_van(adres) == verwacht

    def test_adres_zonder_apenstaart_levert_het_adres_zelf(self):
        """Komt nooit in de allowlist voor en wordt dus geweigerd."""
        assert domein_van("geen-apenstaart") == "geen-apenstaart"


class TestIsToegestaan:
    def test_zonder_allowlist_mag_alles(self):
        assert is_toegestaan("wie.dan.ook@internet.com", [])

    def test_adres_binnen_de_allowlist(self):
        assert is_toegestaan("nieuw@lokalist.nl", DOMEINEN)

    def test_adres_buiten_de_allowlist(self):
        assert not is_toegestaan("jeroen@prive.nl", DOMEINEN)

    def test_hoofdletters_maken_niet_uit(self):
        assert is_toegestaan("Nieuw@Lokalist.NL", DOMEINEN)

    def test_subdomein_telt_niet_als_het_hoofddomein(self):
        assert not is_toegestaan("info@mail.lokalist.nl", DOMEINEN)

    def test_bestaande_ontvanger_mag_altijd(self):
        """Adressen uit .env zijn al goedgekeurd, ook buiten de allowlist."""
        adres = "jeroenkrajenbrink@gmail.com"
        assert is_toegestaan(adres, DOMEINEN, [adres])

    def test_bestaande_ontvanger_vergelijkt_hoofdletterongevoelig(self):
        assert is_toegestaan("JEROEN@gmail.com", DOMEINEN, ["  jeroen@gmail.com "])


class TestGeweigerdeAdressen:
    def test_geeft_alleen_de_afgewezen_adressen(self):
        geweigerd = geweigerde_adressen(
            ["info@lokalist.nl", "jeroen@prive.nl", "planning@ophaaldienstmiedema.nl"],
            DOMEINEN,
        )
        assert geweigerd == ["jeroen@prive.nl"]

    def test_zonder_allowlist_wordt_niets_geweigerd(self):
        assert geweigerde_adressen(["wie@dan.ook"], []) == []

    def test_negeert_lege_adressen(self):
        assert geweigerde_adressen(["", "   "], DOMEINEN) == []

    def test_meldt_een_adres_maar_een_keer(self):
        geweigerd = geweigerde_adressen(
            ["jeroen@prive.nl", " jeroen@prive.nl ", "JEROEN@PRIVE.NL"], DOMEINEN
        )
        assert geweigerd == ["jeroen@prive.nl"]

    def test_behoudt_de_volgorde(self):
        geweigerd = geweigerde_adressen(["b@extern.nl", "a@extern.nl"], DOMEINEN)
        assert geweigerd == ["b@extern.nl", "a@extern.nl"]

    def test_uitzonderingen_worden_doorgegeven(self):
        assert geweigerde_adressen(["extern@gmail.com"], DOMEINEN, ["extern@gmail.com"]) == []
