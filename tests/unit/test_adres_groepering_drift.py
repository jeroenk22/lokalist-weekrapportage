"""Bewaakt dat het week- en het jaaroverzicht adressen identiek groeperen.

`lokalist_staffel_overzicht.sql` (weekrapport) en
`lokalist_periode_overzicht.sql` (jaaroverzicht, via
`scripts/run_jaaroverzicht.py`) hebben allebei een eigen kopie van het
TaakNamen + AdresTotalen-blok: groeperen op het genormaliseerde adres in plaats
van op de bedrijfsnaam, met de namen komma-gescheiden.

Lopen die kopieën uiteen, dan telt het jaaroverzicht stilletjes andere bedragen
op dan de som van de weekrapporten. CLAUDE.md schrijft voor dat gedupliceerde
logica een drift-test krijgt; dit is die test.
"""

from tests.helpers.sql_extract import haal_groeperingsblok, haal_periode_groeperingsblok


def test_beide_queries_groeperen_adressen_identiek():
    assert haal_groeperingsblok() == haal_periode_groeperingsblok(), (
        "Het TaakNamen/AdresTotalen-blok in lokalist_staffel_overzicht.sql en "
        "lokalist_periode_overzicht.sql is uiteengelopen. Pas beide bestanden aan, "
        "of leg in de headers vast waarom ze bewust verschillen."
    )


def test_het_blok_bevat_de_kern_van_de_groepering():
    # Vangt af dat de test groen blijft doordat de extractie per ongeluk niets
    # oplevert en twee lege strings vergeleken worden.
    blok = haal_groeperingsblok()
    assert "GROUP BY Datum, TaskType, AdresSleutel" in blok, "groepering op adres ontbreekt"
    assert "STRING_AGG(CASE WHEN NaamRang = 1 THEN LocName END, ', ')" in blok, (
        "komma-gescheiden namen (elk een keer) ontbreken"
    )
    assert "WITHIN GROUP (ORDER BY LocName)" in blok, "vaste volgorde van de namen ontbreekt"
