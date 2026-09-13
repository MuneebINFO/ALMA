"""
Alma - assistant personnel local pour Windows.

Modes de lancement :
    python main.py                     mode texte (par defaut)
    python main.py --voice             mode voix (micro + synthese vocale)
    python main.py -c "ouvre Chrome"   execution d une seule commande
    python main.py --list-commands     liste toutes les commandes

Aucune IA generative distante n est utilisee : le cerveau est un moteur de
regles local (voir core/router.py).
"""

from __future__ import annotations

import argparse
import logging
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alma",
        description="Assistant personnel local (texte et voix), sans IA payante.",
    )
    parser.add_argument("--voice", action="store_true", help="activer le mode voix (micro)")
    parser.add_argument("--no-voice", action="store_true", help="forcer le mode texte")
    parser.add_argument("--mute", action="store_true", help="ne pas lire les reponses a voix haute")
    parser.add_argument("--speak", action="store_true", help="lire les reponses a voix haute")
    parser.add_argument("--config", metavar="FICHIER", help="chemin d un fichier de configuration")
    parser.add_argument("-c", "--command", metavar="TEXTE", help="executer une commande puis quitter")
    parser.add_argument("--list-commands", action="store_true", help="lister les commandes puis quitter")
    parser.add_argument("--list-voices", action="store_true", help="lister les voix installees puis quitter")
    parser.add_argument("--debug", action="store_true", help="afficher les logs de debogage")
    return parser


def configure_console() -> None:
    """Force l UTF-8 sur la sortie console (accents et guillemets francais)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    configure_console()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    from config import load_config
    from core.assistant import Assistant
    from core.registry import by_category, load_commands

    config = load_config(args.config)

    # Les options de ligne de commande priment sur config.yaml.
    if args.voice:
        config.set("voice.enabled", True)
    if args.no_voice:
        config.set("voice.enabled", False)
    if args.mute:
        config.set("voice.speak_responses", False)
    if args.speak:
        config.set("voice.speak_responses", True)

    if args.list_commands:
        load_commands()
        for category, commands in sorted(by_category().items()):
            print("\n[" + category + "]")
            for cmd in commands:
                example = ("   ex: " + cmd.examples[0]) if cmd.examples else ""
                print("  - " + (cmd.description or cmd.name) + example)
        return 0

    assistant = Assistant(config=config)

    if args.list_voices:
        voices = assistant.tts.list_voices()
        if not voices:
            print("Aucune voix disponible (pyttsx3 est-il installe ?).")
        for voice_id, name in voices:
            print(name + "\n    voice_id: " + voice_id)
        return 0

    # Mode une seule commande : pratique pour les raccourcis Windows.
    if args.command:
        response = assistant.handle_and_emit(args.command)
        assistant.shutdown()
        return 0 if response.ok else 1

    # Choix de la source d entree.
    if config.get("voice.enabled", False):
        from core.input_sources import VoiceInput
        from core.stt import SpeechToText

        stt = SpeechToText(config)
        assistant.stt = stt
        if stt.available:
            print("[mode voix] Parlez apres le signal. (Ctrl+C pour quitter)")
            stt.calibrate()
            assistant.io = VoiceInput(stt, assistant.tts)
        else:
            print("[mode voix indisponible] " + (stt.error or "micro introuvable"))
            print("[repli] Mode texte activé.")
    else:
        print("[mode texte] Tapez votre demande. « aide » pour la liste, « quitte » pour sortir.")

    # Le premier lancement passe avant tout le reste : sans lui, Alma ne sait
    # ni comment vous appeler, ni comment vous l appelez.
    from core import premier_lancement

    if premier_lancement.est_necessaire(config):
        premier_lancement.poser_en_texte(
            assistant, lambda invite: assistant.io.read(invite), print)

    assistant.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
