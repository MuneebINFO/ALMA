"""
L'interface : plein écran, orbe centré et grand, historique à la demande.

Aucune fenêtre n'apparaît pendant ces tests — la racine Tk est retirée de
l'écran. On vérifie ce qui se mesure : que l'orbe suit la taille qu'on lui
donne, qu'il reste centré, et que rien n'est dessiné en pixels fixes.
"""

import tkinter as tk
from pathlib import Path

import pytest

import gui

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def racine(tk_root):
    """La racine Tk partagée (voir conftest) : une seule pour toute la session."""
    return tk_root


def orbe_de(racine, largeur, hauteur):
    """Un orbe dessiné à une taille donnée, sans passer par le gestionnaire."""
    o = gui.Orbe(racine)
    o.arreter()                        # une seule image, pas de boucle
    o.after = lambda *a, **k: None
    o._redimensionner(type("E", (), {"width": largeur, "height": hauteur})())
    o._animer()
    return o


def orbe_sonore(racine, largeur, hauteur):
    """Un orbe qu'on a laissé monter au niveau maximum."""
    o = orbe_de(racine, largeur, hauteur)
    o.definir_etat("arme")
    for _ in range(30):               # le lissage doit avoir le temps de monter
        o.definir_niveau(1.0)
        o._animer()
    return o


# --------------------------------------------------------------------------
# L'orbe suit la fenêtre
# --------------------------------------------------------------------------
@pytest.mark.parametrize("largeur,hauteur", [(700, 500), (1400, 900), (1920, 1080)])
def test_l_orbe_est_centre(racine, largeur, hauteur):
    o = orbe_de(racine, largeur, hauteur)
    gauche, haut, droite, bas = o.bbox("all")
    # Le dessin doit être centré à quelques pixels près : c'est ce qui le
    # distingue d'un orbe posé dans un coin d'un grand écran.
    assert abs((gauche + droite) / 2 - largeur / 2) < largeur * 0.03
    assert abs((haut + bas) / 2 - hauteur / 2) < hauteur * 0.03


def test_l_orbe_grandit_avec_la_fenetre(racine):
    """
    Le défaut d'avant : une taille fixe de 300 pixels, qui laissait l'orbe
    flotter au milieu d'un écran entier.
    """
    petit = orbe_de(racine, 600, 600).bbox("all")
    grand = orbe_de(racine, 1200, 1200).bbox("all")
    largeur_petit = petit[2] - petit[0]
    largeur_grand = grand[2] - grand[0]
    assert largeur_grand > largeur_petit * 1.7


def test_l_orbe_occupe_vraiment_la_place(racine):
    """Grand, pas seulement centré : il doit remplir la hauteur disponible."""
    o = orbe_de(racine, 1400, 900)
    haut, bas = o.bbox("all")[1], o.bbox("all")[3]
    assert (bas - haut) > 900 * 0.85


def test_l_orbe_ne_deborde_pas(racine):
    """
    Au niveau maximum, rien ne doit sortir du cadre.

    Mesuré : sans marge, les graduations extérieures dépassaient de dix
    pixels, et l'orbe était rogné en haut et en bas en plein écran.
    """
    o = orbe_sonore(racine, 800, 800)
    gauche, haut, droite, bas = o.bbox("all")
    assert gauche >= -2 and haut >= -2
    assert droite <= 802 and bas <= 802


def test_une_fenetre_minuscule_ne_fait_pas_tomber(racine):
    """Pendant le tout premier affichage, le canvas mesure quelques pixels."""
    o = orbe_de(racine, 4, 4)
    assert o.find_all() == ()


def test_le_niveau_sonore_gonfle_le_noyau(racine):
    """
    C'est le NOYAU qu'il faut mesurer, pas l'orbe entier : la couronne
    extérieure est graduée, donc fixe — elle sert d'échelle, et une échelle
    qui respire n'en est plus une.
    """
    calme = orbe_de(racine, 900, 900)
    fort = orbe_sonore(racine, 900, 900)

    def largeur(o):
        gauche, _haut, droite, _bas = o.bbox("coeur")
        return droite - gauche

    assert largeur(fort) > largeur(calme) * 1.15


def test_la_couronne_graduee_ne_bouge_pas_avec_le_son(racine):
    calme = orbe_de(racine, 900, 900)
    fort = orbe_sonore(racine, 900, 900)

    def largeur(o):
        gauche, _haut, droite, _bas = o.bbox("arcs")
        return droite - gauche

    assert abs(largeur(fort) - largeur(calme)) <= 2


# --------------------------------------------------------------------------
# Ce que l'interface doit montrer, et ne pas montrer
# --------------------------------------------------------------------------
def source() -> str:
    return (RACINE / "gui.py").read_text(encoding="utf-8")


def test_l_acronyme_est_affiche():
    assert '"A.L.M.A"' in source()


def test_le_plein_ecran_est_demande():
    assert '"-fullscreen"' in source()


def test_l_historique_n_est_pas_affiche_au_depart():
    """
    Le panneau est construit au démarrage — il se remplit même caché — mais
    il n'est posé que sur demande. S'il était `pack` à la construction, il
    serait visible d'emblée.
    """
    texte = source()
    construction = texte[texte.index("def _construire("):texte.index("def basculer_historique(")]
    assert "self.panneau.pack(" not in construction
    assert "self.panneau.place(" not in construction


def test_le_panneau_pousse_la_colonne_au_lieu_de_la_couvrir():
    """
    En superposition, il masquait le bouton « Quitter » et la fin de la
    phrase entendue. `before` est ce qui garantit qu'il obtient sa largeur
    face à une colonne qui s'étend.
    """
    texte = source()
    bascule = texte[texte.index("def basculer_historique("):
                    texte.index("def _rafraichir_bouton_historique(")]
    assert "before=self.colonne" in bascule


def test_on_peut_sortir_du_plein_ecran():
    """Sans barre de titre, il ne resterait aucune prise sur la fenêtre."""
    assert '"<Escape>"' in source()


def test_l_orbe_n_a_plus_de_taille_fixe():
    """Garde-fou : une constante de taille reviendrait à figer l'orbe."""
    assert "TAILLE = " not in source()


# --------------------------------------------------------------------------
# Se rendormir sans avoir à le dire
# --------------------------------------------------------------------------
# Le « stop » vocal reste le chemin principal, mais il dépend de la
# transcription d'un ordre d'un seul mot -- celui que la reconnaissance rate
# le plus. Il faut donc un geste qui marche à tous les coups.
def test_l_orbe_se_clique():
    texte = source()
    assert 'self.orbe.bind("<Button-1>", self.basculer_veille)' in texte
    assert 'self.orbe.configure(cursor="hand2")' in texte


def test_la_barre_d_espace_rendort():
    bascule = source()
    debut = bascule.index("def _sur_touche(")
    assert 'evenement.keysym == "space"' in bascule[debut:debut + 600]


def test_echap_sort_d_abord_du_plein_ecran():
    """
    Sans barre de titre, Échap est la seule prise sur la fenêtre : elle
    garde ce rôle en priorité, et ne rendort qu'une fois hors plein écran.
    """
    texte = source()
    corps = texte[texte.index("def _sur_echap("):texte.index("def endormir(")]
    assert corps.index("self._plein_ecran(False)") < corps.index("self.endormir()")


class MoteurFactice:
    def __init__(self, arme=True):
        self.arme = arme

    def armer(self):
        self.arme = True

    def desarmer(self):
        self.arme = False


class AssistantFactice:
    def __init__(self):
        self.gestes = []

    def interrompre(self):
        self.gestes.append("interrompre")
        return False

    def interrompre_parole(self):
        self.gestes.append("parole")

    def oublier_contexte(self):
        self.gestes.append("contexte")


def application_factice(arme=True, micro=True):
    """Juste ce qu'il faut pour exercer la mise en veille, sans Tkinter."""
    import queue
    import threading

    from gui import AlmaApp

    faux = AlmaApp.__new__(AlmaApp)
    faux.moteur = MoteurFactice(arme)
    faux.assistant = AssistantFactice()
    faux.evenements = queue.Queue()
    faux.ecoute_active = threading.Event()
    if micro:
        faux.ecoute_active.set()
    return faux


def test_endormir_coupe_tout_et_oublie_le_contexte():
    faux = application_factice()
    faux.endormir()
    assert faux.moteur.arme is False
    assert faux.assistant.gestes == ["interrompre", "parole", "contexte"]


def test_le_clic_sur_l_orbe_reveille_aussi():
    """Le même geste dans les deux sens, sans prononcer le nom."""
    faux = application_factice(arme=False)
    faux.basculer_veille()
    assert faux.moteur.arme is True
    faux.basculer_veille()
    assert faux.moteur.arme is False


def test_le_clic_ne_reveille_pas_un_micro_coupe():
    faux = application_factice(arme=False, micro=False)
    faux.basculer_veille()
    assert faux.moteur.arme is False
