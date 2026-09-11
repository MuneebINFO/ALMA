"""
Ou Alma range ses reglages une fois empaquetee (--onefile, MSIX...).

En developpement, ROOT est le dossier du projet -- ce que tous les autres
tests supposent deja. Une fois figee par PyInstaller (sys.frozen), le
dossier de l'executable n'est ni stable ni inscriptible (onefile l'extrait
dans un temp differt a chaque lancement ; le Store l'installe en lecture
seule) : les reglages doivent alors aller dans %LOCALAPPDATA%\\Alma, sans
quoi config.yaml et l'historique disparaîtraient a chaque redemarrage.
"""

import config


def test_en_developpement_le_dossier_est_celui_du_projet():
    assert config._dossier_utilisateur() == config.ROOT
    assert (config.ROOT / "config.py").exists(), "doit être le dossier du projet"


def test_une_fois_figee_le_dossier_est_localappdata(monkeypatch, tmp_path):
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config._dossier_utilisateur() == tmp_path / "Alma"


def test_sans_localappdata_on_retombe_sur_le_dossier_personnel(monkeypatch, tmp_path):
    """Cas degrade (LOCALAPPDATA absent) : le dossier personnel plutôt que rien."""
    from pathlib import Path

    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert config._dossier_utilisateur() == Path.home() / "Alma"
