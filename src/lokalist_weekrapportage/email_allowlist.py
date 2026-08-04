"""Domein-allowlist voor de ontvangers die het dashboard meestuurt.

Het weekrapport bevat klantgegevens van De Lokalist. In de regenereer-modal kan
iemand het Aan-adres aanpassen of extra adressen toevoegen; zonder grens gaat
het rapport daarmee naar elk ingetypt adres. `DASHBOARD_EMAIL_DOMEINEN` in .env
begrenst dat tot een vaste lijst domeinen.

Twee bewuste keuzes:

* **Leeg = geen begrenzing.** Dat is het gedrag van vóór deze controle, zodat een
  bestaande installatie zonder aangepaste .env niet ineens niets meer verstuurt.
* **De adressen uit .env zijn altijd toegestaan**, ook als hun domein niet in de
  lijst staat. Anders zou een te krappe lijst de gewone ontvangers blokkeren en
  krijg je een configuratie die zichzelf tegenspreekt.

De echte controle hoort hier, in Python: de browser is geen beveiliging. De
lijst gaat wel mee naar het dashboard, zodat de UI het al bij het typen meldt.
"""

import os
from collections.abc import Iterable

ENV_NAAM = "DASHBOARD_EMAIL_DOMEINEN"


def lees_toegestane_domeinen(ruw: str | None = None) -> list[str]:
    """Domeinen uit `DASHBOARD_EMAIL_DOMEINEN`, genormaliseerd naar kleine letters.

    Een lege of ontbrekende waarde levert een lege lijst op: geen begrenzing.
    Een leidende `@` mag (`@lokalist.nl`), zodat beide schrijfwijzen werken.
    """
    if ruw is None:
        ruw = os.getenv(ENV_NAAM, "")
    return [deel.strip().lstrip("@").lower() for deel in ruw.split(",") if deel.strip()]


def domein_van(adres: str) -> str:
    """Het domeindeel van een e-mailadres, in kleine letters.

    Een adres zonder `@` levert het adres zelf op; dat komt nooit in de
    allowlist voor en wordt dus geweigerd.
    """
    _, _, domein = adres.strip().rpartition("@")
    return domein.lower() if domein else adres.strip().lower()


def is_toegestaan(
    adres: str,
    domeinen: Iterable[str],
    altijd_toegestaan: Iterable[str] = (),
) -> bool:
    """Mag dit adres het rapport ontvangen?"""
    domeinlijst = list(domeinen)
    if not domeinlijst:
        return True
    if adres.strip().lower() in {a.strip().lower() for a in altijd_toegestaan}:
        return True
    return domein_van(adres) in domeinlijst


def geweigerde_adressen(
    adressen: Iterable[str],
    domeinen: Iterable[str],
    altijd_toegestaan: Iterable[str] = (),
) -> list[str]:
    """Adressen die buiten de allowlist vallen, in volgorde en zonder dubbelen."""
    domeinlijst = list(domeinen)
    toegestaan = list(altijd_toegestaan)
    geweigerd: list[str] = []
    for adres in adressen:
        schoon = adres.strip()
        if not schoon or is_toegestaan(schoon, domeinlijst, toegestaan):
            continue
        if schoon.lower() not in {g.lower() for g in geweigerd}:
            geweigerd.append(schoon)
    return geweigerd
