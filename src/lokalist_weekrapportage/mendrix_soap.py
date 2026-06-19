"""Fase 2 — order aanmaken in MendriX via SOAP. NOG NIET GEBOUWD.

Ontbreekt voordat dit geïmplementeerd kan worden (zie CLAUDE.md §4d):
  - voorbeeld-XML van een CreateOrder SOAP-request
  - WSDL/methode-documentatie (operatienaam onbekend)
  - bevestiging: ClientId of ClientNumber bij het aanmaken?
  - authenticatiemethode in de SOAP-envelope

Bouw dit NIET zelf op aannames — vraag de ontbrekende documentatie na bij
Jeroen of wacht tot die is aangeleverd.
"""


def bouw_instructies(rows: list[tuple], weeknummer: int, jaar: int) -> str:
    """Bouwt het Instructions-veld: samenvattingszin + alle unieke
    ordernummers, gesorteerd, elk op een eigen regel. Zie CLAUDE.md §4b."""
    alle_orders: set[int] = set()
    for r in rows:
        ordernummers_veld = r[8]
        for nr in ordernummers_veld.split(","):
            nr = nr.strip()
            if nr:
                alle_orders.add(int(nr))
    gesorteerd = sorted(alle_orders)
    regels = [f"Lokalist week {weeknummer} {jaar} overzicht. Ordernummers:"]
    regels.extend(str(nr) for nr in gesorteerd)
    return "\n".join(regels)


def maak_order_aan(*args, **kwargs):
    raise NotImplementedError(
        "Fase 2 (SOAP order-aanmaak) is nog niet geïmplementeerd — "
        "wacht op de documentatie/voorbeelden uit CLAUDE.md §4d."
    )
