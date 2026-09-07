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
