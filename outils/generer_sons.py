"""
Fabrique les bruitages d'ALMA, dans assets/sons/.

    .venv\\Scripts\\python.exe outils/generer_sons.py

Pourquoi les GENERER plutot qu'embarquer des fichiers : on sait exactement
d'où ils viennent — aucune licence à vérifier, rien à créditer —, ils pèsent
quelques kilo-octets, et les retoucher revient à changer deux nombres ici.

Le vocabulaire sonore tient en quatre signes, et il est volontairement
pauvre : un assistant qui tinte à chaque geste devient fatigant en une
demi-journée.

  reveil   deux notes qui MONTENT  — je vous écoute
  veille   deux notes qui DESCENDENT — je me retire
  ok       une note brève et claire — c'est fait (là où rien n'est dit)
  erreur   deux notes basses        — ça n'a pas marché

Chacun dure moins de 300 ms. Une enveloppe douce à l'attaque et à
l'extinction évite le « clic » qu'un signal coupé net produit toujours.
"""

from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "assets" / "sons"

TAUX = 22050           # suffisant pour quelques sinusoïdes, et deux fois plus léger
AMPLITUDE = 0.34       # un bruitage se remarque, il ne couvre pas

# Chaque son : une suite de (fréquence en Hz, durée en secondes).
# Les fréquences suivent une gamme pentatonique — n'importe quelle paire y
# sonne juste, ce qui évite l'effet « alarme » des intervalles arbitraires.
SONS = {
    "reveil": ((587.33, 0.075), (880.00, 0.130)),      # ré → la, ça ouvre
    "veille": ((880.00, 0.075), (587.33, 0.150)),      # la → ré, ça referme
    "ok": ((987.77, 0.090),),                          # si, une seule note
    "erreur": ((392.00, 0.090), (293.66, 0.170)),      # sol → ré grave
}


def _enveloppe(i: int, total: int) -> float:
    """
    Monte vite, tient, s'éteint doucement.

    Sans elle, la sinusoïde coupée net claque : l'oreille entend le bord,
    pas la note.
    """
    attaque = max(1, int(total * 0.06))
    chute = max(1, int(total * 0.55))
    if i < attaque:
        return i / attaque
    if i > total - chute:
        return max(0.0, (total - i) / chute)
    return 1.0


def _note(frequence: float, duree: float) -> list:
    """Une sinusoïde enveloppée, en échantillons 16 bits signés."""
    total = int(TAUX * duree)
    echantillons = []
    for i in range(total):
        valeur = math.sin(math.tau * frequence * i / TAUX)
        # Une pointe d'harmonique : une sinusoïde pure sonne « bip de four ».
        valeur += 0.22 * math.sin(math.tau * frequence * 2 * i / TAUX)
        valeur *= AMPLITUDE * _enveloppe(i, total) / 1.22
        echantillons.append(int(max(-1.0, min(1.0, valeur)) * 32767))
    return echantillons


def ecrire(nom: str, notes) -> Path:
    """Écrit un .wav mono 16 bits, et rend son chemin."""
    echantillons: list = []
    for frequence, duree in notes:
        echantillons.extend(_note(frequence, duree))
    chemin = DOSSIER / (nom + ".wav")
    with wave.open(str(chemin), "wb") as fichier:
        fichier.setnchannels(1)
        fichier.setsampwidth(2)
        fichier.setframerate(TAUX)
        fichier.writeframes(struct.pack("<%dh" % len(echantillons), *echantillons))
    return chemin


def main() -> int:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    for nom, notes in SONS.items():
        chemin = ecrire(nom, notes)
        print("%-8s %6d octets  %s" % (nom, chemin.stat().st_size, chemin))
    return 0


if __name__ == "__main__":
    sys.exit(main())
