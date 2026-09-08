"""
Ouvrir n'importe quelle application installée, sur l'écran voulu.

La configuration ne peut pas tout prévoir : ce qui n'y figure pas est
cherché là où Windows range ses applications.
"""

import json

import pytest

from commands.apps import separer_ecran
from core import applications, desktop
from core.context import Utterance


# --------------------------------------------------------------------------
# « ... sur l ecran N »
# --------------------------------------------------------------------------
@pytest.mark.parametrize("demande,nom,ecran", [
    ("visual studio code sur l'écran 1", "visual studio code", 1),
    ("Discord sur l'écran 2", "Discord", 2),
    ("Word sur l'ecran 1", "Word", 1),
    ("Paint sur le deuxieme ecran", "Paint", 2),
    ("le Bloc-notes sur l'écran principal", "le Bloc-notes", 1),
    # « 2 » transcrit « de », comme ailleurs dans le projet.
    ("la calculatrice sur écran de", "la calculatrice", 2),
    # Sans mention d'écran, le nom reste entier.
    ("Chrome", "Chrome", None),
    ("Visual Studio Code", "Visual Studio Code", None),
    # « écran » sans numéro n'est pas une mention d'écran.
    ("Notepad sur l'écran", "Notepad sur l'écran", None),
])
def test_la_mention_decran_est_detachee(demande, nom, ecran):
    assert separer_ecran(demande) == (nom, ecran)


def test_lecran_de_droite_suit_le_nombre_decrans(monkeypatch):
    """Sur trois écrans, « de droite » désigne le troisième, pas le deuxième."""
    monkeypatch.setattr(desktop, "ecrans", lambda: [
        desktop.Ecran(1, (0, 0, 1920, 1080), 1),
        desktop.Ecran(2, (1920, 0, 3840, 1080), 2),
        desktop.Ecran(3, (3840, 0, 5760, 1080), 3),
    ])
    assert separer_ecran("Notepad sur l'écran de droite") == ("Notepad", 3)
    assert separer_ecran("Notepad sur l'écran de gauche") == ("Notepad", 1)


# --------------------------------------------------------------------------
# L inventaire
# --------------------------------------------------------------------------
@pytest.fixture
def inventaire(monkeypatch):
    """Un parc d'applications connu, pour ne pas dépendre de la machine."""
    monkeypatch.setattr(applications, "raccourcis_du_menu", lambda: {
        "Visual Studio Code": r"C:\Menu\Visual Studio Code.lnk",
        "Discord": r"C:\Menu\Discord.lnk",
        "IntelliJ IDEA 2025.3.3": r"C:\Menu\IntelliJ.lnk",
        "Git Bash": r"C:\Menu\Git Bash.lnk",
    })
    monkeypatch.setattr(applications, "applications_du_systeme",
                        lambda forcer=False: {
                            "Calculatrice": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
                            "Paint": "Microsoft.Paint_8wekyb3d8bbwe!App",
                        })


@pytest.mark.parametrize("demande,attendu", [
    ("Visual Studio Code", "Visual Studio Code"),
    ("visual studio code", "Visual Studio Code"),
    ("code", "Visual Studio Code"),          # un mot du nom suffit
    ("discord", "Discord"),
    ("git bash", "Git Bash"),
    ("intellij", "IntelliJ IDEA 2025.3.3"),
    # Absentes du menu Démarrer : elles viennent de la liste du système.
    ("calculatrice", "Calculatrice"),
    ("paint", "Paint"),
])
def test_une_application_installee_est_retrouvee(inventaire, demande, attendu):
    trouve = applications.chercher(demande)
    assert trouve is not None, demande
    assert trouve[0] == attendu


@pytest.mark.parametrize("demande", ["machin truc bidule", "", "zzzz"])
def test_ce_qui_nest_pas_installe_nest_pas_invente(inventaire, demande):
    assert applications.chercher(demande) is None


def test_le_menu_demarrer_passe_avant_la_liste_du_systeme(monkeypatch):
    """La première source est instantanée : on ne paie la seconde qu'au besoin."""
    monkeypatch.setattr(applications, "raccourcis_du_menu",
                        lambda: {"Paint": r"C:\Menu\Paint.lnk"})
    appels = []
    monkeypatch.setattr(applications, "applications_du_systeme",
                        lambda forcer=False: appels.append(1) or {})
    assert applications.chercher("paint")[1].endswith("Paint.lnk")
    assert appels == [], "la liste du système n'avait pas lieu d'être consultée"


@pytest.mark.parametrize("nom", [
    "Uninstall Git", "Documentation", "Release Notes", "IntelliJ IDEA FAQs",
])
def test_les_raccourcis_qui_ne_sont_pas_des_applications_sont_ecartes(nom):
    assert applications._indesirable(nom) is True


def test_un_vrai_nom_dapplication_est_garde():
    for nom in ("Visual Studio Code", "Discord", "Paint", "Git Bash"):
        assert applications._indesirable(nom) is False


def test_le_cache_est_relu_sans_relancer_le_systeme(monkeypatch, tmp_path):
    fichier = tmp_path / "applications_installees.json"
    fichier.write_text(json.dumps({"Paint": "Microsoft.Paint"}), encoding="utf-8")
    monkeypatch.setattr(applications, "_chemin_cache", lambda: fichier)

    def interdit(*a, **k):
        raise AssertionError("le système ne devait pas être interrogé")

    monkeypatch.setattr(applications.subprocess, "run", interdit)
    assert applications.applications_du_systeme() == {"Paint": "Microsoft.Paint"}


# --------------------------------------------------------------------------
# La commande
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("ouvre Visual Studio Code sur l'écran 1", "open_app"),
    ("ouvre Discord", "open_app"),
    ("ouvre Chrome", "open_app"),
    # Un site nommé exactement reste un site.
    ("ouvre Google", "open_website"),
    ("ouvre Netflix", "open_website"),
])
def test_le_routage_reste_juste(assistant, inventaire, phrase, attendu):
    resolution = assistant.router.resolve(Utterance.parse(phrase), assistant=assistant)
    assert resolution is not None, phrase
    assert resolution.command.name == attendu, phrase


@pytest.fixture
def lancement(monkeypatch):
    """Observe le lancement et le placement, sans rien ouvrir."""
    from commands import apps

    etat = {"lance": [], "place": []}
    monkeypatch.setattr(applications, "lancer",
                        lambda cible: etat["lance"].append(cible) or (True, cible))
    monkeypatch.setattr(apps.win_utils, "launch",
                        lambda chemins: etat["lance"].append(tuple(chemins)) or (True, "ok"))
    monkeypatch.setattr(apps, "_placer",
                        lambda connues, index, processus="":
                        etat["place"].append(index) or True)
    monkeypatch.setattr(desktop, "poignees_visibles", lambda: set())
    return etat


def test_sans_precision_lapplication_va_sur_lecran_un(assistant, inventaire, lancement):
    assistant.definir_ecran(2)          # même en travaillant sur l'écran 2
    reponse = assistant.handle("ouvre Discord")
    assert reponse.ok, reponse.text
    assert lancement["place"] == [1]


def test_lecran_demande_est_respecte(assistant, inventaire, lancement):
    reponse = assistant.handle("ouvre Discord sur l'écran 2")
    assert reponse.ok, reponse.text
    assert lancement["place"] == [2]
    assert "écran 2" in reponse.text


def test_un_ecran_inexistant_est_refuse(assistant, inventaire, lancement):
    reponse = assistant.handle("ouvre Discord sur l'écran 9")
    assert not reponse.ok
    assert lancement["lance"] == [], "rien ne devait être lancé"


def test_une_application_installee_mais_non_configuree_souvre(assistant, inventaire,
                                                              lancement):
    """« IntelliJ » n'est pas dans config.yaml : elle est trouvée sur le disque."""
    reponse = assistant.handle("ouvre IntelliJ sur l'écran 1")
    assert reponse.ok, reponse.text
    assert lancement["lance"] == [r"C:\Menu\IntelliJ.lnk"]


# --------------------------------------------------------------------------
# Reperage de la fenetre qui vient de s ouvrir
# --------------------------------------------------------------------------
def fenetre(titre, processus, ecran=1, handle=1):
    return desktop.Fenetre(handle=handle, titre=titre, processus=processus, ecran=ecran)


def test_la_console_de_lancement_nest_pas_prise_pour_lapplication(monkeypatch):
    """
    « code.cmd » ouvre une console avant Visual Studio Code. C'est
    l'application qu'il faut déplacer, pas la console de passage.
    """
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("C:\\Windows\\system32\\cmd.exe", "WindowsTerminal.exe", handle=10),
        fenetre("projet - Visual Studio Code", "Code.exe", handle=11),
    ])
    trouve = desktop.attendre_nouvelle_fenetre(set(), delai=0.2)
    assert trouve is not None and trouve.handle == 11


def test_une_console_demandee_expressement_est_acceptee(monkeypatch):
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("cmd", "WindowsTerminal.exe", handle=10),
    ])
    trouve = desktop.attendre_nouvelle_fenetre(set(), delai=0.2,
                                               processus="WindowsTerminal.exe")
    assert trouve is not None and trouve.handle == 10


def test_les_fenetres_deja_la_sont_ignorees(monkeypatch):
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("Ancienne", "notepad.exe", handle=10),
    ])
    assert desktop.attendre_nouvelle_fenetre({10}, delai=0.2) is None
