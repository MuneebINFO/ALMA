"""
Fermer un onglet par son numéro d'ordre — le plus à gauche est le 1.

Aucun navigateur n'est réellement piloté : les fenêtres et les onglets sont
doublés, avec une position X pour chacun. On vérifie le comptage de gauche à
droite, le ciblage de l'écran de travail, et que « ferme cet onglet » (onglet
courant) n'est pas capté au passage.
"""

import pytest

from core import browser_tabs, desktop
from core.context import Utterance
from commands import fenetres


class FenetreFactice:
    est_navigateur = True

    def __init__(self, handle, ecran):
        self.handle = handle
        self.ecran = ecran
        self.titre = "Chrome " + str(handle)
        self.processus = "chrome.exe"


class OngletFactice:
    def __init__(self, nom, gauche):
        self.nom = nom
        self._gauche = gauche
        self.ferme = False
        self.active = False
        # Ce que le code lit pour trier : onglet.element.CurrentBoundingRectangle.left
        self.element = type("E", (), {"CurrentBoundingRectangle": type(
            "R", (), {"left": gauche})()})()

    def activer(self):
        self.active = True
        return True


@pytest.fixture
def bureau(monkeypatch):
    """
    Un Chrome sur l'écran 1 (4 onglets) et un sur l'écran 2 (2 onglets).

    Les onglets sont volontairement donnés dans le DÉSORDRE de leur position :
    le tri de gauche à droite doit les remettre d'aplomb.
    """
    ecran1 = FenetreFactice(handle=101, ecran=1)
    ecran2 = FenetreFactice(handle=202, ecran=2)
    par_fenetre = {
        101: [OngletFactice("D", 300), OngletFactice("A", 0),
              OngletFactice("C", 200), OngletFactice("B", 100)],
        202: [OngletFactice("Écran2-b", 90), OngletFactice("Écran2-a", 10)],
    }
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [ecran1, ecran2])
    monkeypatch.setattr(browser_tabs, "onglets",
                        lambda f: list(par_fenetre.get(f.handle, [])))

    fermes = []

    def fermer(onglet):
        onglet.ferme = True
        fermes.append(onglet.nom)
        return True

    # La vraie `_navigateur_vise` tourne : elle appelle GetForegroundWindow,
    # qui renverra un vrai handle sans rapport avec 101/202 -- donc le choix
    # se fera sur l'écran, ce qu'on veut ici.
    monkeypatch.setattr(fenetres, "_fermer_onglet", fermer)
    return {"ecran1": ecran1, "ecran2": ecran2, "onglets": par_fenetre, "fermes": fermes}


def commande(assistant, phrase):
    resolution = assistant.router.resolve(
        Utterance.parse(phrase, wake_words=assistant.config.get("general.wake_words")),
        assistant=assistant,
    )
    return resolution.command.name if resolution else "aucune"


# --------------------------------------------------------------------------
# Routage
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "ferme l'onglet 3",
    "ferme l'onglet numéro 3",
    "ferme onglet 2",
    "ferme le troisième onglet",
    "ferme le 3e onglet",
    "ferme le dernier onglet",
    "vire l'onglet 5",
])
def test_ces_phrases_ferment_un_onglet_par_numero(assistant, phrase):
    assert commande(assistant, phrase) == "fermer_onglet_numero"


@pytest.mark.parametrize("phrase,attendu", [
    ("ferme cet onglet", "fermer_onglet"),
    ("ferme l'onglet", "fermer_onglet"),
    ("ferme la fenêtre", "fermer_fenetre"),
    ("onglet suivant", "onglet_suivant"),
    ("ferme Chrome", "close_app"),
])
def test_les_commandes_voisines_ne_sont_pas_captees(assistant, phrase, attendu):
    assert commande(assistant, phrase) == attendu


# --------------------------------------------------------------------------
# Le comptage de gauche à droite
# --------------------------------------------------------------------------
def test_les_onglets_sont_ordonnes_par_position(bureau):
    ordonnes = fenetres._onglets_gauche_a_droite(bureau["ecran1"])
    assert [o.nom for o in ordonnes] == ["A", "B", "C", "D"]


@pytest.mark.parametrize("phrase,cible", [
    ("ferme l'onglet 1", "A"),
    ("ferme l'onglet 2", "B"),
    ("ferme l'onglet 4", "D"),
    ("ferme le troisième onglet", "C"),
    ("ferme le dernier onglet", "D"),
    ("ferme l'onglet numéro deux", "B"),
])
def test_le_bon_onglet_est_ferme(assistant, bureau, phrase, cible):
    assistant.ecran_actif = 1
    reponse = assistant.handle(phrase)
    assert reponse.ok, reponse.text
    assert bureau["fermes"] == [cible]


def test_un_numero_trop_grand_le_dit(assistant, bureau):
    assistant.ecran_actif = 1
    reponse = assistant.handle("ferme l'onglet 9")
    assert not reponse.ok
    assert "4 onglets" in reponse.text
    assert bureau["fermes"] == []


def test_ce_qui_n_est_pas_un_numero_fait_demander_lequel(assistant, bureau):
    assistant.ecran_actif = 1
    reponse = assistant.handle("ferme l'onglet bleu")
    assert not reponse.ok
    assert bureau["fermes"] == []


# --------------------------------------------------------------------------
# L'écran de travail
# --------------------------------------------------------------------------
def test_l_ecran_de_travail_decide_du_navigateur(assistant, bureau):
    """« ferme l'onglet 1 » vise le Chrome de l'écran où l'on travaille."""
    assistant.ecran_actif = 2
    assistant.handle("ferme l'onglet 1")
    assert bureau["fermes"] == ["Écran2-a"]


def test_l_ecran_peut_etre_nomme_dans_la_phrase(assistant, bureau):
    assistant.ecran_actif = 1
    assistant.handle("ferme l'onglet 2 sur l'écran 2")
    assert bureau["fermes"] == ["Écran2-b"]


def test_sans_navigateur_il_le_dit(assistant, monkeypatch):
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [])
    reponse = assistant.handle("ferme l'onglet 2")
    assert not reponse.ok


# --------------------------------------------------------------------------
# Le choix de la fenêtre : l'écran de travail passe avant le premier plan
# --------------------------------------------------------------------------
def test_le_navigateur_de_l_ecran_actif_bat_celui_du_premier_plan(monkeypatch):
    """
    Mesuré sur la vraie machine : le Chrome de l'écran 2 était au premier
    plan, mais « sur l'écran 1 » doit viser celui de l'écran 1, fût-il
    minimisé et derrière.
    """
    ecran1 = FenetreFactice(handle=101, ecran=1)
    ecran2 = FenetreFactice(handle=202, ecran=2)
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [ecran2, ecran1])

    class Ctx:
        class assistant:
            ecran_actif = 1

            # L'écran 2 est bien au premier plan...
            @staticmethod
            def fenetre_courante():
                return ecran2

    # ... mais « sur l'écran 1 » vise le 1.
    assert fenetres._navigateur_vise(Ctx()).handle == 101
