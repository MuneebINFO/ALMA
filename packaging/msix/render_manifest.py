"""
Remplit Package.appxmanifest.template avec votre identite Partner Center et
ecrit le resultat dans PackageLayout/Package.appxmanifest.

Usage :
    python packaging/msix/render_manifest.py

Lit packaging/msix/identity.local.json (copie non versionnee de
identity.example.json -- voir packaging/msix/README.md pour l obtenir).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
IDENTITE = ICI / "identity.local.json"
MODELE = ICI / "Package.appxmanifest.template"
CIBLE = ICI / "PackageLayout" / "Package.appxmanifest"

# Cle du JSON -> jeton a remplacer dans le modele.
CHAMPS = {
    "package_name": "__PACKAGE_NAME__",
    "publisher": "__PUBLISHER__",
    "publisher_display_name": "__PUBLISHER_DISPLAY_NAME__",
    "app_display_name": "__APP_DISPLAY_NAME__",
    "app_description": "__APP_DESCRIPTION__",
    "version": "__VERSION__",
}


def main() -> int:
    if not IDENTITE.exists():
        print("Introuvable :", IDENTITE)
        print("Copiez identity.example.json en identity.local.json et "
              "remplissez-le avec votre identite Partner Center "
              "(voir packaging/msix/README.md).")
        return 1

    identite = json.loads(IDENTITE.read_text(encoding="utf-8"))
    texte = MODELE.read_text(encoding="utf-8")

    manquants = []
    for cle, jeton in CHAMPS.items():
        valeur = str(identite.get(cle, "")).strip()
        if not valeur or valeur.startswith("Votre") or "00000000" in valeur:
            manquants.append(cle)
        texte = texte.replace(jeton, valeur)

    if manquants:
        print("Ces champs de identity.local.json n'ont pas ete remplis (ou "
              "sont encore la valeur d'exemple) :", ", ".join(manquants))
        return 1

    CIBLE.parent.mkdir(parents=True, exist_ok=True)
    CIBLE.write_text(texte, encoding="utf-8")
    print("Manifeste ecrit :", CIBLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
