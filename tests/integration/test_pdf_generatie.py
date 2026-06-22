"""Integratietests voor de volledige query-rows → PDF keten.

Geen mocks voor de transformatielogica — genereer_pdf wordt echt aangeroepen
met fixture-rijen. Alleen de externe SQL-verbinding wordt niet gebruikt.
"""

import os

import pytest

from lokalist_weekrapportage.genereer_rapport import genereer_pdf
from tests.fixtures.sample_rows import GEMENGDE_RIJEN, LADEN_RIJEN


def test_genereer_pdf_maakt_bestand_aan(tmp_path):
    output = str(tmp_path / "test.pdf")
    pad, totals = genereer_pdf(
        rows=LADEN_RIJEN,
        weeknummer=24,
        jaar=2026,
        periode_omschrijving="8 t/m 14 juni 2026",
        output_path=output,
    )
    assert os.path.isfile(pad)
    assert os.path.getsize(pad) > 0


def test_genereer_pdf_geeft_correcte_totalen(tmp_path):
    output = str(tmp_path / "test.pdf")
    _, totals = genereer_pdf(
        rows=LADEN_RIJEN,
        weeknummer=24,
        jaar=2026,
        periode_omschrijving="8 t/m 14 juni 2026",
        output_path=output,
    )
    assert "laden" in totals
    assert "lossen" in totals
    assert "totaal" in totals
    assert totals["laden"] == pytest.approx(sum(r[10] for r in LADEN_RIJEN if r[1] == "Laden"))


def test_genereer_pdf_met_gemengde_rijen(tmp_path):
    output = str(tmp_path / "test_gemengd.pdf")
    pad, totals = genereer_pdf(
        rows=GEMENGDE_RIJEN,
        weeknummer=24,
        jaar=2026,
        periode_omschrijving="8 t/m 14 juni 2026",
        output_path=output,
    )
    assert os.path.isfile(pad)


def test_genereer_pdf_lege_rows_geeft_geen_crash(tmp_path):
    output = str(tmp_path / "leeg.pdf")
    pad, totals = genereer_pdf(
        rows=[],
        weeknummer=1,
        jaar=2026,
        periode_omschrijving="29 dec t/m 4 jan 2026",
        output_path=output,
    )
    assert os.path.isfile(pad)
