"""
Le bug signalé : sur un écran sans Chrome, « ouvre Google » ouvrait l'onglet
dans le Chrome de l'AUTRE écran -- invisible pour l'utilisateur, qui ne
regardait pas cet écran-là.

Ces tests verrouillent le comportement voulu : rien n'est jamais repris sur
un autre écran que celui où l'on travaille ; s'il n'y a rien à reprendre ICI,
une fenêtre neuve y est ouverte -- et SEULEMENT là.
"""

import subprocess

import pytest

from commands import websites
from core import desktop
from core.context import Utterance


def fenetre(handle, titre, ecran, processus="chrome.exe"):
    return desktop.Fenetre(handle=handle, titre=titre, processus=processus, ecran=ecran)


def executer(router, assistant, phrase):
    utterance = Utterance.parse(phrase, wake_words=assistant.config.get("general.wake_words"))
    return router.run(utterance, assistant)


# --------------------------------------------------------------------------
# `_ouvrir_normalement` : la fenêtre neuve, et où elle atterrit
# --------------------------------------------------------------------------
@pytest.fixture
def chrome_localisable(monkeypatch, config):
    """Chrome « existe », sans qu'aucun processus ne soit réellement lancé."""
    monkeypatch.setattr(websites, "_chemin_chrome", lambda cfg: "C:/chrome.exe")
    lancements = []
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **k: lancements.append(args) or object())
    return lancements


def test_une_fenetre_neuve_est_demandee_avec_l_url(config, chrome_localisable, monkeypatch):
    monkeypatch.setattr(desktop, "poignees_visibles", lambda: set())
    monkeypatch.setattr(desktop, "attendre_nouvelle_fenetre", lambda *a, **k: None)
    ok = websites._ouvrir_normalement(config, "https://www.google.com", 1)
    assert ok is True
    assert chrome_localisable == [["C:/chrome.exe", "--new-window", "https://www.google.com"]]


def test_la_fenetre_neuve_est_amenee_sur_lecran_demande(config, chrome_localisable, monkeypatch):
    """
    Chrome peut très bien ouvrir sa fenêtre neuve sur SON écran habituel :
    on la ramène ensuite sur celui où l'on travaille.
    """
    apparue = fenetre(99, "Google - Google Chrome", ecran=2)
    monkeypatch.setattr(desktop, "poignees_visibles", lambda: set())
    monkeypatch.setattr(desktop, "attendre_nouvelle_fenetre", lambda *a, **k: apparue)
    deplacements = []
    monkeypatch.setattr(desktop, "deplacer_vers_ecran",
                        lambda h, i: deplacements.append((h, i)) or True)

    websites._ouvrir_normalement(config, "https://www.google.com", 1)
    assert deplacements == [(99, 1)]


def test_une_fenetre_deja_sur_le_bon_ecran_nest_pas_deplacee(config, chrome_localisable, monkeypatch):
    apparue = fenetre(99, "Google - Google Chrome", ecran=1)
    monkeypatch.setattr(desktop, "poignees_visibles", lambda: set())
    monkeypatch.setattr(desktop, "attendre_nouvelle_fenetre", lambda *a, **k: apparue)
    monkeypatch.setattr(desktop, "deplacer_vers_ecran",
                        lambda h, i: pytest.fail("rien à déplacer"))

    assert websites._ouvrir_normalement(config, "https://www.google.com", 1) is True


def test_sans_chrome_localisable_on_retombe_sur_le_navigateur_par_defaut(config, monkeypatch):
    monkeypatch.setattr(websites, "_chemin_chrome", lambda cfg: "")
    appels = []
    monkeypatch.setattr(websites, "open_url", lambda url: appels.append(url) or True)
    assert websites._ouvrir_normalement(config, "https://www.google.com", 1) is True
    assert appels == ["https://www.google.com"]


def test_sans_ecran_connu_on_retombe_aussi(config, chrome_localisable, monkeypatch):
    """Pas d'écran de travail su : impossible de savoir où placer la fenêtre."""
    appels = []
    monkeypatch.setattr(websites, "open_url", lambda url: appels.append(url) or True)
    assert websites._ouvrir_normalement(config, "https://www.google.com", None) is True
    assert appels == ["https://www.google.com"]
    assert chrome_localisable == [], "aucun processus ne devait être lancé"


# --------------------------------------------------------------------------
# Bout en bout : le scénario signalé
# --------------------------------------------------------------------------
def test_ouvrir_un_site_sans_chrome_sur_lecran_ne_touche_pas_lautre_ecran(
        assistant, router, monkeypatch, chrome_localisable):
    """
    Le scénario exact : Chrome tourne sur l'écran 2, l'utilisateur travaille
    sur l'écran 1 où rien n'est ouvert. « ouvre Google » ne doit RIEN faire
    dans la fenêtre de l'écran 2.
    """
    autre_ecran = fenetre(5, "Autre chose - Google Chrome", ecran=2)
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [autre_ecran])
    monkeypatch.setattr(desktop, "poignees_visibles", lambda: set())
    monkeypatch.setattr(desktop, "attendre_nouvelle_fenetre", lambda *a, **k: None)

    touchees = []
    monkeypatch.setattr(desktop, "ouvrir_onglet",
                        lambda f, url: touchees.append(f.handle) or True)
    monkeypatch.setattr(desktop, "naviguer_dans_fenetre",
                        lambda f, url: touchees.append(f.handle) or True)
    monkeypatch.setattr(desktop, "mettre_au_premier_plan",
                        lambda h: touchees.append(h) or True)

    assistant.definir_ecran(1)
    reponse, _ = executer(router, assistant, "ouvre Google")
    assert reponse.ok, reponse.text
    assert touchees == [], "la fenêtre de l'écran 2 n'aurait jamais dû être touchée"
    assert chrome_localisable, "une fenêtre neuve aurait dû être demandée"


def test_va_sur_un_site_ouvert_ailleurs_nest_pas_repris(
        assistant, router, monkeypatch, chrome_localisable):
    """Même chose pour « va sur X » : reprendre l'onglet de l'écran 2 serait
    invisible depuis l'écran 1."""
    from core import browser_tabs

    monkeypatch.setattr(browser_tabs, "trouver_onglet", lambda *a, **k: None)
    autre_ecran = fenetre(5, "Netflix - Google Chrome", ecran=2)
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [autre_ecran])
    monkeypatch.setattr(desktop, "poignees_visibles", lambda: set())
    monkeypatch.setattr(desktop, "attendre_nouvelle_fenetre", lambda *a, **k: None)

    touchees = []
    monkeypatch.setattr(desktop, "mettre_au_premier_plan",
                        lambda h: touchees.append(h) or True)

    assistant.definir_ecran(1)
    reponse, _ = executer(router, assistant, "va sur Netflix")
    assert reponse.ok, reponse.text
    assert touchees == [], "la fenêtre Netflix de l'écran 2 n'aurait pas dû être touchée"
