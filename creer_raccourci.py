"""
Cree un raccourci Windows pour lancer Alma comme une vraie application.

    python creer_raccourci.py            # raccourci dans le dossier du projet
    python creer_raccourci.py --bureau   # + un raccourci sur le Bureau

Le raccourci pointe vers pythonw.exe (binaire signe, donc autorise meme quand
Smart App Control est actif) et porte l icone de l application. Aucune fenetre
de console n apparait.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
NOM = "Alma.lnk"


def interpreteur_fenetre() -> Path:
    """pythonw.exe de l environnement virtuel, sinon celui du systeme."""
    candidat = RACINE / ".venv" / "Scripts" / "pythonw.exe"
    if candidat.exists():
        return candidat
    return Path(sys.executable).with_name("pythonw.exe")


def creer(destination: Path) -> Path:
    """Ecrit le raccourci .lnk via l API Windows (pywin32)."""
    from win32com.client import Dispatch

    shell = Dispatch("WScript.Shell")
    raccourci = shell.CreateShortCut(str(destination))
    raccourci.TargetPath = str(interpreteur_fenetre())
    raccourci.Arguments = '"' + str(RACINE / "gui.py") + '"'
    raccourci.WorkingDirectory = str(RACINE)
    raccourci.Description = "Alma - assistant personnel local"
    icone = RACINE / "assets" / "alma.ico"
    if icone.exists():
        raccourci.IconLocation = str(icone)
    raccourci.save()
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Cree le raccourci de lancement de Alma")
    parser.add_argument("--bureau", action="store_true", help="créer aussi un raccourci sur le Bureau")
    args = parser.parse_args()

    interpreteur = interpreteur_fenetre()
    if not interpreteur.exists():
        print("pythonw.exe est introuvable (" + str(interpreteur) + ").")
        print("Créez d abord l environnement : python -m venv .venv")
        return 1

    icone = RACINE / "assets" / "alma.ico"
    if not icone.exists():
        print("Icône absente, génération...")
        os.system('"' + sys.executable + '" "' + str(RACINE / "make_icon.py") + '"')

    try:
        cibles = [creer(RACINE / NOM)]
        if args.bureau:
            bureau = Path(os.path.expandvars("%USERPROFILE%")) / "Desktop"
            if bureau.is_dir():
                cibles.append(creer(bureau / NOM))
            else:
                print("Bureau introuvable : raccourci créé dans le projet uniquement.")
    except ImportError:
        print("pywin32 est requis : pip install pywin32")
        return 1

    for cible in cibles:
        print("Raccourci créé :", cible)
    print("\nDouble-cliquez dessus pour lancer Alma.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
