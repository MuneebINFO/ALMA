"""
Le premier lancement : quatre questions, une fois.

À l'installation ALMA ne sait rien de l'utilisateur. Il demande — puis ne
redemande plus jamais, et tout ce qui a été choisi se change ensuite d'une
phrase (voir tests/test_personnalisation.py).

Ce qui est vérifié ici : que les questions se posent, que la langue choisie
emmène les suivantes avec elle, que chaque réponse est appliquée tout de
suite ET retenue, et qu'au lancement suivant l'installation ne revient pas.
"""

import pytest

from config import load_config
from core import premier_lancement as pl


def relire(assistant):
    """La configuration telle qu'elle serait au prochain lancement."""
    return load_config(preferences_file=assistant.preferences.chemin)


def poser(assistant, reponses):
    """Joue les quatre réponses, dans l'ordre, et rend ce qui a été affiché."""
    suite = iter(reponses)
    affiche = []
    pl.poser_en_texte(assistant, lambda _invite: next(suite), affiche.append)
    return "\n".join(affiche)


# --------------------------------------------------------------------------
# Quand cela se déclenche
# --------------------------------------------------------------------------
def test_a_l_installation_les_questions_se_posent(assistant):
    assert pl.est_necessaire(assistant.config) is True


def test_une_fois_fait_cela_ne_revient_plus(assistant):
    poser(assistant, ["1", "Muneeb", "Jarvis", "1"])
    assert pl.est_necessaire(assistant.config) is False
    # Et surtout au lancement SUIVANT : c'est là que ça se verrait.
    assert relire(assistant).get("general.setup_done") is True


def test_tout_passer_compte_quand_meme_comme_fait(assistant):
    """Sinon « Passer » ne servirait à rien : la question reviendrait."""
    poser(assistant, ["", "", "", ""])
    assert pl.est_necessaire(assistant.config) is False
    # Rien n'a été imposé : les valeurs par défaut tiennent.
    assert assistant.name == "ALMA"
    assert assistant.config.get("general.user_name") == ""


# --------------------------------------------------------------------------
# Ce que les réponses produisent
# --------------------------------------------------------------------------
def test_les_quatre_reponses_sont_appliquees_et_retenues(assistant):
    poser(assistant, ["2", "Muneeb", "Jarvis", "2"])

    assert assistant.config.get("general.language") == "en"
    assert assistant.config.get("general.user_name") == "Muneeb"
    assert assistant.name == "Jarvis"
    assert assistant.config.get("voice.neural_voice") == "en-US-GuyNeural"

    apres = relire(assistant)
    assert apres.get("general.language") == "en"
    assert apres.get("general.user_name") == "Muneeb"
    assert apres.get("general.assistant_name") == "Jarvis"
    assert apres.get("voice.neural_voice") == "en-US-GuyNeural"


def test_le_nom_choisi_reveille_tout_de_suite(assistant):
    """Pas au prochain lancement : le moteur d'écoute est reconfiguré."""
    poser(assistant, ["1", "", "Jarvis", "1"])
    assert assistant.moteur.est_mot_appel("jarvis") is True
    assert assistant.moteur.est_mot_appel("alma") is False


def test_la_langue_choisie_emmene_l_ecoute_et_la_voix(assistant):
    poser(assistant, ["2", "", "", "1"])
    assert assistant.config.get("voice.stt_language") == "en-US"
    assert assistant.config.get("voice.neural_voice").startswith("en-")


def test_les_questions_suivantes_passent_dans_la_langue_choisie(assistant):
    """C'est pour cela que la langue est demandée en premier."""
    affiche = poser(assistant, ["2", "", "", "1"])
    assert "What should I call you?" in affiche
    assert "Comment dois-je vous appeler ?" not in affiche

    autre = poser(assistant, ["1", "", "", "1"])
    assert "Comment dois-je vous appeler ?" in autre


def test_la_langue_choisie_devient_le_repli_des_phrases_sans_indice(assistant):
    """
    « call me Sarah » ne contient aucun mot exclusivement anglais. Sans ce
    repli, un anglophone se ferait répondre en français une phrase sur trois.
    """
    poser(assistant, ["2", "", "", "1"])
    assert "Got it" in assistant.handle("call me Sarah").text


def test_la_majuscule_est_rendue_aux_noms(assistant):
    poser(assistant, ["1", "muneeb", "jarvis", "1"])
    assert assistant.config.get("general.user_name") == "Muneeb"
    assert assistant.name == "Jarvis"


def test_un_nom_trop_court_laisse_le_nom_en_place(assistant):
    """On ne bloque pas l'installation pour si peu : on garde ALMA."""
    poser(assistant, ["1", "", "Al", "1"])
    assert assistant.name == "ALMA"


def test_le_mot_de_fin_nomme_l_assistant(assistant):
    affiche = poser(assistant, ["1", "", "Jarvis", "1"])
    assert "Jarvis" in affiche.splitlines()[-1]


# --------------------------------------------------------------------------
# Comment une réponse est lue
# --------------------------------------------------------------------------
@pytest.mark.parametrize("saisie,attendu", [
    ("1", "fr"), ("2", "en"),
    ("Français", "fr"), ("english", "en"), ("EN", "en"),
    ("", ""),            # passer
    ("42", ""),          # hors liste : on passe plutôt que d'insister
    ("n'importe quoi", ""),
])
def test_une_question_fermee_accepte_le_numero_ou_le_mot(saisie, attendu):
    assert pl._lire_reponse(pl.PAR_CLE["langue"], saisie) == attendu


def test_une_question_libre_prend_ce_qui_est_tape():
    assert pl._lire_reponse(pl.PAR_CLE["nom_assistant"], "  Jarvis  ") == "Jarvis"


# --------------------------------------------------------------------------
# Le catalogue des questions
# --------------------------------------------------------------------------
def test_la_langue_est_demandee_en_premier():
    assert pl.QUESTIONS[0].cle == "langue"


def test_il_y_a_peu_de_questions():
    """Un formulaire avant de servir à quoi que ce soit se fait fermer."""
    assert len(pl.QUESTIONS) <= 5


def test_chaque_question_est_ecrite_dans_les_deux_langues():
    for question in pl.QUESTIONS:
        assert question.titre("fr") and question.titre("en"), question.cle
        for possible in question.choix:
            assert possible.libelle("fr") and possible.libelle("en")


def test_chaque_reponse_ne_touche_que_des_reglages_personnalisables(assistant):
    """Le premier lancement passe par la même liste blanche que le reste."""
    from core.preferences import PAR_CHEMIN

    for question in pl.QUESTIONS:
        valeur = question.choix[0].valeur if question.choix else "Test"
        for chemin in pl.reglages_pour(question.cle, valeur, assistant.config):
            assert chemin in PAR_CHEMIN, chemin


def test_le_drapeau_de_fin_est_retenu_comme_le_reste(assistant):
    pl.terminer(assistant)
    assert assistant.preferences.charger().get(pl.CLE_TERMINE) is True


def test_tout_oublier_repose_les_questions(assistant, monkeypatch):
    """Revenir aux réglages d'origine, c'est revenir avant l'installation."""
    monkeypatch.setattr(assistant, "confirm", lambda *a, **k: True)
    poser(assistant, ["1", "Muneeb", "Jarvis", "1"])
    assert pl.est_necessaire(assistant.config) is False

    assistant.handle("oublie mes préférences")
    assert pl.est_necessaire(assistant.config) is True
    assert assistant.name == "ALMA"


# --------------------------------------------------------------------------
# Le panneau graphique pose LES MÊMES questions
# --------------------------------------------------------------------------
def test_l_interface_ne_tient_pas_une_deuxieme_liste():
    """
    Deux listes de questions divergeraient. Le panneau graphique lit
    `premier_lancement.QUESTIONS`, comme le mode texte.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "gui.py").read_text(
        encoding="utf-8")
    assert "premier_lancement.QUESTIONS" in source
    assert "premier_lancement.repondre" in source


def test_l_ecoute_ne_demarre_qu_apres_les_questions():
    """
    Sinon ALMA répondrait aux réponses qu'on lui donne — et il ne saurait
    toujours pas comment s'appeler.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "gui.py").read_text(
        encoding="utf-8")
    lancement = source[source.index("if app.installation_necessaire():"):]
    assert "montrer_installation(demarrer)" in lancement[:400]


def panneau_factice(tk_root, assistant):
    """
    De quoi exercer le panneau du premier lancement sans ouvrir la vraie
    fenêtre : les widgets sont réels, le reste de l'application ne l'est pas.
    """
    import tkinter as tk

    from gui import FOND, AlmaApp

    faux = AlmaApp.__new__(AlmaApp)
    faux.root = tk_root
    faux.assistant = assistant
    faux.nom = assistant.name
    faux.corps = tk.Frame(tk_root, bg=FOND)
    faux.colonne = tk.Frame(faux.corps, bg=FOND)
    faux.colonne.pack(side="left", fill="both", expand=True)
    faux.panneau = tk.Frame(faux.corps, bg=FOND)
    faux.historique_visible = False
    faux.installation = None
    faux._suite_installation = None
    faux.journalise = []
    faux.journaliser = lambda qui, texte, tag="assistant": faux.journalise.append(texte)
    return faux


def test_le_panneau_se_dessine_et_se_parcourt(tk_root, assistant):
    """
    Un panneau qui plante le fait au TOUT premier lancement, chez quelqu'un
    qui découvre l'application : c'est le pire endroit possible.
    """
    faux = panneau_factice(tk_root, assistant)
    fini = []
    faux.montrer_installation(lambda: fini.append(True))
    assert faux.installation is not None, "le panneau doit remplacer l'orbe"
    assert faux.colonne not in faux.corps.pack_slaves(), "l'orbe doit être retiré"

    for reponse in ("en", "Muneeb", "Jarvis", "homme"):
        assert faux.installation is not None, "il restait des questions"
        faux._repondre(reponse)

    assert fini == [True], "l'écoute doit démarrer à la fin"
    assert faux.installation is None, "le panneau doit être rangé"
    assert assistant.name == "Jarvis"
    assert assistant.config.get("general.user_name") == "Muneeb"
    assert faux.journalise and "Jarvis" in faux.journalise[-1]


def test_le_panneau_se_dessine_dans_les_deux_langues(tk_root, assistant):
    faux = panneau_factice(tk_root, assistant)
    faux.montrer_installation(lambda: None)
    faux._repondre("en")            # la suite doit basculer en anglais
    textes = [enfant.cget("text")
              for cadre in faux.installation.winfo_children()
              for enfant in cadre.winfo_children()
              if enfant.winfo_class() == "Label"]
    assert any("What should I call you?" in t for t in textes), textes
