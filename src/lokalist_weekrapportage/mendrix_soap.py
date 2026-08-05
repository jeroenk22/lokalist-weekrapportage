"""Fase 2 — order aanmaken in MendriX via SOAP. NOG NIET GEBOUWD.

Ontbreekt voordat dit geïmplementeerd kan worden (zie CLAUDE.md §4d):
  - voorbeeld-XML van een CreateOrder SOAP-request
  - WSDL/methode-documentatie (operatienaam onbekend)
  - bevestiging: ClientId of ClientNumber bij het aanmaken?
  - authenticatiemethode in de SOAP-envelope

Bouw dit NIET zelf op aannames — vraag de ontbrekende documentatie na bij
Jeroen of wacht tot die is aangeleverd.
"""


def bouw_instructies(
    rows: list[tuple], weeknummer: int, jaar: int, spoed_rows: list[tuple] | None = None
) -> str:
    """Bouwt het Instructions-veld: samenvattingszin + alle unieke
    ordernummers (normaal + spoed), gesorteerd, elk op een eigen regel."""
    alle_orders: set[int] = set()
    for r in rows:
        for nr in r[8].split(","):
            nr = nr.strip()
            if nr:
                alle_orders.add(int(nr))
    for r in spoed_rows or []:
        nr = r[1].strip()
        if nr:
            alle_orders.add(int(nr))
    n = len(alle_orders)
    return (
        f"Lokalist week {weeknummer} {jaar} overzicht. "
        f"Ordernummers: zie PDF in dossier ({n} orders)"
    )


def bouw_ordernummers_txt(
    rows: list[tuple], weeknummer: int, jaar: int, spoed_rows: list[tuple] | None = None
) -> str:
    """Geeft de inhoud van ordernummers.txt terug: koptekst + gesorteerde nummers."""
    alle_orders: set[int] = set()
    for r in rows:
        for nr in r[8].split(","):
            nr = nr.strip()
            if nr:
                alle_orders.add(int(nr))
    for r in spoed_rows or []:
        nr = r[1].strip()
        if nr:
            alle_orders.add(int(nr))
    gesorteerd = sorted(alle_orders)
    regels = [f"Lokalist week {weeknummer} {jaar} — ordernummers ({len(gesorteerd)}):"]
    regels.extend(str(nr) for nr in gesorteerd)
    return "\n".join(regels) + "\n"


def maak_order_aan(*args, **kwargs):
    raise NotImplementedError(
        "Fase 2 (SOAP order-aanmaak) is nog niet geïmplementeerd — "
        "wacht op de documentatie/voorbeelden uit CLAUDE.md §4d."
    )
