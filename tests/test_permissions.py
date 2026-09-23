"""
Les autorisations Windows : micro et caméra.

CE FICHIER EXISTE À CAUSE D'UN REFUS DU STORE. La certification a renvoyé
« Unusable Feature: Voice commands », testée sur une machine neuve avec une
connexion établie. Rien n'était cassé : Windows refusait le micro à
l'application empaquetée, et PortAudio rend alors du SILENCE — pas une
erreur. `available` restait vrai, le flux s'ouvrait, l'orbe tournait, et
aucune voix n'arrivait jamais.

Personne ne disait à l'utilisateur ce qui se passait. C'est la règle 6 — le
silence doit se distinguer d'une panne — appliquée au cas auquel personne
n'avait pensé : le silence venu d'une case à cocher dans Windows.

Ces tests gardent le message. Sans lui, la même panne reviendra à
l'identique, et elle ressemblera de nouveau à une application cassée.
"""

import queue

import pytest

from core import permissions


# --------------------------------------------------------------------------
# Le module lui-même
# --------------------------------------------------------------------------
# Le fixture `aucune_trace_sur_la_machine` double ces trois fonctions, pour
# que la suite ne dépende pas des réglages de la machine. Ici, ce sont elles
# qu'on éprouve : on les capture à l'import, avant les doublures, et
# `vraies_fonctions` les remet en place.
VRAI_ETAT = permissions.etat
VRAIE_EXPLICATION = permissions.explication
VRAI_UTILISABLE = permissions.utilisable


@pytest.fixture
def vraies_fonctions(monkeypatch):
    """Les vraies `explication` et `utilisable`, par-dessus les doublures."""
    monkeypatch.setattr(permissions, "explication", VRAIE_EXPLICATION)
    monkeypatch.setattr(permissions, "utilisable", VRAI_UTILISABLE)


def test_l_etat_reel_se_lit_sans_lever():
    """
    Lancé depuis les sources, hors paquet, rien de tout cela ne s'applique —
    mais l'appel ne doit jamais lever, sinon ALMA ne démarrerait pas.
    """
    etat = VRAI_ETAT(permissions.MICRO)

    assert etat in (permissions.AUTORISE, permissions.REFUSE_UTILISATEUR,
                    permissions.REFUSE_SYSTEME, permissions.NON_DECLARE,
                    permissions.A_DEMANDER, permissions.INCONNU)


def test_un_etat_illisible_ne_bloque_rien(vraies_fonctions, monkeypatch):
    """
    Si l'API n'est pas joignable, on laisse l'essai avoir lieu. Bloquer sur
    une supposition rendrait ALMA inutilisable là où elle marchait très bien.
    """
    monkeypatch.setattr(permissions, "etat",
                        lambda capacite: permissions.INCONNU)

    assert permissions.utilisable(permissions.MICRO) is True
    assert permissions.explication(permissions.MICRO) == ""


def test_a_demander_n_est_pas_un_refus(vraies_fonctions, monkeypatch):
    """Windows n'a pas encore posé la question : ce n'est pas un « non »."""
    monkeypatch.setattr(permissions, "etat",
                        lambda capacite: permissions.A_DEMANDER)

    assert permissions.utilisable(permissions.MICRO) is True


@pytest.mark.parametrize("refus", [
    permissions.REFUSE_UTILISATEUR,
    permissions.REFUSE_SYSTEME,
    permissions.NON_DECLARE,
])
def test_un_refus_franc_arrete_tout(vraies_fonctions, monkeypatch, refus):
    monkeypatch.setattr(permissions, "etat", lambda capacite: refus)

    assert permissions.utilisable(permissions.MICRO) is False
    assert permissions.explication(permissions.MICRO), refus


def test_chaque_refus_nomme_un_geste_different(vraies_fonctions, monkeypatch):
    """
    « Autorisez ALMA » et « rallumez le micro pour toutes les applications »
    ne sont pas le même geste. Les confondre fait chercher au mauvais endroit.
    """
    messages = {}
    for refus in (permissions.REFUSE_UTILISATEUR, permissions.REFUSE_SYSTEME,
                  permissions.NON_DECLARE):
        monkeypatch.setattr(permissions, "etat", lambda capacite, r=refus: r)
        messages[refus] = permissions.explication(permissions.MICRO)

    assert len(set(messages.values())) == 3, messages


def test_les_explications_sont_bilingues(vraies_fonctions, monkeypatch):
    monkeypatch.setattr(permissions, "etat",
                        lambda capacite: permissions.REFUSE_UTILISATEUR)

    fr = permissions.explication(permissions.MICRO, "fr")
    en = permissions.explication(permissions.MICRO, "en")

    assert fr != en
    assert "Windows" in fr and "Windows" in en


def test_le_micro_et_la_camera_ne_disent_pas_la_meme_chose(vraies_fonctions,
                                                               monkeypatch):
    monkeypatch.setattr(permissions, "etat",
                        lambda capacite: permissions.REFUSE_UTILISATEUR)

    assert (permissions.explication(permissions.MICRO)
            != permissions.explication(permissions.CAMERA))


def test_chaque_capacite_a_sa_page_de_reglages():
    """Y emmener vaut mieux que décrire un chemin dans six menus."""
    assert permissions.REGLAGES[permissions.MICRO].startswith("ms-settings:")
    assert permissions.REGLAGES[permissions.CAMERA].startswith("ms-settings:")
    assert permissions.REGLAGES[permissions.MICRO] != permissions.REGLAGES[permissions.CAMERA]


# --------------------------------------------------------------------------
# Le démarrage de l'écoute : LE défaut trouvé par la certification
# --------------------------------------------------------------------------
def panneau_factice(tk_root, assistant):
    import tkinter as tk

    from gui import FOND, AlmaApp

    faux = AlmaApp.__new__(AlmaApp)
    faux.root = tk_root
    faux.assistant = assistant
    faux.nom = assistant.name
    faux.corps = tk.Frame(tk_root, bg=FOND)
    faux.colonne = tk.Frame(faux.corps, bg=FOND)
    faux.installation = None
    faux.abonnement = None
    faux._champ_cle = None
    faux._etat_cle = None
    faux.stt = None
    faux.thread_audio = None
    faux.evenements = queue.Queue()
    import threading
    faux.ecoute_active = threading.Event()
    return faux


def evenements(faux):
    vus = []
    while not faux.evenements.empty():
        vus.append(faux.evenements.get())
    return vus


def test_un_micro_refuse_le_dit_au_lieu_de_se_taire(tk_root, assistant,
                                                    monkeypatch):
    """
    LE test de ce fichier.

    Sans lui, ALMA ouvre le flux, l'orbe tourne, et aucune voix n'arrive
    jamais — ce que la certification a vu et refusé. Le message doit partir,
    et l'écoute ne doit PAS démarrer.
    """
    monkeypatch.setattr(
        permissions, "explication",
        lambda capacite, langue="fr": "Windows bloque le micro pour ALMA.")

    faux = panneau_factice(tk_root, assistant)
    faux.demarrer_ecoute()

    vus = evenements(faux)
    textes = " ".join(str(charge) for _genre, charge in vus)
    assert "bloque le micro" in textes, vus
    assert any(genre == "erreur" for genre, _c in vus), vus
    assert not faux.ecoute_active.is_set(), \
        "l'écoute a démarré alors que Windows refuse le micro"
    assert faux.thread_audio is None, "un thread micro a été lancé pour rien"


def test_le_message_dit_ou_aller_et_comment_reessayer(tk_root, assistant,
                                                      monkeypatch):
    """
    Un diagnostic sans geste à faire ne vaut guère mieux que le silence.
    """
    monkeypatch.setattr(permissions, "explication",
                        lambda capacite, langue="fr": "Windows bloque le micro.")

    faux = panneau_factice(tk_root, assistant)
    faux.demarrer_ecoute()

    textes = " ".join(str(c) for _g, c in evenements(faux))
    assert "Confidentialité" in textes or "Privacy" in textes, textes
    assert "M " in textes or "M." in textes, textes


def test_windows_est_interroge_avant_qu_on_ouvre_le_micro(tk_root, assistant,
                                                          monkeypatch):
    """
    L'ordre compte : demander après avoir ouvert le flux ne servirait à
    rien, puisque PortAudio réussit et rend du silence.
    """
    ordre = []
    monkeypatch.setattr(permissions, "explication",
                        lambda capacite, langue="fr":
                        ordre.append("autorisation") or "Refusé.")

    faux = panneau_factice(tk_root, assistant)

    class MicroInterdit:
        def __init__(self, *a, **k):
            ordre.append("micro")

    monkeypatch.setattr("core.stt.SpeechToText", MicroInterdit)
    faux.demarrer_ecoute()

    assert ordre == ["autorisation"], ordre


def test_une_autorisation_jamais_demandee_est_demandee(tk_root, assistant,
                                                       monkeypatch):
    """
    « A demander » veut dire que Windows n'a jamais posé la question. On la
    lui fait poser — c'est lui qui affiche l'invite, pas nous.
    """
    demandes = []
    monkeypatch.setattr(permissions, "etat",
                        lambda capacite: permissions.A_DEMANDER)
    monkeypatch.setattr(permissions, "demander",
                        lambda capacite: demandes.append(capacite)
                        or permissions.AUTORISE)

    # L'autorisation accordée, `demarrer_ecoute` va jusqu'au bout — et sans
    # cette doublure il construit un VRAI SpeechToText, ouvre le micro de qui
    # lance la suite, et lance le thread d'écoute. Règle 4 : un test ne laisse
    # aucune trace sur la machine, micro allumé compris.
    class MicroFactice:
        available = True
        error = ""

    monkeypatch.setattr("core.stt.SpeechToText", lambda *a, **k: MicroFactice())
    monkeypatch.setattr("threading.Thread.start", lambda self: None)

    faux = panneau_factice(tk_root, assistant)
    faux.demarrer_ecoute()

    assert demandes == [permissions.MICRO], demandes


# --------------------------------------------------------------------------
# Le filet : un micro autorisé qui n'entend rien quand même
# --------------------------------------------------------------------------
# L'autorisation traite la cause la plus probable. Celui-ci traite TOUTES les
# autres d'un coup — micro coupé matériellement, volume à zéro, mauvais
# périphérique par défaut, pilote muet — en mesurant ce qui arrive vraiment
# plutôt qu'en devinant pourquoi rien n'arrive.
def capteur_de_niveau(tk_root, assistant, monkeypatch, niveaux, avance=0.0):
    """Joue la boucle micro sur une suite de niveaux, sans toucher au matériel."""
    import gui as module

    faux = panneau_factice(tk_root, assistant)
    horloge = {"t": 0.0}
    monkeypatch.setattr(module.time, "monotonic", lambda: horloge["t"])

    class MicroFactice:
        available = True
        error = ""

        def recalibrate(self, _duree, on_level=None):
            for niveau in niveaux:
                horloge["t"] += avance
                if on_level:
                    on_level(niveau, "repos")
            raise StopIteration            # on s'arrête après la calibration

    faux.stt = MicroFactice()
    try:
        faux._boucle_micro()
    except StopIteration:
        pass
    return faux


def test_un_micro_muet_finit_par_le_dire(tk_root, assistant, monkeypatch):
    """
    Vingt secondes de niveau strictement nul : ALMA doit le signaler, au
    lieu de laisser tourner l'orbe indéfiniment.
    """
    faux = capteur_de_niveau(tk_root, assistant, monkeypatch,
                             niveaux=[0.0] * 5, avance=6.0)

    textes = " ".join(str(c) for _g, c in evenements(faux))
    assert "absolument rien" in textes, textes


def test_un_micro_qui_entend_ne_se_plaint_pas(tk_root, assistant, monkeypatch):
    """
    Le bruit de fond suffit : dès qu'un niveau non nul arrive, il n'y a plus
    rien à signaler, même si personne ne parle.
    """
    faux = capteur_de_niveau(tk_root, assistant, monkeypatch,
                             niveaux=[0.0, 0.00002, 0.0, 0.0, 0.0], avance=6.0)

    textes = " ".join(str(c) for _g, c in evenements(faux))
    assert "absolument rien" not in textes, textes


def test_on_ne_previent_pas_avant_d_avoir_attendu(tk_root, assistant, monkeypatch):
    """Un démarrage tranquille de quelques secondes ne doit rien déclencher."""
    faux = capteur_de_niveau(tk_root, assistant, monkeypatch,
                             niveaux=[0.0] * 5, avance=1.0)

    textes = " ".join(str(c) for _g, c in evenements(faux))
    assert "absolument rien" not in textes, textes


def test_on_ne_previent_qu_une_fois(tk_root, assistant, monkeypatch):
    """
    Répéter ferait du bruit par-dessus un problème qu'on vient de signaler.
    """
    faux = capteur_de_niveau(tk_root, assistant, monkeypatch,
                             niveaux=[0.0] * 12, avance=6.0)

    textes = [str(c) for _g, c in evenements(faux)]
    plaintes = [t for t in textes if "absolument rien" in t]
    assert len(plaintes) == 1, plaintes


def test_le_message_atteint_l_ECRAN_pas_seulement_le_journal(tk_root, assistant,
                                                              monkeypatch):
    """
    LE test qui manquait, et son absence a coûté cher.

    Les tests plus haut vérifient que l'événement « erreur » PART. Aucun ne
    vérifiait que quelqu'un le VOIT — et le jour où le bouton d'historique a
    été retiré de l'écran, le message est parti dans un panneau que plus
    personne ne pouvait ouvrir. Le paquet installé montrait alors l'orbe qui
    tourne et rien d'autre : exactement la panne muette que ce message
    servait à éviter, et exactement ce que la certification avait refusé.

    Une erreur doit atterrir sur une étiquette VISIBLE de la fenêtre.
    """
    import tkinter as tk

    from gui import ETATS

    faux = panneau_factice(tk_root, assistant)
    faux.etiquette_entendu = tk.Label(faux.corps, text="")
    faux.journalise = []
    faux.journaliser = lambda qui, texte, tag="assistant": \
        faux.journalise.append(texte)

    faux.evenements.put(("erreur", "Windows bloque le micro pour ALMA."))
    faux._traiter_evenements(boucler=False)

    assert faux.etiquette_entendu.cget("text") == "Windows bloque le micro pour ALMA.", \
        "l'erreur n'atteint pas l'écran"
    assert faux.etiquette_entendu.cget("fg") == ETATS["erreur"][0]


def test_une_erreur_affichee_s_efface_quand_la_suite_arrive(tk_root, assistant):
    """
    Sinon elle reste à l'écran par-dessus une situation qui n'a plus rien à
    voir — et on cherche un problème réglé depuis longtemps.
    """
    import tkinter as tk

    from gui import TEXTE

    faux = panneau_factice(tk_root, assistant)
    faux.etiquette_entendu = tk.Label(faux.corps, text="")
    faux.journaliser = lambda *a, **k: None

    faux.evenements.put(("erreur", "Micro bloqué."))
    faux._traiter_evenements(boucler=False)
    faux.evenements.put(("entendu", "quelle heure est-il"))
    faux._traiter_evenements(boucler=False)

    assert "heure" in faux.etiquette_entendu.cget("text")
    assert faux.etiquette_entendu.cget("fg") == TEXTE


# La zone d'affichage sous l'orbe réserve DEUX lignes. Le message complet doit
# y tenir : la première version en faisait trois, et la dernière passait sous
# la barre du bas — vu sur le paquet installé, pas en test.
LONGUEUR_MAX_MESSAGE = 110


@pytest.mark.parametrize("refus", [
    permissions.REFUSE_UTILISATEUR,
    permissions.REFUSE_SYSTEME,
    permissions.NON_DECLARE,
])
@pytest.mark.parametrize("langue", ["fr", "en"])
def test_le_message_tient_dans_la_place_reservee(vraies_fonctions, monkeypatch,
                                                 refus, langue):
    monkeypatch.setattr(permissions, "etat", lambda capacite: refus)

    suite = ("Settings > Privacy > Microphone, then press M." if langue == "en"
             else "Paramètres > Confidentialité > Microphone, puis M.")
    complet = permissions.explication(permissions.MICRO, langue) + " " + suite

    assert len(complet) <= LONGUEUR_MAX_MESSAGE, (len(complet), complet)


def test_le_diagnostic_ne_repete_pas_le_chemin(vraies_fonctions, monkeypatch):
    """
    L'explication DIAGNOSTIQUE ; le chemin vers les réglages est ajouté par
    qui affiche. Les deux ensemble disaient la même chose deux fois.
    """
    monkeypatch.setattr(permissions, "etat",
                        lambda capacite: permissions.REFUSE_UTILISATEUR)

    message = permissions.explication(permissions.MICRO)

    assert "Paramètres" not in message, message
    assert "confidentialité" not in message.lower(), message
