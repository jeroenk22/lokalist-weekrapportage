"""Tests voor de domein-allowlist van het dashboard.

Het rapport bevat klantgegevens; de allowlist bepaalt naar welke domeinen het
verstuurd mag worden als iemand in de modal een adres aanpast of toevoegt.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lokalist_weekrapportage.email_allowlist import (
    domein_van,
    geweigerde_adressen,
    is_adresregel,
    is_toegestaan,
    lees_allowlist,
    omschrijf,
)

DOMEINEN = ["lokalist.nl", "ophaaldienstmiedema.nl"]

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "allowlist_gevallen.json"


def _gedeelde_gevallen():
    """Platgeslagen waarheidstabel uit de gedeelde fixture.

    Levert (scenario, regels, adres, verwacht) per geval, zodat een falend geval
    meteen leesbaar in de testnaam staat.
    """
    scenarios = json.loads(_FIXTURE.read_text(encoding="utf-8"))["scenarios"]
    return [
        pytest.param(
            scenario["regels"],
            geval["adres"],
            geval["toegestaan"],
            id=f"{scenario['naam']} | {geval['adres']}",
        )
        for scenario in scenarios
        for geval in scenario["gevallen"]
    ]


class TestGedeeldeWaarheidstabel:
    """Bewaakt dat Python en de UI hetzelfde oordelen.

    Dezelfde fixture wordt ingelezen door web/tests/useEmailSelectie.test.ts.
    Loopt één van beide implementaties weg, dan valt daar of hier een test om —
    in plaats van dat het verschil pas opvalt als de UI een adres accepteert
    dat de server weigert. Zelfde gedachte als test_verzamelorder_drift.py.
    """

    @pytest.mark.parametrize(("regels", "adres", "verwacht"), _gedeelde_gevallen())
    def test_geval(self, regels, adres, verwacht):
        assert is_toegestaan(adres, regels) is verwacht

    def test_de_fixture_bevat_gevallen(self):
        """Vangt een leeg of stukgelopen fixture-bestand af."""
        assert len(_gedeelde_gevallen()) >= 15


class TestLeesAllowlist:
    def test_leeg_betekent_geen_begrenzing(self):
        assert lees_allowlist("") == []

    def test_splitst_op_komma_en_ruimt_witruimte_op(self):
        assert lees_allowlist(" lokalist.nl , ophaaldienstmiedema.nl ") == DOMEINEN

    def test_slaat_lege_delen_over(self):
        assert lees_allowlist("a.nl,,  ,b.nl") == ["a.nl", "b.nl"]

    def test_leidende_apenstaart_mag(self):
        assert lees_allowlist("@lokalist.nl") == ["lokalist.nl"]

    def test_normaliseert_naar_kleine_letters(self):
        assert lees_allowlist("Lokalist.NL") == ["lokalist.nl"]

    def test_leest_uit_de_omgeving_zonder_argument(self):
        with patch.dict(os.environ, {"DASHBOARD_EMAIL_DOMEINEN": "lokalist.nl"}):
            assert lees_allowlist() == ["lokalist.nl"]

    def test_ontbrekende_variabele_geeft_lege_lijst(self):
        with patch.dict(os.environ, {}, clear=True):
            assert lees_allowlist() == []


class TestAdresregels:
    """Een regel met een naam vóór de @ is één adres, niet een domein."""

    @pytest.mark.parametrize("regel", ["jeroen@gmail.com", "a.b+tag@voorbeeld.co.uk"])
    def test_herkent_een_volledig_adres(self, regel):
        assert is_adresregel(regel)

    @pytest.mark.parametrize("regel", ["lokalist.nl", "sub.lokalist.nl"])
    def test_herkent_een_domein(self, regel):
        assert not is_adresregel(regel)

    def test_leidende_apenstaart_blijft_een_domein(self):
        """@gmail.com is het hele domein; lees_allowlist haalt de @ eraf."""
        assert lees_allowlist("@gmail.com") == ["gmail.com"]
        assert not is_adresregel(lees_allowlist("@gmail.com")[0])

    def test_adres_behoudt_zijn_volledige_vorm(self):
        assert lees_allowlist("Jeroen@Gmail.com") == ["jeroen@gmail.com"]

    def test_domeinen_en_adressen_door_elkaar(self):
        assert lees_allowlist("lokalist.nl, jeroen@gmail.com, @miedema.nl") == [
            "lokalist.nl",
            "jeroen@gmail.com",
            "miedema.nl",
        ]

    def test_toegestaan_adres_mag(self):
        assert is_toegestaan("jeroen@gmail.com", ["lokalist.nl", "jeroen@gmail.com"])

    def test_ander_adres_op_datzelfde_domein_mag_niet(self):
        """Precies het punt van deze vorm: gmail.com blijft verder dicht."""
        assert not is_toegestaan("iemand.anders@gmail.com", ["lokalist.nl", "jeroen@gmail.com"])

    def test_adresregel_vergelijkt_hoofdletterongevoelig(self):
        assert is_toegestaan("JEROEN@Gmail.com", [" Jeroen@GMAIL.com "])

    def test_adresregel_opent_het_domein_niet_via_de_domeincontrole(self):
        assert not is_toegestaan("info@gmail.com", ["jeroen@gmail.com"])


class TestOmschrijf:
    """De tekst die de gebruiker in de foutmelding en de modal ziet."""

    def test_domeinen_krijgen_een_apenstaart(self):
        assert omschrijf(["lokalist.nl", "miedema.nl"]) == "@lokalist.nl, @miedema.nl"

    def test_adressen_blijven_zoals_ze_zijn(self):
        assert omschrijf(["lokalist.nl", "jeroen@gmail.com"]) == "@lokalist.nl, jeroen@gmail.com"

    def test_lege_lijst_geeft_lege_tekst(self):
        assert omschrijf([]) == ""

    def test_normaliseert_zelf(self):
        """Gelijk aan omschrijfAllowlist in de UI, die dat ook doet."""
        assert omschrijf([" @Lokalist.NL ", "Jeroen@Gmail.com"]) == (
            "@lokalist.nl, jeroen@gmail.com"
        )


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

    @pytest.mark.parametrize("domein", ["@lokalist.nl", " Lokalist.NL ", "LOKALIST.nl"])
    def test_normaliseert_de_domeinlijst_zelf(self, domein):
        """Werkt ook op een lijst die niet via lees_allowlist kwam."""
        assert is_toegestaan("info@lokalist.nl", [domein])


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
