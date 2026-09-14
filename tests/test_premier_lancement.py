"""
Le premier lancement : quatre questions, une fois.

À l'installation ALMA ne sait rien de l'utilisateur. Il demande — puis ne
redemande plus jamais, et tout ce qui a été choisi se change ensuite d'une
phrase (voir tests/test_personnalisation.py).

Ce qui est vérifié ici : que les questions se posent, que la langue choisie
emmène les suivantes avec elle, que chaque réponse est appliquée tout de
suite ET retenue, et qu'au lancement suivant l'installation ne revient pas.
"""

import time

import pytest

from config import load_config
from core import premier_lancement as pl


def relire(assistant):
    """La configuration telle qu'elle serait au prochain lancement."""
    return load_config(preferences_file=assistant.preferences.chemin)


def poser(assistant, reponses, entendu=None):
    """
    Joue les réponses aux questions à DÉCIDER, dans l'ordre, et rend ce qui a
    été affiché.

    Les étapes d'écoute (« dites-le à voix haute ») sont passées par défaut :
    elles confirment une réponse déjà donnée, et n'existent pas sans micro.
    `entendu={"ecoute_nom_assistant": "Djarvis"}` les fait répondre.
    """
    decisions = iter(reponses)
    entendu = entendu or {}
    affiche = []
    restantes = [q.cle for q in pl.QUESTIONS]

    def lire(_invite):
        cle = restantes.pop(0)
        if pl.PAR_CLE[cle].ecoute:
            return entendu.get(cle, "")
        return next(decisions)

    pl.poser_en_texte(assistant, lire, affiche.append)
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


def test_il_y_a_peu_de_choses_a_decider():
    """
    Un formulaire avant de servir à quoi que ce soit se fait fermer. Les
    étapes d'écoute ne comptent pas : elles ne demandent pas de décider, elles
    font répéter à voix haute une réponse déjà donnée.
    """
    assert len([q for q in pl.QUESTIONS if not q.ecoute]) <= 5


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
    faux._recevoir_entendu = None
    faux.boule = None
    # Un micro DÉCLARÉ indisponible, et non pas absent : `None` aurait fait
    # construire un vrai `SpeechToText`, donc ouvrir le micro de la machine.
    # Les étapes « dites-le à voix haute » se sautent alors d'elles-mêmes,
    # ce qui est le comportement attendu sans entrée audio.
    faux.stt = type("SansMicro", (), {"available": False})()
    faux.journalise = []
    faux.journaliser = lambda qui, texte, tag="assistant": faux.journalise.append(texte)
    return faux


def etiquettes(faux):
    """Tous les textes affichés dans le panneau, à n'importe quelle profondeur."""
    trouves = []

    def descendre(widget):
        for enfant in widget.winfo_children():
            if enfant.winfo_class() == "Label":
                trouves.append(enfant.cget("text"))
            descendre(enfant)

    descendre(faux.installation)
    return trouves


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

    for reponse in ("en", "Muneeb", "", "Jarvis", "", "homme"):
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
    textes = etiquettes(faux)
    assert any("What should I call you?" in t for t in textes), textes


# --------------------------------------------------------------------------
# On n'inscrit que ce qui a vraiment été choisi
# --------------------------------------------------------------------------
def test_passer_une_question_fermee_n_inscrit_rien(assistant):
    """
    Passer, ce n'est pas « prends le premier choix » : c'est « laisse comme
    c'est ». Sinon la valeur par défaut apparaîtrait ensuite dans « mes
    préférences » comme un choix que personne n'a fait.
    """
    poser(assistant, ["", "", "", ""])
    assert assistant.preferences.charger() == {pl.CLE_TERMINE: True}


def test_valider_le_nom_pre_rempli_n_inscrit_rien(assistant):
    """Le champ propose « ALMA » : le valider ne change rien."""
    poser(assistant, ["1", "", "ALMA", "1"])
    assert "general.assistant_name" not in assistant.preferences.charger()
    assert assistant.name == "ALMA"


def test_passer_la_voix_apres_avoir_choisi_l_anglais_garde_la_voix_anglaise(assistant):
    """Passer ne doit pas ramener la voix française choisie par la langue."""
    poser(assistant, ["2", "", "", ""])
    assert assistant.config.get("voice.neural_voice") == "en-US-AriaNeural"


def test_seul_ce_qui_change_est_retenu(assistant):
    poser(assistant, ["2", "Muneeb", "Jarvis", "2"])
    retenu = set(assistant.preferences.charger())
    assert retenu == {
        "general.language", "voice.stt_language", "voice.neural_voice",
        "general.user_name", "general.assistant_name", "general.wake_word",
        pl.CLE_TERMINE,
    }


# --------------------------------------------------------------------------
# « Dites-le à voix haute »
# --------------------------------------------------------------------------
# Un nom s'écrit rarement comme il s'entend : « Muneeb » revient en
# « Mounib », « Jarvis » en « Djarvis ». Le taper ne suffit donc pas — ALMA
# doit savoir sous quelle forme il lui parvient, sinon elle reste muette
# quand on l'appelle.
def test_le_nom_prononce_devient_une_variante_du_mot_dappel(assistant):
    poser(assistant, ["1", "", "Jarvis", "1"],
          entendu={"ecoute_nom_assistant": "Djarvis"})

    variantes = assistant.config.get("general.wake_variants")
    assert "djarvis" in variantes
    # Et le moteur d'écoute y répond TOUT DE SUITE.
    assert assistant.moteur.est_mot_appel("djarvis") is True
    assert assistant.moteur.est_mot_appel("jarvis") is True


def test_la_variante_du_mot_dappel_survit_au_redemarrage(assistant):
    poser(assistant, ["1", "", "Jarvis", "1"],
          entendu={"ecoute_nom_assistant": "Djarvis"})
    assert "djarvis" in relire(assistant).get("general.wake_variants")


def test_entendu_exactement_comme_ecrit_il_n_y_a_rien_a_retenir(assistant):
    """Une variante identique au nom n'apprend rien et encombrerait la liste."""
    poser(assistant, ["1", "", "Jarvis", "1"],
          entendu={"ecoute_nom_assistant": "Jarvis"})
    assert assistant.config.get("general.wake_variants") == []


def test_ne_rien_dire_passe_l_etape(assistant):
    poser(assistant, ["1", "", "Jarvis", "1"])
    assert assistant.config.get("general.wake_variants") == []
    assert pl.est_necessaire(assistant.config) is False


def test_le_prenom_prononce_protege_son_orthographe(assistant):
    """
    Le vrai effet, côté utilisateur : dire « appelle-moi Muneeb » après coup
    renvoie « Mounib » à la transcription. Sans la variante apprise, la bonne
    orthographe serait remplacée par la mauvaise.
    """
    poser(assistant, ["1", "Muneeb", "", "1"],
          entendu={"ecoute_nom_utilisateur": "Mounib"})
    assert "mounib" in assistant.config.get("general.user_name_variants")

    reponse = assistant.handle("appelle-moi Mounib")

    assert assistant.config.get("general.user_name") == "Muneeb", (
        "la forme entendue ne doit pas écraser celle qui a été écrite")
    assert "Muneeb" in reponse.text


def test_un_prenom_vraiment_different_change_bien_le_nom(assistant):
    """Le pendant : la protection ne doit pas empêcher de se renommer."""
    poser(assistant, ["1", "Muneeb", "", "1"],
          entendu={"ecoute_nom_utilisateur": "Mounib"})

    assistant.handle("appelle-moi Sarah")

    assert assistant.config.get("general.user_name") == "Sarah"


def test_les_etapes_d_ecoute_suivent_le_nom_qu_elles_confirment():
    """Demander de prononcer un nom trois questions plus loin n'a pas de sens."""
    ordre = [q.cle for q in pl.QUESTIONS]
    for question in pl.QUESTIONS:
        if question.ecoute:
            assert ordre.index(question.cle) == ordre.index(question.echo_de) + 1


def boutons(faux):
    """Les libellés des boutons du panneau, à n'importe quelle profondeur."""
    trouves = []

    def descendre(widget):
        for enfant in widget.winfo_children():
            if enfant.winfo_class() == "Button":
                trouves.append(enfant.cget("text"))
            descendre(enfant)

    descendre(faux.installation)
    return trouves


def test_sans_micro_l_etape_ne_propose_pas_de_parler(tk_root, assistant):
    """
    Une machine sans entrée audio ne doit pas rester bloquée devant un bouton
    « Parler » qui ne fera rien : il n'y a qu'à continuer.
    """
    faux = panneau_factice(tk_root, assistant)
    faux.montrer_installation(lambda: None)
    faux._repondre("fr")
    faux._repondre("Muneeb")

    libelles = boutons(faux)
    assert "Parler" not in libelles, libelles
    assert "Continuer" in libelles, libelles
    assert faux.boule is None, "pas de bille sans micro"


# --------------------------------------------------------------------------
# La bille de niveau
# --------------------------------------------------------------------------
# « Il ne détecte pas la voix, ou en tout cas il dit qu'il n'a rien saisi » :
# sans retour visuel, on ne peut pas savoir laquelle des deux moitiés échoue.
def test_la_bille_suit_le_niveau_et_monte_plus_vite_qu_elle_ne_descend(tk_root):
    from gui import BouleNiveau

    boule = BouleNiveau(tk_root)
    boule.definir_niveau(1.0, actif=True)
    boule._battre()
    apres_une_montee = boule.niveau
    assert apres_une_montee > 0.3, "la montée doit être franche"

    boule.definir_niveau(0.0)
    boule._battre()
    assert boule.niveau > apres_une_montee * 0.5, "la descente doit être douce"
    boule.arreter()


def test_la_bille_survit_a_la_destruction_de_son_cadre(tk_root):
    """Elle se redessine en boucle : détruite, elle doit s'arrêter seule."""
    import tkinter as tk

    from gui import BouleNiveau

    cadre = tk.Frame(tk_root)
    boule = BouleNiveau(cadre)
    cadre.destroy()
    boule._battre()              # ne doit pas lever
    assert boule._vivante is False


def test_l_etape_ecoutee_montre_une_bille_et_calibre_avant(tk_root, assistant,
                                                           monkeypatch):
    """
    Le bruit ambiant se mesure pendant qu'on lit la consigne. Le mesurer au
    clic revenait à mesurer la voix qu'on venait de demander : le seuil montait
    au plafond et le micro devenait sourd pour le reste de l'étape.
    """
    faux = panneau_factice(tk_root, assistant)
    prepare = []
    faux.stt = type("Micro", (), {
        "available": True,
        "preparer": lambda self: prepare.append(True) or True,
        "listen_live": lambda self, **k: "",
    })()

    faux.montrer_installation(lambda: None)
    faux._repondre("fr")
    faux._repondre("Muneeb")

    assert faux.boule is not None, "la bille doit être là pour voir sa voix arriver"
    assert "Parler" in boutons(faux)
    for _ in range(40):          # le calibrage tourne dans un thread
        if prepare:
            break
        tk_root.update()
        time.sleep(0.01)
    assert prepare == [True], "le silence doit être mesuré avant de parler"


@pytest.mark.parametrize("pic,raison,attendu", [
    # La voix est arrivée, mais aucun mot n'en est sorti : répéter.
    (0.60, "incompris", "pas compris"),
    # Le micro n'a rien capté du tout : c'est le micro qu'il faut regarder.
    (0.02, "incompris", "rien entendu"),
    # Capté, mais le service n'a pas répondu : ni l'un ni l'autre.
    (0.60, "injoignable", "connecté"),
])
def test_chaque_echec_dit_quoi_faire(tk_root, assistant, pic, raison, attendu):
    """
    « Je n'ai rien saisi » ne disait pas s'il fallait parler plus fort,
    répéter, ou vérifier sa connexion. Trois causes, trois gestes.
    """
    faux = panneau_factice(tk_root, assistant)
    faux.stt = type("Micro", (), {
        "available": True,
        "preparer": lambda self: True,
        "listen_live": lambda self, **k: "",
    })()
    faux.montrer_installation(lambda: None)
    faux._repondre("fr")
    faux._repondre("Muneeb")

    faux._recevoir_entendu(("", pic, raison))

    assert any(attendu in t for t in etiquettes(faux)), etiquettes(faux)


def test_un_service_injoignable_ne_se_confond_pas_avec_un_micro_muet(tk_root,
                                                                     assistant):
    """Le pendant : sans connexion, dire « parlez plus fort » est un faux conseil."""
    from gui import AlmaApp

    assert "micro" in AlmaApp._pourquoi_rien(0.02, "incompris", False)
    assert "connecté" in AlmaApp._pourquoi_rien(0.02, "injoignable", False)


def test_ce_qui_est_entendu_est_montre_avant_d_etre_retenu(tk_root, assistant):
    """On ne retient pas une transcription sans l'avoir fait voir."""
    faux = panneau_factice(tk_root, assistant)
    faux.stt = type("Micro", (), {
        "available": True,
        "preparer": lambda self: True,
        "listen_live": lambda self, **k: "",
    })()
    faux.montrer_installation(lambda: None)
    faux._repondre("fr")
    faux._repondre("Muneeb")

    faux._recevoir_entendu(("Mounib", 0.7, ""))

    assert any("Mounib" in t for t in etiquettes(faux)), etiquettes(faux)
    assert "C'est ça" in boutons(faux)


# --------------------------------------------------------------------------
# Moins de mots
# --------------------------------------------------------------------------
def test_les_consignes_restent_courtes():
    """
    Un panneau d'installation se lit d'un coup d'œil, ou ne se lit pas. Les
    boutons disent déjà ce qu'ils font.
    """
    for question in pl.QUESTIONS:
        for langue in ("fr", "en"):
            aide = question.aide(langue)
            assert len(aide) <= 90, (question.cle, langue, len(aide), aide)
            assert len(question.titre(langue)) <= 90, (question.cle, langue)


def test_la_bille_dessine_ses_cinq_couches(tk_root):
    """
    Halo, pointillés, étoiles, anneau d'onde, noyau. Un dessin qui lève ne le
    ferait qu'à l'écran de quelqu'un qui installe l'application.
    """
    from gui import BouleNiveau

    boule = BouleNiveau(tk_root)
    for niveau in (0.0, 0.4, 1.0):
        boule.definir_niveau(niveau, actif=niveau > 0.25)
        boule._battre()
        formes = boule.find_all()
        # 40 graduations + 14 étoiles + 2 halos + l'onde + le noyau.
        assert len(formes) >= BouleNiveau.GRADUATIONS + BouleNiveau.ETOILES, len(formes)
    boule.arreter()


def test_l_onde_suit_l_historique_et_non_le_niveau_courant(tk_root):
    """
    Prendre le niveau courant ferait pulser le cercle d'un bloc ; l'historique
    fait voyager la vague autour de lui.
    """
    from gui import BouleNiveau

    boule = BouleNiveau(tk_root)
    assert len(boule.historique) == BouleNiveau.MEMOIRE
    boule.definir_niveau(1.0)
    boule._battre()
    assert boule.historique[-1] > boule.historique[0], "le plus récent est en fin"
    assert len(boule.historique) == BouleNiveau.MEMOIRE, "la mémoire est bornée"
    boule.arreter()


def test_les_etoiles_ne_tournent_pas_ensemble(tk_root):
    """Toutes à la même vitesse, elles formeraient un motif, pas de la poussière."""
    from gui import BouleNiveau

    boule = BouleNiveau(tk_root)
    vitesses = {round(e["vitesse"], 6) for e in boule.etoiles}
    orbites = {round(e["orbite"], 6) for e in boule.etoiles}
    assert len(vitesses) > 1 and len(orbites) > 1
    boule.arreter()


# --------------------------------------------------------------------------
# Une phrase, pas un mot
# --------------------------------------------------------------------------
# « Il entend mais ne comprend pas » : un mot isolé est le pire cas pour la
# reconnaissance vocale, qui s'appuie sur le contexte pour trancher.
@pytest.mark.parametrize("phrase,attendu,heard", [
    # Ce qui se dit vraiment, et ce qu'on doit en tirer.
    ("Tu m'entends Jarvis", "jarvis", "jarvis"),
    ("tu m'entends Djarvis", "jarvis", "djarvis"),
    ("Can you hear me Garvis", "jarvis", "garvis"),
    ("Je m'appelle Muneeb", "muneeb", "muneeb"),
    ("je m'appelle Mounib", "muneeb", "mounib"),
    ("My name is Mounib", "muneeb", "mounib"),
    # Entendu en DEUX mots : n'en garder qu'un retiendrait une forme que
    # personne ne prononce.
    ("je m'appelle mon nid", "muneeb", "mon nid"),
    # Rien du tout.
    ("", "jarvis", ""),
])
def test_le_nom_est_tire_de_la_phrase_porteuse(phrase, attendu, heard):
    assert pl.extraire_nom(phrase, attendu) == heard


def test_chaque_etape_ecoutee_fait_dire_une_phrase():
    """Le nom seul ne se transcrit pas : il faut du contexte autour."""
    for question in pl.QUESTIONS:
        if not question.ecoute:
            continue
        for langue in ("fr", "en"):
            dite = question.phrase(langue, "Jarvis")
            assert "Jarvis" in dite, question.cle
            assert len(dite.split()) >= 3, (question.cle, dite)


def test_la_phrase_a_dire_est_affichee(tk_root, assistant):
    faux = panneau_factice(tk_root, assistant)
    faux.stt = type("Micro", (), {
        "available": True,
        "preparer": lambda self: True,
        "listen_live": lambda self, **k: "",
    })()
    faux.montrer_installation(lambda: None)
    faux._repondre("fr")
    faux._repondre("Muneeb")

    assert any("Je m'appelle Muneeb" in t for t in etiquettes(faux)), etiquettes(faux)
