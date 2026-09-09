"""
Memoire longue : ce qu Alma retient d une session a l autre.

Trois choses a ne pas confondre, et qui vivent chacune ailleurs :

  - le CONTEXTE de session (« recherche Damso » apres « va sur YouTube »)
    expire au bout d une minute, dans core.assistant ;
  - les NOTES sont des pense-betes dates, que l on relit et que l on efface ;
  - les SOUVENIRS, ici, sont des faits durables : vos preferences, vos
    proches, vos projets. Ils n expirent pas, et se rappellent par leur sujet.

Tout reste sur la machine, dans data/souvenirs.json, en clair : c est votre
fichier, relisible et modifiable sans passer par Alma.
"""

from __future__ import annotations

from core import text_utils
from core.context import CommandContext, Response
from core.registry import command

# Mots trop courants pour designer un sujet : les retenir ferait ressortir
# n importe quel souvenir a la moindre question.
MOTS_VIDES = {
    "je", "j", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "me", "moi", "te", "toi", "se", "le", "la", "les", "l", "un", "une",
    "des", "du", "de", "d", "au", "aux", "a", "en", "et", "ou", "que",
    "qui", "quoi", "est", "sont", "ai", "as", "mon", "ma", "mes", "ton",
    "ta", "tes", "son", "sa", "ses", "pour", "avec", "dans", "sur", "par",
    "ne", "pas", "plus", "tout", "tous", "toute", "c", "ce", "cette", "s",
}

VERBES_RETENIR = (r"(?:retiens|retenir|souviens\s+toi|souvenez\s+vous|"
                  r"note\s+bien|memorise|memoriser|rappelle\s+toi|garde\s+en\s+tete)")


def _mots_utiles(texte: str) -> set:
    jetons = text_utils.tokenize(text_utils.normalize(texte or ""))
    return {mot for mot in jetons if mot and mot not in MOTS_VIDES and len(mot) > 1}


def _sans_conjonction(fait: str) -> str:
    """
    Retire le « que » qui introduit le fait.

    Le motif le rend facultatif -- « retiens : j aime le the » se dit aussi --
    et le mot se retrouve alors dans ce qu on croit etre le fait.
    """
    fait = (fait or "").strip(" .:")
    for conjonction in ("que ", "qu ", "qu'"):
        if fait.lower().startswith(conjonction):
            return fait[len(conjonction):].strip(" .:")
    return "" if fait.lower() in ("que", "qu") else fait


def _pertinence(souvenir: dict, mots: set) -> int:
    """Combien de mots du sujet demande figurent dans ce souvenir ?"""
    return len(mots & _mots_utiles(str(souvenir.get("text", ""))))


@command(
    name="memoire_retenir",
    patterns=[
        r"^" + VERBES_RETENIR + r"\s+(?:bien\s+)?(?:que\s+|:\s*)?(?P<fait>.+)$",
    ],
    keywords=[["retiens"], ["souviens", "toi"], ["memorise"]],
    category="Productivité",
    description="Retenir un fait durablement",
    examples=["retiens que je suis allergique aux arachides",
              "souviens-toi que ma sœur s'appelle Yasmine"],
    priority=92,
)
def memoire_retenir(ctx: CommandContext) -> Response:
    """Enregistre un fait que l'assistant devra retrouver plus tard."""
    fait = _sans_conjonction(ctx.group("fait"))
    if not fait or len(_mots_utiles(fait)) == 0:
        return Response.error("Que dois-je retenir ?")

    connus = ctx.storage.souvenirs.load()
    normalise = text_utils.normalize(fait).strip()
    for souvenir in connus:
        if text_utils.normalize(str(souvenir.get("text", ""))).strip() == normalise:
            return Response(text="Je le savais déjà.", speak=False)

    ctx.storage.souvenirs.append({"text": fait, "source": ctx.source})
    return Response(text="C'est retenu : " + fait, speak=False)


@command(
    name="memoire_rappeler",
    patterns=[
        r"^(?:qu\s+est\s+ce\s+que\s+tu\s+sais|que\s+sais\s+tu|qu\s+as\s+tu\s+retenu)"
        r"(?:\s+(?:sur|de|a\s+propos\s+de|concernant))?\s*(?P<sujet>.*)$",
        r"^(?:de\s+quoi\s+)?te\s+souviens\s+tu(?:\s+(?:sur|de))?\s*(?P<sujet>.*)$",
        r"^(?:mes\s+)?souvenirs$",
    ],
    keywords=[["que", "sais", "tu"], ["souviens", "tu"]],
    category="Productivité",
    description="Dire ce qui a été retenu",
    examples=["qu'est-ce que tu sais sur moi", "de quoi te souviens-tu"],
    priority=93,
    informatif=True,
)
def memoire_rappeler(ctx: CommandContext) -> Response:
    """Restitue ce qui a été retenu, sur un sujet ou en entier."""
    souvenirs = ctx.storage.souvenirs.load()
    if not souvenirs:
        return Response(text="Je ne retiens rien pour l'instant.")

    sujet = (ctx.group("sujet") or "").strip(" .?")
    mots = _mots_utiles(sujet)
    if mots:
        classes = [(s, _pertinence(s, mots)) for s in souvenirs]
        retenus = [s for s, score in sorted(classes, key=lambda c: -c[1]) if score]
        if not retenus:
            return Response(text="Je ne retiens rien sur « " + sujet + " ».")
        entete = "Sur « " + sujet + " » : "
    else:
        retenus = souvenirs
        entete = "Je retiens : "

    if len(retenus) > 5:
        entete = entete + str(len(retenus)) + " choses, dont "
        retenus = retenus[:5]
    return Response(text=entete + " ; ".join(str(s.get("text", "")) for s in retenus) + ".")


@command(
    name="memoire_oublier",
    patterns=[
        r"^(?:oublie|oublier|efface|effacer|supprime)\s+(?:que\s+|le\s+souvenir\s+)?"
        r"(?P<sujet>.+)$",
    ],
    keywords=[["oublie"], ["efface", "souvenir"]],
    category="Productivité",
    description="Oublier ce qui a été retenu sur un sujet",
    examples=["oublie que je suis allergique aux arachides"],
    priority=92,
)
def memoire_oublier(ctx: CommandContext) -> Response:
    """Retire les souvenirs qui parlent du sujet donné."""
    sujet = (ctx.group("sujet") or "").strip(" .")
    souvenirs = ctx.storage.souvenirs.load()
    if not souvenirs:
        return Response(text="Je ne retiens rien.", speak=False)

    if text_utils.normalize(sujet).strip() in ("tout", "tous mes souvenirs", "mes souvenirs"):
        ctx.storage.souvenirs.clear()
        return Response(text="J'ai tout oublié.", speak=False)

    mots = _mots_utiles(sujet)
    if not mots:
        return Response.error("Qu'est-ce que je dois oublier ?")
    # On n efface que ce qui parle VRAIMENT du sujet. « ma soeur s appelle
    # Yasmine » et « mon frere s appelle Karim » partagent « appelle » : un
    # seul mot en commun ferait disparaitre le second avec le premier. On
    # exige donc la majorite des mots du sujet.
    seuil = max(1, round(len(mots) * 0.6 + 0.5))
    gardes = [s for s in souvenirs if _pertinence(s, mots) < seuil]
    efface = len(souvenirs) - len(gardes)
    if not efface:
        return Response(text="Je ne retiens rien sur « " + sujet + " ».", speak=False)
    ctx.storage.souvenirs.save(gardes)
    return Response(
        text="Oublié" + ("" if efface == 1 else " (" + str(efface) + " souvenirs)") + ".",
        speak=False,
    )
