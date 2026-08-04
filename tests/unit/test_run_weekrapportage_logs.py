"""Tests voor het opruimen van oude logbestanden in de zondagrun.

scripts/run_weekrapportage.py is de draaiende productieketen en wordt niet
zomaar gewijzigd. De opruimlus verwijderde echter elk bestand ouder dan 60
dagen, dus ook logs/.gitkeep — waarmee de map uit Git verdwijnt. Deze tests
leggen het gedrag van die ene helper vast; de rest van het script blijft
ongemoeid.
"""

import importlib.util
import os
from datetime import datetime

import pytest

_SCRIPT_PAD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "run_weekrapportage.py",
)


@pytest.fixture(scope="module")
def productie_script():
    """Laadt scripts/run_weekrapportage.py als module zonder het te draaien."""
    spec = importlib.util.spec_from_file_location("_run_weekrapportage_logs", _SCRIPT_PAD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _maak_oud(pad) -> None:
    """Zet de wijzigingsdatum ruim buiten de bewaartermijn."""
    oud = datetime.now().timestamp() - 90 * 86400
    os.utime(pad, (oud, oud))


class TestRuimOudeLogsOp:
    def test_verwijdert_oude_logbestanden(self, productie_script, tmp_path, monkeypatch):
        monkeypatch.setattr(productie_script, "LOG_DIR", str(tmp_path))
        oud = tmp_path / "testscript_2020-01-01_120000.log"
        oud.write_text("oud")
        _maak_oud(oud)

        productie_script._ruim_oude_logs_op()

        assert not oud.exists()

    def test_laat_verse_logbestanden_staan(self, productie_script, tmp_path, monkeypatch):
        monkeypatch.setattr(productie_script, "LOG_DIR", str(tmp_path))
        vers = tmp_path / "testscript_vandaag.log"
        vers.write_text("vers")

        productie_script._ruim_oude_logs_op()

        assert vers.exists()

    def test_laat_gitkeep_staan(self, productie_script, tmp_path, monkeypatch):
        """De zondagrun draait wekelijks en was de dominante route naar dit lek."""
        monkeypatch.setattr(productie_script, "LOG_DIR", str(tmp_path))
        gitkeep = tmp_path / ".gitkeep"
        gitkeep.write_text("")
        _maak_oud(gitkeep)

        productie_script._ruim_oude_logs_op()

        assert gitkeep.exists()

    def test_laat_andere_bestanden_staan(self, productie_script, tmp_path, monkeypatch):
        monkeypatch.setattr(productie_script, "LOG_DIR", str(tmp_path))
        notitie = tmp_path / "aantekening.txt"
        notitie.write_text("bewaren")
        _maak_oud(notitie)

        productie_script._ruim_oude_logs_op()

        assert notitie.exists()

    def test_gedraagt_zich_gelijk_aan_de_dashboardversie(self, productie_script, tmp_path):
        """Beide entrypoints ruimen op; ze horen hetzelfde over te houden."""
        spec = importlib.util.spec_from_file_location(
            "_web_runner_logs",
            os.path.join(os.path.dirname(_SCRIPT_PAD), "web_runner.py"),
        )
        web_runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(web_runner)

        overgebleven = []
        for module in (productie_script, web_runner):
            map_ = tmp_path / module.__name__
            map_.mkdir()
            for naam in ("oud.log", "vers.log", ".gitkeep", "aantekening.txt"):
                bestand = map_ / naam
                bestand.write_text("x")
                if naam != "vers.log":
                    _maak_oud(bestand)
            module.LOG_DIR = str(map_)
            module._ruim_oude_logs_op()
            overgebleven.append(sorted(p.name for p in map_.iterdir()))

        assert overgebleven[0] == overgebleven[1]
        assert overgebleven[0] == [".gitkeep", "aantekening.txt", "vers.log"]
