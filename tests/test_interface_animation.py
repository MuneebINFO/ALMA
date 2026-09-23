"""
Les animations de l'interface : le fondu au lancement, et l'historique qui
glisse au lieu de surgir — l'orbe rétrécissant avec lui.

Une racine Tk unique et invisible pour tout le module, une AlmaApp construite
une fois, et surtout AUCUNE boucle d'événements : les tests appellent les
méthodes directement, donc les `after` planifiés ne se déclenchent jamais. On
mesure les effets SYNCHRONES, qui sont déterministes.
"""

import tkinter as tk  # noqa: F401  (utilise via isinstance dans un test)

import pytest

import gui


@pytest.fixture(scope="module")
def app(tk_root, config):
    from core.assistant import Assistant

    class Muet:
        available = False
        voices: list = []
        error = ""
        moteur_actif = "aucun"

        def say(self, *a, **k):
            pass

        def wait(self, *a, **k):
            pass

        def list_voices(self):
            return []

        def shutdown(self):
            pass

        def parle(self):
            return False

    class SansEntree:
        source = "text"

        def read(self, prompt=""):
            return ""

        def write(self, texte):
            pass

        def ask(self, question):
            return "non"

        def close(self):
            pass

    return gui.AlmaApp(tk_root, Assistant(config=config, io=SansEntree(), tts=Muet()))


@pytest.fixture(autouse=True)
def _repartir_ferme(app):
    """Chaque test part d'un historique fermé, sans animation en vol."""
    if app._animation_historique is not None:
        app.root.after_cancel(app._animation_historique)
    app._animation_historique = None
    app.historique_visible = False
    app._largeur_panneau = 0
    app.panneau.pack_forget()
    app.panneau.configure(width=0)
    yield
    if app._animation_historique is not None:
        app.root.after_cancel(app._animation_historique)
        app._animation_historique = None


# --------------------------------------------------------------------------
# L'assouplissement, commun aux deux animations
# --------------------------------------------------------------------------
def test_assouplir_va_de_zero_a_un():
    assert gui._assouplir(0.0) == 0.0
    assert gui._assouplir(1.0) == 1.0


def test_assouplir_est_monotone_et_ralentit():
    valeurs = [gui._assouplir(i / 20) for i in range(21)]
    assert valeurs == sorted(valeurs)
    increments = [b - a for a, b in zip(valeurs, valeurs[1:])]
    # Ease-out : le premier bond est le plus grand, le dernier le plus petit.
    assert increments[0] > increments[-1]


# --------------------------------------------------------------------------
# Le fondu au lancement
# --------------------------------------------------------------------------
def test_la_fenetre_part_invisible():
    """Sans quoi elle apparaîtrait pleine opacité avant le fondu."""
    source = open(gui.__file__, encoding="utf-8").read()
    debut = source.index("class AlmaApp")
    init = source[debut:source.index("def _construire(")]
    assert '"-alpha", 0.0' in init


def test_le_fondu_avance_par_paliers_intermediaires(app):
    """Le premier palier doit être entre transparent et opaque, pas à 1."""
    app.root.attributes("-alpha", 0.0)
    app._animer_entree(0)
    alpha = float(app.root.attributes("-alpha"))
    assert 0.0 < alpha < 1.0


def test_le_fondu_finit_opaque(app):
    for pas in range(gui.PAS_ENTREE):
        app._animer_entree(pas)
    assert float(app.root.attributes("-alpha")) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# L'historique qui glisse
# --------------------------------------------------------------------------
def test_la_largeur_progresse_du_depart_a_la_cible(app):
    valeurs = [app._largeur_historique_au_pas(0, gui.LARGEUR_HISTORIQUE, pas)
               for pas in range(gui.PAS_HISTORIQUE)]
    assert valeurs[-1] == gui.LARGEUR_HISTORIQUE
    assert valeurs == sorted(valeurs), "chaque image avance, jamais ne recule"
    assert len(set(valeurs)) > 1, "une suite d'images, pas un seul saut"
    assert 0 < valeurs[0] < gui.LARGEUR_HISTORIQUE, "le premier pas n'est pas la cible"


def test_le_glissement_ralentit_en_approchant(app):
    valeurs = [app._largeur_historique_au_pas(0, gui.LARGEUR_HISTORIQUE, pas)
               for pas in range(gui.PAS_HISTORIQUE)]
    increments = [b - a for a, b in zip(valeurs, valeurs[1:])]
    assert increments[0] > increments[-1]


def test_ouvrir_pose_le_panneau_sans_sauter_a_sa_largeur(app):
    """
    Le défaut à corriger : `pack()` posait le panneau à pleine largeur et
    l'orbe rétrécissait d'un bloc. Le premier appel s'arrête à mi-chemin.
    """
    app.basculer_historique()
    assert app.historique_visible is True
    assert app.panneau.winfo_manager() == "pack"
    assert 0 < app._largeur_panneau < gui.LARGEUR_HISTORIQUE


def test_fermer_retire_le_panneau_seulement_a_la_derniere_image(app):
    app.historique_visible = True
    app._largeur_panneau = gui.LARGEUR_HISTORIQUE
    app.panneau.configure(width=gui.LARGEUR_HISTORIQUE)
    app.panneau.pack(side="right", fill="y", before=app.colonne)

    for pas in range(gui.PAS_HISTORIQUE - 1):
        app._glisser_historique(gui.LARGEUR_HISTORIQUE, 0, pas)
        assert app.panneau.winfo_manager() == "pack", "encore posé, il glisse"

    app._glisser_historique(gui.LARGEUR_HISTORIQUE, 0, gui.PAS_HISTORIQUE - 1)
    assert app.panneau.winfo_manager() == "", "retiré à la fin"
    assert app._largeur_panneau == 0


def test_interrompre_l_ouverture_repart_d_ou_on_en_est(app):
    """Un double-clic : refermer avant la fin ne fait pas d'abord sauter à fond."""
    app.basculer_historique()                       # ouverture, une image
    largeur_a_l_interruption = app._largeur_panneau
    assert 0 < largeur_a_l_interruption < gui.LARGEUR_HISTORIQUE

    app.basculer_historique()                       # fermeture, avant la fin
    assert app.historique_visible is False
    # La fermeture démarre de la largeur courante, pas de LARGEUR_HISTORIQUE.
    assert app._largeur_panneau <= largeur_a_l_interruption


def test_le_second_appel_annule_l_animation_du_premier(app):
    """Sans l'annulation, deux animations tourneraient de front."""
    app.basculer_historique()
    premiere = app._animation_historique
    assert premiere is not None
    app.basculer_historique()
    assert app._animation_historique != premiere


# --------------------------------------------------------------------------
# L'orbe suit le mouvement
# --------------------------------------------------------------------------
def test_le_glissement_redimensionne_bien_le_panneau(app):
    """
    C'est le changement de largeur du panneau qui fait rétrécir la colonne,
    donc l'orbe : Tk recalcule la mise en page à chaque `configure(width=)`.
    """
    largeurs = []
    for pas in range(gui.PAS_HISTORIQUE):
        app._glisser_historique(0, gui.LARGEUR_HISTORIQUE, pas)
        largeurs.append(int(app.panneau.cget("width")))
    assert largeurs[0] < largeurs[-1]
    assert largeurs[-1] == gui.LARGEUR_HISTORIQUE


def test_l_orbe_ecoute_les_changements_de_taille(app):
    """L'autre moitié du mécanisme : l'orbe se recale sur son `<Configure>`."""
    assert app.orbe.bind("<Configure>"), "l'orbe ne suivrait plus la fenêtre"


# --------------------------------------------------------------------------
# Les boutons retirés, et leurs raccourcis de remplacement
# --------------------------------------------------------------------------
def test_la_barre_du_bas_ne_garde_que_l_essentiel(app):
    """
    Elle s'est vidée en trois fois, et chaque retrait avait sa raison.

    Micro et aide d'abord : l'un se demande à la voix, l'autre au clavier.
    Puis l'historique — il occupait la place la plus visible de l'écran pour
    quelque chose que personne ne consultait, et il vit maintenant dans le
    menu du compte.

    Ce qui reste : le compte à gauche, quitter à droite.
    """
    def libelles(widget):
        trouves = []
        for enfant in widget.winfo_children():
            if isinstance(enfant, tk.Button):
                trouves.append(enfant.cget("text"))
            trouves += libelles(enfant)
        return trouves

    textes = libelles(app.root)
    assert "Couper le micro" not in textes
    assert "Que sais-tu faire ?" not in textes
    assert "Historique" not in textes,         "l'historique est revenu occuper la barre du bas"
    assert "Abonnement" not in textes,         "l'abonnement se trouve dans le menu du compte, pas dans la barre"
    assert "Quitter" in textes


def test_le_bouton_du_compte_est_en_bas_a_gauche(app):
    """La pastille du compte est le seul point d'entrée de l'écran."""
    from gui import BoutonCompte

    def chercher(widget):
        for enfant in widget.winfo_children():
            if isinstance(enfant, BoutonCompte):
                return enfant
            trouve = chercher(enfant)
            if trouve is not None:
                return trouve
        return None

    bouton = chercher(app.root)
    assert bouton is not None, "le bouton du compte a disparu"
    assert bouton.pack_info()["side"] == "left"


def test_la_touche_m_bascule_le_micro(app, monkeypatch):
    appels = []
    monkeypatch.setattr(app, "basculer_micro", lambda: appels.append("m"))
    app._sur_touche(type("E", (), {"keysym": "m", "char": "m"})())
    app._sur_touche(type("E", (), {"keysym": "M", "char": "M"})())
    assert appels == ["m", "m"]


def test_la_touche_f1_montre_l_aide(app, monkeypatch):
    appels = []
    monkeypatch.setattr(app, "montrer_aide", lambda: appels.append("f1"))
    app._sur_touche(type("E", (), {"keysym": "F1", "char": ""})())
    assert appels == ["f1"]


def test_une_touche_ordinaire_ne_declenche_rien(app, monkeypatch):
    appels = []
    monkeypatch.setattr(app, "basculer_micro", lambda: appels.append("x"))
    monkeypatch.setattr(app, "montrer_aide", lambda: appels.append("x"))
    app._sur_touche(type("E", (), {"keysym": "a", "char": "a"})())
    assert appels == []
