"""Bewaakt dat beide queries de staffeltrede op precies dezelfde manier kiezen.

`lokalist_staffel_overzicht.sql` en `lokalist_spoed_overzicht.sql` hebben allebei
een eigen `OUTER APPLY` dat bepaalt welke trede geldt: bij overlap wint het
hoogste tarief, en boven de hoogste trede grijpt de fallback uit #27.

Twee kopieën van dezelfde regel lopen vanzelf uiteen — dat is precies wat er bij
#27 gebeurde, toen alleen het hoofdrapport de fallback kreeg en de spoedquery
achterbleef (issue #28). CLAUDE.md schrijft daarom voor dat gedupliceerde logica
een drift-test krijgt.

Vergeleken wordt alleen de keuzelogica (WHERE + ORDER BY). De projectie
verschilt bewust: het hoofdrapport toont de trede zelf, de spoedquery heeft
alleen het tarief nodig. Het colli-veld heet ook anders (`at.TotaalColli` tegen
`oc.LadenColli`), want de queries tellen op een ander niveau; dat wordt
genormaliseerd zodat de vergelijking over de logica gaat en niet over namen.
"""

import re

from tests.helpers.sql_extract import haal_outer_apply_blok, haal_spoed_outer_apply_blok

# Het hoofdrapport telt per adres + dag, de spoedquery per order. Dat verschil
# is bewust en mag de vergelijking niet in de weg zitten.
_COLLI_UITDRUKKINGEN = ("at.TotaalColli", "oc.LadenColli")


def _keuzelogica(blok: str) -> str:
    """Kookt een OUTER APPLY-blok terug tot de kale keuzelogica."""
    tekst = re.sub(r"--[^\n]*", " ", blok)  # commentaar eruit
    tekst = tekst[tekst.index("WHERE") :]  # projectie eruit
    tekst = re.sub(r"\)\s*(cg|s)\s*$", "", tekst)  # sluithaak + alias eruit
    for uitdrukking in _COLLI_UITDRUKKINGEN:
        tekst = tekst.replace(uitdrukking, "<COLLI>")
    return " ".join(tekst.split())


def test_beide_queries_kiezen_de_trede_identiek():
    hoofd = _keuzelogica(haal_outer_apply_blok())
    spoed = _keuzelogica(haal_spoed_outer_apply_blok())

    assert hoofd == spoed, (
        "De staffelkeuze in lokalist_staffel_overzicht.sql en "
        "lokalist_spoed_overzicht.sql is uiteengelopen. Pas beide bestanden aan, "
        "of leg in de header vast waarom ze bewust verschillen."
    )


def test_beide_blokken_bevatten_de_tie_break_en_de_fallback():
    # Vangt af dat de test groen blijft doordat _keuzelogica per ongeluk alles
    # wegstript en twee lege strings vergelijkt.
    for blok in (haal_outer_apply_blok(), haal_spoed_outer_apply_blok()):
        logica = _keuzelogica(blok)
        assert "ORDER BY s.Minimum DESC" in logica, "tie-break op hoogste tarief ontbreekt"
        assert "NOT EXISTS" in logica, "fallback boven de hoogste trede ontbreekt"
        assert "<COLLI>" in logica, "colli-uitdrukking niet herkend"
