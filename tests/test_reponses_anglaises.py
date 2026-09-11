"""
Parlez anglais, ALMA répond en anglais.

Le pendant de `test_anglais.py` : celui-là vérifie qu'une phrase anglaise
atteint la bonne commande, celui-ci qu'elle en revient dans la bonne langue.
Une commande peut très bien router parfaitement et répondre « C'est noté »
à qui vient de dire "note that...".

Deux garde-fous :

  1. quelques réponses sont comparées mot à mot, pour les commandes dont le
     texte ne dépend pas de la machine ;
  2. les autres passent par un filet : aucun mot exclusivement français ne
     doit apparaître dans une réponse à une phrase anglaise.

Règle pour la suite : une commande nouvelle écrit ses réponses avec
`ctx.reponse(fr, en)` / `ctx.erreur(fr, en)`, jamais `Response(text=...)`.
"""

import pytest

from core.text_utils import normalize, tokenize

# Mots qui n'existent QU'en français : ni le même mot anglais, ni un nom
# propre, ni un mot de la configuration (les noms d'applications et de sites
# y sont écrits en français et ne se traduisent pas). Ils suffisent à repérer
# une réponse restée dans la mauvaise langue, sans lister le dictionnaire.
MOTS_FRANCAIS = {
    "je", "j", "vous", "votre", "vos", "le", "la", "les", "un", "une", "des",
    "du", "est", "sont", "aucun", "aucune", "rien", "pas", "dans",
    "avec", "pour", "ecran", "fichier", "dossier", "heure", "heures",
    "ouvre", "ferme", "cherche", "voici", "desole", "compris", "trouve",
    "reussi", "revoir", "bonjour", "bonsoir", "merci", "plaisir",
    "connais", "commandes", "lecture", "enregistree", "supprimee",
}


def parle_francais(texte: str) -> set:
    """Les mots français trouvés dans une réponse."""
    return set(tokenize(normalize(texte))) & MOTS_FRANCAIS


# --------------------------------------------------------------------------
# Les réponses dont le texte ne dépend pas de la machine
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("note that I need to call my bank", "Noted: that I need to call my bank"),
    ("delete note 9", "I couldn't find a note numbered 9."),
    ("copy hello world to the clipboard", "Copied to the clipboard: hello world"),
    ("open the folder zzzzz", "Folder not found: zzzzz"),
    ("cancel all my reminders", "0 reminder(s) cancelled."),
    ("my reminders", "No reminders pending."),
])
def test_la_reponse_anglaise_est_exacte(assistant, phrase, attendu):
    assert assistant.handle(phrase).text == attendu, phrase


def test_la_meme_commande_repond_en_francais(assistant):
    """Le pendant : rien n'a été perdu du côté français."""
    assert assistant.handle("note que je dois appeler ma banque").text == (
        "C'est noté : je dois appeler ma banque")
    assert assistant.handle("supprime la note 9").text == (
        "Je n'ai pas trouvé de note numéro 9.")


# --------------------------------------------------------------------------
# Le filet : pas un mot de français dans une réponse anglaise
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    # Conversation
    "hello", "how are you", "thank you", "who are you", "what's your name",
    "tell me a joke", "goodbye",
    # Informations
    "what time is it", "what's the date", "how much battery is left",
    "how much disk space is left", "what screen are you on",
    # Calcul et hasard
    "how much is 15 times 4", "flip a coin", "roll a dice",
    # Notes, rappels, presse-papiers
    "note that the oven is on", "read my notes", "clear all my notes",
    "remind me in 10 minutes to take out the cake", "my reminders",
    "start a timer for 5 minutes", "cancel all my reminders",
    "read the clipboard",
    # Mémoire
    "remember that my dentist is Doctor Smith", "what do you remember",
    "forget everything",
    # Sites et recherches
    "list websites", "search Google for gift ideas",
    "show me pictures of mountains", "where is the central station",
    # Système : des refus, puisque rien ne joue et que l'écran 9 n'existe pas
    "what's playing", "pause the video on screen 9",
    "set the video volume to 30",
    # Le reste
    "help", "xyzzy plover",
])
def test_aucune_reponse_anglaise_ne_parle_francais(assistant, phrase):
    reponse = assistant.handle(phrase)
    fautifs = parle_francais(reponse.text)
    assert not fautifs, phrase + " -> " + reponse.text + "  (" + ", ".join(sorted(fautifs)) + ")"


# --------------------------------------------------------------------------
# Ce qui se dit dans les deux langues sans se traduire
# --------------------------------------------------------------------------
def test_l_heure_anglaise_se_lit_sur_douze_heures(assistant):
    """« 14:05 » ne se dit pas en anglais : c'est « 2:05 PM »."""
    texte = assistant.handle("what time is it").text
    assert "AM" in texte or "PM" in texte, texte


def test_l_heure_francaise_reste_sur_vingt_quatre_heures(assistant):
    texte = assistant.handle("quelle heure est-il").text
    assert "AM" not in texte and "PM" not in texte, texte


def test_wikipedia_lit_l_edition_de_la_langue_parlee(monkeypatch):
    """« who is X » doit lire en.wikipedia, pas fr.wikipedia."""
    from commands import search
    from core.context import CommandContext, Utterance
    from core.registry import all_commands, load_commands

    load_commands()
    commande = next(c for c in all_commands() if c.name == "search_wikipedia")
    langues = []

    def faux_resume(query, lang="fr", timeout=8):
        langues.append(lang)
        return query, "A summary."

    monkeypatch.setattr(search, "_wikipedia_summary", faux_resume)
    for phrase in ("who is Marie Curie", "qui est Marie Curie"):
        enonce = Utterance.parse(phrase)
        trouve = next(m for m in (p.search(enonce.norm) for p in commande.patterns) if m)
        commande.handler(CommandContext(enonce, None, match=trouve, command=commande))
    assert langues == ["en", "fr"], langues
