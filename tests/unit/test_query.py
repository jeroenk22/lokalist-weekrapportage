"""Unit tests voor query.py — bepaal_week, connectiestring, SQL-parametrisering."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from lokalist_weekrapportage.config import Config
from lokalist_weekrapportage.query import (
    _bouw_connectiestring,
    _parametriseer_sql,
    _vervang_spoed_filter,
    bepaal_week,
    haal_spoeddata_op,
    haal_weekdata_op,
)


def _maak_config(**kwargs) -> Config:
    defaults = dict(
        db_server="srv",
        db_database="db",
        db_auth_method="windows",
        db_driver="ODBC Driver 17 for SQL Server",
        db_user=None,
        db_password=None,
        week_offset=0,
        dry_run=True,
        smtp_host=None,
        smtp_poort=None,
        smtp_gebruiker=None,
        smtp_wachtwoord=None,
        smtp_gebruik_tls=True,
        afzender_email=None,
        admin_email_ontvangers=[],
        email_ontvangers=[],
        email_cc=[],
        email_bcc=[],
        email_provider="smtp",
        ms_tenant_id=None,
        ms_client_id=None,
        ms_client_secret=None,
        ms_sender_email=None,
    )
    defaults.update(kwargs)
    return Config(**defaults)


# --- bepaal_week ---


def test_bepaal_week_geeft_juiste_iso_week():
    # 2026-06-08 = maandag week 24
    week, jaar = bepaal_week(date(2026, 6, 8))
    assert week == 24
    assert jaar == 2026


def test_bepaal_week_met_offset_een():
    # week 24 minus 1 = week 23
    week, jaar = bepaal_week(date(2026, 6, 8), offset=1)
    assert week == 23
    assert jaar == 2026


def test_bepaal_week_jaargrens():
    # 2025-12-29 = week 1 van 2026
    week, jaar = bepaal_week(date(2025, 12, 29))
    assert week == 1
    assert jaar == 2026


def test_bepaal_week_laatste_week_van_jaar():
    # 2026-12-28 = week 53 van 2026
    week, jaar = bepaal_week(date(2026, 12, 28))
    assert week == 53
    assert jaar == 2026


# --- _bouw_connectiestring ---


def test_connectiestring_windows():
    config = _maak_config(db_auth_method="windows", db_driver="ODBC Driver 17 for SQL Server")
    cs = _bouw_connectiestring(config)
    assert "Trusted_Connection=yes" in cs
    assert "ODBC Driver 17 for SQL Server" in cs
    assert "UID" not in cs


def test_connectiestring_sql():
    config = _maak_config(
        db_auth_method="sql",
        db_driver="ODBC Driver 17 for SQL Server",
        db_user="user",
        db_password="pass",
    )
    cs = _bouw_connectiestring(config)
    assert "UID=user" in cs
    assert "PWD=pass" in cs
    assert "Trusted_Connection" not in cs


# --- _parametriseer_sql ---


def test_parametriseer_sql_vervangt_week_en_jaar():
    sql = _parametriseer_sql(24, 2026)
    assert "DECLARE @WeekNumber INT = 24;" in sql
    assert "DECLARE @Year INT = 2026;" in sql


def test_parametriseer_sql_overschrijft_originele_waarden():
    sql1 = _parametriseer_sql(1, 2020)
    sql2 = _parametriseer_sql(52, 2025)
    assert "DECLARE @WeekNumber INT = 1;" in sql1
    assert "DECLARE @WeekNumber INT = 52;" in sql2
    assert "DECLARE @Year INT = 2020;" in sql1
    assert "DECLARE @Year INT = 2025;" in sql2


# --- haal_weekdata_op (pyodbc gemockt) ---


def _maak_rij(
    datum="2026-06-08",
    type_naam="Laden",
    loc_name="Boer",
    street="Weg 1",
    zip_code="1234AB",
    city="Stad",
    colli=5,
    taken=1,
    orders="123",
    trede="1 tot 4",
    tarief=15.39,
):
    rij = MagicMock()
    rij.Datum = date.fromisoformat(datum)
    rij.TaskTypeNaam = type_naam
    rij.LocName = loc_name
    rij.LocStreet = street
    rij.LocZip = zip_code
    rij.LocCity = city
    rij.TotaalColli = colli
    rij.AantalTaken = taken
    rij.OrderNummers = orders
    rij.Staffeltrede = trede
    rij.StaffelTarief = tarief
    return rij


@patch("lokalist_weekrapportage.query.pyodbc.connect")
def test_haal_weekdata_op_geeft_genormaliseerde_rijen(mock_connect):
    ruwe_rij = _maak_rij()
    cursor = MagicMock()
    cursor.fetchall.return_value = [ruwe_rij]
    mock_connect.return_value.__enter__ = MagicMock(
        return_value=MagicMock(cursor=MagicMock(return_value=cursor))
    )
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_connect.return_value = conn

    config = _maak_config()
    rows = haal_weekdata_op(config, 24, 2026)

    assert len(rows) == 1
    rij = rows[0]
    assert rij[0] == "2026-06-08"
    assert rij[1] == "Laden"
    assert rij[6] == 5
    assert rij[10] == 15.39


@patch("lokalist_weekrapportage.query.pyodbc.connect")
def test_haal_weekdata_op_geeft_lege_lijst_bij_geen_rijen(mock_connect):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_connect.return_value = conn

    config = _maak_config()
    rows = haal_weekdata_op(config, 24, 2026)
    assert rows == []


@patch("lokalist_weekrapportage.query.pyodbc.connect")
def test_haal_weekdata_op_sluit_verbinding_bij_fout(mock_connect):
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("DB fout")
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_connect.return_value = conn

    config = _maak_config()
    with pytest.raises(Exception, match="DB fout"):
        haal_weekdata_op(config, 24, 2026)

    conn.close.assert_called_once()


# --- _vervang_spoed_filter ---


def test_vervang_spoed_filter_zonder_ids_geeft_and_1_is_1():
    sql = "SELECT 1 WHERE AND 1=1 -- <<SPOED_IDS_FILTER>>"
    result = _vervang_spoed_filter(sql, [])
    assert "AND 1=1" in result
    assert "<<SPOED_IDS_FILTER>>" not in result


def test_vervang_spoed_filter_met_ids_geeft_not_in():
    sql = "SELECT 1 WHERE AND 1=1 -- <<SPOED_IDS_FILTER>>"
    result = _vervang_spoed_filter(sql, [101, 202])
    assert "NOT IN (101,202)" in result
    assert "<<SPOED_IDS_FILTER>>" not in result


# --- haal_spoeddata_op ---


def _maak_spoed_rij(order_id=9999, colli=2, tarief=55.0):
    from datetime import date

    r = MagicMock()
    r.Datum = date(2026, 6, 9)
    r.OrderId = order_id
    r.VanNaam = "Van Loc"
    r.VanAdres = "Straat 1"
    r.NaarNaam = "Naar Loc"
    r.NaarAdres = "Straat 2"
    r.TotaalColli = colli
    r.SpoedTarief = tarief
    return r


@patch("lokalist_weekrapportage.query.pyodbc.connect")
def test_haal_spoeddata_op_geeft_genormaliseerde_rijen(mock_connect):
    ruwe_rij = _maak_spoed_rij()
    cursor = MagicMock()
    cursor.fetchall.return_value = [ruwe_rij]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_connect.return_value = conn

    config = _maak_config()
    rows = haal_spoeddata_op(config, 24, 2026)

    assert len(rows) == 1
    assert rows[0][0] == "2026-06-09"
    assert rows[0][1] == "9999"
    assert rows[0][6] == 2
    assert rows[0][7] == 55.0


@patch("lokalist_weekrapportage.query.pyodbc.connect")
def test_haal_spoeddata_op_sluit_verbinding_bij_fout(mock_connect):
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("DB fout")
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_connect.return_value = conn

    config = _maak_config()
    with pytest.raises(Exception, match="DB fout"):
        haal_spoeddata_op(config, 24, 2026)

    conn.close.assert_called_once()
