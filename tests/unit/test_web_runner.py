"""Tests voor de orkestratie van het webdashboard.

Zwaartepunt ligt op de volgorde en het vangnet: er mag nooit een verzamelorder
verdwijnen doordat een run halverwege faalt.
"""

import dataclasses
import importlib.util
import json
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from lokalist_weekrapportage.verzamelorder_query import Verzamelorder

_SCRIPT_PAD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "web_runner.py",
)


@pytest.fixture(scope="module")
def runner():
    spec = importlib.util.spec_from_file_location("_web_runner", _SCRIPT_PAD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def config():
    """Config-dubbel met dezelfde velden als de echte dataclass."""
    from lokalist_weekrapportage.config import Config

    return Config(
        db_server="server",
        db_database="db",
        db_auth_method="windows",
        db_driver="driver",
        db_user=None,
        db_password=None,
        week_offset=0,
        dry_run=False,
        smtp_host="smtp",
        smtp_poort=587,
        smtp_gebruiker="u",
        smtp_wachtwoord="w",
        smtp_gebruik_tls=True,
        afzender_email="afzender@voorbeeld.nl",
        admin_email_ontvangers=["admin@voorbeeld.nl"],
        email_ontvangers=["info@lokalist.nl"],
        email_cc=["cc@voorbeeld.nl"],
        email_bcc=["bcc@voorbeeld.nl"],
        email_provider="smtp",
        ms_tenant_id=None,
        ms_client_id=None,
        ms_client_secret=None,
        ms_sender_email=None,
    )


ORDER = Verzamelorder(
    order_id=1266289,
    aangemaakt=datetime(2026, 8, 2, 23, 30, 4),
    weeknummer=31,
    jaar=2026,
    handmatig=False,
    notities="",
    totaal_colli=32,
    totaal_bedrag=238.13,
)

RIJEN = [("2026-08-01", "Laden", "A", "S", "1234AB", "Plaats", 10, 1, "111", "1-20", 25.0)]

# Standaardselectie zoals de modal die opstuurt.
EMAIL = {"to": ["info@lokalist.nl"], "cc": ["cc@voorbeeld.nl"], "bcc": []}
NAAM = "Jeroen"


class TestConfigMetEmail:
    def test_vervangt_de_adressen_uit_env(self, runner, config):
        nieuw = runner._config_met_email(
            config, {"to": ["jeroen@prive.nl"], "cc": [], "bcc": ["stil@voorbeeld.nl"]}
        )

        assert nieuw.email_ontvangers == ["jeroen@prive.nl"]
        assert nieuw.email_cc == []
        assert nieuw.email_bcc == ["stil@voorbeeld.nl"]

    def test_laat_de_overige_configuratie_ongemoeid(self, runner, config):
        nieuw = runner._config_met_email(config, {"to": ["a@b.nl"]})

        assert nieuw.smtp_host == config.smtp_host
        assert nieuw.afzender_email == config.afzender_email
        assert nieuw.db_server == config.db_server

    def test_negeert_lege_en_witruimte_adressen(self, runner, config):
        nieuw = runner._config_met_email(
            config, {"to": ["  a@b.nl  ", "", "   "], "cc": [], "bcc": []}
        )
        assert nieuw.email_ontvangers == ["a@b.nl"]

    def test_origineel_blijft_onaangetast(self, runner, config):
        runner._config_met_email(config, {"to": ["ander@adres.nl"]})
        assert config.email_ontvangers == ["info@lokalist.nl"]


class TestZoekVerzamelorder:
    def test_vindt_de_order(self, runner, config):
        with patch.object(runner, "haal_verzamelorders_op", return_value=[ORDER]):
            assert runner._zoek_verzamelorder(config, 1266289) is ORDER

    def test_onbekende_order_geeft_begrijpelijke_melding(self, runner, config):
        with patch.object(runner, "haal_verzamelorders_op", return_value=[ORDER]):
            with pytest.raises(ValueError, match="niet gevonden"):
                runner._zoek_verzamelorder(config, 999)


class TestOpdrachtLijst:
    def test_geeft_orders_en_email_instellingen(self, runner, config):
        with patch.object(runner, "haal_verzamelorders_op", return_value=[ORDER]):
            resultaat = runner._opdracht_lijst(config)

        assert resultaat["verzamelorders"][0]["orderId"] == 1266289
        assert resultaat["verzamelorders"][0]["label"] == "zondag 02 augustus 2026 (automatisch)"
        assert resultaat["email"]["to"] == ["info@lokalist.nl"]
        assert resultaat["email"]["bcc"] == ["bcc@voorbeeld.nl"]


class TestStandaardUitgevinkt:
    """Adressen die zichtbaar zijn maar niet vooraf aangevinkt staan."""

    def _lijst(self, runner, config, waarde):
        with patch.dict(os.environ, {"DASHBOARD_EMAIL_UITGEVINKT": waarde}, clear=False):
            with patch.object(runner, "haal_verzamelorders_op", return_value=[ORDER]):
                return runner._opdracht_lijst(config)

    def test_leeg_betekent_alles_aangevinkt(self, runner, config):
        assert self._lijst(runner, config, "")["email"]["uitgevinkt"] == []

    def test_geeft_de_adressen_door(self, runner, config):
        resultaat = self._lijst(runner, config, "johannes@lokalist.nl")
        assert resultaat["email"]["uitgevinkt"] == ["johannes@lokalist.nl"]

    def test_meerdere_adressen_kommagescheiden(self, runner, config):
        resultaat = self._lijst(runner, config, "a@b.nl, c@d.nl ,, e@f.nl")
        assert resultaat["email"]["uitgevinkt"] == ["a@b.nl", "c@d.nl", "e@f.nl"]

    def test_laat_de_gewone_cc_lijst_ongemoeid(self, runner, config):
        """Het adres blijft in CC staan; alleen het vinkje gaat eraf."""
        resultaat = self._lijst(runner, config, "cc@voorbeeld.nl")
        assert resultaat["email"]["cc"] == ["cc@voorbeeld.nl"]
        assert resultaat["email"]["uitgevinkt"] == ["cc@voorbeeld.nl"]


@pytest.fixture
def geslaagde_keten(runner, tmp_path):
    """Patcht de volledige keten zodat een run zonder externe systemen slaagt."""
    with (
        patch.object(runner, "haal_verzamelorders_op", return_value=[ORDER]),
        patch.object(runner, "haal_spoeddata_op", return_value=[]),
        patch.object(runner, "haal_weekdata_op", return_value=RIJEN),
        patch.object(
            runner, "genereer_pdf", return_value=(str(tmp_path / "rapport.pdf"), {"totaal": 25.0})
        ),
        patch.object(runner, "stuur_soap", return_value="<respons/>"),
        patch.object(runner, "extraheer_order_id", return_value=1266400),
        patch.object(runner, "haal_order_xml_op", return_value="<order/>"),
        patch.object(runner, "rest_login", return_value="jwt"),
        patch.object(runner, "upload_bestand_naar_dossier") as upload,
        patch.object(runner, "verstuur_rapport") as mail,
        patch.object(runner, "verwijder_order") as verwijder,
        patch.object(runner, "OUTPUT_DIR", str(tmp_path)),
        patch.dict(
            os.environ,
            {
                "MENDRIX_SOAP_URL": "https://soap",
                "MENDRIX_SOAP_USER": "u",
                "MENDRIX_SOAP_PASS": "w",
                "MENDRIX_API_URL": "https://api/",
                "MENDRIX_API_TOKEN": "token",
                # Expliciet leeg: de allowlist hoort deze tests niet te sturen.
                "DASHBOARD_EMAIL_DOMEINEN": "",
            },
        ),
    ):
        (tmp_path / "rapport.pdf").write_bytes(b"%PDF-1.4 test")
        yield {"upload": upload, "mail": mail, "verwijder": verwijder}


class TestRegenereerGeslaagd:
    def test_maakt_nieuw_aan_en_verwijdert_daarna_het_oude(self, runner, config, geslaagde_keten):
        resultaat = runner._opdracht_regenereer(
            config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM}
        )

        assert resultaat["nieuweOrderId"] == 1266400
        assert resultaat["oudeOrderId"] == 1266289
        # Alleen de OUDE order wordt verwijderd, en precies één keer.
        geslaagde_keten["verwijder"].assert_called_once()
        assert geslaagde_keten["verwijder"].call_args[0][3] == 1266289

    def test_notitie_markeert_de_run_als_handmatig(self, runner, config, geslaagde_keten):
        resultaat = runner._opdracht_regenereer(
            config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM}
        )

        assert resultaat["notitie"].startswith("[HANDMATIG HERGENEREERD | door Jeroen]")
        assert "Week 31 2026" in resultaat["notitie"]
        # Het vervangen ordernummer hoort in de notitie te staan.
        assert "Vorige verzamelorder 1266289 verwijderd" in resultaat["notitie"]

    def test_uploadt_zowel_pdf_als_ordernummers(self, runner, config, geslaagde_keten):
        runner._opdracht_regenereer(config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM})

        namen = [aanroep[0][4] for aanroep in geslaagde_keten["upload"].call_args_list]
        assert namen == [
            "lokalist_week31_2026.pdf",
            "lokalist_week31_2026_ordernummers.txt",
        ]

    def test_gebruikt_de_adressen_uit_het_dashboard(self, runner, config, geslaagde_keten):
        runner._opdracht_regenereer(
            config,
            {
                "orderId": 1266289,
                "email": {"to": ["jeroen@prive.nl"], "cc": [], "bcc": []},
                "naam": NAAM,
            },
        )

        meegegeven = geslaagde_keten["mail"].call_args.kwargs["config"]
        assert meegegeven.email_ontvangers == ["jeroen@prive.nl"]
        assert meegegeven.email_cc == []


class TestRegenereerDryRun:
    def test_raakt_mendrix_niet_aan(self, runner, config, geslaagde_keten):
        resultaat = runner._opdracht_regenereer(
            config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM, "dryRun": True}
        )

        assert resultaat["dryRun"] is True
        geslaagde_keten["verwijder"].assert_not_called()
        geslaagde_keten["mail"].assert_not_called()
        geslaagde_keten["upload"].assert_not_called()


class TestFactuurGrendel:
    """Server-side grendel: de UI is geen beveiliging."""

    def _gefactureerd(self):
        return dataclasses.replace(ORDER, factuur_sleutel=154055, factuur_nummer=31511432)

    def test_gefactureerde_order_wordt_geweigerd(self, runner, config, geslaagde_keten):
        with patch.object(runner, "haal_verzamelorders_op", return_value=[self._gefactureerd()]):
            with pytest.raises(ValueError, match="staat op een factuur 31511432"):
                runner._opdracht_regenereer(
                    config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM}
                )

    def test_er_wordt_niets_aangemaakt_of_verwijderd(self, runner, config, geslaagde_keten):
        with patch.object(runner, "haal_verzamelorders_op", return_value=[self._gefactureerd()]):
            with pytest.raises(ValueError):
                runner._opdracht_regenereer(
                    config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM}
                )

        geslaagde_keten["verwijder"].assert_not_called()
        geslaagde_keten["mail"].assert_not_called()
        geslaagde_keten["upload"].assert_not_called()

    def test_voorlopige_factuur_blokkeert_ook(self, runner, config, geslaagde_keten):
        """Zonder definitief nummer blijft de order net zo goed vergrendeld."""
        concept = dataclasses.replace(ORDER, factuur_sleutel=154793, factuur_nummer=None)
        with patch.object(runner, "haal_verzamelorders_op", return_value=[concept]):
            with pytest.raises(ValueError, match="voorlopige factuur 154793"):
                runner._opdracht_regenereer(
                    config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM}
                )
        geslaagde_keten["verwijder"].assert_not_called()

    def test_grendel_geldt_ook_bij_dry_run(self, runner, config, geslaagde_keten):
        with patch.object(runner, "haal_verzamelorders_op", return_value=[self._gefactureerd()]):
            with pytest.raises(ValueError, match="staat op een factuur"):
                runner._opdracht_regenereer(
                    config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM, "dryRun": True}
                )

    def test_ongefactureerde_order_mag_gewoon(self, runner, config, geslaagde_keten):
        resultaat = runner._opdracht_regenereer(
            config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM}
        )
        assert resultaat["nieuweOrderId"] == 1266400


class TestNaamVerplicht:
    """Zonder naam mag er niets gebeuren — de naam gaat de order in."""

    @pytest.mark.parametrize("ontbrekend", [None, "", "   ", "\t\n"])
    def test_zonder_naam_stopt_alles(self, runner, config, geslaagde_keten, ontbrekend):
        opdracht = {"orderId": 1266289, "email": EMAIL}
        if ontbrekend is not None:
            opdracht["naam"] = ontbrekend

        with pytest.raises(ValueError, match="Vul in wie het rapport opnieuw genereert"):
            runner._opdracht_regenereer(config, opdracht)

        geslaagde_keten["verwijder"].assert_not_called()
        geslaagde_keten["mail"].assert_not_called()

    def test_naam_komt_in_de_notitie(self, runner, config, geslaagde_keten):
        resultaat = runner._opdracht_regenereer(
            config, {"orderId": 1266289, "email": EMAIL, "naam": "Jeroen"}
        )
        assert resultaat["notitie"].startswith("[HANDMATIG HERGENEREERD | door Jeroen]")
        assert resultaat["naam"] == "Jeroen"

    def test_overtollige_spaties_worden_opgeruimd(self, runner, config, geslaagde_keten):
        resultaat = runner._opdracht_regenereer(
            config, {"orderId": 1266289, "email": EMAIL, "naam": "  Jan   Pieter  "}
        )
        assert resultaat["naam"] == "Jan Pieter"
        assert "| door Jan Pieter]" in resultaat["notitie"]


class TestNaamMaxlengte:
    """Python bewaakt de lengte zelf; de maxLength in de browser is geen grens."""

    def test_te_lange_naam_wordt_geweigerd(self, runner, config, geslaagde_keten):
        from lokalist_weekrapportage.verzamelorder import NAAM_MAXLENGTE

        with pytest.raises(ValueError, match=f"maximaal {NAAM_MAXLENGTE} tekens"):
            runner._opdracht_regenereer(
                config,
                {"orderId": 1266289, "email": EMAIL, "naam": "A" * (NAAM_MAXLENGTE + 1)},
            )

        geslaagde_keten["verwijder"].assert_not_called()
        geslaagde_keten["mail"].assert_not_called()

    def test_precies_de_maximale_lengte_mag(self, runner, config, geslaagde_keten):
        from lokalist_weekrapportage.verzamelorder import NAAM_MAXLENGTE

        resultaat = runner._opdracht_regenereer(
            config, {"orderId": 1266289, "email": EMAIL, "naam": "A" * NAAM_MAXLENGTE}
        )
        assert resultaat["naam"] == "A" * NAAM_MAXLENGTE

    def test_lengte_wordt_na_het_opschonen_gemeten(self, runner, config, geslaagde_keten):
        """Spaties eromheen mogen een geldige naam niet over de grens duwen."""
        from lokalist_weekrapportage.verzamelorder import NAAM_MAXLENGTE

        resultaat = runner._opdracht_regenereer(
            config,
            {"orderId": 1266289, "email": EMAIL, "naam": "  " + "A" * NAAM_MAXLENGTE + "  "},
        )
        assert resultaat["naam"] == "A" * NAAM_MAXLENGTE


class TestDomeinAllowlist:
    """Server-side grendel op de ontvangers: de browser is geen beveiliging."""

    def _regenereer(self, runner, config, domeinen, email):
        with patch.dict(os.environ, {"DASHBOARD_EMAIL_DOMEINEN": domeinen}, clear=False):
            return runner._opdracht_regenereer(
                config, {"orderId": 1266289, "email": email, "naam": NAAM}
            )

    def test_adres_buiten_de_allowlist_wordt_geweigerd(self, runner, config, geslaagde_keten):
        with pytest.raises(ValueError, match="jeroen@prive.nl"):
            self._regenereer(
                runner, config, "lokalist.nl", {"to": ["jeroen@prive.nl"], "cc": [], "bcc": []}
            )

        geslaagde_keten["verwijder"].assert_not_called()
        geslaagde_keten["mail"].assert_not_called()

    def test_er_wordt_niets_aangemaakt_voordat_de_adressen_kloppen(
        self, runner, config, geslaagde_keten
    ):
        with pytest.raises(ValueError):
            self._regenereer(
                runner, config, "lokalist.nl", {"to": ["jeroen@prive.nl"], "cc": [], "bcc": []}
            )

        geslaagde_keten["upload"].assert_not_called()

    @pytest.mark.parametrize("veld", ["to", "cc", "bcc"])
    def test_geldt_voor_alle_drie_de_velden(self, runner, config, geslaagde_keten, veld):
        email = {"to": ["info@lokalist.nl"], "cc": [], "bcc": []}
        email[veld] = [*email.get(veld, []), "extern@voorbeeld.com"]

        with pytest.raises(ValueError, match="extern@voorbeeld.com"):
            self._regenereer(runner, config, "lokalist.nl", email)

    def test_adres_binnen_de_allowlist_mag(self, runner, config, geslaagde_keten):
        resultaat = self._regenereer(
            runner, config, "lokalist.nl", {"to": ["nieuw@lokalist.nl"], "cc": [], "bcc": []}
        )
        assert resultaat["nieuweOrderId"] == 1266400

    def test_bestaande_env_ontvangers_mogen_altijd(self, runner, config, geslaagde_keten):
        """Een krappe allowlist mag de gewone ontvangers niet blokkeren."""
        resultaat = self._regenereer(
            runner,
            config,
            "ophaaldienstmiedema.nl",
            {"to": ["info@lokalist.nl"], "cc": ["cc@voorbeeld.nl"], "bcc": ["bcc@voorbeeld.nl"]},
        )
        assert resultaat["nieuweOrderId"] == 1266400

    def test_lege_allowlist_laat_alles_door(self, runner, config, geslaagde_keten):
        resultaat = self._regenereer(
            runner, config, "", {"to": ["wie.dan.ook@internet.com"], "cc": [], "bcc": []}
        )
        assert resultaat["nieuweOrderId"] == 1266400

    def test_melding_noemt_de_toegestane_domeinen(self, runner, config, geslaagde_keten):
        with pytest.raises(ValueError, match="@lokalist.nl"):
            self._regenereer(
                runner, config, "lokalist.nl", {"to": ["jeroen@prive.nl"], "cc": [], "bcc": []}
            )

    def test_grendel_geldt_ook_bij_dry_run(self, runner, config, geslaagde_keten):
        with patch.dict(os.environ, {"DASHBOARD_EMAIL_DOMEINEN": "lokalist.nl"}, clear=False):
            with pytest.raises(ValueError, match="jeroen@prive.nl"):
                runner._opdracht_regenereer(
                    config,
                    {
                        "orderId": 1266289,
                        "email": {"to": ["jeroen@prive.nl"], "cc": [], "bcc": []},
                        "naam": NAAM,
                        "dryRun": True,
                    },
                )

    def test_lijst_geeft_de_domeinen_door_aan_de_ui(self, runner, config):
        with patch.dict(
            os.environ, {"DASHBOARD_EMAIL_DOMEINEN": "lokalist.nl, @Miedema.nl"}, clear=False
        ):
            with patch.object(runner, "haal_verzamelorders_op", return_value=[ORDER]):
                resultaat = runner._opdracht_lijst(config)

        assert resultaat["email"]["domeinen"] == ["lokalist.nl", "miedema.nl"]

    def test_lijst_zonder_allowlist_geeft_een_lege_lijst(self, runner, config):
        with patch.dict(os.environ, {"DASHBOARD_EMAIL_DOMEINEN": ""}, clear=False):
            with patch.object(runner, "haal_verzamelorders_op", return_value=[ORDER]):
                resultaat = runner._opdracht_lijst(config)

        assert resultaat["email"]["domeinen"] == []


class TestRegenereerVangnet:
    """Het kernrisico: er mag nooit een order verloren gaan."""

    def test_mislukte_upload_draait_de_nieuwe_order_terug(self, runner, config, geslaagde_keten):
        geslaagde_keten["upload"].side_effect = RuntimeError("dossier onbereikbaar")

        with pytest.raises(RuntimeError, match="dossier onbereikbaar"):
            runner._opdracht_regenereer(config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM})

        # De NIEUWE order wordt opgeruimd; de oude blijft staan.
        geslaagde_keten["verwijder"].assert_called_once()
        assert geslaagde_keten["verwijder"].call_args[0][3] == 1266400

    def test_mislukte_mail_draait_de_nieuwe_order_terug(self, runner, config, geslaagde_keten):
        geslaagde_keten["mail"].side_effect = RuntimeError("SMTP weigert")

        with pytest.raises(RuntimeError, match="SMTP weigert"):
            runner._opdracht_regenereer(config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM})

        geslaagde_keten["verwijder"].assert_called_once()
        assert geslaagde_keten["verwijder"].call_args[0][3] == 1266400

    def test_mislukt_terugdraaien_blijft_een_fout_geven(self, runner, config, geslaagde_keten):
        geslaagde_keten["mail"].side_effect = RuntimeError("SMTP weigert")
        geslaagde_keten["verwijder"].side_effect = RuntimeError("SOAP ook stuk")

        # De oorspronkelijke fout blijft leidend, ook als opruimen niet lukt.
        with pytest.raises(RuntimeError):
            runner._opdracht_regenereer(config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM})

    def test_lege_week_stopt_voordat_er_iets_wijzigt(self, runner, config, geslaagde_keten):
        with patch.object(runner, "haal_weekdata_op", return_value=[]):
            with pytest.raises(ValueError, match="Geen orders gevonden"):
                runner._opdracht_regenereer(
                    config, {"orderId": 1266289, "email": EMAIL, "naam": NAAM}
                )

        geslaagde_keten["verwijder"].assert_not_called()
        geslaagde_keten["mail"].assert_not_called()

    def test_zonder_aan_adres_wordt_niets_verstuurd(self, runner, config, geslaagde_keten):
        with pytest.raises(ValueError, match="Geen enkel Aan-adres"):
            runner._opdracht_regenereer(
                config,
                {"orderId": 1266289, "email": {"to": [], "cc": [], "bcc": []}, "naam": NAAM},
            )

        geslaagde_keten["mail"].assert_not_called()
        # De nieuwe order is teruggedraaid, de oude staat er nog.
        assert geslaagde_keten["verwijder"].call_args[0][3] == 1266400


class TestOntbrekendeConfiguratie:
    def test_ontbrekende_soap_gegevens(self, runner):
        with patch.dict(os.environ, {"MENDRIX_SOAP_URL": "", "MENDRIX_SOAP_USER": ""}, clear=False):
            with pytest.raises(RuntimeError, match="MENDRIX_SOAP"):
                runner._soap_gegevens()

    def test_ontbrekende_rest_gegevens(self, runner):
        with patch.dict(os.environ, {"MENDRIX_API_URL": "", "MENDRIX_API_TOKEN": ""}, clear=False):
            with pytest.raises(RuntimeError, match="MENDRIX_API"):
                runner._rest_gegevens()


class TestLogbestanden:
    """Alleen een hergeneratie verdient een eigen logbestand."""

    def test_hergeneratie_krijgt_handmatig_prefix(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LOG_DIR", str(tmp_path))
        pad = runner._setup_logging("regenereer")

        assert os.path.basename(pad).startswith("handmatig_")
        assert pad.endswith(".log")
        assert os.path.isfile(pad)

    @pytest.mark.parametrize("opdracht", ["lijst", None, "onzin"])
    def test_overige_opdrachten_schrijven_geen_bestand(
        self, runner, tmp_path, monkeypatch, opdracht
    ):
        """De lijst wordt bij elke pagina-verversing opgehaald; dat hoort geen
        logbestand op te leveren."""
        monkeypatch.setattr(runner, "LOG_DIR", str(tmp_path))

        assert runner._setup_logging(opdracht) == ""
        assert list(tmp_path.iterdir()) == []


class TestOudeLogsOpruimen:
    """Alleen .log-bestanden; logs/.gitkeep houdt de map in Git."""

    def _oud(self, pad):
        """Zet de wijzigingsdatum ruim buiten de bewaartermijn."""
        oud = datetime.now().timestamp() - 90 * 86400
        os.utime(pad, (oud, oud))

    def test_verwijdert_oude_logbestanden(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LOG_DIR", str(tmp_path))
        oud = tmp_path / "handmatig_2020-01-01_120000.log"
        oud.write_text("oud")
        self._oud(oud)

        runner._ruim_oude_logs_op()

        assert not oud.exists()

    def test_laat_gitkeep_staan(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LOG_DIR", str(tmp_path))
        gitkeep = tmp_path / ".gitkeep"
        gitkeep.write_text("")
        self._oud(gitkeep)

        runner._ruim_oude_logs_op()

        assert gitkeep.exists()

    def test_laat_andere_bestanden_staan(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LOG_DIR", str(tmp_path))
        notitie = tmp_path / "aantekening.txt"
        notitie.write_text("bewaren")
        self._oud(notitie)

        runner._ruim_oude_logs_op()

        assert notitie.exists()

    def test_laat_verse_logbestanden_staan(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LOG_DIR", str(tmp_path))
        vers = tmp_path / "handmatig_vandaag.log"
        vers.write_text("vers")

        runner._ruim_oude_logs_op()

        assert vers.exists()


class TestUitvoerprotocol:
    def test_emit_schrijft_een_json_regel(self, runner, capsys):
        runner._emit({"type": "log", "bericht": "hallo €"})

        uitvoer = capsys.readouterr().out
        assert uitvoer.endswith("\n")
        assert json.loads(uitvoer) == {"type": "log", "bericht": "hallo €"}

    def test_stap_meldt_nummer_en_totaal(self, runner, capsys):
        runner._stap(3, "order aanmaken")

        gebeurtenis = json.loads(capsys.readouterr().out)
        assert gebeurtenis == {
            "type": "stap",
            "nummer": 3,
            "totaal": runner.TOTAAL_STAPPEN,
            "bericht": "order aanmaken",
        }

    def test_onbekende_opdracht_geeft_exitcode_2(self, runner, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(read=lambda: '{"command":"onzin"}'))
        monkeypatch.setattr(runner, "_setup_logging", lambda naam: "logbestand.log")
        monkeypatch.setattr(runner, "_ruim_oude_logs_op", lambda *a, **k: None)

        assert runner.main() == 2
        regels = [json.loads(r) for r in capsys.readouterr().out.strip().split("\n")]
        assert regels[-1]["type"] == "fout"
        assert "Onbekende opdracht" in regels[-1]["bericht"]

    def test_ongeldige_json_geeft_exitcode_2(self, runner, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(read=lambda: "{geen json"))
        monkeypatch.setattr(runner, "_setup_logging", lambda naam: "logbestand.log")
        monkeypatch.setattr(runner, "_ruim_oude_logs_op", lambda *a, **k: None)

        assert runner.main() == 2
        assert "Ongeldige JSON" in capsys.readouterr().out
