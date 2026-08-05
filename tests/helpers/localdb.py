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
