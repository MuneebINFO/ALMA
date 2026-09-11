"""
Genere les images requises par le Store (tuiles, icone de liste, ecran de
demarrage) a partir du MEME dessin que assets/alma.ico -- pas de fichier
binaire a maintenir a la main, juste a relancer ce script.

Usage : python packaging/msix/make_store_assets.py
Le resultat va dans packaging/msix/PackageLayout/Assets/ (ignore par git,
regenere a chaque build -- voir build_msix.ps1).
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE))

from make_icon import FOND, dessiner  # noqa: E402

CIBLE = Path(__file__).resolve().parent / "PackageLayout" / "Assets"

# Nom de fichier -> taille carree. Le jeu minimal exige par le Store pour une
# appli Desktop Bridge (Square44x44 pour la liste d applications,
# Square150x150 pour la tuile par defaut, StoreLogo pour la fiche du Store) ;
# les tuiles large/grande sont facultatives mais rendent mieux sur l ecran
# d accueil, donc on les fournit aussi puisqu elles ne coutent rien de plus.
CARRES = {
    "Square44x44Logo.png": 44,
    "Square71x71Logo.png": 71,
    "Square150x150Logo.png": 150,
    "Square310x310Logo.png": 310,
    "StoreLogo.png": 50,
}


def _sur_fond(image, largeur: int, hauteur: int):
    """Centre une image carree sur un canevas rectangulaire de la meme couleur
    de fond, pour les tuiles et l ecran de demarrage qui ne sont pas carres."""
    from PIL import Image

    canevas = Image.new("RGBA", (largeur, hauteur), FOND)
    x = (largeur - image.width) // 2
    y = (hauteur - image.height) // 2
    canevas.paste(image, (x, y), image)
    return canevas


def main() -> int:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Pillow est requis : pip install -r requirements.txt")
        return 1

    CIBLE.mkdir(parents=True, exist_ok=True)

    for nom, taille in CARRES.items():
        dessiner(taille).save(CIBLE / nom)

    # Tuile large (310x150) : l orbe a la taille de la petite dimension.
    orbe_large = dessiner(150)
    _sur_fond(orbe_large, 310, 150).save(CIBLE / "Square310x150Logo.png")

    # Ecran de demarrage (620x300), montre pendant le lancement de l appli.
    orbe_ecran = dessiner(220)
    _sur_fond(orbe_ecran, 620, 300).save(CIBLE / "SplashScreen.png")

    print("Images du Store ecrites dans :", CIBLE)
    for fichier in sorted(CIBLE.glob("*.png")):
        print("  " + fichier.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
