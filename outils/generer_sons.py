"""
Fabrique les bruitages d'ALMA, dans assets/sons/.

    .venv\\Scripts\\python.exe outils/generer_sons.py

Pourquoi les GENERER plutot qu'embarquer des fichiers : on sait exactement
d'où ils viennent — aucune licence à vérifier, rien à créditer, et surtout
rien qui appartienne à quelqu'un d'autre. Les assistants connus ont des
signatures sonores déposées ; on ne les copie pas, on travaille dans la
même FAMILLE, celle qui les rend agréables.

Ce qui la caractérise, et qu'un simple bip n'a pas :

  - un timbre de CLOCHE, pas de sinusoïde. Une note réelle porte des
    partiels légèrement désaccordés (2,01 et non 2,00), et les aigus
    s'éteignent plus vite que les graves. C'est cette extinction inégale
    que l'oreille lit comme « un objet a été frappé » plutôt que
    « un circuit a émis un signal » ;
  - une DECROISSANCE EXPONENTIELLE longue, qui laisse une queue. Un son
    coupé net sonne électronique, même avec un joli timbre ;
  - une attaque douce de quelques millisecondes : assez pour éviter le
    clic, assez peu pour rester net ;
  - des intervalles qui se RESOLVENT. Une quarte juste qui monte ouvre,
    la même qui descend referme. C'est pour cela que les deux paires sont
    l'exact miroir l'une de l'autre.

Le vocabulaire tient en quatre signes, volontairement : un assistant qui
tinte à chaque geste devient fatigant en une demi-journée.

  reveil   deux notes qui MONTENT     — je vous écoute
  veille   les mêmes qui DESCENDENT   — je me retire
  ok       une note seule             — c'est fait (là où rien n'est dit)
  erreur   deux notes basses          — ça n'a pas marché
"""

from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "assets" / "sons"

TAUX = 44100           # une queue de cloche mérite mieux que 22 kHz
AMPLITUDE = 0.30       # un bruitage se remarque, il ne couvre pas

# Le timbre : (rapport de fréquence, poids, rapidité d'extinction).
#
# Les rapports sont volontairement FAUX de quelques millièmes. Exactement
# harmoniques, les partiels fusionnent en une seule note synthétique ; un
# léger écart les fait battre entre eux, et c'est ce battement qui donne
# l'impression de matière.
#
# Le troisième nombre multiplie la vitesse d'extinction : plus il est grand,
# plus le partiel s'éteint vite. Les aigus partent les premiers, comme sur
# n'importe quel objet frappé.
CLOCHE = (
    (1.000, 1.00, 1.0),
    (2.010, 0.40, 1.9),
    (3.012, 0.20, 3.2),
    (4.170, 0.09, 5.0),
    (5.430, 0.04, 7.0),
)

ATTAQUE = 0.006        # 6 ms : pas de clic, pas de mollesse non plus

# Chaque son : une suite de (fréquence, retard avant le départ, durée totale).
# Les notes se CHEVAUCHENT — la queue de la première vit encore quand la
# seconde arrive. Jouées bout à bout, elles sonneraient comme deux bips.
#
# Gamme : ré5 (587) et sol5 (784), une quarte juste. Elle monte pour ouvrir,
# descend pour refermer.
SONS = {
    "reveil": (
        (587.33, 0.000, 0.55),
        (783.99, 0.085, 0.75),
    ),
    "veille": (
        (783.99, 0.000, 0.50),
        (587.33, 0.090, 0.85),
    ),
    # Une seule note, plus haute et plus brève : elle ponctue, elle n'annonce
    # rien. C'est celle qu'on entendra le plus souvent.
    "ok": (
        (880.00, 0.000, 0.42),
    ),
    # Plus grave et plus lente : sans être désagréable, elle ne doit pas
    # pouvoir se confondre avec une réussite.
    "erreur": (
        (392.00, 0.000, 0.50),
        (329.63, 0.100, 0.80),
    ),
}


def _note(frequence: float, duree: float) -> list:
    """
    Une note de cloche : partiels désaccordés, extinction exponentielle.

    Rend une liste de flottants entre -1 et 1, pas encore mise à l'échelle.
    """
    total = int(TAUX * duree)
    attaque = max(1, int(TAUX * ATTAQUE))
    # La constante de temps : au bout de `duree`, il ne doit plus rester
    # qu'un souffle. 4,5 constantes donnent une queue qui s'efface sans
    # jamais paraître coupée.
    tau = duree / 4.5

    poids_total = sum(poids for _, poids, _ in CLOCHE)
    echantillons = []
    for i in range(total):
        t = i / TAUX
        valeur = 0.0
        for rapport, poids, vitesse in CLOCHE:
            valeur += poids * math.exp(-t / (tau / vitesse)) * math.sin(
                math.tau * frequence * rapport * t)
        valeur /= poids_total
        if i < attaque:
            valeur *= i / attaque
        echantillons.append(valeur)
    return echantillons


def _melanger(notes) -> list:
    """
    Superpose les notes à leur instant de départ.

    Le chevauchement est l'essentiel : c'est ce qui fait entendre un accord
    qui se déplace plutôt que deux signaux successifs.
    """
    pistes = []
    longueur = 0
    for frequence, retard, duree in notes:
        depart = int(TAUX * retard)
        piste = _note(frequence, duree)
        pistes.append((depart, piste))
        longueur = max(longueur, depart + len(piste))

    melange = [0.0] * longueur
    for depart, piste in pistes:
        for i, valeur in enumerate(piste):
            melange[depart + i] += valeur
    return melange


def ecrire(nom: str, notes) -> Path:
    """Écrit un .wav mono 16 bits, et rend son chemin."""
    melange = _melanger(notes)
    # On normalise sur le pic réel : deux notes superposées peuvent dépasser
    # 1,0, et la saturation s'entend immédiatement comme un grésillement.
    pic = max((abs(v) for v in melange), default=1.0) or 1.0
    facteur = AMPLITUDE / pic

    donnees = [int(max(-1.0, min(1.0, v * facteur)) * 32767) for v in melange]
    chemin = DOSSIER / (nom + ".wav")
    with wave.open(str(chemin), "wb") as fichier:
        fichier.setnchannels(1)
        fichier.setsampwidth(2)
        fichier.setframerate(TAUX)
        fichier.writeframes(struct.pack("<%dh" % len(donnees), *donnees))
    return chemin


def main() -> int:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    for nom, notes in SONS.items():
        chemin = ecrire(nom, notes)
        duree = max(retard + duree for _, retard, duree in notes)
        print("%-8s %4.0f ms  %6d octets  %s"
              % (nom, duree * 1000, chemin.stat().st_size, chemin.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
