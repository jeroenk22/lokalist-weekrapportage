"""Allowlist voor de ontvangers die het dashboard meestuurt.

Het weekrapport bevat klantgegevens van De Lokalist. In de regenereer-modal kan
iemand het Aan-adres aanpassen of extra adressen toevoegen; zonder grens gaat
het rapport daarmee naar elk ingetypt adres. `DASHBOARD_EMAIL_DOMEINEN` in .env
begrenst dat.

Elke regel in die variabele is óf een domein óf één volledig adres:

    DASHBOARD_EMAIL_DOMEINEN=lokalist.nl,@miedema.nl,jeroen@gmail.com

Het onderscheid zit in de apenstaart: staat er een naam vóór de `@`, dan is het
één adres; anders een domein (een leidende `@` mag). Zo kun je één privéadres
toestaan om een testmail naar jezelf te sturen, zonder een heel publiek
maildomein als gmail.com open te zetten.

Twee bewuste keuzes:

* **Leeg = geen begrenzing.** Dat is het gedrag van vóór deze controle, zodat een
  bestaande installatie zonder aangepaste .env niet ineens niets meer verstuurt.
* **De adressen uit .env zijn altijd toegestaan**, ook als ze niet in de lijst
  staan. Anders zou een te krappe lijst de gewone ontvangers blokkeren en krijg
  je een configuratie die zichzelf tegenspreekt.

De echte controle hoort hier, in Python: de browser is geen beveiliging. De
lijst gaat wel mee naar het dashboard, zodat de UI het al bij het typen meldt.
"""

import os
from collections.abc import Iterable

# De naam zegt "DOMEINEN" terwijl er ook losse adressen in mogen. Bewust niet
# hernoemd: de variabele staat al in draaiende .env-bestanden en een rename zou
# de allowlist daar stilzwijgend uitschakelen — precies het gevaarlijke geval.
# .env.example en web/README.md leggen beide vormen uit.
ENV_NAAM = "DASHBOARD_EMAIL_DOMEINEN"


def is_adresregel(regel: str) -> bool:
    """Is dit één volledig adres in plaats van een domein?

    `jeroen@gmail.com` is een adres, `gmail.com` en `@gmail.com` zijn domeinen.
    """
    return "@" in regel


def lees_allowlist(ruw: str | None = None) -> list[str]:
    """Regels uit `DASHBOARD_EMAIL_DOMEINEN`, genormaliseerd naar kleine letters.

    Een lege of ontbrekende waarde levert een lege lijst op: geen begrenzing.
    Domeinen verliezen hun leidende `@`, adressen blijven volledig.
    """
    if ruw is None:
        ruw = os.getenv(ENV_NAAM, "")
    return [_normaliseer(deel) for deel in ruw.split(",") if deel.strip()]


def _normaliseer(regel: str) -> str:
    schoon = regel.strip().lower()
    # Alleen een leidende @ zonder naam ervoor hoort bij een domein.
    return schoon[1:] if schoon.startswith("@") else schoon


def domein_van(adres: str) -> str:
    """Het domeindeel van een e-mailadres, in kleine letters.

    Een adres zonder `@` levert het adres zelf op; dat komt nooit in de
    allowlist voor en wordt dus geweigerd.
    """
    _, _, domein = adres.strip().rpartition("@")
    return domein.lower() if domein else adres.strip().lower()


def omschrijf(regels: Iterable[str]) -> str:
    """De allowlist zoals hij in een foutmelding aan de gebruiker getoond wordt.

    Domeinen krijgen hun `@` terug, adressen blijven zoals ze zijn:
    `@lokalist.nl, @miedema.nl, jeroen@gmail.com`.

    Normaliseert zelf, net als is_toegestaan en omschrijfAllowlist in de UI:
    functies die als elkaars spiegel gedocumenteerd staan horen niet te
    verschillen in wat ze van hun invoer verwachten.
    """
    genormaliseerd = (_normaliseer(regel) for regel in regels if regel.strip())
    return ", ".join(regel if is_adresregel(regel) else f"@{regel}" for regel in genormaliseerd)


def is_toegestaan(
    adres: str,
    regels: Iterable[str],
    altijd_toegestaan: Iterable[str] = (),
) -> bool:
    """Mag dit adres het rapport ontvangen?

    Normaliseert de regels zelf, zodat een handmatig samengestelde lijst
    hetzelfde werkt als een lijst uit lees_allowlist(). Blijft daarmee gelijk
    aan toegestaan() in useEmailSelectie.ts, dat dit ook doet; twee als spiegel
    gedocumenteerde functies horen niet te verschillen in wat ze van hun invoer
    verwachten.
    """
    genormaliseerd = [_normaliseer(regel) for regel in regels if regel.strip()]
    if not genormaliseerd:
        return True

    schoon = adres.strip().lower()
    if schoon in {a.strip().lower() for a in altijd_toegestaan}:
        return True
    if schoon in {regel for regel in genormaliseerd if is_adresregel(regel)}:
        return True
    return domein_van(schoon) in {regel for regel in genormaliseerd if not is_adresregel(regel)}


def geweigerde_adressen(
    adressen: Iterable[str],
    regels: Iterable[str],
    altijd_toegestaan: Iterable[str] = (),
) -> list[str]:
    """Adressen die buiten de allowlist vallen, in volgorde en zonder dubbelen."""
    regellijst = list(regels)
    toegestaan = list(altijd_toegestaan)
    geweigerd: list[str] = []
    for adres in adressen:
        schoon = adres.strip()
        if not schoon or is_toegestaan(schoon, regellijst, toegestaan):
            continue
        if schoon.lower() not in {g.lower() for g in geweigerd}:
            geweigerd.append(schoon)
    return geweigerd
