"""
« mets la série The Flash » : toute la démarche, jusqu'au bouton Lecture.

Chercher, choisir le bon résultat, ouvrir sa fiche — et s'arrêter là. Lancer
la lecture reste une décision de l'utilisateur.
"""

import pytest

from commands import websites
from core import desktop, interaction
from core.context import Utterance


# --------------------------------------------------------------------------
# Ce qui est un titre, et ce qui n en est pas
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "mets la série The Flash",
    "mets la serie The Flash",
    "lance le film Interstellar",
    "joue le film Interstellar sur Netflix",
    "regarde le documentaire Cosmos",
    "mets un épisode de Friends",
    "ouvre la saison 3 de Dark",
    "trouve l'anime One Piece",
    "affiche le match de ce soir",
])
def test_ces_phrases_lancent_la_demarche(assistant, phrase):
    resolution = assistant.router.resolve(Utterance.parse(phrase), assistant=assistant)
    assert resolution is not None, phrase + " n'atteint aucune commande"
    assert resolution.command.name == "lancer_titre", phrase


@pytest.mark.parametrize("phrase,attendu", [
    # « le film » y est le sujet d'un réglage, pas un titre à chercher.
    ("mets le film plus fort", "volume_media_up"),
    ("mets le film moins fort", "volume_media_down"),
    ("baisse le volume de la vidéo", "volume_media_down"),
    # Ces commandes-là existaient déjà et doivent le rester.
    ("mets de la musique", "play_music"),
    ("lance la vidéo", "media_lecture"),
    ("mets pause à la vidéo", "media_mettre_en_pause"),
    ("mets The Adam Project sur Netflix", "site_search"),
    ("va sur Netflix", "open_website"),
    ("retourne à l'accueil", "retour_accueil"),
])
def test_les_commandes_voisines_ne_sont_pas_captees(assistant, phrase, attendu):
    resolution = assistant.router.resolve(Utterance.parse(phrase), assistant=assistant)
    assert resolution is not None and resolution.command.name == attendu, phrase


@pytest.mark.parametrize("brut,attendu", [
    ("de Friends", "Friends"),
    ("du Seigneur des anneaux", "Seigneur des anneaux"),
    ("d'Interstellar", "Interstellar"),
    ("The Flash", "The Flash"),
    ("", ""),
])
def test_larticle_de_liaison_est_retire(brut, attendu):
    """« un épisode DE Friends » : le catalogue ne connaît pas « de Friends »."""
    assert websites._titre_propre(brut) == attendu


# --------------------------------------------------------------------------
# Reconnaissance de la fiche
# --------------------------------------------------------------------------
def cible(nom, largeur=364, hauteur=205, haut=0):
    c = interaction.Cible(nom, (0, haut, largeur, haut + hauteur), object(),
                          interaction.LIEN)
    return c


@pytest.mark.parametrize("noms,attendu", [
    (["Play"], True),
    (["Lecture", "Ma liste"], True),
    (["Reprendre S. 6 Ép. 5"], True),
    (["Saison 3"], True),
    (["Bande-annonce"], True),
    # Une page de résultats n'est pas une fiche.
    (["The Flash", "Green Lantern", "Titans"], False),
    ([], False),
])
def test_la_fiche_se_reconnait_a_son_bouton(noms, attendu):
    assert websites._fiche_ouverte([cible(n) for n in noms]) is attendu


# --------------------------------------------------------------------------
# La demarche complete, avec une page factice
# --------------------------------------------------------------------------
@pytest.fixture
def page(monkeypatch):
    """
    Une page pilotable : on décide ce qu'elle contient, et le clic la fait
    passer de la liste de résultats à la fiche.
    """
    etat = {"elements": [], "apres_clic": [], "clics": [], "adresse": "netflix.com/search"}

    def elements(fenetre, taille_min=12, visibles_seulement=True):
        return [c for c in etat["elements"]
                if c.rect[2] - c.rect[0] >= taille_min
                and c.rect[3] - c.rect[1] >= taille_min]

    def cliquer(c, physique=False):
        etat["clics"].append(c.nom)
        etat["elements"] = etat["apres_clic"]
        return True

    monkeypatch.setattr(interaction, "elements_cliquables", elements)
    monkeypatch.setattr(interaction, "cliquer", cliquer)
    monkeypatch.setattr(websites, "STABILISATION", 0)
    monkeypatch.setattr(websites, "PAS_DE_SONDAGE", 0)
    monkeypatch.setattr(websites, "ATTENTE_RESULTATS", 0.05)
    monkeypatch.setattr(websites, "ATTENTE_FICHE", 0.05)
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        desktop.Fenetre(handle=20, titre="Netflix - Google Chrome",
                        processus="chrome.exe", ecran=1),
    ])
    return etat


def test_le_bon_resultat_est_ouvert(page):
    page["elements"] = [cible("The Flash"), cible("Flash Gordon"), cible("Titans")]
    page["apres_clic"] = [cible("Play"), cible("Ma liste")]
    fenetre = desktop.fenetres()[0]

    trouve, nom = websites._ouvrir_le_resultat(fenetre, "The Flash")
    assert nom == "The Flash"
    assert page["clics"] == ["The Flash"]


def test_un_titre_absent_du_catalogue_est_dit_tel_quel(page):
    page["elements"] = [cible("Titans"), cible("Green Lantern")]
    fenetre = desktop.fenetres()[0]

    trouve, nom = websites._ouvrir_le_resultat(fenetre, "The Flash")
    assert trouve is None and nom is None
    assert page["clics"] == [], "rien ne devait être cliqué"


def test_un_fragment_de_texte_nest_pas_un_resultat(page):
    """
    Netflix affiche « We don't have "The Flash", but... » : le titre y figure,
    dans un texte minuscule. Une affiche fait 364x205, pas 91x30.
    """
    page["elements"] = [cible("The Flash", largeur=91, hauteur=30)]
    fenetre = desktop.fenetres()[0]

    trouve, nom = websites._ouvrir_le_resultat(fenetre, "The Flash")
    assert trouve is None
    assert page["clics"] == []


def test_un_clic_sans_effet_est_retente(page):
    """La grille se réorganise pendant le chargement : on reprend l'élément."""
    page["elements"] = [cible("The Flash")]
    page["apres_clic"] = [cible("The Flash")]        # rien n'a bougé
    fenetre = desktop.fenetres()[0]

    trouve, nom = websites._ouvrir_le_resultat(fenetre, "The Flash")
    assert nom is None, "la fiche ne s'est jamais ouverte"
    assert len(page["clics"]) == websites.TENTATIVES_CLIC


# --------------------------------------------------------------------------
# Sur quel service
# --------------------------------------------------------------------------
def test_le_service_nomme_lemporte(assistant, monkeypatch):
    demandes = []
    monkeypatch.setattr(websites, "afficher_site",
                        lambda *a, **k: demandes.append(a[1:3]) or (False, "ouvert"))
    assistant.handle("lance le film Interstellar sur Netflix")
    assert demandes and demandes[0][0] == "netflix"
    assert "netflix.com/search" in demandes[0][1]


def test_sans_service_on_reprend_celui_du_contexte(assistant, monkeypatch):
    demandes = []
    monkeypatch.setattr(websites, "afficher_site",
                        lambda *a, **k: demandes.append(a[1:3]) or (False, "ouvert"))
    assistant.memoriser("site", "disney")
    assistant.handle("mets la série The Mandalorian")
    assert demandes and demandes[0][0] == "disney"


def test_sans_rien_pour_deviner_le_service_on_le_demande(assistant, monkeypatch):
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [])
    reponse = assistant.handle("mets la série The Flash")
    assert not reponse.ok
    assert "Netflix" in reponse.text          # l'exemple proposé
