"""
Tests de comportement des commandes (execution reelle des handlers).

Aucun test n ouvre de navigateur ni ne modifie l etat du systeme :
on se limite aux commandes locales (notes, rappels, aide, historique).
"""

from datetime import datetime, timedelta


def test_prendre_puis_relire_une_note(assistant):
    reponse = assistant.handle("note que je dois rappeler ma banque demain")
    assert reponse.ok
    notes = assistant.storage.notes.load()
    assert len(notes) == 1
    assert notes[0]["text"] == "je dois rappeler ma banque demain"

    relecture = assistant.handle("lis mes notes")
    assert "banque" in relecture.text


def test_notes_vides(assistant):
    reponse = assistant.handle("lis mes notes")
    assert "aucune note" in reponse.text.lower()


def test_supprimer_une_note_par_numero(assistant):
    assistant.handle("note que acheter du pain")
    note_id = assistant.storage.notes.load()[0]["id"]
    reponse = assistant.handle("supprime la note " + str(note_id))
    assert reponse.ok
    assert assistant.storage.notes.load() == []


def test_effacer_les_notes_demande_confirmation(assistant):
    assistant.handle("note que test un")
    assistant.io.answers = ["non"]           # l utilisateur refuse
    reponse = assistant.handle("efface toutes mes notes")
    assert len(assistant.storage.notes.load()) == 1
    assert "conserv" in reponse.text.lower()

    assistant.io.answers = ["oui"]           # l utilisateur accepte
    assistant.handle("efface toutes mes notes")
    assert assistant.storage.notes.load() == []


def test_minuteur_programme_un_rappel(assistant):
    reponse = assistant.handle("lance un minuteur de 5 minutes")
    assert reponse.ok
    pending = assistant.scheduler.pending()
    assert len(pending) == 1
    due = datetime.fromisoformat(pending[0]["due"])
    ecart = due - datetime.now()
    assert timedelta(minutes=4) < ecart <= timedelta(minutes=5)
    assistant.scheduler.cancel_all()


def test_rappel_avec_libelle(assistant):
    assistant.handle("rappelle-moi dans 10 minutes de sortir le gateau")
    pending = assistant.scheduler.pending()
    assert len(pending) == 1
    assert "gateau" in pending[0]["label"]
    assistant.scheduler.cancel_all()


def test_annuler_les_rappels(assistant):
    assistant.handle("lance un minuteur de 5 minutes")
    reponse = assistant.handle("annule mes rappels")
    assert reponse.ok
    assert assistant.scheduler.pending() == []


def test_minuteur_sans_duree_est_signale(assistant):
    reponse = assistant.handle("lance un minuteur")
    assert not reponse.ok
    assert "durée" in reponse.text.lower()


def test_commande_inconnue_suggere_aide(assistant):
    """Le message est tire au hasard : il doit toujours orienter l utilisateur."""
    from core.ai_fallback import SUGGESTIONS

    reponse = assistant.handle("xyzzy plover blorb")
    assert not reponse.ok
    assert reponse.text in SUGGESTIONS


def test_aide_liste_les_commandes(assistant):
    reponse = assistant.handle("que peux-tu faire")
    assert reponse.ok
    affichage = "\n".join(assistant.io.written)
    assert "[Applications]" in affichage
    assert "[Système]" in affichage


def test_quitter_arrete_la_boucle(assistant):
    reponse = assistant.handle("au revoir Alma")
    assert reponse.should_exit
    assert assistant.running is False


def test_historique_enregistre_les_demandes(assistant):
    assistant.handle("quelle heure est-il")
    assistant.handle("quel jour sommes-nous")
    entrees = assistant.storage.history.load()
    assert [e["command"] for e in entrees] == ["get_time", "get_date"]


def test_repeter_la_derniere_commande(assistant):
    assistant.handle("quelle heure est-il")
    reponse = assistant.handle("repete")
    assert "heures" in reponse.text


def test_heure_et_date(assistant):
    assert "heures" in assistant.handle("quelle heure est-il").text
    assert str(datetime.now().year) in assistant.handle("quelle est la date").text


def test_une_erreur_de_handler_ne_casse_pas_l_assistant(assistant, monkeypatch):
    """Le routeur doit transformer une exception en reponse d erreur lisible."""
    import commands.smalltalk as smalltalk

    def handler_casse(ctx):
        raise RuntimeError("panne simulee")

    monkeypatch.setattr(smalltalk.joke.command, "handler", handler_casse)
    reponse = assistant.handle("raconte-moi une blague")
    assert not reponse.ok
    assert "panne simulee" in reponse.text
    assert assistant.running is True
