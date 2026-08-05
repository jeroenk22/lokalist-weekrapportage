"""Unit tests voor mendrix_soap.py — bouw_instructies, bouw_ordernummers_txt, maak_order_aan."""

import pytest

from lokalist_weekrapportage.mendrix_soap import (
    bouw_instructies,
    bouw_ordernummers_txt,
    maak_order_aan,
)


def _rij(orders: str = "1001") -> tuple:
    return ("2026-06-09", "Laden", "Loc", "Straat 1", "1234AB", "Aalten", 3, 2, orders, "A", 10.0)


def _spoed_rij(order_id: str = "9999") -> tuple:
    return ("2026-06-09", order_id, "SpLoc", "Spoed 1", "Sp1 Naam", "Aalten", 1, 50.0)


# ---------------------------------------------------------------------------
# bouw_instructies
# ---------------------------------------------------------------------------


def test_bouw_instructies_bevat_weeknummer_en_jaar():
    result = bouw_instructies([_rij("1001")], 24, 2026)
    assert "week 24 2026" in result


def test_bouw_instructies_verwijst_naar_pdf():
    result = bouw_instructies([_rij("1001")], 24, 2026)
    assert "zie PDF in dossier" in result


def test_bouw_instructies_telt_unieke_orders():
    result = bouw_instructies([_rij("1001,1002")], 24, 2026)
    assert "(2 orders)" in result


def test_bouw_instructies_dedupliceert():
    rows = [_rij("1001"), _rij("1001,1002")]
    result = bouw_instructies(rows, 24, 2026)
    assert "(2 orders)" in result


def test_bouw_instructies_met_spoed_rows():
    result = bouw_instructies([_rij("1001")], 24, 2026, spoed_rows=[_spoed_rij("9999")])
    assert "(2 orders)" in result


def test_bouw_instructies_lege_input():
    result = bouw_instructies([], 1, 2026)
    assert "week 1 2026" in result
    assert "(0 orders)" in result


# ---------------------------------------------------------------------------
# bouw_ordernummers_txt
# ---------------------------------------------------------------------------


def test_bouw_ordernummers_txt_bevat_koptekst():
    result = bouw_ordernummers_txt([_rij("1001")], 24, 2026)
    assert "week 24 2026" in result


def test_bouw_ordernummers_txt_bevat_ordernummers():
    result = bouw_ordernummers_txt([_rij("1001,1002")], 24, 2026)
    assert "1001" in result
    assert "1002" in result


def test_bouw_ordernummers_txt_gesorteerd():
    rows = [_rij("1003"), _rij("1001"), _rij("1002")]
    result = bouw_ordernummers_txt(rows, 24, 2026)
    pos_1001 = result.index("1001")
    pos_1002 = result.index("1002")
    pos_1003 = result.index("1003")
    assert pos_1001 < pos_1002 < pos_1003


def test_bouw_ordernummers_txt_dedupliceert():
    rows = [_rij("1001"), _rij("1001,1002")]
    result = bouw_ordernummers_txt(rows, 24, 2026)
    assert result.count("1001") == 1


def test_bouw_ordernummers_txt_met_spoed_rows():
    result = bouw_ordernummers_txt([_rij("1001")], 24, 2026, spoed_rows=[_spoed_rij("9999")])
    assert "9999" in result
    assert "(2)" in result


def test_bouw_ordernummers_txt_eindigt_met_newline():
    result = bouw_ordernummers_txt([_rij("1001")], 24, 2026)
    assert result.endswith("\n")


# ---------------------------------------------------------------------------
# maak_order_aan
# ---------------------------------------------------------------------------


def test_maak_order_aan_gooit_not_implemented():
    with pytest.raises(NotImplementedError):
        maak_order_aan()
