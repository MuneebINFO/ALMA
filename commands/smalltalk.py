"""
Petite conversation : salutations, politesse, humour.

Aucune generation de texte par IA : uniquement des reponses predefinies
choisies aleatoirement pour eviter l effet robot.
"""

from __future__ import annotations

import random
from datetime import datetime

from core.context import CommandContext, Response
from core.registry import command


def greeting_for_now(user_name: str = "", lang: str = "fr") -> str:
    """Salutation adaptee a l'heure de la journee, dans la langue demandee."""
    hour = datetime.now().hour
    if lang == "en":
        if hour < 6:
            base = "Good night"
        elif hour < 12:
            base = "Good morning"
        elif hour < 18:
            base = "Good afternoon"
        else:
            base = "Good evening"
        who = (" " + user_name) if user_name else ""
        return base + who + ", I'm at your service."

    if hour < 6:
        base = "Bonne nuit"
    elif hour < 12:
        base = "Bonjour"
    elif hour < 18:
        base = "Bon après-midi"
    else:
        base = "Bonsoir"
    who = (" " + user_name) if user_name else ""
    return base + who + ", je suis à votre service."


@command(
    name="greet",
    informatif=True,
    patterns=[r"^(?:bonjour|salut|coucou|bonsoir|hello|hey|yo|hi)\b"],
    category="Conversation",
    description="Dire bonjour",
    examples=["bonjour", "salut Alma"],
    priority=70,
)
def greet(ctx: CommandContext) -> Response:
    """Repond a une salutation, dans la langue employee."""
    user = str(ctx.config.get("general.user_name", "") or "")
    return Response(text=greeting_for_now(user, ctx.lang))


@command(
    name="how_are_you",
    informatif=True,
    patterns=[r"(?:comment\s+(?:ca\s+va|vas\s+tu|allez\s+vous)|ca\s+va\s*\?*$|how\s+are\s+you)"],
    category="Conversation",
    description="Prendre des nouvelles",
    examples=["comment ca va", "ca va"],
    priority=75,
)
def how_are_you(ctx: CommandContext) -> Response:
    """Reponse predefinie a "comment ca va"."""
    if ctx.lang == "en":
        answers = [
            "All my systems are running perfectly, thanks. And you?",
            "In great shape, ready to help.",
            "Running at full speed. What can I do for you?",
        ]
    else:
        answers = [
            "Tous mes systèmes fonctionnent parfaitement, merci. Et vous ?",
            "En pleine forme, prêt à vous aider.",
            "Je tourne a plein régime. Que puis-je faire pour vous ?",
        ]
    return Response(text=random.choice(answers))


@command(
    name="thanks",
    informatif=True,
    patterns=[r"^(?:merci|merci\s+beaucoup|thanks|thank\s+you|nickel|parfait|super)\b"],
    category="Conversation",
    description="Répondre à un remerciement",
    examples=["merci"],
    priority=70,
)
def thanks(ctx: CommandContext) -> Response:
    """Reponse a un remerciement."""
    if ctx.lang == "en":
        return Response(text=random.choice(
            ["My pleasure.", "You're welcome.", "At your service."]))
    return Response(text=random.choice(["Avec plaisir.", "Je vous en prie.", "À votre service."]))


@command(
    name="who_are_you",
    informatif=True,
    patterns=[r"(?:qui\s+es\s+tu|tu\s+es\s+qui|presente\s+toi|who\s+are\s+you|c\s+est\s+quoi\s+alma)"],
    category="Conversation",
    description="Se présenter",
    examples=["qui es-tu"],
    priority=92,
)
def who_are_you(ctx: CommandContext) -> Response:
    """Presentation de l'assistant."""
    name = str(ctx.config.get("general.assistant_name", "Alma"))
    return ctx.reponse(
        "Je suis " + name + ", votre assistant local. Je fonctionne entièrement sur "
        "votre ordinateur, sans intelligence artificielle distante ni abonnement. "
        "Dites « aide » pour connaître mes commandes.",
        "I'm " + name + ", your local assistant. I run entirely on your computer, "
        "with no remote artificial intelligence and no subscription. "
        "Say \"help\" to see what I can do.",
    )


@command(
    name="joke",
    informatif=True,
    patterns=[r"(?:raconte|dis|donne)\s*(?:moi)?\s*(?:une|un)?\s*(?:blague|histoire\s+drole|joke)",
              r"^(?:blague|joke)$", r"fais\s+moi\s+rire",
              r"(?:tell|give)\s*(?:me)?\s*a\s+joke", r"make\s+me\s+laugh"],
    keywords=[["blague"], ["joke"], ["tell", "joke"]],
    category="Conversation",
    description="Raconter une blague",
    examples=["raconte-moi une blague", "tell me a joke"],
    priority=88,
)
def joke(ctx: CommandContext) -> Response:
    """Raconte une blague tiree d'une liste locale (aucun appel reseau)."""
    return Response(text=random.choice(JOKES_EN if ctx.lang == "en" else JOKES))


JOKES = [
    "Pourquoi les développeurs détestent-ils la nature ? Il y a trop de bugs.",
    "Un octet entre dans un bar et commande un verre. Le barman demande : tu veux un bit ?",
    "Pourquoi le programmeur est-il mort sous la douche ? Le shampoing disait : "
    "faire mousser, rincer, répéter.",
    "Il y a 10 sortes de gens : ceux qui comprennent le binaire et les autres.",
    "Que dit un informaticien quand il se noie ? F1 ! F1 !",
    "Pourquoi les plongeurs plongent-ils toujours en arrière ? "
    "Parce que sinon ils tombent dans le bateau.",
    "Qu'est-ce qu'un ordinateur dit à l'autre ? On se voit sur le réseau.",
    "Comment appelle-t-on un chat tombé dans un pot de peinture le jour de Noël ? "
    "Un chat-peint de Noël.",
    "Un SQL entre dans un bar, s'approche de deux tables et demande : je peux vous joindre ?",
    "Pourquoi les fantômes sont-ils de mauvais menteurs ? Parce qu'on voit clair à travers eux.",
    "Le cache, c'est comme le frigo : on y met des choses et on oublie pourquoi.",
    "J'allais faire une blague sur les récursions, mais j'allais faire une blague "
    "sur les récursions.",
]

# Les memes, cote anglais : traduire mot a mot tuerait la moitie des chutes,
# donc ce sont des blagues du meme genre plutot que des traductions.
JOKES_EN = [
    "Why do developers hate nature? It has too many bugs.",
    "A byte walks into a bar and orders a drink. The bartender asks: want a bit?",
    "Why did the programmer die in the shower? The shampoo said: lather, rinse, repeat.",
    "There are 10 kinds of people: those who understand binary, and those who don't.",
    "What does a drowning computer scientist shout? F1! F1!",
    "Why do divers always fall backwards off the boat? Because otherwise "
    "they'd fall into it.",
    "What did one computer say to the other? See you on the network.",
    "A SQL query walks into a bar, goes up to two tables and asks: may I join you?",
    "Why are ghosts such bad liars? Because you can see right through them.",
    "Cache is like the fridge: you put things in and forget why.",
    "I was going to tell a joke about recursion, but I was going to tell a joke "
    "about recursion.",
]
