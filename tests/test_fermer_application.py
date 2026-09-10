"""
« ferme Chrome » ne ferme qu'UNE fenêtre — celle où l'on est.

Le défaut signalé : sur l'écran 1, « ferme Chrome » tuait le processus et
emportait le Chrome de l'écran 2. Une commande d'application ne doit toucher
que ce qu'on a devant soi.

Aucune fenêtre n'est réellement fermée : `desktop.fermer_fenetre` et
`win_utils.kill_process` sont doublés et on inspecte ce qu'ils reçoivent.
"""

import pytest

from core import desktop, win_utils
from core.context import Utterance
from commands import apps


class FenetreFactice:
    def __init__(self, handle, ecran, processus="chrome.exe", titre=None):
        self.handle = handle
        self.ecran = ecran
        self.processus = processus
        self.titre = titre or (processus.split(".")[0] + " " + str(handle))

    @property
    def est_navigateur(self):
        return self.processus.lower() == "chrome.exe"


@pytest.fixture
def machine(monkeypatch):
    """
    Deux fenêtres Chrome sur l'écran 1, une sur l'écran 2, et un Spotify.
    """
    fenetres = [
        FenetreFactice(11, 1),
        FenetreFactice(12, 1),
        FenetreFactice(21, 2),
        FenetreFactice(30, 1, "Spotify.exe"),
    ]
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: list(fenetres))

    fermees = []
    tuees = []
    monkeypatch.setattr(desktop, "fermer_fenetre",
                        lambda h: fermees.append(h) or True)
    monkeypatch.setattr(win_utils, "kill_process",
                        lambda p: tuees.append(p) or (True, p))
    monkeypatch.setattr(desktop, "fenetre_au_premier_plan", lambda: None)
    monkeypatch.setattr(desktop, "fenetre_par_poignee",
                        lambda h: next((f for f in fenetres if f.handle == h), None))
    return {"fenetres": fenetres, "fermees": fermees, "tuees": tuees}


def reponse(assistant, phrase):
    return assistant.handle(phrase)


# --------------------------------------------------------------------------
# Une seule fenêtre, sur le bon écran
# --------------------------------------------------------------------------
def test_ferme_une_seule_fenetre_pas_le_processus(assistant, machine):
    assistant.ecran_actif = 1
    r = reponse(assistant, "ferme Chrome")
    assert r.ok
    assert len(machine["fermees"]) == 1
    assert machine["tuees"] == [], "le processus ne doit pas être tué"


def test_ne_touche_que_l_ecran_de_travail(assistant, machine):
    """Sur l'écran 1, on ne ferme jamais le Chrome de l'écran 2."""
    assistant.ecran_actif = 1
    reponse(assistant, "ferme Chrome")
    assert machine["fermees"] == [11] or machine["fermees"] == [12]
    assert 21 not in machine["fermees"]


def test_l_ecran_2_est_visable_quand_on_y_travaille(assistant, machine):
    assistant.ecran_actif = 2
    reponse(assistant, "ferme Chrome")
    assert machine["fermees"] == [21]


def test_l_ecran_peut_etre_nomme_dans_la_phrase(assistant, machine):
    assistant.ecran_actif = 1
    reponse(assistant, "ferme Chrome sur l'écran 2")
    assert machine["fermees"] == [21]


# --------------------------------------------------------------------------
# Plusieurs fenêtres sur le même écran : celle où l'on est
# --------------------------------------------------------------------------
def test_parmi_plusieurs_sur_l_ecran_celle_ou_l_on_est(assistant, machine, monkeypatch):
    assistant.ecran_actif = 1
    # L'utilisateur est sur la fenêtre 12 (Alma est passée devant, mais
    # l'interface a retenu 12 comme dernière fenêtre vue).
    assistant.poignee_alma = 999
    assistant.fenetre_utilisateur = 12
    monkeypatch.setattr(desktop, "fenetre_au_premier_plan",
                        lambda: FenetreFactice(999, 1, "python.exe", "ALMA"))
    reponse(assistant, "ferme Chrome")
    assert machine["fermees"] == [12]


def test_la_fenetre_au_premier_plan_l_emporte(assistant, machine, monkeypatch):
    assistant.ecran_actif = 1
    monkeypatch.setattr(desktop, "fenetre_au_premier_plan",
                        lambda: machine["fenetres"][1])   # handle 12
    reponse(assistant, "ferme Chrome")
    assert machine["fermees"] == [12]


# --------------------------------------------------------------------------
# Tout fermer : là, oui, on tue le processus
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "ferme tout Chrome",
    "ferme complètement Chrome",
    "tue Chrome",
])
def test_tout_fermer_tue_le_processus(assistant, machine, phrase):
    assistant.ecran_actif = 1
    r = reponse(assistant, phrase)
    assert r.ok
    assert machine["tuees"] == ["chrome.exe"]
    assert machine["fermees"] == [], "on n'a pas fermé fenêtre par fenêtre"


def test_ferme_normal_ne_dit_pas_tout(assistant, machine):
    """Garde-fou : « ferme Chrome » seul ne doit jamais tuer le processus."""
    assistant.ecran_actif = 1
    reponse(assistant, "ferme Chrome")
    assert machine["tuees"] == []


# --------------------------------------------------------------------------
# Application sans fenêtre visible : on tue, faute de mieux
# --------------------------------------------------------------------------
def test_sans_fenetre_visible_on_tue_le_processus(assistant, monkeypatch):
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [])
    tuees = []
    monkeypatch.setattr(win_utils, "kill_process",
                        lambda p: tuees.append(p) or (True, p))
    monkeypatch.setattr(desktop, "fenetre_au_premier_plan", lambda: None)
    reponse(assistant, "ferme Chrome")
    assert tuees == ["chrome.exe"]


# --------------------------------------------------------------------------
# Spotify (une seule fenêtre) : même logique
# --------------------------------------------------------------------------
def test_une_autre_application(assistant, machine):
    assistant.ecran_actif = 1
    reponse(assistant, "quitte Spotify")
    assert machine["fermees"] == [30]
    assert machine["tuees"] == []


# --------------------------------------------------------------------------
# La mémoire de « où j'étais »
# --------------------------------------------------------------------------
def test_alma_au_premier_plan_rend_la_derniere_fenetre_utilisateur(assistant, monkeypatch):
    chrome = FenetreFactice(50, 1)
    alma = FenetreFactice(999, 1, "python.exe", "ALMA")
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [chrome, alma])
    monkeypatch.setattr(desktop, "fenetre_par_poignee",
                        lambda h: {50: chrome, 999: alma}.get(h))
    monkeypatch.setattr(desktop, "fenetre_au_premier_plan", lambda: alma)
    assistant.poignee_alma = 999
    assistant.noter_fenetre_utilisateur(50)      # l'interface a vu Chrome avant
    assistant.noter_fenetre_utilisateur(999)     # puis Alma -> ignoré
    assert assistant.fenetre_utilisateur == 50
    assert assistant.fenetre_courante().handle == 50


def test_noter_la_fenetre_ne_coute_rien(assistant, monkeypatch):
    """Appelée 25 fois par seconde : elle ne doit rien énumérer."""
    def interdit(*a, **k):
        raise AssertionError("noter_fenetre_utilisateur a énuméré les fenêtres")

    monkeypatch.setattr(desktop, "fenetres", interdit)
    assistant.poignee_alma = 999
    assistant.noter_fenetre_utilisateur(123)
    assert assistant.fenetre_utilisateur == 123
