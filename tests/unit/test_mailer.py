"""Unit tests voor mailer.py — verstuur_admin_melding en verstuur_rapport."""

import smtplib
from unittest.mock import MagicMock, mock_open, patch

import pytest

from lokalist_weekrapportage.config import Config
from lokalist_weekrapportage.mailer import verstuur_admin_melding, verstuur_rapport


def _maak_config(**kwargs) -> Config:
    defaults = dict(
        db_server="srv", db_database="db", db_auth_method="windows",
        db_driver="ODBC Driver 17 for SQL Server",
        db_user=None, db_password=None, week_offset=0, dry_run=True,
        smtp_host="smtp.example.com", smtp_poort=587,
        smtp_gebruiker="user@x.nl", smtp_wachtwoord="secret",
        smtp_gebruik_tls=True, afzender_email="noreply@x.nl",
        admin_email_ontvangers=["admin@x.nl"],
    )
    defaults.update(kwargs)
    return Config(**defaults)


def test_geen_ontvangers_logt_warning_en_stuurt_niet(caplog):
    config = _maak_config(admin_email_ontvangers=[])
    with patch("smtplib.SMTP") as mock_smtp:
        verstuur_admin_melding(config, "Test", "bericht")
    mock_smtp.assert_not_called()
    assert "Geen ADMIN_EMAIL_ONTVANGERS" in caplog.text


def test_geen_smtp_host_logt_warning_en_stuurt_niet(caplog):
    config = _maak_config(smtp_host=None)
    with patch("smtplib.SMTP") as mock_smtp:
        verstuur_admin_melding(config, "Test", "bericht")
    mock_smtp.assert_not_called()
    assert "SMTP niet geconfigureerd" in caplog.text


def test_geen_afzender_logt_warning_en_stuurt_niet(caplog):
    config = _maak_config(afzender_email=None)
    with patch("smtplib.SMTP") as mock_smtp:
        verstuur_admin_melding(config, "Test", "bericht")
    mock_smtp.assert_not_called()


def test_verstuurt_mail_via_smtp():
    config = _maak_config()
    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        verstuur_admin_melding(config, "Onderwerp", "Bericht")
    mock_smtp.assert_called_once_with("smtp.example.com", 587)


def test_verstuurt_mail_zonder_tls():
    config = _maak_config(smtp_gebruik_tls=False)
    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        verstuur_admin_melding(config, "Onderwerp", "Bericht")
    mock_server.starttls.assert_not_called()


def test_smtp_fout_wordt_gelogd_niet_gethrowd(caplog):
    config = _maak_config()
    with patch("smtplib.SMTP", side_effect=smtplib.SMTPException("verbinding mislukt")):
        verstuur_admin_melding(config, "Onderwerp", "Bericht")
    assert "Fout bij verzenden" in caplog.text


def test_ontbrekend_logbestand_logt_warning(caplog):
    config = _maak_config()
    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        verstuur_admin_melding(config, "Onderwerp", "Bericht", logbestand="/bestaat/niet.log")
    assert "Logbestand niet gevonden" in caplog.text


def test_bestaand_logbestand_wordt_bijgevoegd(tmp_path):
    logbestand = tmp_path / "test.log"
    logbestand.write_bytes(b"log inhoud")
    config = _maak_config()
    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        verstuur_admin_melding(config, "Onderwerp", "Bericht", logbestand=str(logbestand))
    mock_server.sendmail.assert_called_once()


def test_verstuur_rapport_gooit_not_implemented():
    with pytest.raises(NotImplementedError):
        verstuur_rapport()


def test_smtp_poort_default_587_als_none():
    config = _maak_config(smtp_poort=None)
    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        verstuur_admin_melding(config, "Onderwerp", "Bericht")
    mock_smtp.assert_called_once_with("smtp.example.com", 587)
