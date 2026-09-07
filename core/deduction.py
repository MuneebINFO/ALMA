"""
Deduction : retrouver l intention quand la transcription a mal entendu.

La reconnaissance vocale bute surtout sur les mots courts et les mots anglais
glisses dans une phrase francaise. « Scroll » revient regulierement en
« Paul ». Plutot que d abandonner, on essaie trois choses, de la plus sure a
la plus audacieuse :

  1. CORRECTIONS : remplacer un mot par une confusion connue ;
  2. PHONETIQUE : rapprocher un mot inconnu d un mot du vocabulaire des
     commandes, par la sonorite plutot que par l orthographe ;
  3. INDICES : reconstruire l intention a partir du RESTE de la phrase.
     « ... vers le bas » indique un defilement, meme si le verbe est perdu.

Regle d or : une deduction n est retenue QUE si la phrase reconstruite
correspond effectivement a une commande connue. On ne devine jamais dans le
vide, et une phrase deja comprehensible n est jamais modifiee.

Ce module n est sollicite que lorsque plus rien ne correspond, et donc --
en mode vocal -- apres que le mot d appel a ete prononce : l utilisateur
voulait bien quelque chose.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core import text_utils

# --------------------------------------------------------------------------
# Cle phonetique approximative pour le francais
# --------------------------------------------------------------------------
_SUBSTITUTIONS = (
    ("eau", "o"), ("aux", "o"), ("au", "o"), ("ou", "u"), ("oi", "wa"),
    ("ai", "e"), ("ei", "e"), ("eu", "e"), ("ph", "f"), ("qu", "k"),
    ("ch", "x"), ("gn", "n"), ("th", "t"), ("sc", "sk"), ("ck", "k"),
    ("ce", "se"), ("ci", "si"), ("cy", "si"), ("ge", "je"), ("gi", "ji"),
    ("c", "k"), ("q", "k"), ("y", "i"), ("h", ""), ("w", "v"), ("z", "s"),
)
_FINALES_MUETTES = ("es", "e", "s", "t", "d", "x", "p", "z")


def cle_phonetique(mot: str) -> str:
    """
    Reduit un mot a une approximation de sa sonorite.

    Volontairement grossier : le but n est pas de transcrire fidelement mais
    de rapprocher « scrol », « scrolle » et « skroll ».
    """
    mot = text_utils.normalize(mot).strip()
    if not mot:
        return ""
    for avant, apres in _SUBSTITUTIONS:
        mot = mot.replace(avant, apres)
    # Finales muettes du francais.
    for finale in _FINALES_MUETTES:
        if len(mot) > 3 and mot.endswith(finale):
            mot = mot[: -len(finale)]
            break
    # Lettres doublees.
    resultat = []
    for lettre in mot:
        if not resultat or resultat[-1] != lettre:
            resultat.append(lettre)
    return "".join(resultat)


def se_ressemblent(a: str, b: str, seuil: float = 0.8) -> bool:
    """Deux mots sonnent-ils pareil ?"""
    cle_a, cle_b = cle_phonetique(a), cle_phonetique(b)
    if not cle_a or not cle_b:
        return False
    if cle_a == cle_b:
        return True
    return text_utils.similarity(cle_a, cle_b) >= seuil


# --------------------------------------------------------------------------
# Nombres : « ecran 2 » revient souvent en « ecran de »
# --------------------------------------------------------------------------
NOMBRES_MOTS = {
    "un": 1, "une": 1, "premier": 1, "premiere": 1,
    "deux": 2, "second": 2, "seconde": 2, "deuxieme": 2,
    "trois": 3, "troisieme": 3,
    "quatre": 4, "quatrieme": 4,
    "cinq": 5, "cinquieme": 5,
    "six": 6, "sixieme": 6,
    "sept": 7, "septieme": 7,
    "huit": 8, "huitieme": 8,
    "neuf": 9, "neuvieme": 9,
}

# Transcriptions fautives constatees. Certaines de ces formes sont des mots
# courants (« si », « cette ») : cette table ne s applique qu au mot voisin
# d un nombre attendu, jamais a une phrase entiere.
NOMBRES_ENTENDUS = {
    "d": 2, "de": 2, "du": 2, "des": 2, "dos": 2, "deu": 2, "oeufs": 2,
    "toi": 3, "troie": 3, "trop": 3,
    "cat": 4, "quatr": 4, "car": 4,
    "sain": 5, "sein": 5, "saint": 5, "cinque": 5,
    "si": 6, "sis": 6, "scie": 6,
    "cette": 7, "cet": 7, "set": 7,
    "wit": 8, "uit": 8, "huite": 8,
    "neu": 9, "oeuf": 9,
}


def nombre_entendu(mot: str, maximum: int = 9):
    """
    Le nombre qu un mot designe, meme mal transcrit. None si ce n en est pas un.

    A n utiliser que la ou un nombre est attendu -- typiquement le mot voisin
    de « ecran ». « va sur l ecran 2 » est regulierement transcrit « va sur
    ecran de » : sans cette lecture, l assistant demande quel ecran alors que
    l utilisateur vient de le dire.
    """
    mot = text_utils.normalize(mot or "").strip().lower()
    if not mot:
        return None
    if mot.isdigit():
        valeur = int(mot)
        return valeur if 1 <= valeur <= maximum else None
    for table in (NOMBRES_MOTS, NOMBRES_ENTENDUS):
        valeur = table.get(mot)
        if valeur is not None and valeur <= maximum:
            return valeur
    # Dernier recours : la sonorite. « toi » pour « trois », « cat » pour
    # « quatre ».
    for texte, valeur in NOMBRES_MOTS.items():
        if valeur <= maximum and se_ressemblent(mot, texte):
            return valeur
    return None


# --------------------------------------------------------------------------
# 1. Confusions connues
# --------------------------------------------------------------------------
# Chaque correction est VERIFIEE avant d etre retenue : elle ne s applique
# que si la phrase corrigee designe une commande. « Cherche Paul sur
# YouTube » reste donc intact.
CORRECTIONS = {
    "scroll": ("paul", "pol", "poll", "roll", "rol", "school", "crawl",
               "scrawl", "srol", "strol", "escrol", "escroll", "sol"),
    "pause": ("pose", "poz", "peau", "pauses", "poses"),
    "clique": ("clic", "click", "clik", "klik", "cliques"),
    "volume": ("volumes", "volum"),
    "ecran": ("ecrans", "ecrin", "ecrit"),
    "capture": ("capturer", "captures", "kapture"),
    "luminosite": ("lumiere", "luminosites", "luminosite"),
    "suivant": ("suivante", "suivan"),
    "precedent": ("precedente", "precedant"),
    "musique": ("music", "musik"),
    "video": ("videos", "vidéo"),
    "onglet": ("onglets", "onglais", "anglet"),
    "meteo": ("meteos", "metheo"),
    "heure": ("heures", "eure"),
}

# Vocabulaire des commandes, pour le rapprochement phonetique.
VOCABULAIRE = tuple(CORRECTIONS) + (
    "ouvre", "ferme", "lance", "monte", "baisse", "coupe", "mets", "cherche",
    "note", "rappelle", "minuteur", "blague", "aide", "bonjour", "merci",
    "defile", "descends", "remonte", "verrouille", "eteins", "redemarre",
    "traduis", "wikipedia", "google", "youtube", "netflix", "spotify",
)


# --------------------------------------------------------------------------
# 3. Reconstruction a partir d indices
# --------------------------------------------------------------------------
@dataclass
class Regle:
    """
    Reconstruit une intention a partir de fragments de la phrase.

    `indices` : au moins un doit etre present.
    `interdits` : aucun ne doit l etre -- « vers le bas » evoque un
    defilement, sauf si l on parle de volume ou de luminosite.
    """

    indices: tuple
    commande: str
    interdits: tuple = field(default_factory=tuple)

    def correspond(self, texte_norme: str) -> bool:
        if any(mot in texte_norme for mot in self.interdits):
            return False
        return any(indice in texte_norme for indice in self.indices)


SON = ("volume", "son", "musique", "fort")
AFFICHAGE = ("luminosite", "lumiere", "ecran")

REGLES = (
    # Defilement : c est l exemple type. Meme si le verbe est perdu,
    # « vers le bas » ne laisse guere de doute.
    Regle(("vers le bas", "en bas", "plus bas", "descendre", "vers en bas"),
          "scrolle vers le bas", interdits=SON + AFFICHAGE),
    Regle(("vers le haut", "en haut", "plus haut", "remonter"),
          "scrolle vers le haut", interdits=SON + AFFICHAGE),
    Regle(("defiler", "defile", "scroller", "faire defiler"), "scrolle"),

    # Son
    Regle(("plus fort", "augmente le son", "monter le son"), "monte le son"),
    Regle(("moins fort", "baisser le son", "trop fort"), "baisse le son"),
    Regle(("silence", "plus de son", "coupe tout"), "coupe le son"),

    # Lecture
    Regle(("en pause", "pause"), "pause", interdits=("ecran",)),
    Regle(("reprendre", "reprend", "continuer la lecture"), "reprends"),
    Regle(("chanson d apres", "morceau d apres", "titre suivant"), "chanson suivante"),

    # Informations
    Regle(("quelle heure", "l heure qu il est", "il est quelle"), "quelle heure est-il"),
    Regle(("le temps qu il fait", "temperature", "meteo"), "quel temps fait-il"),
    Regle(("quel jour", "la date"), "quelle est la date"),

    # Systeme
    Regle(("capture", "screenshot", "photo de l ecran"), "prends une capture d'écran"),
    Regle(("verrouiller", "verrouille"), "verrouille l'ordinateur"),

    # Divers
    Regle(("une blague", "fais moi rire", "raconte moi quelque chose"),
          "raconte-moi une blague"),
    Regle(("mes notes", "lire les notes"), "lis mes notes"),
)


# --------------------------------------------------------------------------
# Moteur de deduction
# --------------------------------------------------------------------------
def _variantes_corrigees(texte: str) -> list:
    """Reecritures possibles de la phrase, par correction mot a mot."""
    tokens = texte.split()
    if not tokens:
        return []
    inverse = {}
    for correct, confusions in CORRECTIONS.items():
        for confusion in confusions:
            inverse[confusion] = correct

    variantes = []

    # a) Confusions connues.
    corriges = []
    change = False
    for token in tokens:
        cle = text_utils.normalize(token).strip(" .,!?;:")
        remplacement = inverse.get(cle)
        if remplacement:
            corriges.append(remplacement)
            change = True
        else:
            corriges.append(token)
    if change:
        variantes.append(" ".join(corriges))

    # b) Rapprochement phonetique avec le vocabulaire des commandes.
    phonetiques = []
    change = False
    for token in tokens:
        cle = text_utils.normalize(token).strip(" .,!?;:")
        if len(cle) < 3:
            phonetiques.append(token)
            continue
        proche = next((mot for mot in VOCABULAIRE if mot != cle and se_ressemblent(cle, mot)), None)
        if proche:
            phonetiques.append(proche)
            change = True
        else:
            phonetiques.append(token)
    if change:
        variantes.append(" ".join(phonetiques))

    return variantes


def deduire(texte: str, resout) -> str | None:
    """
    Tente de retrouver l intention d une phrase incomprise.

    `resout(phrase) -> bool` indique si une phrase correspond a une commande.
    Rien n est renvoye tant qu une reconstruction n a pas ete validee ainsi :
    on ne devine jamais dans le vide.
    """
    texte = (texte or "").strip()
    if not texte:
        return None
    # Une phrase deja comprehensible n est JAMAIS reecrite : sans ce garde-fou,
    # « cherche Paul sur YouTube » deviendrait « cherche scroll sur YouTube ».
    if resout(texte):
        return None

    for variante in _variantes_corrigees(texte):
        if variante != texte and resout(variante):
            return variante

    norme = " ".join(text_utils.tokenize(text_utils.normalize(texte)))
    for regle in REGLES:
        if regle.correspond(norme) and resout(regle.commande):
            return regle.commande
    return None
