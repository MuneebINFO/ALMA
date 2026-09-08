"""
Diagnostic du mot d'appel : que comprend Alma quand vous l'appelez ?

    python diagnostic_appel.py

Appelez-la simplement par son nom, plusieurs fois, en marquant une pause
entre chaque. Le programme affiche, pour chaque essai, ce que la
reconnaissance vocale a réellement transcrit et si le nom a été reconnu.

À la fin, il propose les transcriptions à ajouter dans config.yaml si
certaines reviennent sans être reconnues.
"""

from __future__ import annotations

import sys
import time

ESSAIS = 6
DUREE_CALIBRATION = 1.2
TIMEOUT = 8.0


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
    from core import text_utils
    from core.stt import SpeechToText
    from core.wake import MoteurEcoute

    config = load_config()
    moteur = MoteurEcoute(config)
    stt = SpeechToText(config)

    print("=" * 66)
    print("  DIAGNOSTIC DU MOT D'APPEL — Alma")
    print("=" * 66)
    print("Nom attendu      : « %s »" % moteur.mot_appel)
    print("Seuil de mesure  : %.2f  (1.00 = correspondance exacte exigée)" % moteur.seuil)
    print("Orthographes acceptées : %s" % ", ".join(sorted(moteur.variantes)))

    if not stt.available:
        print("\nLa reconnaissance vocale est indisponible : " + (stt.error or "?"))
        return 1

    print("\n1) Calibration — ne parlez pas pendant %.1f seconde(s)..." % DUREE_CALIBRATION)
    seuil = stt.recalibrate(DUREE_CALIBRATION)
    print("   Seuil de déclenchement : %.5f" % seuil)

    print("\n2) Dites « %s », seul, %d fois. Marquez une pause entre chaque."
          % (moteur.mot_appel, ESSAIS))
    print("   (Ctrl+C pour arrêter avant la fin)\n")

    manques: list[str] = []
    reussites = 0
    try:
        for essai in range(1, ESSAIS + 1):
            print("   essai %d/%d — parlez..." % (essai, ESSAIS), end=" ", flush=True)
            debut = time.time()
            texte = stt.listen_live(timeout=TIMEOUT, phrase_limit=6.0)
            duree = time.time() - debut

            if not texte:
                print("rien compris  (%.1f s)" % duree)
                continue

            norme = text_utils.normalize(texte).strip()
            mots = text_utils.tokenize(norme)
            premier = mots[0] if mots else ""
            proximite = text_utils.similarity(premier, moteur.mot_appel)
            reconnu = moteur.separer_mot_appel(texte)[0]

            print("« %s »" % texte)
            print("        normalisé « %s » | 1er mot « %s » | ressemblance %.2f | %s"
                  % (norme, premier, proximite,
                     "RECONNU" if reconnu else "NON RECONNU"))
            if reconnu:
                reussites += 1
            elif premier:
                manques.append(premier)
    except KeyboardInterrupt:
        print("\n   (interrompu)")
    finally:
        stt.fermer()

    print("\n" + "=" * 66)
    print("  RÉSULTAT")
    print("=" * 66)
    print("  Reconnu : %d fois" % reussites)

    if not manques:
        if reussites:
            print("  Le nom est reconnu correctement. Rien à changer.")
        else:
            print("  Rien n'a été capté : lancez d'abord « python diagnostic_micro.py ».")
        return 0

    # On propose les transcriptions revenues au moins une fois.
    proposees = sorted(set(manques))
    print("  Transcriptions NON reconnues : %s" % ", ".join(proposees))
    print()
    print("  Ajoutez-les dans config.yaml pour qu'elles réveillent Alma :")
    print()
    print("    general:")
    print("      wake_variants:")
    for mot in proposees:
        print("        - %s" % mot)
    print()
    print("  N'y mettez que des mots que vous ne prononcez jamais autrement :")
    print("  chacun réveillera Alma à chaque fois qu'il sera entendu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
