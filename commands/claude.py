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
SECTIONS = {
    "cowork": ("Chat and Cowork", "Cowork"),
    "chat": ("Chat and Cowork", "le chat"),
    "conversation": ("Chat and Cowork", "le chat"),
    "code": ("Code", "Claude Code"),
    "artifacts": ("Artifacts", "les artifacts"),
    "artefacts": ("Artifacts", "les artifacts"),
    "nouvelle": ("New", "une nouvelle session"),
    "nouveau": ("New", "une nouvelle session"),
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
    ],
    keywords=[["demande", "claude"]],
    category="Recherche",
    description="Poser une question à l'application Claude et lire sa réponse",
    examples=["demande à Claude comment fonctionne un moteur de recherche"],
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
        return Response.error("Que dois-je lui demander ?")

    fenetre = claude_app.fenetre()
    if not claude_app.reveiller(fenetre):
        return Response.error(
            "L'application Claude ne répond pas. Ouvrez-la, puis réessayez."
        )
    avant = claude_app.conversation(fenetre)
    if not claude_app.poser(fenetre, question):
        return Response.error("Je n'ai pas trouvé où écrire dans l'application Claude.")

    reponse = claude_app.attendre_la_reponse(fenetre, avant)
    if not reponse:
        return Response.error(
            "Claude n'a rien répondu dans le temps imparti. "
            "La réponse arrive peut-être encore à l'écran."
        )
    if len(reponse) > LONGUEUR_PARLEE:
        coupe = reponse[:LONGUEUR_PARLEE].rsplit(" ", 1)[0]
        return Response(text=coupe + "… La suite est à l'écran.")
    return Response(text=reponse)


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
    ],
    keywords=[["claude", "cowork"], ["claude", "code"]],
    category="Recherche",
    description="Afficher Chat, Cowork, Code ou Artifacts dans l'application Claude",
    examples=["ouvre Cowork", "va sur Claude Code", "nouvelle session Claude"],
    priority=96,
    guard=_application_ouverte,
    contextuel=True,
)
def claude_section(ctx: CommandContext) -> Response:
    """Bascule l'application Claude sur la section demandée."""
    from core import interaction

    demande = text_utils.normalize(ctx.group("section")).strip()
    if demande not in SECTIONS:
        return Response.error("Je ne connais pas cette partie de Claude.")
    libelle, nom_parle = SECTIONS[demande]

    fenetre = claude_app.fenetre()
    if not claude_app.reveiller(fenetre):
        return Response.error("L'application Claude ne répond pas.")

    cible = claude_app.bouton(fenetre, libelle)
    if cible is None:
        return Response.error(
            "Je ne trouve pas « " + libelle + " » dans l'application Claude."
        )
    if not interaction.cliquer(cible):
        return Response.error("Je n'ai pas réussi à ouvrir " + nom_parle + ".")
    return Response(text="J'ouvre " + nom_parle + ".", speak=False)
