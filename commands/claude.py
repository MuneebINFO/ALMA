"""
Parler a l application Claude installee sur la machine.

Alma ne remplace pas Claude et ne l imite pas : elle lui transmet la question,
attend, et lit la reponse a voix haute. Le travail est fait par l application
deja installee et deja connectee, avec l abonnement de l utilisateur -- aucune
cle d API n intervient, et Alma n en detient aucune.

Deux facons d y acceder, et elles ne servent pas a la meme chose :

  - CES COMMANDES pilotent la fenetre. On voit ce qui se passe, la
    conversation reste dans l historique de l application, et Cowork ou Code
    s atteignent d un mot. En contrepartie, il faut attendre que la reponse
    finisse de s ecrire ;
  - le PROVIDER `claude_code` (core/providers) appelle le CLI en mode
    headless. Plus direct, sans fenetre a piloter, mais sans trace visible.

Voir docs : ai_fallback dans config.yaml.
"""

from __future__ import annotations

from core import claude_app, text_utils
from core.context import CommandContext, Response
from core.registry import command

# Ce qu on peut demander d afficher, et les mots qui y menent. Les libelles de
# l application sont en anglais, ce qu on ne demandera pas a l utilisateur.
# Chaque entree : (libelle dans l application, nom parle en francais, en anglais).
SECTIONS = {
    "cowork": ("Chat and Cowork", "Cowork", "Cowork"),
    "chat": ("Chat and Cowork", "le chat", "the chat"),
    "conversation": ("Chat and Cowork", "le chat", "the chat"),
    "code": ("Code", "Claude Code", "Claude Code"),
    "artifacts": ("Artifacts", "les artifacts", "the artifacts"),
    "artefacts": ("Artifacts", "les artifacts", "the artifacts"),
    "nouvelle": ("New", "une nouvelle session", "a new session"),
    "nouveau": ("New", "une nouvelle session", "a new session"),
    "new": ("New", "une nouvelle session", "a new session"),
}

# Longueur lue a voix haute : au-dela, on renvoie a l ecran.
LONGUEUR_PARLEE = 500


def _application_ouverte(ctx: CommandContext) -> bool:
    """Guard : ces commandes n ont de sens que si l application tourne."""
    return claude_app.fenetre() is not None


@command(
    name="claude_demander",
    patterns=[
        r"^(?:demande|demander|pose|poser)\s+a\s+claude\s*(?:que|de|:)?\s*(?P<question>.+)$",
        r"^claude\s*,?\s+(?P<question>.+)$",
        r"^ask\s+claude\s*(?:that|to|:)?\s*(?P<question>.+)$",
        r"^tell\s+claude\s*(?::)?\s*(?P<question>.+)$",
    ],
    keywords=[["demande", "claude"], ["ask", "claude"]],
    category="Recherche",
    description="Poser une question à l'application Claude et lire sa réponse",
    examples=["demande à Claude comment fonctionne un moteur de recherche",
              "ask Claude how a search engine works"],
    priority=95,
    guard=_application_ouverte,
    informatif=True,
    # N a de sens que si l application tourne : sinon la question part au
    # navigateur, par ask_claude. Verifie dans tests/test_claude_app.py.
    contextuel=True,
)
def claude_demander(ctx: CommandContext) -> Response:
    """Transmet la question à l'application Claude et rapporte sa réponse."""
    question = (ctx.group("question") or "").strip()
    if not question:
        return ctx.erreur("Que dois-je lui demander ?", "What should I ask it?")

    fenetre = claude_app.fenetre()
    if not claude_app.reveiller(fenetre):
        return ctx.erreur(
            "L'application Claude ne répond pas. Ouvrez-la, puis réessayez.",
            "The Claude app isn't responding. Open it, then try again.",
        )

    # La question part dans une conversation NEUVE, et on demande d'abord.
    # Sans cela elle atterrit dans ce qui est affiché — une session Claude Code
    # en cours de travail, par exemple — et s'y mélange à autre chose.
    if not ctx.confirm("J'ouvre une nouvelle conversation Claude ?"):
        return ctx.reponse("Très bien, je n'ouvre rien.",
                           "All right, I won't open anything.", speak=False)
    # Le chat d'abord : « New » depuis la section Code créerait une session de
    # code, pas une conversation.
    claude_app.activer(fenetre, "Chat and Cowork")
    if not claude_app.activer(fenetre, "New"):
        return ctx.erreur("Je n'ai pas pu ouvrir de nouvelle conversation Claude.",
                          "I couldn't open a new Claude conversation.")

    avant = claude_app.etat(fenetre)
    if not claude_app.poser(fenetre, question):
        return ctx.erreur("Je n'ai pas trouvé où écrire dans l'application Claude.",
                          "I couldn't find where to type in the Claude app.")

    reponse = claude_app.attendre_la_reponse(fenetre, avant)
    if not reponse:
        return ctx.erreur(
            "Claude n'a rien répondu dans le temps imparti. "
            "La réponse arrive peut-être encore à l'écran.",
            "Claude didn't answer in time. The answer may still be arriving on screen.",
        )
    if len(reponse) > LONGUEUR_PARLEE:
        coupe = reponse[:LONGUEUR_PARLEE].rsplit(" ", 1)[0]
        return ctx.reponse(coupe + "… La suite est à l'écran.",
                           coupe + "… The rest is on screen.")
    return Response(text=reponse)


def _delegation_ouverte(ctx: CommandContext) -> bool:
    """Guard : la délégation doit avoir été activée dans config.yaml."""
    return bool(ctx.config.get("ai_fallback.enabled", False))


@command(
    name="claude_code_tache",
    patterns=[
        r"^(?:demande|demander|dis|dire)\s+a\s+claude\s+code\s+(?:de\s+)?(?P<tache>.+)$",
        r"^(?:lance|lancer|fais|faire)\s+(?:une\s+)?tache\s+"
        r"(?:avec\s+|dans\s+|en\s+|sur\s+)?claude\s+code\s*:?\s*(?P<tache>.+)$",
        r"^claude\s+code\s*,\s*(?P<tache>.+)$",
        r"^ask\s+claude\s+code\s+to\s+(?P<tache>.+)$",
        r"^(?:run|start)\s+(?:a\s+)?task\s+(?:with\s+|in\s+|on\s+)?claude\s+code\s*:?\s*(?P<tache>.+)$",
    ],
    keywords=[["claude", "code", "demande"], ["claude", "code", "ask"]],
    category="Recherche",
    description="Confier une tâche au CLI Claude Code",
    examples=["demande à Claude Code de lister les fichiers du dossier",
              "ask Claude Code to list the files in the folder"],
    priority=98,
    guard=_delegation_ouverte,
    informatif=True,
    contextuel=True,
)
def claude_code_tache(ctx: CommandContext) -> Response:
    """Transmet la demande au CLI Claude Code et rapporte sa réponse."""
    from core.ai_fallback import handle_with_ai
    from core.providers.claude_code_provider import ClaudeCodeProvider

    tache = (ctx.group("tache") or "").strip()
    if not tache:
        return ctx.erreur("Que dois-je lui demander ?", "What should I ask it?")
    # Le provider est construit ici plutôt que lu dans la configuration : la
    # phrase dit « Claude Code », c'est donc lui qu'on veut, même si un autre
    # provider est choisi par défaut. `enabled` reste l'interrupteur général.
    return Response(text=handle_with_ai(tache, ctx.config, ClaudeCodeProvider(ctx.config)))


@command(
    name="claude_cowork",
    patterns=[
        r"^(?:demande|demander|dis|dire)\s+a\s+cowork\s+(?:de\s+)?(?P<tache>.+)$",
        r"^(?:lance|lancer|demarre|demarrer|fais|faire)\s+(?:une\s+)?"
        r"(?:tache\s+)?(?:en\s+|dans\s+|avec\s+|sur\s+)?cowork\s*:?\s*(?P<tache>.+)$",
        r"^(?P<tache>.+?)\s+(?:en|dans|avec)\s+cowork$",
        r"^ask\s+cowork\s+to\s+(?P<tache>.+)$",
        r"^(?:run|start)\s+(?:a\s+)?task\s+(?:in\s+|with\s+|on\s+)?cowork\s*:?\s*(?P<tache>.+)$",
        r"^(?P<tache>.+?)\s+in\s+cowork$",
    ],
    keywords=[["cowork"]],
    category="Recherche",
    description="Lancer une tâche dans Cowork",
    examples=["demande à Cowork de résumer mes notes de la semaine",
              "lance une tâche Cowork : trier mes captures d'écran",
              "ask Cowork to summarize my notes from this week"],
    priority=97,
    guard=_application_ouverte,
    contextuel=True,
)
def claude_cowork(ctx: CommandContext) -> Response:
    """Ouvre une session Cowork et y dicte la tâche."""
    tache = (ctx.group("tache") or "").strip()
    if not tache:
        return ctx.erreur("Quelle tâche dois-je lancer ?", "Which task should I start?")

    fenetre = claude_app.fenetre()
    if not claude_app.reveiller(fenetre):
        return ctx.erreur("L'application Claude ne répond pas.",
                          "The Claude app isn't responding.")

    # Une session neuve, sinon la tâche part dans la conversation affichée --
    # et le sélecteur Chat/Cowork n'existe que sur une page vierge.
    if not claude_app.activer(fenetre, "New"):
        return ctx.erreur("Je n'ai pas pu ouvrir de nouvelle session Claude.",
                          "I couldn't open a new Claude session.")
    if not claude_app.activer(fenetre, "Cowork"):
        return ctx.erreur(
            "Je ne trouve pas le mode Cowork. Il n'apparaît que sur une page vierge.",
            "I can't find Cowork mode. It only shows up on a blank page.",
        )
    if not claude_app.poser(fenetre, tache):
        return ctx.erreur("Je n'ai pas trouvé où écrire dans l'application Claude.",
                          "I couldn't find where to type in the Claude app.")
    # On ne lit pas la reponse : une tache Cowork dure, et l ecran la montre.
    return ctx.reponse("C'est parti dans Cowork.", "Off it goes in Cowork.", speak=False)


@command(
    name="claude_section",
    patterns=[
        # « ouvre Cowork », « passe sur les artifacts », « nouvelle session »
        r"^(?:va|vas|passe|passer|bascule|basculer|ouvre|ouvrir|montre|affiche)\s+"
        r"(?:moi\s+)?(?:sur|dans|a|vers|en)?\s*(?:l\s+|le\s+|la\s+|les\s+)?"
        r"(?P<section>cowork|chat|conversation|artifacts|artefacts)"
        r"(?:\s+(?:de\s+|dans\s+|sur\s+)?claude)?$",
        # « ouvre Claude Code », « va sur Claude Cowork », ou « Claude Code »
        # tout court -- sans quoi la phrase partirait en question posee a Claude.
        r"^(?:(?:va|vas|passe|bascule|ouvre|ouvrir|lance|lancer)\s+(?:sur\s+|dans\s+)?)?"
        r"claude\s+(?P<section>cowork|chat|code|artifacts|artefacts)$",
        # « nouvelle session Claude », « nouveau chat Claude »
        r"^(?P<section>nouvelle|nouveau)\s+(?:session|chat|conversation)"
        r"(?:\s+(?:de\s+|dans\s+)?claude)?$",
        # « go to Cowork », « switch to the artifacts », « open Claude Code »
        r"^(?:go|switch|open|show)\s+(?:me\s+)?(?:to\s+|on\s+)?(?:the\s+)?"
        r"(?P<section>cowork|chat|conversation|artifacts)"
        r"(?:\s+(?:in\s+|of\s+)?claude)?$",
        r"^(?:(?:go|switch|open|show)\s+(?:to\s+)?)?"
        r"claude\s+(?P<section>cowork|chat|code|artifacts)$",
        r"^(?P<section>new)\s+(?:session|chat|conversation)(?:\s+(?:in\s+|of\s+)?claude)?$",
    ],
    keywords=[["claude", "cowork"], ["claude", "code"]],
    category="Recherche",
    description="Afficher Chat, Cowork, Code ou Artifacts dans l'application Claude",
    examples=["ouvre Cowork", "va sur Claude Code", "nouvelle session Claude",
              "go to Cowork"],
    priority=96,
    guard=_application_ouverte,
    contextuel=True,
)
def claude_section(ctx: CommandContext) -> Response:
    """Bascule l'application Claude sur la section demandée."""
    from core import interaction

    demande = text_utils.normalize(ctx.group("section")).strip()
    if demande not in SECTIONS:
        return ctx.erreur("Je ne connais pas cette partie de Claude.",
                          "I don't know that part of Claude.")
    libelle, nom_fr, nom_en = SECTIONS[demande]

    fenetre = claude_app.fenetre()
    if not claude_app.reveiller(fenetre):
        return ctx.erreur("L'application Claude ne répond pas.",
                          "The Claude app isn't responding.")

    cible = claude_app.bouton(fenetre, libelle)
    if cible is None:
        return ctx.erreur(
            "Je ne trouve pas « " + libelle + " » dans l'application Claude.",
            "I can't find \"" + libelle + "\" in the Claude app.",
        )
    if not interaction.cliquer(cible):
        return ctx.erreur("Je n'ai pas réussi à ouvrir " + nom_fr + ".",
                          "I couldn't open " + nom_en + ".")
    return ctx.reponse("J'ouvre " + nom_fr + ".", "Opening " + nom_en + ".", speak=False)
