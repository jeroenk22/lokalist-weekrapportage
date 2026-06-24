"""Unit tests voor mailer.py — verstuur_admin_melding en verstuur_rapport."""

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from lokalist_weekrapportage.config import Config
from lokalist_weekrapportage.mailer import (
    _graph_beschikbaar,
    _graph_token,
    _graph_verstuur,
    _laad_html_template,
    verstuur_admin_melding,
    verstuur_rapport,
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
        smtp_host="smtp.example.com",
        smtp_poort=587,
        smtp_gebruiker="user@x.nl",
        smtp_wachtwoord="secret",
        smtp_gebruik_tls=True,
        afzender_email="noreply@x.nl",
        admin_email_ontvangers=["admin@x.nl"],
        email_ontvangers=["klant@x.nl"],
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


def test_smtp_poort_default_587_als_none():
    config = _maak_config(smtp_poort=None)
    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        verstuur_admin_melding(config, "Onderwerp", "Bericht")
    mock_smtp.assert_called_once_with("smtp.example.com", 587)


# --- verstuur_rapport ---


def _smtp_mock():
    mock_server = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_server)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_server, mock_ctx


def test_verstuur_rapport_geen_ontvangers_logt_warning(caplog):
    config = _maak_config(email_ontvangers=[])
    with patch("smtplib.SMTP") as mock_smtp:
        verstuur_rapport(config, "/dummy.pdf", 24, 2026, "periode")
    mock_smtp.assert_not_called()
    assert "Geen EMAIL_ONTVANGERS" in caplog.text


def test_verstuur_rapport_geen_smtp_host_logt_warning(caplog):
    config = _maak_config(smtp_host=None, email_ontvangers=["x@x.nl"])
    with patch("smtplib.SMTP") as mock_smtp:
        verstuur_rapport(config, "/dummy.pdf", 24, 2026, "periode")
    mock_smtp.assert_not_called()
    assert "SMTP niet geconfigureerd" in caplog.text


def test_verstuur_rapport_verstuurt_naar_ontvangers(tmp_path):
    pdf = tmp_path / "rapport.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    config = _maak_config(email_ontvangers=["klant@x.nl"])
    mock_server, mock_ctx = _smtp_mock()
    with patch("smtplib.SMTP", return_value=mock_ctx):
        verstuur_rapport(config, str(pdf), 24, 2026, "8 t/m 14 juni 2026")
    mock_server.sendmail.assert_called_once()
    _, recipients, _ = mock_server.sendmail.call_args[0]
    assert "klant@x.nl" in recipients


def test_verstuur_rapport_ontbrekende_inline_afbeelding_logt_warning(tmp_path, caplog):
    pdf = tmp_path / "rapport.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    config = _maak_config(email_ontvangers=["klant@x.nl"])
    mock_server, mock_ctx = _smtp_mock()
    with (
        patch("smtplib.SMTP", return_value=mock_ctx),
        patch(
            "lokalist_weekrapportage.mailer._RAPPORT_AFBEELDINGEN",
            [("cid1", "/bestaat/niet.png")],
        ),
    ):
        verstuur_rapport(config, str(pdf), 24, 2026, "periode")
    assert "Inline afbeelding niet gevonden" in caplog.text


def test_verstuur_rapport_extra_ontvangers_opgenomen(tmp_path):
    pdf = tmp_path / "rapport.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    config = _maak_config(email_ontvangers=["klant@x.nl"])
    mock_server, mock_ctx = _smtp_mock()
    with patch("smtplib.SMTP", return_value=mock_ctx):
        verstuur_rapport(config, str(pdf), 24, 2026, "periode", extra_ontvangers=["extra@x.nl"])
    _, recipients, _ = mock_server.sendmail.call_args[0]
    assert "klant@x.nl" in recipients
    assert "extra@x.nl" in recipients


def test_verstuur_rapport_smtp_fout_wordt_gegooid(tmp_path):
    pdf = tmp_path / "rapport.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    config = _maak_config(email_ontvangers=["klant@x.nl"])
    with patch("smtplib.SMTP", side_effect=smtplib.SMTPException("fout")):
        with pytest.raises(smtplib.SMTPException):
            verstuur_rapport(config, str(pdf), 24, 2026, "periode")


# --- _laad_html_template ---


def test_laad_html_template_gooit_file_not_found_met_pad():
    with patch("lokalist_weekrapportage.mailer._TEMPLATE_PAD", "/bestaat/niet.html"):
        with pytest.raises(FileNotFoundError, match="E-mail template niet gevonden"):
            _laad_html_template()


# --- _graph_beschikbaar ---


def test_graph_beschikbaar_false_als_credentials_ontbreken():
    config = _maak_config()
    assert _graph_beschikbaar(config) is False


def test_graph_beschikbaar_true_als_credentials_aanwezig():
    config = _maak_config(ms_tenant_id="t", ms_client_id="c", ms_client_secret="s")
    assert _graph_beschikbaar(config) is True


# --- _graph_token ---


def test_graph_token_geeft_access_token():
    config = _maak_config(ms_tenant_id="tenant", ms_client_id="cid", ms_client_secret="sec")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok123"}
    with patch("lokalist_weekrapportage.mailer.requests.post", return_value=mock_resp) as mock_post:
        token = _graph_token(config)
    assert token == "tok123"
    mock_resp.raise_for_status.assert_called_once()
    call_url = mock_post.call_args[0][0]
    assert "tenant" in call_url


def test_graph_token_logt_warning_bij_fout(caplog):
    config = _maak_config(ms_tenant_id="t", ms_client_id="c", ms_client_secret="s")
    with patch(
        "lokalist_weekrapportage.mailer.requests.post",
        side_effect=Exception("netwerk"),
    ):
        with pytest.raises(Exception, match="netwerk"):
            _graph_token(config)
    assert "Graph API token-aanvraag mislukt" in caplog.text


# --- _graph_verstuur ---


def _graph_config():
    return _maak_config(
        ms_tenant_id="t",
        ms_client_id="c",
        ms_client_secret="s",
        ms_sender_email="sender@x.nl",
    )


def test_graph_verstuur_post_naar_sendmail_endpoint():
    config = _graph_config()
    token_resp = MagicMock()
    token_resp.json.return_value = {"access_token": "tok"}
    send_resp = MagicMock()
    with patch(
        "lokalist_weekrapportage.mailer.requests.post",
        side_effect=[token_resp, send_resp],
    ) as mock_post:
        _graph_verstuur(config, "Onderwerp", "Body", "Text", ["a@x.nl"])
    send_call = mock_post.call_args_list[1]
    assert "sendMail" in send_call[0][0]
    assert send_resp.raise_for_status.called


def test_graph_verstuur_bevat_bijlage(tmp_path):
    bijlage = tmp_path / "doc.pdf"
    bijlage.write_bytes(b"%PDF")
    config = _graph_config()
    token_resp = MagicMock()
    token_resp.json.return_value = {"access_token": "tok"}
    send_resp = MagicMock()
    with patch(
        "lokalist_weekrapportage.mailer.requests.post",
        side_effect=[token_resp, send_resp],
    ) as mock_post:
        _graph_verstuur(config, "Sub", "Body", "Text", ["a@x.nl"], [(str(bijlage), None, False)])
    payload = mock_post.call_args_list[1][1]["json"]
    assert len(payload["message"]["attachments"]) == 1
    assert payload["message"]["attachments"][0]["isInline"] is False


def test_graph_verstuur_slaat_ontbrekende_bijlage_over(caplog):
    config = _graph_config()
    token_resp = MagicMock()
    token_resp.json.return_value = {"access_token": "tok"}
    send_resp = MagicMock()
    with patch(
        "lokalist_weekrapportage.mailer.requests.post",
        side_effect=[token_resp, send_resp],
    ) as mock_post:
        _graph_verstuur(
            config, "Sub", "Body", "Text", ["a@x.nl"], [("/bestaat/niet.png", "cid1", True)]
        )
    payload = mock_post.call_args_list[1][1]["json"]
    assert "attachments" not in payload["message"]
    assert "Bijlage niet gevonden" in caplog.text


def test_graph_verstuur_logt_en_gooit_bij_send_fout(caplog):
    config = _graph_config()
    token_resp = MagicMock()
    token_resp.json.return_value = {"access_token": "tok"}
    with patch(
        "lokalist_weekrapportage.mailer.requests.post",
        side_effect=[token_resp, Exception("HTTP 500")],
    ):
        with pytest.raises(Exception, match="HTTP 500"):
            _graph_verstuur(config, "Sub", "Body", "Text", ["a@x.nl"])
    assert "Graph API e-mailverzending mislukt" in caplog.text


# --- verstuur_admin_melding (graph-pad) ---


def test_admin_melding_graph_niet_geconfigureerd_logt_warning(caplog):
    config = _maak_config(email_provider="graph")
    with patch("lokalist_weekrapportage.mailer.requests.post") as mock_post:
        verstuur_admin_melding(config, "Sub", "Body")
    mock_post.assert_not_called()
    assert "Graph API niet geconfigureerd" in caplog.text


def test_admin_melding_graph_verstuurt(caplog):
    import logging

    config = _maak_config(
        email_provider="graph",
        ms_tenant_id="t",
        ms_client_id="c",
        ms_client_secret="s",
        ms_sender_email="sender@x.nl",
    )
    token_resp = MagicMock()
    token_resp.json.return_value = {"access_token": "tok"}
    send_resp = MagicMock()
    with (
        caplog.at_level(logging.INFO),
        patch(
            "lokalist_weekrapportage.mailer.requests.post",
            side_effect=[token_resp, send_resp],
        ),
    ):
        verstuur_admin_melding(config, "Sub", "Body")
    assert "Admin-melding verstuurd" in caplog.text


def test_admin_melding_graph_met_bestaand_logbestand(tmp_path):
    logbestand = tmp_path / "test.log"
    logbestand.write_bytes(b"log")
    config = _maak_config(
        email_provider="graph",
        ms_tenant_id="t",
        ms_client_id="c",
        ms_client_secret="s",
        ms_sender_email="sender@x.nl",
    )
    token_resp = MagicMock()
    token_resp.json.return_value = {"access_token": "tok"}
    send_resp = MagicMock()
    with patch(
        "lokalist_weekrapportage.mailer.requests.post",
        side_effect=[token_resp, send_resp],
    ) as mock_post:
        verstuur_admin_melding(config, "Sub", "Body", logbestand=str(logbestand))
    payload = mock_post.call_args_list[1][1]["json"]
    assert len(payload["message"]["attachments"]) == 1


def test_admin_melding_graph_ontbrekend_logbestand_logt_warning(tmp_path, caplog):
    config = _maak_config(
        email_provider="graph",
        ms_tenant_id="t",
        ms_client_id="c",
        ms_client_secret="s",
        ms_sender_email="sender@x.nl",
    )
    token_resp = MagicMock()
    token_resp.json.return_value = {"access_token": "tok"}
    send_resp = MagicMock()
    with patch(
        "lokalist_weekrapportage.mailer.requests.post",
        side_effect=[token_resp, send_resp],
    ):
        verstuur_admin_melding(config, "Sub", "Body", logbestand="/bestaat/niet.log")
    assert "Logbestand niet gevonden" in caplog.text


# --- verstuur_rapport (graph-pad) ---


def test_verstuur_rapport_graph_niet_geconfigureerd_logt_warning(caplog):
    config = _maak_config(email_provider="graph")
    with patch("lokalist_weekrapportage.mailer.requests.post") as mock_post:
        verstuur_rapport(config, "/dummy.pdf", 24, 2026, "periode")
    mock_post.assert_not_called()
    assert "Graph API niet geconfigureerd" in caplog.text


def test_verstuur_rapport_graph_verstuurt(tmp_path, caplog):
    import logging

    pdf = tmp_path / "rapport.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    config = _maak_config(
        email_provider="graph",
        email_ontvangers=["klant@x.nl"],
        ms_tenant_id="t",
        ms_client_id="c",
        ms_client_secret="s",
        ms_sender_email="sender@x.nl",
    )
    token_resp = MagicMock()
    token_resp.json.return_value = {"access_token": "tok"}
    send_resp = MagicMock()
    with (
        caplog.at_level(logging.INFO),
        patch(
            "lokalist_weekrapportage.mailer.requests.post",
            side_effect=[token_resp, send_resp],
        ),
    ):
        verstuur_rapport(config, str(pdf), 24, 2026, "periode")
    assert "Rapport verstuurd" in caplog.text
