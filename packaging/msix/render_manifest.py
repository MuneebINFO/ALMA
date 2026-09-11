"""
Remplit Package.appxmanifest.template avec votre identite Partner Center et
ecrit le resultat dans PackageLayout/AppxManifest.xml (nom exige par
makeappx.exe -- pas celui du modele).

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
# makeappx.exe exige ce nom EXACT dans le dossier passe a /d -- « Package.
# appxmanifest » est la convention d un projet Visual Studio (qui le
# renomme lui-meme a la compilation), pas celle de makeappx en ligne de
# commande : sans ce nom precis, il refuse le paquet ("missing a required
# footprint file").
CIBLE = ICI / "PackageLayout" / "AppxManifest.xml"

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

    # makeappx accepte un XML mal forme sans le dire clairement (« '>'
    # attendu », sans numero de ligne utile) -- on le valide nous-memes ici,
    # avec un message qui dit vraiment ou est le probleme. Vu une fois pour
    # de vrai : deux tirets d affilee a l interieur d un commentaire XML,
    # pourtant courants dans la prose francaise du modele.
    import xml.etree.ElementTree as ET

    try:
        ET.fromstring(texte)
    except ET.ParseError as exc:
        print("Le manifeste rempli n'est pas un XML valide :", exc)
        print("(un commentaire <!-- ... --> ne peut jamais contenir deux "
              "tirets d'affilee ailleurs qu'a son ouverture/fermeture)")
        return 1

    CIBLE.parent.mkdir(parents=True, exist_ok=True)
    CIBLE.write_text(texte, encoding="utf-8")
    print("Manifeste ecrit :", CIBLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
