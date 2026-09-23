"""
Le compte, le profil et la modale d'abonnement.

Deux choses s'y jouent qui valent des tests plutôt qu'une relecture.

**Aucune clé d'API n'est proposée, jamais.** Ce chemin a existé, il a été
retiré, et la fin de ce fichier interdit son retour — pas seulement dans le
code, mais dans le TEXTE affiché : suggérer à quelqu'un d'aller se procurer
une clé chez un tiers est une décision de produit, et elle a été prise dans
l'autre sens.

**Le bouton d'abonnement ne fait pas semblant.** Tant qu'aucun moyen de
paiement n'existe, il le dit au lieu d'en ouvrir un. Un bouton qui prétend
encaisser coûte plus cher en confiance qu'il ne rapporte, et c'est
exactement le genre de chose qui part en production sans que personne le
remarque.
"""

import queue

import pytest

from core import abonnement_store, edition


# --------------------------------------------------------------------------
# De quoi exercer les panneaux sans ouvrir la vraie fenêtre
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
    faux.popup_compte = None
    faux._etat_achat = None
    faux.evenements = queue.Queue()
    return faux


def _textes(racine):
    trouves = []

    def descendre(widget):
        for enfant in widget.winfo_children():
            if enfant.winfo_class() in ("Label", "Button"):
                trouves.append(enfant.cget("text"))
            descendre(enfant)

    descendre(racine)
    return trouves


def etiquettes(faux):
    return _textes(faux.abonnement)


def texte_affiche(faux):
    return " ".join(etiquettes(faux)).lower()


def textes_popup(faux):
    return " ".join(_textes(faux.popup_compte)).lower()


@pytest.fixture
def modale(tk_root, assistant):
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()
    yield faux
    if faux.abonnement is not None:
        faux._fermer_abonnement()


@pytest.fixture
def abonne(assistant, monkeypatch):
    """Une machine dont l'abonnement est actif."""
    monkeypatch.setattr(abonnement_store, "abonne", lambda store_id: True)
    edition.oublier_le_cache()
    return assistant


# --------------------------------------------------------------------------
# Le menu du compte : l'unique point d'entrée de l'écran
# --------------------------------------------------------------------------
def menu(tk_root, assistant):
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_compte()
    return faux


def test_le_menu_s_ouvre_et_se_referme(tk_root, assistant):
    faux = menu(tk_root, assistant)
    assert faux.popup_compte is not None

    faux.basculer_compte()
    assert faux.popup_compte is None


def test_le_menu_propose_profil_et_abonnement(tk_root, assistant):
    affiche = textes_popup(menu(tk_root, assistant))

    assert "profil" in affiche, affiche
    assert "abonnement" in affiche, affiche


def test_la_pastille_annonce_la_formule_pas_le_nom_de_l_app(tk_root, assistant):
    """
    « ALMA » ne répond pas à « à quoi ai-je droit ». La ligne sous le nom
    doit nommer la FORMULE — c'est la seule information qu'on vient y
    chercher.
    """
    libelle, _accent = panneau_factice(tk_root, assistant)._edition_affichee()

    assert "gratuit" in libelle.lower(), libelle


def test_la_pastille_change_avec_l_abonnement(tk_root, abonne):
    libelle, _accent = panneau_factice(tk_root, abonne)._edition_affichee()

    assert "alma+" in libelle.lower(), libelle


def test_le_profil_montre_ce_qu_alma_a_retenu(tk_root, assistant):
    assistant.config.set("general.user_name", "Muneeb")
    faux = panneau_factice(tk_root, assistant)
    faux._ouvrir_profil()

    affiche = textes_popup(faux)
    assert "muneeb" in affiche, affiche
    assert "français" in affiche, affiche


def test_le_profil_dit_comment_changer_plutot_que_d_offrir_un_formulaire(
        tk_root, assistant):
    """
    Ces réglages se changent en le demandant à ALMA. Le rappeler ici apprend
    la commande à qui l'ignore — un formulaire l'aurait cachée.
    """
    faux = panneau_factice(tk_root, assistant)
    faux._ouvrir_profil()

    assert "appelle-moi" in textes_popup(faux)


def test_l_abonnement_depuis_le_menu_referme_le_menu(tk_root, assistant):
    """Deux popups ouverts l'un sur l'autre, c'est une fenêtre en désordre."""
    faux = menu(tk_root, assistant)

    faux._ouvrir_abonnement_depuis_menu()

    assert faux.popup_compte is None
    assert faux.abonnement is not None


# --------------------------------------------------------------------------
# La modale : un comparatif de formules
# --------------------------------------------------------------------------
def test_elle_s_ouvre_et_se_referme(tk_root, assistant):
    faux = panneau_factice(tk_root, assistant)

    faux.basculer_abonnement()
    assert faux.abonnement is not None

    faux.basculer_abonnement()
    assert faux.abonnement is None


def test_les_deux_formules_sont_montrees(modale):
    affiche = texte_affiche(modale)

    assert "alma+" in affiche, affiche
    assert "pour commencer" in affiche, affiche
    assert "tout ce qu'alma fait" in affiche, affiche


def test_le_gratuit_est_decrit_en_entier(modale):
    """
    Ce n'est pas une version amputée. Si la modale ne listait que ce qui
    manque, elle présenterait un produit complet comme une démo bridée.
    """
    affiche = texte_affiche(modale)

    for promesse in ("commandes", "rappels", "hors ligne"):
        assert promesse in affiche, (promesse, affiche)


def test_les_capacites_sont_des_capacites_pas_des_phrases_a_dire(modale):
    """
    « Ouvre Chrome » apprend à se SERVIR de l'application ; ça ne dit pas ce
    qu'on achète. Sur une page de forfait, la question est « qu'est-ce que
    j'obtiens », et elle se répond en capacités.
    """
    affiche = texte_affiche(modale)

    for exemple in ("« ouvre chrome »", "« monte le son »", "« prends une photo »"):
        assert exemple not in affiche, exemple


def test_la_formule_en_cours_ne_propose_pas_de_l_acheter(modale):
    assert "votre formule actuelle" in texte_affiche(modale)


def test_le_prix_affiche_vient_de_la_configuration(tk_root, assistant):
    assistant.config.set("abonnement.prix_fr", "3,50 € par mois")
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    assert "3,50" in texte_affiche(faux)


def test_le_gratuit_affiche_zero(modale):
    assert "0" in etiquettes(modale)


def test_en_anglais_tout_est_en_anglais(tk_root, assistant):
    assistant.config.set("general.language", "en")
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    affiche = texte_affiche(faux)
    assert "start with the basics" in affiche, affiche
    assert "pour commencer" not in affiche, affiche


def test_une_fois_abonne_la_modale_le_montre(tk_root, abonne):
    faux = panneau_factice(tk_root, abonne)
    faux.basculer_abonnement()

    affiche = texte_affiche(faux)
    assert "votre formule actuelle" in affiche
    assert "résilier" in affiche, affiche


# --------------------------------------------------------------------------
# Le bouton d'abonnement : il ne fait pas semblant
# --------------------------------------------------------------------------
def test_sans_moyen_de_paiement_le_bouton_le_dit(modale):
    """
    Le test qui compte. Tant qu'aucun moyen de paiement n'existe, rien ne
    doit prétendre encaisser quoi que ce soit.
    """
    assert "ouvre bientôt" in texte_affiche(modale)


def test_aucune_page_n_est_ouverte_sans_url(tk_root, assistant, monkeypatch):
    ouvertes = []
    monkeypatch.setattr("gui.AlmaApp._ouvrir_page_abonnement",
                        lambda self, url: ouvertes.append(url))

    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    assert ouvertes == []


def test_avec_le_store_le_bouton_apparait(tk_root, assistant, monkeypatch):
    monkeypatch.setattr(abonnement_store, "disponible", lambda: True)
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    affiche = texte_affiche(faux)
    assert "ouvre bientôt" not in affiche
    assert "alma+" in affiche


def test_l_achat_passe_par_le_store_avec_le_bon_identifiant(tk_root, assistant,
                                                            monkeypatch):
    achats = []
    monkeypatch.setattr(abonnement_store, "disponible", lambda: True)
    monkeypatch.setattr(
        abonnement_store, "acheter",
        lambda store_id, fenetre: achats.append((store_id, fenetre))
        or (True, "C'est fait.", "All set."))

    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()
    faux._acheter_puis_rafraichir(fenetre=1234, anglais=False)

    assert len(achats) == 1
    store_id, fenetre = achats[0]
    assert store_id == assistant.config.get("abonnement.store_id")
    assert fenetre == 1234, "le handle de fenêtre n'est pas transmis"


def test_un_achat_annule_le_dit_sans_rien_activer(tk_root, assistant,
                                                  monkeypatch):
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


def test_le_cache_est_oublie_apres_un_achat(tk_root, assistant, monkeypatch):
    """
    Sans cela, ALMA continuerait de croire l'utilisateur non abonné pendant
    trente secondes après qu'il vient de payer — la pire seconde possible
    pour un doute.
    """
    oublis = []
    monkeypatch.setattr(abonnement_store, "disponible", lambda: True)
    monkeypatch.setattr(abonnement_store, "acheter",
                        lambda store_id, fenetre: (True, "fait", "done"))
    monkeypatch.setattr(edition, "oublier_le_cache",
                        lambda: oublis.append(True))

    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()
    faux._acheter_puis_rafraichir(fenetre=1, anglais=False)

    assert oublis, "le cache d'abonnement n'a pas été invalidé"


def test_un_echec_arrive_apres_fermeture_ne_leve_pas(tk_root, assistant):
    """
    L'achat peut mettre longtemps : la modale a pu être refermée entre-temps,
    et le thread revient alors sur des widgets détruits.
    """
    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()
    etiquette = faux._etat_achat
    faux._fermer_abonnement()

    faux._etat_achat = etiquette
    faux._echec_achat("Trop tard.")        # ne doit pas lever


def test_la_resiliation_renvoie_au_store(tk_root, abonne, monkeypatch):
    """
    C'est Microsoft qui encaisse : nous n'avons ni le droit ni le moyen
    d'annuler à sa place, et prétendre le contraire laisserait quelqu'un
    croire qu'il a résilié alors qu'il sera prélevé le mois suivant.
    """
    ouvertes = []
    monkeypatch.setattr("core.win_utils.launch",
                        lambda cible: ouvertes.append(cible) or (True, ""))

    faux = panneau_factice(tk_root, abonne)
    faux.basculer_abonnement()
    faux._resilier()

    assert ouvertes and "store" in ouvertes[0].lower(), ouvertes


# --------------------------------------------------------------------------
# Aucune clé d'API n'est proposée — ni même l'idée
# --------------------------------------------------------------------------
# Une décision de produit, pas un détail technique : il n'y a qu'une voie
# vers ALMA+, l'abonnement. Proposer « ou bien procurez-vous une clé chez un
# tiers » demande à quelqu'un de choisir entre deux choses qu'il ne sait pas
# comparer, et en fait fuir la plupart.

@pytest.mark.parametrize("ecran", ["abonnement", "menu", "profil"])
def test_aucun_ecran_ne_parle_de_cle_d_api(tk_root, assistant, ecran):
    faux = panneau_factice(tk_root, assistant)
    if ecran == "abonnement":
        faux.basculer_abonnement()
        affiche = texte_affiche(faux)
    else:
        faux.basculer_compte() if ecran == "menu" else faux._ouvrir_profil()
        affiche = textes_popup(faux)

    for mot in ("clé d'api", "api key", "anthropic", "sk-ant", "clé"):
        assert mot not in affiche, (ecran, mot, affiche)


def test_la_fenetre_n_a_plus_aucun_champ_de_saisie_de_cle(tk_root, assistant):
    import tkinter as tk

    faux = panneau_factice(tk_root, assistant)
    faux.basculer_abonnement()

    def champs(widget):
        trouves = []
        for enfant in widget.winfo_children():
            if isinstance(enfant, tk.Entry):
                trouves.append(enfant)
            trouves += champs(enfant)
        return trouves

    assert champs(faux.abonnement) == [], "un champ de saisie subsiste"


def test_la_fenetre_n_offre_aucune_methode_pour_poser_une_cle():
    from gui import AlmaApp

    # « cle » tout court attrapait `_boucle_micro` : on vise les mots, pas
    # les sous-chaines.
    interdits = [nom for nom in dir(AlmaApp)
                 if any(mot in nom.lower().split("_")
                        for mot in ("cle", "cles", "key", "apikey"))]
    assert interdits == [], interdits
