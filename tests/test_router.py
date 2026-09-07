"""
Tests du moteur de routage : verifier que les bonnes phrases declenchent
les bons handlers. C est le test le plus important du projet.
"""

import pytest

from core.context import SOURCE_GESTURE, SOURCE_VOICE, Utterance

# (phrase, nom de commande attendu)
CAS_NOMINAUX = [
    # Applications
    ("Alma, ouvre Chrome", "open_app"),
    ("ouvre la calculatrice", "open_app"),
    ("lance VS Code", "open_app"),
    ("demarre le bloc note", "open_app"),
    ("ferme Chrome", "close_app"),
    # Sites web
    ("ouvre YouTube", "open_website"),
    ("ouvre Gmail", "open_website"),
    ("va sur GitHub", "open_website"),
    ("ouvre Netflix", "open_website"),
    # Recherches
    ("ouvre YouTube et cherche lofi hip hop", "site_search"),
    ("cherche une recette de crepes sur YouTube", "site_search"),
    ("va sur Netflix et mets Fast and Furious", "site_search"),
    ("mets Interstellar sur Prime Video", "site_search"),
    ("cherche les dernieres nouvelles sur l IA sur Google", "site_search"),
    ("cherche des idees de cadeaux", "search_google"),
    ("demande a Claude comment fonctionne un moteur de recherche", "ask_claude"),
    ("cherche Alan Turing sur Wikipedia", "search_wikipedia"),
    ("qui est Marie Curie", "search_wikipedia"),
    ("traduis bonjour le monde en anglais", "translate"),
    ("cherche des images de montagne", "search_images"),
    # Systeme
    ("mets le volume a 30%", "volume_set"),
    ("coupe le son", "volume_mute"),
    ("remets le son", "volume_unmute"),
    ("monte le son", "volume_up"),
    ("baisse le volume", "volume_down"),
    ("mets la luminosite a 50%", "brightness_set"),
    ("prends une capture d ecran", "screenshot"),
    ("verrouille l ordinateur", "lock_session"),
    ("eteins l ordinateur", "shutdown_pc"),
    ("redemarre l ordinateur", "restart_pc"),
    ("ouvre le dossier telechargements", "open_folder"),
    # Productivite
    ("note que je dois rappeler ma banque demain", "add_note"),
    ("lis mes notes", "read_notes"),
    ("supprime la note 2", "delete_note"),
    ("rappelle-moi dans 10 minutes de sortir le gateau", "set_reminder"),
    ("lance un minuteur de 5 minutes", "set_timer"),
    ("mes rappels", "list_reminders"),
    ("lis le presse-papiers", "read_clipboard"),
    # Informations
    ("quelle heure est-il", "get_time"),
    ("quel jour sommes-nous", "get_date"),
    ("quel temps fait-il a Bruxelles", "weather"),
    # Musique
    ("mets de la musique", "play_music"),
    # Lecture et pause explicites, distinctes de la bascule « pause » seule.
    ("lance la vidéo", "media_lecture"),
    ("joue la vidéo", "media_lecture"),
    ("démarre la vidéo", "media_lecture"),
    ("remets la vidéo", "media_lecture"),
    ("mets la vidéo en marche", "media_lecture"),
    ("mets pause à la vidéo", "media_mettre_en_pause"),
    ("mets la vidéo en pause", "media_mettre_en_pause"),
    ("pause la vidéo", "media_mettre_en_pause"),
    ("mets pause à la musique", "media_mettre_en_pause"),
    ("mets pause sur l ecran 2", "media_pause_ecran"),
    ("arrete la video sur le deuxieme ecran", "media_pause_ecran"),
    ("reprends la lecture sur l ecran 2", "media_reprise_ecran"),
    ("mets tout en pause", "media_pause_tout"),
    ("qu est-ce qui joue", "media_what_is_playing"),
    ("chanson suivante", "media_next"),
    ("chanson precedente", "media_previous"),
    ("arrete la musique", "media_mettre_en_pause"),
    # Divers et conversation
    ("que peux-tu faire", "help"),
    ("aide", "help"),
    ("raconte-moi une blague", "joke"),
    ("bonjour", "greet"),
    ("comment ca va", "how_are_you"),
    ("qui es-tu", "who_are_you"),
    ("merci", "thanks"),
    ("historique", "history"),
    ("repete", "repeat_last"),
    ("au revoir Alma", "exit"),
]


def resolve(router, config, phrase, source="text"):
    utterance = Utterance.parse(
        phrase, source=source, wake_words=config.get("general.wake_words")
    )
    return router.resolve(utterance, None)


@pytest.mark.parametrize("phrase,attendu", CAS_NOMINAUX)
def test_les_phrases_declenchent_la_bonne_commande(router, config, phrase, attendu):
    resolution = resolve(router, config, phrase)
    assert resolution is not None, "aucune commande trouvee pour : " + phrase
    assert resolution.command.name == attendu


def test_phrase_inconnue_ne_matche_rien(router, config):
    assert resolve(router, config, "xyzzy plover blorb") is None


def test_phrase_vide_ne_matche_rien(router, config):
    assert resolve(router, config, "   ") is None


@pytest.mark.parametrize("phrase,attendu", [
    ("ouvre chrome", "open_app"),
    ("OUVRE CHROME", "open_app"),
    ("Ouvre, Chrome !", "open_app"),
    ("alma ouvre chrome", "open_app"),
    ("ok alma, ouvre chrome", "open_app"),
])
def test_casse_ponctuation_et_mot_de_reveil_sont_ignores(router, config, phrase, attendu):
    resolution = resolve(router, config, phrase)
    assert resolution is not None and resolution.command.name == attendu


def test_arguments_extraits_avec_accents_et_casse(router, config):
    """Le groupe capture doit revenir tel que l utilisateur l a ecrit."""
    phrase = "cherche des idees de repas sur Google"
    utterance = Utterance.parse(phrase, wake_words=config.get("general.wake_words"))
    resolution = router.resolve(utterance, None)
    debut, fin = resolution.match.span(1)
    assert utterance.raw[debut:fin] == "des idees de repas"


def test_priorite_app_avant_site_web(router, config):
    """"ouvre Chrome" est une application, "ouvre YouTube" un site web."""
    assert resolve(router, config, "ouvre Chrome").command.name == "open_app"
    assert resolve(router, config, "ouvre YouTube").command.name == "open_website"


def test_les_sources_voix_et_geste_utilisent_le_meme_routeur(router, config):
    """La logique metier ne doit jamais dependre de la source d entree."""
    for source in (SOURCE_VOICE, SOURCE_GESTURE):
        resolution = resolve(router, config, "prends une capture d ecran", source=source)
        assert resolution is not None
        assert resolution.command.name == "screenshot"


def test_toutes_les_commandes_ont_une_description_et_un_nom_unique(router):
    noms = [cmd.name for cmd in router.commands]
    assert len(noms) == len(set(noms)), "noms de commandes dupliques"
    for cmd in router.commands:
        assert cmd.description, "description manquante pour " + cmd.name


def test_les_exemples_documentes_sont_routes_vers_leur_commande(router, config):
    """Chaque exemple affiche dans l aide doit reellement fonctionner."""
    echecs = []
    for cmd in router.commands:
        if cmd.contextuel:
            # Ces commandes exigent un contexte (« recherche Damso » suppose
            # un site ouvert) : elles sont couvertes par test_site_search.py.
            continue
        for exemple in cmd.examples:
            resolution = resolve(router, config, exemple)
            if resolution is None or resolution.command.name != cmd.name:
                trouve = resolution.command.name if resolution else "AUCUNE"
                echecs.append(exemple + " -> " + trouve + " (attendu " + cmd.name + ")")
    assert not echecs, "exemples mal routes :\n" + "\n".join(echecs)


def test_la_liste_des_modules_est_a_jour():
    """
    commands.MODULES doit lister TOUS les modules du dossier : c est cette
    liste qui est embarquee dans l executable. Si ce test echoue, ajoutez le
    module manquant dans commands/__init__.py.
    """
    import commands
    from core.registry import discover_command_modules

    sur_disque = set(discover_command_modules())
    declares = set(commands.MODULES)
    assert declares == sur_disque, (
        "commands/__init__.py MODULES est desynchronise. "
        "Manquants : " + str(sorted(sur_disque - declares)) + " ; "
        "en trop : " + str(sorted(declares - sur_disque))
    )


# Formulations libres : ni mot pour mot, ni dans l ordre attendu.
PHRASES_APPROXIMATIVES = [
    ("je voudrais que tu montes le son", "volume_up"),
    ("tu peux baisser le volume stp", "volume_down"),
    ("fais moi une capture", "screenshot"),
    ("j aimerais savoir quelle heure il est", "get_time"),
    ("note quelque part que je dois appeler le dentiste", "add_note"),
    ("peux-tu me dire la météo", "weather"),
    ("est-ce que tu peux mettre en pause", "media_play_pause"),
    ("ferme moi Chrome s il te plait", "close_app"),
    ("montre moi mes notes", "read_notes"),
    ("balance de la musique", "play_music"),
    ("verrouille moi cette machine", "lock_session"),
    ("programme un minuteur de 3 minutes", "set_timer"),
    ("coupe le son sur le deuxième écran", "media_pause_ecran"),
]


@pytest.mark.parametrize("phrase,attendu", PHRASES_APPROXIMATIVES)
def test_les_formulations_approximatives_sont_comprises(router, config, phrase, attendu):
    """
    L'assistant doit comprendre une intention même mal formulée : c'est ce qui
    sépare un moteur de règles utilisable d'un moteur qui exige la phrase exacte.
    """
    resolution = resolve(router, config, phrase)
    assert resolution is not None, "aucune commande trouvée pour : " + phrase
    assert resolution.command.name == attendu


def test_une_phrase_hors_sujet_reste_ignoree(router, config):
    """
    La tolérance ne doit pas virer au déclenchement systématique : une phrase
    sans rapport doit continuer à ne rien déclencher.
    """
    for phrase in ("il fait beau aujourd hui", "j ai mangé une pomme ce matin",
                   "xyzzy plover blorb"):
        assert resolve(router, config, phrase) is None, phrase


# Formulations voisines qui doivent garder leur commande d'origine : c'est
# la contrepartie des motifs de lecture et de pause explicites.
VOISINS_A_NE_PAS_CAPTURER = [
    ("remets le son", "volume_unmute"),        # rétablir le volume, pas relire
    # « Arrêter la lecture » a été retiré : mettre en pause conserve la
    # position, ce qu'un arrêt pur perdait.
    ("arrête la musique", "media_mettre_en_pause"),
    ("arrête la vidéo", "media_mettre_en_pause"),
    ("pause", "media_play_pause"),             # bascule, sans objet précisé
    ("play", "media_play_pause"),
    ("mets de la musique", "play_music"),      # lancer une lecture depuis zéro
    ("mets pause sur l écran 2", "media_pause_ecran"),
    ("lance un minuteur de 5 minutes", "set_timer"),
    ("clique sur la vidéo Interstellar", "cliquer_sur"),
]


@pytest.mark.parametrize("phrase,attendu", VOISINS_A_NE_PAS_CAPTURER)
def test_les_commandes_voisines_ne_sont_pas_capturees(router, config, phrase, attendu):
    """
    « lance la vidéo » et « mets pause à la vidéo » sont des motifs larges :
    ils ne doivent pas déborder sur les commandes proches.
    """
    resolution = resolve(router, config, phrase)
    assert resolution is not None, phrase
    assert resolution.command.name == attendu


def test_un_titre_apres_l_objet_reste_une_recherche(router, config):
    """
    « lance la vidéo » lance la lecture, mais « lance la vidéo Interstellar »
    désigne une vidéo précise : l'objet doit terminer la phrase.
    """
    resolution = resolve(router, config, "lance la vidéo Interstellar")
    assert resolution is None or resolution.command.name != "media_lecture"
