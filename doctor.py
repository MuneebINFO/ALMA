"""
Diagnostic complet d'ALMA : qu'est-ce qui marche, qu'est-ce qui manque.

    python doctor.py

Vérifie toute la chaîne — Python, dépendances, micro, transcription, voix,
écrans, navigateur, applications, extension IA — et dit quoi corriger pour
chaque manque. Ne lance rien : il regarde.

Les deux autres diagnostics restent utiles quand celui-ci pointe un problème :
`diagnostic_micro.py` mesure votre voix en direct, `diagnostic_appel.py`
montre ce que la reconnaissance entend quand vous prononcez le nom.
"""

from __future__ import annotations

import sys

RESULTATS = {"ok": 0, "manque": 0, "note": 0}


def titre(texte: str) -> None:
    print()
    print(texte)
    print("-" * len(texte))


def ok(message: str) -> None:
    print("  [ok]    " + message)
    RESULTATS["ok"] += 1


def manque(message: str, remede: str = "") -> None:
    print("  [MANQUE] " + message)
    if remede:
        print("           -> " + remede)
    RESULTATS["manque"] += 1


def note(message: str, remede: str = "") -> None:
    print("  [note]  " + message)
    if remede:
        print("           -> " + remede)
    RESULTATS["note"] += 1


def info(message: str) -> None:
    print("          " + message)


# --------------------------------------------------------------------------
def verifier_python() -> None:
    titre("Python")
    version = sys.version_info
    lisible = "%d.%d.%d" % (version.major, version.minor, version.micro)
    if version >= (3, 11):
        ok("Python " + lisible)
    else:
        manque("Python " + lisible + " : trop ancien",
               "Alma demande Python 3.11 ou plus récent.")
    if sys.platform != "win32":
        manque("Système « " + sys.platform + " »",
               "Alma pilote Windows : micro, volume, fenêtres, applications. "
               "Depuis WSL, rien de tout cela n'existe.")
    else:
        ok("Windows")


def verifier_dependances() -> None:
    titre("Dépendances")
    requises = [
        ("yaml", "PyYAML", "lecture de config.yaml"),
        ("requests", "requests", "météo"),
        ("psutil", "psutil", "identification des fenêtres"),
        ("PIL", "Pillow", "captures d'écran"),
    ]
    vocales = [
        ("pyaudio", "PyAudio", "micro"),
        ("speech_recognition", "SpeechRecognition", "transcription"),
        ("pyttsx3", "pyttsx3", "voix locale de secours"),
        ("edge_tts", "edge-tts", "voix neuronale"),
    ]
    facultatives = [
        ("comtypes", "comtypes", "clic et lecture des pages"),
        ("pycaw", "pycaw", "volume Windows"),
        ("winsdk", "winsdk", "pause par application"),
        ("faster_whisper", "faster-whisper", "transcription locale (facultative)"),
    ]
    for modules, remede in ((requises, "pip install -r requirements.txt"),
                            (vocales, "pip install -r requirements-voice.txt")):
        for module, paquet, role in modules:
            if _importable(module):
                ok("%-22s %s" % (paquet, role))
            else:
                manque("%-22s %s" % (paquet, role), remede)
    for module, paquet, role in facultatives:
        if _importable(module):
            ok("%-22s %s" % (paquet, role))
        else:
            note("%-22s %s : absent" % (paquet, role), "pip install " + paquet)


def _importable(nom: str) -> bool:
    if nom == "faster_whisper":
        return _whisper_utilisable()
    try:
        __import__(nom)
        return True
    except Exception:
        return False


def _whisper_utilisable() -> bool:
    """
    Whisper s importe-t-il ?

    Son paquet charge `av`, qui ne sert qu a DECODER DES FICHIERS audio -- ce
    dont Alma n a pas besoin, puisqu elle fournit du PCM brut. Sur une machine
    ou le controle d application de Windows bloque cette DLL, le paquet est
    pourtant installe et parfaitement utilisable. On teste donc comme le code
    l utilise reellement.
    """
    import types

    if "av" not in sys.modules:
        try:
            import av  # noqa: F401
        except Exception:
            sys.modules["av"] = types.ModuleType("av")
    try:
        from faster_whisper.transcribe import WhisperModel  # noqa: F401

        return True
    except Exception:
        return False


def verifier_micro(config) -> None:
    titre("Micro")
    try:
        import pyaudio
    except ImportError:
        manque("PyAudio absent : Alma ne peut pas entendre",
               "pip install -r requirements-voice.txt")
        return
    audio = pyaudio.PyAudio()
    try:
        peripherique = audio.get_default_input_device_info()
        ok("Entrée par défaut : " + str(peripherique["name"]))
    except Exception:
        manque("Aucun micro par défaut dans Windows",
               "Paramètres > Système > Son > Entrée.")
        return
    finally:
        audio.terminate()

    from core.stt import LevelMeterListener

    ecouteur = LevelMeterListener(
        plancher=config.get("voice.min_threshold", None),
        facteur=config.get("voice.noise_factor", None),
    )
    seuil = ecouteur.calibrate(1.0)
    ecouteur.fermer()
    info("bruit ambiant %.5f, pic %.5f" % (ecouteur.ambient, ecouteur.pic_calibration))
    if seuil >= LevelMeterListener.SEUIL_MAX:
        manque("Seuil au plafond (%.4f) : il faudrait crier" % seuil,
               "La pièce est bruyante, ou le micro capte un souffle constant.")
    elif seuil > 0.01:
        note("Seuil élevé (%.4f)" % seuil,
             "Normal dans une pièce bruyante. Sinon, montez le volume d'entrée.")
    else:
        ok("Seuil de déclenchement %.4f" % seuil)


def verifier_transcription(config) -> None:
    titre("Transcription")
    moteur = str(config.get("voice.stt_engine", "google") or "google")
    if moteur == "google":
        ok("Moteur « google » : rapide (environ 200 ms)")
        note("Votre audio est envoyé à Google",
             "Pour que tout reste sur la machine : voice.stt_engine: whisper")
    elif moteur == "whisper":
        if _importable("faster_whisper"):
            taille = config.get("voice.whisper_model", "small")
            ok("Moteur « whisper » (" + str(taille) + ") : tout reste sur la machine")
            note("Comptez une trentaine de secondes au démarrage, "
                 "puis 1 à 3 s par phrase.")
        else:
            manque("Moteur « whisper » demandé mais faster-whisper est absent",
                   "pip install faster-whisper")
    elif moteur == "vosk":
        chemin = str(config.get("voice.vosk_model_path", "") or "")
        if chemin and _importable("vosk"):
            ok("Moteur « vosk » : " + chemin)
        else:
            manque("Moteur « vosk » mal configuré",
                   "Renseignez voice.vosk_model_path et installez vosk.")
    else:
        manque("Moteur de transcription inconnu : " + moteur,
               "Valeurs acceptées : google, whisper, vosk.")


def verifier_voix(config) -> None:
    titre("Voix")
    if not _importable("edge_tts"):
        note("edge-tts absent : voix locale seulement (plus robotique)",
             "pip install edge-tts")
    else:
        ok("Voix neuronale disponible (" + str(config.get("voice.neural_voice", "?")) + ")")
    if _importable("pyttsx3"):
        ok("Voix locale de secours (SAPI5)")
    else:
        manque("pyttsx3 absent : aucune voix de secours hors ligne",
               "pip install -r requirements-voice.txt")


def verifier_mot_appel(config) -> None:
    titre("Mot d'appel")
    from core.wake import MoteurEcoute

    moteur = MoteurEcoute(config)
    ok("Nom « " + moteur.mot_appel + " », " + str(len(moteur.variantes)) + " orthographes acceptées")
    if moteur.tolere_seul:
        ok("À-peu-près toléré quand le nom est dit seul")
    else:
        note("Tolérance désactivée : la transcription doit être exacte",
             "general.wake_tolerate_alone: true pour la réactiver.")
    if moteur.prefixe_obligatoire:
        note("Un préfixe est exigé : « OK " + moteur.mot_appel + " »")


def verifier_ecrans() -> None:
    titre("Écrans")
    from core import desktop

    ecrans = desktop.ecrans()
    if not ecrans:
        manque("Aucun écran détecté")
        return
    for ecran in desktop.ecrans_physiques():
        ok("écran %d : %d x %d en %s" % (ecran.index, ecran.largeur,
                                         ecran.hauteur, ecran.rect[:2]))
    if len(ecrans) > 1:
        info("« va sur l'écran 2 » fixe l'écran de travail.")


def verifier_navigateur() -> None:
    titre("Navigateur")
    from core import browser_tabs, desktop, interaction

    fenetres = [f for f in desktop.fenetres() if f.est_navigateur]
    if not fenetres:
        note("Aucun navigateur ouvert : clic et recherche non vérifiables ici")
        return
    ok("%d fenêtre(s) de navigateur" % len(fenetres))
    fenetre = fenetres[0]
    if browser_tabs._client()[0] is None:
        manque("API d'accessibilité indisponible : ni clic ni lecture de page",
               "pip install comtypes")
        return
    ok("API d'accessibilité disponible")
    if interaction.zone_page(fenetre) is None:
        note("Zone de page introuvable sur « " + fenetre.titre[:32] + " »")
    else:
        ok("Zone de page délimitée (les onglets sont exclus des clics)")
    adresse = browser_tabs.adresse_courante(fenetre)
    if adresse:
        ok("Adresse lisible : " + adresse[:44])
    else:
        note("Barre d'adresse illisible : le titre servira de repli")


def verifier_applications() -> None:
    titre("Applications")
    from core import applications

    menu = applications.raccourcis_du_menu()
    if menu:
        ok("%d raccourcis dans le menu Démarrer" % len(menu))
    else:
        manque("Menu Démarrer illisible : « ouvre X » sera limité à config.yaml")
    systeme = applications.applications_du_systeme()
    if systeme:
        ok("%d applications connues du système (dont le Store)" % len(systeme))
    else:
        note("Liste du système indisponible : les applis du Store seront manquées")


def verifier_ia(config) -> None:
    titre("Extension IA")
    actif = bool(config.get("ai_fallback.enabled", False))
    provider = str(config.get("ai_fallback.provider", "none") or "none")
    if not actif:
        ok("Désactivée : aucun appel, aucun coût (provider prêt : " + provider + ")")
        return
    if provider == "ollama":
        from core.providers.ollama_provider import OllamaProvider

        souci = OllamaProvider(config).diagnostic()
        if souci:
            manque("Ollama : " + souci)
        else:
            ok("Modèle local prêt (" + str(config.get("ai_fallback.ollama.modele")) + ")")
    elif provider == "claude_code":
        from core.providers.claude_code_provider import ClaudeCodeProvider

        provider_cc = ClaudeCodeProvider(config)
        problemes = provider_cc.check()
        if problemes:
            for probleme in problemes:
                manque(probleme)
        else:
            ok("CLI Claude Code prêt, périmètre : " + str(provider_cc.resolve_working_dir()))
            connecte, methode = provider_cc.connexion()
            if connecte:
                ok("CLI connecté (" + (methode or "compte Anthropic") + ")")
            elif connecte is None:
                note("État de connexion du CLI illisible ; il sera vérifié au premier appel")
            else:
                # Le compte de l application Claude et celui du CLI sont deux
                # connexions distinctes : l une peut etre ouverte et l autre non.
                # Le chemin du binaire est affiche : c est ce qui permet de
                # voir qu on s est connecte ailleurs -- dans WSL, par exemple,
                # alors qu ALMA appelle celui de Windows.
                manque("CLI non connecté : " + provider_cc.resolve_command())
                note("Lancez « claude auth login » DANS UN TERMINAL WINDOWS. Ni la "
                     "connexion de l'application Claude, ni celle d'un CLI sous WSL "
                     "ne valent pour ce binaire.")
        if provider_cc.api_key_detected():
            note("ANTHROPIC_API_KEY est définie : facturation API au lieu de l'abonnement")
    else:
        note("Provider « " + provider + " » : rien à vérifier")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=" * 66)
    print("  DIAGNOSTIC — ALMA")
    print("=" * 66)

    from config import load_config

    config = load_config()

    for verification, arguments in (
        (verifier_python, ()),
        (verifier_dependances, ()),
        (verifier_micro, (config,)),
        (verifier_transcription, (config,)),
        (verifier_voix, (config,)),
        (verifier_mot_appel, (config,)),
        (verifier_ecrans, ()),
        (verifier_navigateur, ()),
        (verifier_applications, ()),
        (verifier_ia, (config,)),
    ):
        try:
            verification(*arguments)
        except Exception as exc:
            titre(verification.__name__.replace("verifier_", "").capitalize())
            manque("Vérification impossible : " + type(exc).__name__ + " " + str(exc)[:70])

    print()
    print("=" * 66)
    print("  %d vérifications passées, %d manques, %d remarques"
          % (RESULTATS["ok"], RESULTATS["manque"], RESULTATS["note"]))
    if RESULTATS["manque"] == 0:
        print("  Rien ne bloque.")
    return 1 if RESULTATS["manque"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
