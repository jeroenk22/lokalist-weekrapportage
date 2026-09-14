"""Verbinding met een lokale SQL Server LocalDB-instantie, voor tests die
echte T-SQL willen uitvoeren (geen mock) tegen een draaiende engine.

Gebruikt door tests met de marker `sql_localdb`. Op een ontwikkelmachine
zonder LocalDB/ODBC-driver worden die tests netjes geskipt. In CI (env var
CI gezet, zoals door GitHub Actions) faalt de test hard bij ontbrekende
LocalDB, zodat een kapotte testomgeving zichtbaar blijft i.p.v. stilzwijgend
groen te draaien.
"""

import os
import subprocess

import pyodbc
import pytest

_INSTANCE = r"MSSQLLocalDB"
_DRIVERS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server")


def _connectiestring(driver: str, database: str) -> str:
    return (
        f"DRIVER={{{driver}}};SERVER=(localdb)\\{_INSTANCE};"
        f"DATABASE={database};Trusted_Connection=yes;TrustServerCertificate=yes;"
    )


def _start_instance() -> None:
    subprocess.run(["SqlLocalDB", "start", _INSTANCE], capture_output=True, check=False)


def connect(database: str = "master") -> pyodbc.Connection:
    """Verbindt met de gegeven database op de LocalDB-instantie.

    Probeert meerdere ODBC-driverversies, want welke driver geïnstalleerd is
    verschilt per machine (dev-laptop vs. windows-latest CI-runner).
    """
    laatste_fout: Exception | None = None
    for driver in _DRIVERS:
        try:
            return pyodbc.connect(_connectiestring(driver, database), autocommit=True, timeout=5)
        except Exception as exc:
            laatste_fout = exc
    raise RuntimeError(
        f"Geen ODBC-driver kon verbinden met LocalDB-instantie {_INSTANCE}: {laatste_fout}"
    )


def master_connectie_of_skip() -> pyodbc.Connection:
    """Geeft een verbinding met de master-database, of skipt/faalt de test."""
    _start_instance()
    try:
        return connect("master")
    except Exception as exc:
        bericht = (
            f"SQL Server LocalDB-instantie '{_INSTANCE}' niet bereikbaar: {exc}. "
            "Deze test heeft een lokale SQL Server LocalDB nodig (zie tests/README.md)."
        )
        if os.environ.get("CI"):
            pytest.fail(bericht)
        pytest.skip(bericht)


# STRING_AGG bestaat pas vanaf SQL Server 2017, en de WITHIN GROUP-variant
# vraagt daarnaast compatibiliteitsniveau 110+. Tests die de VOLLEDIGE
# lokalist_staffel_overzicht.sql uitvoeren hebben dat nodig; tests die er
# alleen fragmenten uit draaien niet.
_MIN_MAJOR_VOOR_STRING_AGG = 14  # 14 = SQL Server 2017


def vereis_string_agg_of_skip(conn: pyodbc.Connection) -> None:
    """Skipt (of faalt in CI) als de engine te oud is voor STRING_AGG."""
    versie = str(conn.execute("SELECT SERVERPROPERTY('ProductVersion')").fetchone()[0])
    major = int(versie.split(".")[0])
    if major >= _MIN_MAJOR_VOOR_STRING_AGG:
        return
    bericht = (
        f"LocalDB-instantie '{_INSTANCE}' draait SQL Server-versie {versie}; "
        f"STRING_AGG vereist major {_MIN_MAJOR_VOOR_STRING_AGG} (SQL Server 2017) "
        "of hoger, net als de productiedatabase MENDRIXDB01."
    )
    if os.environ.get("CI"):
        pytest.fail(bericht)
    pytest.skip(bericht)
