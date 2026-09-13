"""
Utilitaires de normalisation de texte.

Point clef : la normalisation est *alignee caractere par caractere* avec la
chaine d'origine (meme longueur). Cela permet au routeur de faire du matching
sur une version simplifiee (minuscules, sans accents, sans ponctuation) tout en
extrayant les arguments (requete de recherche, texte d'une note, ...) depuis la
chaine ORIGINALE, avec ses accents et sa casse intactes.
"""

from __future__ import annotations

import difflib
import re
from typing import Iterable, Sequence

# Table de repliement des accents. Chaque entree DOIT faire un seul caractere
# en sortie pour preserver l'alignement des index.
_ACCENT_MAP = str.maketrans(
    {
        "à": "a", "á": "a", "â": "a", "ã": "a", "ä": "a", "å": "a", "æ": "a",
        "ç": "c",
        "è": "e", "é": "e", "ê": "e", "ë": "e",
        "ì": "i", "í": "i", "î": "i", "ï": "i",
        "ñ": "n",
        "ò": "o", "ó": "o", "ô": "o", "õ": "o", "ö": "o", "ø": "o", "œ": "o",
        "ù": "u", "ú": "u", "û": "u", "ü": "u",
        "ý": "y", "ÿ": "y",
        "ß": "s",
        "’": "'", "‘": "'", "“": '"', "”": '"',
    }
)

# Caracteres de ponctuation conservés tels quels car porteurs de sens.
_KEEP = set("%:")

# Mots d appel ignores en debut de phrase ("Alma, ouvre Chrome").
# Valeur de repli uniquement : en fonctionnement, la liste est construite a
# partir de general.wake_word et general.wake_prefixes (voir config.py).
DEFAULT_WAKE_WORDS = ("alma", "ok alma", "hey alma", "dis alma")


def _lower_char(char: str) -> str:
    """Minuscule sur un caractere en garantissant la longueur 1."""
    lowered = char.lower()
    return lowered if len(lowered) == 1 else char


def normalize(text: str) -> str:
    """
    Retourne une version simplifiee de `text` de MEME LONGUEUR :
    minuscules, accents replies, ponctuation ET espaces exotiques remplaces
    par des espaces ordinaires.

    La longueur est preservee caractere par caractere : c est ce qui permet
    de reperer un argument dans la chaine normalisee puis de le decouper
    dans la chaine d origine, accents et majuscules intacts.
    """
    out = []
    for char in text:
        char = _lower_char(char)
        char = char.translate(_ACCENT_MAP)
        if len(char) != 1:  # securite : ne jamais casser l'alignement
            char = " "
        if char.isspace():
            # Espace insecable, espace fine... Les sites en mettent partout
            # (« Classe 16+ », « Sortie : 2024 ») : sans ce repli, les mots
            # ne se separent pas et aucune comparaison ne tombe juste.
            out.append(" ")
        elif char.isalnum() or char in _KEEP:
            out.append(char)
        else:
            out.append(" ")
    return "".join(out)


def strip_wake_word(raw: str, norm: str, wake_words: Sequence[str] = DEFAULT_WAKE_WORDS) -> tuple[str, str]:
    """
    Retire un eventuel mot d'appel en tete de phrase, en coupant raw et norm
    au meme endroit pour preserver l'alignement.
    """
    stripped = norm.lstrip()
    offset = len(norm) - len(stripped)
    for wake in sorted(wake_words, key=len, reverse=True):
        wake_norm = normalize(wake).strip()
        if not wake_norm:
            continue
        if stripped == wake_norm:
            return "", ""
        if stripped.startswith(wake_norm) and (
            len(stripped) == len(wake_norm) or not stripped[len(wake_norm)].isalnum()
        ):
            cut = offset + len(wake_norm)
            # On avale aussi les separateurs qui suivent (virgule -> espace).
            while cut < len(norm) and not norm[cut].isalnum():
                cut += 1
            return raw[cut:], norm[cut:]
    return raw, norm


def tokenize(norm: str) -> list[str]:
    """Decoupe une chaine normalisee en mots."""
    return [token for token in re.split(r"\s+", norm) if token]


# Mots qui n existent QUE dans une langue -- jamais les mots partages
# ("second", "music" a une orthographe propre mais "musique" aussi, donc
# absent ; "sur"/"on" sont ambigus dans les deux langues, donc absents
# aussi). Le but n est pas la linguistique : juste de departager une phrase
# COURTE, du genre de celles qu on dicte a Alma.
_MARQUEURS_FRANCAIS = frozenset((
    "le", "la", "les", "un", "une", "des", "du", "de", "au", "aux",
    "est", "suis", "es", "sommes", "etes", "sont", "tu", "vous", "nous",
    "moi", "toi", "lui", "leur", "notre", "votre", "mon", "ma", "mes",
    "ton", "ta", "tes", "son", "sa", "ses", "que", "qui", "quoi",
    "comment", "pourquoi", "combien", "quel", "quelle", "quels", "quelles",
    "avec", "dans", "sans", "vers", "chez", "tres", "ou", "et", "ca",
    "ouvre", "ouvrir", "ferme", "fermer", "fais", "faire", "donne",
    "veux", "voudrais", "peux", "peut", "stp", "merci", "bonjour",
    "salut", "coucou", "bonsoir", "aujourd", "hui", "demain",
    "maintenant", "beaucoup", "encore", "toujours", "jamais", "voila",
    "voici", "cette", "cet", "ces", "etre", "avoir",
))
_MARQUEURS_ANGLAIS = frozenset((
    # Mots-outils
    "the", "is", "are", "am", "was", "were", "what", "who", "how", "why",
    "when", "where", "which", "please", "thanks", "thank", "hello", "hi",
    "hey", "yes", "my", "your", "his", "her", "our", "their", "this",
    "that", "these", "those", "and", "but", "with", "for", "of", "at",
    "today", "tomorrow", "now", "very", "also", "still", "never",
    "always", "maybe", "does", "do", "did", "can", "could", "would",
    "should", "want", "about", "from", "into", "some", "any", "all",
    # Verbes d action : ce sont eux qui portent une commande courte, et
    # aucun n est un mot francais (« minimize » s ecrit « minimise » ici).
    "open", "close", "tell", "give", "show", "make", "take", "put",
    "turn", "set", "find", "search", "read", "write", "play", "start",
    "stop", "run", "ask", "remind", "copy", "paste", "cut", "save",
    "print", "select", "delete", "clear", "empty", "lock", "sleep",
    "restart", "reboot", "shut", "scroll", "click", "switch", "forget",
    "remember", "maximize", "minimize", "resume", "skip", "mute",
    "unmute", "refresh", "reload", "flip", "roll", "calculate",
    # Noms et qualificatifs frequents dans une commande, sans equivalent
    # orthographique francais (« volume », « timer », « note » sont partages,
    # donc absents).
    "next", "previous", "last", "new", "song", "tab", "window", "screen",
    "monitor", "louder", "quieter", "brightness", "battery", "disk",
    "folder", "file", "clipboard", "desktop", "everything", "history",
    # Petits mots de direction et de lieu, tous absents du francais.
    "go", "home", "up", "down", "back", "out", "off", "to", "it",
    "here", "there", "left", "right",
    # Ce qu on demande a lister, regler ou lancer. Meme regle que plus haut :
    # rien de partage avec le francais (« liste », « musique », « annule »
    # s ecrivent autrement ; « notes », « timer », « volume » sont exclus).
    "list", "websites", "reminders", "timers", "music", "playing", "movie",
    "picture", "browser", "computer", "help", "again", "everywhere",
    "translate", "cancel", "add", "create", "press", "wait", "lower",
    "raise", "increase", "decrease", "quit", "loud", "mouse", "keyboard",
    "weather", "time", "temperature", "bye", "goodbye", "name",
    "pictures", "pics", "anything", "nothing", "something",
    "call", "yourself", "faster", "slower", "sensitive", "preferences",
    "settings", "reset", "default", "awake", "loud",
))

# Langue supposee quand la phrase ne porte AUCUN indice : « call me Sarah »
# n a pas un mot exclusif a l anglais, et « screenshot » pas davantage au
# francais. C est alors la langue choisie a l installation qui tranche --
# sans quoi un utilisateur anglophone se ferait repondre en francais une
# phrase sur trois. L assistant la regle au demarrage et a chaque
# changement (voir Assistant._appliquer).
LANGUE_PAR_DEFAUT = "fr"


def definir_langue_par_defaut(langue: str) -> None:
    """Fixe la langue de repli. Tout sauf « en » vaut francais."""
    global LANGUE_PAR_DEFAUT
    LANGUE_PAR_DEFAUT = "en" if str(langue or "")[:2] == "en" else "fr"


def detect_language(norm: str) -> str:
    """
    « fr » ou « en », devine a partir de mots qui n existent que dans une
    langue. Sur une egalite ou une phrase sans mot reconnu (« screenshot »,
    un nom propre...), on retombe sur LANGUE_PAR_DEFAUT -- la langue choisie
    a l installation, le francais tant que rien n a ete choisi.
    """
    tokens = set(tokenize(norm))
    score_fr = len(tokens & _MARQUEURS_FRANCAIS)
    score_en = len(tokens & _MARQUEURS_ANGLAIS)
    if score_en != score_fr:
        return "en" if score_en > score_fr else "fr"
    return LANGUE_PAR_DEFAUT


def similarity(a: str, b: str) -> float:
    """Similarite 0..1 entre deux mots (tolerance aux fautes de frappe)."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def fuzzy_in(word: str, tokens: Iterable[str], threshold: float = 0.82) -> bool:
    """
    True si `word` est present (exactement ou approximativement) dans `tokens`.
    Gere aussi les mots composes ("presse papiers") en les comparant a la
    concatenation des tokens voisins.
    """
    word = word.strip()
    if not word:
        return False
    token_list = list(tokens)
    if " " in word:
        parts = word.split()
        needed = len(parts)
        for i in range(len(token_list) - needed + 1):
            window = token_list[i : i + needed]
            if all(fuzzy_in(p, [w], threshold) for p, w in zip(parts, window)):
                return True
        return False
    for token in token_list:
        if token == word:
            return True
        # Les mots courts ne tolerent pas d'approximation (trop de collisions).
        if len(word) >= 4 and similarity(token, word) >= threshold:
            return True
    return False


def best_match(query: str, candidates: Iterable[str], threshold: float = 0.75) -> str | None:
    """
    Retourne le candidat le plus proche de `query`, ou None si aucun ne depasse
    le seuil. Utilise pour resoudre "ouvre gogle chrome" -> "chrome".
    """
    query = normalize(query).strip()
    best: str | None = None
    best_score = threshold
    for candidate in candidates:
        cand_norm = normalize(candidate).strip()
        if not cand_norm:
            continue
        if cand_norm == query:
            return candidate
        score = similarity(query, cand_norm)
        # Bonus si l'un contient l'autre ("chrome" dans "google chrome").
        if cand_norm in query or query in cand_norm:
            score = max(score, 0.9)
        if score > best_score:
            best_score = score
            best = candidate
    return best


# --------------------------------------------------------------------------
# Balisage Markdown
# --------------------------------------------------------------------------
_CLOTURE_CODE = re.compile(r"^\s*```.*$", re.MULTILINE)
_TITRE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_PUCE = re.compile(r"^\s{0,6}[-*+]\s+", re.MULTILINE)
_GRAS = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIQUE = re.compile(r"(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)")
_CODE = re.compile(r"`([^`\n]+)`")
_LIEN = re.compile(r"\[([^\]\n]+)\]\([^)\s]+\)")


def sans_balisage(texte: str) -> str:
    """
    Le texte débarrassé du balisage Markdown, pour être lu à voix haute.

    « **1 seul fichier** » se lirait « astérisque astérisque 1 seul fichier ».
    On ne retire que ce qui est sans ambiguïté : gras, italique, code, titres,
    puces et libellés de liens. Les soulignés sont laissés tels quels — ils
    apparaissent dans les noms de fichiers bien plus souvent qu'en italique.
    """
    texte = _CLOTURE_CODE.sub("", texte or "")
    texte = _LIEN.sub(r"\1", texte)
    texte = _GRAS.sub(r"\1", texte)
    texte = _ITALIQUE.sub(r"\1", texte)
    texte = _CODE.sub(r"\1", texte)
    texte = _TITRE.sub("", texte)
    texte = _PUCE.sub("", texte)
    return texte.strip()
