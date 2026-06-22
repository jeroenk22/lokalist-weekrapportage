"""Database-koppeling voor de Lokalist staffel-query.

Gebruikt lokalist_staffel_overzicht.sql ONGEWIJZIGD als basis (zie CLAUDE.md —
"Expliciet NIET opnieuw te beslissen"). Alleen de hardcoded @WeekNumber/@Year
DECLARE-regels worden bij het uitvoeren dynamisch vervangen; de queryskelet
zelf wordt niet aangepast.
"""

import os
import re
from datetime import date, timedelta

import pyodbc

from .config import Config

SQL_BESTAND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lokalist_staffel_overzicht.sql")


def bepaal_week(run_datum: date, offset: int = 0) -> tuple[int, int]:
    """Geeft (iso_week, iso_jaar) terug voor run_datum minus offset weken."""
    iso_jaar, iso_week, _ = (run_datum - timedelta(weeks=offset)).isocalendar()
    return iso_week, iso_jaar


def _bouw_connectiestring(config: Config) -> str:
    if config.db_auth_method == "windows":
        return (
            f"DRIVER={{{config.db_driver}}};"
            f"SERVER={config.db_server};DATABASE={config.db_database};"
            f"Trusted_Connection=yes;TrustServerCertificate=yes;"
        )
    return (
        f"DRIVER={{{config.db_driver}}};"
        f"SERVER={config.db_server};DATABASE={config.db_database};"
        f"UID={config.db_user};PWD={config.db_password};"
        f"TrustServerCertificate=yes;"
    )


def _parametriseer_sql(week_nummer: int, jaar: int) -> str:
    with open(SQL_BESTAND, encoding="utf-8") as f:
        sql_tekst = f.read()
    sql_tekst = re.sub(r"DECLARE @WeekNumber INT = \d+;", f"DECLARE @WeekNumber INT = {week_nummer};", sql_tekst)
    sql_tekst = re.sub(r"DECLARE @Year INT = \d+;", f"DECLARE @Year INT = {jaar};", sql_tekst)
    return sql_tekst


def haal_weekdata_op(config: Config, week_nummer: int, jaar: int) -> list[tuple]:
    """Voert de staffel-query uit en zet de resultaten om naar de 11-veld
    rij-vorm die genereer_rapport.genereer_pdf verwacht."""
    sql_tekst = _parametriseer_sql(week_nummer, jaar)
    conn = pyodbc.connect(_bouw_connectiestring(config))
    try:
        cursor = conn.cursor()
        cursor.execute(sql_tekst)
        ruwe_rijen = cursor.fetchall()
    finally:
        conn.close()

    rows: list[tuple] = []
    for r in ruwe_rijen:
        datum_str = r.Datum.strftime("%Y-%m-%d") if hasattr(r.Datum, "strftime") else str(r.Datum)
        rows.append((
            datum_str,
            r.TaskTypeNaam,
            r.LocName,
            r.LocStreet,
            r.LocZip,
            r.LocCity,
            int(r.TotaalColli or 0),
            int(r.AantalTaken or 0),
            r.OrderNummers or "",
            r.Staffeltrede or "",
            float(r.StaffelTarief or 0.0),
        ))
    return rows
