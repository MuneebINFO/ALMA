"""
L'onglet Abonnement : ce qu'il montre, et ce qu'il refuse de faire.

Deux choses s'y jouent qui valent des tests plutôt qu'une relecture.

La CLÉ. Elle est vérifiée contre le vrai service avant d'être acceptée —
donc jamais rangée si elle est mauvaise, et jamais affichée en clair. Ici
la vérification est doublée : la suite n'appelle aucun réseau.

Et le BOUTON D'ABONNEMENT. Tant qu'aucune page de paiement n'existe, il doit
le dire au lieu d'en ouvrir une. Un bouton qui fait semblant d'encaisser
coûte plus cher en confiance qu'il ne rapporte, et c'est exactement le genre
de chose qui part en production sans que personne le remarque.
"""

import queue

import pytest

from core import edition, secrets


# --------------------------------------------------------------------------
# De quoi exercer le panneau sans ouvrir la vraie fenêtre
# --------------------------------------------------------------------------
def panneau_factice(tk_root, assistant):
    """Les widgets sont réels ; le reste de l'application ne l'est pas."""
    import tkinter as tk

    from gui import FOND, AlmaApp

    faux = AlmaApp.__new__(AlmaApp)
    faux.root = tk_root
    faux.assistant = assistant
    faux.nom = assistant.name
    faux.corps = tk.Frame(tk_root, bg=FOND)
    faux.colonne = tk.Frame(faux.corps, bg=FOND)
    faux.colonne.pack(side="left", fill="both", expand=True)
    faux.installation = None
    faux.abonnement = None
    faux._champ_cle = None
    faux._etat_cle = None
    faux.evenements = queue.Queue()
    return faux


def etiquettes(faux):
    """Tous les textes affichés dans le panneau, à n'importe quelle profondeur."""
    trouves = []

    def descendre(widget):
        for enfant in widget.winfo_children():
            if enfant.winfo_class() == "Label":
                trouves.append(enfant.cget("text"))
            descendre(enfant)

    descendre(faux.abonnement)
    return trouves


def texte_affiche(faux):
    return " ".join(etiquettes(faux)).lower()


@pytest.fixture
def panneau(tk_root, assistant):
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()
    yield faux
    if faux.abonnement is not None:
        faux._fermer_abonnement()


@pytest.fixture
def avec_cle(assistant, monkeypatch):
    """Une machine où la clé est déjà posée."""
    monkeypatch.setattr(secrets, "lire",
                        lambda nom, cfg=None: "sk-ant-fausse-cle")
    assistant.config.set("general.edition", "complete")
    return assistant


# --------------------------------------------------------------------------
# Ce que le panneau montre
# --------------------------------------------------------------------------
def test_il_s_ouvre_et_se_referme(tk_root, assistant):
    faux = panneau_factice(tk_root, assistant)

    faux.basculer_abonnement()
    assert faux.abonnement is not None

    faux.basculer_abonnement()
    assert faux.abonnement is None


def test_les_deux_editions_sont_montrees(panneau):
    affiche = texte_affiche(panneau)
    assert "alma" in affiche
    assert "gratuit" in affiche, affiche


def test_l_edition_libre_est_decrite_en_entier(panneau):
    """
    Elle n'est pas une version amputée. Si le panneau ne listait que ce qui
    manque, il présenterait un produit complet comme une démo bridée.
    """
    affiche = texte_affiche(panneau)
    for promesse in ("commandes", "conversation", "hors ligne"):
        assert promesse in affiche, (promesse, affiche)


def test_sans_cle_c_est_l_edition_libre_qui_est_en_cours(panneau):
    assert "en cours" in texte_affiche(panneau)


def test_le_prix_affiche_vient_de_la_configuration(tk_root, assistant):
    assistant.config.set("abonnement.prix_fr", "3,50 € par mois")
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    assert "3,50 € par mois" in texte_affiche(faux)


def test_en_anglais_tout_est_en_anglais(tk_root, assistant):
    assistant.config.set("general.language", "en")
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    affiche = texte_affiche(faux)
    assert "subscription" in affiche
    assert "free, always" in affiche
    assert "gratuit" not in affiche, affiche


# --------------------------------------------------------------------------
# Le bouton d'abonnement : il ne fait pas semblant
# --------------------------------------------------------------------------
def test_sans_page_de_paiement_le_bouton_le_dit(panneau):
    """
    Le test qui compte. Tant que la page n'existe pas, aucun bouton ne doit
    prétendre encaisser quoi que ce soit.
    """
    assert "pas encore ouvert" in texte_affiche(panneau)


def test_aucune_page_n_est_ouverte_sans_url(tk_root, assistant, monkeypatch):
    ouvertes = []
    monkeypatch.setattr("gui.AlmaApp._ouvrir_page_abonnement",
                        lambda self, url: ouvertes.append(url))

    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    assert ouvertes == []


def test_avec_une_url_le_bouton_apparait(tk_root, assistant):
    assistant.config.set("abonnement.url", "https://exemple.test/abonnement")
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    assert "pas encore ouvert" not in texte_affiche(faux)


# --------------------------------------------------------------------------
# La clé : vérifiée avant d'être rangée
# --------------------------------------------------------------------------
def test_une_cle_refusee_n_est_pas_rangee(panneau, monkeypatch):
    """
    Accepter sans vérifier serait pire que tout : la clé serait rangée,
    l'édition passerait en complète, et le premier échec arriverait plus
    tard, sur une vraie demande, sans que personne sache pourquoi.
    """
    posees = []
    monkeypatch.setattr("core.providers.claude_api_provider.verifier_cle",
                        lambda cle, delai=15.0: (False, "Clé refusée.", "Key refused."))
    monkeypatch.setattr(edition, "poser_cle",
                        lambda cfg, valeur: posees.append(valeur))

    panneau._champ_cle.insert(0, "sk-ant-mauvaise")
    panneau._verifier_puis_ranger("sk-ant-mauvaise", anglais=False)

    assert posees == [], "une clé refusée a été rangée"


def test_une_cle_acceptee_est_rangee_et_appliquee(panneau, monkeypatch):
    """Règle 3 : appliqué ET retenu. Les deux moitiés, ou rien."""
    posees = []
    personnalisees = []
    monkeypatch.setattr("core.providers.claude_api_provider.verifier_cle",
                        lambda cle, delai=15.0: (True, "", ""))
    monkeypatch.setattr(edition, "poser_cle",
                        lambda cfg, valeur: posees.append(valeur) or True)
    panneau.assistant.personnaliser = lambda reglages: personnalisees.append(reglages)

    panneau._verifier_puis_ranger("sk-ant-bonne", anglais=False)

    assert posees == ["sk-ant-bonne"]
    assert personnalisees == [{"general.edition": "complete"}]


def test_un_champ_vide_ne_part_pas_sur_le_reseau(panneau, monkeypatch):
    appels = []
    monkeypatch.setattr("core.providers.claude_api_provider.verifier_cle",
                        lambda cle, delai=15.0: appels.append(cle) or (True, "", ""))

    panneau._activer_cle()

    assert appels == [], "une vérification est partie pour un champ vide"


def test_la_cle_ne_s_affiche_jamais_en_clair(panneau):
    """
    Une clé lisible à l'écran, c'est un partage d'écran ou une capture et
    elle est dehors. Le champ la masque, comme un mot de passe.
    """
    assert panneau._champ_cle.cget("show") not in ("", None)


def test_la_cle_n_apparait_pas_dans_les_etiquettes(panneau, monkeypatch):
    monkeypatch.setattr("core.providers.claude_api_provider.verifier_cle",
                        lambda cle, delai=15.0: (False, "Refusée.", "Refused."))

    panneau._champ_cle.insert(0, "sk-ant-secrete-0123456789")
    panneau._activer_cle()
    panneau.root.update()

    assert "sk-ant" not in texte_affiche(panneau)


def test_le_message_d_echec_s_affiche(panneau):
    panneau._echec_cle("Cette clé n'est pas reconnue.")

    assert "pas reconnue" in texte_affiche(panneau)


def test_un_echec_arrive_apres_fermeture_ne_leve_pas(tk_root, assistant):
    """
    La vérification part sur le réseau et peut mettre quinze secondes. Le
    panneau, lui, peut avoir été refermé entre-temps : le thread revient
    alors sur des widgets détruits.
    """
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()
    etiquette = faux._etat_cle
    faux._fermer_abonnement()

    faux._etat_cle = etiquette          # ce que le thread a encore sous la main
    faux._echec_cle("Trop tard.")       # ne doit pas lever


# --------------------------------------------------------------------------
# Une fois abonné
# --------------------------------------------------------------------------
def test_avec_une_cle_l_edition_complete_est_en_cours(tk_root, avec_cle):
    faux = panneau_factice(tk_root, avec_cle)
    faux.basculer_abonnement()

    affiche = texte_affiche(faux)
    assert "chiffr" in affiche, affiche
    assert "retirer la cl" in affiche, affiche


def test_il_n_y_a_plus_de_champ_de_saisie_une_fois_abonne(tk_root, avec_cle):
    faux = panneau_factice(tk_root, avec_cle)
    faux.basculer_abonnement()

    assert faux._champ_cle is None


def test_retirer_la_cle_ramene_en_edition_libre(tk_root, avec_cle, monkeypatch):
    oublis = []
    personnalisees = []
    monkeypatch.setattr(edition, "retirer_cle",
                        lambda cfg: oublis.append(True) or True)
    faux = panneau_factice(tk_root, avec_cle)
    faux.basculer_abonnement()
    faux.assistant.personnaliser = lambda reglages: personnalisees.append(reglages)

    faux._retirer_cle()

    assert oublis == [True]
    assert personnalisees == [{"general.edition": "libre"}]


def test_une_verification_qui_revient_apres_la_fermeture_de_la_fenetre(panneau,
                                                                       monkeypatch):
    """
    La vérification dure jusqu'à quinze secondes. L'utilisateur peut avoir
    quitté entre-temps : `root.after` lève alors depuis le thread, et
    l'exception meurt dans son coin sans que personne la voie.
    """
    monkeypatch.setattr("core.providers.claude_api_provider.verifier_cle",
                        lambda cle, delai=15.0: (False, "Refusée.", "Refused."))

    class FenetrePartie:
        @staticmethod
        def after(_delai, _quoi):
            raise RuntimeError("main thread is not in main loop")

    panneau.root = FenetrePartie()

    panneau._verifier_puis_ranger("sk-ant-peu-importe", anglais=False)


def test_echap_referme_le_panneau_avant_d_endormir(panneau):
    """
    Sinon Échap endormirait ALMA en laissant l'onglet ouvert : on croirait
    avoir fermé, et on aurait mis l'assistant en veille sans le vouloir.
    """
    sommeils = []
    panneau.endormir = lambda: sommeils.append(True)
    panneau.plein_ecran = False

    panneau._sur_echap()

    assert panneau.abonnement is None
    assert sommeils == [], "ALMA a été endormie au lieu de fermer l'onglet"


# --------------------------------------------------------------------------
# Le bouton « S'abonner » branché sur le Store
# --------------------------------------------------------------------------
@pytest.fixture
def store_present(assistant, monkeypatch):
    """Une machine où le Store répond, avec un achat sous surveillance."""
    from core import abonnement_store

    achats = []
    monkeypatch.setattr(abonnement_store, "disponible", lambda: True)
    monkeypatch.setattr(
        abonnement_store, "acheter",
        lambda store_id, fenetre: achats.append((store_id, fenetre))
        or (True, "C'est fait.", "All set."))
    return achats


def test_avec_le_store_le_bouton_s_abonner_apparait(tk_root, assistant,
                                                    store_present):
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    assert "pas encore ouvert" not in texte_affiche(faux)


def test_l_achat_passe_par_le_store_avec_le_bon_identifiant(tk_root, assistant,
                                                            store_present):
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    faux._acheter_puis_rafraichir(fenetre=1234, anglais=False)

    assert len(store_present) == 1
    store_id, fenetre = store_present[0]
    assert store_id == assistant.config.get("abonnement.store_id")
    assert fenetre == 1234, "le handle de fenêtre n'est pas transmis"


def test_un_achat_annule_le_dit_sans_rien_activer(tk_root, assistant,
                                                  monkeypatch):
    from core import abonnement_store, edition

    monkeypatch.setattr(abonnement_store, "disponible", lambda: True)
    monkeypatch.setattr(
        abonnement_store, "acheter",
        lambda store_id, fenetre: (False, "L'achat a été annulé.",
                                   "The purchase was cancelled."))
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    faux._acheter_puis_rafraichir(fenetre=1, anglais=False)
    faux.root.update()

    assert "annulé" in texte_affiche(faux)
    assert edition.est_complete(assistant.config) is False


def test_le_cache_est_oublie_apres_un_achat(tk_root, assistant, store_present,
                                            monkeypatch):
    """
    Sans cela, ALMA continuerait de croire l'utilisateur non abonné pendant
    trente secondes après qu'il vient de payer — la pire seconde possible
    pour un doute.
    """
    from core import edition

    oublis = []
    monkeypatch.setattr(edition, "oublier_le_cache",
                        lambda: oublis.append(True))
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    faux._acheter_puis_rafraichir(fenetre=1, anglais=False)

    assert oublis, "le cache d'abonnement n'a pas été invalidé"


# --------------------------------------------------------------------------
# Les deux voies vers l'édition complète
# --------------------------------------------------------------------------
def test_une_cle_envoie_droit_chez_anthropic(assistant, monkeypatch):
    """Rien ne transite par le relais : c'est le compte de l'utilisateur."""
    from core import edition, secrets
    from core.providers.claude_api_provider import ClaudeApiProvider

    monkeypatch.setattr(secrets, "lire", lambda nom, cfg=None: "sk-ant-a-lui")
    assistant.config.set("general.edition", "complete")
    assistant.config.set("abonnement.relais_url", "https://relais.test")

    assert edition.voie(assistant.config) == edition.VOIE_CLE

    construits = []
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic",
                        lambda **k: construits.append(k) or object())

    ClaudeApiProvider(assistant.config).client()

    assert construits[0]["api_key"] == "sk-ant-a-lui"
    assert "base_url" not in construits[0], "la clé de l'utilisateur est passée par le relais"


def test_un_abonnement_passe_par_le_relais(assistant, monkeypatch):
    """Et l'application n'a alors AUCUNE clé — seulement un jeton signé."""
    from core import abonnement_store, edition
    from core.providers.claude_api_provider import ClaudeApiProvider

    monkeypatch.setattr(abonnement_store, "abonne", lambda store_id: True)
    monkeypatch.setattr(abonnement_store, "jeton", lambda audience="": "jeton-signe")
    edition.oublier_le_cache()
    assistant.config.set("abonnement.relais_url", "https://relais.test")

    assert edition.voie(assistant.config) == edition.VOIE_ABONNEMENT

    construits = []
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic",
                        lambda **k: construits.append(k) or object())

    ClaudeApiProvider(assistant.config).client()

    assert construits[0]["base_url"] == "https://relais.test"
    assert construits[0]["api_key"] == "jeton-signe"
    assert not construits[0]["api_key"].startswith("sk-ant")


def test_un_abonnement_sans_relais_le_dit_clairement(assistant, monkeypatch):
    """
    Le cas qui arrivera pendant le déploiement : abonné, mais le relais n'est
    pas encore en ligne. Il faut que le message le dise, pas qu'il ressemble
    à un problème d'abonnement.
    """
    from core import abonnement_store, edition
    from core.providers.claude_api_provider import ClaudeApiProvider

    monkeypatch.setattr(abonnement_store, "abonne", lambda store_id: True)
    edition.oublier_le_cache()
    assistant.config.set("abonnement.relais_url", "")

    with pytest.raises(RuntimeError, match="relais"):
        ClaudeApiProvider(assistant.config).client()


def test_la_cle_l_emporte_sur_l_abonnement(assistant, monkeypatch):
    """
    Quelqu'un qui a posé une clé l'a fait exprès, et elle ne coûte rien à
    personne d'autre. La consulter est par ailleurs instantané.
    """
    from core import abonnement_store, edition, secrets

    monkeypatch.setattr(secrets, "lire", lambda nom, cfg=None: "sk-ant-a-lui")
    monkeypatch.setattr(abonnement_store, "abonne", lambda store_id: True)
    edition.oublier_le_cache()
    assistant.config.set("general.edition", "complete")

    assert edition.voie(assistant.config) == edition.VOIE_CLE
