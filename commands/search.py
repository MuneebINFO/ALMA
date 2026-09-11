"""
Recherches web : Google, YouTube, Wikipedia, Claude, traduction.

Aucune API payante : on construit des URL de recherche et on ouvre le
navigateur. Wikipedia utilise la librairie Python `wikipedia` (gratuite) pour
lire un résumé, avec repli sur l ouverture de la page si elle est absente.
"""

from __future__ import annotations

from urllib.parse import quote, quote_plus

from core.context import CommandContext, Response
from core.registry import command

from commands.websites import open_url

SEARCH_VERBS = r"(?:cherche|chercher|recherche|rechercher|trouve|trouver|search|find|google)"

# Langues reconnues pour la traduction (nom parle -> code Google Traduction).
LANGUAGES = {
    "francais": "fr", "french": "fr",
    "anglais": "en", "english": "en",
    "espagnol": "es", "spanish": "es",
    "allemand": "de", "german": "de",
    "italien": "it", "italian": "it",
    "portugais": "pt", "neerlandais": "nl", "hollandais": "nl", "dutch": "nl",
    "japonais": "ja", "chinois": "zh-CN", "arabe": "ar", "russe": "ru",
    "coreen": "ko", "turc": "tr", "polonais": "pl", "suedois": "sv",
}


@command(
    name="search_youtube",
    # Les formes « cherche X sur YouTube » et « mets X sur YouTube » sont
    # traitees par site_search, qui reutilise en plus l onglet deja ouvert.
    # Il ne reste ici que le raccourci direct.
    patterns=[r"^youtube\s+(.+)$"],
    category="Recherche",
    description="Rechercher sur YouTube (raccourci)",
    examples=["youtube lofi hip hop"],
    priority=95,
)
def search_youtube(ctx: CommandContext) -> Response:
    """Lance une recherche YouTube dans le navigateur."""
    query = ctx.arg
    if not query:
        return ctx.erreur("Que dois-je chercher sur YouTube ?",
                          "What should I look up on YouTube?")
    open_url("https://www.youtube.com/results?search_query=" + quote_plus(query))
    return ctx.reponse("Je cherche « " + query + " » sur YouTube.",
                       'Searching YouTube for "' + query + '".')


@command(
    name="ask_claude",
    informatif=True,
    patterns=[
        r"^(?:demande|demander|pose|poser)\s+a\s+claude\s*(?:que|de|:)?\s*(.*)$",
        r"^claude\s*,?\s+(.+)$",
    ],
    category="Recherche",
    description="Envoyer une question à Claude dans le navigateur",
    examples=["demande a Claude comment fonctionne un moteur de recherche"],
    priority=92,
)
def ask_claude(ctx: CommandContext) -> Response:
    """
    Ouvre claude.ai avec la question pre-remplie.
    Aucune API n est appelee : c est le navigateur qui fait le travail, donc
    aucun coût cote Alma.
    """
    query = ctx.arg
    if not query:
        open_url("https://claude.ai/new")
        return ctx.reponse("J'ouvre Claude.", "Opening Claude.")
    from core import win_utils

    # La question est aussi copiée dans le presse-papiers : pratique si le
    # paramêtre d URL n'est pas pris en compte par le site.
    win_utils.set_clipboard(query)
    open_url("https://claude.ai/new?q=" + quote_plus(query))
    return ctx.reponse(
        "Je transmets votre question à Claude (elle est aussi copiée dans le presse-papiers).",
        "Passing your question to Claude (it's also copied to the clipboard).",
    )


def _wikipedia_summary(query: str, lang: str = "fr", timeout: int = 8) -> tuple[str, str]:
    """
    Résumé Wikipedia via l API REST officielle (gratuite, sans cle).

    On n utilise pas la librairie `wikipedia` par defaut : elle envoie un
    User-Agent que Wikipedia refuse desormais, ce qui la fait échouér.
    Retourne (titre, résumé) ou ("", "").
    """
    import requests

    headers = {"User-Agent": "Alma-Assistant-Local/1.0 (assistant personnel hors ligne)"}
    base = "https://" + lang + ".wikipedia.org"

    # 1) On cherche le titre exact de la page correspondante.
    search = requests.get(
        base + "/w/api.php",
        params={
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": 1, "format": "json",
        },
        headers=headers,
        timeout=timeout,
    )
    search.raise_for_status()
    hits = ((search.json() or {}).get("query") or {}).get("search") or []
    if not hits:
        return "", ""
    title = hits[0].get("title", "")

    # 2) On recupere le résumé de cette page.
    summary = requests.get(
        base + "/api/rest_v1/page/summary/" + quote(title.replace(" ", "_")),
        headers=headers,
        timeout=timeout,
    )
    summary.raise_for_status()
    payload = summary.json() or {}
    return title, str(payload.get("extract", "") or "")


def _wikipedia_summary_legacy(query: str, lang: str = "fr") -> str:
    """Repli sur la librairie `wikipedia` si elle est installee et fonctionne."""
    try:
        import wikipedia
    except ImportError:
        return ""
    try:
        wikipedia.set_lang(lang)
        return str(wikipedia.summary(query, sentences=3, auto_suggest=True))
    except Exception as exc:
        if type(exc).__name__ == "DisambiguationError":
            options = ", ".join(list(getattr(exc, "options", []))[:5])
            return "Ce terme est ambigu. Vouliez-vous dire : " + options + " ?"
        return ""


@command(
    name="search_wikipedia",
    informatif=True,
    patterns=[
        r"^" + SEARCH_VERBS + r"\s+(.+?)\s+sur\s+wikipedia$",
        r"^wikipedia\s+(.+)$",
        r"^(?:qui\s+est|qu\s+est\s+ce\s+que|qu\s+est\s+ce\s+qu|c\s+est\s+quoi|parle\s+moi\s+de|definition\s+de)\s+(.+)$",
        r"^(?:who\s+is|what\s+is|tell\s+me\s+about|definition\s+of)\s+(.+)$",
    ],
    category="Recherche",
    description="Lire un résumé Wikipedia",
    examples=["cherche Alan Turing sur Wikipedia", "qui est Marie Curie",
              "who is Marie Curie"],
    priority=90,
)
def search_wikipedia(ctx: CommandContext) -> Response:
    """Recupere un résumé Wikipedia et l affiche (et le lit en mode voix)."""
    query = ctx.arg
    if not query:
        return ctx.erreur("Sur quel sujet ?", "On what subject?")
    lang = ctx.lang
    page_url = "https://" + lang + ".wikipedia.org/wiki/Special:Search?search=" + quote_plus(query)

    try:
        title, extract = _wikipedia_summary(query, lang)
    except Exception:
        title, extract = "", ""

    if not extract:
        extract = _wikipedia_summary_legacy(query, lang)
        title = query

    if extract:
        # On limite la lecture a quelques phrases pour rester ecoûtable.
        sentences = extract.split(". ")
        short = ". ".join(sentences[:3]).strip()
        if short and not short.endswith("."):
            short += "."
        return ctx.reponse("D'après Wikipedia, " + title + " : " + short,
                           "According to Wikipedia, " + title + ": " + short)

    open_url(page_url)
    return ctx.reponse(
        "Je n'ai pas trouvé de résumé pour « " + query + " » : j'ouvre la recherche Wikipedia.",
        "I couldn't find a summary for \"" + query + "\": opening the Wikipedia search.",
    )


@command(
    name="translate",
    informatif=True,
    patterns=[
        r"^(?:traduis|traduire|traduit|translate)\s+(.+?)\s+(?:en|in|into|vers|to)\s+([a-z]+)$",
        r"^(?:traduis|traduire|traduit|translate)\s+(.+)$",
    ],
    category="Recherche",
    description="Traduire un texte avec Google Traduction",
    examples=["traduis bonjour le monde en anglais", "traduis good morning en francais"],
    priority=91,
)
def translate(ctx: CommandContext) -> Response:
    """Ouvre Google Traduction avec le texte pre-rempli."""
    text = ctx.arg
    if not text:
        return ctx.erreur("Que dois-je traduire ?", "What should I translate?")
    target_word = ctx.group(2).lower() if ctx.match and ctx.match.lastindex and ctx.match.lastindex >= 2 else ""
    target = LANGUAGES.get(target_word, "")
    if not target:
        # Pas de langue precisee : on vise l AUTRE langue que celle parlee.
        # Demander « traduis bonjour » en francais vise l anglais, et
        # "translate hello" vise le francais -- sinon on traduirait une
        # phrase vers sa propre langue.
        target = "fr" if ctx.lang == "en" else "en"
    url = (
        "https://translate.google.com/?sl=auto&tl=" + target
        + "&text=" + quote_plus(text) + "&op=translate"
    )
    open_url(url)
    label = target_word if target_word in LANGUAGES else target
    return ctx.reponse("Je traduis « " + text + " » en " + label + ".",
                       'Translating "' + text + '" into ' + label + ".")


@command(
    name="search_google",
    patterns=[
        r"^" + SEARCH_VERBS + r"\s+(.+?)\s+sur\s+(?:google|internet|le\s+web)$",
        r"^" + SEARCH_VERBS + r"\s+(?:for\s+)?(.+?)\s+on\s+(?:google|the\s+web|the\s+internet)$",
        r"^google\s+(?:for\s+)?(.+)$",
        r"^(?:search|look\s+up)\s+google\s+(?:for\s+)?(.+)$",
        r"^" + SEARCH_VERBS + r"\s+(?:for\s+)?(.+)$",
        r"^(?:recherche\s+google|search)\s*:?\s*(.+)$",
    ],
    category="Recherche",
    description="Rechercher sur Google",
    examples=["cherche des idées de cadeaux", "google météo Bruxelles",
              "search Google for gift ideas"],
    priority=80,
)
def search_google(ctx: CommandContext) -> Response:
    """Lance une recherche Google dans le navigateur."""
    query = ctx.arg
    if not query:
        return ctx.erreur("Que dois-je chercher ?", "What should I search for?")
    open_url("https://www.google.com/search?q=" + quote_plus(query))
    return ctx.reponse("Je cherche « " + query + " » sur Google.",
                       'Searching Google for "' + query + '".')


@command(
    name="search_images",
    patterns=[
        r"^" + SEARCH_VERBS + r"\s+(?:des\s+|une\s+|les\s+|some\s+)?"
        r"(?:images?|photos?|pictures?|pics?)\s+(?:de\s+|d\s+|of\s+)?(.+)$",
        r"^(?:montre|montrer|show)\s+(?:moi\s+|me\s+)?(?:des\s+|some\s+)?"
        r"(?:images?|photos?|pictures?|pics?)\s+(?:de\s+|d\s+|of\s+)?(.+)$",
    ],
    category="Recherche",
    description="Rechercher des images",
    examples=["cherche des images de montagne", "montre moi des photos de chats",
              "show me pictures of mountains"],
    priority=93,
)
def search_images(ctx: CommandContext) -> Response:
    """Lance une recherche Google Images."""
    query = ctx.arg
    if not query:
        return ctx.erreur("Des images de quoi ?", "Images of what?")
    open_url("https://www.google.com/search?tbm=isch&q=" + quote_plus(query))
    return ctx.reponse("Voici des images de « " + query + " ».",
                       'Here are images of "' + query + '".')


@command(
    name="search_maps",
    patterns=[
        r"^(?:ou\s+est|ou\s+se\s+trouve|itineraire\s+(?:vers|pour)|localise|carte\s+de)\s+(.+)$",
        r"^" + SEARCH_VERBS + r"\s+(.+?)\s+sur\s+(?:google\s+)?maps$",
        r"^(?:where\s+is|directions\s+to|locate)\s+(.+)$",
    ],
    category="Recherche",
    description="Localiser un lieu sur Google Maps",
    examples=["ou est la gare centrale", "itineraire vers Bruxelles"],
    priority=89,
)
def search_maps(ctx: CommandContext) -> Response:
    """Ouvre Google Maps sur un lieu."""
    query = ctx.arg
    if not query:
        return ctx.erreur("Quel lieu ?", "Which place?")
    open_url("https://www.google.com/maps/search/" + quote_plus(query))
    return ctx.reponse("Je localise « " + query + " » sur Maps.",
                       'Finding "' + query + '" on Maps.')
