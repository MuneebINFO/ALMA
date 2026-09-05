"""
Genere l icone de l application (assets/alma.ico).

Dessine l orbe de Alma : un coeur lumineux entoure d anneaux, sur fond
sombre. Aucun fichier binaire a versionner : l icone est reproductible.

Usage : python make_icon.py
"""

from __future__ import annotations

from pathlib import Path

RACINE = Path(__file__).resolve().parent
CIBLE = RACINE / "assets" / "alma.ico"

FOND = (10, 14, 23, 255)
COEUR = (34, 211, 238, 255)      # cyan
ANNEAU = (129, 140, 248, 255)    # indigo


def dessiner(taille: int):
    from PIL import Image, ImageDraw

    # On dessine en 4x puis on reduit : bords lisses sans antialiasing manuel.
    echelle = 4
    grand = taille * echelle
    image = Image.new("RGBA", (grand, grand), (0, 0, 0, 0))
    dessin = ImageDraw.Draw(image)
    centre = grand / 2

    dessin.ellipse([0, 0, grand - 1, grand - 1], fill=FOND)

    for index, rayon_relatif in enumerate((0.44, 0.34)):
        rayon = grand * rayon_relatif
        epaisseur = max(1, int(grand * 0.022))
        opacite = 200 - index * 60
        dessin.ellipse(
            [centre - rayon, centre - rayon, centre + rayon, centre + rayon],
            outline=ANNEAU[:3] + (opacite,), width=epaisseur,
        )

    rayon_coeur = grand * 0.21
    dessin.ellipse(
        [centre - rayon_coeur, centre - rayon_coeur,
         centre + rayon_coeur, centre + rayon_coeur],
        fill=COEUR,
    )
    return image.resize((taille, taille), Image.LANCZOS)


def main() -> int:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Pillow est requis : pip install -r requirements.txt")
        return 1

    CIBLE.parent.mkdir(parents=True, exist_ok=True)
    tailles = (16, 24, 32, 48, 64, 128, 256)
    # On part de la PLUS GRANDE image : Pillow derive les autres tailles a
    # partir de celle-ci. Partir de la 16x16 donnerait une icone floue.
    base = dessiner(max(tailles))
    base.save(CIBLE, format="ICO", sizes=[(t, t) for t in tailles])
    print("Icone ecrite :", CIBLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
