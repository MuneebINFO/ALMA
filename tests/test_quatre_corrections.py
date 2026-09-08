"""
Quatre corrections demandées après usage.

1. Un prénom mal transcrit doit quand même être reconnu.
2. « ouvre Google » ouvre la page, « ouvre Chrome » ouvre le navigateur.
3. Une action réussie ne se commente pas à voix haute.
4. Le seuil de détection ne doit pas obliger à crier.
"""

import pytest

from commands.apps import alias_exacts
from core import interaction
from core.context import Utterance
from core.registry import all_commands
from core.stt import LevelMeterListener


def cible(nom, largeur=300, hauteur=200):
    return interaction.Cible(nom, (0, 0, largeur, hauteur), object(), interaction.LIEN)


# --------------------------------------------------------------------------
# 1. Les noms propres mal entendus
# --------------------------------------------------------------------------
@pytest.mark.parametrize("entendu", ["Muneeb", "Mounib", "Munib", "Mouneeb"])
def test_un_prenom_mal_transcrit_est_retrouve(entendu):
    """
    « Muneeb » revient en « Mounib » : 0,67 de ressemblance en lettres, donc
    sous le seuil, mais la même chose à l'oreille.
    """
    cibles = [cible("Profil de Muneeb. Sélectionnez cette option pour ouvrir"),
              cible("Ajouter un profil"), cible("Accueil")]
    trouve = interaction.chercher_cible(cibles, entendu)
    assert trouve is not None, entendu
    assert "Muneeb" in trouve.nom


def test_la_sonorite_ne_rapproche_pas_nimporte_quoi():
    cibles = [cible("Profil de Muneeb"), cible("Accueil"), cible("Ma liste")]
    for etranger in ("Interstellar", "Netflix", "Sébastien"):
        assert interaction.chercher_cible(cibles, etranger) is None, etranger


# --------------------------------------------------------------------------
# 2. Le site ou l application
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    # « google » nomme exactement un site : il l'emporte sur la ressemblance
    # avec l'application « google chrome ».
    ("ouvre Google", "open_website"),
    ("ouvre YouTube", "open_website"),
    ("ouvre Gmail", "open_website"),
    ("ouvre Netflix", "open_website"),
    ("ouvre Maps", "open_website"),
    # Ceux-là nomment bien une application.
    ("ouvre Chrome", "open_app"),
    ("ouvre Google Chrome", "open_app"),
    ("ouvre le navigateur", "open_app"),
    ("ouvre la calculatrice", "open_app"),
    ("ouvre Discord", "open_app"),
])
def test_ouvrir_vise_le_bon_objet(assistant, phrase, attendu):
    resolution = assistant.router.resolve(Utterance.parse(phrase), assistant=assistant)
    assert resolution is not None, phrase + " n'atteint aucune commande"
    assert resolution.command.name == attendu, phrase


def test_les_alias_exacts_sont_bien_releves(config):
    apps = alias_exacts(config.get("applications", {}))
    sites = alias_exacts(config.get("websites", {}))
    assert "chrome" in apps and "google chrome" in apps
    assert "google" in sites and "google" not in apps


# --------------------------------------------------------------------------
# 3. Une action ne se commente pas
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "quelle heure est-il", "raconte-moi une blague", "combien font 12 fois 8",
    "sur quel écran es-tu", "quel est le volume", "lis mes notes",
])
def test_une_question_recoit_une_reponse_a_voix_haute(assistant, phrase):
    reponse = assistant.handle(phrase)
    assert reponse.ok, reponse.text
    assert reponse.speak is True, phrase


@pytest.mark.parametrize("phrase", [
    "note que je dois rappeler ma banque",
    "monte le son",
    "mets le volume à 40",
])
def test_une_action_reussie_reste_silencieuse(assistant, phrase):
    reponse = assistant.handle(phrase)
    assert reponse.ok, reponse.text
    assert reponse.speak is False, phrase


def test_ce_qui_nest_pas_compris_se_dit(assistant):
    """
    Le seul échec qui se dit : celui où rien n'a été compris. Sans voix,
    l'utilisateur attendrait une action qui ne viendra jamais.
    """
    reponse = assistant.handle("xyzzy plover blorb")
    assert not reponse.ok
    assert reponse.speak is True


@pytest.mark.parametrize("phrase", [
    "va sur l'écran 9",                        # écran inexistant
    "mets le volume de la vidéo à 30",         # rien ne joue ici
])
def test_une_action_impossible_saffiche_sans_se_dire(assistant, phrase):
    """
    La demande a été comprise, mais elle n'a pas abouti. Le texte l'explique
    à l'écran ; le dire à voix haute reviendrait à commenter l'action.
    """
    reponse = assistant.handle(phrase)
    assert not reponse.ok
    assert reponse.speak is False, phrase


def test_aucune_action_nexplique_a_lutilisateur_quoi_dire():
    """
    « Je fais défiler vers le bas. Dites « arrête » quand ça suffit. » : la
    seconde phrase est du mode d'emploi. Elle n'est acceptable que dans un
    message d'échec, où elle aide à reformuler, ou dans une présentation.
    """
    from pathlib import Path

    racine = Path(__file__).resolve().parent.parent
    # La présentation de l'assistant a vocation à faire découvrir « aide ».
    EXEMPTES = {"smalltalk.py"}
    fautifs = []
    for fichier in (racine / "commands").rglob("*.py"):
        if fichier.name in EXEMPTES:
            continue
        texte = fichier.read_text(encoding="utf-8")
        depart = 0
        while True:
            position = texte.find("Dites «", depart)
            if position < 0:
                break
            depart = position + 1
            avant = texte[max(0, position - 300):position]
            if "Response.error(" in avant:
                continue          # message d'échec : le conseil y a sa place
            ligne = texte.count(chr(10), 0, position) + 1
            fautifs.append("%s:%d" % (fichier.name, ligne))
    assert not fautifs, "mode d'emploi dans une réponse : " + ", ".join(fautifs)


@pytest.mark.parametrize("phrase", ["fais défiler vers le bas", "défile vers le haut"])
def test_le_defilement_ne_se_commente_pas(assistant, phrase, monkeypatch):
    """Le cas signalé : « scroll vers le bas » ne doit pas être expliqué."""
    from core import interaction

    monkeypatch.setattr(interaction.Defilement, "demarrer", lambda self, **k: True)
    reponse = assistant.handle(phrase)
    assert reponse.ok, reponse.text
    assert reponse.speak is False
    assert "Dites" not in reponse.text, reponse.text


def test_les_commandes_informatives_sont_declarees():
    """Le drapeau doit rester en phase avec ce que font les commandes."""
    informatives = {c.name for c in all_commands() if c.informatif}
    assert {"get_time", "weather", "joke", "read_notes", "quel_ecran"} <= informatives
    assert not ({"defiler", "cliquer_sur", "volume_set", "add_note"} & informatives)


# --------------------------------------------------------------------------
# 4. Le seuil de detection
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bruit,pic,attendu", [
    # Pièce calme, mesurée sur la machine de référence.
    (0.00003, 0.00038, 0.0015),
    # Un média joue : la carte son en efface le bruit, mais atténue la voix.
    (0.00001, 0.00106, 0.0017),
    # Bureau animé : c'est le pic mesuré qui commande, pas un multiplicateur.
    (0.00200, 0.00600, 0.0096),
])
def test_le_seuil_suit_le_bruit_reellement_mesure(bruit, pic, attendu):
    ecouteur = LevelMeterListener()
    ecouteur.pic_calibration = pic
    assert round(ecouteur._appliquer_seuil(bruit), 4) == round(attendu, 4)


def test_le_seuil_est_plafonne():
    """Au-delà, il faudrait crier : mieux vaut quelques déclenchements à vide."""
    ecouteur = LevelMeterListener()
    ecouteur.pic_calibration = 1.0
    assert ecouteur._appliquer_seuil(0.5) == LevelMeterListener.SEUIL_MAX


def test_le_plancher_reste_reglable():
    ecouteur = LevelMeterListener(plancher=0.02)
    assert ecouteur._appliquer_seuil(0.0) == 0.02
