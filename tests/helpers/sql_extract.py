"""Haalt SQL-fragmenten letterlijk uit lokalist_staffel_overzicht.sql.

Zo verifieert de test in tests/integration/test_staffel_overlap_localdb.py de
daadwerkelijke queryskelet-tekst i.p.v. een losse kopie die kan verwateren
als iemand de productiequery later aanpast.
"""

import os

_SQL_PAD = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "src",
        "lokalist_weekrapportage",
        "lokalist_staffel_overzicht.sql",
    )
)


def _sql_tekst() -> str:
    with open(_SQL_PAD, encoding="utf-8") as f:
        return f.read()


def haal_staffel_cte_body() -> str:
    """Geeft de body van de `;WITH Staffel AS (...)`-CTE, zonder omliggende parens."""
    sql = _sql_tekst()
    start_marker = ";WITH Staffel AS ("
    eind_marker = "TaskColli AS ("
    try:
        start = sql.index(start_marker) + len(start_marker)
        eind = sql.index(eind_marker, start)
        body = sql[start:eind].rstrip()
        assert body.endswith("),"), "onverwacht einde van de Staffel-CTE"
        return body[: -len("),")].rstrip()
    except (ValueError, AssertionError) as exc:
        raise AssertionError(
            f"Kon de Staffel-CTE niet extraheren uit {_SQL_PAD} — is de "
            f"structuur van de query gewijzigd? ({exc})"
        ) from exc


_SPOED_SQL_PAD = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "src",
        "lokalist_weekrapportage",
        "lokalist_spoed_overzicht.sql",
    )
)


def haal_spoed_outer_apply_blok() -> str:
    """Geeft het `OUTER APPLY (...) s`-blok uit de spoed-query, letterlijk."""
    with open(_SPOED_SQL_PAD, encoding="utf-8") as f:
        sql = f.read()
    start_marker = "OUTER APPLY ("
    eind_marker = "\n) s"
    try:
        start = sql.index(start_marker)
        eind = sql.index(eind_marker, start) + len(eind_marker)
        return sql[start:eind]
    except ValueError as exc:
        raise AssertionError(
            f"Kon het OUTER APPLY-blok niet extraheren uit {_SPOED_SQL_PAD} — is de "
            f"structuur van de query gewijzigd? ({exc})"
        ) from exc


def haal_outer_apply_blok() -> str:
    """Geeft het volledige `OUTER APPLY (...) cg`-blok, letterlijk uit het bestand."""
    sql = _sql_tekst()
    start_marker = "OUTER APPLY ("
    eind_marker = ") cg"
    try:
        start = sql.index(start_marker)
        eind = sql.index(eind_marker, start) + len(eind_marker)
        return sql[start:eind]
    except ValueError as exc:
        raise AssertionError(
            f"Kon het OUTER APPLY-blok niet extraheren uit {_SQL_PAD} — is de "
            f"structuur van de query gewijzigd? ({exc})"
        ) from exc


_PERIODE_SQL_PAD = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "src",
        "lokalist_weekrapportage",
        "lokalist_periode_overzicht.sql",
    )
)

_GROEPERING_START = "TaakNamen AS ("
_GROEPERING_EIND = "\n)\nSELECT"


def _haal_groeperingsblok(pad: str) -> str:
    """Geeft het TaakNamen + AdresTotalen-blok, letterlijk uit het bestand."""
    with open(pad, encoding="utf-8") as f:
        sql = f.read()
    try:
        start = sql.index(_GROEPERING_START)
        eind = sql.index(_GROEPERING_EIND, start) + len("\n)")
        return sql[start:eind]
    except ValueError as exc:
        raise AssertionError(
            f"Kon het TaakNamen/AdresTotalen-blok niet extraheren uit {pad} — is de "
            f"structuur van de query gewijzigd? ({exc})"
        ) from exc


def haal_groeperingsblok() -> str:
    """Het adres-groeperingsblok uit het weekrapport."""
    return _haal_groeperingsblok(_SQL_PAD)


def haal_periode_groeperingsblok() -> str:
    """Het adres-groeperingsblok uit het jaar-/periodeoverzicht."""
    return _haal_groeperingsblok(_PERIODE_SQL_PAD)
