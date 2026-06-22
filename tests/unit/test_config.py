"""Unit tests voor config.py — laad_config() validatie en parsing."""

from unittest.mock import patch

import pytest

from lokalist_weekrapportage.config import DB_DRIVER_DEFAULT, laad_config


@pytest.fixture(autouse=True)
def geen_dotenv():
    with patch("lokalist_weekrapportage.config.load_dotenv"):
        yield


def _basis_env(monkeypatch):
    monkeypatch.setenv("DB_SERVER", "srv")
    monkeypatch.setenv("DB_DATABASE", "db")
    monkeypatch.setenv("DB_AUTH_METHOD", "windows")
    monkeypatch.delenv("DB_DRIVER", raising=False)
    monkeypatch.delenv("WEEK_OFFSET", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_POORT", raising=False)
    monkeypatch.delenv("SMTP_GEBRUIKER", raising=False)
    monkeypatch.delenv("SMTP_WACHTWOORD", raising=False)
    monkeypatch.delenv("SMTP_GEBRUIK_TLS", raising=False)
    monkeypatch.delenv("AFZENDER_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_EMAIL_ONTVANGERS", raising=False)


def test_ontbrekende_verplichte_velden_geeft_runtime_error(monkeypatch):
    monkeypatch.delenv("DB_SERVER", raising=False)
    monkeypatch.delenv("DB_DATABASE", raising=False)
    monkeypatch.delenv("DB_AUTH_METHOD", raising=False)
    with pytest.raises(RuntimeError, match="ontbreken"):
        laad_config()


def test_sql_auth_zonder_credentials_geeft_runtime_error(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.setenv("DB_AUTH_METHOD", "sql")
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="DB_USER"):
        laad_config()


def test_windows_auth_laadt_correct(monkeypatch):
    _basis_env(monkeypatch)
    config = laad_config()
    assert config.db_server == "srv"
    assert config.db_database == "db"
    assert config.db_auth_method == "windows"
    assert config.db_driver == DB_DRIVER_DEFAULT


def test_custom_driver_wordt_geladen(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.setenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    config = laad_config()
    assert config.db_driver == "ODBC Driver 17 for SQL Server"


def test_week_offset_default_is_nul(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.delenv("WEEK_OFFSET", raising=False)
    config = laad_config()
    assert config.week_offset == 0


def test_week_offset_wordt_geparsed(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.setenv("WEEK_OFFSET", "1")
    config = laad_config()
    assert config.week_offset == 1


def test_dry_run_default_is_true(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.delenv("DRY_RUN", raising=False)
    config = laad_config()
    assert config.dry_run is True


def test_dry_run_false_wordt_herkend(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.setenv("DRY_RUN", "false")
    config = laad_config()
    assert config.dry_run is False


def test_smtp_poort_wordt_geparsed(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.setenv("SMTP_POORT", "465")
    config = laad_config()
    assert config.smtp_poort == 465


def test_smtp_poort_leeg_is_none(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.delenv("SMTP_POORT", raising=False)
    config = laad_config()
    assert config.smtp_poort is None


def test_admin_ontvangers_kommagescheiden(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.setenv("ADMIN_EMAIL_ONTVANGERS", "a@x.nl, b@x.nl, c@x.nl")
    config = laad_config()
    assert config.admin_email_ontvangers == ["a@x.nl", "b@x.nl", "c@x.nl"]


def test_admin_ontvangers_leeg_geeft_lege_lijst(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.delenv("ADMIN_EMAIL_ONTVANGERS", raising=False)
    config = laad_config()
    assert config.admin_email_ontvangers == []


def test_lege_smtp_host_is_none(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "")
    config = laad_config()
    assert config.smtp_host is None


def test_smtp_gebruik_tls_default_true(monkeypatch):
    _basis_env(monkeypatch)
    monkeypatch.delenv("SMTP_GEBRUIK_TLS", raising=False)
    config = laad_config()
    assert config.smtp_gebruik_tls is True
