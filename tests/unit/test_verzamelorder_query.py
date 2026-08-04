"""Tests voor het ophalen en interpreteren van verzamelorders."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from lokalist_weekrapportage.verzamelorder_query import (
    Verzamelorder,
    _rij_naar_verzamelorder,
    haal_verzamelorders_op,
    parse_kenmerk,
)


def maak_rij(**overrides):
    """Bootst een pyodbc-rij na (attribuuttoegang op kolomnaam)."""
    velden = {
        "OrderId": 1266289,
        "Aangemaakt": datetime(2026, 8, 2, 23, 30, 4),
        "Notities": "",
        "TotaalColli": 32,
        "TotaalBedrag": 238.13,
        "Kenmerk": "Week 31 2026",
        "FactuurSleutel": None,
        "FactuurNummer": None,
        "FactuurJaar": None,
        "FactuurStatus": 2,
    }
    velden.update(overrides)
    return SimpleNamespace(**velden)


class TestParseKenmerk:
    @pytest.mark.parametrize(
        ("kenmerk", "verwacht"),
        [
            ("Week 31 2026", (31, 2026)),
            ("Week 1 2026", (1, 2026)),
            ("Week 53 2020", (53, 2020)),
            ("week 31 2026", (31, 2026)),  # hoofdletterongevoelig
            ("  Week 31 2026  ", (31, 2026)),  # spaties eromheen
            ("Week  31  2026", (31, 2026)),  # dubbele spaties
        ],
    )
    def test_geldige_kenmerken(self, kenmerk, verwacht):
        assert parse_kenmerk(kenmerk) == verwacht

    @pytest.mark.parametrize(
        "kenmerk",
        [
            "week 1 t/m 24, 2026",  # jaaroverzicht — hoort niet in het dashboard
            "",
            None,
            "Verzamelorder",
            "Week 31",
            "Week 0 2026",  # week 0 bestaat niet
            "Week 54 2026",  # week 54 bestaat niet
            "Week 31 26",  # geen viercijferig jaar
            "Weekend 31 2026",
        ],
    )
    def test_ongeldige_kenmerken(self, kenmerk):
        assert parse_kenmerk(kenmerk) is None


class TestRijNaarVerzamelorder:
    def test_automatische_order(self):
        vo = _rij_naar_verzamelorder(maak_rij())

        assert vo is not None
        assert vo.order_id == 1266289
        assert (vo.weeknummer, vo.jaar) == (31, 2026)
        assert vo.handmatig is False
        assert vo.label == "zondag 02 augustus 2026 (automatisch)"

    def test_handmatige_order(self):
        vo = _rij_naar_verzamelorder(
            maak_rij(
                Notities="[HANDMATIG HERGENEREERD] opnieuw gedraaid",
                Aangemaakt=datetime(2026, 8, 4, 11, 9),
            )
        )

        assert vo is not None
        assert vo.handmatig is True
        assert vo.label == "dinsdag 04 augustus 2026 (handmatig)"

    def test_rij_zonder_weekkenmerk_wordt_overgeslagen(self):
        assert _rij_naar_verzamelorder(maak_rij(Kenmerk="week 1 t/m 24, 2026")) is None

    def test_lege_waarden_worden_opgevangen(self):
        vo = _rij_naar_verzamelorder(maak_rij(Notities=None, TotaalColli=None, TotaalBedrag=None))

        assert vo is not None
        assert vo.notities == ""
        assert vo.totaal_colli == 0
        assert vo.totaal_bedrag == 0.0


class TestAsDict:
    def test_bevat_de_velden_die_de_frontend_verwacht(self):
        vo = Verzamelorder(
            order_id=1266289,
            aangemaakt=datetime(2026, 8, 2, 23, 30, 4),
            weeknummer=31,
            jaar=2026,
            handmatig=False,
            notities="",
            totaal_colli=32,
            totaal_bedrag=238.13,
        )

        d = vo.as_dict()

        assert d == {
            "orderId": 1266289,
            "aangemaakt": "2026-08-02T23:30:04",
            "weeknummer": 31,
            "jaar": 2026,
            "handmatig": False,
            "notities": "",
            "totaalColli": 32,
            "totaalBedrag": 238.13,
            "label": "zondag 02 augustus 2026 (automatisch)",
            "hergenereerdDoor": None,
            "herkomstTekst": None,
            "gefactureerd": False,
            "factuurNummer": None,
            "factuurSleutel": None,
            "factuurVoorlopig": False,
            "factuurKopieerwaarde": None,
            "factuurOmschrijving": None,
        }


class TestHaalVerzamelordersOp:
    def _mock_connect(self, rijen):
        cursor = MagicMock()
        cursor.fetchall.return_value = rijen
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_filtert_niet_weekgebonden_orders_eruit(self, tmp_path):
        rijen = [
            maak_rij(OrderId=1, Kenmerk="Week 31 2026"),
            maak_rij(OrderId=2, Kenmerk="week 1 t/m 24, 2026"),
            maak_rij(OrderId=3, Kenmerk="Week 30 2026"),
        ]
        with patch(
            "lokalist_weekrapportage.verzamelorder_query.pyodbc.connect",
            return_value=self._mock_connect(rijen),
        ):
            orders = haal_verzamelorders_op(MagicMock())

        assert [vo.order_id for vo in orders] == [1, 3]

    def test_sluit_de_verbinding_ook_bij_een_fout(self):
        conn = MagicMock()
        conn.cursor.return_value.execute.side_effect = RuntimeError("SQL kapot")

        with patch("lokalist_weekrapportage.verzamelorder_query.pyodbc.connect", return_value=conn):
            with pytest.raises(RuntimeError, match="SQL kapot"):
                haal_verzamelorders_op(MagicMock())

        conn.close.assert_called_once()

    def test_lege_lijst_is_geen_fout(self):
        with patch(
            "lokalist_weekrapportage.verzamelorder_query.pyodbc.connect",
            return_value=self._mock_connect([]),
        ):
            assert haal_verzamelorders_op(MagicMock()) == []


class TestGefactureerd:
    """Een gefactureerde order mag nooit hergenereerd worden."""

    def test_zonder_factuurnummer_is_niet_gefactureerd(self):
        vo = _rij_naar_verzamelorder(
            maak_rij(FactuurSleutel=None, FactuurNummer=None, FactuurStatus=2)
        )
        assert vo is not None
        assert vo.gefactureerd is False
        assert vo.factuur_nummer is None

    def test_met_factuurnummer_is_gefactureerd(self):
        vo = _rij_naar_verzamelorder(
            maak_rij(FactuurSleutel=154055, FactuurNummer=31511432, FactuurStatus=20)
        )
        assert vo is not None
        assert vo.gefactureerd is True
        assert vo.factuur_nummer == 31511432
        assert vo.factuur_voorlopig is False
        assert vo.factuur_omschrijving == "factuur 31511432"
        # Definitief: kopieren geeft het InvNo, niet de interne InvKey.
        assert vo.factuur_kopieerwaarde == 31511432

    def test_factuursleutel_nul_telt_niet_als_factuur(self):
        """InvKey=0 komt voor als 'geen factuur' en mag niet blokkeren."""
        vo = _rij_naar_verzamelorder(maak_rij(FactuurSleutel=0))
        assert vo is not None
        assert vo.gefactureerd is False

    def test_voorlopige_factuur_blokkeert_ook(self):
        """Wel een factuurregel (InvKey), nog geen definitief nummer (InvNo)."""
        vo = _rij_naar_verzamelorder(maak_rij(FactuurSleutel=154793, FactuurNummer=None))
        assert vo is not None
        assert vo.gefactureerd is True
        assert vo.factuur_voorlopig is True
        assert vo.factuur_nummer is None
        assert vo.factuur_omschrijving == "voorlopige factuur 154793"
        # Kopieren moet de sleutel geven, want een nummer bestaat nog niet.
        assert vo.factuur_kopieerwaarde == 154793

    def test_as_dict_geeft_de_factuurvelden_door(self):
        vo = _rij_naar_verzamelorder(maak_rij(FactuurSleutel=154055, FactuurNummer=31511432))
        assert vo is not None
        d = vo.as_dict()
        assert d["gefactureerd"] is True
        assert d["factuurNummer"] == 31511432
        assert d["factuurVoorlopig"] is False
        assert d["factuurOmschrijving"] == "factuur 31511432"
        assert d["factuurKopieerwaarde"] == 31511432
        assert d["factuurSleutel"] == 154055
