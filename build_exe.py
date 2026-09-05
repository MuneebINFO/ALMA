"""
Construction de l executable Alma.exe.

Usage :
    pip install -r requirements-build.txt
    python build_exe.py              # application fenetree (Alma.exe)
    python build_exe.py --console    # ajoute aussi la version console

Le resultat se trouve dans dist/.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent

# Les modules de commandes sont importes dynamiquement : PyInstaller ne peut
# pas les deviner, il faut les declarer explicitement.
import commands  # noqa: E402

IMPORTS_CACHES = [
    "commands." + nom for nom in commands.MODULES
] + [
    # Dependances chargees a la demande dans le code (imports paresseux).
    "core.providers.claude_code_provider",
    "core.wake",
    "core.voice_neural",
    "edge_tts",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "comtypes",
    "pycaw",
    "pyaudio",
    "speech_recognition",
    "PIL.ImageGrab",
    "win32com.client",
    "pythoncom",
]

# Fichiers embarques dans l executable (separateur ";" sous Windows).
DONNEES = [
    ("config.yaml.example", "."),
    ("assets/alma.ico", "assets"),
]


def construire(nom: str, point_entree: str, fenetre: bool) -> int:
    argv = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        "--name", nom,
        "--windowed" if fenetre else "--console",
    ]
    icone = RACINE / "assets" / "alma.ico"
    if icone.exists():
        argv += ["--icon", str(icone)]
    for module in IMPORTS_CACHES:
        argv += ["--hidden-import", module]
    # Filet de securite : embarque tout le paquet de commandes.
    argv += ["--collect-submodules", "commands"]
    for source, cible in DONNEES:
        if (RACINE / source).exists():
            argv += ["--add-data", str(RACINE / source) + ";" + cible]
    argv.append(point_entree)

    print(">>", " ".join(argv[3:]))
    return subprocess.call(argv, cwd=str(RACINE))


def main() -> int:
    parser = argparse.ArgumentParser(description="Construit Alma.exe")
    parser.add_argument("--console", action="store_true",
                        help="construire aussi la version console (AlmaConsole.exe)")
    args = parser.parse_args()

    for dossier in ("build", "dist"):
        chemin = RACINE / dossier
        if chemin.exists():
            shutil.rmtree(chemin, ignore_errors=True)

    code = construire("Alma", "gui.py", fenetre=True)
    if code != 0:
        print("Echec de la construction de l application fenetree.")
        return code

    if args.console:
        code = construire("AlmaConsole", "main.py", fenetre=False)
        if code != 0:
            return code

    print("\nTermine. Executables disponibles dans :", RACINE / "dist")
    for fichier in sorted((RACINE / "dist").glob("*.exe")):
        taille = fichier.stat().st_size / (1024 * 1024)
        print("  " + fichier.name + "  (%.1f Mo)" % taille)
    return 0


if __name__ == "__main__":
    sys.exit(main())
