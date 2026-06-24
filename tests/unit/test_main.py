"""Unit tests voor main.py — _setup_logging, _flush_logs en main()."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from lokalist_weekrapportage.config import Config
from lokalist_weekrapportage.main import _flush_logs, _setup_logging, main


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


def _spoed_rij(order_id=9001):
    return (
        "2026-06-09",
        str(order_id),
        "Van Naam",
        "Straat 1",
        "Naar Naam",
        "Straat 2",
        1,
        55.0,
    )


def _week_rij():
    return (
        "2026-06-09",
        "Laden",
        "Loc",
        "Straat 1",
        "1234AB",
        "Stad",
        5,
        1,
        "1001",
        "A",
        10.0,
    )


# --- _setup_logging ---


def test_setup_logging_maakt_logbestand_met_datum(tmp_path):
    with patch("lokalist_weekrapportage.main.LOG_DIR", str(tmp_path)), patch("logging.basicConfig"):
        pad = _setup_logging()
    assert "lokalist_" in pad
    assert pad.endswith(".log")


def test_setup_logging_maakt_log_dir_aan(tmp_path):
    log_dir = tmp_path / "logs"
    with patch("lokalist_weekrapportage.main.LOG_DIR", str(log_dir)), patch("logging.basicConfig"):
        _setup_logging()
    assert log_dir.exists()


# --- _flush_logs ---


def test_flush_logs_flusht_alle_handlers():
    handler = MagicMock(spec=logging.Handler)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        _flush_logs()
    finally:
        root.removeHandler(handler)
    handler.flush.assert_called()


# --- main() ---


def _mock_main(
    config=None,
    spoed_rows=None,
    week_rows=None,
    pdf_result=None,
    logbestand="/tmp/test.log",
):
    """Geeft een dict van patches terug voor gebruik in with-blocks."""
    return {
        "_setup_logging": patch(
            "lokalist_weekrapportage.main._setup_logging", return_value=logbestand
        ),
        "laad_config": patch(
            "lokalist_weekrapportage.main.laad_config",
            return_value=config or _maak_config(),
        ),
        "haal_spoeddata_op": patch(
            "lokalist_weekrapportage.main.haal_spoeddata_op",
            return_value=spoed_rows if spoed_rows is not None else [],
        ),
        "haal_weekdata_op": patch(
            "lokalist_weekrapportage.main.haal_weekdata_op",
            return_value=week_rows if week_rows is not None else [_week_rij()],
        ),
        "genereer_pdf": patch(
            "lokalist_weekrapportage.main.genereer_pdf",
            return_value=(pdf_result or "/tmp/rapport.pdf", {"laden": 1}),
        ),
        "verstuur_admin_melding": patch("lokalist_weekrapportage.main.verstuur_admin_melding"),
        "os.makedirs": patch("os.makedirs"),
    }


def test_main_happy_path_genereert_pdf():
    patches = _mock_main()
    with (
        patches["_setup_logging"],
        patches["laad_config"],
        patches["haal_spoeddata_op"],
        patches["haal_weekdata_op"],
        patches["genereer_pdf"] as mock_pdf,
        patches["verstuur_admin_melding"],
        patches["os.makedirs"],
    ):
        main()
    mock_pdf.assert_called_once()


def test_main_geen_orders_stuurt_admin_melding():
    patches = _mock_main(week_rows=[])
    with (
        patches["_setup_logging"],
        patches["laad_config"],
        patches["haal_spoeddata_op"],
        patches["haal_weekdata_op"],
        patches["genereer_pdf"] as mock_pdf,
        patches["verstuur_admin_melding"] as mock_admin,
        patches["os.makedirs"],
    ):
        main()
    mock_pdf.assert_not_called()
    mock_admin.assert_called_once()
    onderwerp = mock_admin.call_args[1]["onderwerp"]
    assert "Geen orders" in onderwerp


def test_main_exception_stuurt_admin_melding_en_gooit():
    patches = _mock_main()
    with (
        patches["_setup_logging"],
        patches["laad_config"],
        patch(
            "lokalist_weekrapportage.main.haal_spoeddata_op",
            side_effect=Exception("DB kapot"),
        ),
        patches["verstuur_admin_melding"] as mock_admin,
        patches["os.makedirs"],
    ):
        with pytest.raises(Exception, match="DB kapot"):
            main()
    mock_admin.assert_called_once()
    onderwerp = mock_admin.call_args[1]["onderwerp"]
    assert "FOUT" in onderwerp


def test_main_dry_run_false_logt_warning(caplog):
    patches = _mock_main(config=_maak_config(dry_run=False))
    with caplog.at_level(logging.WARNING):
        with (
            patches["_setup_logging"],
            patches["laad_config"],
            patches["haal_spoeddata_op"],
            patches["haal_weekdata_op"],
            patches["genereer_pdf"],
            patches["verstuur_admin_melding"],
            patches["os.makedirs"],
        ):
            main()
    assert "DRY_RUN=false" in caplog.text


def test_main_geeft_spoed_ids_door_aan_weekquery():
    patches = _mock_main(spoed_rows=[_spoed_rij(9001)])
    with (
        patches["_setup_logging"],
        patches["laad_config"],
        patches["haal_spoeddata_op"],
        patches["haal_weekdata_op"] as mock_week,
        patches["genereer_pdf"],
        patches["verstuur_admin_melding"],
        patches["os.makedirs"],
    ):
        main()
    _, kwargs = mock_week.call_args
    assert kwargs.get("spoed_order_ids") == [9001]
