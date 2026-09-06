"""
Diagnostic du micro : vérifie que Alma entend bien votre voix.

    python diagnostic_micro.py

Affiche un vu-mètre en direct. Parlez normalement : la barre doit franchir
le repère du seuil et la ligne passer au vert. À la fin, un verdict indique
si le réglage convient et, sinon, quoi changer dans config.yaml.
"""

from __future__ import annotations

import sys
import time

DUREE_CALIBRATION = 1.5
DUREE_TEST = 10.0


def barre(niveau: float, seuil: float, largeur: int = 46) -> str:
    """Vu-mètre texte, avec un repère « | » à la position du seuil."""
    echelle = max(seuil * 6, 0.05)
    rempli = int(min(1.0, niveau / echelle) * largeur)
    position_seuil = int(min(1.0, seuil / echelle) * largeur)
    cases = []
    for i in range(largeur):
        if i == position_seuil:
            cases.append("|")
        elif i < rempli:
            cases.append("#")
        else:
            cases.append(".")
    return "".join(cases)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        import pyaudio  # noqa: F401
    except ImportError:
        print("PyAudio n'est pas installé. Depuis Windows (pas WSL) :")
        print("    pip install -r requirements-voice.txt")
        return 1

    from config import load_config
    from core.stt import CHUNK, SAMPLE_RATE, LevelMeterListener, _rms

    config = load_config()
    ecouteur = LevelMeterListener(
        plancher=config.get("voice.min_threshold", None),
        facteur=config.get("voice.noise_factor", None),
    )

    print("=" * 62)
    print("  DIAGNOSTIC DU MICRO — Alma")
    print("=" * 62)

    # Périphérique utilisé
    import pyaudio

    from core.stt import _flux_plausible, choisir_peripherique, peripheriques_entree

    audio = pyaudio.PyAudio()
    candidats = peripheriques_entree(audio)
    if not candidats:
        print("ATTENTION : aucun micro détecté.")
        audio.terminate()
        return 1

    print()
    print("Micros disponibles (du plus prometteur au moins) :")
    for index, nom, taux in candidats:
        etat = "exploitable" if _flux_plausible(audio, index, taux) else "inutilisable"
        print("  [%2d] %-42s %6d Hz  %s" % (index, nom[:42], taux, etat))

    choisi, taux = choisir_peripherique(audio, config.get("voice.input_device"))
    nom_choisi = next((n for i, n, _t in candidats if i == choisi), "?")
    print()
    print("Micro retenu : [" + str(choisi) + "] " + nom_choisi + " à " + str(taux) + " Hz")
    print("Pour en imposer un autre, mettez son numéro dans config.yaml :")
    print("    voice:")
    print("      input_device: <numéro>")
    audio.terminate()

    print("\n1) Calibration — ne parlez pas pendant %.1f secondes..." % DUREE_CALIBRATION)
    seuil = ecouteur.calibrate(DUREE_CALIBRATION)
    print("   Bruit de fond : %.5f" % ecouteur.ambient)
    print("   Seuil retenu  : %.5f" % seuil)

    print("\n2) PARLEZ MAINTENANT, normalement, pendant %.0f secondes." % DUREE_TEST)
    print("   (dites par exemple : « Alma, quelle heure est-il »)\n")

    audio = pyaudio.PyAudio()
    flux = audio.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                      input=True, frames_per_buffer=CHUNK)
    pic = 0.0
    blocs_actifs = 0
    total = 0
    fin = time.time() + DUREE_TEST
    try:
        while time.time() < fin:
            niveau = _rms(flux.read(CHUNK, exception_on_overflow=False))
            pic = max(pic, niveau)
            total += 1
            actif = niveau > seuil
            blocs_actifs += 1 if actif else 0
            etat = "VOIX DETECTEE" if actif else "silence      "
            print("\r   [%s] %.4f  %s" % (barre(niveau, seuil), niveau, etat), end="", flush=True)
    finally:
        flux.stop_stream()
        flux.close()
        audio.terminate()

    proportion = (blocs_actifs / total * 100) if total else 0
    print("\n\n" + "=" * 62)
    print("  RÉSULTAT")
    print("=" * 62)
    print("  Niveau maximum atteint : %.5f" % pic)
    print("  Seuil de déclenchement : %.5f" % seuil)
    print("  Blocs au-dessus du seuil : %.0f%%" % proportion)
    print()

    if pic < seuil:
        print("  ÉCHEC : votre voix n'a jamais franchi le seuil.")
        print("  Le micro capte trop faiblement. À faire, dans l'ordre :")
        print("    1. Windows : Paramètres > Système > Son > Microphone,")
        print("       montez le volume d'entrée à 100 et activez le boost si présent.")
        print("    2. Rapprochez-vous du micro.")
        print("    3. Sinon, abaissez le seuil dans config.yaml :")
        print("         voice:")
        print("           min_threshold: %.5f" % max(0.0008, pic * 0.35))
        return 1
    if proportion < 5:
        print("  LIMITE : la voix passe le seuil, mais rarement.")
        print("  Abaissez un peu le seuil dans config.yaml :")
        print("         voice:")
        print("           min_threshold: %.5f" % max(0.0008, pic * 0.30))
        return 0

    print("  SUCCÈS : votre voix est détectée correctement.")
    print("  Marge : votre voix est %.1fx au-dessus du seuil." % (pic / seuil))
    print("  Alma devrait vous entendre sans réglage supplémentaire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
