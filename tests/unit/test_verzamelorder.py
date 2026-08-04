"""Tests voor de verzamelorder-hulpfuncties van het dashboard."""

from datetime import datetime

import pytest

from lokalist_weekrapportage.verzamelorder import (
    HANDMATIG_PREFIX,
    NOTITIE_MAXLENGTE,
    bouw_handmatige_notitie,
    bouw_store_xml,
    dagnaam,
    formatteer_aanmaakmoment,
    is_handmatig,
    maandnaam,
    parse_naam,
    periode_omschrijving,
    totaal_bedrag,
    totaal_laden_colli,
)


class TestDatumopmaak:
    @pytest.mark.parametrize(
        ("moment", "verwacht"),
        [
            (datetime(2026, 8, 2, 23, 30), "zondag 02 augustus 2026"),
            (datetime(2026, 7, 13, 11, 34), "maandag 13 juli 2026"),
            (datetime(2026, 6, 24, 15, 43), "woensdag 24 juni 2026"),
            (datetime(2026, 1, 1, 0, 0), "donderdag 01 januari 2026"),
            (datetime(2026, 12, 31, 23, 59), "donderdag 31 december 2026"),
        ],
    )
    def test_automatische_order(self, moment, verwacht):
        """Formaat: dagnaam dd maandnaam jaar (automatisch)."""
        assert formatteer_aanmaakmoment(moment, handmatig=False) == f"{verwacht} (automatisch)"

    def test_handmatige_order(self):
        assert formatteer_aanmaakmoment(datetime(2026, 8, 4, 11, 9), handmatig=True) == (
            "dinsdag 04 augustus 2026 (handmatig)"
        )

    def test_dag_wordt_met_twee_cijfers_getoond(self):
        """'dd' in de specificatie: 2 augustus wordt 02 augustus."""
        assert "02 augustus" in formatteer_aanmaakmoment(datetime(2026, 8, 2), handmatig=False)

    def test_alle_dagnamen(self):
        # 2026-08-03 is een maandag.
        verwacht = [
            "maandag",
            "dinsdag",
            "woensdag",
            "donderdag",
            "vrijdag",
            "zaterdag",
            "zondag",
        ]
        for dag, naam in enumerate(verwacht, start=3):
            assert dagnaam(datetime(2026, 8, dag).date()) == naam

    def test_alle_maandnamen(self):
        assert maandnaam(1) == "januari"
        assert maandnaam(12) == "december"

    @pytest.mark.parametrize("maand", [0, 13, -1])
    def test_ongeldige_maand(self, maand):
        with pytest.raises(ValueError):
            maandnaam(maand)


class TestHandmatigeMarkering:
    def test_notitie_bevat_de_marker_en_leesbare_tekst(self):
        notitie = bouw_handmatige_notitie(31, 2026, 1266289, "Jeroen")

        assert notitie.startswith(HANDMATIG_PREFIX)
        assert "| door Jeroen]" in notitie
        assert "Week 31 2026" in notitie
        # Het vervangen ordernummer moet terug te vinden zijn.
        assert "Vorige verzamelorder 1266289 verwijderd" in notitie
        # Datum/tijd staan bewust NIET in de notitie: die komen uit Orders.Moment.
        assert "augustus" not in notitie
        # En hij moet in dbo.Orders.Diversen (varchar 250) passen.
        assert len(notitie) <= NOTITIE_MAXLENGTE

    def test_herkent_handmatige_order(self):
        notitie = bouw_handmatige_notitie(31, 2026, 1266289, "Jeroen")
        assert is_handmatig(notitie) is True

    @pytest.mark.parametrize(
        "notities",
        ["", None, "Aangemeld via postapp door Tos", "gewone notitie zonder marker"],
    )
    def test_herkent_automatische_order(self, notities):
        assert is_handmatig(notities) is False

    def test_oude_notitie_zonder_naam_telt_nog_steeds_als_handmatig(self):
        """Orders van voor de naaminvoer mogen niet ineens automatisch heten."""
        oud = "[HANDMATIG HERGENEREERD] Dit weekrapport (week 31 2026) is op dinsdag..."
        assert is_handmatig(oud) is True
        assert parse_naam(oud) is None

    def test_leest_de_naam_terug(self):
        notitie = bouw_handmatige_notitie(31, 2026, 1266289, "Jeroen")
        assert parse_naam(notitie) == "Jeroen"

    def test_leest_een_lange_naam_terug(self):
        naam = "Christiaan van der Meulen-Bergsma"
        assert parse_naam(bouw_handmatige_notitie(31, 2026, 1266289, naam)) == naam

    def test_kort_een_extreem_lange_naam_in_zodat_hij_past(self):
        notitie = bouw_handmatige_notitie(31, 2026, 1266289, "X" * 300)
        assert len(notitie) <= NOTITIE_MAXLENGTE
        # De markering en het ordernummer blijven overeind.
        assert notitie.startswith(HANDMATIG_PREFIX)
        assert "Vorige verzamelorder 1266289 verwijderd" in notitie

    def test_spaties_worden_genormaliseerd(self):
        notitie = bouw_handmatige_notitie(31, 2026, 1266289, "  Jan   Pieter ")
        assert parse_naam(notitie) == "Jan Pieter"

    @pytest.mark.parametrize("leeg", ["", "   "])
    def test_lege_naam_is_een_fout(self, leeg):
        with pytest.raises(ValueError, match="Naam is verplicht"):
            bouw_handmatige_notitie(31, 2026, 1266289, leeg)


class TestPeriodeOmschrijving:
    def test_binnen_een_maand(self):
        # Week 32 van 2026 loopt van 3 t/m 9 augustus.
        assert periode_omschrijving(32, 2026) == "3 t/m 9 augustus 2026"

    def test_over_een_maandgrens(self):
        # Week 31 van 2026 loopt van 27 juli t/m 2 augustus.
        assert periode_omschrijving(31, 2026) == "27 juli t/m 2 augustus 2026"


class TestTotalen:
    RIJEN = [
        ("2026-08-01", "Laden", "A", "S", "1234AB", "Plaats", 10, 1, "111", "1-20", 25.0),
        ("2026-08-01", "Lossen", "B", "S", "1234AB", "Plaats", 5, 1, "112", "1-20", 12.5),
        ("2026-08-02", "Laden", "C", "S", "1234AB", "Plaats", 7, 1, "113", "21-40", 0.0),
    ]

    def test_telt_alleen_laden_colli(self):
        assert totaal_laden_colli(self.RIJEN) == 17

    def test_telt_bedrag_over_laden_en_lossen(self):
        assert totaal_bedrag(self.RIJEN) == 37.5

    def test_lege_invoer(self):
        assert totaal_laden_colli([]) == 0
        assert totaal_bedrag([]) == 0

    def test_hoofdletterongevoelig_op_tasktype(self):
        rijen = [("2026-08-01", "LADEN", "A", "S", "Z", "P", 4, 1, "1", "1-20", 1.0)]
        assert totaal_laden_colli(rijen) == 4


class TestStoreXml:
    ARGS = (32, 238.13, "Lokalist week 31 2026 overzicht.", "2026-08-02T23:30:04", 31, 2026)

    def test_zonder_notitie_geen_notes_element(self):
        assert "<Notes>" not in bouw_store_xml(*self.ARGS)

    def test_met_notitie_wel_notes_element(self):
        xml = bouw_store_xml(*self.ARGS, notities="Handmatig gedraaid")
        assert "<Notes>Handmatig gedraaid</Notes>" in xml

    def test_notitie_wordt_ge_escaped(self):
        """XML-onveilige tekens in de notitie mogen de XML niet breken."""
        xml = bouw_store_xml(*self.ARGS, notities="Jan & Piet <test>")
        assert "<Notes>Jan &amp; Piet &lt;test&gt;</Notes>" in xml

    def test_kenmerk_bevat_week_en_jaar(self):
        """Het dashboard leest week/jaar later terug uit dit kenmerk."""
        assert "<ReferenceYour>Week 31 2026</ReferenceYour>" in bouw_store_xml(*self.ARGS)

    def test_reference_markeert_verzamelorder(self):
        """CatchWord='Verzamelorder' houdt de order uit zijn eigen weekrapport."""
        assert "<Reference>Verzamelorder</Reference>" in bouw_store_xml(*self.ARGS)

    def test_instructies_worden_ge_escaped(self):
        xml = bouw_store_xml(32, 1.0, "A & B", "2026-08-02T23:30:04", 31, 2026)
        assert "<Instructions>A &amp; B</Instructions>" in xml
